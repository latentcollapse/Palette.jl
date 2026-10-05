#!/usr/bin/env python3
"""Integration proof for plugin-lab multi-workspace routing.

This is intentionally an adapter-level test: it exercises the real existing
operator_mcp child and therefore the real Rust Palette host.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
ROUTER = REPO / "runtime/security/operator_workspace_router.py"
HOST = REPO / "runtime/host/target/release/palette-host"


class WorkspaceRouterIntegration(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HOST.is_file(), "Build release palette-host before running integration tests")

        self.tmp = tempfile.TemporaryDirectory(prefix="palette-workspace-router-")
        root = Path(self.tmp.name)
        self.workspace = root / "project"
        self.workspace.mkdir()

        env = {
            **os.environ,
            "PALETTE_REPO": str(REPO),
            "PALETTE_HOST": str(HOST),
            "OPERATOR_WORKSPACE": str(self.workspace),
            "PALETTE_STATE_DIR": str(root / "legacy-state"),
            "PALETTE_WORKSPACE_STATE_ROOT": str(root / "registry"),
            "PALETTE_SCRATCH_ROOT": str(root / "scratch"),
        }
        self.env = env
        self.router_stderr = (root / "router-stderr.log").open("w+")
        self.start_router()

    def start_router(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(ROUTER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.router_stderr,
            text=True,
            env=self.env,
        )

    def tearDown(self):
        if getattr(self, "proc", None):
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            if self.proc.stdout:
                self.proc.stdout.close()
        if getattr(self, "router_stderr", None):
            self.router_stderr.close()
        if getattr(self, "tmp", None):
            self.tmp.cleanup()

    def diagnostics(self):
        self.router_stderr.flush()
        return Path(self.router_stderr.name).read_text(errors="replace")[-12000:]

    def call(self, name, arguments, *, error=False):
        request = {
            "jsonrpc": "2.0",
            "id": "test",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.proc.stdout, selectors.EVENT_READ)
            ready = selector.select(timeout=240)
            self.assertTrue(ready, "MCP reply deadline exceeded\n" + self.diagnostics())
        raw = self.proc.stdout.readline()
        self.assertTrue(raw, "Router exited without reply\n" + self.diagnostics())
        frame = json.loads(raw)
        self.assertIn("result", frame, frame)
        reply = frame["result"]
        self.assertEqual(bool(reply.get("isError")), error, f"{reply}\n{self.diagnostics()}")
        return json.loads(reply["content"][0]["text"])

    def test_startup_failure_keeps_its_cause_through_router(self):
        self.proc.stdin.close(); self.proc.wait(timeout=60); self.proc.stdout.close()
        self.env["PALETTE_HOST"] = str(Path(self.tmp.name) / "missing-host")
        self.start_router()
        result = self.call("palette", {"context_id": "failed-startup", "code": "1"}, error=True)
        self.assertIn("FileNotFoundError", result["error"])
        self.assertTrue(result["workspace_id"])

    def test_portable_and_compatibility_installation(self):
        for fmt in ("portable", "codex"):
            with self.subTest(format=fmt):
                plugin = Path(self.tmp.name) / fmt
                command = [sys.executable, str(REPO / "runtime/security/install_operator_plugin.py"), "--format", fmt,
                    "--plugin-dir", str(plugin), "--workspace-dir", str(self.workspace), "--bin-dir", str(Path(self.tmp.name) / "bin")]
                subprocess.run(command, capture_output=True, text=True, check=True)
                config_path = plugin / ("mcp.json" if fmt == "portable" else ".mcp.json")
                config = json.loads(config_path.read_text())
                config["mcpServers"]["palette"]["env"]["INSTALL_TEST_PRESERVED"] = "yes"
                config_path.write_text(json.dumps(config))
                subprocess.run(command, capture_output=True, text=True, check=True)
                entry = json.loads(config_path.read_text())["mcpServers"]["palette"]
                self.assertEqual(entry["env"]["INSTALL_TEST_PRESERVED"], "yes")
                request = {"jsonrpc":"2.0", "id":1, "method":"tools/list"}
                result = subprocess.run([entry["command"], *entry["args"]], input=json.dumps(request)+"\n",
                    capture_output=True, text=True, check=True, timeout=60, cwd=self.tmp.name, env={**self.env, **entry["env"]})
                self.assertEqual({t["name"] for t in json.loads(result.stdout)["result"]["tools"]},
                    {"palette", "palette_control", "palette_workspace", "palette_patch"})
        wrapper = Path(self.tmp.name) / "bin/palette-mcp"
        result = subprocess.run([str(wrapper)], input=json.dumps(request)+"\n", capture_output=True,
            text=True, check=True, timeout=60, cwd=self.tmp.name, env=self.env)
        self.assertEqual(len(json.loads(result.stdout)["result"]["tools"]), 4)

    def test_thread_project_open_and_revival(self):
        # Thread A and B are truly separate worlds.
        a = self.call("palette_workspace", {
            "action": "create",
            "workspace_id": "thread-a",
            "scope": "thread",
            "context_id": "ctx-a",
        })
        self.assertTrue(a["active_for_context"])
        self.call("palette", {"context_id": "ctx-a", "code": "x=1"})
        self.assertEqual(
            self.call("palette", {"context_id": "ctx-a", "code": "x"})["data"],
            1,
        )

        self.call("palette_workspace", {
            "action": "create",
            "workspace_id": "thread-b",
            "scope": "thread",
            "context_id": "ctx-b",
        })
        self.assertFalse(
            self.call(
                "palette",
                {"context_id": "ctx-b", "code": "isdefined(@__MODULE__, :x)"},
            )["data"]
        )
        self.call("palette", {"context_id": "ctx-b", "code": "x=2"})
        self.assertEqual(
            self.call("palette", {"context_id": "ctx-a", "code": "x"})["data"],
            1,
        )

        # Thread scope fails closed for the wrong context.
        denied = self.call(
            "palette",
            {
                "workspace_id": "thread-a",
                "context_id": "ctx-b",
                "code": "x",
            },
            error=True,
        )
        self.assertIn("PermissionError", denied["error"])

        # Project scope intentionally shares a world across contexts.
        self.call("palette_workspace", {
            "action": "create",
            "workspace_id": "project-shared",
            "scope": "project",
            "context_id": "ctx-a",
        })
        self.call("palette_workspace", {
            "action": "attach",
            "workspace_id": "project-shared",
            "context_id": "ctx-b",
        })
        self.call("palette", {
            "workspace_id": "project-shared",
            "context_id": "ctx-a",
            "code": "p=7",
        })
        self.assertEqual(
            self.call("palette", {
                "workspace_id": "project-shared",
                "context_id": "ctx-b",
                "code": "p",
            })["data"],
            7,
        )

        # Open scope is deliberately attachable by either context.
        self.call("palette_workspace", {
            "action": "create",
            "workspace_id": "open-lab",
            "scope": "open",
            "context_id": "ctx-a",
        })
        self.call("palette_workspace", {
            "action": "attach",
            "workspace_id": "open-lab",
            "context_id": "ctx-b",
        })
        self.call("palette", {
            "workspace_id": "open-lab",
            "context_id": "ctx-a",
            "code": "o=11",
        })
        self.assertEqual(
            self.call("palette", {
                "workspace_id": "open-lab",
                "context_id": "ctx-b",
                "code": "o",
            })["data"],
            11,
        )

        # Closing only parks the process; explicit routing must select that world.
        closed = self.call("palette_workspace", {
            "action": "close",
            "workspace_id": "thread-a",
            "context_id": "ctx-a",
        })
        self.assertTrue(closed["state_retained"])
        self.assertEqual(
            self.call("palette", {"workspace_id":"thread-a", "context_id": "ctx-a", "code": "x"})["data"],
            1,
        )


        # Routed restart must not restart another world.
        epoch_b = self.call("palette", {"workspace_id":"thread-b", "context_id":"ctx-b", "code":"x"})["epoch"]
        self.call("palette_control", {"action":"restart", "workspace_id":"thread-a", "context_id":"ctx-a"})
        self.assertEqual(self.call("palette", {"workspace_id":"thread-a", "context_id":"ctx-a", "code":"x"})["data"], 1)
        self.assertEqual(self.call("palette", {"workspace_id":"thread-b", "context_id":"ctx-b", "code":"x"})["epoch"], epoch_b)
        scratch_a = self.call("palette", {"workspace_id":"thread-a", "context_id":"ctx-a", "code":"pwd()", "ephemeral":True})["data"]
        scratch_b = self.call("palette", {"workspace_id":"thread-b", "context_id":"ctx-b", "code":"pwd()", "ephemeral":True})["data"]
        self.assertNotEqual(scratch_a, scratch_b)
        self.call("palette_workspace", {"action":"close", "workspace_id":"thread-b", "context_id":"ctx-b"})
        legacy = self.call("palette", {"code":"legacy_value=31"})
        self.assertTrue(legacy["legacy_shared"])
        self.assertEqual(legacy["workspace_id"], "default")
        self.assertEqual(self.call("palette_control", {"action":"status"})["state_dir"], self.env["PALETTE_STATE_DIR"])
        self.call("palette_workspace", {"action":"attach", "workspace_id":"thread-a", "context_id":"ctx-a"})
        self.proc.stdin.close()
        self.assertEqual(self.proc.wait(timeout=60), 0)
        self.proc.stdout.close()
        self.start_router()
        self.assertEqual(self.call("palette", {"context_id":"ctx-a", "code":"x"})["data"], 1)
        self.assertEqual(self.call("palette", {"code":"legacy_value"})["data"], 31)

    def test_two_routers_cannot_own_one_world(self):
        self.call("palette_workspace", {"action":"create", "workspace_id":"shared", "scope":"project", "context_id":"a"})
        self.call("palette", {"context_id":"a", "code":"shared_value=77"})
        first = self.proc
        self.start_router()
        second = self.proc
        try:
            denied = self.call("palette", {"workspace_id":"shared", "context_id":"b", "code":"shared_value"}, error=True)
            self.assertIn("already owned", denied["error"])
            self.proc = first
            self.call("palette_workspace", {"action":"close", "workspace_id":"shared", "context_id":"a"})
            self.proc = second
            self.assertEqual(self.call("palette", {"workspace_id":"shared", "context_id":"b", "code":"shared_value"})["data"], 77)
            # A different canonical project must fail the project scope check.
            self.call("palette_workspace", {"action":"close", "workspace_id":"shared", "context_id":"b"})
            second.stdin.close()
            second.wait(timeout=60)
            second.stdout.close()
            other = Path(self.tmp.name) / "other-project"
            other.mkdir()
            self.env = {**self.env, "OPERATOR_WORKSPACE":str(other)}
            self.start_router()
            denied = self.call("palette_workspace", {"action":"attach", "workspace_id":"shared", "context_id":"a"}, error=True)
            self.assertIn("PermissionError", denied["error"])
        finally:
            first.stdin.close()
            first.wait(timeout=60)
            first.stdout.close()
            if second.poll() is None:
                second.stdin.close()
                second.wait(timeout=60)
                second.stdout.close()

    def test_patch_approval_uses_mcp_client_response(self):
        # Real server/client elicitation, not a model-supplied approve argument.
        target = Path(self.tmp.name) / "target"
        target.mkdir()
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        self.proc.stdout.close()
        self.env["PALETTE_PATCH_ROOTS"] = json.dumps({"test":str(target)})
        self.start_router()
        def exchange(value):
            self.proc.stdin.write(json.dumps(value)+"\n")
            self.proc.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(self.proc.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=30))
            return json.loads(self.proc.stdout.readline())
        response = exchange({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"capabilities":{"elicitation":{"form":{}}}}})
        self.assertIn("result",response)
        prepared = self.call("palette_patch", {"action":"prepare", "target":"test", "changes":[{"path":"new.txt", "before_sha256":None, "content":"approved content\n"}]})
        prompt = exchange({"jsonrpc":"2.0", "id":2, "method":"tools/call", "params":{"name":"palette_patch", "arguments":{"action":"apply", "request_id":prepared["request_id"]}}})
        self.assertEqual(prompt["method"], "elicitation/create")
        result = exchange({"jsonrpc":"2.0", "id":prompt["id"], "result":{"action":"accept", "content":{"confirm":True}}})
        receipt = json.loads(result["result"]["content"][0]["text"])
        self.assertEqual(receipt["status"],"applied",receipt)
        self.assertEqual(receipt["granted_by"],"mcp_client_confirmed_user")
        self.assertEqual((target/"new.txt").read_text(),"approved content\n")


    def test_live_limit_and_router_crash_recovery(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        self.proc.stdout.close()
        self.env["PALETTE_MAX_LIVE_WORKSPACES"] = "1"
        self.start_router()
        a = self.call("palette_workspace", {"action":"create", "workspace_id":"crash-a", "context_id":"a"})
        self.call("palette", {"context_id":"a", "code":"crash_value=89"})
        self.call("palette_workspace", {"action":"create", "workspace_id":"limit-b", "context_id":"b"})
        denied = self.call("palette", {"context_id":"b", "code":"1"}, error=True)
        self.assertIn("Live workspace limit", denied["error"])
        status = self.call("palette_workspace", {"action":"status", "workspace_id":"crash-a", "context_id":"a"})
        adapter = status["local_adapter_pid"]
        os.kill(adapter, signal.SIGSTOP)
        try:
            old = self.proc
            old.kill()
            old.wait(timeout=10)
            old.stdin.close()
            old.stdout.close()
            self.start_router()
            denied = self.call("palette", {"workspace_id":"crash-a", "context_id":"a", "code":"crash_value"}, error=True)
            self.assertIn("already owned", denied["error"])
        finally:
            os.kill(adapter, signal.SIGCONT)
        # Await the concrete kernel lock-release event, not elapsed time.
        lock = Path(a["state_dir"]).with_name("crash-a.owner.lock")
        command = "import fcntl,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_EX); print('released',flush=True)"
        waiter = subprocess.Popen([sys.executable,"-c",command,str(lock)],stdout=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(waiter.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=60),"Old adapter failed to release ownership")
            self.assertEqual(waiter.stdout.readline().strip(),"released")
            self.assertEqual(waiter.wait(timeout=10),0)
        finally:
            if waiter.poll() is None:
                waiter.kill()
                waiter.wait()
            waiter.stdout.close()
        self.assertEqual(self.call("palette", {"workspace_id":"crash-a", "context_id":"a", "code":"crash_value"})["data"],89)
        self.call("palette_workspace", {"action":"close", "workspace_id":"crash-a", "context_id":"a"})
        self.assertEqual(self.call("palette", {"context_id":"b", "code":"42"})["data"],42)


if __name__ == "__main__":
    unittest.main()
