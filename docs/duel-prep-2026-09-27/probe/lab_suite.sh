#!/usr/bin/env bash
# Full lab suites against a worktree and its own project and depot.
#   lab_suite.sh <worktree> <rnd-dir with project/ and depot/>
set -u
WT=$1; RD=$2
cd "$WT"
export JULIA_DEPOT_PATH=$RD/depot NEURAJL_JULIA_BIN=$HOME/.julia/juliaup/julia-1.12.6+0.x64.linux.gnu/bin/julia NEURAJL_TEST_PROJECT_DIR=$RD/project
python3 security/prewarm_depot.py --project-dir "$RD/project" 2>&1 | tail -1
for t in test_revival test_session_cli test_session test_authority; do
  echo "== $t"; timeout 2400 python3 -m unittest security.$t 2>&1 | grep -E "^Ran|^OK|FAILED|^FAIL:|^ERROR:"
done
echo "== julia"; timeout 1800 "$NEURAJL_JULIA_BIN" --project=. -e 'using Pkg; Pkg.test()' 2>&1 | grep -cE "Test Summary" | sed 's/^/test summaries: /'
echo "== done"
