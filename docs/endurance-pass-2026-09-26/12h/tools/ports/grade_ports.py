"""python3 grade_ports.py <workspace> [ports,...] -> one line per port plus a total; each port graded in its own julia with a timeout."""
import json, os, pathlib, re, subprocess, sys
H = pathlib.Path(__file__).resolve().parent; home = pathlib.Path.home()
ws = sys.argv[1]; g = json.loads((H / "out/goldens.json").read_text())
names = sys.argv[2].split(",") if len(sys.argv) > 2 else list(g)
env = {**os.environ, "JULIA_DEPOT_PATH": f"{home}/.neurajl-trial/depot:{home}/.julia"}
julia = str(home / ".julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia")
tp = tt = 0; lines = []
for n in names:
    total = len(g[n]["cases"])
    try:
        out = subprocess.run([julia, f"--project={home}/.neurajl-trial/project", str(H / "grade_ports.jl"), ws, str(H / "out/goldens.json"), n],
                             capture_output=True, text=True, timeout=300, env=env).stdout.strip().splitlines()
        line = out[-1] if out else f"{n}: 0/{total} (grader produced no output)"
    except subprocess.TimeoutExpired:
        line = f"{n}: 0/{total} (timed out)"
    m = re.match(rf"{re.escape(n)}: (\d+)/(\d+)", line)
    tp += int(m.group(1)) if m else 0; tt += total
    lines.append(line)
lines.append(f"ports total: {tp}/{tt}")
print("\n".join(lines))
