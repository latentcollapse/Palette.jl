# julia --project=<trial project> grade_ports.jl <workspace> <goldens.json> <port>
# Prints "<port>: <passed>/<total>" and the first failures.
using JSON
ws, gfile, name = ARGS
g = JSON.parse(read(gfile, String))[name]
exact = name in ("numeric", "random", "struct")
file = joinpath(ws, g["file"])
isfile(file) || (println("$name: 0/$(length(g["cases"])) (no $(g["file"]))"); exit())
holder = Module()
mod = try
    Base.include(holder, file)
    getfield(holder, Symbol(g["module"]))
catch e
    println("$name: 0/$(length(g["cases"])) (load failed: $(replace(first(sprint(showerror, e), 300), "\n" => " ")))"); exit()
end
norm(x) = x isa AbstractDict ? Dict{String,Any}(string(k) => norm(v) for (k, v) in x) :
          x isa Union{AbstractVector,Tuple} ? Any[norm(v) for v in x] :
          x isa Union{Symbol,AbstractChar,AbstractString} ? String(string(x)) : x
function same(e, x)
    if e isa AbstractDict && haskey(e, "__float__") && length(e) == 1
        v = e["__float__"]
        return x isa AbstractFloat && (v == "nan" ? isnan(x) : x == (v == "inf" ? Inf : -Inf))
    end
    e isa Bool && return x isa Bool && x == e
    e isa Integer && return x isa Number && !(x isa Bool) && x == e
    e isa AbstractFloat && return x isa Number && !(x isa Bool) && (exact ? (x == e && signbit(x) == signbit(e)) : isapprox(x, e; rtol=1e-9, atol=1e-12))
    e === nothing && return x === nothing
    e isa AbstractString && return x isa AbstractString && x == e
    e isa AbstractVector && return x isa AbstractVector && length(x) == length(e) && all(same(a, b) for (a, b) in zip(e, x))
    e isa AbstractDict && return x isa AbstractDict && Set(keys(x)) == Set(keys(e)) && all(same(e[k], x[k]) for k in keys(e))
    false
end
# Arguments that JSON cannot hold (inf, nan) arrive encoded like expected
# values; a port is called with the Float64 itself.
decode_arg(x) = x isa AbstractDict && haskey(x, "__float__") && length(x) == 1 ?
                Base.parse(Float64, replace(x["__float__"], "inf" => "Inf", "nan" => "NaN")) :
                x isa AbstractVector ? Any[decode_arg(v) for v in x] : x
ok = 0; fails = String[]
for (fn, raw_args, expected) in g["cases"]
    args = decode_arg(raw_args)
    global ok
    wants_error = expected isa AbstractDict && haskey(expected, "__error__")
    pass = try
        f = getfield(mod, Symbol(fn))
        got = Base.invokelatest(f, args...)
        !wants_error && same(expected, norm(got))
    catch
        wants_error
    end
    ok += pass
    pass || length(fails) >= 3 || push!(fails, "$fn$(first(JSON.json(raw_args), 120))")
end
println("$name: $ok/$(length(g["cases"]))", isempty(fails) ? "" : "  first failures: " * join(fails, " | "))
