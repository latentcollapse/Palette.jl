#!/usr/bin/env python3
"""
Real Jupyter-wire-protocol proof of Phase 1's central claim, driving an
actual IJulia kernel process via ZMQ execute_request messages -- not a
direct in-process function call. Verified working 2026-09-22: a real
IJulia kernel process, real ZMQ connection, two separate execute_request
messages (x = 41, then x + 1), correct 42 back over the wire, plus
OperatorSurface itself loading and persisting state correctly when run
inside a real kernel (not just a plain `julia` process).

Setup (one-time):

  1. A Julia environment with both this package and IJulia:
       julia --project=<env-dir> -e '
         using Pkg
         Pkg.develop(path="/path/to/OperatorSurface.jl")
         Pkg.add("IJulia")'

  2. A kernelspec pointing at that environment, installed into an isolated
     Jupyter data dir (so this doesn't touch any real Jupyter install):
       JUPYTER_DATA_DIR=<jdata-dir> julia --project=<env-dir> -e '
         using IJulia
         IJulia.installkernel("OperatorSurfaceTest", "--project=<env-dir>")'

  3. A Python venv with jupyter_client (this script needs nothing else):
       python3 -m venv <venv-dir>
       <venv-dir>/bin/pip install jupyter_client

Run:
  JUPYTER_DATA_DIR=<jdata-dir> JUPYTER_PATH=<jdata-dir> \\
    <venv-dir>/bin/python scripts/real_ijulia_proof.py

If the kernelspec's display name differs from "OperatorSurfaceTest 1.12",
update KERNEL_NAME below to match the actual installed kernel directory
name (check `<jdata-dir>/kernels/`) -- IJulia.installkernel appends the
Julia minor version, e.g. "operatorsurfacetest-1.12".
"""
import sys
from jupyter_client.manager import KernelManager

KERNEL_NAME = "operatorsurfacetest-1.12"

def run_cell(kc, code, timeout=60):
    msg_id = kc.execute(code)
    outputs = []
    status = None
    while True:
        msg = kc.get_iopub_msg(timeout=timeout)
        if msg["parent_header"].get("msg_id") != msg_id:
            continue
        msg_type = msg["msg_type"]
        if msg_type == "execute_result":
            outputs.append(("execute_result", msg["content"]["data"].get("text/plain")))
        elif msg_type == "stream":
            outputs.append(("stream", msg["content"]["text"]))
        elif msg_type == "error":
            outputs.append(("error", "\n".join(msg["content"]["traceback"])))
        elif msg_type == "status" and msg["content"]["execution_state"] == "idle":
            status = "idle"
            break
    reply = kc.get_shell_msg(timeout=timeout)
    ok = reply["content"]["status"] == "ok"
    return ok, outputs

def main():
    km = KernelManager(kernel_name=KERNEL_NAME)
    print(f"[real-ijulia-proof] starting real IJulia kernel ({KERNEL_NAME})...")
    km.start_kernel()
    kc = km.client()
    kc.start_channels()
    kc.wait_for_ready(timeout=120)
    print("[real-ijulia-proof] kernel ready, connection over real ZMQ/Jupyter wire protocol")

    results = {}

    ok, out = run_cell(kc, "x = 41")
    print(f"[req 1] x = 41  -> ok={ok} out={out}")
    results["req1"] = ok

    ok, out = run_cell(kc, "x + 1")
    print(f"[req 2] x + 1   -> ok={ok} out={out}")
    got_42 = any(v == "42" for (t, v) in out if t == "execute_result")
    results["req2_is_42"] = got_42
    print(f"  Phase 1 core claim (x=41 then x+1==42, over the real wire protocol): {'PASS' if got_42 else 'FAIL'}")

    ok, out = run_cell(kc, 'using OperatorSurface; OperatorSurface.reset_kernel_state(); OperatorSurface.execute(OperatorSurface.ExecuteCode("y = 10"))')
    print(f"[req 3] load OperatorSurface, execute via it -> ok={ok}")
    results["req3_package_loads_in_real_kernel"] = ok

    ok, out = run_cell(kc, 'OperatorSurface.execute(OperatorSurface.ExecuteCode("y + 5")).result.data')
    got_15 = any(v == "15" for (t, v) in out if t == "execute_result")
    print(f"[req 4] OperatorSurface's own persistence, inside a real kernel -> {out} -> {'PASS' if got_15 else 'FAIL'}")
    results["req4_operatorsurface_persistence_in_real_kernel"] = got_15

    kc.stop_channels()
    km.shutdown_kernel(now=True)

    print("\n=== SUMMARY ===")
    all_pass = True
    for k, v in results.items():
        print(f"{k}: {'PASS' if v else 'FAIL'}")
        all_pass = all_pass and v
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    main()
