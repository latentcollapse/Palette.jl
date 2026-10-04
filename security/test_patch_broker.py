"""Real host file operations and one-shot administrator approval entry point."""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from patch_broker import PatchBroker, request_digest


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.store = Path(self.tmp.name) / "grants"
        self.broker = PatchBroker(self.store, {"project": str(self.root)})
        (self.root / "a.txt").write_text("before\n")

    def prepare(self, path="a.txt", before="before\n", content="after\n"):
        return self.broker.prepare({"target": "project", "changes": [{"path": path, "before_sha256": hashlib.sha256(before.encode()).hexdigest() if before is not None else None, "content": content}]}, "world-a")

    def approve(self, record):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("patch_broker.py")), "--storage", str(self.store), "approve", record["request_id"], "--digest", record["patch_sha256"]], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_apply_and_replay(self):
        read = self.broker.call({"action":"read", "target":"project", "path":"a.txt"}, "world-a", {}, None, None)
        self.assertEqual(read["content"], "before\n")
        self.assertEqual(read["sha256"], hashlib.sha256(b"before\n").hexdigest())
        request = self.prepare()
        with self.assertRaises(PermissionError):
            self.broker.apply(request["request_id"], "world-a")
        self.approve(request)
        with self.assertRaises(PermissionError):
            self.broker.apply(request["request_id"], "world-b")
        result = self.broker.apply(request["request_id"], "world-a")
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual((self.root / "a.txt").read_text(), "after\n")
        self.assertEqual(result["files_touched"][0]["after_sha256"], hashlib.sha256(b"after\n").hexdigest())
        with self.assertRaises(PermissionError):
            self.broker.apply(request["request_id"], "world-a")
        self.assertIn('"status": "applied"', (self.store / "receipts.jsonl").read_text())

    def test_target_lock_is_shared_across_registries(self):
        other = PatchBroker(Path(self.tmp.name) / "other-grants", {"project": str(self.root)})
        lock_path = self.root.parent / ("." + self.root.name + ".palette-patch.lock")
        for broker in [self.broker, other]:
            with broker.target_locked(str(self.root)):
                fd = os.open(lock_path, os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(fd)
        fd = os.open(lock_path, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)

    def test_conflict_consumes_without_overwrite(self):
        request = self.prepare()
        self.approve(request)
        (self.root / "a.txt").write_text("someone else's work\n")
        result = self.broker.apply(request["request_id"], "world-a")
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual((self.root / "a.txt").read_text(), "someone else's work\n")
        with self.assertRaises(PermissionError):
            self.broker.apply(request["request_id"], "world-a")

    def test_create_and_unsafe_paths(self):
        request = self.prepare("new.txt", None, "new\n")
        self.approve(request)
        self.assertEqual(self.broker.apply(request["request_id"], "world-a")["status"], "applied")
        self.assertEqual((self.root / "new.txt").read_text(), "new\n")
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "external.txt").write_text("before\n")
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        (self.root / "alias.txt").symlink_to(outside / "external.txt")
        os.link(outside / "external.txt", self.root / "hard.txt")
        for path in ["../outside/external.txt", "link/external.txt", "alias.txt", "hard.txt", ".git/config", "/tmp/nope"]:
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                self.prepare(path)
        self.assertEqual((outside / "external.txt").read_text(), "before\n")

    def test_symlink_swap_after_approval(self):
        request = self.prepare()
        self.approve(request)
        outside = Path(self.tmp.name) / "external.txt"
        outside.write_text("before\n")
        (self.root / "a.txt").unlink()
        (self.root / "a.txt").symlink_to(outside)
        result = self.broker.apply(request["request_id"], "world-a")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(outside.read_text(), "before\n")

    def test_client_without_confirmation_cannot_apply(self):
        request = self.prepare()
        result = self.broker.call({"action": "apply", "request_id": request["request_id"]}, "world-a", {}, None, None)
        self.assertEqual(result["status"], "approval_required")
        self.assertEqual((self.root / "a.txt").read_text(), "before\n")
        with self.assertRaises(PermissionError):
            self.broker.approve(request["request_id"], "wrong digest", "local_administrator")


    def test_expired_and_tampered_requests(self):
        request = self.prepare()
        path = self.broker.path(request["request_id"])
        request["expiry"] = 0
        request["patch_sha256"] = request_digest(request)
        path.write_text(json.dumps(request))
        with self.assertRaises(PermissionError):
            self.broker.approve(request["request_id"], request["patch_sha256"], "local_administrator")
        request = self.prepare()
        altered = dict(request, changes=[{"path":"a.txt", "before_sha256":request["changes"][0]["before_sha256"], "content":"not approved"}])
        self.broker.path(request["request_id"]).write_text(json.dumps(altered))
        with self.assertRaises(PermissionError):
            self.broker.approve(request["request_id"], request["patch_sha256"], "local_administrator")
        self.assertEqual((self.root/"a.txt").read_text(), "before\n")

    def test_partial_failure_is_reported_without_replay(self):
        protected = self.root/"protected"
        protected.mkdir()
        (protected/"b.txt").write_text("before\n")
        before = hashlib.sha256(b"before\n").hexdigest()
        request = self.broker.prepare({"target":"project", "changes":[{"path":name, "before_sha256":before, "content":"after\n"} for name in ["a.txt", "protected/b.txt"]]}, "world-a")
        self.approve(request)
        protected.chmod(0o555)
        try:
            result = self.broker.apply(request["request_id"], "world-a")
            self.assertEqual(result["status"], "partial", result)
            self.assertEqual([row["path"] for row in result["files_touched"]], ["a.txt"])
            self.assertEqual((self.root/"a.txt").read_text(), "after\n")
            self.assertEqual((protected/"b.txt").read_text(), "before\n")
            with self.assertRaises(PermissionError):
                self.broker.apply(request["request_id"], "world-a")
        finally:
            protected.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
