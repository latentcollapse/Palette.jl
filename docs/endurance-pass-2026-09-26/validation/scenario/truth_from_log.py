import re, json, statistics, collections, sys
cls=collections.Counter(); ub=collections.Counter(); per_min=collections.defaultdict(lambda:[0,0]); users=collections.defaultdict(list)
import datetime
for line in open(sys.argv[1]):
    ts, rest = line.split(" ",1); f=dict(kv.split("=",1) for kv in rest.split())
    st=int(f["status"]); cls[f"{st//100}xx"]+=1; ub[f["user"]]+=int(f["bytes"])
    m=ts[11:16]; per_min[m][0]+=1; per_min[m][1]+= st>=500
    users[f["user"]].append(datetime.datetime.fromisoformat(ts.replace("Z","+00:00")))
rates={m:b/a for m,(a,b) in per_min.items()}; med=statistics.median(rates.values())
anom=sorted(m for m,r in rates.items() if r>3*med)
sessions=0; durs=[]
for u,ts in users.items():
    ts.sort(); start=ts[0]; prev=ts[0]
    for t in ts[1:]:
        if (t-prev).total_seconds()>=1800: sessions+=1; durs.append((prev-start).total_seconds()); start=t
        prev=t
    sessions+=1; durs.append((prev-start).total_seconds())
print(json.dumps({"classes":cls,"top_user":ub.most_common(1),"median_5xx_rate":med,"anomalous_minutes":anom,"sessions":sessions,"median_session_s":statistics.median(durs)}))