using Neura, Random, Serialization
Random.seed!(1)
st = Neura.get_kernel_state(); mod = st.eval_module
dir = mktempdir(); Neura.STATE_DIR[] = dir; Neura.WORKSPACE_ROOT[] = dir
rs(n) = randstring(n)
Core.eval(mod, :(cases4 = $([(rs(20), rs(30)) for _ in 1:200_000])))
Core.eval(mod, :(input_random = $(Any[rand(Bool) ? rs(15) : rand(1:1000) for _ in 1:300_000])))
Core.eval(mod, :(expected_random = $(Any[[rs(5), rand()] for _ in 1:100_000])))
Core.eval(mod, :(byuser = $(Dict(rs(8) => rand(1:10^6, 500) for _ in 1:500))))
for i in 1:300; Core.eval(mod, :($(Symbol("small", i)) = $(rand(10)))); end
Neura.snapshot_state!(1)   # compile
t = @elapsed m = Neura.snapshot_state!(2)
println("snapshot: ", round(t, digits=2), " s, ", round(m["bytes"] / 1e6, digits=1), " MB, groups ", length(m["data"]))
# where does it go: the walk alone
w() = for sym in names(mod; all=true)
    isdefined(mod, sym) || continue
    v = getglobal(mod, sym); v isa Module && continue
    Neura.refusal(Neura.Walk(mod, IdDict{Any, Nothing}(), Set{String}(), Set{UInt}()), v)
end
w(); println("walk only: ", round(@elapsed(w()), digits=2), " s")
ser() = for sym in names(mod; all=true)
    isdefined(mod, sym) || continue
    v = getglobal(mod, sym); v isa Module && continue
    Neura.snapshot_bytes(mod, v)
end
ser(); println("serialize only: ", round(@elapsed(ser()), digits=2), " s")
