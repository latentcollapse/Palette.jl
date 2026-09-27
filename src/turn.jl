# The turn machinery of scripts/session_loop.jl: capturing a turn's output,
# running it under a deadline, and shaping its value for the protocol. It
# lives in the package so its native code is cached with the package; as
# part of the unprecompiled script it compiled in every new kernel, about
# seven seconds before the first reply.

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

# Julia-level stdout and stderr for a turn: every write is one write(2) to
# the capture file, which fd 1 and fd 2 (and so every `run` child) also
# point at. Writes land in the order they happen, with no buffering and no
# task switch; through a libuv pipe each `println` cost ~50us, and printing
# 10^6 lines outran the turn limit.
struct FdWriter <: IO
    fd::Cint
    target::IOStream
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

# `redirect_stdout(devnull) do ... end` in turn code restores the stream it
# found, which is an FdWriter, and Base has no method for that: the idiom
# threw, and a redirect to a file left fd 1 on that file for the rest of the
# turn, so everything printed after it was lost.
function (f::Base.RedirectStdStream)(w::FdWriter)
    f.unix_fd in (1, 2) || throw(ArgumentError("cannot redirect fd $(f.unix_fd) to an FdWriter"))
    f(w.target)
    Base._redirect_io_global(w, f.unix_fd)
    return w
end

# tempdir() is looked up when a turn runs: this file is precompiled, and a
# constant would hold the build machine's temp directory.
capture_path() = joinpath(tempdir(), "neurajl-turn-output")

# Runs `f` with fd 1 and fd 2 on a fresh append-only file. A process the
# turn left running keeps its descriptor to that file, now unlinked, so its
# later output reaches neither this turn nor the next one.
function capture_output(@nospecialize(f))
    # Boxed so the closures below compile once, not once per caller: the
    # first real turn compiled them again for its own closure type (0.7s).
    fn = Ref{Function}(f)
    path = capture_path()
    rm(path; force=true)
    file = open(path, "a+")
    value = nothing
    try
        redirect_stdout(file) do
            redirect_stderr(file) do
                Base._redirect_io_global(FdWriter(1, file), 1)
                Base._redirect_io_global(FdWriter(2, file), 2)
                value = fn[]()
            end
        end
    finally
        close(file)
    end
    total = filesize(path)
    output = String(open(io -> read(io, MAX_OUTPUT_BYTES), path))
    keep_for_late_output!(path, total)
    total > MAX_OUTPUT_BYTES && (output *= "\n[output truncated: $total bytes total]")
    return value, output
end

# A process a call left running keeps writing to that call's capture file.
# The last few are kept, renamed, and what grows in them after their call is
# reported as background output at the start of the next call.
const LATE_FILES = Tuple{String, Int}[]
const KEEP_LATE_FILES = 32
const LATE_SEQ = Ref(0)

function keep_for_late_output!(path::String, total::Int)
    late = "$path-$(LATE_SEQ[] += 1)"
    mv(path, late; force=true)
    push!(LATE_FILES, (late, total))
    while length(LATE_FILES) > KEEP_LATE_FILES
        rm(popfirst!(LATE_FILES)[1]; force=true)
    end
    return
end

function late_output()
    parts = String[]
    for (i, (path, read_to)) in enumerate(LATE_FILES)
        total = isfile(path) ? filesize(path) : 0
        total > read_to || continue
        skip = max(read_to, total - MAX_BACKGROUND_BYTES)
        push!(parts, open(f -> (seek(f, skip); String(read(f))), path))
        LATE_FILES[i] = (path, drop_reported!(path, total))
    end
    return join(parts)
end

# The session module's name is an internal uuid, and types defined by turn
# code print qualified with it (`Main.KernelScope_2d97….P(3)`).
function scrub(s::AbstractString)
    name = string(nameof(get_kernel_state().eval_module))
    return replace(s, "Main.$name." => "", "$name." => "", "Main.$name" => "Main", name => "Main")
end
scrub(x) = x

const TEST_PKG = Base.PkgId(Base.UUID("8dfed614-e22c-5e08-85e1-65c5234f0b40"), "Test")

