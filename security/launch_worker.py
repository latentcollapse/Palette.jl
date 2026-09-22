#!/usr/bin/env python3
"""
NeuraJL contained worker launcher -- the first trust domain.

Builds a bubblewrap sandbox around a real, unrestricted `julia` process:
full language semantics inside (eval, ccall, run, Base, Pkg, metaprogramming
-- nothing about the language itself is restricted), bounded by the OS
outside it (namespace isolation, not a language-level blacklist).

This reuses the same doctrine NeuraBash's security_launcher.py already
proved: bind only what's needed, read-only unless a path genuinely needs to
be writable, no ambient credentials (--clearenv), no network unless
explicitly enabled, a private writable depot layered on top of a read-only
precompiled base depot so the worker doesn't recompile packages from
scratch. It is a new implementation for a different substrate (Julia, not
Bash), not a copy -- see docs/NEURABASH_SECURITY_PORT.md for exactly what
was reused vs. redesigned.

Paths are bound at IDENTICAL guest paths to their host paths (no
remapping). Julia's own package manifests and precompile cache embed
absolute host paths; remapping them would invalidate the whole prewarmed
depot and force full recompilation inside every sandboxed launch -- the
exact cold-start tax this project has already hit once, on NeuraBash, and
is not interested in reproducing here.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _real_julia_binary() -> str:
    """Resolve past the juliaup shim to the real julia binary -- the shim
    itself does version-selection logic this sandbox doesn't need or want
    to grant filesystem access to resolve."""
    out = subprocess.run(["julia", "-e", "print(Sys.BINDIR)"], capture_output=True, text=True, check=True)
    bindir = out.stdout.strip()
    return str(Path(bindir) / "julia")


def build_bwrap_argv(
    *,
    workspace_dir: str,
    broker_socket_dir: str | None,
    project_dir: str,
    repo_dir: str,
    julia_bin: str,
    julia_depot: str,
    network_enabled: bool,
    extra_ro_binds: list[str] | None = None,
) -> list[str]:
    julia_toolchain_dir = str(Path(julia_bin).parent.parent)  # .../julia-1.12.6+0.x64.linux.gnu

    argv = [
        "bwrap",
        "--unshare-user", "--uid", "1000", "--gid", "1000",
        "--disable-userns", "--assert-userns-disabled",
        "--unshare-pid", "--as-pid-1",
        "--unshare-ipc",
    ]
    argv += ["--unshare-net"] if not network_enabled else []
    argv += [
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--dir", "/run/neurajl",
        "--tmpfs", "/run/neurajl",
        "--dir", "/run/neurajl/depot",
        "--dir", "/run/neurajl/home",
        "--clearenv",
        "--die-with-parent",
        "--new-session",
        "--cap-drop", "ALL",
        # base OS -- read-only
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib", "/lib64",
        "--symlink", "usr/bin", "/bin",
        "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
        # julia toolchain + shared depot (packages + precompiled cache) -- read-only
        "--ro-bind", julia_toolchain_dir, julia_toolchain_dir,
        "--ro-bind", julia_depot, julia_depot,
        # this repo's source (the Neura package) -- read-only, worker cannot modify it
        "--ro-bind", repo_dir, repo_dir,
        # the dev project (Project.toml/Manifest.toml naming Neura + IJulia + deps) -- read-only
        "--ro-bind", project_dir, project_dir,
        # bounded, writable workspace -- the sandbox-local effect envelope
        "--bind", workspace_dir, workspace_dir,
    ]
    for path in extra_ro_binds or []:
        argv += ["--ro-bind", path, path]
    if broker_socket_dir:
        argv += ["--ro-bind", broker_socket_dir, broker_socket_dir]
    argv += [
        "--setenv", "HOME", "/run/neurajl/home",
        "--setenv", "JULIA_DEPOT_PATH", f"/run/neurajl/depot:{julia_depot}",
        "--setenv", "JULIA_PROJECT", project_dir,
        "--setenv", "PATH", f"{julia_toolchain_dir}/bin:/usr/bin:/bin",
        "--setenv", "LANG", "en_US.UTF-8",
        "--chdir", workspace_dir,
    ]
    if broker_socket_dir:
        argv += ["--setenv", "NEURAJL_BROKER_SOCKET", str(Path(broker_socket_dir) / "broker.sock")]
    return argv


def run_worker(
    *,
    workspace_dir: str,
    project_dir: str,
    repo_dir: str,
    script: str,
    broker_socket_dir: str | None = None,
    network_enabled: bool = False,
    julia_depot: str | None = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess:
    julia_bin = _real_julia_binary()
    depot = julia_depot or os.environ.get("JULIA_DEPOT_PATH", str(Path.home() / ".julia")).split(":")[-1]
    Path(workspace_dir).mkdir(parents=True, exist_ok=True)
    argv = build_bwrap_argv(
        workspace_dir=workspace_dir,
        broker_socket_dir=broker_socket_dir,
        project_dir=project_dir,
        repo_dir=repo_dir,
        julia_bin=julia_bin,
        julia_depot=depot,
        network_enabled=network_enabled,
    )
    argv += ["--", julia_bin, "--startup-file=no", "-e", script]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--script", required=True, help="Julia code to run with -e")
    ap.add_argument("--broker-socket-dir")
    ap.add_argument("--network", action="store_true")
    args = ap.parse_args()

    result = run_worker(
        workspace_dir=args.workspace,
        project_dir=args.project,
        repo_dir=args.repo,
        script=args.script,
        broker_socket_dir=args.broker_socket_dir,
        network_enabled=args.network,
    )
    print("--- stdout ---")
    print(result.stdout)
    print("--- stderr ---")
    print(result.stderr, file=sys.stderr)
    sys.exit(result.returncode)
