"""
Neura — Experiment 001: NeuraJL operator surface, built on IJulia

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
module Neura

using Dates
using UUIDs
using Sockets
using JSON
using SHA
using Statistics: mean as stdlib_mean

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
        # `Core.eval`'d code lands in this fresh module, not Main -- `using
        # Neura` at Main scope (e.g. in scripts/session_loop.jl) does not
        # make `Neura` visible here (confirmed by direct testing: a real
        # UndefVarError for `Neura` from inside eval_module otherwise).
        # Bound once here so turn code can call
        # `Neura.request_capability(...)` without re-importing it on every
        # single turn just to reach the one function that's the entire
        # point of the authority fence.
        Core.eval(state.eval_module, :(const Neura = $(@__MODULE__)))
        # A bare `Module(...)` never gets `include` for free (confirmed by
        # direct testing across all constructor flag combinations -- this
        # is not a Julia version regression, it never worked the way an
        # earlier comment in this file assumed). Needed so promoted, kit-
        # scope code (written to disk via a real broker-mediated
        # external_fs_write, then loaded back with `include`) can actually
        # be loaded into the persistent mind's own module, not just Main.
        Core.eval(state.eval_module, :(include(path) = Base.include(@__MODULE__, path)))
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
    EphemeralTool

Operation type for disposable, task-scoped code: generated helper logic
that should not become a permanent member of the persistent session's
`eval_module`. See `execute(op::EphemeralTool)` for why this needs to be a
genuinely different code path from `ExecuteCode`, not just a naming
convention -- Julia has no operation to un-define a method once it has
been evaluated anywhere in the process, so "ephemeral" has to be enforced
before eval, not cleaned up after.
"""
struct EphemeralTool <: OperatorType
    code::String
    tool_id::String

    function EphemeralTool(code::String; tool_id::String=string(uuid4()))
        new(code, tool_id)
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

        # Variable index for GetState/discovery convenience, built from
        # real module reflection (`names`) rather than regex-guessing
        # assignment targets out of the source text -- the previous
        # approach matched one simple `name =` per line and silently
        # missed destructuring (`a, b = 1, 2`), multi-statement lines
        # (`x = 1; y = 2`), and anything else that isn't that one shape.
        # `names(module; all=true)` reports exactly what Julia itself
        # considers a top-level binding in this module, which is the
        # actual question being asked here.
        # World-age note: Core.eval above ran in a compiled function, so it
        # defines eval_module's new bindings in a NEW world age -- plain
        # names/isdefined/getfield here would still see the OLD world and
        # miss bindings that unquestionably exist (confirmed by direct
        # testing, not assumed). Base.invokelatest forces resolution
        # against the current world.
        own_name = nameof(state.eval_module)
        for sym in Base.invokelatest(names, state.eval_module; all=true)
            # :Neura is the constant KernelState's constructor binds here so
            # turn code can reach `Neura.request_capability` without
            # re-importing it every turn -- not a user variable, must not
            # show up in GetState/discovery any more than :eval or :include do.
            (sym === own_name || sym === :eval || sym === :include || sym === :Neura) && continue
            startswith(string(sym), '#') && continue
            if Base.invokelatest(isdefined, state.eval_module, sym)
                state.variables[string(sym)] = Base.invokelatest(getfield, state.eval_module, sym)
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

struct EphemeralToolViolation <: Exception
    reason::String
end
Base.showerror(io::IO, e::EphemeralToolViolation) = print(io, "EphemeralToolViolation: ", e.reason)

"""
    _qualified_def_target(head)::Bool

True if a function-definition call head is a dotted/qualified name
(`function Mod.name(...)`), i.e. defines a method on a generic function
that belongs to another module, reachable and permanent from anywhere in
the process the instant it's evaluated -- confirmed by direct testing:
`Core.eval` of `function Base.show(io, x::Int) ... end` into a brand new,
otherwise-unrelated module still adds a real, permanent method to
`Base.show`, with no `import` needed at all.
"""
_qualified_def_target(head) = false
_qualified_def_target(head::Expr) = head.head === :(.)

"""
    _call_head(expr)

Pulls the name/target expression out of a function-definition's call
signature, for both `function f(...) ... end` and `f(...) = ...` forms.
`where`-clauses (`function f(x::T) where T`) wrap the call one level
deeper and are unwrapped first.
"""
function _call_head(expr::Expr)
    sig = expr.args[1]  # the signature slot for both `function f(...) ... end` and `f(...) = ...`
    sig = sig isa Expr && sig.head === :where ? sig.args[1] : sig
    sig isa Expr && sig.head === :call ? sig.args[1] : nothing
