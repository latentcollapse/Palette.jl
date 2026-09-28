# Revival: what a new kernel can truthfully bring back of the one before it.
#
# After each call that succeeds, while the model reads the reply, the kernel
# writes a snapshot of its state to the host's state directory. When a kernel
# stops (a call that never yields, a crash, a harness restart) the next kernel
# revives from the last snapshot, which is the state at the end of the last
# call that completed:
#
# - definitions (functions, methods, types, macros, `using`/`import`) are
#   rebuilt by evaluating their source again, never deserialized, and then
#   checked against what the old kernel had;
# - data bindings are deserialized, in groups that keep shared references
#   shared, only when Julia, the packages and every user type they use are
#   unchanged;
# - closures and anonymous functions are data too: Serialization carries a
#   closure's own type and method, and its captured values are checked like
#   any struct's fields;
# - everything else (tasks, processes, IO, pointers, values built from an
#   earlier version of a type) is reported lost, with the code that made it.
#
# Nothing is reported restored unless it is the same value or the same
# definition. Anything uncertain is reported as such, or as lost.

using Serialization

const STATE_DIR = Ref("")
const REVIVAL_FORMAT = 1
# Per binding (or group of bindings sharing data) and per snapshot; the
# environment can lower them, as the tests do.
max_binding_bytes() = parse(Int, get(ENV, "NEURAJL_STATE_MAX_BINDING_BYTES", string(16 * 1024 * 1024)))
max_snapshot_bytes() = parse(Int, get(ENV, "NEURAJL_STATE_MAX_BYTES", string(128 * 1024 * 1024)))
const MAX_RECIPE_CHARS = 240

# Definition statements from every call, in order: what a new kernel
# evaluates again. Whole calls are never replayed, only these forms.
const DEFINITION_LOG = Vector{Dict{String, Any}}()
# Files each call named (see note_file!), so a restored value computed from a
# file that has since changed can be reported stale.
const CALL_FILES = Dict{Int, Vector{Tuple{String, Tuple{Float64, Int}}}}()
# ENV as the kernel found it; a snapshot records what calls changed.
const INITIAL_ENV = Ref{Dict{String, String}}(Dict{String, String}())
# What the first call after a revival is told.
const REVIVAL_REPORT = Ref("")

# --- definitions ---------------------------------------------------------

const DEFINITION_MACROS = ("@kwdef", "Base.@kwdef", "@inline", "@noinline", "@enum", "Base.@enum", "@doc",
                           "Core.@doc", "@__doc__", "@static")

function macro_name(ex::Expr)
    ex.head === :macrocall || return ""
    m = ex.args[1]
    m isa GlobalRef && return "$(m.mod).$(m.name)"
    m isa Expr && m.head === :. && m.args[2] isa QuoteNode && return "$(m.args[1]).$(m.args[2].value)"
    return string(m)
end

is_signature(ex) = ex isa Expr && (ex.head === :call || (ex.head in (:where, :(::)) && is_signature(ex.args[1])))

"""
    definition_kind(ex) -> String or nothing

`"def"` for a function, method, macro or type definition, `"using"` for
`using`/`import`, `"const"` for a constant, `"include"` for `include("…")` of
a literal path, and `nothing` for anything else. Only these forms are ever
evaluated again.
"""
function definition_kind(ex)
    ex isa Expr || return nothing
    h = ex.head
    h in (:function, :macro, :struct, :abstract, :primitive, :module) && return "def"
    h === :(=) && is_signature(ex.args[1]) && return "def"
    h in (:using, :import) && return "using"
    h === :const && return "const"
    if h === :macrocall
        name = macro_name(ex)
        if name == "Core.@doc" || name == "@doc"
            # A docstring: the documented expression is the last argument.
            return definition_kind(ex.args[end]) == "def" ? "def" : nothing
        end
        name in DEFINITION_MACROS || return nothing
        (endswith(name, "@enum") || definition_kind(ex.args[end]) == "def") && return "def"
        return nothing
    end
    if h === :call && ex.args[1] === :include && length(ex.args) == 2 && ex.args[2] isa String
        return "include"
    end
    return nothing
end

function top_statements(ex)
    out = Any[]
    ex isa Expr && ex.head in (:toplevel, :block) || return Any[ex]
    for a in ex.args
        a isa LineNumberNode && continue
        append!(out, a isa Expr && a.head in (:toplevel, :block) ? top_statements(a) : Any[a])
    end
    return out
end

function defined_names(ex)
    ex isa Expr || return String[]
    h = ex.head
    if h === :macrocall
        return endswith(macro_name(ex), "@enum") ? enum_names(ex) : defined_names(ex.args[end])
    elseif h in (:struct,)
        return [string(type_head(ex.args[2]))]
    elseif h === :module
        return [string(ex.args[2])]
    elseif h in (:abstract, :primitive)
        return [string(type_head(ex.args[1]))]
    elseif h in (:function, :macro, :(=))
        sig = ex.args[1]
        while sig isa Expr && sig.head in (:where, :(::))
            sig = sig.args[1]
        end
        sig isa Expr && sig.head === :call || return String[]
        f = sig.args[1]
        f isa Expr && f.head === :(::) && return String[]   # a callable-object method
        name = string(f)
        return [h === :macro ? "@" * name : name]
    elseif h === :const
        a = ex.args[1]
        a isa Expr && a.head === :(=) || return String[]
        return a.args[1] isa Symbol ? [string(a.args[1])] : String[]
    end
    return String[]
