import json, os, subprocess, sys, time, tempfile, shutil
sys.path.insert(0, "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab/security")
from test_revival import Kernel
res = []
for mb in [1, 10, 50, 100, 120]:
    ws, st = tempfile.mkdtemp(), tempfile.mkdtemp()
    n = max(1, mb // 8); per = (mb * 2**20) // n // 8
    k = Kernel(ws, st, timeout=120)
    t = time.time(); k.turn(f"for i in 1:{n}; eval(:($(Symbol(\"a\", i)) = rand({per}))); end; 1"); build = time.time() - t
    t = time.time(); k.turn("1"); blocked = time.time() - t          # sent right after the reply: waits for the snapshot
    time.sleep(1)
    t = time.time(); k.turn("2"); idle = time.time() - t             # baseline latency once idle
    time.sleep(max(3, mb / 10))
    r = k.turn('using JSON; m = JSON.parsefile(ENV["NEURAJL_STATE_DIR"] * "/manifest.json"); (m["seconds"], m["bytes"], Sys.maxrss() / 2^20)')
    k.close()
    secs, byts, rss = json.loads(r["display"].replace("(", "[").replace(")", "]"))
    disk = sum(os.path.getsize(os.path.join(st, f)) for f in os.listdir(st))
    t = time.time(); k2 = Kernel(ws, st, timeout=300); r2 = k2.turn("length(a1)"); revive = time.time() - t; k2.close()
    ok = "restored exactly" in r2["output"] and "not revived" not in r2["output"]
    res.append(dict(target_mb=mb, bindings=n, snapshot_s=secs, saved_mb=round(byts / 2**20, 1), disk_mb=round(disk / 2**20, 1),
                    maxrss_mb=round(rss), next_call_right_after_s=round(blocked, 2), next_call_idle_s=round(idle, 2),
                    revival_first_call_s=round(revive, 1), all_restored=ok))
    print(json.dumps(res[-1]), flush=True)
    shutil.rmtree(ws, ignore_errors=True); shutil.rmtree(st, ignore_errors=True)
