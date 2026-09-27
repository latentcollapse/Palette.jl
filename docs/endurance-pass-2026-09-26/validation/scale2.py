import json, sys, time, tempfile, shutil
sys.path.insert(0, "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab/security")
from test_revival import Kernel
ws, st = tempfile.mkdtemp(), tempfile.mkdtemp()
k = Kernel(ws, st, timeout=120)
k.turn("for i in 1:15; eval(:($(Symbol(\"a\", i)) = rand(1048576))); end; 1"); k.turn("1"); time.sleep(4)
for i in range(4):
    k.turn("a1[1] += 1.0; 1"); t = time.time(); k.turn("1"); print("steady next-call-right-after at 120MB:", round(time.time() - t, 2)); time.sleep(3)
for i in range(3):
    t = time.time(); k.turn("1"); print("idle call:", round(time.time() - t, 3)); time.sleep(0.2)
k.close(); shutil.rmtree(ws); shutil.rmtree(st)
