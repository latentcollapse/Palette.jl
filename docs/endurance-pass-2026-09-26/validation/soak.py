"""Substrate soak: one supervised NeuraJL session for hours, no model. Every ~20s a realistic call;
the kernel is killed every KILL_EVERY seconds and must revive. Logs latency, RSS, /tmp, state and correctness."""
import json, os, random, shutil, signal, subprocess, sys, tempfile, time, pathlib
sys.path.insert(0, "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab/security")
from test_revival import Kernel
HOURS = float(sys.argv[1]); KILL_EVERY = float(sys.argv[2]); out = open(sys.argv[3], "a")
random.seed(7)
ws, st = tempfile.mkdtemp(prefix="soak-ws-"), tempfile.mkdtemp(prefix="soak-state-")
pkg = pathlib.Path(ws, "Soak", "src"); pkg.mkdir(parents=True)
pathlib.Path(ws, "Soak", "Project.toml").write_text('name = "Soak"\nuuid = "0f5c2a5e-9a44-4c3b-8f2e-6c1d8e7b9a0f"\n')
def write_pkg(v): (pkg / "Soak.jl").write_text(f"module Soak\nversion() = {v}\nscale(x) = {v} * x\nend\n")
write_pkg(1)
pathlib.Path(ws, "data.csv").write_text("a,b\n" + "".join(f"{i},{i*i}\n" for i in range(5000)))
os.environ["NEURAJL_JULIA_BIN"] = str(pathlib.Path.home() / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia")
k = Kernel(ws, st, timeout=60); t0 = time.time(); last_kill = t0; n = 0; version = 1; kills = 0; bad = []
def log(**kv): kv["t"] = round(time.time() - t0); out.write(json.dumps(kv) + "\n"); out.flush()
def kernel_pid():
    for p in os.listdir("/proc"):
        if not p.isdigit(): continue
        try:
            c = open(f"/proc/{p}/cmdline", "rb").read()
            if b"session_loop.jl" in c and not c.startswith(b"bwrap") and os.readlink(f"/proc/{p}/cwd") == ws: return int(p)
        except OSError: pass
k.turn('pushfirst!(LOAD_PATH, joinpath(pwd(), "Soak")); using Soak, CSV, DataFrames; total = 0; hist = Float64[]; nothing')
while time.time() - t0 < HOURS * 3600:
    n += 1; kind = n % 6
    if kind == 0:
        version += 1; write_pkg(version); code, want = "Soak.version()", version
    elif kind == 1:
        code, want = 'd = CSV.read("data.csv", DataFrame); total += sum(d.a); length(d.a)', 5000
    elif kind == 2:
        code, want = 'job = @async (sleep(1); println("tick ", time())); x = rand(10^6); push!(hist, sum(x) / 10^6); length(hist) > 0', True
    elif kind == 3:
        code, want = 'r = sh"ls | wc -l"; r.exitcode', 0
    elif kind == 4:
        code, want = 'big = [rand(1000) for _ in 1:200]; big = nothing; GC.gc(false); 1', 1
    else:
        code, want = "Soak.scale(2)", 2 * version
    s = time.time(); r = k.turn(code); lat = time.time() - s
    ok = r.get("success") and r.get("data") == want
    if not ok and not r.get("session_dead"): bad.append((n, code, str(r.get("error"))[:200], r.get("data"))); log(event="mismatch", call=n, code=code, got=r.get("data"), want=want, err=str(r.get("error"))[:300])
    if r.get("session_dead") or "the kernel stopped" in str(r.get("error")):
        k.close(); k = Kernel(ws, st, timeout=60); r2 = k.turn("(Soak.version(), total > 0)"); log(event="revived", report=r2["output"][:600], data=r2.get("data"))
    if n % 30 == 0:
        pid = kernel_pid(); rss = tmpb = None
        if pid:
            rss = int([l for l in open(f"/proc/{pid}/status") if l.startswith("VmRSS")][0].split()[1]) // 1024
            tmpb = int(subprocess.run(["du", "-sbx", f"/proc/{pid}/root/tmp"], capture_output=True, text=True).stdout.split()[0])
        man = json.loads(pathlib.Path(st, "manifest.json").read_text()) if pathlib.Path(st, "manifest.json").exists() else {}
        log(event="sample", calls=n, lat_s=round(lat, 3), rss_mb=rss, sandbox_tmp=tmpb, state_bytes=sum(f.stat().st_size for f in pathlib.Path(st).iterdir()),
            snapshot_s=man.get("seconds"), kills=kills, mismatches=len(bad))
    if time.time() - last_kill > KILL_EVERY:
        pid = kernel_pid()
        if pid: os.kill(pid, signal.SIGKILL); kills += 1; last_kill = time.time(); log(event="kill", call=n)
    time.sleep(20)
k.close(); log(event="end", calls=n, kills=kills, mismatches=len(bad))
