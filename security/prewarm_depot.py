#!/usr/bin/env python3
"""
Precompile every Julia stdlib into the real depot, compatible with Neura.

A worker loads Neura before any turn runs, and Neura's cache pins the
stdlib caches it was built against (Logging, Dates, ...) from the depot
itself rather than the ones Julia ships. Every shipped stdlib cache that
depends on a different copy is then rejected, so the first `using Test` in
a session took ~30s and `using Pkg` ~70-80s -- redone in every session,
since each worker writes to a throwaway depot clone. Loading everything once
here, in the worker's own order and environment, leaves caches in the real
depot that every later clone inherits.

Run once per depot, and again after Neura or the project changes:
    python3 security/prewarm_depot.py --project-dir <project>
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch_worker import default_depot, resolve_real_julia_binary  # noqa: E402

PREWARM = r"""
using Neura
failed = String[]
for name in sort(readdir(Sys.STDLIB))
    isfile(joinpath(Sys.STDLIB, name, "Project.toml")) || continue
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
    # The same environment build_bwrap_argv gives a worker, minus the sandbox.
    env = {
        "HOME": os.environ.get("HOME", "/tmp"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "en_US.UTF-8",
        "JULIA_DEPOT_PATH": default_depot(),
        "JULIA_PROJECT": str(Path(args.project_dir).resolve()),
        "NEURAJL_REPO_DIR": str(Path(args.repo_dir).resolve()),
    }
    result = subprocess.run(
        [resolve_real_julia_binary(), "--startup-file=no", "-e", PREWARM],
        env=env, stdin=subprocess.DEVNULL,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
