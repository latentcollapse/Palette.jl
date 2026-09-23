#!/usr/bin/env python3
"""
Executable tests for security/session_cli.py -- the stdio bridge a
different-language host (Node, via Prime-Agent's baseToolsFactory) spawns
once per agent session to drive a persistent NeuraSession.

Regression coverage for a real, serious bug found while building the
Prime-Agent chassis integration: any `subprocess.run(["julia", ...])`
call anywhere in this codebase that didn't explicitly set `stdin=` would
silently corrupt session_cli.py's OWN stdin the moment it ran inside this
process (confirmed: `julia -e ...` invoked with an inherited, unspecified
stdin breaks the CALLER's own subsequent reads from that same stdin,
while e.g. `/bin/true` does not) -- invisible for every one-shot caller
before this bridge existed, since nothing depended on a live stdin pipe
surviving past that point. The most dangerous instance: NeuraSession's own
broker runs in a background thread INSIDE this same process, and its
spawn_child_worker handler (reached by every ephemeral turn) calls
launch_worker.run_worker(), which itself calls resolve_real_julia_binary()
-- both previously missing stdin=subprocess.DEVNULL. A single ephemeral
turn would have silently broken every turn after it.

Run:
    python3 security/test_session_cli.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_DIR = str(Path(__file__).resolve().parent.parent)
CLI = str(Path(__file__).resolve().parent / "session_cli.py")
PROJECT_DIR = os.environ.get(
    "NEURAJL_TEST_PROJECT_DIR",
    "/tmp/claude-1000/-mnt-d-Code-Projects/c3c092a4-acab-472c-b26c-e9672fac8468/scratchpad/ijulia-harness-env",
)


def _skip_if_no_bwrap():
    if shutil.which("bwrap") is None:
        raise unittest.SkipTest("bubblewrap (bwrap) not found on PATH")


def _skip_if_no_project():
    if not Path(PROJECT_DIR).exists():
        raise unittest.SkipTest(f"no Julia dev project at {PROJECT_DIR}")


class TestSessionCli(unittest.TestCase):
    def setUp(self):
        _skip_if_no_bwrap()
        _skip_if_no_project()
        self.proc = subprocess.Popen(
            [sys.executable, CLI, "--project-dir", PROJECT_DIR, "--ceiling", "{}"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        hello_line = self.proc.stdout.readline()
        self.assertTrue(hello_line, "no HELLO line -- process died before startup")
        self.hello = json.loads(hello_line)
        self.assertEqual(self.hello.get("kind"), "HELLO")

    def tearDown(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                pipe.close()
            except Exception:
                pass

    def _turn(self, code: str, request_id: str = "1", **extra) -> dict:
        req = {"request_id": request_id, "code": code, **extra}
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        self.assertTrue(line, f"no response line for request {req!r} -- stdin pipe likely broken")
        return json.loads(line)

    def test_hello_has_a_real_epoch(self):
        self.assertIsInstance(self.hello.get("epoch"), str)
        self.assertTrue(self.hello["epoch"])

    def test_state_persists_across_turns(self):
        r1 = self._turn("x = 42")
        self.assertTrue(r1["success"])
        r2 = self._turn("x + 1")
        self.assertTrue(r2["success"])
        self.assertEqual(r2["data"], 43)

    def test_ephemeral_turn_does_not_break_the_stdin_pipe_for_later_turns(self):
        """The regression this file exists for. An ephemeral turn routes
        through spawn_child_worker, which calls launch_worker.run_worker,
        which calls resolve_real_julia_binary -- both subprocess.run
        `julia` invocations that used to inherit (and silently break)
        this CLI process's own stdin. If the fix regresses, this test
        hangs or fails on the turn AFTER the ephemeral one, not the
        ephemeral one itself."""
        r1 = self._turn("x = 42")
        self.assertTrue(r1["success"])

        r2 = self._turn("helper(y) = y * 10; helper(3)", ephemeral=True)
        self.assertTrue(r2["success"], r2)
        self.assertEqual(r2["data"], 30)

        # The real test: does the pipe still work at all, and is the
        # persistent mind's state (from turn 1) still there?
        r3 = self._turn("x")
        self.assertTrue(r3["success"], r3)
        self.assertEqual(r3["data"], 42)

        r4 = self._turn("@isdefined(helper)")
        self.assertTrue(r4["success"], r4)
        self.assertFalse(r4["data"])

    def test_malformed_request_gets_an_error_response_not_a_crash(self):
        self.proc.stdin.write("not valid json\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        self.assertTrue(line)
        resp = json.loads(line)
        self.assertFalse(resp["success"])
        self.assertIn("malformed", resp["error"])

        # process must still be alive and usable after a malformed request
        r = self._turn("1 + 1")
        self.assertTrue(r["success"])
        self.assertEqual(r["data"], 2)


if __name__ == "__main__":
    unittest.main()
