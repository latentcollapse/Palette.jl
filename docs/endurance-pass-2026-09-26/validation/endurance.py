"""Supervisor for the NeuraJL endurance run: launches the agent, injects the planned
interventions (one kernel kill, one requirements change), samples resources, and grades."""
import json, os, pathlib, shutil, signal, subprocess, sys, tempfile, time
S = pathlib.Path("/tmp/claude-1000/-mnt-d-Code-Projects/56f83ff8-67ed-443a-885c-30ae6f715177/scratchpad/njl")
E = pathlib.Path(os.environ.get("ENDURANCE_SCENARIO", S / "scenarios/s11-endurance")); NP2 = "/mnt/d/Code Projects/Project NIRA/The Battleground/NIRA-Prime-NeuraJL"
LAB = "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab"
label = sys.argv[1]; KILLS = [int(x) for x in sys.argv[2].split(",")]; CHANGE_AT = int(sys.argv[3]); EDIT_AT = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9
FOLLOWUPS = sys.argv[5] if len(sys.argv) > 5 else ""
run = S / "runs" / f"s11-endurance--{label}"; shutil.rmtree(run, ignore_errors=True)
for d in ("agent", "rlm", "home"): (run / d).mkdir(parents=True)
ws = pathlib.Path(tempfile.mkdtemp(prefix="nje-ws-")); shutil.copytree(E / "fixture", ws, dirs_exist_ok=True)
shutil.copy(E / "prompt.txt", run / "prompt.txt"); (run / "workspace_path").write_text(str(ws))
key = run / "key"; key.write_text(json.load(open(pathlib.Path.home() / ".prime/agent/auth.json"))["openrouter"]["key"]); key.chmod(0o600)
env = {**os.environ, "HOME": str(run / "home"), "ABC_PROMPT_FILE": str(run / "prompt.txt"), "ABC_TRACE_FILE": str(run / "trace.json"),
       "ABC_AGENT_DIR": str(run / "agent"), "ABC_RLM_SESSION_DIR": str(run / "rlm"),
       "NEURAJL_SESSION_CLI": f"{LAB}/security/session_cli.py", "NEURAJL_PROJECT_DIR": str(pathlib.Path.home() / ".neurajl-trial/project"),
       "NEURAJL_REPO_DIR": LAB, "JULIA_DEPOT_PATH": str(pathlib.Path.home() / ".neurajl-trial/depot"),
       "ABC_NEURAJL_MAX_OUTPUT_CHARS": "12000", "ABC_MODEL": "openai/gpt-6-luna", "ABC_OPENROUTER_PROVIDER": "openai",
       "ABC_OPENROUTER_KEY_FILE": str(key), "ABC_MAX_REQUESTS": "2000", "ABC_CONTEXT_WINDOW": "100000",
       "ABC_MAX_OUTPUT_TOKENS": "16000", "ABC_KEEP_RECENT_TOKENS": "16000",
       "ABC_FOLLOWUP_PROMPTS": FOLLOWUPS, "ABC_MAX_RETRIES": "8", "ABC_RETRY_BASE_MS": "5000", "ABC_FOLLOWUP_HOOK": str(E / "followup_hook.sh"), "FOLLOWUP_LOG": str(run / "followups.jsonl"),
       "NEURAJL_JULIA_BIN": str(pathlib.Path.home() / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia")}
log = open(run / "supervisor.jsonl", "a")
def note(**kv):
    kv["t"] = round(time.time() - t0, 1); log.write(json.dumps(kv) + "\n"); log.flush(); print(json.dumps(kv), flush=True)
def kernels():
    out = []
    for p in os.listdir("/proc"):
        if not p.isdigit(): continue
        try:
            cmd = open(f"/proc/{p}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
            if "session_loop.jl" in cmd and "bwrap" not in cmd and os.readlink(f"/proc/{p}/cwd") == str(ws):
                out.append(int(p))
        except OSError: pass
    return out
def trace_stats():
    try: t = json.load(open(run / "trace.json"))
    except Exception: return {}
    E_ = t.get("rawSessionEntries", [])
    calls = sum(1 for e in E_ if e.get("type") == "message" and (e.get("message") or {}).get("role") == "assistant"
                for c in (e["message"].get("content") or []) if c.get("type") == "toolCall" and c.get("name") == "neurajl")
    b = t.get("modelRequestBudget", {})
    return {"neurajl_calls": calls, "compactions": sum(1 for e in E_ if e.get("type") == "compaction"),
            "requests": b.get("attempts"), "in": b.get("inputTokens"), "out": b.get("outputTokens"), "cacheR": b.get("cacheReadTokens")}
def du(path, one_fs=False):
    try: return int(subprocess.run(["du", "-sbx" if one_fs else "-sb", path], capture_output=True, text=True, timeout=60).stdout.split()[0])
    except Exception: return None
t0 = time.time()
proc = subprocess.Popen([f"{NP2}/node_modules/.bin/tsx", "--tsconfig", f"{NP2}/tsconfig.json", f"{NP2}/scripts/.endurance-agent.ts"],
                        cwd=ws, env=env, stdout=open(run / "stdout.txt", "w"), stderr=open(run / "stderr.txt", "w"))
note(event="start", workspace=str(ws), pid=proc.pid)
kills_done = set(); changed = edited = False; last_sample = 0
while proc.poll() is None:
    time.sleep(15)
    st = trace_stats(); n = st.get("neurajl_calls", 0)
    for ka in KILLS:
        if ka not in kills_done and n >= ka and kernels():
            for pid in kernels(): os.kill(pid, signal.SIGKILL)
            kills_done.add(ka); note(event="intervention", what="SIGKILL the kernel(s)", at_calls=n)
    if not edited and n >= EDIT_AT:
        f = ws / "src" / "dict_support.jl"; f.write_text(f.read_text() + chr(10) + "# Maintainer note: helpers shared by the dict types." + chr(10))
        edited = True; note(event="intervention", what="teammate committed a comment to src/dict_support.jl", at_calls=n)
    if not changed and n >= CHANGE_AT:
        with open(ws / "ISSUES.md", "a") as f: f.write((E / "ISSUES_CHANGE.md").read_text())
        changed = True; note(event="intervention", what="teammate appended a requirements change to ISSUES.md", at_calls=n)
    if time.time() - last_sample > 60:
        last_sample = time.time(); ks = kernels(); rss = tmpb = None
        if ks:
            try:
                rss = int([l for l in open(f"/proc/{ks[0]}/status") if l.startswith("VmRSS")][0].split()[1]) // 1024
                tmpb = du(f"/proc/{ks[0]}/root/tmp", one_fs=True)
            except OSError: pass
        note(event="sample", kernel_rss_mb=rss, sandbox_tmp_bytes=tmpb, state_root_bytes=du("/tmp/neurajl-state"), kernel_pid=(ks[0] if ks else None), **st)
note(event="exit", code=proc.returncode, **trace_stats())
key.unlink(missing_ok=True)
shutil.copytree(ws, run / "workspace-after", dirs_exist_ok=True)
g = subprocess.run(["julia", f"--project={ws}", str(E / "grader.jl")], cwd=ws, capture_output=True, text=True, timeout=900,
                   env={**os.environ, "JULIA_DEPOT_PATH": f"{pathlib.Path.home()}/.neurajl-trial/depot:{pathlib.Path.home()}/.julia"})
s = subprocess.run(["julia", f"--project={ws}", "test/runtests.jl"], cwd=ws, capture_output=True, text=True, timeout=1800,
                   env={**os.environ, "JULIA_DEPOT_PATH": f"{pathlib.Path.home()}/.neurajl-trial/depot:{pathlib.Path.home()}/.julia"})
(run / "grade.txt").write_text(g.stdout[-3000:] + g.stderr[-2000:] + "\n--- suite ---\n" + s.stdout[-2000:] + s.stderr[-2000:])
extra = []
if (E / "grade_python.py").exists():
    extra.append(subprocess.run(["python3", str(E / "grade_python.py"), str(ws), str(E)], capture_output=True, text=True).stdout.strip())
if (E / "grade_json5.jl").exists():
    extra.append((subprocess.run(["julia", f"--project={pathlib.Path.home()}/.neurajl-trial/project", str(E / "grade_json5.jl"), str(ws), str(E / "json5_cases.json")],
                                capture_output=True, text=True, timeout=900,
                                env={**os.environ, "JULIA_DEPOT_PATH": f"{pathlib.Path.home()}/.neurajl-trial/depot:{pathlib.Path.home()}/.julia"}).stdout.strip().splitlines() or [""])[-1])
if (E / "grade_toml.jl").exists():
    extra.append((subprocess.run(["julia", f"--project={pathlib.Path.home()}/.neurajl-trial/project", str(E / "grade_toml.jl"), str(ws), str(E / "toml_cases.json")],
                                capture_output=True, text=True, timeout=900,
                                env={**os.environ, "JULIA_DEPOT_PATH": f"{pathlib.Path.home()}/.neurajl-trial/depot:{pathlib.Path.home()}/.julia"}).stdout.strip().splitlines() or [""])[-1])
if (ws / "reports" / "logs.md").exists():
    shutil.copytree(ws / "reports", run / "reports-copy", dirs_exist_ok=True); pathlib.Path(run / "workspace-after" / "report.md").write_text((ws / "reports" / "logs.md").read_text())
    extra.append(subprocess.run(["python3", str(S / "s10_check.py"), str(S / "scenarios/s10-logs/truth.json"), str(run)], capture_output=True, text=True).stdout.strip())
(run / "grade_extra.txt").write_text(chr(10).join(extra))
note(event="graded", extra=extra, grader_all=[l for l in g.stdout.splitlines() if "passed" in l], grader=g.stdout.strip().splitlines()[-1] if g.stdout.strip() else g.stderr[-300:], suite_exit=s.returncode)
