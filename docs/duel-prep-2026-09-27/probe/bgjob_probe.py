"""A build longer than the 60 s call limit, run as a background job and collected later."""
import os, sys, tempfile, time, json
sys.path.insert(0, "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab")
from security.test_revival import Kernel
root = os.path.expanduser("~/.neurajl-runs/probe")
k = Kernel(tempfile.mkdtemp(prefix="bg-ws-", dir=root), tempfile.mkdtemp(prefix="bg-st-", dir=root), timeout=60)
t = time.time(); r = k.turn('job = @async sh"for i in 1 2 3 4 5 6 7; do sleep 10; echo step $i; done; echo built"')
print("start call", round(time.time() - t, 1), "s success", r["success"])
time.sleep(30); r = k.turn("istaskdone(job)"); print("at +30s done?", r["data"], "| output so far:", repr((r.get("output") or "")[:120]))
time.sleep(45); r = k.turn("res = fetch(job); (res.exitcode, split(strip(res.stdout), '\\n')[end])"); print("at +75s:", r["data"], r.get("error"))
k.close()
