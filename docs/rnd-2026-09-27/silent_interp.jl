# Successful calls that interpolate into a multi-line string holding source
# text (a `function`, `end`, `"""` or `@test` line) and write a file.
using JSON
calls = JSON.parsefile(ARGS[1])
looks_like_source(s) = occursin(r"\n\s*(function |end\b|@test|\"\"\"|module |struct |def |return )", s)
n = 0; shown = 0
for c in calls
    occursin(r"\bwrite\(", c["code"]) || continue
    ex = try Meta.parseall(c["code"]) catch; continue end
    hits = String[]
    walk(x) = if x isa Expr
        if x.head === :string
            lits = join(a for a in x.args if a isa String)
            if occursin('\n', lits) && looks_like_source(lits)
                append!(hits, [string(a) for a in x.args if !(a isa String)])
            end
        end
        foreach(walk, x.args)
    end
    walk(ex)
    isempty(hits) && continue
    global n += 1
    if shown < 8
        global shown += 1
        println(rpad(c["run"], 20), " interpolates: ", join(unique(hits)[1:min(end, 6)], ", "))
    end
end
println("successful file-writing calls interpolating into source-like text: ", n, " of ", length(calls))
