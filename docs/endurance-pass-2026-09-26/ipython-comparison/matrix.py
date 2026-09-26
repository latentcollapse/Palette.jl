import json, os, subprocess, tempfile, pathlib
P = "./ipyvenv/bin/python"
def run(save, check, before_load=None, caps=None, setup=None):
    ws, st = tempfile.mkdtemp(), tempfile.mkdtemp()
    if setup: setup(ws)
    a = subprocess.run([P, "ipycmp/run.py", "save", st, save, ws] + ([json.dumps(caps)] if caps else []), capture_output=True, text=True, timeout=120)
    if before_load: before_load(ws, st)
    b = subprocess.run([P, "ipycmp/run.py", "load", st, check, ws], capture_output=True, text=True, timeout=120)
    try: sa, sb = json.loads(a.stdout.strip().splitlines()[-1]), json.loads(b.stdout.strip().splitlines()[-1])
    except Exception: return {"save_err": a.stderr[-300:], "load_err": b.stderr[-300:]}
    return {"skipped": sa["skipped"], "restored": sb["restored"], "failed": sb["failed"], "error": sb["error"], "check": sb["check"]}
def csv(ws): pathlib.Path(ws, "data.csv").write_text("a\n1\n2\n")
def lib(ws): pathlib.Path(ws, "lib.py").write_text("def helper(x):\n    return 10*x\n")
cases = {
 "plain data": run("n=42; s='hi'; d={'a':[1,2]}; t=(1,'x'); st={1,2}", "(n, s, d, t, st)"),
 "DataFrame": run("import pandas as pd; df=pd.DataFrame({'a':[1,2,3]})", "(df.shape, list(df.a))"),
 "aliasing across names": run("a=[1,2]; b=a; h={'v':a}", "(a is b, h['v'] is a)"),
 "cycle within one value": run("a=[1]; a.append(a)", "a[1] is a"),
 "class identity": run("class P:\n    pass\np=P()", "(isinstance(p, P), type(p) is P)"),
 "function / method": run("def f(x): return x+1", "f(1)"),
 "closure / lambda": run("K=3; g=lambda x: x+K", "g(1)"),
 "import": run("import json", "json.dumps([1])"),
 "data from a file that changed": run("import csv; rows=list(csv.reader(open('data.csv')))", "rows", setup=csv,
       before_load=lambda ws, st: pathlib.Path(ws, "data.csv").write_text("a\n10\n20\n")),
 "function from a module file that changed": run("import sys; sys.path.insert(0, '.'); from lib import helper", "helper(1)", setup=lib,
       before_load=lambda ws, st: pathlib.Path(ws, "lib.py").write_text("def helper(x):\n    return 20*x\n")),
 "open file": run("fh=open('f.txt','w')", "(fh.closed, fh.name)"),
 "thread": run("import threading; th=threading.Thread(target=lambda: None)", "th"),
 "generator": run("gen=(i for i in range(3))", "list(gen)"),
 "Python version tampered": run("n=1", "n", before_load=lambda ws, st: pathlib.Path(st, "kernel-state.json").write_text(
       json.dumps({**json.loads(pathlib.Path(st, "kernel-state.json").read_text()), "pythonVersion": "2.7.0"}))),
 "payload corrupted": run("a=[1,2]; c=3", "(c,)", before_load=lambda ws, st: (lambda p: p.write_bytes(p.read_bytes()[:-5] + b"xxxxx"))(pathlib.Path(st, "kernel-state.dill"))),
 "per-variable size cap": run("import array; big=array.array('d', [0.0]*200000); small=1", "small", caps={"max": 10**7, "var": 10**6}),
}
print(json.dumps(cases, indent=1))
