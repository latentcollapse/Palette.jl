"""Failover check: primary route broken on purpose, the task must still finish on the backup."""
import json, os, pathlib, shutil, socket, subprocess, sys, tempfile, threading
S = pathlib.Path(__file__).resolve().parent.parent
NP2 = "/mnt/d/Code Projects/Project NIRA/The Battleground/NIRA-Prime-NeuraJL"; LAB = "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab"
mode = sys.argv[1]  # refused | blackhole | healthy
run = S / "fotest" / mode; shutil.rmtree(run, ignore_errors=True)
for d in ("agent", "rlm", "home"): (run / d).mkdir(parents=True)
ws = pathlib.Path(tempfile.mkdtemp(prefix="nje-fo-"))
(run / "prompt.txt").write_text("Using the neurajl tool, compute the sum of the squares of 1 to 100 in Julia and write just the number to answer.txt in the workspace. Then say done.")
ork = run / "ork"; ork.write_text(json.load(open(pathlib.Path.home() / ".prime/agent/auth.json"))["openrouter"]["key"]); ork.chmod(0o600)
oak = run / "oak"; shutil.copy(pathlib.Path.home() / ".config/openai-key", oak); oak.chmod(0o600)
env = {**os.environ, "HOME": str(run / "home"), "ABC_PROMPT_FILE": str(run / "prompt.txt"), "ABC_TRACE_FILE": str(run / "trace.json"),
       "ABC_AGENT_DIR": str(run / "agent"), "ABC_RLM_SESSION_DIR": str(run / "rlm"),
       "NEURAJL_SESSION_CLI": f"{LAB}/security/session_cli.py", "NEURAJL_PROJECT_DIR": str(pathlib.Path.home() / ".neurajl-trial/project"),
       "NEURAJL_REPO_DIR": LAB, "JULIA_DEPOT_PATH": str(pathlib.Path.home() / ".neurajl-trial/depot"),
       "ABC_NEURAJL_MAX_OUTPUT_CHARS": "12000", "ABC_MODEL": "gpt-6-luna", "ABC_OPENROUTER_PROVIDER": "openai",
       "ABC_OPENAI_KEY_FILE": str(oak), "ABC_OPENROUTER_KEY_FILE": str(ork), "ABC_BACKUP": "1",
       "ABC_MAX_REQUESTS": "40", "ABC_CONTEXT_WINDOW": "100000", "ABC_MAX_OUTPUT_TOKENS": "16000",
       "ABC_MAX_RETRIES": "2", "ABC_RETRY_BASE_MS": "2000", "ABC_STALL_MS": "60000", "ABC_MAX_RECOVERIES": "4",
       "NEURAJL_JULIA_BIN": str(pathlib.Path.home() / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia")}
if mode == "refused": env["ABC_BASE_URL"] = "http://127.0.0.1:9/v1"
if mode == "blackhole":
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(64); held = []
    def hold():
        while True: held.append(srv.accept()[0])  # accept and never answer
    threading.Thread(target=hold, daemon=True).start()
    env["ABC_BASE_URL"] = f"http://127.0.0.1:{srv.getsockname()[1]}/v1"
p = subprocess.run([f"{NP2}/node_modules/.bin/tsx", "--tsconfig", f"{NP2}/tsconfig.json", f"{NP2}/scripts/.endurance-agent.ts"],
                   cwd=ws, env=env, capture_output=True, text=True, timeout=1500)
t = json.load(open(run / "trace.json"))
ans = (ws / "answer.txt").read_text().strip() if (ws / "answer.txt").exists() else None
last = [m for m in t["messages"] if m["role"] == "assistant"][-1]
print(json.dumps({"mode": mode, "exit": p.returncode, "answer": ans, "expected": "338350", "keyfiles_left": [f.name for f in (ork, oak) if f.exists()],
                  "recoveryLog": t["recoveryLog"], "lastStop": last.get("stopReason"), "lastModel": f'{last.get("provider")}/{last.get("model")}',
                  "error": t.get("error"), "stderr_tail": p.stderr[-800:]}, indent=1))
