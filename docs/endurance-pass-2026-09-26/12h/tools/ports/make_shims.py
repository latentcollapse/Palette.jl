"""Positive control: Julia port files that answer every call by asking CPython (spec.py oracle)."""
import json, pathlib, sys
H = pathlib.Path(__file__).resolve().parent; g = json.loads((H / "out/goldens.json").read_text())
ws = pathlib.Path(sys.argv[1]); (ws / "ports").mkdir(parents=True, exist_ok=True)
files = {}
for name, p in g.items():
    adapters = "difflib" if name == "difflib2" else name
    f = files.setdefault(p["file"], {"module": p["module"], "fns": {}})
    for fn, _, _ in p["cases"]: f["fns"][fn] = adapters
for path, f in files.items():
    body = [f"module {f['module']}", "using JSON",
            "dec(x) = x isa AbstractDict ? (haskey(x, \"__error__\") ? error(x[\"__error__\"]) : haskey(x, \"__float__\") && length(x) == 1 ? parse(Float64, replace(x[\"__float__\"], \"inf\" => \"Inf\", \"nan\" => \"NaN\")) : Dict{String,Any}(k => dec(v) for (k, v) in x)) : x isa AbstractVector ? Any[dec(v) for v in x] : x",
            "enc(x) = x isa AbstractFloat && !isfinite(x) ? Dict(\"__float__\" => (isnan(x) ? \"nan\" : x > 0 ? \"inf\" : \"-inf\")) : x isa AbstractVector ? Any[enc(v) for v in x] : x",
            f"oracle(port, fn, args) = dec(JSON.parse(read(pipeline(`python3 {H / 'spec.py'} oracle`; stdin=IOBuffer(JSON.json(Any[port, fn, enc(Any[args...])]))), String)))"]
    body += [f"{fn}(args...) = oracle(\"{port}\", \"{fn}\", args)" for fn, port in f["fns"].items()]
    body.append("end")
    (ws / path).write_text("\n".join(body) + "\n")
print(len(files), "shim files")
