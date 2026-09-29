"""Which failed neurajl calls broke because a string literal ended early?
Test: parse the code with Julia and see whether the parse differs from the
intended one... simpler and exact: count calls whose code has an odd structure:
a line that is only three quotes (a docstring delimiter) inside a triple-quoted
literal that the model opened with `= \"\"\"` or `(\"\"\"`."""
import json, re, sys, collections
def text(c): return "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
fails = collections.Counter(); total = collections.Counter()
for path in sys.argv[1:]:
    t = json.load(open(path)); ms = [e["message"] for e in t["rawSessionEntries"] if e.get("type") == "message"]
    args = {}
    for m in ms:
        if m["role"] == "assistant":
            for c in m["content"]:
                if c.get("type") == "toolCall" and c.get("name") == "neurajl": args[c["id"]] = c.get("arguments", {}).get("code", "")
        if m["role"] == "toolResult" and m.get("toolName") == "neurajl":
            code = args.get(m.get("toolCallId"), "")
            # a docstring line (only three quotes) while inside an assigned triple-quoted literal
            nested = bool(re.search(r'(=|\(|\*)\s*"""[^\n]*\n(?:(?!""").*\n)*?\s*"""\s*\n\s{0,4}\S', code)) and code.count('"""') >= 4
            key = "nested" if nested else "other"
            total[key] += 1
            if m.get("isError"): fails[key] += 1
for k in total: print(f"{k:7s} calls {total[k]:5d}  failed {fails[k]:4d}  ({100*fails[k]/total[k]:.1f}%)")
