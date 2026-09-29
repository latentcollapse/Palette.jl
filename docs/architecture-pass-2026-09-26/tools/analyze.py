#!/usr/bin/env python3
"""Summarise a NeuraJL Luna run: behaviour, not score. Usage: analyze.py RUN_DIR [--calls]"""
import json, re, sys
from pathlib import Path

run = Path(sys.argv[1]); show_calls = "--calls" in sys.argv
t = json.load(open(run / "trace.json"))
msgs = t["messages"]
calls, results = [], {}
for m in msgs:
    if m.get("role") == "assistant":
        for c in m["content"]:
            if c["type"] == "toolCall":
                calls.append(c)
    elif m.get("role") == "toolResult":
        results[m.get("toolCallId")] = m
turns = sum(1 for m in msgs if m.get("role") == "assistant")
b = t["modelRequestBudget"]

ASSIGN = re.compile(r'(?m)^\s*(?:global\s+|const\s+)?([A-Za-z_][A-Za-z0-9_!]*)\s*(?:::[^=]+)?=(?![=>])|;\s*([A-Za-z_][A-Za-z0-9_!]*)\s*=(?![=>])|^\s*(?:function|struct|mutable struct)\s+([A-Za-z_][A-Za-z0-9_!]*)|^\s*([A-Za-z_][A-Za-z0-9_!]*)\([^)]*\)\s*=(?!=)')
STRIP = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|#[^\n]*')
defined, reuse_calls, reused_names = set(), 0, set()
reads = {}
stats = dict(errors=0, parse_errors=0, interrupted=0, restarts=0, payload=0, sh=0, bash=0, run_cmd=0,
             python_exec=0, write_calls=0, include=0, varinfo=0, kernelinfo=0, ans=0, ephemeral=0)
error_kinds = {}
rows = []
for i, c in enumerate(calls, 1):
    a = c.get("arguments") or {}
    code = a.get("code", ""); payload = a.get("payload")
    r = results.get(c.get("id"))
    txt = " ".join(x.get("text", "") for x in (r or {}).get("content", []) if x.get("type") == "text")
    err = bool(r and r.get("isError"))
    stats["errors"] += err
    if err:
        k = re.search(r"Error: ([A-Za-z]+(?:Error|Exception)|ParseError|Interrupted)", txt)
        k = k.group(1) if k else txt[:40]
        error_kinds[k] = error_kinds.get(k, 0) + 1
    stats["parse_errors"] += "ParseError" in txt
    stats["interrupted"] += "Interrupted:" in txt
    stats["restarts"] += "this call ran in a NEW kernel" in txt
    stats["payload"] += payload is not None
    stats["ephemeral"] += bool(a.get("ephemeral"))
    body = STRIP.sub('""', code)
    stats["sh"] += len(re.findall(r'\bsh"', code))
    stats["bash"] += len(re.findall(r'\bbash\(', code))
    stats["run_cmd"] += len(re.findall(r'\brun\(`|\bread\(`|\bpipeline\(`', code))
    stats["python_exec"] += len(re.findall(r'python3?\b', code))
    stats["write_calls"] += len(re.findall(r'\bwrite\(', code))
    stats["include"] += "include(" in code
    stats["varinfo"] += "varinfo(" in code
    stats["kernelinfo"] += "kernelinfo(" in code
    stats["ans"] += bool(re.search(r'\bans\b', body))
    used = {n for n in defined if re.search(r'(?<![\w.])%s\b' % re.escape(n), body)}
    if used:
        reuse_calls += 1; reused_names |= used
    for mt in ASSIGN.finditer(body):
        defined.add(next(g for g in mt.groups() if g))
    for fn in re.findall(r'(?:read|readlines|readline|CSV\.read|CSV\.File|open|eachline|parsefile|JSON\.parsefile)\(\s*"([^"]+)"', code):
        reads[fn] = reads.get(fn, 0) + 1
    rows.append((i, err, len(code), payload is not None, txt[:160].replace("\n", " | ")))
repeat_reads = {k: v for k, v in reads.items() if v > 1}
print(f"== {run.name}  exit={Path(run/'exit.txt').read_text().strip() if (run/'exit.txt').exists() else '?'}  error={t.get('error')}")
print(f"turns={turns} calls={len(calls)} attempts={b.get('attempts')} in={b.get('inputTokens')} cacheR={b.get('cacheReadTokens')} out={b.get('outputTokens')} cost=${b.get('reportedCostUsd',0):.4f} wall={(t['ended']-t['started'])/1000:.0f}s")
print("stats:", stats)
print("error kinds:", error_kinds)
print(f"cross-call reuse: {reuse_calls}/{len(calls)} calls reuse earlier bindings; names: {sorted(reused_names)[:25]}")
print("repeated file reads:", repeat_reads)
if show_calls:
    for i, err, n, pl, head in rows:
        print(f"  [{i:2}] {'ERR' if err else 'ok '} code={n:5} payload={'Y' if pl else '-'}  {head}")
