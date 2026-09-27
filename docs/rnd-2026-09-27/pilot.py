"""Hint pilot: one ISSUES.md run of the s11 OrderedCollections backlog, on OpenRouter Luna.

python3 pilot.py <arm: hints|control> <label>

hints   = the R&D worktree build (rnd/closure-revival), its own project and depot
control = the build before the hints (lab 7644239), its own project and depot
Both use the same NP2 driver (scripts/.endurance-agent.ts), OpenRouter only.
"""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time
S = pathlib.Path(__file__).resolve().parent.parent / "njl"
H = pathlib.Path.home()
NP2 = "/mnt/d/Code Projects/Project NIRA/The Battleground/NIRA-Prime-NeuraJL"
arm, label = sys.argv[1], sys.argv[2]
# Round 1 ran control on the lab checkout at 7644239; after the 07:22 deploy the
# lab has the hints, so control runs from a worktree pinned at 7644239.
repo = str(H / ("rnd/neurajl-lab-wt" if arm == "hints" else "rnd/neurajl-lab-old"))
project = H / (".neurajl-rnd/project" if arm == "hints" else ".neurajl-rnd3/project")
depot = H / (".neurajl-rnd/depot" if arm == "hints" else ".neurajl-rnd3/depot")
E = S / "scenarios/s11-endurance-xxl"
run = pathlib.Path(__file__).resolve().parent / "pilot" / f"{arm}-{label}"; shutil.rmtree(run, ignore_errors=True)
for d in ("agent", "rlm", "home", "state"): (run / d).mkdir(parents=True)
ws = pathlib.Path(tempfile.mkdtemp(prefix=f"njp-{arm}-")); shutil.copytree(E / "fixture", ws, dirs_exist_ok=True)
shutil.copy(E / "prompt.txt", run / "prompt.txt")
ork = run / "ork"; ork.write_text(json.load(open(H / ".prime/agent/auth.json"))["openrouter"]["key"]); ork.chmod(0o600)
env = {**os.environ, "HOME": str(run / "home"), "ABC_PROMPT_FILE": str(run / "prompt.txt"), "ABC_TRACE_FILE": str(run / "trace.json"),
       "ABC_AGENT_DIR": str(run / "agent"), "ABC_RLM_SESSION_DIR": str(run / "rlm"),
       "NEURAJL_SESSION_CLI": f"{repo}/security/session_cli.py", "NEURAJL_PROJECT_DIR": str(project), "NEURAJL_REPO_DIR": repo,
       "JULIA_DEPOT_PATH": str(depot), "NEURAJL_JULIA_BIN": str(H / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"),
       "NEURAJL_STATE_ROOT": str(run / "state"), "ABC_NEURAJL_MAX_OUTPUT_CHARS": "12000",
       "ABC_MODEL": "openai/gpt-6-luna", "ABC_OPENROUTER_PROVIDER": "openai", "ABC_OPENROUTER_KEY_FILE": str(ork),
       "ABC_MAX_REQUESTS": "250", "ABC_CONTEXT_WINDOW": "100000", "ABC_MAX_OUTPUT_TOKENS": "16000", "ABC_KEEP_RECENT_TOKENS": "16000",
       "ABC_MAX_RETRIES": "4", "ABC_RETRY_BASE_MS": "5000", "ABC_STALL_MS": "600000", "ABC_MAX_RECOVERIES": "6",
       "ABC_DEADLINE_MS": str(50 * 60_000)}
t0 = time.time()
p = subprocess.run([f"{NP2}/node_modules/.bin/tsx", "--tsconfig", f"{NP2}/tsconfig.json", f"{NP2}/scripts/.endurance-agent.ts"],
                   cwd=ws, env=env, stdout=open(run / "stdout.txt", "w"), stderr=open(run / "stderr.txt", "w"))
ork.unlink(missing_ok=True)
g = subprocess.run([str(H / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia"), f"--project={ws}", str(E / "grader.jl")], cwd=ws,
                   capture_output=True, text=True, timeout=900, env={**os.environ, "JULIA_DEPOT_PATH": f"{depot}:{H}/.julia"})
shutil.copytree(ws, run / "workspace-after", dirs_exist_ok=True)
(run / "result.json").write_text(json.dumps({"arm": arm, "label": label, "exit": p.returncode, "minutes": round((time.time() - t0) / 60, 1),
                                             "grader": [l for l in g.stdout.splitlines() if "passed" in l]}))
print(open(run / "result.json").read())
