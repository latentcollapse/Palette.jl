# NeuraJL Architecture Gap Report — 2026-09-26

**Question.** What important capabilities or abstractions are still missing from NeuraJL that would let a long-horizon coding agent do more work with less orchestration, reconstruction, serialization, and context?

**Scope.** This is an architecture pass, not a scored experiment:
- Nothing was compared against NeuraBash.
- No hidden task was touched.
- No winner is declared.

Luna (`openai/gpt-6-luna` through NIRA-Prime-NeuraJL) served as the instrument.

**Commits.**

| Repo | Commit | Change |
|---|---|---|
| lab | `98174d6` | reload, output retention, redirect fix, precompiled turn path |
| lab | `f5334b2` | workspace package first, sh-quote message |
| lab | `d006eba` | test-run display |
| NP2 | `4767842a0` | eager kernel start, elision notice, tool description, stale timeout test |

Codex's uncommitted `scripts/abc-agent.ts` was left alone.

**Tests at the end.** All suites pass:

| Suite | Result |
|---|---|
| `security/test_session_cli.py` | 43 pass (was 37; 6 new, each with a red control) |
| `test_session.py` | 11 pass |
| `test_authority.py` | 27 pass |
| `Pkg.test()` | passes |
| NP2 `neurajl-substrate-modes.test.ts` | 6 pass, against a real kernel |
| `tsgo --noEmit` | clean |

## Evidence base

- **Mined traces:** 12 earlier NeuraJL runs (S1–S6, 184 calls).
- **New scenarios:** two open-ended coding scenarios written for this pass. They are in `architecture-pass-2026-09-26/scenarios/`, and neither is a comparison task.
  - **S8 `s8-julia-pkg`:** OrderedCollections 2.0.1 with three injected bugs. The task is to fix them, then add an exported, documented and tested `move_to_end!`. The suite has 25,972 tests.
  - **S9 `s9-python-pkg`:** a `textkit` package (stdlib `textwrap` and `shlex`) with three injected bugs and 61 golden cases. The task is to fix them, then add an exported, tested `wrap_paragraphs`.
- **Luna runs:** 12 in total, S8 and S9 before and after the changes, plus one S2 regression run.
  - b1/b2: before any change.
  - c1/c2: after the first round (reload, output retention, faster start).
  - d1/d2: after the second round (workspace package first, sh-quote message).
  - Per-call summaries are in `architecture-pass-2026-09-26/run-summaries.txt`.
- **Probes:** direct probes of the session bridge (`tools/probe.py`) for startup, JIT, threads, background work and staleness.
- **JIT profile:** `--trace-compile-timing` profiles of the session loop.

A caveat about the S8 outcomes: 5 of 6 S8 runs ended at the harness's 60-request cap. S8 runs start 2–4 RLM subagents, and their model requests count against the same cap. That is harness policy. It confounds "did the task finish", so this report reads behaviour, not outcomes.

## 1. Remaining friction map

Status legend: **fixed** = changed and tested in this pass; **open** = still present; **model** = the environment is fine and the choice is the model's prior; **harness** = outside NeuraJL.

