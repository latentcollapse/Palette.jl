import os, sys, tempfile, pathlib, json
sys.path.insert(0, os.path.expanduser("~/rnd/neurajl-lab-wt"))
from security.test_revival import Kernel
ws = tempfile.mkdtemp(prefix="exp-ws-"); st = tempfile.mkdtemp(prefix="exp-st-")
p = pathlib.Path(ws, "json5"); (p / "src").mkdir(parents=True)
(p / "Project.toml").write_text('name = "JSON5Lite"\nuuid = "0f9b8a1c-3d2e-4b5f-8a7c-1e2d3c4b5a69"\nversion = "0.1.0"\n')
(p / "src" / "JSON5Lite.jl").write_text("module JSON5Lite\nparse(s) = length(s)\nend\n")
k = Kernel(ws, st)
for code in ['1 + 1', 'using JSON5Lite; JSON5Lite.parse("abc")', 'include("json5/src/JSON5Lite.jl"); using JSON5Lite; JSON5Lite.parse("ab")',
             'LOAD_PATH']:
    r = k.turn(code); print(code[:60], "=>", r["success"], (r.get("error") or r.get("display") or "")[:200].replace("\n", " | "))
k.close()
out = Kernel(ws, st); r = out.turn('JSON5Lite.parse("x")'); print("revived =>", r["success"], r["output"][r["output"].find("not revived"):][:300].replace("\n"," | ")); out.close()
