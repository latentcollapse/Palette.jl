#!/usr/bin/env bash
# Positive control: p2's seven fixes, then the 0.5 features from reference/.
set -e; S=$(cd "$(dirname "$0")" && pwd)
bash "$S/p2_reference_fix.sh" "$1"
cp -r "$S/reference/." "$1/"
