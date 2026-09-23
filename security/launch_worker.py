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
explicitly enabled. It is a new implementation for a different substrate
(Julia, not Bash), not a copy -- see docs/NEURABASH_SECURITY_PORT.md for
exactly what was reused vs. redesigned.

Depot handling is NOT a layered writable-over-readonly overlay (that was
tried and, on this substrate, actively caused the cold-start problem it
was meant to solve -- see _clone_depot's docstring for the root cause,
found by direct reproduction). Each worker gets its own real, cheap
(reflink) clone of the depot, bound writable as the depot's one and only
`JULIA_DEPOT_PATH` entry.

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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _clone_depot(real_depot: str, clone_root: str) -> str:
    """Make a real, independent, cheap copy of the depot for one worker's
    exclusive writable use.

    Root cause this works around (found by direct reproduction outside any
    sandbox, not assumed by analogy to NeuraBash -- see
    docs/NEURABASH_SECURITY_PORT.md's update): a split `JULIA_DEPOT_PATH`
    ("writable:readonly") makes Julia recompute a different "desired
    build_id" for stdlib packages (observed via JULIA_DEBUG=loading) the
    moment the first entry is a fresh/empty writable directory. That
    mismatch cascades and invalidates the entire precompiled dependency
    chain (JSON, Parsers, ...) on every single launch -- a ~40s tax
    regardless of how thoroughly the read-only base depot was prewarmed.
    A *single*-entry, writable depot has no such mismatch, but must be a
    real, independent copy (not the live shared depot bound writable --
    that would let one worker's script corrupt every other session's
    cache) at the SAME absolute path Julia's existing compiled caches
    already reference (package source paths are embedded as absolutes),
    which is why the guest bind target below is `real_depot`, not
    `clone_root`.

    `cp --reflink=auto` on a CoW filesystem (btrfs here) makes this
    near-free: no data is actually duplicated, and a write inside the
    sandbox diverges only the touched blocks. On a non-CoW filesystem it
    falls back to a real byte copy, still correct, just slower (fails
    closed -- correctness first, worth revisiting if that path matters
    later, but not yet proven to be slow enough here to justify a
    filesystem-specific special case).
    """
    dest = tempfile.mkdtemp(dir=clone_root, prefix="depot-")
    shutil.rmtree(dest)  # cp needs the destination to not exist yet
    subprocess.run(["cp", "-a", "--reflink=auto", real_depot, dest], check=True, stdin=subprocess.DEVNULL)
    return dest


def resolve_real_julia_binary() -> str:
    """Resolve past the juliaup shim to the real julia binary -- the shim
    itself does version-selection logic this sandbox doesn't need or want
    to grant filesystem access to resolve.

    `stdin=subprocess.DEVNULL` is not optional here: confirmed by direct
    testing that `julia -e ...` invoked WITHOUT an explicit stdin (the
    default: inherit the caller's own stdin fd) silently breaks the
    CALLER's own subsequent reads from its own stdin -- invisible for
    every one-shot caller so far (nothing before security/session_cli.py
    depended on a live stdin pipe surviving past this call), but fatal for
    a persistent process like session_cli.py, which reads turn requests
    from its own stdin for its entire lifetime. This one call, running
    inside a session's broker thread the moment any ephemeral turn
    requested spawn_child_worker, would have corrupted that whole
    session's ability to receive any further turn after the first one.
    """
    out = subprocess.run(
        ["julia", "-e", "print(Sys.BINDIR)"], capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL,
    )
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
    depot_clone_dir: str | None = None,
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
        # julia toolchain -- read-only
        "--ro-bind", julia_toolchain_dir, julia_toolchain_dir,
        # depot -- bound WRITABLE, at the depot's own real path (package
        # source paths are baked into precompiled caches as absolutes, so
        # the guest path must match, not just the content). The source is
        # this worker's own private clone (see _clone_depot), never the
        # live shared depot: a single writable entry avoids the split-
        # JULIA_DEPOT_PATH build-id cascade below, without handing the
        # worker write access to every other session's cache.
        "--bind", depot_clone_dir or julia_depot, julia_depot,
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
        "--setenv", "JULIA_DEPOT_PATH", julia_depot,
        "--setenv", "JULIA_PROJECT", project_dir,
        "--setenv", "NEURAJL_REPO_DIR", repo_dir,
        "--setenv", "PATH", f"{julia_toolchain_dir}/bin:/usr/bin:/bin",
        "--setenv", "LANG", "en_US.UTF-8",
        "--chdir", workspace_dir,
    ]
    if broker_socket_dir:
        argv += ["--setenv", "NEURAJL_BROKER_SOCKET", str(Path(broker_socket_dir) / "broker.sock")]
    return argv


def default_depot() -> str:
    return os.environ.get("JULIA_DEPOT_PATH", str(Path.home() / ".julia")).split(":")[-1]


def create_session_depot(real_depot: str | None = None, clone_root: str | None = None) -> str:
    """Create one private, writable depot clone for a whole session (not
    one launch) to share. Exists as a public entry point, not just an
    internal `run_worker` detail, because `package_management` (see
    `security/broker.py`) needs the broker to install into the EXACT same
    directory a running worker already has bound -- a bind mount is a live
    view of a directory, not a snapshot, so a host-side write into a
    worker's depot clone while it's still running appears inside the
    sandbox immediately, with no new mount and no restart. That only works
    if there is one clone per session that both the worker and the broker
    agree on, instead of `run_worker` silently making (and destroying) a
    fresh one on every call, as it does for a caller that has no reason to
    share one.
    """
    depot = real_depot or default_depot()
    root = clone_root or str(Path(depot).parent / ".neurajl-depot-clones")
    Path(root).mkdir(parents=True, exist_ok=True)
    return _clone_depot(depot, root)


def run_worker(
    *,
    workspace_dir: str,
    project_dir: str,
    repo_dir: str,
    script: str,
    broker_socket_dir: str | None = None,
    network_enabled: bool = False,
    julia_depot: str | None = None,
    depot_clone_root: str | None = None,
    depot_clone_dir: str | None = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess:
    julia_bin = resolve_real_julia_binary()
    depot = julia_depot or default_depot()
    Path(workspace_dir).mkdir(parents=True, exist_ok=True)

    # A caller that already owns a session-lifetime clone (see
    # create_session_depot) passes it in and keeps owning its cleanup --
    # e.g. so `package_management` can keep installing into it across
    # several launches. A caller with no such need gets the old
    # single-launch behavior: a fresh clone, destroyed when this call ends.
    owns_clone = depot_clone_dir is None
    if owns_clone:
        depot_clone_dir = create_session_depot(depot, depot_clone_root)
    try:
        argv = build_bwrap_argv(
            workspace_dir=workspace_dir,
            broker_socket_dir=broker_socket_dir,
            project_dir=project_dir,
            repo_dir=repo_dir,
            julia_bin=julia_bin,
            julia_depot=depot,
            depot_clone_dir=depot_clone_dir,
            network_enabled=network_enabled,
        )
        argv += ["--", julia_bin, "--startup-file=no", "-e", script]
        # stdin=DEVNULL: see resolve_real_julia_binary's docstring -- the
        # exact same class of bug (an unspecified stdin inherits the
        # caller's, and a `julia -e` invocation silently breaks that
        # caller's own future stdin reads), reachable here via
        # spawn_child_worker's broker handler running inside a persistent
        # session's own process.
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    finally:
        if owns_clone:
            shutil.rmtree(depot_clone_dir, ignore_errors=True)


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
