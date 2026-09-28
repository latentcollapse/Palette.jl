using Test
using Neura
using JSON

# Run before "EphemeralTool isolation", whose same-process case pirates Base methods for the rest of the process.
@testset "Output digest" begin
    fx(name) = read(joinpath(@__DIR__, "fixtures", "digest", name), String)
    # Real tool output, captured from each toolchain, after a long build log.
    noise = join(["   Compiling dep-$i v0.1.$i (registry)" for i in 1:150], "\n") * "\n"
    head(name) = first(split(Neura.with_digest(noise * fx(name)), "\n\n"))
    @test startswith(head("cargo_build.txt"), "[digest of 185 lines of output: 3 errors]")
    @test occursin("src/main.rs:3:18  error[E0308]: mismatched types", head("cargo_build.txt"))
    @test occursin("2 failing tests", head("cargo_test.txt"))
    @test occursin("src/main.rs:4:23  test tests::adds panicked", head("cargo_test.txt"))
    @test occursin("a.ts:4:9  error TS2304: Cannot find name 'missing'.", head("tsc.txt"))
    @test occursin("a.ts:2:19  error TS2322", head("tsc_pretty.txt"))   # ANSI-coloured
    @test occursin("bin/m.ml:1  error This constant has type string but an expression was expected of type int", head("dune.txt"))
    @test occursin("./m.go:2:14  error declared and not used: x", head("go_build.txt"))
    @test occursin("m_test.go:3  test TestAdd: Add(2,2)=0", head("go_test.txt"))
    @test occursin("test_x.py:3  test test_x.T.test_a: AssertionError: 2 != 3", head("py_unittest.txt"))
    @test occursin("1 failing test]", head("node_test.txt"))
    # The whole output still follows the digest.
    @test endswith(Neura.with_digest(noise * fx("cargo_build.txt")), fx("cargo_build.txt"))
    # Short output, and long output with nothing failing, are left as they are.
    @test Neura.with_digest(fx("tsc.txt")) == fx("tsc.txt")
    @test Neura.with_digest(noise) == noise
    @test Neura.with_digest("\e[31mred\e[0m plain") == "red plain"
    # A flood of failures is capped.
    flood = noise * join(["test t$i ... FAILED" for i in 1:40], "\n")
    @test occursin("… and 28 more", Neura.with_digest(flood))
end

@testset "Workspace map" begin
    root = mktempdir()
    @test occursin("the workspace is empty", Neura.workspace_map(root))
    mkpath(joinpath(root, "core", "src")); mkpath(joinpath(root, "api", "src")); mkpath(joinpath(root, "node_modules", "x"))
    write(joinpath(root, "Cargo.toml"), "[workspace]\nmembers = [\"core\"]\n")
    write(joinpath(root, "core", "src", "lib.rs"), "pub fn f() {}\n")
    write(joinpath(root, "api", "package.json"), "{\"scripts\": {\"build\": \"tsc\", \"test\": \"node --test\"}}")
    write(joinpath(root, "api", "src", "index.ts"), "export const x = 1\n")
    write(joinpath(root, "node_modules", "x", "a.js"), "")
    write(joinpath(root, "Makefile"), "build:\n\tcargo build\ntest: build\n\tcargo test\n.PHONY: build test\n")
    m = Neura.workspace_map(root)
    @test startswith(m, "[workspace map] 5 files")          # node_modules left out
    @test occursin("Rust 1", m) && occursin("TypeScript 1", m) && !occursin("JavaScript", m)
    @test occursin("cargo: Cargo.toml (workspace)", m)
    @test occursin("npm: api/package.json scripts: build, test", m) || occursin("npm: api/package.json scripts: test, build", m)
    @test occursin("Makefile: Makefile targets: build, test", m)
    @test length(m) <= Neura.MAP_MAX_CHARS + 2
end

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