end

type_head(x) = x isa Symbol ? x : x isa Expr && x.head in (:curly, :<:, :(::)) ? type_head(x.args[1]) : x
function enum_names(ex)
    args = filter(a -> !(a isa LineNumberNode), ex.args[2:end])
    isempty(args) && return String[]
    names = [string(type_head(args[1]))]
    for a in args[2:end]
        if a isa Symbol
            push!(names, string(a))
        elseif a isa Expr && a.head === :(=)
            push!(names, string(a.args[1]))
        elseif a isa Expr && a.head === :block
            append!(names, [string(b isa Expr ? b.args[1] : b) for b in a.args if !(b isa LineNumberNode)])
        end
    end
    return names
end

"""
    log_definitions!(code, call)

Appends the definition statements of `code` to DEFINITION_LOG. Called for
every call, successful or not: a failed call may have defined things before
it failed, and the check after a revival compares against what the kernel
really had. A failed call's statement that bound nothing is left out.
"""
# The names a `using`/`import` binds: `using A` binds A, `using A: f` binds
# f, `import A.B as C` binds C.
function imported_names(ex)
    out = String[]
    last_name(p) = p isa Expr && p.head === :. ? string(p.args[end]) : string(p)
    for a in ex.args
        if a isa Expr && a.head === :(:)
            for b in a.args[2:end]
                push!(out, b isa Expr && b.head === :as ? string(b.args[2]) : last_name(b))
            end
        elseif a isa Expr && a.head === :as
            push!(out, string(a.args[2]))
        else
            push!(out, last_name(a))
        end
    end
    return out
end

function log_definitions!(code::String, call::Int; failed_in::Union{Nothing, Module}=nothing)
    ex = try
        Meta.parseall(code; filename="call $call")
    catch
        return
    end
    for st in top_statements(ex)
        kind = definition_kind(st)
        kind === nothing && continue
        entry = Dict{String, Any}("call" => call, "kind" => kind, "code" => string(st),
                                  "names" => defined_names(st))
        if kind == "include"
            path = abspath(WORKSPACE_ROOT[], st.args[2])
            entry["path"] = path
            entry["stamp"] = isfile(path) ? collect(file_stamp(path)) : nothing
            entry["names"] = isfile(path) ? unique(reduce(vcat, (defined_names(d) for (_, d) in file_definitions(path)); init=String[])) : String[]
        end
        # In a call that failed, a statement after the error never ran. One
        # that bound nothing is left out, or a revival would report the loss
        # of something the kernel never had.
        if failed_in !== nothing
            # A method of another module's function (`Base.show`) cannot be
            # looked up by name here, so it is kept.
            bound = kind == "using" ? imported_names(st) : entry["names"]
            !isempty(bound) && !any(n -> occursin('.', n) || Base.invokelatest(isdefined, failed_in, Symbol(n)), bound) && continue
        end
        push!(DEFINITION_LOG, entry)
    end
    return
end

# Definition forms of an included file, as they are on disk now, with nested
# includes resolved the same way.
function file_definitions(path::String, depth::Int=0)
    depth > 8 && return Any[]
    ex = Meta.parseall(read(path, String); filename=path)
    out = Any[]
    for st in top_statements(ex)
        kind = definition_kind(st)
        if kind == "include"
            inner = abspath(dirname(path), st.args[2])
            isfile(inner) && append!(out, file_definitions(inner, depth + 1))
        elseif kind in ("def", "using")
            push!(out, (path, st))
        end
    end
    return out
end

# --- data ----------------------------------------------------------------

# Why a value cannot be revived as the same value, or nothing when it can.
# `user` collects the kernel's own types the value uses, and `ids` the
# mutable objects it reaches, so bindings sharing one are saved together.
struct Walk
    mod::Module
    seen::IdDict{Any, Nothing}
    user::Set{String}
    ids::Set{UInt}
end

const REFUSED_TYPES = (Task, Channel, Condition, Threads.Condition, ReentrantLock, Threads.SpinLock, Timer,
                       Base.Process, Base.ProcessChain, Base.Libc.RawFD, WeakRef, Module, Core.MethodInstance,
                       Method, Core.CodeInfo, Base.Semaphore, Base.Event)

const PTR_FREE = IdDict{Any, Bool}()
function ptr_free(T)
    get!(PTR_FREE, T) do
        T <: Ptr && return false
        isstructtype(T) || return true
        PTR_FREE[T] = true   # recursive types
        all(ptr_free, fieldtypes(T))
    end