| Friction | Evidence | Status |
|---|---|---|
| Editing a workspace package left the kernel running the old code. `using` a loaded package does nothing. | Probe: after an edit that fixed `get`, the kernel still returned `:missing`. Both baseline S8 runs abandoned in-kernel tests after one run and moved to `julia` subprocesses. | **fixed**: the kernel now reloads edited workspace packages. |
| In-kernel tests loaded the kernel's copy of the package, not the workspace's. | S8 c1 appended the workspace to `LOAD_PATH`. All 25,972 tests passed against OrderedCollections from the kernel's own environment (DataFrames needs it). Luna found out 9 calls later with `pathof`. | **fixed**: when the workspace is itself a package, it comes first in `LOAD_PATH`. |
| Output the host elided was gone. | In the baseline, 40 of 309 results were elided. S8 b1 re-ran the 53s suite solely to capture output it had already printed (calls 9 and 10). S8 b2 spent 3 calls trying to capture it. | **fixed**: `Neura.output(n)` returns everything a call printed. Luna never used it (0 uses in 22+ elisions). |
| `redirect_stdout(x) do … end` inside a turn threw, or lost the rest of the turn's output. | S8 b2 calls 17, 18 and 21 all printed nothing. The kernel's `FdWriter` had no restore method. | **fixed** |
| A passing test run's value displayed as a 14,000–25,000 character struct dump. | S8 c1 and c2: 42k characters across 3 runs, all elided. | **fixed**: now one line of counts; the testset stays in `ans`. |
| Startup: about 8s from spawn to first reply. First call 11.7–12.7s in 3 of 4 baseline runs (LLM time included). | `--trace-compile-timing`: 7.0s of runtime JIT in the unprecompiled session script. | **fixed**: 3.4s, and the kernel starts with the session. First call is now 3.2–4.4s including LLM time. |
| A `"` inside `sh"…"` gave an opaque `MethodError` for `@sh_str`. | S8 b2 call 46; S9 c1 call 14. | **fixed**: the error now explains itself. In S9 d1, Luna switched to `payload` on the next call. |
| Foreign source text inside Julia string literals (`$`, `\n`, `"""`). | 10 ParseErrors in 309 baseline calls, 7 of them `$`-related. S9 b2 spent 2 calls on escape levels. | **open / model.** `payload` and `bash(PAYLOAD)` avoid it. Luna reaches for them only after an error names them. |
| Test output volume. The model writes capture-and-filter code for every test run. | S8 d1 used `sh"julia … > log; grep …"`. S8 d2 used `redirect_stdout` to a file, then `filter`. | **model.** Both are one line of ordinary Julia or shell. See the rejected `TestRun` below. |
| Choosing where tests run. | After the fixes, 2 of 4 S8 runs tested in the kernel (c2, d2) and 2 used the CLI (c1 after the `LOAD_PATH` trap, d1 by choice). | **model.** Both are now correct; the CLI costs 40–50s a run against 10s warm in the kernel. |
| One line of noise, `SYSTEM: caught exception … failed Task notice`, the first time a workspace package precompiles in the kernel. | 3 S8 runs. It appears only through `Base.require` with the turn's stderr. Overriding `errormonitor` did not catch it, and the root cause was not found. | **open**, cosmetic. The package loads correctly. |
| RLM subagent requests exhaust the 60-request cap. | 5 of 6 S8 runs. | **harness** |

## 2. Missing abstractions (what the evidence says is actually missing)

Only one abstraction was missing in a way that changed behaviour: **the world must stay current with the files it is built from.** NeuraJL's thesis is a persistent computational world. For coding work, the thing being built lives on disk, and a persistent world that silently diverges from disk is worse than no persistence: it gives confident wrong answers. Luna's move to `julia` subprocesses was the rational response. It was not foolishness.

Two further gaps belong to the same class:
- **Which code is loaded.** The workspace package has to win over the kernel's own copy.
- **What the world last printed.** Output must not vanish because the host elided it.

The coding-native objects the brief listed — Repo, SourceFile, AST, SearchResults, GitDiff, TestRun, Diagnostics, DependencyGraph, BuildResult, Process — were checked against the traces. None was reconstructed across calls in a way a new type would remove:
- **Search** is `sh"grep …"` once, and the result is read, not kept.
- **Git** was unavailable: no scenario workspace is a repository, and Luna runs `git status` anyway in almost every run.
- **Test results** already exist as Julia's `DefaultTestSet`, and processes as `Process` and `Task`.
- **Parsed files and repo maps** were never held: Luna re-reads files by line range, which is cheap. It did define and reuse its own helpers (a `lines(file, a, b)` function in S8 c2), which is the persistent world working as intended.

## 3. Proposed changes, ranked by leverage

| # | Change | Leverage | Status |
|---|---|---|---|
| 1 | Reload edited workspace packages before each call and before `include`. | Highest. It turns the kernel into a correct place for the edit→test loop: 10s warm test runs instead of 40–50s CLI runs, and no stale answers. | done |
| 2 | Workspace package first in `LOAD_PATH`. | High. It removes a silent-wrong-answer trap that #1 would otherwise invite. | done |
| 3 | Precompiled turn path, plus eager kernel start in NP2. | High for short tasks. First reply at 3.4s instead of 8s, and it overlaps the model's first request. | done |
| 4 | Test-run value shown as counts. | Medium. It removes 14–25k characters from every passing in-kernel suite run. | done |
| 5 | `redirect_stdout` restore. | Medium. It is a correctness bug on the in-kernel test path. | done |
| 6 | `sh"…"` quote message. | Low to medium: 2 in 8 runs, and it steers to `payload`. | done |
| 7 | Retained output via `Neura.output(n)`. | Low as observed: 0 adoption. Kept because it is the only way to recover elided output without recomputing, and it costs at most 64 × 256 KiB. | done |

## 4. Changes implemented

Each change passes the brief's four tests: observed friction, the boundary it removes, why Julia or the shell alone falls short, and how it stays simple.

