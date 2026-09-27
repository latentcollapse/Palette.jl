import json, subprocess, sys, pathlib
ws = pathlib.Path(sys.argv[1]) / "python"
cases = json.loads((pathlib.Path(sys.argv[2]) / "cases.json").read_text())
sys.path.insert(0, str(ws))
import textkit
ok = 0
for fn, args, kw, exp in cases:
    try:
        ok += getattr(textkit, fn)(*args, **kw) == exp
    except Exception:
        pass
try:
    wp = textkit.wrap_paragraphs("one two three\n\nfour five", 9) == "one two\nthree\n\nfour five"
except Exception:
    wp = False
suite = subprocess.run([sys.executable, "-m", "unittest"], cwd=ws, capture_output=True, text=True).returncode == 0
print(f"textkit: golden {ok}/{len(cases)}, wrap_paragraphs {'ok' if wp else 'WRONG'}, suite {'pass' if suite else 'FAIL'}")
