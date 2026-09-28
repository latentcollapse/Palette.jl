# A digest of long build and test output.
#
# A failing cargo, tsc, dune, go or test-runner run can print thousands of
# lines, and the host shows a long result with its middle elided: the model
# then sees the first screen and the summary, not the errors in between. When
# a call's output is long and holds recognisable failures, a short digest of
# them opens the result, where elision never reaches.

const ANSI_ESCAPE = r"\e\[[0-9;?]*[A-Za-z]"
# Output shorter than this is shown whole, so it needs no digest.
const DIGEST_MIN_CHARS = 4000
const DIGEST_MAX_ENTRIES = 12

strip_ansi(s::AbstractString) = replace(s, ANSI_ESCAPE => "")

struct Finding
    kind::Symbol          # :error, :warning or :test
    location::String      # "path:line[:col]", or "" when the tool gives none
    message::String
end

# Each tool's error shapes, as (pattern, kind, location, message) readers over
# one line; the few multi-line shapes are handled after.
const LINE_SHAPES = [
    # tsc: a.ts(2,19): error TS2322: ...   and pretty: a.ts:2:19 - error TS2322: ...
    (r"^(\S+?\.[cm]?[jt]sx?)\((\d+),(\d+)\): (error|warning) (TS\d+: .*)$", m -> (Symbol(m[4]), "$(m[1]):$(m[2]):$(m[3])", m[5])),
    (r"^(\S+?\.[cm]?[jt]sx?):(\d+):(\d+) - (error|warning) (TS\d+: .*)$", m -> (Symbol(m[4]), "$(m[1]):$(m[2]):$(m[3])", m[5])),
    # go build/vet: ./m.go:2:14: declared and not used: x
    (r"^(\.?/?[\w./-]+\.go):(\d+):(\d+): (.*)$", m -> (:error, "$(m[1]):$(m[2]):$(m[3])", m[4])),
    # pytest: FAILED tests/test_x.py::test_a - AssertionError: ...
    (r"^FAILED ([\w./-]+::[\w\[\]./-]+)(?: - (.*))?$", m -> (:test, m[1], something(m[2], "failed"))),
    # cargo test: test tests::adds ... FAILED
    (r"^test (\S+) \.\.\. FAILED$", m -> (:test, m[1], "failed")),
    # jest/vitest: ● Suite › name   and node:test: ✖ name (4.01ms) (the summary block repeats them)
    (r"^\s*● (.+)$", m -> (:test, "", m[1])),
    (r"^✖ (?!failing tests:)(.+?)(?: \([\d.]+m?s\))?$", m -> (:test, "", m[1])),
    # Julia Test: Test Failed at /path/file.jl:12
    (r"^Test Failed at (\S+:\d+)", m -> (:test, m[1], "Test Failed")),
    (r"^Error During Test at (\S+:\d+)", m -> (:test, m[1], "Error During Test")),
]

