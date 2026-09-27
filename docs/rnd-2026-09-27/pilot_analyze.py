"""Per pilot run: quoting failures, hints shown, payload use before and after the first quoting failure."""
import json, pathlib, re, sys
QUOTE = re.compile(r'invalid keyword argument name|ParseError|UndefVarError|cannot juxtapose')
HINT = re.compile(r'Hint: the string that begins|is interpolated into a string|Hint: in a Julia string \$|pass it as this call.s payload')
def text(c): return "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
root = pathlib.Path(__file__).resolve().parent / "pilot"
rows = []
for d in sorted(p for p in root.iterdir() if p.is_dir()):
    try: t = json.load(open(d / "trace.json"))
    except Exception: continue
    ms = [e["message"] for e in t["rawSessionEntries"] if e.get("type") == "message"]
    calls = {}; order = []
    for m in ms:
        if m["role"] == "assistant":
            for c in m["content"]:
                if c.get("type") == "toolCall" and c.get("name") == "neurajl":
                    calls[c["id"]] = c.get("arguments", {}); order.append(c["id"])
    results = {m["toolCallId"]: m for m in ms if m["role"] == "toolResult" and m.get("toolName") == "neurajl"}
    first_q = None; qfail = hints = 0; writes_before = writes_after = pay_before = pay_after = 0
    for i, cid in enumerate(order):
        a = calls[cid]; r = results.get(cid)
        writes = bool(re.search(r"\bwrite\(", a.get("code", "")))
        pay = bool(a.get("payload"))
        if first_q is None:
            writes_before += writes; pay_before += pay and writes
        else:
            writes_after += writes; pay_after += pay and writes
        if r is not None and r.get("isError"):
            s = text(r["content"])
            code = a.get("code", "")
            quoting = bool(QUOTE.search(s)) and ('"""' in code or re.search(r'"[^"\n]*\$', code))
            if quoting:
                qfail += 1
                first_q = i if first_q is None else first_q
            hints += bool(HINT.search(s))
    res = json.loads((d / "result.json").read_text()) if (d / "result.json").exists() else {}
    rows.append(dict(run=d.name, calls=len(order), quoting_failures=qfail, hints_shown=hints,
                     payload_writes_before=f"{pay_before}/{writes_before}", payload_writes_after_first_quoting_failure=f"{pay_after}/{writes_after}",
                     grader=res.get("grader"), minutes=res.get("minutes")))
for r in rows: print(json.dumps(r))
