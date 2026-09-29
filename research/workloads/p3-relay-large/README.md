# p3-relay-large: a polyglot workload built to take 20+ minutes

This is a workload for comparing operator surfaces. It was built and controlled on 2026-09-28, but no model has run it yet.

## The task

Fix existing bugs and implement a spec across five languages, in `relay`:
- a Rust core;
- a TypeScript API;
- an OCaml planner;
- SQLite state;
- a Go control tool, `relayctl`.

The bugs are seven seeded ones from p2-relay-hard, including an intermittent race in `core/src/events.rs`. It fails about 2–15% of runs.

The features are six, from `SPEC.md`:
- Rust quantiles and backoff;
- a TypeScript query-string codec;
- OCaml first-fit-decreasing packing;
- a SQL priority migration and query;
- a Go INI parser.

The model must not change any test, test script, tool script, `SPEC.md` or the `Makefile`. `tests.sha256` checks that.

## Use

```sh
./setup.sh /path/to/workspace
# give the model prompt.txt, working in that workspace, then:
./grade.sh /path/to/workspace
```

`grade.sh` builds each part clean and runs `make test-<part>` for `core`, `load`, `api`, `planner`, `db` and `ctl`. It then checks that the tests are unchanged, and runs the race test 200 times.

It needs the polyglot toolchain at `~/.neurajl-runs/toolchains/polyglot`: cargo, node/tsc, dune, go and sqlite3.

## Controls, 2026-09-28

| Control | Result |
|---|---|
| Reference solution (`reference_fix.sh`) | every stage passes; race 200/200 |
| Untouched fixture | every real stage fails (`load` always passes; it only generates noise) |
| Features only, old bugs left | the old bugs still fail |
| An edited test | `tests unchanged: no` |

Two defects were caught by these controls before any run:
- the spec and a test disagreed about indented key lines;
- `check.sh` inserted rows without naming columns, which migration 003 broke.