function findings(text::AbstractString)
    out = Finding[]
    lines = split(text, '\n')
    for (i, line) in enumerate(lines)
        # rustc/cargo: error[E0308]: message, with the location on a following ` --> ` line
        if (m = match(r"^(error|warning)(\[\w+\])?: (.*)$", line)) !== nothing
            loc = ""
            for j in i+1:min(i + 3, length(lines))
                (l = match(r"^\s*--> (\S+)$", lines[j])) !== nothing && (loc = l[1]; break)
            end
            # cargo's closing lines (could not compile, test failed) only restate the count.
            isempty(loc) && occursin(r"^(could not compile|test failed|aborting due to|\d+ warnings? emitted|build failed)", m[3]) && continue
            push!(out, Finding(Symbol(m[1]), loc, string(something(m[2], ""), isempty(something(m[2], "")) ? "" : ": ", m[3])))
            continue
        end
        # unittest: FAIL: test_a (test_x.T.test_a), then a traceback ending in the exception
        if (m = match(r"^(FAIL|ERROR): (\w+) \(([\w.]+)\)", line)) !== nothing
            loc = ""; msg = m[1] == "FAIL" ? "failed" : "raised an error"
            for j in i+1:min(i + 60, length(lines))
                (startswith(lines[j], "=====") || startswith(lines[j], "Ran ")) && break
                (f = match(r"^\s*File \"([^\"]+)\", line (\d+)", lines[j])) !== nothing && (loc = "$(f[1]):$(f[2])")
                (x = match(r"^(\w*(?:Error|Exception|Exit)\w*): (.*)$", lines[j])) !== nothing && (msg = "$(x[1]): $(x[2])")
            end
            push!(out, Finding(:test, loc, "$(m[3]): $msg"))
            continue
        end
        # go test: --- FAIL: TestAdd (0.00s), then indented   m_test.go:3: message
        if (m = match(r"^\s*--- FAIL: (\S+)", line)) !== nothing
            loc = ""; msg = "failed"
            if i < length(lines) && (d = match(r"^\s+(\S+_test\.go:\d+): (.*)$", lines[i+1])) !== nothing
                loc = d[1]; msg = d[2]
            end
            push!(out, Finding(:test, loc, "$(m[1]): $msg"))
            continue
        end
        # rust test panics: thread 'tests::adds' (123) panicked at src/main.rs:4:23:  then the message
        if (m = match(r"^thread '([^']+)'.* panicked at (\S+?):?$", line)) !== nothing
            msg = i < length(lines) ? strip(lines[i+1]) : ""
            push!(out, Finding(:test, m[2], "$(m[1]) panicked: $msg"))
            continue
        end
        # OCaml: File "bin/m.ml", line 1, characters 28-31:  ... then Error: message
        if (m = match(r"^File \"([^\"]+)\", line (\d+)", line)) !== nothing
            for j in i+1:min(i + 8, length(lines))
                if (e = match(r"^(Error|Warning[^:]*): (.*)$", lines[j])) !== nothing
                    msg = e[2]
                    for k in j+1:min(j + 3, length(lines))
                        startswith(lines[k], "  ") || break
                        msg *= " " * strip(lines[k])
                    end
                    push!(out, Finding(startswith(e[1], "Error") ? :error : :warning, "$(m[1]):$(m[2])", msg))
                    break
                end
            end
            continue
        end
        for (rx, read) in LINE_SHAPES
            if (m = match(rx, line)) !== nothing
                kind, loc, msg = read(m)
                push!(out, Finding(kind, loc, strip(msg)))
                break
            end
        end
    end
    return out
end

"""
    with_digest(output) -> String

`output` without ANSI colour codes, and, when it is long and holds recognisable
errors or failing tests, a digest of them in front.
"""
function with_digest(output::AbstractString)
    text = strip_ansi(output)
    length(text) < DIGEST_MIN_CHARS && return text
    fs = findings(text)
    isempty(fs) && return text
    seen = Set{Tuple{Symbol, String, String}}()
    unique_fs = Finding[]
    for f in fs
        key = (f.kind, f.location, f.message)
        key in seen && continue
        push!(seen, key); push!(unique_fs, f)
    end
    panicked = Set(first(split(f.message, " panicked: ")) for f in unique_fs if f.kind === :test && occursin(" panicked: ", f.message))
    filter!(f -> !(f.kind === :test && f.message == "failed" && f.location in panicked), unique_fs)
    n(k) = count(f -> f.kind === k, unique_fs)
    counts = join(filter(!isempty, [n(:error) > 0 ? "$(n(:error)) error$(n(:error) == 1 ? "" : "s")" : "",
                                     n(:warning) > 0 ? "$(n(:warning)) warning$(n(:warning) == 1 ? "" : "s")" : "",
                                     n(:test) > 0 ? "$(n(:test)) failing test$(n(:test) == 1 ? "" : "s")" : ""]), ", ")
    # Errors and failing tests first; warnings only while there is room.
    ordered = vcat(filter(f -> f.kind !== :warning, unique_fs), filter(f -> f.kind === :warning, unique_fs))
    shown = first(ordered, DIGEST_MAX_ENTRIES)
    lines = ["[digest of $(count(==('\n'), text) + 1) lines of output: $counts]"]
    for f in shown
        loc = isempty(f.location) ? "" : f.location * "  "
        label = f.kind === :test ? "test " : string(f.kind, startswith(f.message, "[") ? "" : " ")
        push!(lines, "  $loc$label$(first(f.message, 200))")
    end
    length(ordered) > length(shown) && push!(lines, "  … and $(length(ordered) - length(shown)) more")
    return join(lines, "\n") * "\n\n" * text
end
