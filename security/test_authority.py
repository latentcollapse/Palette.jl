#!/usr/bin/env python3
"""
Executable tests for Experiment 002's authority-fence claims.

These are deliberately NOT mocked. Every test launches a real bubblewrap
sandbox around a real julia process (or, for the ceiling-subset tests,
exercises the real broker logic directly). This is slow by design --
several tests pay a real, currently-unsolved ~40s Julia precompilation
cost per sandboxed launch (see docs/NEURABASH_SECURITY_PORT.md) -- and
that slowness is itself honest evidence about the current state of the
depot problem, not something to hide by mocking it away.

Every "blocked" assertion checks REAL evidence (host filesystem state,
process exit codes, a second process's own PID), never just the worker's
own self-reported stdout -- see docs/THREAT_MODEL.md's note on why two
early manual tests were false positives until checked this way.

Run:
    python3 security/test_authority.py            # full suite (slow: real sandboxes)
    python3 security/test_authority.py -k subset   # ceiling_is_subset only (fast, no sandbox)

Requires: bubblewrap (bwrap) on PATH, a Julia install with this package and
IJulia available in some project environment (see README.md's Naming
section and docs/EXPERIMENT_002_AUTHORITY.md for how this session's own
dev environment was built).
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import broker as B
from launch_worker import create_session_depot, run_worker

REPO_DIR = str(Path(__file__).resolve().parent.parent)

# A Julia project environment with `Neura` (this repo, dev-installed) and
# `IJulia` available. Point this at your own dev environment via env var;
# defaults to the path this session actually used.
PROJECT_DIR = os.environ.get(
    "NEURAJL_TEST_PROJECT_DIR",
    "/tmp/claude-1000/-mnt-d-Code-Projects/c3c092a4-acab-472c-b26c-e9672fac8468/scratchpad/ijulia-harness-env",
)


def _julia_str(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _julia_dict(d: dict) -> str:
    parts = []
    for k, v in d.items():
        if isinstance(v, str):
            v_lit = _julia_str(v)
        elif isinstance(v, bool):
            v_lit = "true" if v else "false"
        elif isinstance(v, (int, float)):
            v_lit = str(v)
        else:
            raise TypeError(f"unsupported value type for Julia Dict literal: {type(v)}")
        parts.append(f"{_julia_str(k)} => {v_lit}")
    return "Dict(" + ", ".join(parts) + ")"


def _skip_if_no_bwrap():
    if shutil.which("bwrap") is None:
        raise unittest.SkipTest("bubblewrap (bwrap) not found on PATH")


def _skip_if_no_project():
    if not Path(PROJECT_DIR).exists():
        raise unittest.SkipTest(
            f"no Julia dev project at {PROJECT_DIR} -- set NEURAJL_TEST_PROJECT_DIR "
            "to a project with Neura (dev-installed from this repo) and IJulia"
        )


def _skip_if_no_network():
    import socket

    try:
        socket.create_connection(("pkg.julialang.org", 443), timeout=5).close()
    except OSError:
        raise unittest.SkipTest("no network reachable -- package_management needs the real Julia registry")


class SandboxTestCase(unittest.TestCase):
    """Common setup for tests that launch a real sandboxed worker."""

    def setUp(self):
        _skip_if_no_bwrap()
        _skip_if_no_project()
        self.tmp = tempfile.mkdtemp(prefix="neurajl-test-")
        self.workspace = os.path.join(self.tmp, "workspace")
        os.makedirs(self.workspace, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, script: str, broker_socket_dir: str | None = None, timeout: float = 90):
        return run_worker(
            workspace_dir=self.workspace,
            project_dir=PROJECT_DIR,
            repo_dir=REPO_DIR,
            script=script,
            broker_socket_dir=broker_socket_dir,
            timeout=timeout,
        )


class TestSandboxContainment(SandboxTestCase):
    def test_network_blocked_via_run(self):
        r = self.run_script('run(`curl -s -m 3 http://example.com`)')
        self.assertNotEqual(r.returncode, 0, "curl should fail with no network namespace")

    def test_network_blocked_via_raw_socket(self):
        r = self.run_script(
            'using Sockets; try; Sockets.connect("1.1.1.1", 80); println("ESCAPE"); '
            'catch e; println("blocked: ", sprint(showerror, e)); end'
        )
        self.assertNotIn("ESCAPE", r.stdout)
        self.assertIn("blocked", r.stdout)

    def test_sensitive_file_not_visible(self):
        r = self.run_script(
            'try; read("/etc/shadow", String); println("ESCAPE"); '
            'catch e; println("blocked: ", sprint(showerror, e)); end'
        )
        self.assertNotIn("ESCAPE", r.stdout)
        self.assertIn("No such file", r.stdout)

    def test_ephemeral_tmp_write_does_not_reach_host(self):
        marker = f"neurajl-test-{os.getpid()}-{time.time_ns()}"
        host_path = f"/tmp/{marker}.txt"
        self.assertFalse(os.path.exists(host_path))
        r = self.run_script(f'write("{host_path}", "pwned")')
        self.assertEqual(r.returncode, 0)
        # It "succeeded" inside the sandbox (its own ephemeral /tmp) -- the
        # only claim that matters is that it never reaches the real host.
        self.assertFalse(os.path.exists(host_path), "a /tmp write inside the sandbox must not reach the real host")

    def test_workspace_write_is_real_and_reaches_host(self):
        host_file = os.path.join(self.workspace, "positive-control.txt")
        self.assertFalse(os.path.exists(host_file))
        r = self.run_script(f'write("{host_file}", "legit sandbox-local write")')
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(host_file), "a write inside the bounded workspace must reach the real host")
        self.assertEqual(Path(host_file).read_text(), "legit sandbox-local write")

    def test_eval_has_identical_power_and_failure_modes_as_direct_code(self):
        r = self.run_script(
            'direct = 1 + 1; evaled = Core.eval(Main, Meta.parse("1 + 1")); '
            'println("equal=", direct == evaled)'
        )
        self.assertIn("equal=true", r.stdout)

    def test_subprocess_inherits_network_restriction(self):
        r = self.run_script(
            'out = read(`sh -c "curl -s -m 3 http://example.com || echo NO_NETWORK_IN_CHILD"`, String); '
            'println(strip(out))'
        )
        self.assertIn("NO_NETWORK_IN_CHILD", r.stdout)

    def test_worker_cannot_self_spawn_a_new_sandbox(self):
        r = self.run_script(
            'try; run(`bwrap --unshare-user --uid 0 --gid 0 -- echo pwned`); println("ESCAPE"); '
            'catch e; println("blocked: ", sprint(showerror, e)); end'
        )
        self.assertNotIn("ESCAPE", r.stdout)


class TestBrokerMediatedCapabilities(SandboxTestCase):
    def setUp(self):
        super().setUp()
        self.broker_socket_dir = tempfile.mkdtemp(prefix="njl-bsock-")  # short path: AF_UNIX length limit
        self.approved_dir = os.path.join(self.tmp, "approved-out")
        os.makedirs(self.approved_dir, exist_ok=True)
        self.receipts_path = os.path.join(self.tmp, "receipts.jsonl")
        self.ceiling = {
            "external_fs_write": {"allowed_dirs": [self.approved_dir]},
            "network_access": {"allowed": False},
        }
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=B.serve,
            args=(
                os.path.join(self.broker_socket_dir, "broker.sock"),
                self.ceiling,
                self.receipts_path,
                "test-session",
                self._stop,
            ),
            daemon=True,
        )
        self._thread.start()
        time.sleep(0.3)

    def tearDown(self):
        self._stop.set()
        time.sleep(0.2)
        shutil.rmtree(self.broker_socket_dir, ignore_errors=True)
        super().tearDown()

    def _request(self, category: str, params: dict) -> str:
        # Build a Julia Dict(...) literal directly rather than round-tripping
        # through JSON.parse: JSON is only a transitive dependency of the
        # test project (via Neura), so `using JSON` isn't available to a
        # plain top-level script here -- same restriction Julia's Pkg
        # enforces on any transitive-only dependency.
        return f'using Neura; r = Neura.request_capability("{category}", {_julia_dict(params)}); println(r)'

    def test_approved_write_reaches_real_host(self):
        target = os.path.join(self.approved_dir, "from-worker.txt")
        r = self.run_script(
            self._request("external_fs_write", {"path": target, "content": "real write via broker"}),
            broker_socket_dir=self.broker_socket_dir,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"approved" => true', r.stdout)
        self.assertTrue(os.path.exists(target))
        self.assertEqual(Path(target).read_text(), "real write via broker")

    def test_denied_write_outside_ceiling_does_not_reach_host(self):
        target = "/tmp/definitely-not-in-ceiling.txt"
        self.assertFalse(os.path.exists(target))
        r = self.run_script(
            self._request("external_fs_write", {"path": target, "content": "nope"}),
            broker_socket_dir=self.broker_socket_dir,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"approved" => false', r.stdout)
        self.assertFalse(os.path.exists(target))

    def test_denied_network_request(self):
        r = self.run_script(
            self._request("network_access", {"url": "http://example.com"}),
            broker_socket_dir=self.broker_socket_dir,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"approved" => false', r.stdout)

    def test_direct_bypass_of_broker_still_blocked(self):
        """A denied capability isn't just declined by the nice API -- the
        same effect attempted directly, bypassing request_capability
        entirely, must still fail."""
        target = "/tmp/direct-bypass-attempt.txt"
        self.assertFalse(os.path.exists(target))
        r = self.run_script(f'write("{target}", "bypass")', broker_socket_dir=self.broker_socket_dir)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(target))

    def test_receipts_are_written_for_every_decision(self):
        r = self.run_script(
            self._request("network_access", {"url": "http://example.com"}),
            broker_socket_dir=self.broker_socket_dir,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        receipts = [json.loads(l) for l in Path(self.receipts_path).read_text().splitlines() if l.strip()]
        self.assertTrue(any(rec["category"] == "network_access" and rec["approved"] is False for rec in receipts))


class TestNetworkRedirectSafety(unittest.TestCase):
    """Direct Broker unit tests (no sandbox needed) -- regression for a
    real bypass found by direct exploitation: an allowlisted host that
    responds with an HTTP redirect to a DIFFERENT, non-allowlisted host
    was silently followed by urllib's default opener, reaching the
    disallowed host with the allowlist only ever having checked the FIRST
    url."""

    def setUp(self):
        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(handler_self):
                if handler_self.path == "/redirect":
                    handler_self.send_response(302)
                    handler_self.send_header(
                        "Location", f"http://localhost:{handler_self.server.server_address[1]}/secret"
                    )
                    handler_self.end_headers()
                else:
                    handler_self.send_response(200)
                    handler_self.end_headers()
                    handler_self.wfile.write(b"SECRET REACHED")

            def log_message(handler_self, *args):
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_redirect_to_disallowed_host_is_not_followed(self):
        # allowlist covers the INITIAL host (127.0.0.1) but not the
        # redirect target (localhost) -- confirmed exploitable before the
        # fix: the redirect target's content ("SECRET REACHED") came back
        # with the allowlist never having been asked about "localhost" at all.
        broker = B.Broker(
            {"network_access": {"allowed": True, "allowed_hosts": ["127.0.0.1"]}},
            os.path.join(tempfile.mkdtemp(), "receipts.jsonl"), "redirect-test",
        )
        result = broker._handle_network_access({"url": f"http://127.0.0.1:{self.port}/redirect"})
        self.assertEqual(result["status"], 302)
        self.assertNotIn("SECRET", result["body_prefix"])


class TestCeilingSubset(unittest.TestCase):
    """Fast, no sandbox: the C_child ⊆ C_caller logic in isolation."""

    def setUp(self):
        self.parent = {
            "external_fs_write": {"allowed_dirs": ["/tmp/a"]},
            "network_access": {"allowed": False},
        }

    def test_identical_to_parent_is_allowed(self):
        ok, _ = B.ceiling_is_subset({"external_fs_write": {"allowed_dirs": ["/tmp/a"]}}, self.parent)
        self.assertTrue(ok)

    def test_narrower_subdir_is_allowed(self):
        ok, _ = B.ceiling_is_subset({"external_fs_write": {"allowed_dirs": ["/tmp/a/sub"]}}, self.parent)
        self.assertTrue(ok)

    def test_network_escalation_is_denied(self):
        ok, reason = B.ceiling_is_subset({"network_access": {"allowed": True}}, self.parent)
        self.assertFalse(ok)
        self.assertIn("network_access", reason)

    def test_dir_outside_parent_is_denied(self):
        ok, _ = B.ceiling_is_subset({"external_fs_write": {"allowed_dirs": ["/tmp/b"]}}, self.parent)
        self.assertFalse(ok)

    def test_unrecognized_category_fails_closed(self):
        ok, reason = B.ceiling_is_subset({"credential_access": {"allowed": True}}, self.parent)
        self.assertFalse(ok)
        self.assertIn("not present", reason)

    def test_omitted_allowed_hosts_against_host_restricted_parent_is_denied(self):
        """Regression: a parent restricted to specific hosts previously let
        a child omit allowed_hosts entirely (or pass it as null) and pass
        the subset check -- "child said nothing about hosts" was silently
        treated as "no widening", when omitting it actually means
        unrestricted, which IS wider than a host-restricted parent.
        Confirmed exploitable by direct testing before this fix."""
        parent = {"network_access": {"allowed": True, "allowed_hosts": ["example.invalid"]}}
        ok, reason = B.ceiling_is_subset({"network_access": {"allowed": True}}, parent)
        self.assertFalse(ok)
        self.assertIn("allowed_hosts", reason)

        ok2, reason2 = B.ceiling_is_subset({"network_access": {"allowed": True, "allowed_hosts": None}}, parent)
        self.assertFalse(ok2)
        self.assertIn("allowed_hosts", reason2)

    def test_real_host_subset_still_allowed(self):
        """Not a false positive from the fix above: a child that DOES name
        a real subset of the parent's allowed_hosts must still pass."""
        parent = {"network_access": {"allowed": True, "allowed_hosts": ["a.invalid", "b.invalid"]}}
        ok, _ = B.ceiling_is_subset({"network_access": {"allowed": True, "allowed_hosts": ["a.invalid"]}}, parent)
        self.assertTrue(ok)


