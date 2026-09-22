#!/usr/bin/env python3
"""
NeuraJL host capability broker -- the second trust domain.

Runs entirely OUTSIDE the sandboxed Julia worker's OS namespace. The worker
can reach it only through one narrow channel: a Unix domain socket whose
*listening* end lives here, on the host, and whose path is bind-mounted into
the sandbox (see launch_worker.py). The worker cannot reach the broker any
other way -- no network namespace access, no shared filesystem beyond the
one socket path.

Protocol: one JSON request per connection, one JSON response, connection
closed. Request:
    {"id": "<uuid>", "category": "<capability category>", "params": {...}}
Response:
    {"id": "<uuid>", "approved": true/false, "result": ..., "reason": "..."}

Authorize before effect, execute, receipt after -- in that literal order:
1. Validate the request's category+params against this session's capability
   ceiling (fixed at broker start, never mutated by a request).
2. If approved, the BROKER performs the effect itself, on the host, with
   host privilege. The worker never performs a broker-mediated effect
   itself -- it has no code path to. That is what makes "the worker cannot
   grant itself capabilities" literally true, not a policy the worker is
   trusted to follow.
3. Append an audit receipt (JSONL) regardless of outcome -- receipts are
   evidence of what was requested and decided, not permission; the
   authorization already happened in step 1.

Only two capability categories are fully implemented and enforced here:
external_fs_write and network_access. See docs/CAPABILITY_MODEL.md for the
full category list and which remain NOT YET PROVEN.
"""
from __future__ import annotations

