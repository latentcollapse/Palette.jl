#!/usr/bin/env python3
"""
NeuraJL session bridge -- a thin, persistent stdio wrapper around
`NeuraSession`, for a host process in a DIFFERENT language (Node, via
Prime-Agent's `baseToolsFactory`) to spawn ONCE per agent session and drive
for that session's whole lifetime, instead of shelling out fresh per call.

This is the missing piece between what NeuraJL already proves
(security/session.py's NeuraSession: real state persistence, real epoch
handshake, real authority fence, all adversarially tested) and an actual
chassis integration: Prime-Agent's tool boundary is TypeScript calling a
subprocess, not a Python API. NeuraSession itself does not change here --
this only exposes it over one more stdio hop, mirroring (structurally, not
literally) the same "newline-delimited JSON, one line per turn" shape
scripts/session_loop.jl already uses one layer down, for the same reason:
simple to spawn, simple to pipe, no new transport to build.

Protocol (all newline-delimited JSON):

  Request:   {"request_id": "...", "code": "...", "ephemeral": bool?, "ceiling": {...}?, "payload": str?}
  Response:  {"request_id": "...", "success": bool, "data": ..., "display": str?, "output": str?,
              "error": ..., "epoch": "...", "interrupted": bool, "call": int?, "session_dead": true?}
             `call` numbers a persistent turn; Neura.output(call) returns everything it printed.
  HELLO:     {"kind": "HELLO", "epoch": "...", "session_id": "..."}  -- printed once, at startup

`ephemeral`/`ceiling` map directly onto `NeuraSession.turn()`'s own
`ephemeral`/`ephemeral_ceiling` parameters -- see security/session.py for
what they mean and why the default ceiling is `{}` (full language power,
zero broker-mediated authority) rather than inherited automatically.

A malformed request line is answered with an error response (not a crash);
this process exits only when stdin closes (the host process closing its
end, e.g. on agent session dispose) or the underlying NeuraSession dies
(SessionDeadError from a turn is reported as an error response, not
silently swallowed -- the caller decides whether that's fatal to ITS
session too).
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session import NeuraSession, SessionDeadError  # noqa: E402


def _respond(resp: dict) -> None:
    print(json.dumps(resp), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--repo-dir")
    ap.add_argument("--ceiling", default="{}", help="JSON object, or a path to a JSON file")
    ap.add_argument("--network", action="store_true")
    ap.add_argument("--turn-timeout", type=float, default=60.0)
    ap.add_argument("--startup-timeout", type=float, default=180.0)
    ap.add_argument("--workspace-dir", help="Task directory the worker works in; bound writable, never deleted")
    args = ap.parse_args()

    # Default SIGTERM handling exits without running `finally`, which leaked
    # the session's depot clone every time a host killed this bridge.
    def _terminate(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGHUP, _terminate)

    ceiling_arg = args.ceiling
    if Path(ceiling_arg).is_file():
        ceiling = json.loads(Path(ceiling_arg).read_text())
    else:
        ceiling = json.loads(ceiling_arg)

    kwargs = {"project_dir": args.project_dir, "ceiling": ceiling,
              "network_enabled": args.network, "turn_timeout": args.turn_timeout,
              "startup_timeout": args.startup_timeout, "task_workspace_dir": args.workspace_dir}
    if args.repo_dir:
        kwargs["repo_dir"] = args.repo_dir

    try:
        session = NeuraSession(**kwargs)
    except Exception as e:
        _respond({"kind": "ERROR", "error": f"failed to start NeuraSession: {e}"})
        return 1

    _respond({"kind": "HELLO", "epoch": session.epoch, "session_id": session.session_id})

    try:
        while True:
            # NOT `for line in sys.stdin:` -- confirmed by direct testing
            # that iterating sys.stdin block-buffers on a pipe instead of
            # yielding line by line, which is invisible for a "pipe
            # everything then close" test but breaks a live interactive
            # request/response protocol (a second write-then-read from the
            # host process hung waiting for a line that had already
            # arrived, sitting in the iterator's internal buffer instead
            # of being handed back). readline() reads exactly one line and
            # has no such buffering surprise.
            line = sys.stdin.readline()
            if not line:
                break  # real EOF: the host process closed its end
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as e:
                _respond({"request_id": None, "success": False, "data": None, "error": f"malformed request: {e}"})
                continue

            request_id = req.get("request_id")
            code = req.get("code")
            if not isinstance(code, str):
                _respond({"request_id": request_id, "success": False, "data": None,
                           "error": "request 'code' must be a string"})
                continue

            try:
                result = session.turn(
                    code,
                    ephemeral=bool(req.get("ephemeral", False)),
                    ephemeral_ceiling=req.get("ceiling"),
                    payload=req.get("payload") if isinstance(req.get("payload"), str) else None,
                )
                _respond({
                    "request_id": request_id,
                    "success": result.get("success", False),
                    "data": result.get("data"),
                    "display": result.get("display"),
                    "output": result.get("output"),
                    "error": result.get("error"),
                    "epoch": result.get("epoch"),
                    "interrupted": bool(result.get("interrupted", False)),
                    "call": result.get("call"),
                })
            except SessionDeadError as e:
                # `session_dead` lets the host stop sending turns now, rather
                # than racing this process's exit.
                _respond({"request_id": request_id, "success": False, "data": None, "error": str(e),
                          "session_dead": True})
                # The underlying worker is gone; every subsequent turn would
                # fail the same way. Nothing left to serve.
                break
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