**4.1 Workspace-package reload** (`src/Neura.jl`: `refresh_workspace_packages!`, `reload_package!`).
- **Friction:** in S8 b1/b2, 2 of 2 runs moved tests to subprocesses after the first in-kernel run. The probe showed stale results.
- **Boundary removed:** kernel → subprocess → log file → re-read.
- **Why Julia alone falls short:** `using` does nothing for a loaded package. A plain `include` of the root file creates a nested module. Revise.jl would fix it, but it depends on OrderedCollections, Preferences, JuliaInterpreter and others. Loading it would shadow a workspace OrderedCollections (exactly S8), and outside the REPL it still needs `revise()` called by hand.
- **How it stays simple:** no new command.
  - Before each call, and inside the kernel's `include`, any package whose `pathof` lies in the workspace and whose `.jl` sources changed is re-evaluated in place, and one line says so.
  - A failed reload says the package keeps its old code.
  - Docstring-replacement warnings are filtered.
  - Limits, documented in `OPERATOR_SURFACE.md`: methods deleted from the source stay defined, and `__init__` does not run again.
- **Measured:** in-kernel `include("test/runtests.jl")` takes 49.6s the first time (compile) and 10.1s after. The CLI takes 38.8–53s every time.

**4.2 Workspace package first in `LOAD_PATH`** (`workspace_package_first!`).
- **Friction:** S8 c1 got a silent all-pass against the wrong package. The other three S8 runs had to know to `pushfirst!`.
- **Boundary removed:** the model no longer has to know that the kernel's environment is ahead of the workspace.
- **How it stays simple:** at kernel start, a workspace whose `Project.toml` has a name and uuid is put first, which is what `julia --project=.` does. Workspaces that are not packages are untouched.

**4.3 Retained output** (`Neura.OUTPUTS`, `Neura.output(n)`, `call` in each response, NP2 elision notice).
- **Friction:** 40 of 309 results were elided, and a 53s suite was re-run just to see its failures.
- **How it stays simple:** the accessor lives on the existing `Neura` handle rather than as a bare `output` binding, which would have stolen a common variable name. The elision notice names the exact call, e.g. `Neura.output(12) returns everything this call printed`. No doctrine is needed beyond the notice.

**4.4 `redirect_stdout` / `redirect_stderr` inside a turn** (`(::RedirectStdStream)(::FdWriter)`). A plain bug fix: Base could not restore to the turn's writer. `redirect_stdout(devnull) do … end`, the most common Julia idiom for this, threw.

**4.5 Precompiled turn path** (`src/turn.jl`, `src/precompile_workload.jl`, NP2 eager start).
- **What moved:** the turn machinery (JSON, output capture, deadline, value shaping, `execute_turn`) left the unprecompiled `session_loop.jl` for the package, with a workload that runs six representative turns.
- **Traps handled along the way:**
  - Precompilation refuses evaluation into a foreign module, so the workload runs in a `baremodule` of the package's own.
  - Load-time constants such as `tempdir()`, the namespace check and the kernel name became runtime lookups, so the build machine's values are never baked into the image.
  - The closure behind `capture_output` is boxed so it compiles once.
- **Warm-up:** the post-HELLO warm-up now hits `UndefVarError`, the error models make most, whose message runs the REPL's hint handlers.

| Measure | Before | After |
|---|---|---|
| Runtime JIT | 7.0s | 1.3s |
| HELLO | 3.8–6.5s | 1.5s |
| First turn right after HELLO | 3.5–4.1s | 1.9s |
| First `UndefVarError` | 0.49s | 0.00s |

- **NP2 eager start:** the kernel now starts when the session's tools are built. With a 3–4s model request in front of it, the first call's result came back in 0.06s.
- **Cost:** Neura's precompile grew from about 1s to about 9s. That is paid once per depot build (`prewarm_depot.py`).

**4.6 Test-run display** (`testset_summary`). A passing `DefaultTestSet` now displays as, for example, `Test.DefaultTestSet "OrderedCollections": 25972 passed, 0 failed, 0 errored, 0 broken (41.0s)`. The object itself stays in `ans`, so this is a preview of a live object, not a new type.

**4.7 `sh"…"` quote message** (`@sh_str(script, suffix)`). The message says the command ended early, names the stray word, and names `\"` and `bash(PAYLOAD)`. Evidence that it steers: in S9 d1, the call after the message used `payload`.

**4.8 NP2 test repair.** The timeout test asserted the old contract, that every timeout stops the kernel. It had been failing since lab `1fa0a2a` made waiting work interruptible. It now checks both halves: a wait is interrupted and the kernel kept, and compute that never yields stops the kernel.

