#!/usr/bin/env python3
"""
Mid-call host requests: the kernel asks the agent host to act (an RLM child,
for instance) while a call runs, through its broker, and only for the request
types its ceiling names. These tests play the host on session_cli's stdio.

Run:
    python3 security/test_host_bridge.py
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import broker as _broker  # noqa: E402
from test_session_cli import CLI, PROJECT_DIR, _skip_if_no_bwrap, _skip_if_no_project  # noqa: E402

RLM_TYPES = ["rlm.run", "rlm.collect", "rlm.list_subagents"]
CHILD = {"rlm_child_id": "c1", "name": "w", "session_dir": "/s/c1", "model": "openai/luna"}


def _ok(result):
    return {"status": "ok", "result": result}


class Host:
    """session_cli with a given ceiling, driven the way the agent host drives it."""

    def __init__(self, ceiling: dict, turn_timeout: float = 20):
        self.workspace = tempfile.mkdtemp(prefix="neurajl-bridge-")
        self.proc = subprocess.Popen(
            [sys.executable, CLI, "--project-dir", PROJECT_DIR, "--ceiling", json.dumps(ceiling),
             "--workspace-dir", self.workspace, "--turn-timeout", str(turn_timeout)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        hello = json.loads(self.proc.stdout.readline())
        assert hello.get("kind") == "HELLO", hello
        self.n = 0

    def send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def read(self, timeout: float = 60) -> dict | None:
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            return None
        line = self.proc.stdout.readline()
        return json.loads(line) if line else None

    def call(self, code: str, answer=lambda data: None, **extra) -> tuple[dict, list]:
        """Run one call; answer each host request with `answer(data)` (None: no reply).
        Returns the call's response and the requests seen."""
        self.n += 1
        rid = f"r{self.n}"
        self.send({"request_id": rid, "code": code, **extra})
        seen = []
        while True:
            msg = self.read()
            assert msg is not None, "no response"
            if msg.get("event") == "host_request":
                seen.append(msg["data"])
                reply = answer(msg["data"])
                if reply is not None:
                    self.send({"host_reply": msg["id"], "reply": reply})
                continue
            assert msg.get("request_id") == rid, msg
            return msg, seen

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def _rlm_host(data):
    if data["type"] == "rlm.run":
        return _ok(dict(CHILD, name=data["kwargs"]["name"]))
    if data["type"] == "rlm.collect":
        return _ok({"results": [{"rlm_child_id": "c1", "status": "done", "settled": True, "answer_preview": "42"}]})
    return {"status": "error", "error": f"no handler for {data['type']}"}


class TestHostBridge(unittest.TestCase):
    def setUp(self):
        _skip_if_no_bwrap()
        _skip_if_no_project()
        self.hosts = []

    def tearDown(self):
        for h in self.hosts:
            h.close()

    def host(self, ceiling, **kw):
        h = Host(ceiling, **kw)
        self.hosts.append(h)
        return h

    def test_spawn_and_collect_in_one_call(self):
        h = self.host({"host_request": {"allowed_types": RLM_TYPES}})
        r, seen = h.call('h = Neura.rlm.spawn("add 40 and 2"; name = "w"); '
                         'r = only(Neura.rlm.collect(h; timeout_ms = 1000)); (h.rlm_child_id, r.status, r.answer_preview)',
                         _rlm_host)
        self.assertTrue(r["success"], r)
        self.assertIn('("c1", "done", "42")', r["display"])
        self.assertEqual([d["type"] for d in seen], ["rlm.run", "rlm.collect"])
        self.assertEqual(seen[0]["prompt"], "add 40 and 2")
        self.assertEqual(seen[1]["targets"], ["c1"])
        self.assertEqual(seen[1]["timeout_ms"], 1000)

    def test_spawn_now_collect_in_a_later_call_and_from_a_background_task(self):
        h = self.host({"host_request": {"allowed_types": RLM_TYPES}})
        r, _ = h.call('h = Neura.rlm.spawn("x"; name = "w"); h.name', _rlm_host)
        self.assertTrue(r["success"], r)
        r, seen = h.call('only(Neura.rlm.collect(h)).answer_preview', _rlm_host)
        self.assertIn('"42"', r["display"])
        # A background collect whose request arrives after its call returned:
        # the host answers between calls, and the next call fetches it.
        r, seen = h.call('job = @async (sleep(1.0); only(Neura.rlm.collect(h)).status); :started', _rlm_host)
        self.assertTrue(r["success"], r)
        msg = h.read(timeout=30)
        self.assertEqual(msg.get("event"), "host_request", msg)
        h.send({"host_reply": msg["id"], "reply": _rlm_host(msg["data"])})
        time.sleep(1.0)
        r, _ = h.call("fetch(job)")
        self.assertIn('"done"', r["display"])

    def test_denied_without_the_permission_and_nothing_reaches_the_host(self):
        h = self.host({})
        r, seen = h.call('Neura.rlm.spawn("x"; name = "w")', _rlm_host)
        self.assertFalse(r["success"])
        self.assertIn("host_request not in this session's ceiling", json.dumps(r))
        self.assertEqual(seen, [])

    def test_a_type_outside_allowed_types_is_denied(self):
        h = self.host({"host_request": {"allowed_types": ["rlm.collect"]}})
        r, seen = h.call('Neura.rlm.spawn("x"; name = "w")', _rlm_host)
        self.assertFalse(r["success"])
        self.assertIn("'rlm.run' is not in this session's allowed_types", json.dumps(r))
        self.assertEqual(seen, [])
        r, seen = h.call('Neura.host_request("rlm.collect", Dict("type" => "rlm.run", "targets" => []))',
                         lambda d: _ok({"results": []}))
        self.assertTrue(r["success"], r)
        self.assertEqual(seen[0]["type"], "rlm.collect", "a payload key must not reroute the request")

    def test_the_hosts_error_and_a_malformed_reply_reach_julia_truthfully(self):
        h = self.host({"host_request": {"allowed_types": RLM_TYPES}})
        r, _ = h.call('Neura.rlm.spawn("x"; name = "w")', lambda d: {"status": "error", "error": "name 'w' is taken"})
        self.assertFalse(r["success"])
        self.assertIn("name 'w' is taken", json.dumps(r))
        r, _ = h.call('Neura.rlm.spawn("x"; name = "w")', lambda d: {"surprise": True})
        self.assertFalse(r["success"])
        self.assertIn("malformed reply", json.dumps(r))

    def test_an_unanswered_request_times_out_and_a_late_reply_is_dropped(self):
        h = self.host({"host_request": {"allowed_types": RLM_TYPES}}, turn_timeout=8)
        ids = []
        r, seen = h.call('Neura.rlm.spawn("x"; name = "w")', lambda d: ids.append(d) or None)
        self.assertFalse(r["success"])
        self.assertIn("did not answer 'rlm.run' within 3s", json.dumps(r))
        self.assertFalse(r.get("session_dead"), "the kernel must survive an unanswered request")
        h.send({"host_reply": "no-such-request", "reply": _ok(CHILD)})
        r, _ = h.call("1 + 1")
        self.assertTrue(r["success"], r)
        self.assertIn("2", r["display"])

    def test_the_host_closing_its_end_fails_a_waiting_request_and_the_bridge_exits(self):
        h = self.host({"host_request": {"allowed_types": RLM_TYPES}})
        h.send({"request_id": "r1", "code": 'Neura.rlm.spawn("x"; name = "w")'})
        msg = h.read()
        self.assertEqual(msg.get("event"), "host_request")
        h.proc.stdin.close()
        t0 = time.time()
        h.proc.wait(timeout=60)
        self.assertLess(time.time() - t0, 60)

    def test_ephemeral_code_cannot_reach_the_host(self):
        h = self.host({"host_request": {"allowed_types": RLM_TYPES}})
        r, seen = h.call('Neura.rlm.spawn("x"; name = "w")', _rlm_host, ephemeral=True,
                         ceiling={"host_request": {"allowed_types": ["rlm.run"]}})
        self.assertFalse(r["success"])
        self.assertIn("no agent host is attached", json.dumps(r))
        self.assertEqual(seen, [], "an ephemeral worker must not reach the agent host")


