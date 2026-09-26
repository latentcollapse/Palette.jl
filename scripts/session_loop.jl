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

Request:  {"request_id": "...", "kind": "EXECUTE" | "EPHEMERAL", "code": "...", "ceiling": {...}?,
           "payload": "..."?, "timeout_s": number?}
Response: {"request_id": "...", "epoch": "...", "success": bool, "data": ..., "display": ..., "output": ...,
           "error": ..., "interrupted": true?, "kernel_exit": true?}
HELLO:    {"kind": "HELLO", "epoch": "..."}

`payload` is bound as `PAYLOAD` for that one EXECUTE turn. At `timeout_s` a
turn still waiting is interrupted (`interrupted`) and the kernel keeps its
state; one that ignores the interrupt for INTERRUPT_GRACE_S ends the process
right after its reply (`kernel_exit`).

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
# Requests arrive on a duplicate of fd 0 for the same reason, and fd 0 itself
# becomes /dev/null: a `readline()` or a `run(`cat`)` in turn code used to
# consume the next request and leave the host waiting for a reply until the
# turn timed out.
const PROTO_IN = let fd = ccall(:dup, Cint, (Cint,), 0)
    fd < 0 && error("dup(0) failed")
    open(Base.RawFD(fd))
end
redirect_stdin(open("/dev/null"))
const SINK = open(joinpath(tempdir(), "neurajl-background-output.log"), "a")
redirect_stdout(SINK)
redirect_stderr(SINK)

# `display(x)` goes through the display stack, whose TextDisplay was built at
# startup around the original stdout, which is the protocol pipe: one
# `display` in turn code wrote a matrix into the protocol and killed the
# session. This display writes to whatever stdout is when it is called, which
# during a turn is the turn's captured output.
struct TurnDisplay <: AbstractDisplay end
Base.display(::TurnDisplay, ::MIME"text/plain", @nospecialize(x)) = (show(stdout, MIME"text/plain"(), x); println(stdout))
Base.display(d::TurnDisplay, @nospecialize(x)) = display(d, MIME"text/plain"(), x)
Base.displayable(::TurnDisplay, ::MIME"text/plain") = true
empty!(Base.Multimedia.displays)
pushdisplay(TurnDisplay())

# Without the REPL loaded, `@doc sum` returns a raw DocStr instead of the
# rendered docstring.
import REPL

# Enough for any output a model can use; the host applies its own tighter cap.
const MAX_OUTPUT_BYTES = 256 * 1024
const MAX_DATA_JSON_BYTES = 256 * 1024

# Output is whatever bytes the turn printed. JSON.jl copies invalid UTF-8
# into the line as-is, and the reader rejected the whole line.
valid_utf8(s::String) = isvalid(s) ? s : String(map(c -> isvalid(c) ? c : '\ufffd', collect(s)))

function safe_json(x)
    json = try
        JSON.json(x)
    catch
        JSON.json(string(x))
    end
    return valid_utf8(json)
end

function respond(resp::Dict{String,Any})
    println(PROTO, safe_json(resp))
    flush(PROTO)
end

# Julia-level stdout and stderr for a turn: every write is one write(2) to
# the capture file, which fd 1 and fd 2 (and so every `run` child) also
# point at. Writes land in the order they happen, with no buffering and no
# task switch; through a libuv pipe each `println` cost ~50us, and printing
# 10^6 lines outran the turn limit.
struct FdWriter <: IO
    fd::Cint
end
function Base.unsafe_write(w::FdWriter, p::Ptr{UInt8}, n::UInt)
    done = 0
    while done < n
        r = ccall(:write, Cssize_t, (Cint, Ptr{UInt8}, Csize_t), w.fd, p + done, n - done)
        if r < 0
            Libc.errno() == Libc.EINTR && continue
            throw(SystemError("write", Libc.errno()))
        end
        done += r
    end
    return Int(n)
end
Base.write(w::FdWriter, b::UInt8) = (r = Ref(b); GC.@preserve r unsafe_write(w, Base.unsafe_convert(Ptr{UInt8}, r), UInt(1)))
Base.isopen(::FdWriter) = true
Base.flush(::FdWriter) = nothing

const CAPTURE_PATH = joinpath(tempdir(), "neurajl-turn-output")

