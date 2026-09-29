#!/usr/bin/env bash
# grade.sh <workspace>: make -k test from a clean build, and the tests unchanged. Prints one line per stage.
S=$(cd "$(dirname "$0")" && pwd); W=$1; P=$HOME/.neurajl-runs/toolchains/polyglot
export PATH="$P/bin:/usr/bin:/bin"; set -a; eval "$(python3 -c "
import shlex
for l in open('$P/task-env'):
    k,_,v=l.rstrip('\n').partition('='); print(f'{k}={shlex.quote(v)}')")"; set +a
cd "$W" || exit 1
tests_ok=yes; (sha256sum -c --quiet "$S/tests.sha256" >/dev/null 2>&1) || tests_ok=no
rm -rf core/target api/dist planner/_build
for t in core load api planner db ctl; do
  if make -s test-$t >/dev/null 2>&1; then r=pass; else r=FAIL; fi
  echo "$t: $r"
done
echo "tests unchanged: $tests_ok"
# The intermittent failure: 200 runs (it fails ~2-15% of runs, depending on load) of the event counter test, in the built test binary.
cd "$W/core" && bin=$(ls -t target/debug/deps/events-* 2>/dev/null | grep -v '\.d$' | head -1)
if [ -n "$bin" ]; then fails=0; for i in $(seq 1 200); do "$bin" --quiet >/dev/null 2>&1 || fails=$((fails+1)); done; echo "events_are_all_counted: $((200-fails))/200"; else echo "events_are_all_counted: not built"; fi
