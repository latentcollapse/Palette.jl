# A compact map of the task workspace: what it is made of, how it builds and
# tests, and what changed. A model rebuilds this picture from scratch after
# every compaction; the map opens the session's first result and the first
# result after each compaction, so it does not have to.

const MAP_SKIP_DIRS = Set([".git", "node_modules", "target", "_build", "_opam", "dist", "build", ".venv", "venv",
                           "__pycache__", ".pixi", ".mypy_cache", ".pytest_cache", ".next", "vendor", ".cache"])
const MAP_MAX_FILES = 50_000
const MAP_MAX_CHARS = 2000
const LANGUAGE_OF = Dict(
    "rs" => "Rust", "ts" => "TypeScript", "tsx" => "TypeScript", "mts" => "TypeScript", "js" => "JavaScript",
    "mjs" => "JavaScript", "cjs" => "JavaScript", "jsx" => "JavaScript", "ml" => "OCaml", "mli" => "OCaml",
    "py" => "Python", "go" => "Go", "jl" => "Julia", "sql" => "SQL", "sh" => "shell", "bash" => "shell",
    "c" => "C", "h" => "C", "cpp" => "C++", "hpp" => "C++", "java" => "Java", "rb" => "Ruby", "toml" => "TOML",
    "json" => "JSON", "yaml" => "YAML", "yml" => "YAML", "md" => "Markdown", "proto" => "protobuf")

function workspace_files(root::AbstractString)
    if isdir(joinpath(root, ".git"))
        out = try
            readchomp(pipeline(`git -C $root ls-files --cached --others --exclude-standard`; stderr=devnull))
        catch
            nothing
        end
        # git lists untracked files too, so vendored and build trees are left out here as below.
        keep(f) = !isempty(f) && !any(c -> c in MAP_SKIP_DIRS, split(dirname(f), '/'))
        out === nothing || return filter(keep, split(out, '\n'))[1:min(end, MAP_MAX_FILES)]
    end
    files = String[]
    for (dir, dirs, fs) in walkdir(root; topdown=true)
        filter!(d -> !(d in MAP_SKIP_DIRS) && !startswith(d, "."), dirs)
        for f in fs
            push!(files, relpath(joinpath(dir, f), root))
            length(files) >= MAP_MAX_FILES && return files
        end
    end
    return files
end

function language(path)
    ext = last(splitext(path))
    return isempty(ext) ? nothing : get(LANGUAGE_OF, lowercase(ext[2:end]), nothing)
end

# How the workspace builds and tests, read from its manifests.
function build_entries(root::AbstractString, files)
    has(f) = f in files
    out = String[]
    for f in filter(p -> basename(p) == "Cargo.toml", files)
        push!(out, "cargo: $f" * (occursin("[workspace]", read(joinpath(root, f), String)) ? " (workspace)" : ""))
    end
    for f in filter(p -> basename(p) == "package.json", files)
        scripts = try
            s = get(JSON.parsefile(joinpath(root, f)), "scripts", Dict())
            isempty(s) ? "" : " scripts: " * join(first(collect(keys(s)), 8), ", ")
        catch
            ""
        end
        push!(out, "npm: $f$scripts")
    end
    for f in filter(p -> basename(p) in ("dune-project", "go.mod", "pyproject.toml", "setup.py", "Project.toml", "CMakeLists.txt"), files)
        push!(out, "$(basename(f)): $f")
    end
    for f in filter(p -> basename(p) in ("Makefile", "justfile", "Justfile"), files)
        targets = try
            unique([m[1] for m in eachmatch(r"(?m)^([A-Za-z][\w-]*):(?!=)", read(joinpath(root, f), String))])
        catch
            String[]
        end
        push!(out, "$(basename(f)): $f" * (isempty(targets) ? "" : " targets: " * join(first(targets, 10), ", ")))
    end
    return first(out, 12)
end

"""
    workspace_map(root = pwd()) -> String

A compact description of the workspace: languages and where each lives, build
and test entry points, git state, and the most recently changed files.
"""
function workspace_map(root::AbstractString=pwd())
    files = workspace_files(root)
    isempty(files) && return "[workspace map] the workspace is empty."
    langs = Dict{String, Int}(); tops = Dict{String, Dict{String, Int}}()
    for f in files
        l = language(f); l === nothing && continue
        langs[l] = get(langs, l, 0) + 1
        top = occursin('/', f) ? first(split(f, '/')) * "/" : "."
        d = get!(tops, top, Dict{String, Int}()); d[l] = get(d, l, 0) + 1
    end
    lines = ["[workspace map] $(length(files)) files" * (length(files) >= MAP_MAX_FILES ? "+" : "") * " in $(root)"]
    isempty(langs) || push!(lines, "  languages: " * join(("$l $n" for (l, n) in sort!(collect(langs); by=x -> -x[2])), ", "))
    if !isempty(tops)
        dirs = sort!(collect(tops); by=x -> -sum(values(x[2])))
        push!(lines, "  top-level: " * join(("$d " * join(("$l $n" for (l, n) in sort!(collect(c); by=x -> -x[2])[1:min(end, 2)]), "/")
                                           for (d, c) in dirs[1:min(end, 12)]), "; "))
    end
    entries = build_entries(root, Set(files))
    isempty(entries) || push!(lines, "  build/test: " * join(entries, "; "))
    if isdir(joinpath(root, ".git"))
        branch = try readchomp(pipeline(`git -C $root rev-parse --abbrev-ref HEAD`; stderr=devnull)) catch; "" end
        status = try readchomp(pipeline(`git -C $root status --porcelain`; stderr=devnull)) catch; "" end
        changed = filter(!isempty, split(status, '\n'))
        push!(lines, "  git: branch $branch, $(length(changed)) changed" *
                     (isempty(changed) ? "" : ": " * join((strip(c[4:end]) for c in first(changed, 8)), ", ")))
    end
    recent = sort!([(mtime(joinpath(root, f)), f) for f in files if isfile(joinpath(root, f))]; rev=true)
    isempty(recent) || push!(lines, "  recently modified: " * join((f for (_, f) in first(recent, 8)), ", "))
    text = join(lines, "\n")
    return length(text) > MAP_MAX_CHARS ? first(text, MAP_MAX_CHARS) * " …" : text
end