## 5. Changes rejected, and why

| Candidate | Why rejected |
|---|---|
| **Revise.jl, preloaded** | It would shadow OrderedCollections and Preferences for any workspace containing them, and outside the REPL it still needs a manual `revise()`. 4.1 covers the observed case with no dependencies. |
| **An edit/patch primitive** (`edit!(path, old => new)`) | There were 20 read→`replace`→write edits in 309 baseline calls, and Luna guarded 17 of them itself. When an anchor failed, its own guard caught it. The real edit pain was escape levels inside Julia literals, which a new function still receives as Julia literals. `payload` and `bash(PAYLOAD)` remove that boundary; a new function would not. |
| **`TestRun` / `Diagnostics` / `BuildResult` types** | Julia's `DefaultTestSet` is the live object. After 4.4 and 4.6, the in-kernel path needs one line of ordinary Julia to filter failures, and Luna wrote that line unprompted (S8 d2). A new type is vocabulary to learn with no friction behind it. |
| **`Repo` / `GitDiff` / `SearchResults` / `DependencyGraph`** | No reconstruction was observed. `grep` results are read once. No workspace is a git repository. The dependency graph in S1 was built once and reused as a binding, which already works. |
| **Structured shell results beyond `ShellResult`** | `ShellResult` fields were used 0 times in 184 baseline calls. Luna prints, then reads. More structure would go unused. |
| **A job abstraction** | Julia already has one, and it works here. A yielding `@async` task progressed between calls (180 ticks in 2s of idle). Julia 1.12 gives the kernel an interactive thread, so `Threads.@spawn` compute runs on the default thread beside the turns without blocking them. Background `run(…; wait=false)` processes survive across calls. Nothing needs adding. |
| **More threads (`-t auto`)** | Warm CSV read plus `groupby` ran 2.5× faster with 8 threads (0.30s → 0.12s), but no run showed data compute as a bottleneck. Recorded as available headroom: a one-line change if a data-heavy task shows the need. |
| **A sysimage** | The package-image workload brought runtime JIT to 1.3s. What remains of the 1.5s HELLO is process start plus package load (about 0.8s, measured), the depot clone (0.3s) and bwrap. A sysimage costs minutes and hundreds of MB per Neura change, to save a fraction of a second. |
| **`using Printf` preloaded** | One run hit it 3 times. The hint already names Printf, and the REPL does not preload it either. |

## 6. Short-horizon improvements

- Spawn to first reply: about 8s → 3.4s. With eager start, the model's first request usually hides it entirely.
- First errors are fast: `UndefVarError` 0.00s, others about 0.3s.
- `redirect_stdout` works inside a turn.
- A stray quote in `sh"…"` explains itself and points at `payload`.

## 7. Long-horizon improvements

- Edit → test in one world. Reload keeps the kernel correct, and warm in-kernel suite runs take 10s against 40–50s on the CLI.
- The workspace package is the one tested.
- Nothing a call printed is lost to elision.
- Passing test runs no longer flood the context.

## 8. State and context savings observed

- **Test time:** S8 b1 spent about 250s in full-suite runs: 4 CLI runs of 43–53s each, plus 1 in-kernel run. S8 d2 made no CLI suite runs; it ran per-file suites and the full suite in the kernel, with reload and capture. Warm in-kernel suite runs take 10s against 40–50s.
- **Recomputation:** the baseline re-ran a 53s suite to recover elided output. No recompute for lost output was observed after the changes.
- **Context:** the testset fix removes about 12,000–26,000 characters per passing in-kernel suite run (42k characters over S8 c1 and c2). Characters returned per S8 run:

  | Runs | Characters |
  |---|---|
  | b1 / b2 | 139k / 114k |
  | c1 / c2 | 94k / 185k (c2 includes 30k of testset dumps) |
  | d1 / d2 | 90k / 88k |

- **Tokens and wall time:** at n=2 per arm, with the request cap truncating runs, I do not claim a token or wall-time saving. The S8 wall times were 418s and 339s (b), 262s and 340s (c), and 284s and 203s (d).
- **Bindings:** reuse of bindings across calls stayed in the same range as before (0–15 of 21–45 calls).

## 9. Remaining intrinsic costs