end

"""
    _qualified_include_call(expr)::Bool

True for a `:call` expression whose target is a qualified `.include`
access (`Base.include(...)`, `Core.include(...)`, or any `Mod.include`),
regardless of what module it targets.
"""
_qualified_include_call(expr) = false
function _qualified_include_call(expr::Expr)
    expr.head === :call || return false
    target = expr.args[1]
    target isa Expr && target.head === :(.) && length(target.args) == 2 || return false
    name = target.args[2]
    name isa QuoteNode && name.value === :include
end

"""
    check_ephemeral_source!(parsed::Expr)

Walks the ENTIRE parsed tree (not just top-level statements -- a
definition nested inside a `let`/`if`/`for`/another function body would
otherwise sail through unchecked) and throws `EphemeralToolViolation`
before any of it is ever evaluated, for the real ways this process
confirmed can extend a foreign generic function's method table
permanently:

1. Any `import` statement. `using Mod: f` alone is already blocked by
   Julia itself for bare-name extension (confirmed by direct testing --
   "function Base.show must be explicitly imported to be extended") --
   but `import Mod: f` followed by a bare `function f(...)` succeeds and
   is exactly the pattern that needs to be stopped before eval, since
   Julia's own runtime won't stop it once `import` has run.
2. Any qualified function definition head (`function Mod.name(...)`),
   which extends `Mod`'s generic function directly, no `import` required
   at all -- also confirmed by direct testing.
3. Any qualified call to `.include` (`Base.include(@__MODULE__, path)`),
   confirmed to load and run a file's contents with zero syntactic trace
   in the calling code itself -- the whole point of this check is to
   examine the submitted source, and an `include`d file's contents were
   never submitted at all, so they can't be inspected here. `include`
   itself is never bound in an ephemeral tool's own module (see
   `execute(op::EphemeralTool)`) specifically so that only the fully
   qualified form needs blocking here, not a bare name too.

**This is a syntactic hygiene check, not a security boundary, and cannot
be one.** Confirmed by direct adversarial testing: `Core.eval(Base,
:(function show(io::IO, x::Int) ... end))` -- a *quoted* expression
constructed and evaluated entirely at runtime -- extends `Base.show`
exactly as effectively as writing the definition directly, and no
parse-time check on the OUTER submitted source can see inside a value
that is only ever assembled once the code is already running (Julia's
`eval`/`Core.eval` remain fully callable, and must, for "unbounded power"
to mean anything). This check stops accidental/careless pollution and the
two simplest deliberate bypass shapes; it does not stop a determined
adversarial payload built to route around exactly this check.
**Genuinely untrusted generated code that must be hard-isolated belongs
in a disposable child worker (`spawn_child_worker`, already OS-level
sandboxed and adversarially tested -- see docs/THREAT_MODEL.md), not
same-process ephemeral tool execution.** See the repository README's
Authority philosophy note for how this relates to (and is separate from)
`SafetyGuard`, a different, unrelated policy layer.
"""
function check_ephemeral_source!(parsed::Expr)
    parsed.head === :toplevel || throw(EphemeralToolViolation("expected a top-level block"))
    _check_ephemeral_node!(parsed)
    nothing
end

function _check_ephemeral_node!(stmt)
    stmt isa Expr || return nothing

    if stmt.head === :import
        throw(EphemeralToolViolation(
            "ephemeral tool code may not use `import` -- it can permanently extend a foreign " *
            "module's function (confirmed: `import Mod: f` then a bare `function f(...)` adds a " *
            "real, permanent method). Use `using` to call existing functionality; a real need to " *
            "extend one belongs in a durable kit, not disposable code."
        ))
    elseif _qualified_include_call(stmt)
        throw(EphemeralToolViolation(
            "ephemeral tool code may not call a qualified `.include` (e.g. `Base.include(...)`) -- " *
            "this loads and runs a file whose contents were never part of the submitted source and " *
            "so cannot be checked here at all. Kit code should be loaded into the persistent " *
            "session's own eval_module, not ephemeral tool code."
        ))
    elseif stmt.head in (:function, :(=))
        head = _call_head(stmt)
        if head !== nothing && _qualified_def_target(head)
            throw(EphemeralToolViolation(
                "ephemeral tool code may not define a qualified method (`function Mod.name(...)`) -- " *
                "confirmed: this extends the foreign module's generic function permanently, with no " *
                "import needed at all. A real need to extend one belongs in a durable kit."
            ))
        end
    end

    # Recurse into every child regardless of which (if any) check matched
    # above -- a dangerous definition or qualified include call nested
    # inside a `let`/`if`/`for`/function body is exactly as real as one at
    # the top level once this code actually runs.
    for child in stmt.args
        _check_ephemeral_node!(child)
    end
    nothing
