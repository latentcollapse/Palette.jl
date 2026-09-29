"""Classify every failed neurajl tool result in a set of traces."""
import json, re, sys, collections, pathlib
CLASSES = [
    ("parse: string/quoting", r"ParseError[\s\S]{0,400}(\\\$|\"\"\"|string|interpolat|invalid escape|character literal|unterminated|cannot juxtapose string)"),
    ("parse: other", r"ParseError|syntax:"),
    ("kernel stopped/revived", r"kernel stopped|NEW kernel|worker process exited"),
    ("timeout", r"timed out|turn timeout|interrupted at the .* limit|InterruptException"),
    ("UndefVarError", r"UndefVarError"),
    ("MethodError", r"MethodError"),
    ("BoundsError", r"BoundsError|StringIndexError"),
    ("shell/process failed", r"ProcessFailedException|failed process|exit code|command not found"),
    ("test failure", r"Test Failed|Some tests did not pass|TestSetException"),
    ("LoadError/include", r"LoadError"),
    ("ArgumentError", r"ArgumentError"),
    ("KeyError", r"KeyError"),
    ("SystemError/IO", r"SystemError|IOError|no such file"),
    ("assertion/other error", r"Error"),
]
def text(c): return "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
tot = collections.Counter(); calls = 0; errs = 0; examples = collections.defaultdict(list); lens = []
for path in sys.argv[1:]:
    t = json.load(open(path)); ms = [e["message"] for e in t.get("rawSessionEntries", []) if e.get("type") == "message"]
    args = {}
    for m in ms:
        if m["role"] == "assistant":
            for c in m["content"]:
                if c.get("type") == "toolCall" and c.get("name") == "neurajl": args[c["id"]] = c.get("arguments", {})
        if m["role"] == "toolResult" and m.get("toolName") == "neurajl":
            calls += 1; s = text(m["content"]); a = args.get(m.get("toolCallId"), {})
            lens.append(len(a.get("code", "")))
            if m.get("isError"):
                errs += 1
                for name, rx in CLASSES:
                    if re.search(rx, s):
                        tot[name] += 1
                        if len(examples[name]) < 3: examples[name].append((pathlib.Path(path).parent.name, s[:300].replace("\n", " | "), a.get("code", "")[:200].replace("\n", " | ")))
                        break
print(f"neurajl calls {calls}, errors {errs} ({100*errs/max(calls,1):.1f}%), median code chars {sorted(lens)[len(lens)//2] if lens else 0}")
for k, v in tot.most_common(): print(f"  {v:4d}  {k}")
if "-v" in sys.argv[0:1] or True:
    for k in [k for k, _ in tot.most_common(5)]:
        print(f"\n== {k}")
        for run, s, code in examples[k]: print(f"  [{run}] {s}\n      code: {code}")
