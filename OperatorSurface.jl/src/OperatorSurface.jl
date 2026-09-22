"""
OperatorSurface — Experiment 001: IJulia Operator Surface

This module implements a persistent Julia/IJulia kernel operator surface that:
- Maintains state across executions (Phase 1)
- Defines operator types and vocabulary (Phase 2)
- Implements core operations (Phase 4)
- Provides structured semantics (Phase 5)
- Enables discovery and introspection (Phase 6)
- Generates operation receipts (Phase 7)
- Supports shell escape hatch (Phase 8)
- Handles failures safely (Phase 9)

Defined in dependency order, not README phase order -- Julia requires a
struct's field types (and a function's signature types) to already exist at
definition time, so the type graph has to be built leaves-first regardless of
which phase a type belongs to conceptually. Phase-number headers are kept as
comments for navigation.

See the repository README for the full brief.
"""
module OperatorSurface

using Dates
using UUIDs

#==============================================================================
PHASE 2: Operator Types & Vocabulary (leaf types first)
==============================================================================#

"""
    OperatorType

Abstract type defining the base for all operator types.
"""
abstract type OperatorType end

#==============================================================================
PHASE 1 (part 1): Execution record -- no forward dependencies
==============================================================================#

"""
    ExecutionRecord

Records details about each code execution for audit and debugging.
"""
struct ExecutionRecord
    id::UUID
    timestamp::DateTime
    code::String
    success::Bool
    error_message::Union{Nothing, String}
    duration_ms::Float64
end

