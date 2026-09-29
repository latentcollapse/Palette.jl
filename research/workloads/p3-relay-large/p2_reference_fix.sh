#!/usr/bin/env bash
# Positive control: the six intended fixes.
set -e; cd "$1"
sed -i 's/let raw: f64 = r.weight \* r.hits;/let raw: f64 = r.weight * r.hits as f64;/' core/src/score.rs
sed -i 's/(0..xs.len() - n)/(0..=xs.len() - n)/' core/src/score.rs
sed -i 's/\${job.id}/${job.jobId}/' api/src/client.ts
sed -i 's/String(d.getUTCMonth())/String(d.getUTCMonth() + 1)/' api/src/client.ts
sed -i 's/if i <= extra/if i < extra/' planner/src/planner.ml
sed -i "s/WHERE state = /WHERE status = /" db/queries/stuck_jobs.sql
python3 - "$1/core/src/events.rs" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = """        let v = self.batches.load(Ordering::Relaxed);
        let _checksum = checkpoint_digest(v);
        self.batches.store(v + 1, Ordering::Relaxed);"""
assert old in s
s = s.replace(old, """        let v = self.batches.fetch_add(1, Ordering::Relaxed);
        let _checksum = checkpoint_digest(v);""")
open(p, "w").write(s)
PY