# A passing `include("test/runtests.jl")` returns its DefaultTestSet, whose
# default display dumps every nested testset down to each one's RNG state:
# 14,000 to 25,000 characters a run in the traces, all of it elided. It is
# shown as its counts, and the testset itself stays in `ans`.
function testset_summary(value)
    test = get(Base.loaded_modules, TEST_PKG, nothing)
    test === nothing && return nothing
    value isa test.DefaultTestSet || return nothing
    c = Base.invokelatest(test.get_test_counts, value)
    return "Test.DefaultTestSet \"$(value.description)\": $(c.passes + c.cumulative_passes) passed, " *
           "$(c.fails + c.cumulative_fails) failed, $(c.errors + c.cumulative_errors) errored, " *
           "$(c.broken + c.cumulative_broken) broken ($(c.duration))"
end

function text_display(value)
    value === nothing && return nothing
    try
        summary = testset_summary(value)
        summary === nothing || return summary
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

# Processes in this sandbox, other than the kernel and bwrap's reaper (PID 1,
# the kernel's parent). The sandbox has its own PID namespace, so /proc lists
# exactly what turns started. Outside such a namespace (a bare test run) there
# is no safe way to tell, and nothing is reaped.
own_namespace() = getpid() == 1 ||
    (ccall(:getppid, Cint, ()) == 1 && isfile("/proc/1/comm") && strip(read("/proc/1/comm", String)) == "bwrap")
function sandbox_pids()
    own_namespace() || return Set{Int}()
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
function run_turn(@nospecialize(f), timeout_s)
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

# Between calls, stdout and stderr (and fd 1 and 2 of every child) point at
# this file. A task still running after its call printed into it, and nothing
# read it back, so its output and its failure reached nobody.
const SINK = Ref{Union{Nothing, IOStream}}(nothing)
const SINK_PATH = Ref("")
const SINK_READ = Ref(0)
const MAX_BACKGROUND_BYTES = 16 * 1024
# Output already reported is dropped once a file holding it passes this size:
# the sandbox's /tmp is memory, and a chatty background job (50 KB/s in the
# endurance pass) grew it by 4 GB a day. Every writer holds these files in
# append mode, so truncating them is safe.
const MAX_REPORTED_BYTES = 1024 * 1024
function drop_reported!(path::String, read_to::Int)
    read_to > MAX_REPORTED_BYTES || return read_to
    open(path, "w") do _ end   # truncate
    return 0
end
const REPORTED_TASKS = WeakKeyDict{Task, Nothing}()

"""
    report_background(mod)

Prints what happened since the last call: output that background tasks and
processes wrote, and each failed task bound in `mod`, once.
"""
function report_background(mod::Module)
    text = late_output()
    io = SINK[]
    if io !== nothing
        flush(io)
        total = filesize(SINK_PATH[])
        if total > SINK_READ[]
            skip = max(SINK_READ[], total - MAX_BACKGROUND_BYTES)
            text *= open(f -> (seek(f, skip); String(read(f))), SINK_PATH[])
            SINK_READ[] = drop_reported!(SINK_PATH[], total)
        end
    end
    if !isempty(text)
        length(text) > MAX_BACKGROUND_BYTES && (text = "…" * last(text, MAX_BACKGROUND_BYTES))
        print("[background output since the last call]\n", text, endswith(text, '\n') ? "" : "\n")
    end
    for sym in Base.invokelatest(names, mod; all=true)
        Base.invokelatest(isdefined, mod, sym) || continue
        t = Base.invokelatest(getglobal, mod, sym)
        t isa Task && istaskfailed(t) && !haskey(REPORTED_TASKS, t) || continue
        REPORTED_TASKS[t] = nothing
        err = t.result isa Exception ? first(split(sprint(showerror, t.result), '\n')) : repr(t.result)
        println("[background: task `$sym` failed: $err]")
    end
    return nothing
end

# Workspace files a call named, with their modification time and size then,
# and the call. A binding computed from a file the model later changed
# outside the kernel kept the old contents, with nothing to say so.
const USED_FILES = Dict{String, Tuple{Tuple{Float64, Int}, Int}}()
const MAX_USED_FILES = 500

file_stamp(path) = (st = stat(path); (st.mtime, Int(st.size)))

function note_file!(path::AbstractString, call::Int)
    root = WORKSPACE_ROOT[]
    isempty(root) && return
    full = abspath(root, path)
    startswith(full, root * "/") && isfile(full) || return
    (haskey(USED_FILES, full) || length(USED_FILES) < MAX_USED_FILES) || return
    USED_FILES[full] = (file_stamp(full), call)
    push!(get!(CALL_FILES, call, Tuple{String, Tuple{Float64, Int}}[]), (full, USED_FILES[full][1]))
    return
end