- **Process start:** a Julia process with Neura and REPL loaded takes about 0.8s. Add the depot reflink clone (0.3s), bwrap, and a 1.9s post-HELLO warm-up that the first call waits on only when it arrives immediately.
- **First JIT of new code paths:** about 0.1–0.3s the first time a new type is displayed or a new error is shown.
- **Test compilation:** 25,972 tests took 49.6s to compile on the first in-kernel run. That is Julia's cost, identical on the CLI, and paid once per kernel instead of once per run.
- **Workspace package precompile:** about 2.2s on first load and on each CLI run after an edit. In-kernel reload skips it.
- **Non-yielding compute:** it cannot be interrupted (Julia 1.12). The kernel is killed 12s after the limit.
- **Preloaded packages:** anything the kernel itself loaded before the first call cannot be replaced by a workspace copy. Today that is Neura's own dependencies, JSON and StructUtils. `workspace_package_first!` cannot help once a module is loaded. This is a known edge, not observed.
- **Reload semantics:** methods deleted from the source stay defined, and `__init__` is not re-run.

## 10. What Luna naturally adopts vs ignores

**Adopts.**
- `sh"…"`: 0–24 calls per run, and at least 5 in all but two.
- Bindings and its own helper functions across calls.
- The in-kernel edit→test loop, once the tool description says packages reload: 2 of 4 post-change S8 runs. It read the `[reloaded …]` lines and relied on them (S8 c2 call 30, d1 call 16).
- `redirect_stdout` capture, once it worked.
- `payload`, after an error message names it (S9 d1), and for whole-file writes in S2 (5 of 12 calls).
- RLM subagents: 2–4 per S8 run.

**Ignores.**
- `Neura.output(n)`: 0 uses in more than 22 elisions. Luna recomputes, which is rational now that recomputation in the kernel is cheap, or re-reads files by line range.
- `kernelinfo()` and `varinfo()`: 0 uses in all runs, before and after.
- `ShellResult` fields: rare. Luna puts `status=$?; echo EXIT:$status` in the shell instead.
- `ephemeral`: never used.

**Is the model foolish, or is the environment making the path rational?** In every awkward pattern examined here, the environment made the path rational:
- Moving tests to subprocesses: the kernel was stale.
- Re-running suites: the output was gone.
- Three capture attempts: redirect was broken.
- Assuming all tests passed: the kernel's copy of the package shadowed the workspace's.

Where the environment is now correct, the remaining choices, such as the CLI for tests in S8 d1 or `grep` over a log, are reasonable preferences, not errors.

## The four questions

**1. What still forces the model to think about machinery instead of the task?**
- **Quoting (the largest remaining tax).** Writing Python, shell or JSON source inside Julia string literals makes Luna manage two escape languages at once. `payload` and `bash(PAYLOAD)` remove the problem, but Luna uses them only after an error points there.
- **Output volume.** Luna writes a capture-and-filter line around every test run. That is ordinary Julia or shell, and cheap, but it is machinery.
- **Harness budget.** Outside NeuraJL, the subagent-inclusive request cap shapes S8 runs more than anything in the kernel does.

**2. What would move NeuraJL's crossover point furthest toward call #1?**
- **Already done:** the precompiled turn path plus eager start. With these, shell and file work costs nothing extra from the first call: the kernel is ready before Luna's first request returns (about 3s).
- **What remains for Julia package work:** the first compile of the test suite (about 50s). It is the same on the CLI, so the kernel breaks even on the first test run and wins from the second (10s against 40–50s).
- **Going further:** earlier would mean paying test compilation before the model asks, for example by precompiling a workspace package's tests at kernel start. That spends CPU on work the model may never request. I would not do it without a task that shows a need.

**3. What single architectural addition, if any, would most increase NeuraJL's ceiling?**

Keeping the world current with the files it is built from: the workspace-package reload, now implemented with its companion (the workspace package loads first). Without it, a persistent kernel is at best a scratchpad beside the real work, and at worst a source of confident wrong answers. With it, the long-horizon edit→test loop can run inside the world.

After this pass, I do not see another single addition of that size in the evidence. The ceiling is now set by model priors (quoting, where to run tests) and harness policy, not by a missing abstraction.

**4. At what point would further work become feature creep?**

The line is:
- any addition not backed by an observed friction;
- any addition that gives the model new vocabulary to learn where Julia or the shell already serves the observed behaviour.

Concrete markers from this pass:
- **Ignored features:** `Neura.output` (0 uses), `kernelinfo`/`varinfo` (0 uses) and `ShellResult` fields (rarely used) show what happens to additions the model does not need. More retained-state features, structured shell types or coding-object wrappers would join them.
- **Remaining frictions are not environment problems:** quoting priors, test-location preference and the request cap. Engineering against them in NeuraJL would be creep.
- **Next worth doing only with new evidence:** threads, for a data-heavy task that shows compute bound; an edit primitive, only if `payload` fails to absorb the quoting cost.
