#!/usr/bin/env bash
set -euo pipefail
db=$(mktemp); trap 'rm -f "$db"' EXIT
for m in db/migrations/*.sql; do sqlite3 "$db" < "$m"; done
sqlite3 "$db" "INSERT INTO jobs (id, status, rows) VALUES ('old','queued',1);"
[ "$(sqlite3 "$db" "SELECT priority, queue FROM jobs WHERE id='old';")" = "0|default" ] || { echo "defaults wrong"; exit 1; }
sqlite3 "$db" "INSERT INTO jobs (id, status, rows, priority, queue) VALUES
  ('a','queued',1,5,'ingest'),('b','queued',1,9,'ingest'),('c','queued',1,5,'ingest'),('d','queued',1,1,'ingest'),
  ('e','done',1,99,'ingest'),('f','queued',1,2,'export'),('g','queued',1,-3,'default');"
got=$(sqlite3 -separator ' ' "$db" < db/queries/next_jobs.sql | tr '\n' ',')
want="default old,default g,export f,ingest b,ingest a,"
[ "$got" = "$want" ] || { echo "next_jobs returned: $got"; echo "want: $want"; exit 1; }
echo "next_jobs ok"
