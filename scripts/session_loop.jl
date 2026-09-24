#!/usr/bin/env julia
#=
NeuraJL persistent session loop -- runs inside the sandboxed worker, kept
alive across many turns instead of one `-e script` per launch.

Protocol: newline-delimited JSON on stdin/stdout, one request per line, one
response per line, in order. The first thing printed is a HELLO line
carrying this process's own `epoch` -- a fresh UUID generated here, inside
this process, not handed in by the orchestrator -- so a caller holding a
handle from a previous process (this one crashed and got relaunched) gets
a real, unambiguous mismatch instead of silently talking to a different
Julia world that happens to share a session_id. See
`security/session.py`'s `NeuraSession` for the orchestrator side and why
this mirrors (not copies) NeuraBash's own `RUNTIME_EPOCH` lesson
(`Project-LIRA-NeuraBash/julia/bin/daemon.jl`).

Request:  {"request_id": "...", "kind": "EXECUTE" | "EPHEMERAL", "code": "...", "ceiling": {...}?}
Response: {"request_id": "...", "epoch": "...", "success": bool, "data": ..., "error": ...}
HELLO:    {"kind": "HELLO", "epoch": "..."}

`kind == "EXECUTE"` evaluates into this session's own persistent
`eval_module` -- the durable "mind": real state, real bindings, real
compiled methods, kept for the life of this process.

`kind == "EPHEMERAL"` does NOT run in this process at all. An earlier
version of this file ran ephemeral code in a fresh, throwaway `Module`
in-process (see `Neura.EphemeralTool`/`check_ephemeral_source!`, which
still exist and are still real, tested, and honestly documented as a
namespace-HYGIENE measure). That was proven, by direct adversarial
testing, not sufficient as an authority boundary: `Core.eval(Base,
:(function show(io::IO, x::Int) ... end))` -- a value only assembled at
RUNTIME -- extends a foreign module's method table with zero syntactic
trace in the submitted source for any parse-time check to see. No static
checker can fully police a language with reflective `eval`, and
crippling `eval` itself would violate NeuraJL's own "unbounded power
inside the sandbox" thesis. The fix is not a smarter checker; it's
putting the boundary underneath the language instead of inside it:
`EPHEMERAL` spawns a real, disposable, OS-sandboxed CHILD process via the
already-adversarially-proven `spawn_child_worker` capability (see
`security/broker.py`, `docs/THREAT_MODEL.md` rows 16-19). If the child's
code corrupts its own `Base.show`, that corruption dies with the child
process -- Linux throws the whole thing away, which is a fundamentally
stronger guarantee than trying to detect or reverse the corruption
afterward. `Neura.request_capability("spawn_child_worker", ...)` already
enforces `C_child ⊆ C_caller`; an ephemeral turn's optional `"ceiling"`
field (default `{}`, i.e. full language power, zero broker-mediated
authority) is validated against THIS session's own ceiling exactly like
any other spawn_child_worker request.
=#
using Neura

# Qualified access to Neura's OWN already-declared dependencies, not a
# separate `using JSON`/`using UUIDs` here -- confirmed by direct testing
# that a script run under a project whose Project.toml lists only `Neura`
# (not JSON/UUIDs directly) cannot `using JSON` itself even though Neura
# depends on it internally: a package's dependencies aren't visible by
# name to code outside that package just because the package is loadable.
# `Neura.JSON`/`Neura.UUIDs` work because `using JSON` inside Neura.jl's
# own source creates that exact binding, and this script never needs a
# project of its own beyond whatever already makes `using Neura` work.
const JSON = Neura.JSON
const UUIDs = Neura.UUIDs

const EPOCH = string(UUIDs.uuid4())

# The protocol gets its own duplicate of fd 1, and fd 1/fd 2 are then pointed
# at a sink file. Turn code prints, `run` children inherit fd 1, and tasks
# left running after a turn all write somewhere; none of it may reach the
# protocol channel, where one stray `println` used to be parsed as a
# response and kill the session.
const PROTO = let fd = ccall(:dup, Cint, (Cint,), 1)
    fd < 0 && error("dup(1) failed")
    fdio(fd, true)
end
const SINK = open(joinpath(tempdir(), "neurajl-background-output.log"), "a")
redirect_stdout(SINK)
redirect_stderr(SINK)

# Enough for any output a model can use; the host applies its own tighter cap.
const MAX_OUTPUT_BYTES = 256 * 1024
const MAX_DATA_JSON_BYTES = 256 * 1024

function safe_json(x)
    try
        return JSON.json(x)
    catch
        return JSON.json(string(x))
    end
end

function respond(resp::Dict{String,Any})
    println(PROTO, safe_json(resp))
    flush(PROTO)
end

