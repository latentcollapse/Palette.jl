#!/usr/bin/env bash
F=/tmp/claude-1000/-mnt-d-Code-Projects/56f83ff8-67ed-443a-885c-30ae6f715177/scratchpad/njl/scenarios/s11-endurance-xxl
case "$(basename "$1")" in f2.txt) cat "$F/BATCH2.md" >> ISSUES.md;; f3.txt) cat "$F/BATCH3.md" >> ISSUES.md;; f6.txt) cat "$F/BATCH6.md" >> ISSUES.md;; esac
echo "{\"followup\": \"$(basename "$1")\", \"t\": $(date +%s)}" >> "$FOLLOWUP_LOG"