end

function current_definition(T::DataType)
    m = parentmodule(T)
    isdefined(m, nameof(T)) || return false
    b = Base.invokelatest(getglobal, m, nameof(T))
    return Base.unwrap_unionall(b) isa DataType && Base.unwrap_unionall(b).name === T.name
end

# A function type the kernel created for an anonymous function or closure.
anonymous_function_type(T) = T isa DataType && T <: Function && startswith(string(nameof(T)), '#')

# Serialization sends a closure's whole type (its method included) only for
# closures of the real Main; one of the kernel's module it sends by name, and a
# new kernel would find no such type, or worse, a same-named closure of a
# later definition. This serializer sends the kernel's closures whole, so a
# revived closure runs the code it was made with.
mutable struct SnapshotSerializer{I<:IO} <: Serialization.AbstractSerializer
    io::I
    counter::Int
    table::IdDict{Any, Any}
    pending_refs::Vector{Int}
    known_object_data::Dict{UInt64, Any}
    version::Int
    mod::Module
    SnapshotSerializer(io::I, mod::Module) where {I<:IO} =
        new{I}(io, 0, IdDict{Any, Any}(), Int[], Dict{UInt64, Any}(), Serialization.ser_version, mod)
end

Serialization.should_send_whole_type(s::SnapshotSerializer, t::DataType) =
    (t.name.module === s.mod && anonymous_function_type(t)) ||
    invoke(Serialization.should_send_whole_type, Tuple{Any, DataType}, s, t)

function snapshot_bytes(mod::Module, x)
    buf = IOBuffer()
    s = SnapshotSerializer(buf, mod)
    Serialization.writeheader(s)
    serialize(s, x)
    return take!(buf)
end

# A closure deserializes with its own method, so its code must come from the
# kernel's module or from a package the new kernel loads too.
function closure_module_refusal(w::Walk, T::DataType)
    m = parentmodule(T)
    m === w.mod && return nothing
    Base.moduleroot(m) in (Base, Core) || haskey(Base.loaded_modules, Base.PkgId(Base.moduleroot(m))) ||
        return "it is a closure from module $(m), which a new kernel does not load"
    return nothing
end

function check_type(w::Walk, @nospecialize(T))
    T isa DataType || return nothing
    anonymous_function_type(T) && (r = closure_module_refusal(w, T)) !== nothing && return r
    for p in T.parameters
        p isa Type && (r = check_type(w, p)) !== nothing && return r
    end
    # Serialization rebuilds a closure's type in its own module, so there is no
    # definition of it to compare; a new kernel's closures reuse the same names.
    # Every value of one closure type is saved in one group: a group read on its
    # own would make its own copy of the type, and `===` would fail between them.
    anonymous_function_type(T) && (push!(w.ids, objectid(T)); return nothing)
    m = parentmodule(T)
    if m === w.mod
        current_definition(T) ||
            return "its type $(nameof(T)) is an earlier definition, since replaced by a new `struct $(nameof(T))`"
        push!(w.user, string(nameof(T)))
    end
    return nothing
end

function refusal(w::Walk, @nospecialize(x))::Union{Nothing, String}
    x isa Union{Nothing, Missing, Bool, Number, Char, String, Symbol} && return nothing
    T = typeof(x)
    for R in REFUSED_TYPES
        x isa R && return "a $(nameof(R)) cannot be revived"
    end
    # Serialization saves a Regex as its pattern and flags and compiles it
    # again. Two bindings sharing one Regex come back as two equal copies; a
    # Regex cannot be changed, so only `===` can tell.
    x isa Regex && return nothing
    x isa Ptr && return "it holds a pointer"
    x isa IO && !(x isa IOBuffer) && return "an open $(nameof(T)) cannot be revived"
    if x isa Function && isdefined(T, :instance) && !startswith(string(nameof(x)), '#')
        m = parentmodule(x)
        m === w.mod && (push!(w.user, string(nameof(x))); return nothing)
        return Base.moduleroot(m) in (Base, Core) || haskey(Base.loaded_modules, Base.PkgId(Base.moduleroot(m))) ?
               nothing : "it refers to function $(nameof(x)) of an unloaded module"
    end
    # Any other function value is a closure or an anonymous function: checked
    # below like a struct whose fields are the values it captured.
    if x isa Type
        u = Base.unwrap_unionall(x)
        u isa DataType && parentmodule(u) === w.mod && !current_definition(u) &&
            return "type $(nameof(u)) was replaced by a later definition"
        u isa DataType && parentmodule(u) === w.mod && push!(w.user, string(nameof(u)))
        return nothing
    end
    haskey(w.seen, x) && return nothing
    ismutable(x) && (w.seen[x] = nothing; push!(w.ids, objectid(x)))
    (r = check_type(w, T)) === nothing || return r
    return refusal_struct(w, x)
end

