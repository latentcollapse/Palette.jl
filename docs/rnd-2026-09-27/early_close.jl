# The lines a docstring's own """ leaked out of an enclosing triple-quoted
# literal: the literal (opened in an expression position) ends at the
# docstring's first """ line, and what follows up to the next """ runs as code.
function leaked_lines(code::AbstractString)
    out = UnitRange{Int}[]
    for m in eachmatch(r"(?:=|\(|\*|=>|,)\s*\"\"\"", code)
        start = m.offset + length(m.match)
        rest = code[start:end]
        close = match(r"\n[ \t]*\"\"\"[ \t]*\n(?=[ \t]+\S)", rest)
        close === nothing && continue
        after = start + close.offset + length(close.match) - 1
        nxt = findnext("\"\"\"", code, after)
        nxt === nothing && continue
        first_line = count(==('\n'), code[1:prevind(code, after)]) + 1
        last_line = count(==('\n'), code[1:first(nxt)]) + 1
        push!(out, first_line:last_line)
    end
    return out
end
function error_line(err::AbstractString)
    m = match(r"around call \d+:(\d+)|at this call, line (\d+)|# Error @ this call, line (\d+)", err)
    m === nothing && return nothing
    parse(Int, something(m.captures...))
end
# The call failed in text the model meant as the content of a string literal.
function failed_in_leaked_text(err, code)
    l = error_line(err)
    l !== nothing && any(r -> l in r, leaked_lines(code))
end
using JSON
calls = JSON.parsefile(ARGS[1])
hits = [c for c in calls if failed_in_leaked_text(c["err"], c["code"])]
println("failed calls: ", length(calls), "; fires on: ", length(hits))
for c in hits
    println(rpad(c["run"], 20), " ", replace(first(c["err"], 100), "\n" => " | "))
end
println("\n--- misses")
for c in calls
    occursin(r"UndefVarError: `(K|key|new|key0)`", c["err"]) || continue
    failed_in_leaked_text(c["err"], c["code"]) && continue
    println(c["run"], " err line=", error_line(c["err"]), " leaked=", leaked_lines(c["code"]), " tq=", count("\"\"\"", c["code"]))
    println("   ", replace(first(c["err"], 160), "\n" => " | "))
end
c = first(filter(c -> occursin("pattern not found", c["err"]), calls))
println("\n--- pattern-not-found code:\n", first(c["code"], 900))
