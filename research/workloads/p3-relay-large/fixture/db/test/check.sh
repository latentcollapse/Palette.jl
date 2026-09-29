#!/usr/bin/env bash
set -euo pipefail
db=$(mktemp); trap 'rm -f "$db"' EXIT
for m in db/migrations/*.sql; do sqlite3 "$db" < "$m"; done
sqlite3 "$db" "INSERT INTO jobs (id, status, rows) VALUES ('a','processing',1),('b','done',2),('c','processing',3);"
got=$(sqlite3 "$db" < db/queries/stuck_jobs.sql | tr '\n' ' ')
[ "$got" = "a c " ] || { echo "stuck_jobs returned: $got"; exit 1; }
echo "db ok"
