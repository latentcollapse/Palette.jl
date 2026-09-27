# The undefined name was `$name` interpolation inside a string literal of the
# call's code: the string was meant to hold source text for a file.
function interpolated_in_string(err::AbstractString, code::AbstractString)
    m = match(r"UndefVarError: `([^`]+)`", err)
    m === nothing && return nothing
    name = m[1]
    ex = try Meta.parseall(code) catch; return nothing end
    found = Ref(false)
    walk(x) = if x isa Expr
        if x.head === :string && any(a -> a === Symbol(name) || (a isa Expr && occursin(Regex("\\b" * name * "\\b"), string(a))), x.args)
            found[] = true
        end
        foreach(walk, x.args)
    end
    walk(ex)
    found[] ? name : nothing
end
using JSON
calls = JSON.parsefile(ARGS[1])
undef = [c for c in calls if occursin("UndefVarError", c["err"])]
hits = [(c, interpolated_in_string(c["err"], c["code"])) for c in undef]
println("UndefVarError failures: ", length(undef), "; interpolation in a string literal: ", count(h -> h[2] !== nothing, hits))
for (c, n) in hits
    println(n === nothing ? "  -  " : "  HIT", " ", rpad(c["run"], 20), first(replace(c["err"], "\n" => " "), 70))
end
