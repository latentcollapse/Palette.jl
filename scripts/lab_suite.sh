#!/usr/bin/env bash
# Full lab suites against a worktree and its own project and depot.
#   scripts/lab_suite.sh <worktree> <rnd-dir with project/ and depot/> [python|rust]
# rust: every session, worker and broker in the tests is the worktree's Rust host (host/target/release/neurajl-host).
set -u
WT=$1; RD=$2; HOST=${3:-python}
for d in "$RD/depot" "$RD/project"; do [ -d "$d" ] || { echo "missing $d"; exit 2; }; done
cd "$WT"
export JULIA_DEPOT_PATH=$RD/depot NEURAJL_JULIA_BIN=$HOME/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia NEURAJL_TEST_PROJECT_DIR=$RD/project
if [ "$HOST" = rust ]; then
  export NEURAJL_HOST_BIN=$WT/host/target/release/neurajl-host
  [ -x "$NEURAJL_HOST_BIN" ] || { echo "missing $NEURAJL_HOST_BIN"; exit 2; }
  "$NEURAJL_HOST_BIN" prewarm --project-dir "$RD/project" 2>&1 | tail -1
else
  unset NEURAJL_HOST_BIN
  python3 security/prewarm_depot.py --project-dir "$RD/project" 2>&1 | tail -1
fi
echo "host: $HOST"
for t in test_revival test_session_cli test_session test_authority test_host_bridge; do
  echo "== $t"; timeout 2400 python3 -m unittest security.$t 2>&1 | grep -E "^Ran|^OK|skipped|FAILED|^FAIL:|^ERROR:"
done
echo "== julia"; J=$(timeout 1800 "$NEURAJL_JULIA_BIN" --project=. -e 'using Pkg; Pkg.test()' 2>&1)
echo "test summaries: $(grep -cE "Test Summary" <<<"$J")"; grep -E "Test Failed|Error During Test|tests passed|did not pass" <<<"$J" | head -5
echo "== done"