class TestBrokerHostRequest(unittest.TestCase):
    def broker(self, ceiling, bridge=None):
        tmp = tempfile.mkdtemp(prefix="neurajl-broker-")
        b = _broker.Broker(ceiling, os.path.join(tmp, "receipts.jsonl"), "s1")
        b.host_bridge = bridge
        return b

    def receipts(self, b):
        return [json.loads(l) for l in Path(b.receipt_log_path).read_text().splitlines()]

    def test_every_request_is_receipted_approved_or_not(self):
        b = self.broker({"host_request": {"allowed_types": ["rlm.run"]}}, lambda t, p: _ok(CHILD))
        self.assertTrue(b.handle_request({"id": "a", "category": "host_request",
                                          "params": {"type": "rlm.run", "payload": {}}})["approved"])
        self.assertFalse(b.handle_request({"id": "b", "category": "host_request",
                                           "params": {"type": "rlm.delete_subagent", "payload": {}}})["approved"])
        rs = self.receipts(b)
        self.assertEqual([(r["request_id"], r["approved"]) for r in rs], [("a", True), ("b", False)])
        self.assertEqual(rs[0]["result"]["result"]["rlm_child_id"], "c1")

    def test_no_bridge_means_no_host(self):
        b = self.broker({"host_request": {"allowed_types": ["rlm.run"]}})
        r = b.handle_request({"category": "host_request", "params": {"type": "rlm.run", "payload": {}}})
        self.assertFalse(r["approved"])
        self.assertIn("no agent host is attached", r["reason"])

    def test_a_request_cannot_supply_its_own_bridge(self):
        called = []
        b = self.broker({"host_request": {"allowed_types": ["rlm.run"]}})
        r = b.handle_request({"category": "host_request",
                              "params": {"type": "rlm.run", "payload": {}, "host_bridge": "x"}, "host_bridge": "x"})
        self.assertFalse(r["approved"])
        self.assertEqual(called, [])

    def test_child_types_must_be_an_explicit_subset(self):
        parent = {"host_request": {"allowed_types": ["rlm.run", "rlm.collect"]}}
        self.assertTrue(_broker.ceiling_is_subset({"host_request": {"allowed_types": ["rlm.collect"]}}, parent)[0])
        self.assertFalse(_broker.ceiling_is_subset({"host_request": {"allowed_types": ["rlm.delete_subagent"]}}, parent)[0])
        self.assertFalse(_broker.ceiling_is_subset({"host_request": {}}, parent)[0])
        self.assertFalse(_broker.ceiling_is_subset({"host_request": {"allowed_types": ["rlm.run"]}}, {})[0])


if __name__ == "__main__":
    unittest.main()