# Runs `f` with fd 1 and fd 2 on a fresh append-only file. A process the
# turn left running keeps its descriptor to that file, now unlinked, so its
# later output reaches neither this turn nor the next one.
function capture_output(f)
    rm(CAPTURE_PATH; force=true)
    file = open(CAPTURE_PATH, "a+")
    value = nothing
    try
        redirect_stdout(file) do
            redirect_stderr(file) do
                Base._redirect_io_global(FdWriter(1), 1)
                Base._redirect_io_global(FdWriter(2), 2)
                value = f()
            end
        end
    finally
        close(file)
    end
    total = filesize(CAPTURE_PATH)
    output = String(open(io -> read(io, MAX_OUTPUT_BYTES), CAPTURE_PATH))
    rm(CAPTURE_PATH; force=true)
    total > MAX_OUTPUT_BYTES && (output *= "\n[output truncated: $total bytes total]")
    return value, output
end

# The session module's name is an internal uuid, and types defined by turn
# code print qualified with it (`Main.KernelScope_2d97….P(3)`).
const KERNEL_NAME = string(nameof(Neura.get_kernel_state().eval_module))
scrub(s::AbstractString) = replace(s, "Main.$KERNEL_NAME." => "", "$KERNEL_NAME." => "", "Main.$KERNEL_NAME" => "Main",
                                   KERNEL_NAME => "Main")
scrub(x) = x

function text_display(value)
    value === nothing && return nothing
    try
        return scrub(Base.invokelatest(sprint, show, MIME"text/plain"(), value; context=:limit => true))
    catch e
        return "<display failed: $(sprint(showerror, e))>"
    end
end

# `data` carries the raw value only when it is a scalar or a short collection
# of short things. The host renders `display`; encoding a large value just to
# learn its size took 14.7s for a 400 MB array and 4.6s for a million-entry
# Dict, and `Base.summarysize` of that Dict alone takes 4.9s.
const SCALAR = Union{Nothing, Bool, Number, AbstractString, Symbol}
const MAX_DATA_ELEMENTS = 1000
const COLLECTION = Union{AbstractArray, AbstractDict, AbstractSet, Tuple, NamedTuple}
short(x) = x isa SCALAR ? !(x isa AbstractString && ncodeunits(x) > MAX_DATA_JSON_BYTES) :
           x isa COLLECTION && length(x) <= MAX_DATA_ELEMENTS
function bounded_data(value)
    if value isa SCALAR
        short(value) || return text_display(value)
        return value isa Number && !isfinite(value) ? text_display(value) : value
    end
    if value isa COLLECTION && short(value) && all(short, value isa AbstractDict ? values(value) : value)
        try
            length(JSON.json(value)) <= MAX_DATA_JSON_BYTES && return value
        catch
        end
    end
    return text_display(value)
end

# In trials a model met these errors and retried the same thing several
# times, a model request each; the hint names what works instead.
const PKG_OFFLINE = get(ENV, "JULIA_PKG_OFFLINE", "") == "true"
const LOADABLE = let deps = get(Base.parsed_toml(Base.active_project()), "deps", Dict())
    join(["the Julia standard library"; sort!([String(k) for k in keys(deps) if k != "Neura"])], ", ")
end

