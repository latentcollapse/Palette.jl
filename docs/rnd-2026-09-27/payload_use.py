import json, re, sys
def text(c): return "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
tot = dict(calls=0, payload=0, tq=0, tq_writes=0, edits=0, edit_multi=0)
quoting_fail = []
QUOTE = r'ParseError|invalid keyword argument name|cannot juxtapose|syntax:'
for path in sys.argv[1:]:
    t = json.load(open(path)); ms = [e["message"] for e in t["rawSessionEntries"] if e.get("type") == "message"]
    args = {}
    for m in ms:
        if m["role"] == "assistant":
            for c in m["content"]:
                if c.get("type") == "toolCall" and c.get("name") == "neurajl":
                    a = c.get("arguments", {}); args[c["id"]] = a; code = a.get("code", "")
                    tot["calls"] += 1
                    tot["payload"] += bool(a.get("payload"))
                    ntq = code.count('"""') // 2
                    tot["tq"] += ntq > 0
                    iswrite = bool(re.search(r"\bwrite\(", code))
                    tot["tq_writes"] += ntq > 0 and iswrite
                    isedit = bool(re.search(r"replace\(", code)) and iswrite
                    tot["edits"] += isedit
                    tot["edit_multi"] += isedit and ntq >= 2
        if m["role"] == "toolResult" and m.get("toolName") == "neurajl" and m.get("isError") and re.search(QUOTE, text(m["content"])):
            code = args.get(m.get("toolCallId"), {}).get("code", "")
            quoting_fail.append(dict(tq=code.count('"""') // 2, write=bool(re.search(r"\bwrite\(", code)), dollar=bool(re.search(r'"[^"\n]*\$[^(a-zA-Z_{]', code))))
print(tot)
print("syntax/parse failures:", len(quoting_fail), "with triple-quoted literals:", sum(q["tq"] > 0 for q in quoting_fail), "writing a file:", sum(q["write"] for q in quoting_fail))