function string_literals!(out::Vector{String}, ex)
    if ex isa String
        push!(out, ex)
    elseif ex isa Expr
        foreach(a -> string_literals!(out, a), ex.args)
    end
    return out
end

"""
    note_files_named!(code, call)

Records each workspace file that `code` names in a string literal, sh"..."
commands included, as used by `call`.
"""
function note_files_named!(code::String, call::Int)
    ex = try
        Meta.parseall(code)
    catch
        return
    end
    for lit in string_literals!(String[], ex), tok in split(lit, (' ', '\t', '\n', '\'', '"', ';', '|', '<', '>', '(', ')', '=', ','))
        isempty(tok) || length(tok) > 4096 || note_file!(tok, call)
    end
    return
end

# Package sources are reloaded, not reported.
in_workspace_package(path) = any(m -> startswith(path, dirname(something(pathof(m), "/nonexistent/x")) * "/"),
                                 keys(WORKSPACE_PACKAGES))

"""
    report_changed_files()

Prints, once per change, the workspace files that changed on disk since the
call that last named them.
"""
function report_changed_files()
    changed = String[]
    for (path, (stamp, call)) in collect(USED_FILES)
        in_workspace_package(path) && (delete!(USED_FILES, path); continue)
        now = isfile(path) ? file_stamp(path) : nothing
        now == stamp && continue
        push!(changed, "$(relpath(path, WORKSPACE_ROOT[])) ($(now === nothing ? "deleted; " : "")call $call)")
        now === nothing ? delete!(USED_FILES, path) : (USED_FILES[path] = (now, call))
    end
    isempty(changed) && return
    println("[changed on disk since the call that used it: ", join(sort!(changed), ", "),
            ". Values computed from these files before the change are out of date.]")
    return
end

# The binding each name held after the last call, and the call that set it.
# The host keeps the list from each reply, so when the kernel dies it can say
# which bindings were lost instead of only that they were.
const BINDING_SEEN = Dict{Symbol, Tuple{UInt, Int}}()
const MAX_LISTED_BINDINGS = 200

function short_type(v)
    v isa Function && return "function"
    v isa Module && return "module"
    v isa Type && return "type"
    T = typeof(v)
    T isa DataType && parentmodule(T) === get_kernel_state().eval_module && !current_definition(T) &&
        return "$(nameof(T)), an earlier definition"
    t = scrub(string(T))
    return length(t) > 40 ? string(nameof(T)) : t
end

"""
    binding_list!(mod, call) -> Vector{String}

`name (type, call n)` for each of the session's own bindings, where `n` is
the last call that gave it a new value.
"""
function binding_list!(mod::Module, call::Int)
    rows = String[]
    live = Set{Symbol}()
    for sym in sort!(Base.invokelatest(names, mod; all=true))
        (sym === nameof(mod) || sym in KERNEL_BINDINGS || startswith(string(sym), '#')) && continue
        Base.invokelatest(isdefined, mod, sym) || continue
        v = Base.invokelatest(getglobal, mod, sym)
        push!(live, sym)
        id = objectid(v)
        seen = get(BINDING_SEEN, sym, nothing)
        seen === nothing || seen[1] != id ? (BINDING_SEEN[sym] = (id, call)) : nothing
        length(rows) < MAX_LISTED_BINDINGS && push!(rows, "$sym ($(short_type(v)), call $(BINDING_SEEN[sym][2]))")
    end
    filter!(kv -> kv.first in live, BINDING_SEEN)
    return rows
end

"""
    execute_turn(code, timeout_s) -> ((receipt, interrupted, stuck), output)

One persistent turn: report what happened in the background and which used
files changed, reload edited workspace packages, run `code` under the
deadline, and capture everything it printed.
"""
function execute_turn(code::String, timeout_s::Union{Nothing, Float64})
    state = get_kernel_state()
    call = length(state.execution_history) + 1
    return capture_output() do
        isempty(REVIVAL_REPORT[]) || (println(REVIVAL_REPORT[]); REVIVAL_REPORT[] = "")
        report_background(state.eval_module)
        report_changed_files()
        refresh_workspace_packages!()
        turn = run_turn(() -> execute(ExecuteCode(code)), timeout_s)
        refresh_workspace_packages!(reload=false)
        note_files_named!(code, call)
        ok = turn[1] isa OperationReceipt && turn[1].result.success && !turn[2]
        log_definitions!(code, call; failed_in=ok ? nothing : state.eval_module)
        turn
    end
end
