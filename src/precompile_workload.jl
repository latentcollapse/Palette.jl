# Runs only while the package is being precompiled. A new kernel used to
# compile its whole turn path while the model waited for the first reply:
# JSON both ways, execute's success and error paths, output capture, the
# deadline machinery and the shaping of values for the protocol. Running
# representative turns here caches that native code with the package.
#
# Every failure is swallowed: a workload problem must never fail the build,
# only leave some code uncompiled. Turn code runs in WorkloadScope, since
# precompilation refuses evaluation into a module this package does not own,
# and the kernel state is discarded afterwards.
baremodule WorkloadScope
using Base
end
if ccall(:jl_generating_output, Cint, ()) == 1
    try
        GLOBAL_STATE[] = KernelState(WorkloadScope)
        JSON.parse("""{"request_id":"1","kind":"EXECUTE","code":"1 + 1","payload":null,"timeout_s":60}""")
        for code in ("x = [1 2; 3 4]\nf(y) = y .+ 1\nf(x)",
                     "for i in 1:3\n    s = i\nend\nprintln(\"done\")",
                     "d = Dict(\"a\" => 1); (d, :b, 1.5, \"s\", nothing)",
                     "error(\"workload\")",
                     "undefined_name + 1",
                     "g(x::Int) = x\ng(\"s\")")
            (receipt, interrupted, _), output = execute_turn(code, 60.0)
            value = receipt.result.data
            safe_json(Dict{String,Any}("kind" => "RESULT", "epoch" => "e", "request_id" => "1",
                "success" => receipt.result.success, "data" => bounded_data(value), "display" => text_display(value),
                "output" => scrub(output), "error" => receipt.result.error, "call" => 1, "interrupted" => interrupted))
            retain_output!(1, output)
            binding_list!(WorkloadScope, 1)
        end
        execute_turn("1", nothing)
    catch
    finally
        GLOBAL_STATE[] = nothing
        empty!(OUTPUTS)
        empty!(WORKSPACE_PACKAGES)
        empty!(USED_FILES)
        foreach(f -> rm(f[1]; force=true), LATE_FILES)
        empty!(LATE_FILES)
        empty!(BINDING_SEEN)
    end
    precompile(Base.open, (Base.RawFD,))
end
