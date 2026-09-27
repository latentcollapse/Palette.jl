import json, re, sys
def text(c): return "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
for path in sys.argv[2:]:
    t = json.load(open(path)); ms = [e["message"] for e in t["rawSessionEntries"] if e.get("type") == "message"]
    args = {}
    for m in ms:
        if m["role"] == "assistant":
            for c in m["content"]:
                if c.get("type") == "toolCall": args[c["id"]] = c.get("arguments", {})
        if m["role"] == "toolResult" and m.get("toolName") == "neurajl" and m.get("isError"):
            s = text(m["content"])
            if re.search(sys.argv[1], s):
                code = args.get(m.get("toolCallId"), {}).get("code", "")
                loc = re.search(r"line (\d+):(\d+)", s)
                snippet = ""
                if loc:
                    ln, col = int(loc.group(1)), int(loc.group(2))
                    lines = code.split("\n")
                    if ln - 1 < len(lines): snippet = lines[ln - 1][max(0, col - 60):col + 40]
                msg = re.sub(r"\s+", " ", s[:260])
                print(f"[{path.split('/')[-2]}] {msg}\n    near: {snippet!r}\n")
