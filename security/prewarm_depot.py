#!/usr/bin/env python3
"""
Precompile every Julia stdlib and project dependency into the real depot,
compatible with Neura.

A worker loads Neura before any turn runs, and Neura's cache pins the
stdlib caches it was built against (Logging, Dates, ...) from the depot
itself rather than the ones Julia ships. Every shipped stdlib cache that
depends on a different copy is then rejected, and so is a project package
built outside this environment, so the first `using Test` in
a session took ~30s and `using Pkg` ~70-80s -- redone in every session,
since each worker writes to a throwaway depot clone. Loading everything once
here, in the worker's own sandbox with the real depot writable, leaves caches
in the real depot that every later clone inherits. It has to be the sandbox:
a cache records the absolute source paths it was built from, and a prewarm
that could see paths the worker cannot built caches every worker rejected.

Run it where sessions will run, with the same mounts; a harness that places
the Julia runtime or this repo at other paths must run it there.

Run once per depot, and again after Neura or the project changes:
    python3 security/prewarm_depot.py --project-dir <project>
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch_worker import build_bwrap_argv, default_depot, resolve_real_julia_binary  # noqa: E402

PREWARM = r"""
using Neura
failed = String[]
stdlibs = filter(n -> isfile(joinpath(Sys.STDLIB, n, "Project.toml")), readdir(Sys.STDLIB))
project_deps = collect(keys(get(Base.parsed_toml(Base.active_project()), "deps", Dict())))
for name in sort(unique([stdlibs; project_deps]))
    try
        Core.eval(Main, :(import $(Symbol(name))))
    catch e
        push!(failed, name * ": " * first(sprint(showerror, e), 200))
    end
end
println("prewarmed ", length(Base.loaded_modules), " modules")
foreach(f -> println("could not load ", f), failed)
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--repo-dir", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args()
    julia_bin = resolve_real_julia_binary()
    with tempfile.TemporaryDirectory(prefix="neurajl-prewarm-") as workspace:
        # No depot clone: the real depot is bound writable at its own path.
        argv = build_bwrap_argv(
            workspace_dir=workspace,
            broker_socket_dir=None,
            project_dir=str(Path(args.project_dir).resolve()),
            repo_dir=str(Path(args.repo_dir).resolve()),
            julia_bin=julia_bin,
            julia_depot=default_depot(),
            network_enabled=False,
        )
        argv += ["--", julia_bin, "--startup-file=no", "-e", PREWARM]
        return subprocess.run(argv, stdin=subprocess.DEVNULL).returncode


if __name__ == "__main__":
    sys.exit(main())
