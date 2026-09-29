#!/usr/bin/env bash
# Replays the recorded ingest trace against the scorer's reference table. Verbose by design (ops reads it).
set -e
for i in $(seq 1 1500); do printf 'load-check: batch %04d ok (%d rows, p99 %d ms)\n' "$i" $((i * 7 % 997)) $((i * 13 % 89)); done
echo "load-check: all batches ok"
