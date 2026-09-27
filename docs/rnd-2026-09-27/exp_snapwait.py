"""How long does a call wait when it arrives while the kernel is saving a large state?"""
import json, os, sys, tempfile, time, pathlib
sys.path.insert(0, os.getcwd())
from security.test_revival import Kernel
ws = tempfile.mkdtemp(prefix="snapw-ws-"); st = tempfile.mkdtemp(prefix="snapw-st-")
k = Kernel(ws, st, timeout=120)
k.turn("using Random; Random.seed!(1)")
t = time.time(); r = k.turn("for i in 1:40; @eval $(Symbol(:b, i)) = [randstring(24) for _ in 1:60_000]; end; :built"); build = time.time() - t
t = time.time(); r2 = k.turn("1 + 1"); waited = time.time() - t
time.sleep(1)
k.turn("2 + 2")          # arrives while call 3's snapshot may be running, too
time.sleep(60)
m = json.loads(pathlib.Path(st, "manifest.json").read_text())
print(json.dumps({"build_s": round(build, 2), "next_call_s": round(waited, 2), "snapshot_call": m["call"], "snapshot_s": m["seconds"], "snapshot_mb": round(m["bytes"] / 1e6, 1)}))
k.close()
