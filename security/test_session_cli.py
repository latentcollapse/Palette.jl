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
import tempfile
import time
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
        self.task_workspace = tempfile.mkdtemp(prefix="neurajl-cli-task-")
        Path(self.task_workspace, "marker.txt").write_text("from-host")
        self.proc = subprocess.Popen(
            [sys.executable, CLI, "--project-dir", PROJECT_DIR, "--ceiling", "{}",
             "--workspace-dir", self.task_workspace, "--turn-timeout", "20"],
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
        shutil.rmtree(self.task_workspace, ignore_errors=True)

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

    def test_printed_output_is_returned_and_does_not_corrupt_the_protocol(self):
        """The worker's stdout used to be the protocol channel, so one
        `println` in turn code was parsed as a response and killed the
        session. Output from subprocesses and from tasks still running after
        the turn must not reach the channel either."""
        r1 = self._turn('println("hello"); @warn "careful"; run(`echo from-child`); @async (sleep(0.2); println("late")); 7')
        self.assertTrue(r1["success"], r1)
        self.assertEqual(r1["data"], 7)
        for text in ("hello", "careful", "from-child"):
            self.assertIn(text, r1["output"])
        time.sleep(0.5)
        r2 = self._turn("8", request_id="2")
        self.assertEqual(r2["request_id"], "2")
        self.assertEqual(r2["data"], 8)

    def test_worker_works_in_the_task_workspace_and_writes_reach_the_host(self):
        r1 = self._turn('read("marker.txt", String)')
        self.assertEqual(r1["data"], "from-host")
        self._turn('write("from-julia.txt", "written")', request_id="2")
        # Checked from outside the sandbox, not from the worker's own view.
        self.assertEqual(Path(self.task_workspace, "from-julia.txt").read_text(), "written")

    def test_task_workspace_survives_session_close(self):
        self._turn("1")
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        self.assertTrue(Path(self.task_workspace, "marker.txt").is_file())

    def test_turn_code_reading_stdin_does_not_consume_the_next_request(self):
        """Turn code shared fd 0 with the request channel: a `readline()` took
        the next request, and the host waited for a reply until timeout."""
        r1 = self._turn('(readline(), read(`cat`, String))')
        self.assertTrue(r1["success"], r1)
        self.assertEqual(r1["data"], ["", ""])
        r2 = self._turn("2 + 2", request_id="2")
        self.assertEqual(r2["request_id"], "2")
        self.assertEqual(r2["data"], 4)

    def test_ephemeral_provenance_stays_out_of_the_task_workspace(self):
        r = self._turn("1 + 1", ephemeral=True)
        self.assertTrue(r["success"], r)
        self.assertEqual(sorted(os.listdir(self.task_workspace)), ["marker.txt"])

    def test_hung_ephemeral_child_is_killed_before_the_session_is(self):
        """The broker gave a child 90s while the session gave the turn less,
        so a hung ephemeral turn killed the persistent kernel with it."""
        self._turn("x = 5")
        r = self._turn("sleep(600)", request_id="2", ephemeral=True)
        self.assertFalse(r["success"])
        self.assertNotIn("session_dead", r)
        self.assertIn("time limit", r["error"])
        r3 = self._turn("x", request_id="3")
        self.assertEqual(r3["data"], 5)

    def test_stdlib_loads_without_precompiling(self):
        """Fails until security/prewarm_depot.py has run for this depot: a
        cold `using Pkg` took ~80s per session, longer than a turn."""
        r = self._turn("using Test, Pkg, SparseArrays; 1")
        self.assertTrue(r["success"], r)
        self.assertNotIn("Precompiling", r["output"], "run security/prewarm_depot.py for this depot")

    def test_bash_runs_shell_syntax_and_returns_the_exit_code(self):
        r = self._turn('bash("ls *.txt | wc -l; echo to-stderr >&2; exit 3")')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], 3)
        self.assertEqual(r["output"].split(), ["1", "to-stderr"])

    def test_shell_syntax_in_backticks_points_to_bash(self):
        r = self._turn("run(`ls *.txt 2>&1`)")
        self.assertFalse(r["success"])
        self.assertIn('bash("...")', r["error"])

    def test_missing_package_says_there_is_no_network(self):
        r = self._turn("using NoSuchPackageAnywhere")
        self.assertFalse(r["success"])
        self.assertIn("no network", r["error"])
        self.assertIn("Loadable: the Julia standard library", r["error"])

    def test_errors_name_the_failing_line_and_function(self):
        self._turn("function f(x)\n    return g(x)\nend")
        r = self._turn("a = 1\nb = f(a)", request_id="2")
        self.assertFalse(r["success"])
        self.assertIn("not defined in `Main`", r["error"])
        self.assertIn("f(x::Int64) at an earlier call, line 2", r["error"])
        self.assertIn("top-level code at this call, line 2", r["error"])

    def test_invalid_utf8_output_does_not_kill_the_session(self):
        """One invalid byte in turn output used to crash the bridge with a
        UnicodeDecodeError, ending the session."""
        r = self._turn('print(String(UInt8[0x61, 0xff, 0x62])); String(UInt8[0xfe])')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["output"], "a�b")
        r2 = self._turn("2 + 2", request_id="2")
        self.assertEqual(r2["data"], 4)

    def test_printing_many_lines_is_fast_and_ordered(self):
        """Each println through a libuv pipe cost ~50us, so 10^6 lines outran
        the turn limit; child output also has to stay in call order."""
        r = self._turn('print("a "); run(`echo b`); println("c"); for i in 1:10^6; println(i); end; 1')
        self.assertTrue(r["success"], r)
        self.assertTrue(r["output"].startswith("a b\nc\n1\n2\n"), r["output"][:40])
        self.assertIn("output truncated", r["output"])

    def test_ephemeral_result_is_displayed_like_a_persistent_one(self):
        """The child used to send struct internals as its result, and a
        value with no JSON form (NaN) crashed it after the code succeeded."""
        r = self._turn("[NaN, 1.0]", ephemeral=True)
        self.assertTrue(r["success"], r)
        self.assertEqual(r["display"], "2-element Vector{Float64}:\n NaN\n   1.0")
        r2 = self._turn("x -> x", request_id="2", ephemeral=True)
        self.assertIn("generic function", r2["display"])

    def test_top_level_loops_use_soft_scope_like_the_repl(self):
        """Turn code ran with script scope: assigning a global inside a
        top-level loop warned and created a new local instead."""
        r = self._turn("best = 0\nfor t in [3, 31, 18]\n    if t > best\n        best = t\n    end\nend\nbest")
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], 31)
        self.assertNotIn("Warning", r["output"])

    def test_session_packages_stay_loadable_after_activating_another_project(self):
        """A model's routine `Pkg.activate(".")` hid every session package."""
        r = self._turn('using Pkg; Pkg.activate("."); using JSON; JSON.json([1])')
        self.assertTrue(r["success"], r)
        self.assertEqual(sorted(os.listdir(self.task_workspace)), ["marker.txt"])

    def test_kernel_exit_reports_its_exit_code(self):
        r = self._turn("exit(3)")
        self.assertFalse(r["success"])
        self.assertIs(r.get("session_dead"), True)
        self.assertIn("exit code 3", r["error"])

    def test_timeout_reply_marks_the_session_dead(self):
        r = self._turn("sleep(60)")
        self.assertFalse(r["success"])
        self.assertIn("turn_timeout", r["error"])
        self.assertIs(r.get("session_dead"), True)


if __name__ == "__main__":
    unittest.main()
