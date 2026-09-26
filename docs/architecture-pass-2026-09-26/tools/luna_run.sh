#!/usr/bin/env bash
# luna_run.sh SCENARIO RUN_LABEL -- run NP2 (NIRA-Prime + NeuraJL) with Luna max on one scenario.
# Harness files (prompt, trace, agent dir) live outside the workspace so the model never sees them.
set -euo pipefail
SC="$1"; LABEL="$2"
NJL=/tmp/claude-1000/-mnt-d-Code-Projects/56f83ff8-67ed-443a-885c-30ae6f715177/scratchpad/njl
NP2="/mnt/d/Code Projects/Project NIRA/The Battleground/NIRA-Prime-NeuraJL"
LAB="/mnt/d/Code Projects/Project NIRA/neurajl-operator-lab"
RUN="$NJL/runs/$SC--$LABEL"
rm -rf "$RUN"; mkdir -p "$RUN/agent" "$RUN/rlm"
WS=$(mktemp -d /tmp/njl-ws-XXXXXX)
cp -a "$NJL/scenarios/$SC/fixture/." "$WS/"
cp "$NJL/scenarios/$SC/prompt.txt" "$RUN/prompt.txt"
KEY="$RUN/key"; umask 077
python3 -c 'import json,pathlib; print(json.load(open(pathlib.Path.home()/".prime/agent/auth.json"))["openrouter"]["key"])' > "$KEY"
echo "$WS" > "$RUN/workspace_path"
cd "$WS"
set +e
env JULIA_DEPOT_PATH="$HOME/.neurajl-trial/depot" \
  ABC_PROMPT_FILE="$RUN/prompt.txt" ABC_TRACE_FILE="$RUN/trace.json" ABC_AGENT_DIR="$RUN/agent" ABC_RLM_SESSION_DIR="$RUN/rlm" \
  NEURAJL_SESSION_CLI="$LAB/security/session_cli.py" NEURAJL_PROJECT_DIR="$HOME/.neurajl-trial/project" NEURAJL_REPO_DIR="$LAB" \
  ABC_NEURAJL_MAX_OUTPUT_CHARS=12000 ABC_MODEL=openai/gpt-6-luna ABC_OPENROUTER_PROVIDER=openai \
  ABC_OPENROUTER_KEY_FILE="$KEY" \
  timeout 2400 "$NP2/node_modules/.bin/tsx" --tsconfig "$NP2/tsconfig.json" "$NP2/scripts/abc-agent.ts" > "$RUN/stdout.txt" 2> "$RUN/stderr.txt"
echo "exit=$?" > "$RUN/exit.txt"
rm -f "$KEY"
cp -a "$WS" "$RUN/workspace-after"
echo "$RUN"
