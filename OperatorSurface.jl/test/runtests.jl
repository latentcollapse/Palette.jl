module TestOperatorSurface

using Test
using ..OperatorSurface

@testset "KernelState" begin
    # Test state initialization
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
end

@testset "GetState Operation" begin
    reset_kernel_state()
    
    # Set a variable first
    execute(ExecuteCode("test_var = 123"))
    
    # Query state
    op = GetState()
    response = execute(op)
    
    @test response isa StructuredResponse
    @test response.result.success
    @test "test_var" in response.result.data["variables"]
end

@testset "OperatorVocabulary" begin
    @test CODE_EXECUTION_VOCAB isa OperatorVocabulary
    @test CODE_EXECUTION_VOCAB.name == "CodeExecution"
    
    @test OPERATOR_INVOCATION_VOCAB isa OperatorVocabulary
    @test STATE_QUERY_VOCAB isa OperatorVocabulary
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
    
    # Execute multiple operations
    execute(ExecuteCode("a = 1"))
    execute(ExecuteCode("b = 2"))
    execute(GetState())
    
    @test length(state.receipt_log) >= 3
    
    # Verify receipt structure
    receipt = state.receipt_log[1]
    @test !isnothing(receipt.id)
    @test !isnothing(receipt.timestamp)
    @test !isnothing(receipt.operation_type)
end

@testset "SafetyGuard" begin
    guard = SafetyGuard(
        allowed_types=[ExecuteCode, GetState],
        blocked_patterns=["rm -rf", ":(){:|:&};:"],
        timeout_ms=5000
    )
    
    @test guard.max_execution_time_ms == 5000
    @test "rm -rf" in guard.blocked_patterns
end

@testset "ErrorHandler" begin
    handler = ErrorHandler(:log, max_retries=5)
    
    @test handler.strategy == :log
    @test handler.max_retries == 5
end

@testset "Demo Functions" begin
    state = demo_setup()
    @test state isa KernelState
    
    result = run_demo()
    @test result isa IntrospectionResult
end

end # module
