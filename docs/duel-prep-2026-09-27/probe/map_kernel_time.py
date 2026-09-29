import os, sys, json, time, subprocess, tempfile, pathlib
REPO = os.environ["NEURAJL_REPO"]; sys.path.insert(0, REPO)
from security.test_revival import CLI, PROJECT_DIR
ws = sorted(pathlib.Path.home().glob(".neurajl-runs/probe/audit-ws-*"), key=os.path.getmtime)[-1]
st = tempfile.mkdtemp(dir=pathlib.Path.home() / ".neurajl-runs/probe", prefix="mt-st-")
p = subprocess.Popen([sys.executable, CLI, "--project-dir", PROJECT_DIR, "--ceiling", "{}", "--workspace-dir", str(ws), "--turn-timeout", "60"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
json.loads(p.stdout.readline())
for i, (code, m) in enumerate([("1", False), ("1", True), ("1", True), ("1", False), ("@elapsed Neura.workspace_map()", False)]):
    t = time.time(); p.stdin.write(json.dumps({"request_id": str(i), "code": code, "map": m}) + "\n"); p.stdin.flush()
    r = json.loads(p.stdout.readline()); print(f"map={m}: {time.time()-t:.2f}s", r.get("data") if code != "1" else "")
p.stdin.close(); p.wait()