function refusal_struct(w::Walk, @nospecialize(x))
    T = typeof(x)
    if x isa Union{Array, Memory}
        E = eltype(x)
        if isbitstype(E)
            return ptr_free(E) ? nothing : "its elements hold pointers"
        end
        for i in eachindex(x)
            isassigned(x, i) || continue
            (r = refusal(w, @inbounds x[i])) === nothing || return r
        end
        return nothing
    end
    isbitstype(T) && return ptr_free(T) ? nothing : "it holds a pointer"
    for i in 1:nfields(x)
        isdefined(x, i) || continue
        (r = refusal(w, getfield(x, i))) === nothing || return r
    end
    return nothing
end

# Fields and field types of a kernel-defined type, as text: a type redefined
# with a different layout, even one Serialization would accept, is caught.
function type_fingerprint(mod::Module, name::String)
    isdefined(mod, Symbol(name)) || return nothing
    t = Base.invokelatest(getglobal, mod, Symbol(name))
    t isa Function && return "function"
    u = Base.unwrap_unionall(t)
    u isa DataType || return nothing
    return string(u.name.name, "{", join(string.(u.parameters), ","), "}:",
                  isstructtype(u) && !isabstracttype(u) ? join(("$f::$(fieldtype(u, f))" for f in fieldnames(u)), ";") : "abstract",
                  ismutabletype(u) ? ":mutable" : "")
end

# Every method of a kernel function, as text, to compare after a rebuild.
function method_set(mod::Module, name::String)
    isdefined(mod, Symbol(name)) || return nothing
    f = Base.invokelatest(getglobal, mod, Symbol(name))
    f isa Function || return nothing
    return sort!([string(m.sig) for m in Base.invokelatest(methods, f) if m.module === mod])
end

# What makes the package environment what it is: data is deserialized only
# into the same one.
function environment_identity()
    manifest = something(Base.project_file_manifest_path(Base.active_project()), "")
    pkgs = sort!([string(k.name, "@", something(pkgversion(m), "stdlib"))
                  for (k, m) in Base.loaded_modules if k.uuid !== nothing])
    return Dict{String, Any}("julia" => string(VERSION),
                             "manifest" => isfile(manifest) ? bytes2hex(sha256(read(manifest))) : "",
                             "packages" => pkgs)
end

# The code that last set `name`, for a binding that cannot be revived.
one_line(ex) = first(replace(string(ex isa Expr ? Base.remove_linenums!(deepcopy(ex)) : ex), r"#=.*?=#" => "", r"\s+" => " "), MAX_RECIPE_CHARS)

function recipe(name::String, call::Int)
    hist = get_kernel_state().execution_history
    1 <= call <= length(hist) || return ""
    code = hist[call].code
    isempty(code) && return ""
    ex = try
        Meta.parseall(code)
    catch
        return first(replace(code, r"\s+" => " "), MAX_RECIPE_CHARS)
    end
    for st in top_statements(ex)
        st isa Expr && st.head in (:(=), :const, :global) || continue
        lhs = st.head === :(=) ? st.args[1] : st.args[1]
        lhs isa Expr && lhs.head === :(=) && (lhs = lhs.args[1])
        (lhs === Symbol(name) || (lhs isa Expr && lhs.head === :tuple && Symbol(name) in lhs.args)) &&
            return one_line(st)
    end
    return first(replace(strip(code), r"\s+" => " "), MAX_RECIPE_CHARS)
end

# --- snapshot ------------------------------------------------------------

mutable struct Group
    names::Vector{String}
    ids::Set{UInt}
    user::Set{String}
end

# The call whose state the last complete snapshot holds, in this kernel, and
# how long that snapshot took.
const LAST_SAVED_CALL = Ref(0)
const LAST_SNAPSHOT_SECONDS = Ref(0.0)
# When saving takes this long, a snapshot gives way to a waiting request, so
# the model does not wait for it, until this many calls have gone unsaved. A
# quick snapshot always completes: the state revived is then the last call's.
const SLOW_SNAPSHOT_SECONDS = 2.0
const MAX_UNSAVED_CALLS = 5

"""
    note_completed_call!(call)

Records in STATE_DIR that `call` completed. A snapshot can give way and fall
behind; a revival compares this with the call its snapshot holds and says
which calls' effects on the kernel it could not bring back.
"""
function note_completed_call!(call::Int)
    dir = STATE_DIR[]
    isempty(dir) && return nothing
    tmp = joinpath(dir, "last_call.tmp")
    write(tmp, string(call))
    mv(tmp, joinpath(dir, "last_call"); force=true)
    return nothing
end

