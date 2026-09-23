using Test
using Neura

@testset "KernelState" begin
    reset_kernel_state()
    state = get_kernel_state()

    @test state isa KernelState
    @test !isnothing(state.id)
    @test !isnothing(state.created_at)
    @test isempty(state.variables)
    @test isempty(state.execution_history)
end

@testset "ExecuteCode Operation" begin
    reset_kernel_state()

    op = ExecuteCode("x = 42")
    receipt = execute(op)

    @test receipt isa OperationReceipt
    @test receipt.operation_type == "ExecuteCode"
    @test receipt.result.success
    @test receipt.result.data == 42
end

@testset "Phase 1: real cross-request state persistence" begin
    reset_kernel_state()

    execute(ExecuteCode("x = 41"))
    r = execute(ExecuteCode("x + 1"))
    @test r.result.success
    @test r.result.data == 42

    execute(ExecuteCode("square(n) = n * n"))
    r2 = execute(ExecuteCode("square(7)"))
    @test r2.result.success
    @test r2.result.data == 49

    execute(ExecuteCode("buf = Int[]"))
    r3 = execute(ExecuteCode("push!(buf, 1); push!(buf, 2); buf"))
    @test r3.result.success
    @test r3.result.data == [1, 2]

    # A thrown exception must not corrupt the session's persistent state.
    r4 = execute(ExecuteCode("error(\"boom\")"))
    @test !r4.result.success
    r5 = execute(ExecuteCode("x"))
    @test r5.result.success
    @test r5.result.data == 41
end

@testset "GetState Operation" begin
    reset_kernel_state()

    execute(ExecuteCode("test_var = 123"))

    op = GetState()
    response = execute(op)

    @test response isa StructuredResponse
    @test response.result.success
    @test "test_var" in response.result.data["variables"]

    keyed = execute(GetState("test_var"))
    @test keyed.result.data["exists"]
    @test keyed.result.data["value"] == 123
end

@testset "OperatorVocabulary" begin
    @test CODE_EXECUTION_VOCAB isa OperatorVocabulary
    @test CODE_EXECUTION_VOCAB.name == "CodeExecution"

    @test OPERATOR_INVOCATION_VOCAB isa OperatorVocabulary
    @test STATE_QUERY_VOCAB isa OperatorVocabulary
end

@testset "InvokeOperator (real registered function)" begin
    reset_kernel_state()
    state = get_kernel_state()
    register_operator!(state, "add_one", args -> args["n"] + 1)

    receipt = execute(InvokeOperator("add_one"; args=Dict("n" => 41)))
    @test receipt.result.success
    @test receipt.result.data == 42

    missing_receipt = execute(InvokeOperator("does_not_exist"))
    @test !missing_receipt.result.success
end

@testset "ShellEscape (real subprocess)" begin
    reset_kernel_state()
    receipt = execute(ShellEscape("echo hello"))
    @test receipt.result.success
    @test strip(receipt.result.data["stdout"]) == "hello"
    @test receipt.result.data["exit_code"] == 0

    fail_receipt = execute(ShellEscape("exit 3"))
    @test !fail_receipt.result.success
    @test fail_receipt.result.data["exit_code"] == 3
end

@testset "DiscoveryService" begin
    reset_kernel_state()

    service = DiscoveryService()
    result = discover(service)

    @test result isa IntrospectionResult
    @test length(result.available_operators) > 0
    @test length(result.vocabularies) > 0
end

@testset "OperationReceipts" begin
    reset_kernel_state()
    state = get_kernel_state()

    execute(ExecuteCode("a = 1"))
    execute(ExecuteCode("b = 2"))
    # GetState returns a StructuredResponse, not an OperationReceipt -- by
    # design it's a pure query and doesn't append to receipt_log (receipts
    # are for auditing state-changing/effectful operations).
    execute(GetState())

    @test length(state.receipt_log) == 2

    receipt = state.receipt_log[1]
    @test !isnothing(receipt.id)
    @test !isnothing(receipt.timestamp)
    @test !isnothing(receipt.operation_type)
end

@testset "SafetyGuard" begin
    guard = SafetyGuard(5000, 1024, Set{DataType}([ExecuteCode, GetState]), [r"rm -rf", r":\(\)\{:\|:&\};:"])

    @test guard.max_execution_time_ms == 5000
    @test any(p -> p.pattern == "rm -rf", guard.blocked_patterns)

    reset_kernel_state()
    allowed = safe_execute(ExecuteCode("1 + 1"), guard)
    @test allowed isa OperationReceipt
    @test allowed.result.success
    @test allowed.result.data == 2

    disallowed = safe_execute(ShellEscape("echo nope"), guard)
    @test disallowed isa StructuredResponse
    @test !disallowed.result.success

    blocked = safe_execute(ExecuteCode("run(`rm -rf /`)"), guard)
    @test blocked isa StructuredResponse
    @test !blocked.result.success
end

@testset "ErrorHandler" begin
    handler = ErrorHandler(:log; max_retries=5)

    @test handler.strategy == :log
    @test handler.max_retries == 5
end

@testset "Demo Functions" begin
    state = demo_setup()
    @test state isa KernelState

    result = run_demo()
    @test result isa IntrospectionResult
end
