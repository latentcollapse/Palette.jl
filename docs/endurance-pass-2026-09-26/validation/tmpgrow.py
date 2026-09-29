import json, sys, time, tempfile, shutil
sys.path.insert(0, "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab/security")
from test_revival import Kernel
ws, st = tempfile.mkdtemp(), tempfile.mkdtemp()
k = Kernel(ws, st, timeout=60)
# A chatty background server (50 KB/s to stdout) and a Julia task logging, as a long run might start.
k.turn('srv = run(pipeline(`bash -c "while true; do head -c 5000 /dev/zero | tr \\"\\\\0\\" x; echo; sleep 0.1; done"`; stdout=stdout); wait=false); '
       'lg = @async while true; println("tick ", time()); sleep(0.05); end; :started')
probe = 'm = parse(Int, split(read(`du -sb /tmp`, String))[1]); s = filesize(joinpath(tempdir(), "neurajl-background-output.log")); (m, s)'
t0 = time.time()
for i in range(7):
    time.sleep(10)
    r = k.turn(probe)
    print(f"t={time.time()-t0:5.0f}s tmp={json.loads(r['display'].replace('(','[').replace(')',']'))} shown_chars={len(r['output'])}", flush=True)
k.close(); shutil.rmtree(ws); shutil.rmtree(st)
