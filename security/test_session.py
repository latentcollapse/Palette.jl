#!/usr/bin/env python3
"""
Executable tests for security/session.py -- NeuraJL's persistent worker.

Same evidence standard as security/test_authority.py: real sandboxes, real
broker, real host filesystem checks, never the worker's own self-report
alone for anything that claims to cross the authority boundary.

Run:
    python3 security/test_session.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from session import NeuraSession, SessionDeadError

REPO_DIR = str(Path(__file__).resolve().parent.parent)
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


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        _skip_if_no_bwrap()
        _skip_if_no_project()


class TestPersistentMind(SessionTestCase):
    def test_state_persists_across_turns(self):
        with NeuraSession(project_dir=PROJECT_DIR, ceiling={}) as s:
            r1 = s.turn("x = 42")
            self.assertTrue(r1["success"])
            r2 = s.turn("x + 1")
            self.assertTrue(r2["success"])
            self.assertEqual(r2["data"], 43)

    def test_ephemeral_does_not_leak_into_persistent_mind(self):
        with NeuraSession(project_dir=PROJECT_DIR, ceiling={}) as s:
            r1 = s.turn("helper(y) = y * 10; helper(3)", ephemeral=True)
            self.assertTrue(r1["success"])
            self.assertEqual(r1["data"], 30)
            r2 = s.turn("@isdefined(helper)")
            self.assertTrue(r2["success"])
            self.assertFalse(r2["data"])

    def test_ephemeral_child_self_corruption_cannot_reach_the_parent(self):
        """The regression this architecture exists to make possible.

        Earlier, same-process ephemeral isolation (Neura.EphemeralTool's
        AST guard) was proven, by direct adversarial testing, insufficient:
        `Core.eval(Base, :(function show(io::IO, x::Int) ... end))` -- a
        value only assembled at runtime -- successfully extended Base.show
        with zero syntactic trace in the submitted source for any
        parse-time check to catch. No static checker can fully police a
        language with reflective eval.

        The fix was architectural, not a smarter checker: `EPHEMERAL`
        turns now run in a real, disposable, OS-sandboxed child process
        (spawn_child_worker, already adversarially proven -- see
        docs/THREAT_MODEL.md rows 16-19), not in this process. The exact
        same payload that broke same-process isolation is preserved here
        deliberately, per the architecture decision: it MUST still succeed
        locally (proving this is still full, unbounded Julia -- nothing
        was crippled to make this "safe"), but the persistent session's
        own Base.show, checked immediately after in a real subsequent
        turn on the SAME session, must be provably unaffected.
        """
        with NeuraSession(project_dir=PROJECT_DIR, ceiling={}) as s:
            before = s.turn("sprint(show, 42)")
            self.assertEqual(before["data"], "42")

            payload = (
                'Core.eval(Base, :(function show(io::IO, x::Int); print(io, "PWNED"); end)); '
                "sprint(show, 42)"
            )
            child = s.turn(payload, ephemeral=True)
            self.assertTrue(child["success"], child)
            self.assertEqual(child["data"], "PWNED")  # the exploit DOES succeed locally -- full power preserved

            after = s.turn("sprint(show, 42)")
            self.assertTrue(after["success"], after)
            self.assertEqual(after["data"], "42")  # but never reaches the persistent process


class TestSessionLifecycle(SessionTestCase):
    def test_two_sessions_get_different_epochs(self):
        s1 = NeuraSession(project_dir=PROJECT_DIR, ceiling={})
        s2 = NeuraSession(project_dir=PROJECT_DIR, ceiling={})
        try:
            self.assertNotEqual(s1.epoch, s2.epoch)
        finally:
            s1.close()
            s2.close()

    def test_killed_worker_is_detected_not_hung_or_silently_respawned(self):
        s = NeuraSession(project_dir=PROJECT_DIR, ceiling={})
        try:
            s._proc.kill()
            s._proc.wait()
            with self.assertRaises(SessionDeadError):
                s.turn("1 + 1")
        finally:
            s.close()

    def test_turn_after_close_raises(self):
        s = NeuraSession(project_dir=PROJECT_DIR, ceiling={})
        s.close()
        with self.assertRaises(SessionDeadError):
            s.turn("1 + 1")

    def test_construction_failure_does_not_leak_the_depot_clone(self):
        """Regression test for a real bug found by direct testing:
        __init__ had no exception handling at all between creating a real
        depot clone (a genuine, if cheap, reflink copy) and the worker's
        subprocess.Popen -- a failure anywhere in that window (confirmed:
        the broker's own serve() raising) leaked the depot clone, the
        broker's thread/socket, and the workspace directories permanently.
        _teardown() itself was also unsafe to call this early (it
        unconditionally referenced self._proc, which didn't exist yet) --
        both fixed together."""
        import session as session_module

        depot_root = os.path.expanduser("~/.neurajl-depot-clones")
        before = set(os.listdir(depot_root)) if os.path.isdir(depot_root) else set()

        orig_serve = session_module._broker.serve
        session_module._broker.serve = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated failure"))
        try:
            with self.assertRaises(RuntimeError):
                NeuraSession(project_dir=PROJECT_DIR, ceiling={})
        finally:
            session_module._broker.serve = orig_serve

        after = set(os.listdir(depot_root)) if os.path.isdir(depot_root) else set()
        self.assertEqual(after - before, set(), "depot clone leaked after a construction failure")


class TestAuthorityUnderPersistence(SessionTestCase):
    """The whole point: keeping the worker warm must not change what it's
    authorized to do. Verified against real host filesystem state, not the
    worker's own self-report."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="neurajl-session-test-")
        self.allowed_sub = os.path.join(self.tmp, "sub")
        os.makedirs(self.allowed_sub)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_approved_write_from_persistent_turn_reaches_real_host(self):
        target = os.path.join(self.allowed_sub, "out.txt")
        with NeuraSession(
            project_dir=PROJECT_DIR, ceiling={"external_fs_write": {"allowed_dirs": [self.allowed_sub]}}
        ) as s:
            r = s.turn(f'Neura.request_capability("external_fs_write", Dict("path" => "{target}", "content" => "hi"))')
            self.assertTrue(r["success"])
            self.assertTrue(r["data"]["approved"])
        self.assertTrue(os.path.isfile(target))
        self.assertEqual(Path(target).read_text(), "hi")

    def test_denied_write_from_persistent_turn_never_reaches_real_host(self):
        denied_target = os.path.join(self.tmp, "outside.txt")  # sibling of allowed_sub, not inside it
        with NeuraSession(
            project_dir=PROJECT_DIR, ceiling={"external_fs_write": {"allowed_dirs": [self.allowed_sub]}}
        ) as s:
            r = s.turn(f'Neura.request_capability("external_fs_write", Dict("path" => "{denied_target}", "content" => "no"))')
            self.assertTrue(r["success"])  # the REQUEST was well-formed; the CAPABILITY was denied
            self.assertFalse(r["data"]["approved"])
        self.assertFalse(os.path.isfile(denied_target))

    def test_ephemeral_default_ceiling_is_empty_not_inherited(self):
        """The new, safer default: an ephemeral child gets NO broker-
        mediated authority unless the caller explicitly widens it, even
        if the parent session's own ceiling would allow more."""
        target = os.path.join(self.allowed_sub, "should_not_exist.txt")
        with NeuraSession(
            project_dir=PROJECT_DIR, ceiling={"external_fs_write": {"allowed_dirs": [self.allowed_sub]}}
        ) as s:
            r = s.turn(
                f'Neura.request_capability("external_fs_write", Dict("path" => "{target}", "content" => "eph"))',
                ephemeral=True,  # no ephemeral_ceiling given -- defaults to {}
            )
            self.assertTrue(r["success"])
            self.assertFalse(r["data"]["approved"])
        self.assertFalse(os.path.isfile(target))

    def test_ephemeral_turn_reaches_the_broker_when_explicitly_widened(self):
        target = os.path.join(self.allowed_sub, "from_ephemeral.txt")
        ceiling = {"external_fs_write": {"allowed_dirs": [self.allowed_sub]}}
        with NeuraSession(project_dir=PROJECT_DIR, ceiling=ceiling) as s:
            r = s.turn(
                f'Neura.request_capability("external_fs_write", Dict("path" => "{target}", "content" => "eph"))',
                ephemeral=True,
                ephemeral_ceiling=ceiling,  # explicit: C_child == C_caller here, still validated as a real subset
            )
            self.assertTrue(r["success"])
            self.assertTrue(r["data"]["approved"])
        self.assertEqual(Path(target).read_text(), "eph")


if __name__ == "__main__":
    unittest.main()