import json
import os
import socket
import socketserver
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class CapabilityDenied(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def ceiling_is_subset(requested: dict, parent: dict) -> tuple[bool, str]:
    """C_child ⊆ C_caller. Fails closed: an unrecognized category, or a
    category present in the request but absent from the parent, is denied
    -- never silently ignored or silently granted."""
    for category, req_cap in requested.items():
        parent_cap = parent.get(category)
        if not parent_cap:
            return False, f"category {category!r} is not present in the parent's ceiling at all"
        if category == "external_fs_write":
            req_dirs = [Path(d).resolve() for d in req_cap.get("allowed_dirs", [])]
            parent_dirs = [Path(d).resolve() for d in parent_cap.get("allowed_dirs", [])]
            for rd in req_dirs:
                if not any(rd == pd or pd in rd.parents for pd in parent_dirs):
                    return False, f"requested external_fs_write dir {rd} is not within any parent allowed_dir {parent_dirs}"
        elif category == "network_access":
            if req_cap.get("allowed") and not parent_cap.get("allowed"):
                return False, "requested network_access=true but parent's ceiling has network_access=false"
            req_hosts = req_cap.get("allowed_hosts")
            parent_hosts = parent_cap.get("allowed_hosts")
            if req_hosts is not None and parent_hosts is not None and not set(req_hosts).issubset(set(parent_hosts)):
                return False, f"requested allowed_hosts {req_hosts} is not a subset of parent's {parent_hosts}"
        else:
            return False, f"unrecognized category {category!r} cannot be validated as a subset -- denied, not ignored"
    return True, ""


class Broker:
    def __init__(self, ceiling: dict[str, Any], receipt_log_path: str, session_id: str):
        self.ceiling = ceiling
        self.receipt_log_path = receipt_log_path
        self.session_id = session_id
        self._log_lock = threading.Lock()
        Path(receipt_log_path).parent.mkdir(parents=True, exist_ok=True)

    # ---- capability handlers -------------------------------------------------

    def _handle_external_fs_write(self, params: dict) -> Any:
        cap = self.ceiling.get("external_fs_write")
        if not cap or not cap.get("allowed_dirs"):
            raise CapabilityDenied("external_fs_write is not in this session's capability ceiling")
        path = params.get("path")
        content = params.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise CapabilityDenied("external_fs_write requires string 'path' and 'content'")
        target = Path(path).resolve()
        allowed = [Path(d).resolve() for d in cap["allowed_dirs"]]
        if not any(target == a or a in target.parents for a in allowed):
            raise CapabilityDenied(f"path {target} is outside the ceiling's allowed_dirs {allowed}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {"path": str(target), "bytes_written": len(content.encode())}

    def _handle_network_access(self, params: dict) -> Any:
        cap = self.ceiling.get("network_access")
        if not cap or not cap.get("allowed"):
            raise CapabilityDenied("network_access is not in this session's capability ceiling")
        url = params.get("url")
        if not isinstance(url, str):
            raise CapabilityDenied("network_access requires a string 'url'")
        allowed_hosts = cap.get("allowed_hosts")
        if allowed_hosts is not None:
            from urllib.parse import urlparse

            host = urlparse(url).hostname
            if host not in allowed_hosts:
                raise CapabilityDenied(f"host {host} is not in this session's allowed_hosts {allowed_hosts}")
        # The broker performs the request itself, on the host, with the
        # host's real network namespace -- the worker never does.
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read(2048)
        return {"url": url, "status": resp.status, "body_prefix": body[:200].decode(errors="replace")}

    def _handle_spawn_child_worker(self, params: dict) -> Any:
        """C_child ⊆ C_caller, enforced here, not by trusting the worker's
        own request. The worker cannot do this itself -- it has no
        namespace-creation privilege (see the adversarial self-spawn test in
        docs/EXPERIMENT_002_AUTHORITY.md); only the broker, unsandboxed on
        the host, can actually launch the child."""
        requested_ceiling = params.get("ceiling", {})
        if not isinstance(requested_ceiling, dict):
            raise CapabilityDenied("spawn_child_worker requires a 'ceiling' object")
        ok, reason = ceiling_is_subset(requested_ceiling, self.ceiling)
        if not ok:
            raise CapabilityDenied(f"requested child ceiling is not a subset of this session's ceiling: {reason}")
        script = params.get("script")
        child_workspace = params.get("child_workspace")
        child_project = params.get("child_project")
        child_repo = params.get("child_repo")
        if not all(isinstance(x, str) for x in (script, child_workspace, child_project, child_repo)):
            raise CapabilityDenied(
                "spawn_child_worker requires string 'script', 'child_workspace', 'child_project', 'child_repo'"
            )
        from launch_worker import run_worker

        network_enabled = bool(requested_ceiling.get("network_access", {}).get("allowed"))
        result = run_worker(
            workspace_dir=child_workspace,
            project_dir=child_project,
            repo_dir=child_repo,
            script=script,
            network_enabled=network_enabled,
            timeout=90,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
        }

    HANDLERS = {
        "external_fs_write": _handle_external_fs_write,
        "network_access": _handle_network_access,
        "spawn_child_worker": _handle_spawn_child_worker,
    }

    # ---- request handling ------------------------------------------------

    def handle_request(self, req: dict) -> dict:
        req_id = req.get("id", str(uuid.uuid4()))
        category = req.get("category")
        params = req.get("params", {})
        handler = self.HANDLERS.get(category)
        approved = False
        result = None
        reason = None
        try:
            if handler is None:
                raise CapabilityDenied(f"unknown capability category: {category!r}")
            result = handler(self, params)
            approved = True
        except CapabilityDenied as e:
            reason = e.reason
        self._write_receipt(req_id, category, params, approved, result, reason)
        resp = {"id": req_id, "approved": approved}
        if approved:
            resp["result"] = result
        else:
            resp["reason"] = reason
        return resp

    def _write_receipt(self, req_id, category, params, approved, result, reason):
        receipt = {
            "receipt_id": str(uuid.uuid4()),
            "request_id": req_id,
            "session_id": self.session_id,
            "timestamp": time.time(),
            "category": category,
            "params": params,
            "approved": approved,
            "result": result,
            "reason": reason,
        }
        with self._log_lock:
            with open(self.receipt_log_path, "a") as f:
                f.write(json.dumps(receipt) + "\n")


class _ConnHandler(socketserver.BaseRequestHandler):
    def handle(self):
        broker: Broker = self.server.broker  # type: ignore[attr-defined]
        f = self.request.makefile("rwb")
        try:
            line = f.readline()
            if not line:
                return
            req = json.loads(line.decode())
            resp = broker.handle_request(req)
            f.write((json.dumps(resp) + "\n").encode())
            f.flush()
        except Exception as e:  # never let a malformed request kill the broker
            try:
                f.write((json.dumps({"approved": False, "reason": f"broker error: {e}"}) + "\n").encode())
                f.flush()
            except Exception:
                pass


class _UnixSocketServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def serve(sock_path: str, ceiling: dict, receipt_log_path: str, session_id: str, stop_event: threading.Event | None = None):
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    broker = Broker(ceiling, receipt_log_path, session_id)
    server = _UnixSocketServer(sock_path, _ConnHandler)
    server.broker = broker  # type: ignore[attr-defined]
    os.chmod(sock_path, 0o666)  # the sandboxed worker connects as a different uid view
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if stop_event is None:
        return server, broker
    try:
        stop_event.wait()
    finally:
        server.shutdown()
        server.server_close()
        if os.path.exists(sock_path):
            os.unlink(sock_path)
    return server, broker


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--ceiling", required=True, help="path to a JSON ceiling file")
    ap.add_argument("--receipts", required=True)
    ap.add_argument("--session-id", default=str(uuid.uuid4()))
    args = ap.parse_args()

    with open(args.ceiling) as f:
        ceiling = json.load(f)

    stop = threading.Event()
    print(f"[broker] listening on {args.socket}, session {args.session_id}")
    serve(args.socket, ceiling, args.receipts, args.session_id, stop_event=stop)