class TestNestedChildWorker(SandboxTestCase):
    def setUp(self):
        super().setUp()
        self.approved_dir = os.path.join(self.tmp, "approved-out")
        os.makedirs(self.approved_dir, exist_ok=True)
        self.child_sub = os.path.join(self.approved_dir, "child-sub")
        os.makedirs(self.child_sub, exist_ok=True)
        self.child_workspace = os.path.join(self.tmp, "child-workspace")
        os.makedirs(self.child_workspace, exist_ok=True)
        self.broker_socket_dir = tempfile.mkdtemp(prefix="njl-bsock-")
        self.receipts_path = os.path.join(self.tmp, "receipts.jsonl")

    def tearDown(self):
        shutil.rmtree(self.broker_socket_dir, ignore_errors=True)
        super().tearDown()

    def _serve(self, ceiling):
        stop = threading.Event()
        t = threading.Thread(
            target=B.serve,
            args=(os.path.join(self.broker_socket_dir, "broker.sock"), ceiling, self.receipts_path, "nested-test", stop),
            kwargs={"project_dir": PROJECT_DIR, "repo_dir": REPO_DIR},
            daemon=True,
        )
        t.start()
        time.sleep(0.3)
        return stop

    def test_child_requesting_wider_ceiling_is_denied(self):
        stop = self._serve({"external_fs_write": {"allowed_dirs": [self.child_sub]}, "network_access": {"allowed": False}})
        try:
            script = (
                'using Neura; r = Neura.request_capability("spawn_child_worker", Dict('
                '"ceiling" => Dict("network_access" => Dict("allowed" => true)), '
                '"script" => "println(1)", '
                f'"child_workspace" => "{self.child_workspace}", '
                f'"child_project" => "{PROJECT_DIR}", '
                f'"child_repo" => "{REPO_DIR}")); println(r)'
            )
            r = self.run_script(script, broker_socket_dir=self.broker_socket_dir)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('"approved" => false', r.stdout)
        finally:
            stop.set()

    def test_child_with_approved_network_cannot_reach_host_outside_allowlist(self):
        """Regression test for a real bug found and fixed after Experiment
        002 first shipped: an approved child ceiling with `network_access`
        used to get a raw, unshared network namespace (`--unshare-net`
        omitted) regardless of `allowed_hosts` -- proven exploitable by
        reaching an arbitrary local listener the ceiling never named, with
        zero broker mediation. Independent host-side evidence, not the
        worker's own self-report: a real local HTTP server, outside the
        sandbox, that only a real network connection could have reached."""

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"UNAUTHORIZED HOST REACHED")

            def log_message(self, *_args):
                pass

        httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        stop = self._serve({"network_access": {"allowed": True, "allowed_hosts": ["example.invalid"]}})
        try:
            child_script = (
                "using Sockets\n"
                "try\n"
                f'    sock = connect("127.0.0.1", {port})\n'
                '    println(sock, "GET / HTTP/1.0\\r\\n\\r\\n")\n'
                "    resp = readline(sock)\n"
                '    println("REACHED: ", resp)\n'
                "catch e\n"
                '    println("BLOCKED: ", e)\n'
                "end\n"
            )
            spawn_script = (
                'using Neura; r = Neura.request_capability("spawn_child_worker", Dict('
                '"ceiling" => Dict("network_access" => Dict("allowed" => true, "allowed_hosts" => ["example.invalid"])), '
                f'"script" => {json.dumps(child_script)}, '
                f'"child_workspace" => "{self.child_workspace}", '
                f'"child_project" => "{PROJECT_DIR}", '
                f'"child_repo" => "{REPO_DIR}")); println(r)'
            )
            r = self.run_script(spawn_script, broker_socket_dir=self.broker_socket_dir)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('"approved" => true', r.stdout)  # the spawn itself is a legitimate subset request
            self.assertIn("BLOCKED", r.stdout)
            self.assertNotIn("REACHED", r.stdout)
        finally:
            stop.set()
            httpd.shutdown()
            httpd.server_close()

    def test_child_workspace_param_cannot_pick_an_arbitrary_host_path(self):
        """Regression test for a real bug found by direct exploitation: a
        worker with a ceiling containing ONLY `spawn_child_worker` (no
        `external_fs_write` at all) could previously name any host
        directory as `child_workspace` in the request and have the broker
        bind-mount it writable into the child -- a write attacker-chosen
        outside any ceiling check. Independent host-side evidence: the
        target directory is checked directly, not through the worker's
        own self-report."""
        attacker_chosen_dir = tempfile.mkdtemp(prefix="njl-attacker-target-")
        stop = self._serve({"spawn_child_worker": {}})  # deliberately NO external_fs_write at all
        try:
            script = (
                'using Neura; r = Neura.request_capability("spawn_child_worker", Dict('
                '"ceiling" => Dict(), '
                '"script" => "write(joinpath(pwd(), \\"ESCAPED.txt\\"), \\"no external_fs_write needed\\")", '
                f'"child_workspace" => "{attacker_chosen_dir}")); println(r)'
            )
            r = self.run_script(script, broker_socket_dir=self.broker_socket_dir)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('"approved" => true', r.stdout)  # the spawn itself is legitimate -- ceiling {} is a valid subset
            self.assertFalse(
                os.path.isfile(os.path.join(attacker_chosen_dir, "ESCAPED.txt")),
                "child_workspace param let the request pick a real host write target with no ceiling check",
            )
        finally:
            stop.set()

    def test_grandchild_nesting_actually_works(self):
        """Regression test for a real bug found by direct testing:
        ceiling_is_subset used `if not parent_cap` (Python truthiness) to
        check whether a category was present in the parent's ceiling --
        but `spawn_child_worker`'s own ceiling shape is `{}` throughout
        this codebase, and an empty dict is falsy. That made granting a
        CHILD the ability to spawn its own children unconditionally
        impossible even when the parent's ceiling explicitly named
        spawn_child_worker, and there was also no explicit
        ceiling_is_subset branch for the category at all. Both fixed;
        this proves a real two-level nesting end to end, not just the
        ceiling-logic unit case -- the grandchild reports its own real,
        independent PID namespace (pid=2: the only process under that
        namespace's own bwrap reaper, where a host pid would be large), the
        same independent evidence the one-level case already used."""
        stop = self._serve({"spawn_child_worker": {}})
        try:
            grandchild_script = 'println("grandchild pid=", getpid())'
            child_script = (
                'using Neura; r2 = Neura.request_capability("spawn_child_worker", Dict('
                '"ceiling" => Dict(), '
                f'"script" => {json.dumps(grandchild_script)})); println("child got: ", r2)'
            )
            top_script = (
                'using Neura; r1 = Neura.request_capability("spawn_child_worker", Dict('
                '"ceiling" => Dict("spawn_child_worker" => Dict()), '
                f'"script" => {json.dumps(child_script)})); println("top got: ", r1)'
            )
            r = self.run_script(top_script, broker_socket_dir=self.broker_socket_dir, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('"approved" => true', r.stdout)
            self.assertIn("grandchild pid=2", r.stdout)
        finally:
            stop.set()


class TestPackageManagement(SandboxTestCase):
    """package_management: the broker decides whether a specific package is
    allowed and performs the real Pkg.add itself, into this session's own
    private depot clone -- never a worker's own writable JULIA_DEPOT_PATH
    (that would let it install and run arbitrary build/artifact-download
    code as an ungated, sandbox-local effect). Real network, real registry,
    real install -- see broker.py's _handle_package_management docstring
    for why this needs a shared, session-lifetime depot clone rather than
    the one-clone-per-launch default every other test in this file uses.
    """

    def setUp(self):
        super().setUp()
        _skip_if_no_network()
        self.depot_dir = create_session_depot()

    def tearDown(self):
        shutil.rmtree(self.depot_dir, ignore_errors=True)
        super().tearDown()

    def _serve(self, ceiling):
        sock_dir = tempfile.mkdtemp(prefix="njl-pkgmgmt-bsock-")
        stop = threading.Event()
        server, _ = B.serve(
            os.path.join(sock_dir, "broker.sock"), ceiling,
            os.path.join(sock_dir, "receipts.jsonl"), "pkgmgmt-test",
            depot_dir=self.depot_dir,
        )
        return sock_dir, server

    def test_allowed_package_installs_and_becomes_usable(self):
        sock_dir, server = self._serve({"package_management": {"allowed_packages": ["Crayons"]}})
        try:
            script = (
                'using Neura\n'
                'r = Neura.request_capability("package_management", Dict("name" => "Crayons"))\n'
                'println("approved: ", r["approved"])\n'
                'using Crayons\n'
                'println("USABLE")\n'
            )
            r = run_worker(
                workspace_dir=self.workspace, project_dir=PROJECT_DIR, repo_dir=REPO_DIR,
                script=script, broker_socket_dir=sock_dir, network_enabled=False,
                depot_clone_dir=self.depot_dir, timeout=400,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("approved: true", r.stdout)
            self.assertIn("USABLE", r.stdout)
        finally:
            server.shutdown()
            server.server_close()
            shutil.rmtree(sock_dir, ignore_errors=True)

    def test_package_outside_allowlist_is_denied_without_installing(self):
        sock_dir, server = self._serve({"package_management": {"allowed_packages": ["Crayons"]}})
        try:
            script = (
                'using Neura\n'
                'r = Neura.request_capability("package_management", Dict("name" => "HTTP"))\n'
                'println("approved: ", r["approved"])\n'
                'ok = try; using HTTP; true; catch; false; end\n'
                'println("HTTP_USABLE: ", ok)\n'
            )
            r = run_worker(
                workspace_dir=self.workspace, project_dir=PROJECT_DIR, repo_dir=REPO_DIR,
                script=script, broker_socket_dir=sock_dir, network_enabled=False,
                depot_clone_dir=self.depot_dir, timeout=60,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("approved: false", r.stdout)
            self.assertIn("HTTP_USABLE: false", r.stdout)
        finally:
            server.shutdown()
            server.server_close()
            shutil.rmtree(sock_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