"""
    snapshot_state!(call; waiting = () -> false)

Writes the state at the end of `call` to STATE_DIR, replacing the last
snapshot only once the new one is complete. When the last complete snapshot was
slow and recent, and `waiting()` says a request is waiting, it stops and
returns `nothing`; the last complete snapshot stays.
"""
function snapshot_state!(call::Int; waiting::Function = () -> false)
    dir = STATE_DIR[]
    isempty(dir) && return nothing
    give_way() = LAST_SNAPSHOT_SECONDS[] >= SLOW_SNAPSHOT_SECONDS && call - LAST_SAVED_CALL[] < MAX_UNSAVED_CALLS && waiting()
    give_way() && return nothing
    started = time()
    mod = get_kernel_state().eval_module
    consts = Set(n for e in DEFINITION_LOG if e["kind"] == "const" for n in e["names"])
    defnames = Set(n for e in DEFINITION_LOG if e["kind"] in ("def", "include") for n in e["names"])
    bindings = Dict{String, Any}[]
    groups = Group[]
    for (k, sym) in enumerate(sort!(Base.invokelatest(names, mod; all=true)))
        k % 32 == 0 && give_way() && return nothing
        (sym === nameof(mod) || sym in KERNEL_BINDINGS || startswith(string(sym), '#')) && continue
        Base.invokelatest(isdefined, mod, sym) || continue
        v = Base.invokelatest(getglobal, mod, sym)
        name = string(sym)
        setcall = get(BINDING_SEEN, sym, (UInt(0), call))[2]
        b = Dict{String, Any}("name" => name, "type" => short_type(v), "call" => setcall,
                              "const" => name in consts)
        own = v isa Function ? isdefined(typeof(v), :instance) && parentmodule(v) === mod && nameof(v) === sym :
              v isa Type && Base.unwrap_unionall(v) isa DataType && parentmodule(Base.unwrap_unionall(v)) === mod &&
              nameof(Base.unwrap_unionall(v)) === sym
        if own && name in defnames
            b["class"] = "definition"
            b["check"] = v isa Function ? method_set(mod, name) : type_fingerprint(mod, name)
        elseif name in defnames && !(name in consts)
            # Made by a definition (an @enum member): rebuilt with it, checked by value.
            b["class"] = "definition"
            b["check"] = "value:" * repr(v)
        elseif own
            b["class"] = "runtime"
            b["reason"] = "it was not defined by top-level code of a call (inside `let`, `@eval` or a block), so it cannot be rebuilt"
        elseif v isa Module
            b["class"] = haskey(Base.loaded_modules, Base.PkgId(v)) ? "import" : "runtime"
            b["class"] == "runtime" && (b["reason"] = "a module defined in the session cannot be revived")
        else
            w = Walk(mod, IdDict{Any, Nothing}(), Set{String}(), Set{UInt}())
            why = try
                refusal(w, v)
            catch e
                "it could not be inspected ($(typeof(e)))"
            end
            if why === nothing
                b["class"] = "data"
                b["user_types"] = sort!(collect(w.user))
                g = Group([name], w.ids, w.user)
                for other in filter(o -> !isdisjoint(o.ids, w.ids), groups)
                    append!(g.names, other.names); union!(g.ids, other.ids); union!(g.user, other.user)
                    filter!(o -> o !== other, groups)
                end
                push!(groups, g)
            else
                b["class"] = "runtime"
                b["reason"] = why
            end
        end
        b["class"] == "runtime" && (b["recipe"] = recipe(name, setcall))
        b["files"] = [[p, collect(s)] for (p, s) in get(CALL_FILES, setcall, Tuple{String, Tuple{Float64, Int}}[])]
        push!(bindings, b)
    end
    byname = Dict(b["name"] => b for b in bindings)
    seq = string(call, "-", round(Int, time() * 1000) % 10^9)
    written = String[]
    stored = Dict{String, Any}[]
    total = 0
    for (i, g) in enumerate(groups)
        if give_way()
            foreach(f -> rm(joinpath(dir, f * ".tmp"); force=true), written)
            return nothing
        end
        bytes = UInt8[]
        ok = try
            bytes = snapshot_bytes(mod, Dict(n => Base.invokelatest(getglobal, mod, Symbol(n)) for n in g.names))
            true
        catch e
            for n in g.names
                byname[n]["class"] = "runtime"
                byname[n]["reason"] = "serializing it failed: $(first(sprint(showerror, e), 160))"
                byname[n]["recipe"] = recipe(n, byname[n]["call"])
            end
            false
        end
        ok || continue
        why = length(bytes) > max_binding_bytes() * length(g.names) ?
                  "$(Base.format_bytes(length(bytes))) is over the $(Base.format_bytes(max_binding_bytes())) limit per binding" :
              total + length(bytes) > max_snapshot_bytes() ?
                  "the snapshot reached its $(Base.format_bytes(max_snapshot_bytes())) limit" : nothing
        if why !== nothing
            for n in g.names
                byname[n]["class"] = "runtime"
                byname[n]["reason"] = "not saved: " * why
                byname[n]["recipe"] = recipe(n, byname[n]["call"])
            end
            continue
        end
        total += length(bytes)
        file = "data-$seq-$i.jls"
        write(joinpath(dir, file * ".tmp"), bytes)
        push!(written, file)
        push!(stored, Dict{String, Any}("file" => file, "names" => sort(g.names), "sha256" => bytes2hex(sha256(bytes)),
                                        "user_types" => sort!(collect(g.user))))
    end
    usertypes = Set(t for g in stored for t in g["user_types"])
    manifest = Dict{String, Any}(
        "format" => REVIVAL_FORMAT, "call" => call, "module" => string(nameof(mod)), "workspace" => WORKSPACE_ROOT[],
        "environment" => environment_identity(),
        "load_path" => copy(LOAD_PATH), "active_project" => something(Base.active_project(), ""),
        "cwd" => pwd(), "env" => Dict(k => v for (k, v) in ENV if get(INITIAL_ENV[], k, nothing) != v),
        "env_removed" => [k for k in keys(INITIAL_ENV[]) if !haskey(ENV, k)],
        "definitions" => DEFINITION_LOG, "bindings" => bindings, "data" => stored,
        "type_fingerprints" => Dict(t => type_fingerprint(mod, t) for t in usertypes),
        "used_files" => [[p, collect(s), c] for (p, (s, c)) in USED_FILES],
        "workspace_packages" => Dict(string(nameof(mod_)) => Dict(k => collect(v) for (k, v) in snap) for (mod_, snap) in WORKSPACE_PACKAGES),
        "processes" => [first(cmd, 200) for (_, cmd, _) in background_processes()],
        "bytes" => total, "seconds" => round(time() - started, digits=3))
    for f in written
        mv(joinpath(dir, f * ".tmp"), joinpath(dir, f); force=true)
    end
    tmp = joinpath(dir, "manifest.json.tmp")
    write(tmp, JSON.json(manifest))
    mv(tmp, joinpath(dir, "manifest.json"); force=true)   # the commit point
    LAST_SAVED_CALL[] = call
    LAST_SNAPSHOT_SECONDS[] = time() - started
    keep = Set(written)
    for f in readdir(dir)
        startswith(f, "data-") && !(f in keep) && rm(joinpath(dir, f); force=true)
    end
    return manifest
