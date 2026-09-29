import json, re, sys, subprocess
run = sys.argv[1]
t = json.load(open(run + "/trace.json")); E = t["rawSessionEntries"]
res = {}; calls = []
for e in E:
    m = e.get("message") or {}
    if m.get("role") == "toolResult": res[m["toolCallId"]] = (" ".join(c.get("text", "") for c in m["content"] if c.get("type") == "text"), m.get("isError"))
for i, e in enumerate(E):
    m = e.get("message") or {}
    if m.get("role") == "assistant":
        for c in m["content"]:
            if c.get("type") == "toolCall" and c.get("name") == "neurajl": calls.append((i, c.get("arguments", {}).get("code", "") or "", *res.get(c["id"], ("", False))))
txt = [r for (_, _, r, _) in calls]
count = lambda pat: sum(1 for r in txt if pat in r)
b = t["modelRequestBudget"]
out = {
  "wall_min": round((t["ended"] - t["started"]) / 60000, 1), "neurajl_calls": len(calls), "errors": sum(1 for c in calls if c[3]),
  "requests": b.get("attempts"), "input_tokens": b.get("inputTokens"), "output_tokens": b.get("outputTokens"), "cache_read_tokens": b.get("cacheReadTokens"),
  "cost_usd": round(b.get("reportedCostUsd", 0), 3), "compactions": sum(1 for e in E if e.get("type") == "compaction"),
  "neurajl_state_notes": sum(1 for e in E if e.get("customType") == "neurajl_state"),
  "output_limit_continuations": sum(1 for e in E if e.get("customType") == "output_limit_continuation"),
  "kernel_stopped_notices": count("the kernel stopped"), "revival_reports": count("[revival]"),
  "changed_on_disk_notices": count("[changed on disk since"), "reload_notices": count("[reloaded "),
  "background_reports": count("[background output since"), "background_task_failures": count("[background: task"),
  "undefvar_errors": count("UndefVarError"), "interrupted_calls": count("Interrupted: the call exceeded"),
  "in_kernel_test_includes": sum(1 for c in calls if re.search(r'include\("test', c[1])),
  "cli_test_runs": sum(1 for c in calls if re.search(r"julia[^\n]*(runtests|Pkg\.test)", c[1])),
  "background_jobs_started": sum(1 for c in calls if re.search(r"@async|Threads\.@spawn|wait\s*=\s*false|&\s*\"", c[1])),
}
# state use after each revival: names restored and then used without redefinition in the next 10 calls
reuse_after_revival = []
for k, (_, code, r, _) in enumerate(calls):
    if "[revival]" in r:
        restored = set(re.findall(r"(?:restored exactly|rebuilt from source|restored but stale[^:]*):? ([^\n]*)", r) and
                       re.findall(r"(\w[\w!]*) \([^)]*, call \d+\)", r.split("not revived")[0]))
        used = set()
        for (_, c2, _, _) in calls[k + 1:k + 11]:
            for n in restored:
                if re.search(rf"(?<![\w.]){re.escape(n)}(?![\w])", c2) and not re.search(rf"(?:^|[;\n])\s*{re.escape(n)}\s*=(?!=)", c2): used.add(n)
        reuse_after_revival.append({"at_call": k + 1, "revived_names": len(restored), "reused_in_next_10_calls": sorted(used)})
out["reuse_after_revival"] = reuse_after_revival
cmp = subprocess.run(["python3", "/tmp/claude-1000/-mnt-d-Code-Projects/56f83ff8-67ed-443a-885c-30ae6f715177/scratchpad/njl/comp_ab.py", run + "/trace.json"], capture_output=True, text=True).stdout
if cmp.strip():
    d = json.loads(cmp.split(" ", 1)[1])
    out["after_compaction"] = {k: d[k] for k in ("post_calls", "reuse", "reconstruct", "reparse_log", "rediscover", "undef_errors")}
    out["after_compaction"]["distinct_reused"] = [n for n in d["names_reused"] if len(n) >= 4]
print(json.dumps(out, indent=1))
