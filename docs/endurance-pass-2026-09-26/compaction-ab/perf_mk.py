import json, sys
m = r'''using JSON; let m = JSON.parsefile(ENV["NEURAJL_STATE_DIR"] * "/manifest.json"); (m["call"], m["seconds"], round(m["bytes"] / 2^20, digits=1)) end'''
calls = [
 ("x = rand(10^6); 1", "8MB vector"),
 (m, "after vector"),
 ("using DataFrames; df = DataFrame(a = rand(10^6), b = rand(1:10, 10^6), c = string.(rand(1:100, 10^6))); 1", "df 1e6x3"),
 (m, "after df"),
 ("many = Dict(i => string(i) for i in 1:10^5); 1", "dict 1e5"),
 (m, "after dict"),
 ("for i in 1:200; eval(:($(Symbol(\"v\", i)) = $i)); end; 1", "200 small"),
 (m, "after small"),
 ("1", "noop"),
 (m, "after noop (steady state)"),
]
json.dump([{"code": c, "label": l, "pause": 4} for c, l in calls], open(sys.argv[1], "w"))
