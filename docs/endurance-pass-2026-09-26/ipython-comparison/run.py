"""Drive prime-agent-runtime's own IPython snapshot/restore (repl.py) across two processes."""
import json, os, sys, types
sys.path.insert(0, "/mnt/d/Code Projects/Project NIRA/The Battleground/NIRA-Prime-NeuraJL/prime-agent-runtime/src")
from rlm import repl

mode, state, code = sys.argv[1], sys.argv[2], sys.argv[3]
os.chdir(sys.argv[4])
main = types.ModuleType("__main__")
sys.modules["__main__"] = main
ns = main.__dict__
if mode == "save":
    exec(compile(code, "<cell>", "exec"), ns)
    caps = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
    r = repl._snapshot_state(ns, f"{state}/kernel-state.dill", f"{state}/kernel-state.json",
                             caps.get("max", 256 * 2**20), caps.get("var", 16 * 2**20), False)
    print(json.dumps({"saved": r.get("saved"), "skipped": r.get("skipped"), "error": r.get("error")}))
else:
    r = repl._restore_state(ns, f"{state}/kernel-state.dill")
    out = {"restored": r.get("restored"), "failed": r.get("failed"), "error": r.get("error")}
    try:
        out["check"] = repr(eval(code, ns))
    except Exception as e:
        out["check"] = f"{type(e).__name__}: {e}"
    print(json.dumps(out))
