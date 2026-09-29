"""What a model can reach from inside the NeuraJL sandbox: toolchains, HOME, network, shell ergonomics."""
import os, sys, tempfile, json
sys.path.insert(0, "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab")
from security.test_revival import Kernel
ws = tempfile.mkdtemp(prefix="probe-ws-", dir=os.path.expanduser("~/.neurajl-runs/probe")); st = tempfile.mkdtemp(prefix="probe-st-", dir=os.path.expanduser("~/.neurajl-runs/probe"))
k = Kernel(ws, st, timeout=60)
probes = [
 ('toolchains', 'r = sh"for t in cargo rustc node npm tsc ocaml dune opam sqlite3 psql make gcc git python3 go; do printf \'%s=%s\\n\' $t \\"$(command -v $t || echo MISSING)\\"; done"; nothing'),
 ('env', 'r = sh"echo HOME=$HOME; echo PATH=$PATH; id -un 2>&1; ls -d ~/.cargo ~/.rustup 2>&1"; nothing'),
 ('versions', 'r = sh"cargo --version 2>&1; node --version 2>&1; git --version"; nothing'),
 ('network', 'r = sh"timeout 5 curl -sS -o /dev/null -w %{http_code} https://example.com 2>&1 || echo NO-NETWORK"; nothing'),
 ('quotes in sh', 'r = sh"echo \\"double\\" \'single\' $((1+2)) && printf \'%s\\n\' a b | wc -l"; nothing'),
 ('heredoc', 'r = sh"""python3 - <<\'PY\'\nprint("heredoc ok", "quotes \\" fine")\nPY"""; nothing'),
 ('pipe exit', 'r = sh"false | true; echo pipestatus=${PIPESTATUS[0]}"; nothing'),
 ('git in ws', 'r = sh"git init -q . && git -c user.email=a@b -c user.name=a commit -q --allow-empty -m x && git log --oneline | wc -l"; nothing'),
]
for name, code in probes:
    r = k.turn(code)
    print(f"== {name}: success={r['success']}")
    print((r.get("output") or "").strip()[:600] or r.get("error", "")[:400])
k.close()
