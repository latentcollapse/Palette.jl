# Pre-duel audit and turbochargers (2026-09-28)

Before the NeuraJL-vs-IPython duel on a polyglot repo, three changes were built into NeuraJL, and every duel stress point was probed. Everything was run on lab branch `rnd/turbo`, in the duel's toolchain environment with network on, as the duel will have it.

## The design rule

Luna uses what lands in front of it and almost nothing it has to go looking for:
- 0 calls to `Neura.output`, `kernelinfo` or `varinfo` across the endurance runs;
- a hint moved 1 run in 4;
- the named payload was adopted because the tool description showed the exact edit form.

So each change here works **inside results the model already reads**, with nothing to adopt.

## 1. A digest of long build and test output (`src/digest.jl`)

**The problem.** A failing `cargo`, `tsc`, `dune`, `go` or test run can print thousands of lines, and the host cuts a result's middle past 12,000 characters. The model then sees the build log's start and the summary, not the errors.

**The change.** When a call's output is over 4,000 characters and holds recognisable failures, a digest opens the result:
- counts by kind;
- the first 12 distinct errors and failing tests, with file:line and message;
- then the whole output, unchanged.

Recognised shapes:
- rustc/cargo errors and warnings, and cargo test failures with their panic location;
- tsc, plain and pretty;
- OCaml/dune `File … Error:` with its continuation lines;
- go build, and go test with the `_test.go:N:` reason;
- unittest, with the exception and the traceback's last frame;
- pytest `FAILED`;
- jest and vitest `●`;
- node:test `✖`;
- Julia `Test Failed at`.

ANSI colour codes are stripped from all output.

**Tests.** `test/runtests.jl` "Output digest", 16 assertions, run on **real output captured from each toolchain** (`test/fixtures/digest/`). Negative cases:
- short output is unchanged;
- long output with no failures is unchanged;
- a flood of failures is capped.

## 2. Job and process awareness (`src/turn.jl`, `src/revival.jl`)

**The problem.** A model that started a server or a long build heard nothing of it again unless it looked. After a kernel death the revival report said nothing about processes, so a model would assume its server was still up. A failed task was also reported as `ans` rather than by the name the model gave it.

**The change:**
- A line at the start of a result, printed only when something changed: `[background jobs: running: task \`job\`, \`python3 -m http.server …\` (pid 24); finished: task \`build\` (fetch(build) returns its value)]`. Processes are the kernel's children and daemons adopted by the sandbox's init, found through the sandbox's own `/proc`.
- Snapshots record running processes. The revival report names them: "Background processes stopped with the previous kernel: `…`. Start them again if you need them."
- Tasks are reported under the model's own name, before `ans`.

**Tests:**
- `test_background_jobs_are_named_when_they_change`: running, unchanged (not repeated), finished, nothing running any more, and a failure named `bad` rather than `ans`;
- `test_background_processes_that_stopped_with_the_kernel_are_named`.

## 3. A workspace map (`src/workspace_map.jl`, NP2 `neurajl.ts`)

**The problem.** After every compaction the model rebuilt its picture of the repo from scratch. That picture is what a messy polyglot repo tests most.

**The change.** A compact map opens the session's first result and the first result after each compaction, and the compaction note says it is coming. It holds:
- languages, and where each lives;
- build and test entry points: `Cargo.toml` (workspace), `package.json` scripts, `dune-project`, `go.mod`, `pyproject`, Makefile targets;
- git branch and changed files;
- the most recently modified files.

It uses `git ls-files` where possible, skips vendor and build trees (`node_modules`, `target`, `_build` …) even in git's untracked list, and is capped at 2,000 characters. NP2 option `workspaceMap`, or `NEURAJL_WORKSPACE_MAP=0`, turns it off for an A/B.

**Tests:**
- "Workspace map" (7 assertions);
- `test_the_workspace_map_opens_a_result_when_the_host_asks`;
- NP2 `the workspace map opens the first result and the first after a compaction`.

## Audit probes (`probe/audit_probe.py`), all 15 pass

| # | Probe | Result |
|---|---|---|
| 1a | A server on loopback, reached from the kernel | 200 |
| 1b | The jobs line names the server | yes |
| 1c | Real SIGKILL of the kernel: the revival names the stopped server | yes, and also "Call 3 completed after this state was saved": the kill came before that call's snapshot finished, reported honestly |
| 1d | The port is free to restart after the kernel died | 200 |
| 2a | 300 runs of a flaky command in one call | 1.0 s |
| 2b | 3,000 runs as a background job, collected later | yes |
| 2c, 2d | A runaway background process, and a task, can be stopped | yes |
| 3a | An 800-line build log opens with its digest | yes |
| 3b | ANSI stripped; invalid UTF-8 survives the protocol | yes |
| 4a | Map of a 20,000-file repo, in the session's first result | 0.47 s |
| 4b | Per-call overhead with 20,000 files | 0.0 s |
| 4c | `rg` across the repo | yes |
| 5a | Named payload: 1 MB text, triple quotes and `$`, a unicode key | exact |
| 5b | `bash(PAYLOAD)`: `set -e` stops, and the exit code is reported | yes |

## Defects found and fixed during the audit

- **The map took 8.7 s on its first call** in a fresh kernel, because its code compiled cold on the session's first call.
  - The map, digest, jobs line and process scan are now in the precompile workload.
  - First call is now 0.9 s on a 20,000-file repo, against 0.2 s warm.
- **The map counted `node_modules`.** git lists untracked files, so the skip list now also applies to git's output.
- **The map found only one Makefile target.** The regex was missing its multiline flag.
- **The map crashed on files with no extension** (`Makefile`).
- **`Neura.output(n)` held the map and the digest.** Retained output is now what the call printed; the additions go only into the result.
- **Task failures were named `ans`.**
- **Test hygiene.** The existing "EphemeralTool isolation" testset pirates `Base.show(::Int)` for the rest of the test process, to demonstrate same-process escape. Later testsets see every integer printed as `PWNED2`. The new testsets run before it. The piracy itself is deliberate, and stays.

## Probe failures that were the probe's fault (all of them quoting traps a model can hit)

- `curl -w %{http_code}` inside a Julia backtick command: braces are special in `Cmd`, and the kernel's existing hint named the problem.
- `$((RANDOM % 7))` inside a Julia string: interpolation. This is what `payload` is for.
- A shell script nested in `bash("…")`: the escaping broke. `bash(PAYLOAD)` avoids it.

## Earlier steps in this pass

- **Step 1:** environment parity (`README.md` in this directory).
- **Step 2:** named payload by default. NP2 `90fd54a31` teaches `bash(PAYLOAD)` for multi-line scripts.
- **Step 3, replaced.** The IPython tool has no per-call timeout, so a NeuraJL-only one would make the limits unequal. Both keep 60 s. NeuraJL's description now teaches background jobs (`job = @async sh"…"`, then `fetch(job)` later), verified with a 70 s job across calls.
- **Step 4:** snapshot-yield merged into lab `main`.
