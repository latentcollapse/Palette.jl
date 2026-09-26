import json,sys
t=json.load(open(sys.argv[1]+"/trace.json")); want={int(x) for x in sys.argv[2].split(",")}; lim=int(sys.argv[3]) if len(sys.argv)>3 else 1500
calls=[];res={}
for m in t["messages"]:
    if m.get("role")=="assistant": calls+=[c for c in m["content"] if c["type"]=="toolCall"]
    elif m.get("role")=="toolResult": res[m.get("toolCallId")]=m
for i,c in enumerate(calls,1):
    if i in want:
        a=c.get("arguments") or {}
        print(f"===== [{i}] {c['name']} code:\n{(a.get('code') or json.dumps(a))[:lim]}")
        r=res.get(c["id"]); print("----- result:\n"+" ".join(x.get("text","") for x in (r or {}).get("content",[]) if x.get("type")=="text")[:lim])