end

# --- revival -------------------------------------------------------------

"""
    revival_module_name() -> Union{Nothing, String}

The eval-module name the last kernel used, so this one can take it: values
of kernel-defined types deserialize only into a module of the same name.
"""
function revival_module_name()
    path = joinpath(STATE_DIR[], "manifest.json")
    isempty(STATE_DIR[]) || !isfile(path) ? nothing : try
        m = JSON.parse(read(path, String))
        get(m, "workspace", nothing) == WORKSPACE_ROOT[] ? String(m["module"]) : nothing
    catch
        nothing
    end
end

fmt_binding(b) = "$(b["name"]) ($(b["type"]), call $(b["call"]))"

# A list line that stays readable at any size: in full while short, then as
# names only, then as the first names and a count; varinfo() has the rest.
const REPORT_LIST_CHARS = 1500
function short_list(heading::String, items::Vector{String})
    line = "  $heading: " * join(items, ", ")
    length(line) <= REPORT_LIST_CHARS && return line
    names = [first(split(i, " ("; limit=2)) for i in items]
    shown = String[]; n = 0
    for nm in names
        n + length(nm) + 2 > REPORT_LIST_CHARS && break
        push!(shown, nm); n += length(nm) + 2
    end
    rest = length(names) - length(shown)
    return "  $heading ($(length(items))): " * join(shown, ", ") *
           (rest > 0 ? ", and $rest more (varinfo() lists every binding)" : "")
end

"""
    revive_state!() -> String

Rebuilds the last snapshot's state in this kernel, and returns the report the
first call shows.
"""
read_or_empty(path) = isfile(path) ? read(path, String) : ""

function revive_state!()
    dir = STATE_DIR[]
    path = joinpath(dir, "manifest.json")
    (isempty(dir) || !isfile(path)) && return ""
    m = try
        JSON.parse(read(path, String))
    catch e
        return "[revival] The previous kernel stopped, and its snapshot could not be read " *
               "($(first(sprint(showerror, e), 160))). Nothing was revived; files in the workspace remain."
    end
    get(m, "format", 0) == REVIVAL_FORMAT || return "[revival] The previous kernel's snapshot is in an unknown format. Nothing was revived."
    # A state saved for another workspace belongs to another task.
    get(m, "workspace", nothing) == WORKSPACE_ROOT[] || return ""
    state = get_kernel_state()
    mod = state.eval_module
    call = Int(m["call"])

    # The environment turn code set up: where packages load from, and where it works.
    empty!(LOAD_PATH); append!(LOAD_PATH, String.(m["load_path"]))
    isempty(m["active_project"]) || (Base.ACTIVE_PROJECT[] = m["active_project"])
    isdir(m["cwd"]) && cd(m["cwd"])
    for (k, v) in m["env"]; ENV[k] = v; end
    for k in m["env_removed"]; delete!(ENV, k); end

    # Definitions, in call order. Package code loads first from `using`.
    errors = Dict{String, String}()
    changed_files = Set{String}()
    pending = Any[]
    for e in m["definitions"]
        e["kind"] == "const" && continue
        if e["kind"] == "include"
            p = e["path"]
            if !isfile(p)
                foreach(n -> errors[n] = "$(relpath(p, WORKSPACE_ROOT[])) is gone", e["names"])
                continue
            end
            e["stamp"] !== nothing && Tuple(e["stamp"]) != file_stamp(p) && push!(changed_files, p)
            for (file, st) in file_definitions(p)
                push!(pending, (file, st, e))
            end
        else
            push!(pending, (nothing, Meta.parse(e["code"]), e))
        end
    end
    function replay(items)
        failed = Any[]
        for item in items
            (file, st, e) = item
            try
                if file === nothing
                    Core.eval(mod, st)
                else
                    task_local_storage(:SOURCE_PATH, file) do
                        Core.eval(mod, st)
                    end
                end
            catch err
                push!(failed, (item, first(sprint(showerror, err isa LoadError ? err.error : err), 160)))
            end
        end
        return failed
    end
    failed = with_logger(DocReplacementFilter(current_logger())) do
        replay(pending)
    end

    # Everything after the replay runs in the world the replay made: checks
    # call methods it defined (an @enum's names, a type's `show`).
    return Base.invokelatest(finish_revival, m, mod, state, call, pending, failed, errors, changed_files, replay)