@testset "EphemeralTool isolation" begin
    reset_kernel_state()
    state = get_kernel_state()

    # ordinary ephemeral code works and does not leak into the persistent
    # session's own eval_module
    r1 = execute(EphemeralTool("helper(x) = x * 2; helper(21)"))
    @test r1.result.success
    @test r1.result.data == 42
    @test !isdefined(state.eval_module, :helper)

    # `import Mod: f` then a bare `function f(...)` is the confirmed real
    # way to permanently extend a foreign generic function -- must be
    # rejected before eval, not cleaned up after (Julia has no method
    # deletion). Checked against REAL Base.show behavior, not the tool's
    # own self-reported success/failure.
    r2 = execute(EphemeralTool("import Base: show; function show(io::IO, x::Int); print(io, \"pwned\"); end"))
    @test !r2.result.success
    @test r2.result.error !== nothing && occursin("import", r2.result.error)
    @test sprint(show, 42) == "42"

    # a fully qualified `function Mod.name(...)` extends the same way with
    # no `import` at all -- confirmed separately, must also be rejected
    r3 = execute(EphemeralTool("function Base.show(io::IO, x::Int); print(io, \"pwned2\"); end"))
    @test !r3.result.success
    @test sprint(show, 42) == "42"

    # the same qualified attempt, but joined onto a prior statement with a
    # semicolon -- regression case: semicolon-joined statements parse as a
    # NESTED :toplevel Expr that an earlier version of this check never
    # recursed into, letting this exact shape bypass the guard silently
    r3b = execute(EphemeralTool("x = 1; function Base.show(io::IO, x::Int); print(io, \"pwned3\"); end"))
    @test !r3b.result.success
    @test sprint(show, 42) == "42"

    # a qualified def NESTED inside a function body -- regression case:
    # an earlier version of this check only inspected top-level statements
    # and their immediate :block/:toplevel children, missing anything
    # nested one level deeper (inside a function body, let, if, for, ...)
    r3c = execute(EphemeralTool("function outer(); function Base.show(io::IO, x::Int); print(io, \"n\"); end; end"))
    @test !r3c.result.success
    @test sprint(show, 42) == "42"

    # `Base.include(...)` (qualified) loads and runs a file's contents
    # with zero syntactic trace in the SUBMITTED source -- must be
    # rejected outright, since there is nothing in the ephemeral tool's
    # own source for this check to inspect once the file is loaded
    mktemp() do path, io
        write(io, "import Base: show; function show(io::IO, x::Int); print(io, \"file-pwned\"); end")
        close(io)
        r3d = execute(EphemeralTool("Base.include(@__MODULE__, \"$(path)\")"))
        @test !r3d.result.success
        @test sprint(show, 42) == "42"
    end

    # KNOWN, DOCUMENTED, UNCLOSABLE GAP -- not a regression, a permanent
    # fact about running inside a language with reflective eval: a value
    # only ASSEMBLED at runtime (here, a quoted Expr passed to Core.eval)
    # has no syntactic trace in the submitted source at all, so no
    # parse-time check can see it coming. This test exists so that a
    # future change silently "closing" this without updating
    # check_ephemeral_source!'s own docstring (which says explicitly this
    # is a hygiene check, not a security boundary) gets caught by a test
    # failure instead of quietly changing the security claim being made.
    # Real isolation for genuinely untrusted code is spawn_child_worker
    # (OS-level, already adversarially proven), not this same-process guard.
    r3e = execute(EphemeralTool("Core.eval(Base, :(function show(io::IO, x::Int); print(io, \"PWNED2\"); end))"))
    @test r3e.result.success  # succeeds -- this IS the documented open gap
    @test sprint(show, 42) != "42"  # Base.show really is compromised at this point
    # Restore Base.show can't be undone (Julia has no method deletion) --
    # this test necessarily leaves Base.show permanently altered for the
    # rest of THIS process. Acceptable here (test runs in its own `julia
    # Pkg.test()` process, never reused), but never call this pattern
    # against a persistent session worth continuing to trust.

    # `using` alone (no import) remains fully unrestricted -- ephemeral
    # tools keep unbounded power to USE anything, only extension is guarded
    r4 = execute(EphemeralTool("using Statistics; Statistics.mean([1.0, 2.0, 3.0])"))
    @test r4.result.success
    @test r4.result.data == 2.0

    # two ephemeral tools do not share state with each other either
    execute(EphemeralTool("z = 999"))
    r5 = execute(EphemeralTool("!@isdefined(z)"))
    @test r5.result.success
    @test r5.result.data == true

    # every retirement leaves a mechanical, content-addressed provenance
    # record -- cold by default (a file on disk), never preloaded
    prov_path = joinpath(pwd(), ".neurajl", "provenance.jsonl")
    @test isfile(prov_path)
    lines = readlines(prov_path)
    @test length(lines) >= 5
    last_record = JSON.parse(lines[end])
    @test last_record["schema"] == "neurajl.tool_capsule.v1"
    @test haskey(last_record, "source_hash")
    @test length(last_record["source_hash"]) == 64  # sha256 hex
    @test last_record["disposition"] == "RETIRED"  # this one succeeded

    # regression: disposition used to be hardcoded "RETIRED" regardless of
    # result.success, so a failed ephemeral tool's capsule was
    # indistinguishable from a successful one in the provenance log
    execute(EphemeralTool("error(\"deliberate failure\")"))
    failed_record = JSON.parse(readlines(prov_path)[end])
    @test failed_record["success"] == false
    @test failed_record["disposition"] == "FAILED"

    rm(joinpath(pwd(), ".neurajl"); recursive=true, force=true)
end

@testset "Session module helpers" begin
    reset_kernel_state()
    run(code) = execute(ExecuteCode(code)).result

    # bash returns the whole result, not only the exit code
    r = run("r = bash(\"echo out; echo err >&2; exit 4\")")
    @test r.success
    @test r.data isa Neura.ShellResult
    @test (r.data.exitcode, r.data.stdout, r.data.stderr) == (4, "out\n", "err\n")
    @test !success(r.data)
    @test run("sh\"x=2; echo \$((x+1))\"").data.stdout == "3\n"

    # ans holds the last call's value
    run("40 + 2")
    @test run("ans").data == 42

    # varinfo lists the session's own bindings and none of the kernel's
    rows = run("varinfo()").data.rows
    @test "r" in first.(rows)
    @test isempty(intersect(first.(rows), string.(collect(Neura.KERNEL_BINDINGS))))

    # turn code reaches authority through Neura, and nothing else of the package
    @test run("Neura.request_capability isa Function").data
    @test !run("Neura.reset_kernel_state()").success

    # the receipt log keeps outcomes, not values
    run("zeros(10^6)")
    @test get_kernel_state().receipt_log[end].result.data === nothing
end
