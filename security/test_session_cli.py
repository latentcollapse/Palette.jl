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
import uuid
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


def _host_processes_with(marker: str) -> list[str]:
    """Command lines of every host process containing `marker`, read from the
    host's own /proc, which sees into every sandbox's PID namespace."""
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if marker in cmd:
            found.append(cmd)
    return found


# Assembles the marker at runtime, so the child's own command line (which
# carries the turn source) never contains it; only descendants it spawns do.
def _descendant_code(marker: str, body: str) -> str:
    return f'mk = string("{marker[:6]}", "{marker[6:]}"); desc = "sleep 300; : $mk"; ' + body


# A daemon in the classic shape: fork, setsid, fork again, ignore TERM and
# HUP, close stdio, then exec the marked descendant.
_DAEMON_PY = (
    "import os, signal\n"
    "if os.fork(): os._exit(0)\n"
    "os.setsid()\n"
    "if os.fork(): os._exit(0)\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
    "os.chdir('/')\n"
    "for f in (0, 1, 2): os.close(f)\n"
    "os.execvp('bash', ['bash', '-c', os.environ['D']])\n"
)
_ESCAPE_ATTEMPTS = (
    'run(`bash -c $desc`; wait=false); '
    'bash("(setsid nohup bash -c \\"trap \'\' TERM HUP INT; $desc\\" >/dev/null 2>&1 &)"); '
    'run(pipeline(`bash -c $desc`; stdout=stdout, stderr=stderr); wait=false); '
    f'write("d.py", {json.dumps(_DAEMON_PY)}); run(addenv(`python3 d.py`, "D" => desc)); '
)
_COUNT_INSIDE = (
    'sleep(1.0); count(p -> occursin(mk, try read("/proc/$p/cmdline", String) catch; "" end), '
    'filter(p -> all(isdigit, p), readdir("/proc")))'
)


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

    def test_bash_runs_shell_syntax_and_returns_its_output_and_status(self):
        """bash() used to return only the exit code, so a command's output
        could be read but not kept."""
        r = self._turn('r = bash("ls *.txt | wc -l; echo to-stderr >&2; exit 3")')
        self.assertTrue(r["success"], r)
        self.assertIn("exitcode=3", r["display"])
        self.assertEqual(r["output"].split(), ["1", "to-stderr"])
        r = self._turn("(r.exitcode, strip(r.stdout), strip(r.stderr), success(r))")
        self.assertEqual(r["data"], [3, "1", "to-stderr", False])

    def test_sh_literal_passes_dollar_to_the_shell(self):
        """In bash("...") a `$` is Julia interpolation, so `$?` and `$VAR`
        were parse errors."""
        r = self._turn('sh"x=5; echo $((x*2)); false; echo status=$?".stdout')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], "10\nstatus=1\n")
        r = self._turn('bash("echo $?")')
        self.assertFalse(r["success"])
        self.assertIn('sh"..."', r["error"])

    def test_payload_reaches_the_kernel_without_julia_quoting(self):
        """Source files embedded in Julia string literals failed to parse
        on triple quotes, `$` and backslashes."""
        text = 'def f():\n    """Doc with "quotes", $dollar and a \\\\ backslash."""\n    return 1\n'
        r = self._turn('write("f.py", PAYLOAD); read("f.py", String) == PAYLOAD', payload=text)
        self.assertTrue(r["success"], r)
        self.assertIs(r["data"], True)
        self.assertEqual(Path(self.task_workspace, "f.py").read_text(), text)
        r = self._turn("PAYLOAD === nothing")
        self.assertIs(r["data"], True, "a payload must not leak into the next call")

    def test_a_docstring_that_ends_an_enclosing_string_is_named(self):
        """Code with a docstring, embedded in a triple-quoted string, failed in
        every endurance run as `invalid keyword argument name "last::Bool"`:
        the docstring's quotes ended the string and its signature ran as code."""
        code = ('block = """\n\n"""\n    move_to_end!(d, key; last::Bool=true)\n\nMove `key` to the end.\n"""\n'
                'function move_to_end!(d, key; last::Bool=true)\n    d\nend\n"""\nlength(block)')
        r = self._turn(code)
        self.assertFalse(r["success"], r)
        self.assertIn("invalid keyword argument", r["error"])
        self.assertIn("begins on line 1 ends at the docstring", r["error"])
        self.assertIn("write(path, PAYLOAD)", r["error"])
        # A docstring kept whole in its own literal is fine, and an unrelated
        # error in the same shape of code gets no such hint.
        r = self._turn('doc = """\n    f(x)\n\nDoc.\n"""\nerror("unrelated")')
        self.assertFalse(r["success"], r)
        self.assertNotIn("docstring", r["error"])

    def test_an_undefined_name_interpolated_into_file_text_is_named(self):
        """Julia source for a file, written as a string literal: its `$K`
        ran in the kernel and failed as an undefined name, 13 times in the
        endurance runs, with no word about interpolation."""
        r = self._turn('write("f.jl", "function f(d::Dict{K,V}) where {K,V}\\n    error(\\"bad key type $K\\")\\nend\\n")')
        self.assertFalse(r["success"], r)
        self.assertIn("`K` is interpolated into a string", r["error"])
        self.assertIn("write(path, PAYLOAD)", r["error"])
        r = self._turn("undefined_thing + 1")
        self.assertFalse(r["success"], r)
        self.assertNotIn("interpolated", r["error"])

    def test_named_payload_texts_carry_an_edit(self):
        """An edit needs two texts, the old and the new, and a single payload
        held one, so models embedded both in Julia literals and met quoting
        errors (2 or more texts in 90% of the pilot's inline writes)."""
        old = 'x = "$a"\n"""\n    f(x)\n"""\n'
        new = 'x = "\\$b"  # \\ and """ kept\n'
        Path(self.task_workspace, "e.jl").write_text("head\n" + old + "tail\n")
        r = self._turn('p = "e.jl"; s = read(p, String); occursin(PAYLOAD["old"], s) || error("no"); '
                       'write(p, replace(s, PAYLOAD["old"] => PAYLOAD["new"])); sort(collect(keys(PAYLOAD)))',
                       payload={"old": old, "new": new})
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], ["new", "old"])
        self.assertEqual(Path(self.task_workspace, "e.jl").read_text(), "head\n" + new + "tail\n")
        r = self._turn("PAYLOAD === nothing", payload={"bad": 1})
        self.assertIs(r["data"], True, "a payload part that is not text is dropped, not bound")

    def test_display_does_not_corrupt_the_protocol(self):
        """display() wrote to the stdout captured at startup, which is the
        protocol pipe, and killed the session."""
        r = self._turn("display([1 2; 3 4]); 5")
        self.assertTrue(r["success"], r)
        self.assertIn("2×2 Matrix{Int64}", r["output"])
        self.assertEqual(self._turn("ans + 1")["data"], 6)

    def test_include_resolves_against_the_workspace(self):
        """include("m.jl") looked next to session_loop.jl."""
        r = self._turn('write("m.jl", "g(x) = 2x"); include("m.jl"); g(21)')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], 42)

    def test_edited_workspace_package_is_reloaded(self):
        """`using` a loaded package does nothing, so the kernel ran a
        workspace package's old code after the model edited it, and in-kernel
        tests checked code that no longer existed."""
        pkg = Path(self.task_workspace, "Wp")
        (pkg / "src").mkdir(parents=True)
        (pkg / "Project.toml").write_text('name = "Wp"\nuuid = "0f5c2a5e-9a44-4c3b-8f2e-6c1d8e7b9a01"\n')
        (pkg / "src" / "Wp.jl").write_text('module Wp\nexport f\n"f doc"\nf(x) = x + 1\ninclude("g.jl")\nend\n')
        (pkg / "src" / "g.jl").write_text("g(x) = 10x\n")
        r = self._turn('pushfirst!(LOAD_PATH, joinpath(pwd(), "Wp")); using Wp; (f(1), Wp.g(1))')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], [2, 10])

        # Edited in a turn of its own: reloaded when the next turn starts.
        r = self._turn('write("Wp/src/g.jl", "g(x) = 20x\\n"); 1')
        self.assertTrue(r["success"], r)
        r = self._turn("Wp.g(1)")
        self.assertEqual(r["data"], 20, r)
        self.assertIn("[reloaded Wp from the workspace: Wp/src/g.jl changed]", r["output"])
        self.assertNotIn("Replacing docs", r["output"])

        # Edited and then included in one call: include reloads first.
        Path(self.task_workspace, "t.jl").write_text("h_result = (f(1), Wp.h())\n")
        r = self._turn('write("Wp/src/Wp.jl", replace(read("Wp/src/Wp.jl", String), "x + 1" => "x + 2", '
                       '"include(\\"g.jl\\")" => "include(\\"g.jl\\")\\nh() = :new")); include("t.jl")')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], [3, "new"])

        # A syntax error keeps the old code and says so.
        r = self._turn('write("Wp/src/g.jl", "g(x) = (\\n"); 1')
        r = self._turn("Wp.g(1)")
        self.assertEqual(r["data"], 20, r)
        self.assertIn("reloading Wp failed, so it still runs the code from before the change to Wp/src/g.jl", r["output"])

    def test_neura_handle_cannot_reset_the_kernel(self):
        """Neura.reset_kernel_state() used to erase every binding silently."""
        self._turn("keep = 1")
        r = self._turn("Neura.reset_kernel_state()")
        self.assertFalse(r["success"])
        self.assertEqual(self._turn("keep")["data"], 1)

    def test_kernel_helpers_describe_the_session(self):
        r = self._turn("struct Pt; x::Int; end; v = zeros(10); Pt(3)")
        self.assertEqual(r["display"], "Pt(3)", "types print without the session module's internal name")
        r = self._turn("varinfo()")
        self.assertTrue(r["success"], r)
        self.assertIn("v", r["display"].split())
        self.assertNotIn("PAYLOAD", r["display"])
        r = self._turn("kernelinfo()")
        self.assertIn("time limit 20s", r["output"])
        self.assertIn("network    none", r["output"])

    def test_unassigned_results_are_not_retained(self):
        """Every call's value used to stay referenced from the receipt log."""
        for i in range(3):
            self.assertTrue(self._turn(f"zeros(UInt8, 200 * 2^20); {i}")["success"])
        r = self._turn("GC.gc(); GC.gc(); Base.gc_live_bytes() / 2^20")
        self.assertLess(r["data"], 200, "three unbound 200 MiB results were kept alive")

    def test_shell_syntax_in_backticks_points_to_bash(self):
        r = self._turn("run(`ls *.txt 2>&1`)")
        self.assertFalse(r["success"])
        self.assertIn('bash("...")', r["error"])

    def test_missing_package_says_there_is_no_network(self):
        r = self._turn("using NoSuchPackageAnywhere")
        self.assertFalse(r["success"])
        self.assertIn("no network", r["error"])
        self.assertIn("Loadable: the Julia standard library", r["error"])

    def test_pkg_add_read_only_failure_says_there_is_no_network(self):
        """A package install can fail after Julia reaches the read-only
        project/depot boundary instead of producing the usual resolver text.
        Keep that failure actionable without relabeling unrelated writes."""
        r = self._turn('error("Pkg.add failed: Read-only file system")')
        self.assertFalse(r["success"])
        self.assertIn("no network", r["error"])
        self.assertIn("Loadable: the Julia standard library", r["error"])

        unrelated = self._turn('error("write failed: Read-only file system")', request_id="2")
        self.assertFalse(unrelated["success"])
        self.assertNotIn("no network", unrelated["error"])

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

    def test_redirecting_stdout_inside_a_turn_restores_the_capture(self):
        """Base could not restore stdout to the turn's writer: the devnull
        idiom threw, and a redirect to a file kept fd 1 on that file, so the
        rest of the turn's output was lost."""
        r = self._turn('redirect_stdout(devnull) do; println("hidden"); run(`echo hidden`); end; '
                       'open("log.txt", "w") do io; redirect_stdout(io) do; println("logged"); end; end; '
                       'println("visible"); run(`echo child`); read("log.txt", String)')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["output"], "visible\nchild\n")
        self.assertIn("logged", r["display"])

    def test_what_each_call_printed_is_kept(self):
        """The host elides the middle of long results; the kernel keeps the
        whole text, failed calls included, under the call's number."""
        r1 = self._turn('for i in 1:3000; println("row ", i); end', request_id="1")
        r2 = self._turn('println("before the error"); error("boom")', request_id="2")
        self.assertEqual((r1["call"], r2["call"]), (1, 2))
        r = self._turn('(count("\\n", Neura.output(1)), Neura.output(2))', request_id="3")
        self.assertEqual(r["data"], [3000, "before the error\n"], r)
        r = self._turn("Neura.output(3)", request_id="4")
        self.assertFalse(r["success"])
        self.assertIn("call 3 printed nothing", r["error"])

    def test_testset_value_is_shown_as_its_counts(self):
        """A passing test run returned its DefaultTestSet, displayed as every
        nested testset down to each one's RNG state: 14,000 to 25,000
        characters per run, all of it elided by the host."""
        r = self._turn('using Test; @testset "outer" begin; @test 1 == 1; '
                       '@testset "inner" begin; @test true; @test_broken false; end; end')
        self.assertTrue(r["success"], r)
        self.assertRegex(r["display"], r'^Test\.DefaultTestSet "outer": 2 passed, 0 failed, 0 errored, 1 broken \(.*s\)$')
        r = self._turn("(ans.description, length(ans.results))")
        self.assertEqual(r["data"], ["outer", 1])

    def test_background_output_and_failures_reach_the_next_call(self):
        """Output a task or process wrote after its call ended, and a bound
        task's failure, reached nobody."""
        r = self._turn('t_err = @async (sleep(0.5); error("background boom")); '
                       '@async (sleep(0.5); println("printed after the call")); '
                       'run(pipeline(`bash -c "sleep 0.5; echo from a process"`; stdout=stdout); wait=false); :started')
        self.assertTrue(r["success"], r)
        time.sleep(2)
        r = self._turn("1")
        self.assertTrue(r["output"].startswith("[background output since the last call]\n"), r["output"])
        self.assertIn("printed after the call", r["output"])
        self.assertIn("from a process", r["output"])
        self.assertIn("[background: task `t_err` failed: background boom]", r["output"])
        r = self._turn("2")
        self.assertEqual(r["output"], "", "each event is reported once")

    def test_background_job_in_sh_does_not_hold_the_call(self):
        """`sh"job &"` handed the job the output pipe, and reading it to its
        end waited for the job until the call's time limit killed it."""
        r = self._turn('t = time(); r = sh"(sleep 2; echo late) & echo started"; (round(time() - t), r.stdout)')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], [0, "started\n"])
        time.sleep(3)
        r = self._turn("1")
        self.assertIn("[background output since the last call]\nlate\n", r["output"])

    def test_reported_background_output_does_not_accumulate_in_tmp(self):
        """The sandbox's /tmp is memory; a chatty background job grew it by
        4 GB a day because output stayed in the sink after it was reported."""
        r = self._turn('@async (sleep(0.5); for i in 1:3000; println(repeat("y", 1000)); end); :started')
        self.assertTrue(r["success"], r)
        time.sleep(2)
        r = self._turn('1')
        self.assertIn("[background output since the last call]", r["output"])
        r = self._turn('(filesize(joinpath(tempdir(), "neurajl-background-output.log")), '
                       'parse(Int, split(read(`du -sb /tmp`, String))[1]))')
        sink, tmp = r["data"]
        self.assertLess(sink, 100_000, r)
        self.assertLess(tmp, 1_500_000, r)

    def test_file_changed_since_a_call_used_it_is_reported(self):
        """A binding computed from a workspace file kept the old contents
        after the file changed outside the call, with nothing to say so."""
        r = self._turn('write("data.csv", "a\\n1\\n"); d = read("data.csv", String); write("h.jl", "h() = 1"); include("h.jl")')
        self.assertTrue(r["success"], r)
        # Changed by a call that does not name the files: reported once.
        r = self._turn('for f in readdir(); endswith(f, ".csv") || endswith(f, ".jl") || continue; '
                       'open(io -> write(io, "\\n"), f, "a"); end')
        self.assertEqual(r["output"], "", r)
        r = self._turn("1")
        self.assertIn("[changed on disk since the call that used it: data.csv (call 1), h.jl (call 1).", r["output"])
        self.assertEqual(self._turn("2")["output"], "")
        # A call that names the file it changes is not told about its own change.
        self._turn('write("data.csv", "a\\n2\\n")')
        self.assertEqual(self._turn("3")["output"], "")

    def test_each_reply_lists_the_bindings_and_the_call_that_set_them(self):
        """When the kernel dies the host can only say which bindings were
        lost if it was told what they were."""
        self._turn("x = [1, 2]; y = 3; f(z) = z")
        r = self._turn("x = [5]; nothing")
        self.assertEqual(r["bindings"], ["f (function, call 1)", "x (Vector{Int64}, call 2)", "y (Int64, call 1)"])

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

    def test_nothing_an_ephemeral_turn_starts_outlives_it(self):
        """The child has its own PID namespace; when it exits, bwrap's reaper
        (PID 1) exits and the kernel kills everything left in that namespace, however it was
        detached. Four escape shapes are started and seen alive inside the
        child, then none may remain on the host."""
        marker = "NJL" + uuid.uuid4().hex[:10]
        r = self._turn(_descendant_code(marker, _ESCAPE_ATTEMPTS + _COUNT_INSIDE), ephemeral=True)
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], 4, "an escape attempt never started, so this test would prove nothing")
        time.sleep(1.0)
        self.assertEqual(_host_processes_with(marker), [])

    def test_descendants_of_a_timed_out_ephemeral_child_die_with_it(self):
        marker = "NJL" + uuid.uuid4().hex[:10]
        code = _descendant_code(marker, _ESCAPE_ATTEMPTS + "sleep(600)")
        self.proc.stdin.write(json.dumps({"request_id": "1", "code": code, "ephemeral": True}) + "\n")
        self.proc.stdin.flush()
        seen = 0
        deadline = time.time() + 30
        while time.time() < deadline and seen < 4:
            seen = len(_host_processes_with(marker))
            time.sleep(0.2)
        self.assertEqual(seen, 4, "the escape attempts never all started")
        r = json.loads(self.proc.stdout.readline())
        self.assertIn("time limit", r["error"])
        time.sleep(1.0)
        self.assertEqual(_host_processes_with(marker), [])

    def test_persistent_kernel_descendants_do_persist_until_the_session_ends(self):
        """Control for the two tests above: the same scan does find a live
        descendant, and the persistent kernel keeps its own."""
        marker = "NJL" + uuid.uuid4().hex[:10]
        r = self._turn(_descendant_code(marker, "run(`bash -c $desc`; wait=false); " + _COUNT_INSIDE))
        self.assertEqual(r["data"], 1)
        self._turn("1", request_id="2")
        self.assertEqual(len(_host_processes_with(marker)), 1)
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        time.sleep(1.0)
        self.assertEqual(_host_processes_with(marker), [])

    def test_task_tools_reach_the_kernel_and_ephemeral_children_read_only(self):
        """A benchmark runner exposes the task image's tools (interpreter,
        bun, ...) to every contestant as one read-only directory; NP2's worker
        used to drop it, so a task's own runtime was unreachable."""
        tools = tempfile.mkdtemp(prefix="neurajl-task-tools-")
        Path(tools, "bin").mkdir()
        tool = Path(tools, "bin", "task-tool")
        tool.write_text("#!/bin/sh\necho task-tool-ran\n")
        tool.chmod(0o755)
        proc = subprocess.Popen(
            [sys.executable, CLI, "--project-dir", PROJECT_DIR, "--ceiling", "{}",
             "--workspace-dir", self.task_workspace, "--turn-timeout", "20"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, env={**os.environ, "NIRA_TASK_TOOLS": tools},
        )
        try:
            self.assertEqual(json.loads(proc.stdout.readline())["kind"], "HELLO")
            code = 'readchomp(`task-tool`), (try; touch(joinpath(ENV["PATH"][1:findfirst(\':\', ENV["PATH"])-1], "x")); "writable"; catch; "read-only"; end)'
            for i, ephemeral in enumerate((False, True)):
                proc.stdin.write(json.dumps({"request_id": str(i), "code": code, "ephemeral": ephemeral}) + "\n")
                proc.stdin.flush()
                r = json.loads(proc.stdout.readline())
                self.assertTrue(r["success"], r)
                self.assertEqual(r["data"], ["task-tool-ran", "read-only"], f"ephemeral={ephemeral}")
        finally:
            proc.stdin.close()
            proc.wait(timeout=60)
            proc.stdout.close()
            shutil.rmtree(tools, ignore_errors=True)

    def test_workspace_package_loads_ahead_of_the_kernels_copy(self):
        """The kernel's environment has OrderedCollections (DataFrames needs
        it). A model working on OrderedCollections appended the workspace to
        LOAD_PATH, and its whole test suite passed against the kernel's copy."""
        ws = tempfile.mkdtemp(prefix="neurajl-cli-pkg-")
        Path(ws, "src").mkdir()
        Path(ws, "Project.toml").write_text(
            'name = "OrderedCollections"\nuuid = "bac558e1-5e72-5ebc-8fee-abe8a469f55d"\nversion = "2.0.1"\n')
        Path(ws, "src", "OrderedCollections.jl").write_text("module OrderedCollections\nconst WORKSPACE_COPY = true\nend\n")
        proc = subprocess.Popen(
            [sys.executable, CLI, "--project-dir", PROJECT_DIR, "--ceiling", "{}",
             "--workspace-dir", ws, "--turn-timeout", "60"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        try:
            self.assertEqual(json.loads(proc.stdout.readline())["kind"], "HELLO")
            code = ('push!(LOAD_PATH, pwd()); using OrderedCollections; '
                    '(isdefined(OrderedCollections, :WORKSPACE_COPY), startswith(pathof(OrderedCollections), pwd()))')
            proc.stdin.write(json.dumps({"request_id": "1", "code": code}) + "\n")
            proc.stdin.flush()
            r = json.loads(proc.stdout.readline())
            self.assertEqual(r["data"], [True, True], r)
        finally:
            proc.stdin.close()
            proc.wait(timeout=60)
            proc.stdout.close()
            shutil.rmtree(ws, ignore_errors=True)

    def test_quote_that_ends_sh_early_is_explained(self):
        """A `"` inside sh"..." made the next word a string-macro suffix, and
        Julia reported only a MethodError for @sh_str."""
        r = self._turn('sh"printf %s \\"quoted\\""')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["output"], "quoted")
        r = self._turn('sh"echo "hello')
        self.assertFalse(r["success"])
        self.assertIn("a quote inside sh", r["error"])
        self.assertIn("`hello`", r["error"])
        self.assertIn("bash(PAYLOAD)", r["error"])

    def test_timeout_interrupts_waiting_work_and_keeps_the_kernel(self):
        """A timeout used to kill the kernel even when the call was only
        waiting. Processes an earlier call started keep running; processes the
        interrupted call started are stopped."""
        self._turn("keep = 99; bg = run(`sleep 300`; wait=false); nothing")
        r = self._turn('println("before"); run(`sleep 300`)')
        self.assertFalse(r["success"])
        self.assertIs(r.get("interrupted"), True)
        self.assertNotIn("session_dead", r)
        self.assertIn("before", r["output"])
        self.assertIn("every binding are intact", r["error"])
        r = self._turn('(keep, process_running(bg), strip(sh"pgrep -c -x sleep".stdout))')
        self.assertEqual(r["data"], [99, True, "1"])

    def test_finished_background_processes_are_reaped(self):
        """With julia as PID 1 an orphaned process that finished stayed a
        zombie, and `pgrep` kept reporting it as running."""
        r = self._turn('sh"(sleep 0.5 &); true"; sleep(2); strip(sh"ps -eo stat= | grep -c ^Z || true".stdout)')
        self.assertTrue(r["success"], r)
        self.assertEqual(r["data"], "0")

    def test_compute_that_never_yields_stops_the_kernel(self):
        r = self._turn("s = 0.0; i = 0; while true; s += sin(i); i += 1; end")
        self.assertFalse(r["success"])
        self.assertIs(r.get("session_dead"), True)
        self.assertIn("never yields", r["error"])

    def test_turn_that_swallows_the_interrupt_stops_the_kernel(self):
        r = self._turn("while true; try sleep(0.5) catch end; end")
        self.assertFalse(r["success"])
        self.assertIs(r.get("session_dead"), True)
        self.assertIn("kept running after being interrupted", r["error"])


if __name__ == "__main__":
    unittest.main()