end

function finish_revival(m, mod, state, call, pending, failed, errors, changed_files, replay)
    dir = STATE_DIR[]
    lines = String[]
    exact = String[]; rebuilt = String[]; approx = String[]; stale = String[]; lost = String[]
    # Data, when this is the environment it was saved in.
    envnow = environment_identity()
    envthen = m["environment"]
    bindings = Dict(b["name"] => b for b in m["bindings"])
    data_block = if envthen["julia"] != envnow["julia"]
        "it was saved by Julia $(envthen["julia"]) and this is $(envnow["julia"])"
    elseif envthen["manifest"] != envnow["manifest"]
        "the package environment changed since it was saved"
    else
        nothing
    end
    values = Dict{String, Any}()
    for g in m["data"]
        names = String.(g["names"])
        why = data_block
        if why === nothing
            bad = [t for t in g["user_types"] if get(m["type_fingerprints"], t, nothing) != type_fingerprint(mod, t)]
            isempty(bad) || (why = "type $(join(bad, ", ")) is defined differently now")
        end
        file = joinpath(dir, g["file"])
        if why === nothing
            bytes = isfile(file) ? read(file) : nothing
            why = bytes === nothing ? "its data file is missing" :
                  bytes2hex(sha256(bytes)) != g["sha256"] ? "its data file is damaged" : nothing
            if why === nothing
                try
                    d = Base.invokelatest(deserialize, IOBuffer(bytes))
                    for n in names
                        values[n] = d[n]
                    end
                catch err
                    why = "reading it failed: $(first(sprint(showerror, err), 160))"
                end
            end
        end
        if why !== nothing
            for n in names
                bindings[n]["class"] = "runtime"
                bindings[n]["reason"] = why
            end
        end
    end
    for (n, v) in collect(values)
        b = bindings[n]
        try
            Core.eval(mod, Expr(b["const"] ? :const : :global, Expr(:(=), Symbol(n), QuoteNode(v))))
        catch err
            delete!(values, n)
            b["class"] = "runtime"
            b["reason"] = "binding it again failed: $(first(sprint(showerror, err), 160))"
        end
    end
    # Definitions that needed a constant or a value restored just now.
    failed = isempty(failed) ? failed : with_logger(DocReplacementFilter(current_logger())) do
        replay(first.(failed))
    end
    for (item, err) in failed
        for n in item[3]["names"]
            errors[n] = "rebuilding it failed: $err"
        end
        # A method of a function that is not the session's own (`Base.show(…) = …`)
        # has no binding to report it under.
        any(n -> haskey(bindings, n), item[3]["names"]) ||
            push!(lost, "the definition from call $(item[3]["call"]) `$(one_line(item[2]))`: rebuilding it failed: $err")
    end

    # Workspace packages (`using` makes no binding for them): loaded again from
    # the workspace, and said to differ when their sources changed.
    for (name, saved) in sort!(collect(get(m, "workspace_packages", Dict())); by=first)
        loaded = [mm for (k, mm) in Base.loaded_modules if k.name == name && pathof(mm) !== nothing &&
                  startswith(pathof(mm), WORKSPACE_ROOT[] * "/")]
        if isempty(loaded)
            push!(lost, "$name (workspace package): it did not load again")
        elseif Dict(k => Tuple(v) for (k, v) in saved) != source_snapshot(dirname(pathof(loaded[1])))
            push!(approx, "$name (workspace package): loaded again from sources that changed since")
        else
            push!(rebuilt, "$name (workspace package)")
        end
    end
    # Check each binding against what the old kernel had: definitions first,
    # because data that refers to a definition is only as exact as it is.
    inexact = Set{String}()
    ordered = sort!(collect(bindings); by=nb -> (nb[2]["class"] in ("definition", "import") ? 0 : 1, nb[1]))
    for (n, b) in ordered
        cls = b["class"]
        if cls == "definition"
            now = b["check"] isa String && startswith(b["check"], "value:") ?
                  (isdefined(mod, Symbol(n)) ? "value:" * repr(getglobal(mod, Symbol(n))) : nothing) :
                  startswith(b["type"], "function") ? method_set(mod, n) : type_fingerprint(mod, n)
            if haskey(errors, n) || now === nothing
                push!(inexact, n)
                push!(lost, "$(fmt_binding(b)): $(get(errors, n, "its definition was not found in any call's top-level code"))")
            elseif now != b["check"]
                push!(inexact, n)
                push!(approx, "$(fmt_binding(b)): rebuilt, but its methods or fields differ from before")
            elseif any(e -> e["kind"] == "include" && n in e["names"] && e["path"] in changed_files, m["definitions"])
                push!(inexact, n)
                push!(approx, "$(fmt_binding(b)): rebuilt from a file that changed since")
            else
                push!(rebuilt, fmt_binding(b))
            end
        elseif cls == "import"
            changed = get(get(m, "workspace_packages", Dict()), n, nothing)
            if !isdefined(mod, Symbol(n))
                push!(lost, "$n (module): its `using`/`import` was not found")
            elseif changed !== nothing && Dict(k => Tuple(v) for (k, v) in changed) != source_snapshot(dirname(something(pathof(getglobal(mod, Symbol(n))), "/x/x")))
                push!(approx, "$n (module): loaded again from workspace sources that changed since")
            else
                push!(rebuilt, "$n (module)")
            end
        elseif cls == "data" && haskey(values, n)
            changed = [relpath(p, WORKSPACE_ROOT[]) for (p, s) in b["files"] if !isfile(p) || file_stamp(p) != Tuple(s)]
            refers = sort!(intersect(Set(String.(get(b, "user_types", String[]))), inexact) |> collect)
            if !isempty(refers)
                push!(approx, "$(fmt_binding(b)): restored, but it refers to $(join(refers, ", ")), which is not the same as before")
            elseif isempty(changed)
                push!(exact, fmt_binding(b))
            else
                push!(stale, "$(fmt_binding(b)): $(join(changed, ", ")) changed since")
            end
        else
            r = get(b, "recipe", "")
            push!(lost, "$(fmt_binding(b)): $(get(b, "reason", "not revived"))" * (isempty(r) ? "" : "; it came from `$r`"))
        end
    end

    # This kernel continues the old one's call numbers and file tracking.
    hist = state.execution_history
    while length(hist) < call
        push!(hist, ExecutionRecord(uuid4(), Dates.now(), "", true, nothing, 0.0))
    end
    empty!(DEFINITION_LOG)
    append!(DEFINITION_LOG, m["definitions"])
    for (p, s, c) in m["used_files"]
        USED_FILES[p] = (Tuple(s), c)
    end
    for (n, b) in bindings
        (haskey(values, n) || b["class"] == "definition") && (BINDING_SEEN[Symbol(n)] = (objectid(Base.invokelatest(getglobal, mod, Symbol(n))), b["call"]))
    end

    push!(lines, "[revival] The previous kernel stopped. This kernel revived the state saved at the end of call $call" *
                 (data_block === nothing ? "." : "; its data could not be restored because $data_block."))
    last = tryparse(Int, strip(read_or_empty(joinpath(dir, "last_call"))))
    last !== nothing && last > call &&
        push!(lines, "  Call$(last == call + 1 ? " $last" : "s $(call + 1)–$last") completed after this state was saved: " *
                     "what $(last == call + 1 ? "it" : "they") changed in the kernel is lost; files written to the workspace remain.")
    procs = String.(get(m, "processes", String[]))
    isempty(procs) || push!(lines, "  Background processes stopped with the previous kernel: " *
                                   join(("`$(first(c, 100))`" for c in procs), ", ") * ". Start them again if you need them.")
    # What needs attention first: a long report is cut in the middle for the
    # model (in the 12h run it reached 23 KB), so the lists that only confirm
    # come last and are shortened.
    isempty(lost) || push!(lines, "  not revived: " * join(lost, "; "))
    isempty(approx) || push!(lines, "  not the same as before: " * join(approx, "; "))
    isempty(stale) || push!(lines, "  restored but stale (a file it was computed from changed): " * join(stale, "; "))
    isempty(rebuilt) || push!(lines, short_list("rebuilt from source", rebuilt))
    isempty(exact) || push!(lines, short_list("restored exactly", exact))
    isempty(bindings) && push!(lines, "  (the previous kernel had no bindings)")
    push!(lines, "  Packages were loaded again, and LOAD_PATH, the active project, ENV and the working directory were restored. " *
                 "Other runtime state starts fresh: random number streams, settings changed inside packages, open handles. " *
                 "Files in the workspace are unchanged.")
    return join(lines, "\n")
end

