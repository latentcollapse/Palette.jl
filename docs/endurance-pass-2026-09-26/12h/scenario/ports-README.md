# ports/

Julia ports of Python standard-library modules, one file per module: `ports/<name>.jl`, defining `module Py<Name> ... end` at top level. Each file is loaded on its own with `include` into a fresh module, so it must not depend on the package in `src/`, on other port files, or on the working directory.

Arguments arrive as parsed JSON values: `Vector{Any}` for lists, an insertion-ordered `AbstractDict{String,Any}` for objects, `String`, `Int64`, `Float64`, `Bool`, and `nothing` for None. Signatures must accept those (use `AbstractVector`, `AbstractDict`, `AbstractString`, `Integer`, `Real`, or leave arguments unannotated).

Return plain values: vectors or tuples for lists, an `AbstractDict` for dicts, strings, numbers, `Bool`, `nothing`. Where Python raises an exception, throw one (any type).

Behaviour must match CPython 3.14 exactly, edge cases included. `python3` (3.14) is on PATH for checking. Julia standard libraries and the packages in the kernel environment may be used unless a task says otherwise.
