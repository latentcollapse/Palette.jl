"""Compaction A/B: what Luna does with kernel state defined before the retained context."""
import json, re, sys
ASSIGN = re.compile(r"(?:^|[;\n])\s*(?:const\s+|global\s+)?([A-Za-z_]\w*)\s*(?:::[^=\n]+)?=(?!=)")
FUNC = re.compile(r"(?:^|[;\n])\s*(?:function\s+([A-Za-z_]\w*)|([A-Za-z_]\w*)\([^()\n]*\)\s*=(?!=))")
def defined(code):
    out = {m.group(1) for m in ASSIGN.finditer(code)}
    for m in FUNC.finditer(code): out.add(m.group(1) or m.group(2))
    return out - {"_"}
def used(code, name): return re.search(rf"(?<![\w.:]){re.escape(name)}(?![\w])", code) is not None
def run(path):
    t = json.load(open(path)); E = t["rawSessionEntries"]; idx = {e.get("id"): i for i, e in enumerate(E)}
    calls = []  # (entry index, code, result text, is_error)
    res = {}
    for i, e in enumerate(E):
        m = e.get("message") or {}
        if e.get("type") == "message" and m.get("role") == "toolResult":
            res[m.get("toolCallId")] = (" ".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"), m.get("isError"))
    for i, e in enumerate(E):
        m = e.get("message") or {}
        if e.get("type") == "message" and m.get("role") == "assistant":
            for c in m.get("content", []):
                if c.get("type") == "toolCall" and c.get("name") == "neurajl":
                    code = (c.get("arguments") or {}).get("code", "") or ""
                    txt, err = res.get(c.get("id"), ("", False))
                    calls.append((i, code, txt, err))
    comps = [(i, idx.get(e.get("firstKeptEntryId"), i)) for i, e in enumerate(E) if e.get("type") == "compaction"]
    notes = sum(1 for e in E if e.get("customType") == "neurajl_state")
    out = {"calls": len(calls), "compactions": len(comps), "notes": notes, "reuse": 0, "reconstruct": 0, "reparse_log": 0,
           "rediscover": 0, "undef_errors": 0, "post_calls": 0, "names_forgotten": set(), "names_reused": set()}
    for ci, (at, kept) in enumerate(comps):
        end = comps[ci + 1][0] if ci + 1 < len(comps) else len(E)
        lost = set().union(*[defined(c) for (i, c, _, _) in calls if i < kept]) if any(i < kept for (i, _, _, _) in calls) else set()
        # names visible in retained context are not "forgotten" candidates
        kept_defs = set().union(*[defined(c) for (i, c, _, _) in calls if kept <= i < at]) if any(kept <= i < at for (i, _, _, _) in calls) else set()
        outside = lost - kept_defs
        for (i, code, txt, err) in calls:
            if not (at < i < end): continue
            out["post_calls"] += 1
            d = defined(code)
            reused = {n for n in outside if used(code, n) and n not in d}
            redone = {n for n in outside if n in d}
            if reused: out["reuse"] += 1; out["names_reused"] |= reused
            if redone: out["reconstruct"] += 1; out["names_forgotten"] |= redone
            if "access.log" in code: out["reparse_log"] += 1
            if re.search(r"varinfo\(|names\(\s*(@__MODULE__|Main)|@isdefined|isdefined\(", code): out["rediscover"] += 1
            if "UndefVarError" in txt: out["undef_errors"] += 1
        out.setdefault("outside_names", set()).update(outside)
    b = t["modelRequestBudget"]
    out.update({"cost": round(b.get("reportedCostUsd", 0), 4), "in": b.get("inputTokens"), "attempts": b.get("attempts"),
                "wall": round((t["ended"] - t["started"]) / 1000)})
    for k in ("names_forgotten", "names_reused", "outside_names"): out[k] = sorted(out.get(k, set()))
    return out
for p in sys.argv[1:]:
    print(p.split("/")[-2], json.dumps(run(p)))
