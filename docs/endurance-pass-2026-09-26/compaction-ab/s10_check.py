import json, re, sys
truth = json.load(open(sys.argv[1]))
for run in sys.argv[2:]:
    try: rep = open(run + "/workspace-after/report.md").read()
    except OSError: print(run.split("/")[-1], "no report.md"); continue
    mins = set(re.findall(r"\b(\d\d:\d\d)\b", rep))
    got = sorted(m for m in truth["anomalous_minutes"] if m in mins)
    sess = str(truth["sessions"]) in rep.replace(",", "")
    top = truth["top_user"][0][0] in rep
    print(run.split("/")[-1], f"anomalies {len(got)}/{len(truth['anomalous_minutes'])}", "sessions ok" if sess else "sessions WRONG", "top user ok" if top else "top user WRONG")
