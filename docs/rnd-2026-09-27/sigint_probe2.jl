# One case per process: argv[1]. Prints "spinning", then the host sends SIGINT.
Base.exit_on_sigint(false)
cases = Dict("tight" => :(let s = 0; while true; s += 1; end; end),
             "float" => :(let x = 0.0; while true; x = sin(x) + 1e-9; end; end),
             "alloc" => :(let v = Int[]; while true; push!(v, 1); length(v) > 10^6 && empty!(v); end; end),
             "sort"  => :(for _ in 1:10^6; sort!(rand(10^6)); end))
t = Task(() -> try
    Core.eval(Main, cases[ARGS[1]]); :finished
catch e
    e isa InterruptException ? :interrupted : e
end)
t.sticky = true
println("spinning"); flush(stdout)
schedule(t)
r = fetch(t)
println("result: ", r); flush(stdout)
