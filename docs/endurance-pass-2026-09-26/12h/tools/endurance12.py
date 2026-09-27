"""Supervisor for the 12h NeuraJL endurance run.

Launches the isolated driver (direct OpenAI primary, OpenRouter backup, stall watchdog,
deadline), injects timed kernel kills and teammate edits, samples resources, writes an
hourly checkpoint (with a live grade of the ports) and grades everything at the end.

python3 endurance12.py <label> [--hours H] [--kills h1,h2,..] [--checkpoint-min M] [--cost-cap USD] [--queue N] [--edit-hours h]
"""
import argparse, json, os, pathlib, shutil, signal, subprocess, sys, tempfile, threading, time

S = pathlib.Path(__file__).resolve().parent
E = S / "scenarios/s12-endurance-12h"
NP2 = "/mnt/d/Code Projects/Project NIRA/The Battleground/NIRA-Prime-NeuraJL"
LAB = "/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab"
HOME = pathlib.Path.home()
JULIA = str(HOME / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia")
DEPOT = {"JULIA_DEPOT_PATH": f"{HOME}/.neurajl-trial/depot:{HOME}/.julia"}

ap = argparse.ArgumentParser()
ap.add_argument("label"); ap.add_argument("--hours", type=float, default=12.0)
ap.add_argument("--kills", default="1.5,4,6.5,9,11"); ap.add_argument("--checkpoint-min", type=float, default=60)
ap.add_argument("--cost-cap", type=float, default=9.0); ap.add_argument("--queue", type=int, default=0)
ap.add_argument("--edit-hours", type=float, default=5.0); ap.add_argument("--change-at-calls", type=int, default=70)
ap.add_argument("--src-edit-at-calls", type=int, default=150); ap.add_argument("--evidence", default="")
ap.add_argument("--prompt", default=""); ap.add_argument("--queue-files", default="")
a = ap.parse_args()

run = S / "runs" / f"s12--{a.label}"; shutil.rmtree(run, ignore_errors=True)
for d in ("agent", "rlm", "home"): (run / d).mkdir(parents=True)
state_root = HOME / ".neurajl-endurance-state" / a.label; shutil.rmtree(state_root, ignore_errors=True); state_root.mkdir(parents=True)
ws = pathlib.Path(tempfile.mkdtemp(prefix="nje12-ws-")); shutil.copytree(E / "fixture", ws, dirs_exist_ok=True)
shutil.copy(E / (a.prompt or "prompt.txt"), run / "prompt.txt"); (run / "workspace_path").write_text(str(ws))
queue = ["f2.txt", "f3.txt", "f4.txt", "f5.txt", "f6.txt", "f7.txt", "f8.txt", "f9.txt", "f10.txt", "f11.txt"] + (E / "queue.txt").read_text().split()
if a.queue: queue = queue[:a.queue]
if a.queue_files: queue = a.queue_files.split(",")
ork = run / "ork"; ork.write_text(json.load(open(HOME / ".prime/agent/auth.json"))["openrouter"]["key"]); ork.chmod(0o600)
oak = run / "oak"; shutil.copy(HOME / ".config/openai-key", oak); oak.chmod(0o600)
env = {**os.environ, "HOME": str(run / "home"), "ABC_PROMPT_FILE": str(run / "prompt.txt"), "ABC_TRACE_FILE": str(run / "trace.json"),
       "ABC_AGENT_DIR": str(run / "agent"), "ABC_RLM_SESSION_DIR": str(run / "rlm"),
       "NEURAJL_SESSION_CLI": f"{LAB}/security/session_cli.py", "NEURAJL_PROJECT_DIR": str(HOME / ".neurajl-trial/project"),
       "NEURAJL_REPO_DIR": LAB, "JULIA_DEPOT_PATH": str(HOME / ".neurajl-trial/depot"), "NEURAJL_JULIA_BIN": JULIA,
       "NEURAJL_STATE_ROOT": str(state_root), "ABC_NEURAJL_MAX_OUTPUT_CHARS": "12000",
       "ABC_MODEL": "gpt-6-luna", "ABC_OPENROUTER_PROVIDER": "openai", "ABC_BACKUP": "1",
       "ABC_OPENAI_KEY_FILE": str(oak), "ABC_OPENROUTER_KEY_FILE": str(ork),
       "ABC_MAX_REQUESTS": "8000", "ABC_CONTEXT_WINDOW": "100000", "ABC_MAX_OUTPUT_TOKENS": "16000", "ABC_KEEP_RECENT_TOKENS": "16000",
       "ABC_MAX_RETRIES": "3", "ABC_RETRY_BASE_MS": "5000", "ABC_STALL_MS": "600000", "ABC_MAX_RECOVERIES": "60",
       "ABC_DEADLINE_MS": str(int(a.hours * 3600_000)),
       "ABC_FOLLOWUP_PROMPTS": ":".join(str(E / q) for q in queue), "ABC_FOLLOWUP_HOOK": str(E / "followup_hook.sh"), "FOLLOWUP_LOG": str(run / "followups.jsonl")}
evidence = pathlib.Path(a.evidence) if a.evidence else None
if evidence: evidence.mkdir(parents=True, exist_ok=True)
log = open(run / "supervisor.jsonl", "a")
t0 = time.time()


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


def rss_mb(pid):
    try: return int([l for l in open(f"/proc/{pid}/status") if l.startswith("VmRSS")][0].split()[1]) // 1024
    except (OSError, IndexError): return None


def trace_stats():
    try: t = json.load(open(run / "trace.json"))
    except Exception: return {}
    ents = t.get("rawSessionEntries", [])
    calls = sum(1 for e in ents if e.get("type") == "message" and (e.get("message") or {}).get("role") == "assistant"
                for c in (e["message"].get("content") or []) if c.get("type") == "toolCall" and c.get("name") == "neurajl")
    b = t.get("modelRequestBudget", {}); rl = t.get("recoveryLog", [])
    return {"neurajl_calls": calls, "compactions": sum(1 for e in ents if e.get("type") == "compaction"),
            "requests": b.get("attempts"), "request_errors": b.get("requestErrors"), "cost_usd": round(b.get("reportedCostUsd") or 0, 4),
            "in": b.get("inputTokens"), "out": b.get("outputTokens"), "cacheR": b.get("cacheReadTokens"),
            "retries": sum(1 for r in rl if r["kind"] == "retry"), "backup_retries": sum(1 for r in rl if r.get("reason") == "backup"),
            "stall_aborts": sum(1 for r in rl if r["kind"] == "stall_abort"), "recoveries": sum(1 for r in rl if r["kind"] == "recovery"),
            "followups_started": sum(1 for r in rl if r["kind"] == "followup"), "trace_mb": round((run / "trace.json").stat().st_size / 1e6, 1)}


def du(path, one_fs=False):
    try: return int(subprocess.run(["du", "-sbx" if one_fs else "-sb", str(path)], capture_output=True, text=True, timeout=120).stdout.split()[0])
    except Exception: return None


def grade_ports():
    try: return subprocess.run(["python3", str(S / "ports/grade_ports.py"), str(ws)], capture_output=True, text=True, timeout=3 * 3600).stdout.strip()
    except subprocess.TimeoutExpired: return "ports grader timed out"


ck_lock = threading.Lock()


def checkpoint(sample, final=False):
  with ck_lock:
      ports = grade_ports()
      done = [json.loads(l)["followup"] for l in open(run / "followups.jsonl")] if (run / "followups.jsonl").exists() else []
      h = (time.time() - t0) / 3600
      block = (f"\n## {'Final' if final else 'Checkpoint'} at {h:.2f} h ({time.strftime('%Y-%m-%d %H:%M:%S')})\n\n"
               f"- driver alive: {proc.poll() is None}; follow-ups delivered: {len(done)}/{len(queue)} (last: {done[-1] if done else '-'})\n"
               + "".join(f"- {k}: {v}\n" for k, v in sample.items())
               + "\nLive port grade:\n\n```\n" + ports + "\n```\n")
      with open(run / "checkpoints.md", "a") as f: f.write(block)
      if evidence: shutil.copy(run / "checkpoints.md", evidence / "checkpoints.md")
      note(event="checkpoint", hours=round(h, 2), ports_total=ports.splitlines()[-1] if ports else None)


(run / "checkpoints.md").write_text(f"# 12h endurance run {a.label}: checkpoints\n\nWorkspace {ws}; state root {state_root}; queue of {len(queue)} follow-ups after the initial ISSUES.md prompt.\n")
proc = subprocess.Popen([f"{NP2}/node_modules/.bin/tsx", "--tsconfig", f"{NP2}/tsconfig.json", f"{NP2}/scripts/.endurance-agent.ts"],
                        cwd=ws, env=env, stdout=open(run / "stdout.txt", "w"), stderr=open(run / "stderr.txt", "w"))
note(event="start", workspace=str(ws), pid=proc.pid, hours=a.hours, queue=len(queue))
kill_at = [float(x) * 3600 for x in a.kills.split(",") if x]
kills_done = set(); changed = src_edited = port_edited = cost_stopped = False
last_sample = 0; next_checkpoint = a.checkpoint_min * 60; sample = {}
while proc.poll() is None:
    time.sleep(30)
    el = time.time() - t0
    for k in kill_at:
        if k not in kills_done and el >= k:
            ks = kernels()
            for pid in ks: os.kill(pid, signal.SIGKILL)
            if ks: kills_done.add(k); note(event="intervention", what="SIGKILL the kernel(s)", pids=ks, planned_h=k / 3600)
    if el - last_sample >= 60:
        last_sample = el; st = trace_stats(); ks = kernels()
        sample = {"kernel_rss_mb": rss_mb(ks[0]) if ks else None, "driver_rss_mb": rss_mb(proc.pid),
                  "sandbox_tmp_bytes": du(f"/proc/{ks[0]}/root/tmp", one_fs=True) if ks else None, "state_root_bytes": du(state_root),
                  "kernel_pid": ks[0] if ks else None, **st}
        note(event="sample", **sample)
        n = st.get("neurajl_calls", 0)
        if not changed and n >= a.change_at_calls:
            with open(ws / "ISSUES.md", "a") as f: f.write((E / "ISSUES_CHANGE.md").read_text())
            changed = True; note(event="intervention", what="teammate appended a requirements change to ISSUES.md", at_calls=n)
        if not src_edited and n >= a.src_edit_at_calls:
            f = ws / "src" / "dict_support.jl"; f.write_text(f.read_text() + "\n# Maintainer note: helpers shared by the dict types.\n")
            src_edited = True; note(event="intervention", what="teammate committed a comment to src/dict_support.jl", at_calls=n)
        if st.get("cost_usd", 0) > a.cost_cap and not cost_stopped:
            cost_stopped = True; note(event="cost_cap", cost=st["cost_usd"]); proc.send_signal(signal.SIGTERM)
    if not port_edited and el >= a.edit_hours * 3600:
        ported = sorted((ws / "ports").glob("*.jl"), key=lambda p: p.stat().st_mtime)
        if ported:
            f = ported[0]; f.write_text(f"# Reviewed by a teammate; keep this module self-contained.\n{f.read_text()}")
            port_edited = True; note(event="intervention", what=f"teammate added a header comment to ports/{f.name}")
    if el >= next_checkpoint:
        next_checkpoint += a.checkpoint_min * 60; threading.Thread(target=checkpoint, args=(dict(sample),), daemon=True).start()
note(event="exit", code=proc.returncode, **trace_stats())
for k in (ork, oak): k.unlink(missing_ok=True)
shutil.copytree(ws, run / "workspace-after", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
extra = []
g = subprocess.run([JULIA, f"--project={ws}", str(E / "grader.jl")], cwd=ws, capture_output=True, text=True, timeout=900, env={**os.environ, **DEPOT})
s = subprocess.run([JULIA, f"--project={ws}", "test/runtests.jl"], cwd=ws, capture_output=True, text=True, timeout=1800, env={**os.environ, **DEPOT})
extra.append(subprocess.run(["python3", str(E / "grade_python.py"), str(ws), str(E)], capture_output=True, text=True).stdout.strip())
for gj, cf in (("grade_json5.jl", "json5_cases.json"), ("grade_toml.jl", "toml_cases.json")):
    extra.append((subprocess.run([JULIA, f"--project={HOME}/.neurajl-trial/project", str(E / gj), str(ws), str(E / cf)],
                                 capture_output=True, text=True, timeout=900, env={**os.environ, **DEPOT}).stdout.strip().splitlines() or [""])[-1])
if (ws / "reports" / "logs.md").exists():
    shutil.copytree(ws / "reports", run / "reports-copy", dirs_exist_ok=True); (run / "workspace-after" / "report.md").write_text((ws / "reports" / "logs.md").read_text())
    extra.append(subprocess.run(["python3", str(S / "s10_check.py"), str(S / "scenarios/s10-logs/truth.json"), str(run)], capture_output=True, text=True).stdout.strip())
(run / "grade.txt").write_text(g.stdout[-3000:] + g.stderr[-2000:] + "\n--- suite ---\n" + s.stdout[-2000:] + s.stderr[-2000:])
(run / "grade_extra.txt").write_text("\n".join(extra))
checkpoint(trace_stats(), final=True)
note(event="graded", extra=extra, grader_all=[l for l in g.stdout.splitlines() if "passed" in l], suite_exit=s.returncode)