end

"""
    execute(op::EphemeralTool)::OperationReceipt

Evaluates disposable code into a genuinely fresh, throwaway `Module` --
never the persistent session's own `state.eval_module` -- so that once
every reference to the returned receipt/result is dropped, the tool's
bindings are ordinary garbage, not permanent state next to the session's
real cognitive world. `check_ephemeral_source!` runs first and throws
before any eval happens at all if the source would otherwise leave a
permanent mark on the process outside this throwaway module (see its
docstring for the two confirmed ways that can happen).

This does not, and cannot, stop a name collision from being merely
confusing (two ephemeral tools both defining a local `helper` function is
fine -- they're in different modules) -- it stops permanent, cross-cutting
pollution of shared, foreign method tables.
"""
function execute(op::EphemeralTool)::OperationReceipt
    kernel_state = get_kernel_state()
    start_time = time_ns()

    result = OperationResult(nothing, true, nothing)
    error_msg = nothing
    tool_module = Module(Symbol("Ephemeral_$(replace(op.tool_id, '-' => '_'))"))
    # Same reasoning as KernelState's own eval_module: ephemeral code has
    # the SAME authority ceiling as durable code (broker-mediated, not
    # granted by which module happens to run it), so it needs the same
    # reachable path to request_capability.
    Core.eval(tool_module, :(const Neura = $(@__MODULE__)))
    # Deliberately NOT given an `include` binding, unlike the persistent
    # eval_module: check_ephemeral_source! only inspects the source string
    # passed directly to EphemeralTool -- it cannot see inside a file that
    # code would dynamically `include` at runtime, so granting `include`
    # here would be a silent bypass of the whole namespace-pollution guard
    # (load a file containing `import Base: show; function show(...)`, and
    # the guard never looked at it). Kit code loads into the durable mind
    # deliberately, not into disposable ephemeral tool code.

    try
        parsed = Meta.parseall(op.code)
        check_ephemeral_source!(parsed)
        value = Core.eval(tool_module, parsed)
        result = OperationResult(value, true, nothing)
    catch e
        result = OperationResult(nothing, false, sprint(showerror, e))
        error_msg = sprint(showerror, e)
    end

    duration_ms = (time_ns() - start_time) / 1_000_000.0

    receipt = OperationReceipt(
        uuid4(),
        Dates.now(),
        "EphemeralTool",
        result,
        duration_ms,
        kernel_state.id,
        Dict{String,Any}("tool_id" => op.tool_id)
    )
    push!(kernel_state.receipt_log, receipt)
    record_tool_capsule(op.tool_id, op.code, result, duration_ms)

    return receipt
end

"""
    record_tool_capsule(tool_id, code, result, duration_ms)

Appends one mechanical, non-authoritative provenance record for a retired
ephemeral tool to this worker's own workspace (`.neurajl/provenance.jsonl`,
relative to `pwd()` -- the sandbox's `--chdir` target, which is already a
real, host-bind-mounted directory, so this needs no broker mediation to
become visible outside the sandbox: workspace writes are Class B, not C).

Deliberately mechanical, not model-authored: a content hash (same
convention as NeuraBash's own Forge module -- `bytes2hex(sha256(...))`),
success/failure, and the source itself, so a human or agent can
reconstruct what ran without the now-garbage-collected ephemeral module
still existing. Written unconditionally at zero LLM cost regardless of
whether anything ever reads it -- reading is opt-in (grep/jq against a
JSONL file), never preloaded into any prompt. This is provenance, not
authorization: nothing in this codebase reads this file to decide whether
to permit anything, and it is never treated as such.
"""
function record_tool_capsule(tool_id::String, code::String, result::OperationResult, duration_ms::Float64)
    dir = joinpath(pwd(), ".neurajl")
    mkpath(dir)
    capsule = Dict{String,Any}(
        "schema" => "neurajl.tool_capsule.v1",
        "tool_id" => tool_id,
        "source_hash" => bytes2hex(sha256(code)),
        "source" => code,
        "success" => result.success,
        "error" => result.error,
        "duration_ms" => duration_ms,
        "retired_at" => string(Dates.now()),
        "disposition" => "RETIRED",
    )
    open(joinpath(dir, "provenance.jsonl"), "a") do io
        println(io, JSON.json(capsule))
    end
    nothing
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

        # Event-driven timeout, not a 10ms sleep-poll loop: a `Timer` fires
        # once at the deadline and kills the process if it's still
        # running, while `wait(proc)` blocks cooperatively on the task
        # scheduler in the meantime (no busy-waking every 10ms for the
        # entire duration of every shell command this runs).
        timed_out = Ref(false)
        timer = Timer(op.timeout_ms / 1000) do _
            if process_running(proc)
                timed_out[] = true
                kill(proc)
            end
        end
        wait(proc)
        close(timer)

        if timed_out[]
            result = OperationResult(
                Dict("stdout" => String(take!(out_buf)), "stderr" => String(take!(err_buf))),
                false,
                "timed out after $(op.timeout_ms)ms",
            )
        else
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