# A reserved word where a name belongs: an argument (`quote::UInt8`), an
# assignment (`end = 3`), a keyword argument or a loop variable. Julia's
# parser reports these as "Expected `end`" several columns away.
const RESERVED_AS_NAME = r"(?:^|[(,;\s])(quote|end|begin|let|local|global|module|baremodule|struct|macro|do|try|catch|finally|export|import|using|const|return|break|continue|function|if|elseif|else|while|for|abstract|primitive|mutable|public)\s*(?:::|=(?!=)|,\s*\w|\s+in\s)"
function with_hint(err, code)
    err isa AbstractString || return err
    if occursin("must be quoted in commands", err)
        return err * "\nHint: backticks start one program without a shell. " *
               "Use sh\"...\" or bash(\"...\") for pipes, globs, redirects and &&."
    elseif startswith(err, "ParseError") && occursin(r"after \$ in string|interpolat", err)
        return err * "\nHint: in a Julia string \$ interpolates; write \\\$ for a literal dollar sign. sh\"...\" passes \$ to the shell " *
               "unchanged, and a file's text passed as this call's payload needs no escaping: write(path, PAYLOAD)."
    elseif startswith(err, "ParseError") && (m = match(RESERVED_AS_NAME, code)) !== nothing
        return err * "\nHint: `$(m[1])` is a reserved word in Julia and cannot name a variable or argument."
    elseif startswith(err, "ParseError") && occursin("\"\"\"", code)
        return err * "\nHint: to write a file's text without Julia quoting, pass it as this call's payload and use write(path, PAYLOAD)."
    elseif PKG_OFFLINE && (
        occursin(r"not found in current path|has no known versions|Could not resolve host|name resolution", err) ||
        (occursin("Pkg", err) &&
            occursin(r"(?i)read-only file system|permission denied", err)))
        # First, not last: the Pkg error that follows runs to many lines.
        return "This kernel has no network, so Pkg.add cannot install packages. Loadable: $LOADABLE.\n" * err
    end
    return err
end

# Processes in this sandbox, other than the kernel and bwrap's reaper (PID 1,
# the kernel's parent). The sandbox has its own PID namespace, so /proc lists
# exactly what turns started. Outside such a namespace (a bare test run) there
# is no safe way to tell, and nothing is reaped.
const OWN_NAMESPACE = getpid() == 1 ||
    (ccall(:getppid, Cint, ()) == 1 && isfile("/proc/1/comm") && strip(read("/proc/1/comm", String)) == "bwrap")
function sandbox_pids()
    OWN_NAMESPACE || return Set{Int}()
    pids = Set{Int}()
    self = getpid()
    for d in readdir("/proc")
        pid = tryparse(Int, d)
        pid === nothing || pid == 1 || pid == self || push!(pids, pid)
    end
    return pids
end
# Kills what a turn started, so a wait on it returns, and nothing it began
# keeps running after the turn is reported interrupted. Processes earlier
# turns started are left alone.
function reap(before::Set{Int})
    for pid in setdiff(sandbox_pids(), before)
        ccall(:kill, Cint, (Cint, Cint), pid, 9)
    end
end

# How long after the deadline a turn has to finish once interrupted. Turn code
# that catches the InterruptException gets it again every second.
const INTERRUPT_GRACE_S = 5.0

"""
    run_turn(f, timeout_s) -> (value, interrupted, stuck)

Runs `f` in its own task. At `timeout_s` the task gets an InterruptException
and the processes it started are killed; waiting work (sleep, run, read, I/O)
ends there with the kernel and every binding intact. The deadline is noticed
only when the task yields: compute that never yields runs until the host
kills the kernel. `stuck` means the task was still running when the grace
period ended.
"""
function run_turn(f, timeout_s)
    t = Task(f)
    t.sticky = true
    schedule(t)
    timeout_s === nothing && return (fetch(t), false, false)
    before = sandbox_pids()
    interrupted = Ref(false)
    outcome = Channel{Symbol}(2)
    @async (try wait(t) catch end; put!(outcome, :done))
    deadline = Timer(timeout_s)
    watchdog = @async begin
        try
            wait(deadline)
        catch
            return  # closed: the turn finished in time
        end
        istaskdone(t) && return
        interrupted[] = true
        giveup = time() + INTERRUPT_GRACE_S
        while !istaskdone(t) && time() < giveup
            try
                schedule(t, InterruptException(); error=true)
            catch
            end
            reap(before)
            timedwait(() -> istaskdone(t), 1.0; pollint=0.05)
        end
        istaskdone(t) || put!(outcome, :stuck)
    end
    result = take!(outcome)
    close(deadline)
    result === :stuck && return (nothing, true, true)
    interrupted[] && reap(before)
    # An interrupt that lands after the turn's own error handling, while its
    # bookkeeping runs, fails the task itself.
    value = try
        fetch(t)
    catch e
        e isa TaskFailedException ? e.task.exception : e
    end
    return (value, interrupted[], false)
end

respond(Dict{String,Any}("kind" => "HELLO", "epoch" => EPOCH))