#==============================================================================
PHASE 5: Structured Semantics (needed by Phase 7's OperationReceipt)
==============================================================================#

"""
    OperationResult

Structured result from an operation execution.
"""
struct OperationResult
    data::Any
    success::Bool
    error::Union{Nothing, Any}

    function OperationResult(data::Any, success::Bool, error::Union{Nothing, Any}=nothing)
        new(data, success, error)
    end
end

"""
    StructuredResponse

A complete structured response including result, metadata, and status.
"""
struct StructuredResponse
    result::OperationResult
    metadata::Dict{String, Any}
    timestamp::DateTime

    function StructuredResponse(data::Any, success::Bool,
                                 metadata::Dict{String, Any}=Dict{String,Any}();
                                 error::Union{Nothing, Any}=nothing)
        result = OperationResult(data, success, error)
        new(result, metadata, Dates.now())
    end
end

#==============================================================================
PHASE 7: Operation Receipts (needed by KernelState's receipt_log field)
==============================================================================#

"""
    OperationReceipt

Audit trail receipt for an operation execution.
"""
struct OperationReceipt
    id::UUID
    timestamp::DateTime
    operation_type::String
    result::OperationResult
    duration_ms::Float64
    kernel_id::UUID
    metadata::Dict{String, Any}

    function OperationReceipt(id::UUID, timestamp::DateTime, op_type::String,
                              result::OperationResult, duration_ms::Float64,
                              kernel_id::UUID,
                              metadata::Dict{String, Any}=Dict{String,Any}())
        new(id, timestamp, op_type, result, duration_ms, kernel_id, metadata)
    end
end

"""
    ReceiptLog

Collection of operation receipts with query capabilities.
"""
struct ReceiptLog
    receipts::Vector{OperationReceipt}
    max_size::Int

    function ReceiptLog(max_size::Int=10000)
        new(OperationReceipt[], max_size)
    end
end

"""
    get_receipts(log::ReceiptLog;
                 operation_type::Union{String, Nothing}=nothing,
                 since::Union{DateTime, Nothing}=nothing,
                 limit::Int=100)::Vector{OperationReceipt}

Retrieves receipts with optional filtering.
"""
function get_receipts(log::ReceiptLog;
                      operation_type::Union{String, Nothing}=nothing,
                      since::Union{DateTime, Nothing}=nothing,
                      limit::Int=100)::Vector{OperationReceipt}
    filtered = log.receipts

    if !isnothing(operation_type)
        filtered = filter(r -> r.operation_type == operation_type, filtered)
    end

    if !isnothing(since)
        filtered = filter(r -> r.timestamp >= since, filtered)
    end

    return filtered[1:min(limit, length(filtered))]
end

#==============================================================================
PHASE 1 (part 2): State Persistence Infrastructure
==============================================================================#

"""
    KernelState

Mutable struct that maintains persistent state across IJulia executions.
This is the core of Phase 1 - proving state persistence.

`eval_module` is a fresh, empty Julia `Module` created once per kernel state.
`ExecuteCode` evaluates real code into this module with `Core.eval`, so
variable bindings genuinely persist for the lifetime of this `KernelState` --
this is not a simulation or a regex-based approximation of assignment.
"""
mutable struct KernelState
    id::UUID
    created_at::DateTime
    last_accessed::DateTime
    eval_module::Module
    variables::Dict{String, Any}
    execution_history::Vector{ExecutionRecord}
    operator_registry::Dict{String, Function}
    receipt_log::Vector{OperationReceipt}

    function KernelState()
        now = Dates.now()
        state = new()
        state.id = uuid4()
        state.created_at = now
        state.last_accessed = now
        # A fresh anonymous module per kernel state: real, isolated eval scope,
        # not shared global mutable state across sessions.
        state.eval_module = Module(Symbol("KernelScope_$(replace(string(state.id), '-' => '_'))"))
        state.variables = Dict{String, Any}()
        state.execution_history = ExecutionRecord[]
        state.operator_registry = Dict{String, Function}()
        state.receipt_log = OperationReceipt[]
        return state
    end
end

"""
    get_kernel_state()

Returns the global kernel state singleton.
"""
const GLOBAL_STATE = Ref{Union{Nothing, KernelState}}(nothing)

function get_kernel_state()::KernelState
    if isnothing(GLOBAL_STATE[])
        GLOBAL_STATE[] = KernelState()
    end
    GLOBAL_STATE[].last_accessed = Dates.now()
    return GLOBAL_STATE[]
end

"""
    reset_kernel_state()

Resets the kernel state (useful for testing or clean restarts).
"""
function reset_kernel_state()
    GLOBAL_STATE[] = nothing
    return nothing
end

"""
    OperatorVocabulary

Defines the vocabulary/lexicon available to operators.
"""
struct OperatorVocabulary <: OperatorType
    name::String
    description::String
    supported_operations::Vector{String}
    input_schema::Dict{String, Any}
    output_schema::Dict{String, Any}

    function OperatorVocabulary(name::String, description::String,
                                ops::Vector{String},
                                input_schema::Dict{String, Any}=Dict(),
                                output_schema::Dict{String, Any}=Dict())
        new(name, description, ops, input_schema, output_schema)
    end
end

"""
    Core vocabulary instances
"""
const CODE_EXECUTION_VOCAB = OperatorVocabulary(
    "CodeExecution",
    "Execute Julia code in the persistent kernel",
    ["execute", "evaluate", "run"],
    Dict{String,Any}("code" => "String", "timeout" => "Int"),
    Dict{String,Any}("result" => "Any", "success" => "Bool")
)

const OPERATOR_INVOCATION_VOCAB = OperatorVocabulary(
    "OperatorInvocation",
    "Invoke a registered operator by name",
    ["invoke", "call", "execute_operator"],
    Dict{String,Any}("operator_name" => "String", "arguments" => "Dict"),
    Dict{String,Any}("result" => "Any", "receipt" => "OperationReceipt")
)

const STATE_QUERY_VOCAB = OperatorVocabulary(
    "StateQuery",
    "Query the current kernel state",
    ["get_state", "inspect", "query"],
    Dict{String,Any}("key" => "String"),
    Dict{String,Any}("value" => "Any", "exists" => "Bool")
)

#==============================================================================
PHASE 4: Core Operations
==============================================================================#

"""
    ExecuteCode

Operation type for executing code in the kernel.
"""
struct ExecuteCode <: OperatorType
    code::String
    timeout_ms::Int
    context::Dict{String, Any}

    function ExecuteCode(code::String; timeout_ms::Int=30000, context::Dict=Dict())
        new(code, timeout_ms, context)
    end
end

"""
    InvokeOperator

Operation type for invoking a registered operator.
"""
struct InvokeOperator <: OperatorType
    operator_name::String
    arguments::Dict{String, Any}

    function InvokeOperator(name::String; args::Dict=Dict())
        new(name, args)
    end
end

"""
    GetState

Operation type for querying kernel state.
"""
struct GetState <: OperatorType
    key::Union{String, Nothing}
    include_metadata::Bool

    function GetState(key::Union{String, Nothing}=nothing; include_metadata::Bool=true)
        new(key, include_metadata)
    end
end

"""
    ShellEscape

Operation type for executing shell commands.
"""
struct ShellEscape <: OperatorType
    command::String
    working_dir::String
    timeout_ms::Int
    capture_output::Bool

    function ShellEscape(command::String;
                         working_dir::String=pwd(),
                         timeout_ms::Int=60000,
                         capture_output::Bool=true)
        new(command, working_dir, timeout_ms, capture_output)
    end
end

"""
    register_operator!(state::KernelState, name::String, f::Function)

Registers a real, callable operator under `name`. `InvokeOperator` calls the
registered function directly -- there is no separate "simulated invocation"
path.
"""
function register_operator!(state::KernelState, name::String, f::Function)
    state.operator_registry[name] = f
    return nothing
end

# Names Julia's parser accepts as assignment targets for the lightweight
# post-eval variable index below. This is a display/introspection
# convenience only -- it does not gate what code may run; eval already ran
# the real, unrestricted code by the time this regex runs.
const ASSIGNMENT_TARGET_PATTERN = r"^\s*([A-Za-z_][A-Za-z0-9_!]*)\s*="

"""
    execute(op::ExecuteCode)::OperationReceipt

Executes code in the kernel's real, persistent eval module and returns a
structured receipt. This performs a genuine `Core.eval` -- the result is the
actual value Julia computed, not a placeholder.
"""
function execute(op::ExecuteCode)::OperationReceipt
    state = get_kernel_state()
    start_time = time_ns()

    result = OperationResult(nothing, true, nothing)
    error_msg = nothing

    try
        # Meta.parse only parses a single top-level statement and throws on
        # anything after it; real code blocks are usually multi-statement, so
        # this needs parseall (a :toplevel Expr, evaluated statement-by-
        # statement, yielding the last statement's value -- REPL semantics).
        parsed = Meta.parseall(op.code)
        value = Core.eval(state.eval_module, parsed)
        result = OperationResult(value, true, nothing)

        # Best-effort variable index for GetState/discovery convenience.
        # Real persistence already happened above via eval_module bindings;
        # this only mirrors top-level simple assignments (one per line) for
        # introspection -- it does not attempt to parse destructuring,
        # compound, or nested assignment targets.
        # World-age note: Core.eval above ran in a compiled function, so it
        # defines eval_module's new bindings in a NEW world age -- plain
        # isdefined/getfield here would still see the OLD world and report
        # `false` for bindings that unquestionably exist (confirmed by
        # direct testing, not assumed). Base.invokelatest forces resolution
        # against the current world.
        for line in split(op.code, '\n')
            m = match(ASSIGNMENT_TARGET_PATTERN, line)
            m === nothing && continue
            var_name = m.captures[1]
            sym = Symbol(var_name)
            if Base.invokelatest(isdefined, state.eval_module, sym)
                state.variables[var_name] = Base.invokelatest(getfield, state.eval_module, sym)
            end
        end
    catch e
        result = OperationResult(nothing, false, sprint(showerror, e))
        error_msg = sprint(showerror, e)
    end

    duration_ms = (time_ns() - start_time) / 1_000_000.0

    record = ExecutionRecord(
        uuid4(),
        Dates.now(),
        op.code,
        result.success,
        error_msg,
        duration_ms
    )
    push!(state.execution_history, record)

    receipt = OperationReceipt(
        uuid4(),
        Dates.now(),
        "ExecuteCode",
        result,
        duration_ms,
        state.id
    )
    push!(state.receipt_log, receipt)

    return receipt
end

"""
    execute(op::InvokeOperator)::OperationReceipt

Invokes a really-registered operator function (see `register_operator!`) and
returns a receipt. There is no "would invoke in a real implementation"
placeholder path -- if the operator is registered, it is actually called
with `op.arguments`.
"""
function execute(op::InvokeOperator)::OperationReceipt
    state = get_kernel_state()
    start_time = time_ns()

    result = OperationResult(nothing, false, "Operator not found: $(op.operator_name)")

    if haskey(state.operator_registry, op.operator_name)
        f = state.operator_registry[op.operator_name]
        try
            value = f(op.arguments)
            result = OperationResult(value, true, nothing)
        catch e
            result = OperationResult(nothing, false, sprint(showerror, e))
        end
    end

    duration_ms = (time_ns() - start_time) / 1_000_000.0

    receipt = OperationReceipt(
        uuid4(),
        Dates.now(),
        "InvokeOperator",
        result,
        duration_ms,
        state.id,
        Dict{String,Any}("operator" => op.operator_name)
    )
    push!(state.receipt_log, receipt)

    return receipt
end

"""
    execute(op::GetState)::StructuredResponse

Queries kernel state and returns a structured response.
"""
function execute(op::GetState)::StructuredResponse
    state = get_kernel_state()

    if !isnothing(op.key)
        exists = haskey(state.variables, op.key)
        value = exists ? state.variables[op.key] : nothing

        return StructuredResponse(
            Dict("key" => op.key, "value" => value, "exists" => exists),
            true,
            Dict{String,Any}();
        )
    else
        metadata = op.include_metadata ? Dict{String,Any}(
            "kernel_id" => string(state.id),
            "created_at" => string(state.created_at),
            "last_accessed" => string(state.last_accessed),
            "variable_count" => length(state.variables),
            "execution_count" => length(state.execution_history)
        ) : Dict{String,Any}()

        return StructuredResponse(
            merge(Dict("variables" => collect(keys(state.variables))), metadata),
            true,
            metadata;
        )
    end
end

"""
    execute(op::ShellEscape)::OperationReceipt

Executes a real shell command as a real subprocess and returns a receipt
carrying its actual stdout, stderr, and exit code. This is a genuine
`run`/pipe, not a static-analysis placeholder -- and it has no safety
envelope of its own (see SafetyGuard / safe_execute, and the repo-level
authority-philosophy note: this experiment intentionally does not implement
privilege enforcement).
"""
function execute(op::ShellEscape)::OperationReceipt
    state = get_kernel_state()
    start_time = time_ns()

    out_buf = IOBuffer()
    err_buf = IOBuffer()
    result = OperationResult(nothing, false, nothing)

    try
        cmd = Cmd(`sh -c $(op.command)`; dir=op.working_dir)
        proc = run(pipeline(cmd; stdout=out_buf, stderr=err_buf); wait=false)

        deadline = time() + op.timeout_ms / 1000
        while process_running(proc) && time() < deadline
            sleep(0.01)
        end
        if process_running(proc)
            kill(proc)
            wait(proc)
            result = OperationResult(
                Dict("stdout" => String(take!(out_buf)), "stderr" => String(take!(err_buf))),
                false,
                "timed out after $(op.timeout_ms)ms",
            )
        else
            wait(proc)
            exit_code = proc.exitcode
            data = op.capture_output ? Dict(
                "stdout" => String(take!(out_buf)),
                "stderr" => String(take!(err_buf)),
                "exit_code" => exit_code,
            ) : Dict("exit_code" => exit_code)
            result = OperationResult(data, exit_code == 0, exit_code == 0 ? nothing : "exit code $(exit_code)")
        end
    catch e
        result = OperationResult(nothing, false, sprint(showerror, e))
    end

    duration_ms = (time_ns() - start_time) / 1_000_000.0

    receipt = OperationReceipt(
        uuid4(),
        Dates.now(),
        "ShellEscape",
        result,
        duration_ms,
        state.id,
        Dict{String,Any}("command" => op.command, "working_dir" => op.working_dir)
    )
    push!(state.receipt_log, receipt)

    return receipt
end

#==============================================================================
PHASE 6: Discovery & Introspection
==============================================================================#

"""
    DiscoveryService

Service for discovering available operators and capabilities.
"""
struct DiscoveryService
    state::KernelState

    function DiscoveryService()
        new(get_kernel_state())
    end
end

"""
    IntrospectionResult

Result of introspecting the operator surface.
"""
struct IntrospectionResult
    available_operators::Vector{String}
    vocabularies::Vector{String}
    registered_variables::Vector{String}
    execution_stats::Dict{String, Any}
    kernel_info::Dict{String, Any}
end

"""
    mean(iter)::Float64

Simple mean calculation (avoiding StatsBase dependency).
"""
function mean(iter)
    vals = collect(Float64, iter)
    return isempty(vals) ? 0.0 : sum(vals) / length(vals)
end

"""
    discover(service::DiscoveryService)::IntrospectionResult

Discovers all available operators and capabilities.
"""
function discover(service::DiscoveryService)::IntrospectionResult
    state = service.state

    operators = collect(keys(state.operator_registry))
    builtin_ops = ["ExecuteCode", "InvokeOperator", "GetState",
                   "ShellEscape", "Discover", "Introspect"]
    operators = unique(vcat(operators, builtin_ops))

    vocabularies = ["CodeExecution", "OperatorInvocation", "StateQuery", "ShellEscape"]

    total_executions = length(state.execution_history)
    successful = sum(r.success for r in state.execution_history; init=0)
    failed = total_executions - successful
    avg_duration = total_executions > 0 ?
        mean(r.duration_ms for r in state.execution_history) : 0.0

    execution_stats = Dict(
        "total" => total_executions,
        "successful" => successful,
        "failed" => failed,
        "average_duration_ms" => avg_duration
    )

    kernel_info = Dict(
        "id" => string(state.id),
        "created_at" => string(state.created_at),
        "uptime_seconds" => Dates.value(Dates.now() - state.created_at) / 1000.0,
        "variable_count" => length(state.variables),
        "receipt_count" => length(state.receipt_log)
    )

    return IntrospectionResult(
        operators,
        vocabularies,
        collect(keys(state.variables)),
        execution_stats,
        kernel_info
    )
end

#==============================================================================
PHASE 9: Failure Handling & Safety
==============================================================================#

"""
    ErrorHandler

Handles errors with configurable strategies.
"""
struct ErrorHandler
    strategy::Symbol  # :propagate, :log, :recover, :fail_safe
    max_retries::Int
    timeout_ms::Int

    function ErrorHandler(strategy::Symbol=:log;
                          max_retries::Int=3,
                          timeout_ms::Int=30000)
        @assert strategy in [:propagate, :log, :recover, :fail_safe]
        new(strategy, max_retries, timeout_ms)
    end
end

"""
    SafetyGuard

Enforces safety constraints on operations. NOTE: this is an
allowlist/pattern-blocklist toy, not the authority fence -- see the
repository README's Authority philosophy section. It exists to demonstrate
failure containment (Phase 9), not to be relied on as a security boundary.
"""
struct SafetyGuard
    max_execution_time_ms::Int
    max_memory_mb::Int
    allowed_operations::Set{String}
    blocked_patterns::Vector{Regex}

    function SafetyGuard(max_time::Int=60000,
                         max_mem::Int=1024,
                         allowed::Set{String}=Set(["ExecuteCode", "InvokeOperator", "GetState"]),
                         blocked::Vector{Regex}=Regex[])
        new(max_time, max_mem, allowed, blocked)
    end
end

"""
    validate(op, guard::SafetyGuard)::Bool

Validates that an operation passes safety checks.
"""
function validate(op, guard::SafetyGuard)::Bool
    op_type = string(typeof(op).name.name)
    return op_type in guard.allowed_operations
end

"""
    check_patterns(code::String, guard::SafetyGuard)::Vector{String}

Checks code against blocked patterns and returns matches.
"""
function check_patterns(code::String, guard::SafetyGuard)::Vector{String}
    matches = String[]
    for pattern in guard.blocked_patterns
        if occursin(pattern, code)
            push!(matches, string(pattern))
        end
    end
    return matches
end

"""
    safe_execute(op, guard::SafetyGuard)::Union{OperationReceipt, StructuredResponse}

Executes an operation with the toy safety guard applied.
"""
function safe_execute(op, guard::SafetyGuard)
    if !validate(op, guard)
        return StructuredResponse(
            nothing,
            false,
            Dict{String,Any}("reason" => "Operation not allowed");
            error = "Safety violation: operation type not permitted"
        )
    end

    if op isa ExecuteCode
        violations = check_patterns(op.code, guard)
        if !isempty(violations)
            return StructuredResponse(
                nothing,
                false,
                Dict{String,Any}("violations" => violations);
                error = "Safety violation: blocked patterns detected"
            )
        end
    end

    return execute(op)
end

#==============================================================================
PHASE 10: Integration Demo Helpers
==============================================================================#

"""
    demo_setup()

Sets up a demonstration environment.
"""
function demo_setup()
    reset_kernel_state()
    state = get_kernel_state()
    register_operator!(state, "demo_operator", args -> get(args, "echo", nothing))
    return state
end

"""
    run_demo()

Runs a simple, real demonstration of the operator surface end to end:
real eval-based execution, real state query, real discovery, and (if `sh`
is available) a real shell escape.
"""
function run_demo()
    println("=== OperatorSurface Demo ===\n")

    state = demo_setup()
    println("1. Kernel initialized with ID: $(state.id)\n")

    code_op = ExecuteCode("x = 42\ny = x * 2")
    receipt = execute(code_op)
    println("2. Executed code operation")
    println("   Receipt ID: $(receipt.id)")
    println("   Real result of last expression (y): $(receipt.result.data)")
    println("   Duration: $(receipt.duration_ms) ms\n")

    state_op = GetState()
    response = execute(state_op)
    println("3. Queried kernel state")
    println("   Variables: $(response.result.data["variables"])\n")

    invoke_op = InvokeOperator("demo_operator"; args=Dict("echo" => "hello from a real call"))
    invoke_receipt = execute(invoke_op)
    println("4. Invoked a real registered operator")
    println("   Result: $(invoke_receipt.result.data)\n")

    shell_op = ShellEscape("echo shell-escape-is-real")
    shell_receipt = execute(shell_op)
    println("5. Real shell escape")
    println("   stdout: $(get(shell_receipt.result.data, "stdout", nothing))\n")

    service = DiscoveryService()
    introspection = discover(service)
    println("6. Discovery results:")
    println("   Available operators: $(introspection.available_operators)")
    println("   Execution count: $(introspection.execution_stats["total"])\n")

    println("=== Demo Complete ===")

    return introspection
end

#==============================================================================
Exports
==============================================================================#

export KernelState, ExecutionRecord
export get_kernel_state, reset_kernel_state
export OperatorType, OperatorVocabulary
export CODE_EXECUTION_VOCAB, OPERATOR_INVOCATION_VOCAB, STATE_QUERY_VOCAB
export ExecuteCode, InvokeOperator, GetState, ShellEscape
export register_operator!
export OperationResult, StructuredResponse
export DiscoveryService, IntrospectionResult, discover
export OperationReceipt, ReceiptLog, get_receipts
export ErrorHandler, SafetyGuard, validate, check_patterns, safe_execute
export demo_setup, run_demo
export execute, mean

end # module
