"""One Luna pilot on the deployed NeuraJL build (lab main, trial project/depot), direct OpenAI, run dir on NVMe.

python3 pilot.py <label> [--prompt FILE] [--scenario DIR] [--port NAME] [--minutes N] [--env K=V ...]
"""
import argparse, json, os, pathlib, shutil, subprocess, sys, tempfile, time
H = pathlib.Path.home(); HN = H / ".neurajl-runs/harness/njl"
NP2 = "/mnt/d/Code Projects/Project NIRA/The Battleground/NIRA-Prime-NeuraJL"
LAB = "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab"
JULIA = str(H / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia")
ap = argparse.ArgumentParser(); ap.add_argument("label"); ap.add_argument("--scenario", default=str(HN / "scenarios/s12-endurance-12h"))
ap.add_argument("--prompt", default="prompt.txt"); ap.add_argument("--port", default=""); ap.add_argument("--minutes", type=int, default=30)
ap.add_argument("--env", nargs="*", default=[]); a = ap.parse_args()
E = pathlib.Path(a.scenario)
run = H / ".neurajl-runs/pilots" / a.label; shutil.rmtree(run, ignore_errors=True)
for d in ("agent", "rlm", "home", "state"): (run / d).mkdir(parents=True)
ws = run / "workspace"; shutil.copytree(E / "fixture", ws)
shutil.copy(E / a.prompt, run / "prompt.txt")
oak = run / "oak"; shutil.copy(H / ".config/openai-key", oak); oak.chmod(0o600)
T = H / ".neurajl-runs/toolchains/polyglot"
env = {**os.environ, "HOME": str(run / "home"), "ABC_PROMPT_FILE": str(run / "prompt.txt"), "ABC_TRACE_FILE": str(run / "trace.json"),
       "ABC_AGENT_DIR": str(run / "agent"), "ABC_RLM_SESSION_DIR": str(run / "rlm"),
       "NEURAJL_SESSION_CLI": f"{LAB}/security/session_cli.py", "NEURAJL_PROJECT_DIR": str(H / ".neurajl-trial/project"), "NEURAJL_REPO_DIR": LAB,
       "JULIA_DEPOT_PATH": str(H / ".neurajl-trial/depot"), "NEURAJL_JULIA_BIN": JULIA, "NEURAJL_STATE_ROOT": str(run / "state"),
       "NIRA_TASK_TOOLS": str(T), "NIRA_TASK_ENV": str(T / "task-env"),
       "ABC_NEURAJL_MAX_OUTPUT_CHARS": "12000", "ABC_MODEL": "gpt-6-luna", "ABC_OPENAI_KEY_FILE": str(oak),
       "ABC_MAX_REQUESTS": "400", "ABC_CONTEXT_WINDOW": "100000", "ABC_MAX_OUTPUT_TOKENS": "8000", "ABC_KEEP_RECENT_TOKENS": "16000",
       "ABC_MAX_RETRIES": "6", "ABC_RETRY_BASE_MS": "2000", "ABC_STALL_MS": "600000", "ABC_MAX_RECOVERIES": "6",
       "ABC_DEADLINE_MS": str(a.minutes * 60_000)}
for kv in a.env: k, _, v = kv.partition("="); env[k] = v
t0 = time.time()
p = subprocess.run(["/usr/bin/node", f"{NP2}/node_modules/.bin/tsx", "--tsconfig", f"{NP2}/tsconfig.json", f"{NP2}/scripts/.endurance-agent.ts"],
                   cwd=ws, env=env, stdout=open(run / "stdout.txt", "w"), stderr=open(run / "stderr.txt", "w"))
oak.unlink(missing_ok=True)
res = {"label": a.label, "exit": p.returncode, "minutes": round((time.time() - t0) / 60, 1)}
try:
    b = json.load(open(run / "trace.json"))["modelRequestBudget"]; res.update(requests=b["attempts"], cost=round(b["reportedCostUsd"], 3))
except Exception as e: res["trace_error"] = str(e)
if (E / "grade.sh").exists():
    res["grade"] = subprocess.run(["bash", str(E / "grade.sh"), str(ws)], capture_output=True, text=True, timeout=1800).stdout.strip().splitlines()
elif a.port:
    res["grade"] = subprocess.run(["python3", str(HN / "ports/grade_ports.py"), str(ws), a.port], capture_output=True, text=True).stdout.strip()
elif (E / "grader.jl").exists():
    g = subprocess.run([JULIA, f"--project={ws}", str(E / "grader.jl")], cwd=ws, capture_output=True, text=True, timeout=900,
                       env={**os.environ, "JULIA_DEPOT_PATH": f"{H}/.neurajl-trial/depot:{H}/.julia"})
    res["grade"] = [l for l in g.stdout.splitlines() if "passed" in l]
(run / "result.json").write_text(json.dumps(res)); print(json.dumps(res))
