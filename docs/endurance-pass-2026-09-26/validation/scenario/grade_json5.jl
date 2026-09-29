# Hidden JSON5 corpus: julia --project=<trial project> grade_json5.jl <workspace> <cases.json>
using JSON
ws, casefile = ARGS
push!(LOAD_PATH, joinpath(ws, "json5"))
using JSON5Lite
cases = JSON.parsefile(casefile)
decode(x) = x isa AbstractDict ? (haskey(x, "__float__") ? Base.parse(Float64, replace(x["__float__"], "inf" => "Inf", "nan" => "NaN")) :
            Dict{String,Any}(k => decode(v) for (k, v) in x)) : x isa AbstractVector ? Any[decode(v) for v in x] : x
same(a, b) = a isa AbstractFloat && isnan(a) ? (b isa AbstractFloat && isnan(b)) :
             a isa AbstractDict ? (b isa AbstractDict && keys(a) == keys(b) && all(same(a[k], b[k]) for k in keys(a))) :
             a isa AbstractVector ? (b isa AbstractVector && length(a) == length(b) && all(same(x, y) for (x, y) in zip(a, b))) :
             a === nothing ? b === nothing : (a isa Number && b isa Number ? a == b : a == b)
ok = 0
for c in cases["valid"]
    global ok
    try
        ok += same(decode(c["expected"]), JSON5Lite.parse(c["input"]))
    catch
    end
end
bad = 0
for s in cases["invalid"]
    global bad
    try
        JSON5Lite.parse(s)
    catch e
        bad += isdefined(JSON5Lite, :ParseError) && e isa JSON5Lite.ParseError
    end
end
println("json5: valid $ok/$(length(cases["valid"])), invalid rejected with ParseError $bad/$(length(cases["invalid"]))")
