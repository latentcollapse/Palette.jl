import json,sys,re
for run in sys.argv[1:]:
    t=json.load(open(run+"/trace.json")); m=t["messages"]
    last_a=None; rows=[]; calls={}
    for x in m:
        if x["role"]=="assistant":
            last_a=x["timestamp"]
            for c in x["content"]:
                if c["type"]=="toolCall": calls[c["id"]]=(c["name"],(c.get("arguments") or {}).get("code","") or "")
        elif x["role"]=="toolResult" and last_a:
            nm,code=calls.get(x["toolCallId"],("?",""))
            rows.append((nm,(x["timestamp"]-last_a)/1000,code))
    tool=sum(r[1] for r in rows if r[0]=="neurajl"); wall=(t["ended"]-t["started"])/1000
    slow=[(i+1,round(d,1),c[:70].replace("\n"," ")) for i,(n,d,c) in enumerate(rows) if d>5]
    print(f"{run.split('/')[-1]:28} wall={wall:5.0f}s neurajl_tool={tool:5.0f}s first={rows[0][1] if rows else 0:.1f}s n={len(rows)}")
    for s in slow: print("    slow",s)