# Runs `f` with fd 1 and fd 2 both on one pipe. A pipe, not a file: Julia
# buffers writes to a file stream, so a `run` child's output (written to the
# fd directly) showed up before prints that came earlier in the turn.
function capture_output(f)
    pipe = Pipe()
    Base.link_pipe!(pipe; reader_supports_async=true, writer_supports_async=true)
    collected = IOBuffer()
    total = Ref(0)
    reader = @async while !eof(pipe)
        chunk = readavailable(pipe)
        total[] += length(chunk)
        room = MAX_OUTPUT_BYTES - collected.size
        room > 0 && write(collected, length(chunk) <= room ? chunk : chunk[1:room])
    end
    value = nothing
    try
        redirect_stdout(pipe.in) do
            redirect_stderr(pipe.in) do
                value = f()
            end
        end
    finally
        close(pipe.in)
        # A background process the turn started still holds the write end, so
        # EOF may never come; take what has arrived rather than hang the turn.
        timedwait(() -> istaskdone(reader), 2.0)
        istaskdone(reader) || close(pipe.out)
    end
    output = String(take!(collected))
    total[] > MAX_OUTPUT_BYTES && (output *= "\n[output truncated: $(total[]) bytes total]")
    return value, output
end

function text_display(value)
    value === nothing && return nothing
    try
        return Base.invokelatest(sprint, show, MIME"text/plain"(), value; context=:limit => true)
    catch e
        return "<display failed: $(sprint(showerror, e))>"
    end
end

# `data` stays the raw value for callers that read it structurally, unless
# it cannot be serialized compactly; then the text rendering stands in.
function bounded_data(value)
    try
        length(JSON.json(value)) <= MAX_DATA_JSON_BYTES && return value
    catch
    end
    return text_display(value)
end

respond(Dict{String,Any}("kind" => "HELLO", "epoch" => EPOCH))

for line in eachline(stdin)
    isempty(strip(line)) && continue

    local req
    try
        req = JSON.parse(line)
    catch e
        respond(Dict{String,Any}("kind" => "ERROR", "epoch" => EPOCH, "error" => sprint(showerror, e)))
        continue
    end

    request_id = get(req, "request_id", nothing)
    kind = get(req, "kind", nothing)
    code = get(req, "code", nothing)
    resp = Dict{String,Any}("kind" => "RESULT", "epoch" => EPOCH, "request_id" => request_id)

    try
        code isa String || error("request 'code' must be a string")
        if kind == "EPHEMERAL"
            requested_ceiling = get(req, "ceiling", Dict{String,Any}())
            requested_ceiling isa AbstractDict || error("request 'ceiling' must be an object")
            # The child's own script: runs `code` through the SAME
            # ExecuteCode/execute path (real Core.eval, real receipt) as a
            # persistent turn would, but inside its own disposable process
            # -- then prints exactly one JSON line this process parses back.
            # `repr(code)` produces a safely re-escaped Julia string literal
            # (that's what `repr` is for); this is textual generation of
            # trusted host-side code embedding untrusted content as DATA,
            # not string-building a shell command.
            child_script = string(
                "using Neura; r = execute(ExecuteCode(", repr(code), ")); ",
                "println(Neura.JSON.json(Dict(\"success\"=>r.result.success, ",
                "\"data\"=>r.result.data, \"error\"=>r.result.error)))",
            )
            # `child_workspace`/`child_project`/`child_repo` are no longer
            # part of this request: the broker now always allocates the
            # child's workspace itself and uses its own session-established
            # project/repo paths -- a request can no longer choose WHERE a
            # child's filesystem view points, only WHICH capabilities it
            # gets (see broker.py's _handle_spawn_child_worker docstring
            # for the exploit this closed).
            spawn_resp = Neura.request_capability("spawn_child_worker", Dict(
                "ceiling" => requested_ceiling,
                "script" => child_script,
            ))
            if get(spawn_resp, "approved", false)
                child_stdout = String(get(spawn_resp["result"], "stdout", ""))
                lines = split(child_stdout, '\n')
                idx = findlast(ln -> !isempty(strip(ln)), lines)
                last_line = idx === nothing ? "" : lines[idx]
                child_result = JSON.parse(last_line)
                resp["success"] = get(child_result, "success", false)
                resp["data"] = get(child_result, "data", nothing)
                resp["output"] = idx === nothing ? "" : join(lines[1:idx-1], '\n')
                resp["error"] = get(child_result, "error", nothing)
                record_tool_capsule(
                    string(request_id), code,
                    OperationResult(resp["data"], resp["success"], resp["error"]),
                    0.0,
                )
            else
                resp["success"] = false
                resp["data"] = nothing
                resp["error"] = "spawn_child_worker denied: " * string(get(spawn_resp, "reason", "unknown"))
            end
        elseif kind == "EXECUTE"
            receipt, output = capture_output(() -> execute(ExecuteCode(code)))
            resp["success"] = receipt.result.success
            resp["data"] = bounded_data(receipt.result.data)
            resp["display"] = receipt.result.success ? text_display(receipt.result.data) : nothing
            resp["output"] = output
            resp["error"] = receipt.result.error
        else
            # Fail closed on an unrecognized `kind` -- confirmed by direct
            # testing that an earlier version of this branch ran ANY
            # non-"EPHEMERAL" kind (a typo, a missing field, a future
            # protocol version this process doesn't understand) as durable
            # ExecuteCode against the persistent mind. A malformed or
            # unrecognized request must be rejected, not silently treated
            # as "the durable default."
            error("unrecognized request 'kind': $(repr(kind)) (expected \"EXECUTE\" or \"EPHEMERAL\")")
        end
    catch e
        resp["success"] = false
        resp["data"] = nothing
        resp["error"] = sprint(showerror, e)
    end

    respond(resp)
end
