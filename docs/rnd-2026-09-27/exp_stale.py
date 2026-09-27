import json, os, sys, tempfile, time, pathlib
sys.path.insert(0, os.getcwd())
from security.test_revival import Kernel
ws = tempfile.mkdtemp(prefix="stale-ws-"); st = tempfile.mkdtemp(prefix="stale-st-")
k = Kernel(ws, st, timeout=120)
def saved():
    p = pathlib.Path(st, "manifest.json"); return json.loads(p.read_text())["call"] if p.exists() else None
r = k.turn("using Random; Random.seed!(1); for i in 1:40; @eval $(Symbol(:b, i)) = [randstring(24) for _ in 1:60_000]; end")
print("call", r["call"], "success", r["success"], "saved", saved())
for _ in range(7):
    t = time.time(); r = k.turn("1 + 1"); print("call", r["call"], f"{time.time()-t:.2f}s", "saved", saved())
time.sleep(12); print("after idle saved", saved(), os.listdir(st)[:5])
k.close()
