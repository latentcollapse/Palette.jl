#!/usr/bin/env julia
"""
This file previously claimed to be an "IJulia Integration Test Harness"
that "launches an IJulia kernel, connects via the Jupyter protocol." It did
not do that: it never called `using IJulia`, `using ZMQ`, or spawned any
kernel process at all -- it called `OperatorSurface.execute(...)` directly,
in-process, in the same Julia session, then printed "VERIFIED" for things
it never actually verified. It also would have errored immediately on its
own `SafetyGuard(allowed_types=..., timeout_ms=...)` call, since that is
not `SafetyGuard`'s real (positional-argument) constructor signature --
this file had never been run.

The real things that file was gesturing at now live in two places:

  - `OperatorSurface.jl/test/runtests.jl`, testset "Phase 1: real
    cross-request state persistence" -- exercises real `Core.eval`-based
    execution, real function-definition persistence, real mutable-object
    persistence, and real exception containment, all verified by
    `Pkg.test()`, in-process (fast, no kernel process, appropriate for CI).

  - `scripts/real_ijulia_proof.py` -- the actual Jupyter-wire-protocol
    proof: spawns a real IJulia kernel via `jupyter_client.KernelManager`,
    sends real `execute_request` ZMQ messages, and confirms `x = 41` then
    `x + 1` returns `42` over the real wire protocol -- not an in-process
    call. This is the one that answers the README's literal Phase 1
    question. See that file's own docstring for setup (a Python venv with
    `jupyter_client`, plus an IJulia kernelspec pointing at a Julia
    environment that has this package and `IJulia` installed).

This file is kept only as a pointer so a future reader who remembers the
old (fake) name doesn't go looking for a script that no longer claims what
it never did.
"""

println("See OperatorSurface.jl/test/runtests.jl and scripts/real_ijulia_proof.py")
println("This file intentionally does nothing else -- read its docstring.")
