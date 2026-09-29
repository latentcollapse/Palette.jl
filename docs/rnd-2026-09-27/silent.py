import json, re, sys
def text(c): return "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
TQ = re.compile(r'(?<![a-z_])"""(.*?)(?<!\\)"""', re.S)   # plain triple-quoted literals, not raw"""
n = 0; hits = []
for path in sys.argv[1:]:
    t = json.load(open(path)); ms = [e["message"] for e in t["rawSessionEntries"] if e.get("type") == "message"]
    ok = {m.get("toolCallId") for m in ms if m["role"] == "toolResult" and not m.get("isError")}
    for m in ms:
        if m["role"] != "assistant": continue
        for c in m["content"]:
            if c.get("type") != "toolCall" or c.get("name") != "neurajl" or c["id"] not in ok: continue
            code = c.get("arguments", {}).get("code", "")
            if not re.search(r"\bwrite\(", code): continue
            for lit in TQ.findall(code):
                interp = re.findall(r'(?<!\\)\$(?:\(|[A-Za-z_])', lit)
                esc = re.findall(r'(?<!\\)\\[nt"]', lit)
                if interp or esc:
                    n += 1
                    if len(hits) < 8: hits.append((path.split("/")[-2], interp[:3], esc[:3], lit[:160].replace("\n", "⏎")))
print("successful file-writing calls whose triple-quoted literal interpolates or processes escapes:", n)
for h in hits: print(h)