`Statistics.mean` (a stdlib, not the StatsBase dependency this was
originally hand-rolled to avoid) with this package's own empty-input
convention (`0.0`, not `NaN`) for `execution_stats`.
"""
function mean(iter)
    isempty(iter) && return 0.0
    return Float64(stdlib_mean(iter))
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
    allowed_operations::Set{DataType}
    blocked_patterns::Vector{Regex}

    function SafetyGuard(max_time::Int=60000,
                         max_mem::Int=1024,
                         allowed::Set{DataType}=Set{DataType}([ExecuteCode, InvokeOperator, GetState]),
                         blocked::Vector{Regex}=Regex[])
        new(max_time, max_mem, allowed, blocked)
    end
end

"""
    validate(op, guard::SafetyGuard)::Bool

Validates that an operation passes safety checks. Dispatches on the
operation's actual type against a `Set{DataType}` -- this used to stringify
`typeof(op)` and look it up in a `Set{String}`, which is duck-typing
grafted onto a language whose type system already answers "is this op one
of the allowed kinds" directly, without an allocation or a name-collision
risk between unrelated types that happen to share a short name.
"""
function validate(op, guard::SafetyGuard)::Bool
    return typeof(op) in guard.allowed_operations
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
EXPERIMENT 002: broker-mediated capability requests
==============================================================================#

"""
    request_capability(category::String, params::Dict=Dict(); timeout_s::Real=10.0) -> Dict

Request a broker-mediated (Effect Class C) capability -- see
docs/CAPABILITY_MODEL.md and docs/EXPERIMENT_002_AUTHORITY.md.

This is the ONLY code path in this package that can reach outside the
sandbox's own bounded filesystem/network envelope. It does not perform any
external effect itself: it connects to the host capability broker over the
Unix socket named by the `NEURAJL_BROKER_SOCKET` environment variable (set
by `security/launch_worker.py`, reachable only because that one socket path
was explicitly bind-mounted into this sandbox), sends one JSON request, and
returns the broker's JSON response. The broker -- a separate process
running outside this sandbox's OS namespace entirely -- decides whether to
approve the request against this session's fixed capability ceiling, and if
approved, performs the actual effect itself, with host privilege this
process never has.

This function is a convenience for well-behaved callers. It is not, and is
not meant to be, an enforcement mechanism: a caller that wants to skip it
and try the effect directly (raw `write`, raw `Sockets.connect`, `ccall`,
`run`) is exactly the adversarial case Experiment 002's tests exercise --
and what stops that is the OS-level sandbox boundary this process runs
inside, not this function's cooperation.

Throws if `NEURAJL_BROKER_SOCKET` is unset (no broker configured for this
session -- e.g. running unsandboxed) or if the connection fails.
"""
function request_capability(category::String, params::Dict=Dict{String,Any}(); timeout_s::Real=10.0)
    sock_path = get(ENV, "NEURAJL_BROKER_SOCKET", "")
    isempty(sock_path) && error("NEURAJL_BROKER_SOCKET is not set -- no capability broker is available in this session")
    req = Dict("id" => string(uuid4()), "category" => category, "params" => params)
    conn = connect(sock_path)
    try
        write(conn, JSON.json(req) * "\n")
        line = readline(conn)
        isempty(line) && error("broker closed the connection without a response")
        return JSON.parse(line)
    finally
        close(conn)
    end
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
    println("=== Neura Demo ===\n")

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
export EphemeralTool, EphemeralToolViolation, check_ephemeral_source!, record_tool_capsule
export register_operator!
export OperationResult, StructuredResponse
export DiscoveryService, IntrospectionResult, discover
export OperationReceipt, ReceiptLog, get_receipts
export ErrorHandler, SafetyGuard, validate, check_patterns, safe_execute
export demo_setup, run_demo
export execute, mean
export request_capability

end # module
