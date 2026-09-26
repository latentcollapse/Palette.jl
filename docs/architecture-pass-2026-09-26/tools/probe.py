#!/usr/bin/env python3
"""Drive session_cli.py the way the NIRA-Prime host does, and time each turn.

Usage: probe.py SCRIPT.json [--timeout N]
SCRIPT.json is a list of turns: {"code": ..., "ephemeral"?: bool, "payload"?: str, "label"?: str}
"""
import json, os, subprocess, sys, time, tempfile, argparse
from pathlib import Path

LAB = "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab"
ap = argparse.ArgumentParser()
ap.add_argument("script")
ap.add_argument("--timeout", type=float, default=60)
ap.add_argument("--workspace")
ap.add_argument("--full", action="store_true")
a = ap.parse_args()
turns = json.load(open(a.script))
ws = a.workspace or tempfile.mkdtemp(prefix="njl-probe-")
env = dict(os.environ, JULIA_DEPOT_PATH=str(Path.home() / ".neurajl-trial/depot"))
t0 = time.time()
p = subprocess.Popen([sys.executable, "-u", f"{LAB}/security/session_cli.py", "--project-dir", str(Path.home() / ".neurajl-trial/project"),
                      "--ceiling", "{}", "--workspace-dir", ws, "--turn-timeout", str(a.timeout)],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1)
hello = p.stdout.readline()
if os.environ.get("PROBE_DELAY"): time.sleep(float(os.environ["PROBE_DELAY"]))
print(f"HELLO after {time.time()-t0:.2f}s: {hello.strip()[:160]}", flush=True)
for i, t in enumerate(turns, 1):
    req = {"request_id": str(i), "code": t["code"]}
    for k in ("ephemeral", "payload"):
        if k in t: req[k] = t[k]
    if t.get("pause"): time.sleep(t["pause"])
    s = time.time()
    p.stdin.write(json.dumps(req) + "\n"); p.stdin.flush()
    line = p.stdout.readline()
    dt = time.time() - s
    if not line:
        print(f"--- [{i}] {t.get('label','')} ({dt:.2f}s) BRIDGE EXITED; stderr: {p.stderr.read()[-2000:]}")
        break
    r = json.loads(line)
    lim = None if a.full else 1500
    out = (r.get("output") or "")
    print(f"--- [{i}] {t.get('label','')} ({dt:.2f}s) success={r.get('success')} dead={r.get('session_dead', False)}")
    if out: print("  output:", out[:lim].replace("\n", "\n          "))
    if r.get("display") is not None: print("  display:", str(r.get("display"))[:lim].replace("\n", "\n           "))
    if r.get("error"): print("  error:", str(r.get("error"))[:lim].replace("\n", "\n         "))
    if r.get("session_dead"): break
p.stdin.close()
try: p.wait(timeout=30)
except subprocess.TimeoutExpired: p.kill()
print(f"total {time.time()-t0:.1f}s; workspace {ws}")
