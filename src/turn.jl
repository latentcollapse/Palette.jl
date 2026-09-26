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
    rm(path; force=true)
    total > MAX_OUTPUT_BYTES && (output *= "\n[output truncated: $total bytes total]")
    return value, output
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

"""
    execute_turn(code, timeout_s) -> ((receipt, interrupted, stuck), output)

One persistent turn: reload edited workspace packages, run `code` under the
deadline, and capture everything it printed.
"""
function execute_turn(code::String, timeout_s::Union{Nothing, Float64})
    return capture_output() do
        refresh_workspace_packages!()
        turn = run_turn(() -> execute(ExecuteCode(code)), timeout_s)
        refresh_workspace_packages!(reload=false)
        turn
    end
end
