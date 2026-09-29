"""Duel-prep audit: services, heisenbug tooling, output at scale, big repos, new pieces' edges."""
import json, os, sys, tempfile, time, pathlib, subprocess
REPO = os.environ["NEURAJL_REPO"]; sys.path.insert(0, REPO)
from security.test_revival import CLI, PROJECT_DIR
root = pathlib.Path.home() / ".neurajl-runs/probe"
class K:
    def __init__(self, ws, st, timeout=60, network=True):
        args = [sys.executable, CLI, "--project-dir", PROJECT_DIR, "--ceiling", "{}", "--workspace-dir", ws,
                "--turn-timeout", str(timeout), "--state-dir", st] + (["--network"] if network else [])
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.hello = json.loads(self.p.stdout.readline()); self.n = 0
    def turn(self, code, **extra):
        self.n += 1; t = time.time()
        self.p.stdin.write(json.dumps({"request_id": str(self.n), "code": code, **extra}) + "\n"); self.p.stdin.flush()
        r = json.loads(self.p.stdout.readline()); r["_s"] = round(time.time() - t, 2); return r
    def close(self): self.p.stdin.close(); self.p.wait(timeout=60)
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  | {detail}" if detail else ""), flush=True)
ws = tempfile.mkdtemp(prefix="audit-ws-", dir=root); st = tempfile.mkdtemp(prefix="audit-st-", dir=root)
k = K(ws, st)
# 1. a service on loopback, reachable from the kernel; a kill; restart
r = k.turn('srv = run(pipeline(`python3 -m http.server 18766 --bind 127.0.0.1`; stdout=devnull, stderr=devnull); wait=false); sleep(1.5); strip(sh"curl -s -o /dev/null -w \'%{http_code}\' http://127.0.0.1:18766/".stdout)')
check("1a loopback service answers", r.get("data") == "200", repr(r.get("data")) + " " + (r.get("error") or "")[:120])
r = k.turn("1")
check("1b jobs line names the server", "[background jobs: running: `python3 -m http.server" in r["output"], r["output"][:160])
k.turn("x_before_kill = 7")
import signal
for pid in os.listdir("/proc"):
    try:
        if pid.isdigit() and b"session_loop.jl" in open(f"/proc/{pid}/cmdline", "rb").read() and os.readlink(f"/proc/{pid}/cwd") == ws:
            os.kill(int(pid), signal.SIGKILL); print("killed kernel", pid)
    except OSError: pass
time.sleep(1)
k.close(); k = K(ws, st)
r = k.turn("x_before_kill")
check("1c revival names the stopped server", "Background processes stopped with the previous kernel: `python3 -m http.server" in r["output"], r["output"][:300])
r = k.turn('srv = run(pipeline(`python3 -m http.server 18766 --bind 127.0.0.1`; stdout=devnull, stderr=devnull); wait=false); sleep(1.5); strip(sh"curl -s -o /dev/null -w \'%{http_code}\' http://127.0.0.1:18766/".stdout)')
check("1d the port is free again after the kernel died", r.get("data") == "200", repr(r.get("data")) + " " + (r.get("error") or "")[:160])
k.turn("kill(srv)")
# 2. heisenbug tooling: a flaky command run many times, in the call and in the background
k.turn('write("flaky.sh", PAYLOAD); chmod("flaky.sh", 0o755)', payload="#!/bin/bash\n[ $((RANDOM % 7)) -ne 0 ]\n")
r = k.turn('fails = count(i -> !success(`./flaky.sh`), 1:300); (fails > 0, fails < 300)')
check("2a 300 runs inside one call", r.get("data") == [True, True] and r["_s"] < 60, f"{r.get('data')} in {r['_s']}s")
r = k.turn('stress = @async [success(`./flaky.sh`) for _ in 1:3000]; 1')
time.sleep(25)
r = k.turn('istaskdone(stress) ? count(!, fetch(stress)) : -1')
check("2b 3000 runs as a background job, collected later", isinstance(r.get("data"), int) and r["data"] > 0, repr(r.get("data")))
r = k.turn('hog = run(`sleep 1000`; wait=false); sleep(0.5); kill(hog); sleep(0.5); process_exited(hog)')
check("2c a runaway background process can be stopped", r.get("data") is True, repr(r.get("data")))
r = k.turn('spin = @async (while true; sleep(0.1); end); sleep(0.3); schedule(spin, InterruptException(); error=true); sleep(0.3); istaskdone(spin)')
check("2d a runaway background task can be stopped", r.get("data") is True, repr(r.get("data")))
# 3. output at scale
r = k.turn('bash(PAYLOAD); nothing', payload='for i in $(seq 1 400); do echo "   Compiling crate$i v0.1.0"; done\nprintf "error[E0308]: mismatched types\\n --> src/lib.rs:12:5\\n"\nfor i in $(seq 1 400); do echo "note: line $i"; done\n')
check("3a a long build log opens with its digest", r["output"].startswith("[digest of") and "src/lib.rs:12:5  error[E0308]" in r["output"][:300], r["output"][:200])
r = k.turn('bash("printf \'\\\\033[31mRED\\\\033[0m and \\\\xff\\\\xfe bytes\\\\n\'"); nothing')
check("3b ANSI stripped, invalid UTF-8 survives the protocol", r["success"] and "\x1b" not in r["output"] and "RED and" in r["output"], repr(r["output"][:120]))
# 4. a big repo
big = pathlib.Path(ws, "big"); 
for d in range(200):
    p = big / f"mod{d}"; p.mkdir(parents=True, exist_ok=True)
    for f in range(100): (p / f"f{f}.rs").write_text(f"pub fn f{f}() {{}}\n")
subprocess.run(["git", "init", "-q", str(ws)]); subprocess.run(["git", "-C", str(ws), "add", "-A"]); subprocess.run(["git", "-C", str(ws), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "big"])
r = k.turn("1 + 1", map=True)
check("4a map of a 20k-file repo", r["output"].startswith("[workspace map] 200") and r["_s"] < 5, f"{r['_s']}s " + r["output"][:120])
times = []
for _ in range(5):
    times.append(k.turn('read("big/mod3/f7.rs", String); 1')["_s"])
check("4b per-call cost with a 20k-file repo", max(times) < 1.0, f"{times}")
r = k.turn('length(readlines(`rg -l "pub fn f7" big`))')
check("4c rg across the repo", r.get("data") == 2200, repr(r.get("data")) + " (f7 and f70-f79 in 200 dirs)")
# 5. edges of the new pieces
r = k.turn('(sort(collect(keys(PAYLOAD))), length(PAYLOAD["big"]), PAYLOAD["q"])', payload={"big": "x" * 1_000_000, "q": '"""$x\\n"""', "ünïcode key": "ok"})
check("5a named payload: 1 MB text, quotes, a unicode key", r.get("data") == [["big", "q", "ünïcode key"], 1000000, '"""$x\\n"""'], repr(r.get("data"))[:160])
r = k.turn('r = bash(PAYLOAD); (r.exitcode, strip(r.stdout))', payload="set -e\necho one\nfalse\necho never\n")
check("5b bash(PAYLOAD) stops at set -e and reports the exit code", r.get("data") == [1, "one"], repr(r.get("data")))
k.close()
