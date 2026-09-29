#!/usr/bin/env bash
# setup.sh <dir>: a fresh task workspace, the fixture as one commit (the model sees a clean git tree).
set -e; S=$(cd "$(dirname "$0")" && pwd); W=$1
mkdir -p "$W" && cp -r "$S/fixture/." "$W/"
cd "$W" && git init -q && git add -A && git -c user.name=relay -c user.email=relay@example.invalid commit -qm "relay 0.5.0-pre"
