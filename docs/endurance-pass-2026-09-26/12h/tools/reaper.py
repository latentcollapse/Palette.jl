"""Live-run stand-in for NP2 425c61161 (neurajl idle stop): SIGTERM a session_cli whose
state dir has not been written for IDLE seconds. session_cli tears its sandbox down on
SIGTERM, which is what the tool's dispose does; the next call to that session revives."""
import json, os, pathlib, signal, sys, time
root = pathlib.Path(sys.argv[1]); log = pathlib.Path(sys.argv[2]); sup = int(sys.argv[3]); IDLE = 20 * 60
done = set()
def newest(d):
    ts = [p.stat().st_mtime for p in d.rglob("*") if p.is_file()]
    return max(ts) if ts else None
while os.path.exists(f"/proc/{sup}"):
    for p in os.listdir("/proc"):
        if not p.isdigit() or int(p) in done: continue
        try: args = open(f"/proc/{p}/cmdline", "rb").read().split(b"\0")
        except OSError: continue
        if not any(a.endswith(b"session_cli.py") for a in args) or b"--state-dir" not in args: continue
        sd = pathlib.Path(args[args.index(b"--state-dir") + 1].decode())
        if root not in sd.parents: continue
        started = os.stat(f"/proc/{p}").st_mtime
        last = max(filter(None, [newest(sd), started]))
        if time.time() - last > IDLE:
            os.kill(int(p), signal.SIGTERM); done.add(int(p))
            with open(log, "a") as f: f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "pid": int(p), "session": sd.name, "idle_min": round((time.time() - last) / 60, 1)}) + "\n")
    time.sleep(60)