# This script is not precompiled, so its turn machinery compiled during the
# first call and doubled its latency (0.8s to 1.6s). Compiling it here, after
# HELLO, overlaps with the host deciding what to send first. The one warm-up
# call leaves no history, receipt or binding behind.
let state = Neura.get_kernel_state()
    Core.eval(state.eval_module, Expr(:global, Expr(:(=), :PAYLOAD, nothing)))
    (r, _, _), out = capture_output(() -> run_turn(() -> execute(ExecuteCode("print(\"\"); [1 2]")), 60.0))
    (e, _, _), _ = capture_output(() -> run_turn(() -> execute(ExecuteCode("error(\"warm-up\")")), 60.0))
    with_hint(e.result.error, "")
    text_display(r.result.data); bounded_data(r.result.data); bounded_data(Dict("a" => [1]))
    scrub(out); with_hint("x", "y"); safe_json(Dict{String,Any}("a" => 1))
    empty!(state.execution_history)
    empty!(state.receipt_log)
    Core.eval(state.eval_module, Expr(:global, Expr(:(=), :ans, nothing)))
end

for line in eachline(PROTO_IN)
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
    timeout_s = get(req, "timeout_s", nothing)
    resp = Dict{String,Any}("kind" => "RESULT", "epoch" => EPOCH, "request_id" => request_id)

    try
        code isa String || error("request 'code' must be a string")
        timeout_s === nothing || timeout_s isa Real && timeout_s > 0 || error("request 'timeout_s' must be a positive number")
        payload = get(req, "payload", nothing)
        payload === nothing || payload isa String || error("request 'payload' must be a string")
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
            child_script = string("using Neura; Neura.ephemeral_main(", repr(code), ")")
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
                child_result = try
                    JSON.parse(last_line)
                catch
                    # The child died before printing its result line.
                    stderr_tail = strip(String(get(spawn_resp["result"], "stderr", "")))
                    error("ephemeral child exited with code $(get(spawn_resp["result"], "returncode", "?")) and no result" *
                          (isempty(stderr_tail) ? "" : ":\n" * last(stderr_tail, 1500)))
                end
                resp["success"] = get(child_result, "success", false)
                resp["data"] = get(child_result, "data", nothing)
                resp["display"] = get(child_result, "display", nothing)
                resp["output"] = idx === nothing ? "" : rstrip(join(lines[1:idx-1], '\n'))
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
            mod = Neura.get_kernel_state().eval_module
            # A file's text arrives as a JSON string and is bound as it is,
            # so it needs no Julia quoting: `write("x.py", PAYLOAD)`.
            Core.eval(mod, Expr(:global, Expr(:(=), :PAYLOAD, payload)))
            (receipt, interrupted, stuck), output = capture_output(
                () -> run_turn(() -> execute(ExecuteCode(code)), timeout_s))
            resp["output"] = scrub(output)
            if stuck
                resp["success"] = false
                resp["data"] = nothing
                resp["error"] = "The call exceeded its $(timeout_s)s limit and kept running after being interrupted " *
                                "for $(Int(INTERRUPT_GRACE_S))s, so the kernel stopped. Every binding is gone; files written to the workspace remain."
                resp["kernel_exit"] = true
                respond(resp)
                ccall(:_exit, Cvoid, (Cint,), 3)
            end
            if !(receipt isa Neura.OperationReceipt)
                receipt = Neura.OperationReceipt(UUIDs.uuid4(), Neura.Dates.now(), "ExecuteCode",
                                                 Neura.OperationResult(nothing, false, sprint(showerror, receipt)),
                                                 0.0, Neura.get_kernel_state().id)
            end
            resp["success"] = receipt.result.success && !interrupted
            resp["data"] = resp["success"] ? bounded_data(receipt.result.data) : nothing
            resp["display"] = resp["success"] ? text_display(receipt.result.data) : nothing
            resp["error"] = scrub(something(receipt.result.error, ""))
            if interrupted
                resp["interrupted"] = true
                resp["error"] = "Interrupted: the call exceeded its $(timeout_s)s limit. The kernel and every binding are intact; " *
                                "processes this call started were stopped. Output printed before the interrupt is above.\n" * resp["error"]
            end
            isempty(resp["error"]) && (resp["error"] = nothing)
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

    resp["error"] = with_hint(get(resp, "error", nothing), code isa String ? code : "")
    respond(resp)
end
