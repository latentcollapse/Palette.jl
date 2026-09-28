import random, datetime, sys
random.seed(10)
eps = ["/api/items/{}", "/api/users/{}/orders", "/api/search", "/health", "/api/cart/{}", "/static/app.js", "/api/items/{}/reviews"]
users = [f"u{i}" for i in range(1, 900)]
t = datetime.datetime(2026, 9, 1, 0, 0, 0)
bad = {random.randrange(0, 1440) for _ in range(6)}
lines = []
for i in range(300000):
    t += datetime.timedelta(milliseconds=random.expovariate(1/288))
    ep = random.choice(eps)
    path = ep.format(random.randrange(1, 5000)) if "{}" in ep else ep
    minute = t.hour * 60 + t.minute
    st = random.choices([200, 201, 304, 404, 500, 503], [80, 5, 8, 4, 2, 1] if minute not in bad else [50, 2, 3, 5, 25, 15])[0]
    lat = max(1, int(random.lognormvariate(4 if "search" not in ep else 5.2, 0.6)))
    lines.append(f"{t.isoformat(timespec='milliseconds')}Z ip=10.0.{random.randrange(256)}.{random.randrange(256)} user={random.choice(users)} method={'GET' if random.random()<0.85 else 'POST'} path={path} status={st} latency_ms={lat} bytes={random.randrange(200, 90000)}")
open(sys.argv[1], "w").write("\n".join(lines) + "\n")