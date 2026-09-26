# NeuraJL build report, 2026-09-25

This was the build stage for NP2 (NIRA-Prime + NeuraJL). It was **not a scored experiment and not a freeze**. The goal was to remove NeuraJL's accidental friction before a fair head-to-head with NeuraBash.

**Author:** Claude. **Model used as an engineering instrument:** `openai/gpt-6-luna` at reasoning max, via OpenRouter pinned to OpenAI, driven through NP2's own `scripts/abc-agent.ts`. Twelve open-ended runs across six scenarios cost $0.17 in total.

- **Scenarios:** written for this report and kept in the session scratchpad. None of them is a comparison task.
- **Hidden tasks:** no hidden comparison task was read, written or changed.
- **Scope:** NeuraBash was not touched.

**Changed repositories:**
- `neurajl-operator-lab`, this commit.
- `NIRA-Prime-NeuraJL`: `packages/coding-agent/src/core/tools/neurajl.ts` only. Codex's uncommitted `scripts/abc-agent.ts` was left as it was.
- The trial Julia project `~/.neurajl-trial/project` gained **StatsBase**, and its depot was re-prewarmed.

**Verification at the end:**
- `security/test_session_cli.py` 37/37: 12 tests new or rewritten for this work, a net 10 more than the baseline.
- `security/test_session.py` 11/11.
- `security/test_authority.py` 27/27.
- `Pkg.test()` passes, including 11 new checks.
- The baseline before any change was 27 + 11 + 27, all passing.

---

## 1. Architecture map

```
model ── tool call {code, payload?, ephemeral?}
  │
NIRA-Prime-NeuraJL  neurajl.ts (TypeScript, one kernel per agent session / RLM child, restart notice)
  │  newline JSON over stdio
security/session_cli.py  (bridge process; SIGTERM-safe teardown)
  │
security/session.py  NeuraSession  (depot clone, broker thread, bwrap argv, per-turn deadline + hard margin)
  │  newline JSON over the worker's stdio          │ Unix socket
  │                                                security/broker.py (Class-C authority: fs write,
bwrap sandbox (user/pid/ipc/net namespaces,           network, package mgmt, spawn_child_worker;
 cap-drop ALL, clearenv, RO /usr + toolchain +         C_child ⊆ C_caller; receipts)
 repo + project, RW workspace + depot clone)
  └─ PID 1: bwrap reaper
      └─ PID 2: julia scripts/session_loop.jl
            protocol on dup'd fds; fd0=/dev/null; fd1/fd2 = per-turn capture file
            each turn: Task with deadline → Neura.execute(ExecuteCode) → Core.eval into KernelScope module
            session module bindings: bash, sh"", ShellResult, PAYLOAD, ans, varinfo, kernelinfo, include, Neura(=Api)
            EPHEMERAL → broker spawn_child_worker → fresh sandboxed julia (ephemeral_main)
```

The trust boundary is below the language, in the OS sandbox. The broker is the only path to host effects. The kernel module holds all of the model's state.

## 2. Original defect and friction ledger

The evidence comes from the probes (`p1`–`p3`), the timeout experiments and the baseline suites. Every item is listed below with its current status.

| # | Item | Class | Severity | Status |
|---|---|---|---|---|
| L1 | `display(x)` wrote into the protocol pipe and **killed the session** | bug | **blocker** | fixed |
| L2 | `bash()` returned only the exit code, so output could not be kept | missing capability | major | fixed |
| L3 | `$` in `bash("...")` is Julia interpolation, so `$?` and `$VAR` fail to parse | language-prior friction | major | mitigated |
| L4 | Source files embedded in Julia string literals fail on `"""`, `$` and `\` | model-ergonomics | major | fixed |
| L5 | Every turn's result value was retained forever (403 → 803 MB after two unbound 400 MB results) | bug (leak) | major | fixed |
| L6 | Each turn JSON-encoded the whole value (400 MB: 14.7s; 1e6 Dict: 4.6s) | performance | major | fixed |
| L7 | A timeout killed the kernel even when the turn was only waiting | implementation deficiency | major | fixed |
| L8 | Non-yielding compute cannot be interrupted | intrinsic cost | major | measured and documented |
| L9 | The `Neura` handle exposed Experiment-001 internals; `Neura.reset_kernel_state()` silently erased every binding; `discover()` listed fictional operators | misleading affordance / bug | moderate | fixed |
| L10 | `include("rel.jl")` resolved against `scripts/`, not the workspace | bug | major | fixed |
| L11 | No `ans` | discovery | moderate | fixed |
| L12 | No `varinfo()`; `names(@__MODULE__)` useless | discovery | moderate | fixed |
| L13 | `@doc f` returned a raw `DocStr` | discovery | minor | fixed |
| L14 | Types printed as `Main.KernelScope_<uuid>.P` | model-ergonomics | minor | fixed |
| L15 | `Pkg.add` failed after ~8s with the hint below ~20 Pkg frames | model-ergonomics | moderate | fixed (hint first, frames collapsed) |
| L16 | Library-internal stack frames listed in full | model-ergonomics | minor | fixed |
| L17 | No executable environment card | discovery | moderate | fixed (`kernelinfo()`) |
| L18 | Tool description said `bash` "returns the exit code"; nothing about payload, `ans` or interruption | misleading affordance | moderate | fixed |
| L19 | One Julia thread (BLAS has 18) | desirable future capability | minor | open |
| L20 | Ephemeral turns take about 10s and cannot see the workspace | intrinsic (by design) | minor | documented |
| L21 | An abort kills the kernel (one-request protocol) | intrinsic given the protocol | minor | open |
| L22 | First-call latency 0.8s (JIT of the eval path) | performance | minor | fixed (0.12s when the first call arrives ≥4s after HELLO) |

**Found during the Luna runs:**

| # | Item | Class | Severity | Status |
|---|---|---|---|---|
| L23 | World-age warning printed in every error from a function defined in the same call | bug | moderate | fixed |
| L24 | A reserved word used as a name (`quote::UInt8`) is reported as "Expected `end`" several columns away; Luna spent 3 calls on it | language-prior friction | moderate | fixed (hint) |
| L25 | A literal `$` in an ordinary string (`"$1,234"`) | language-prior friction | moderate | mitigated (hint; still the most frequent error) |
| L26 | StatsBase missing (Luna reached for it for data work) | missing capability | moderate | fixed |
| L27 | Finished background processes stayed as zombies (julia was PID 1 and never reaped), so `pgrep` reported them running | bug | moderate | fixed (bwrap reaper) |
| L28 | The payload affordance went unused while only the tool-level description mentioned it | discovery | moderate | fixed (named in the `code` parameter) |

**Checked and found fine:**
- The authority fence: 27 adversarial tests.
- `@warn`/`@info` capture.
- Struct redefinition.
- Startup: HELLO in about 3.7s.
- Package load times: `using DataFrames, CSV` 1.1s.
- Printing a million lines: 1.75s.

## 3. Fixes made

| Fix | Where | Test |
|---|---|---|
| `TurnDisplay` replaces the display stack; `display` writes to the turn's output | `session_loop.jl` | `test_display_does_not_corrupt_the_protocol` |
| `bash` returns `ShellResult(exitcode, stdout, stderr)` after printing; `sh"..."` runs raw shell text | `Neura.jl` | `test_bash_runs_shell_syntax_and_returns_its_output_and_status`, `test_sh_literal_passes_dollar_to_the_shell`, runtests |
| `payload` tool field → `PAYLOAD` for one call, `nothing` otherwise | `neurajl.ts`, `session_cli.py`, `session.py`, `session_loop.jl` | `test_payload_reaches_the_kernel_without_julia_quoting` |
| The receipt log keeps outcomes, not values | `Neura.jl` | `test_unassigned_results_are_not_retained`, runtests |
| `data` only for scalars and short collections of short things | `session_loop.jl` | measured: 1e6 Dict 5.5s → 2.4s (the rest is construction and JIT) |
| Each turn runs in its own Task. At the deadline: `InterruptException`, turn-started processes killed, re-interrupt every 1s for 5s, then a clean `kernel_exit`. The host waits 12s more before a hard kill | `session_loop.jl`, `session.py` | `test_timeout_interrupts_waiting_work_and_keeps_the_kernel`, `test_turn_that_swallows_the_interrupt_stops_the_kernel`, `test_compute_that_never_yields_stops_the_kernel` |
| `Neura` in the session is `Neura.Api` (only `request_capability`) | `Neura.jl` | `test_neura_handle_cannot_reset_the_kernel`, runtests |
| `include` resolves against the workspace (a fresh Task has no inherited `SOURCE_PATH`) | `session_loop.jl` | `test_include_resolves_against_the_workspace` |
| `ans`, `varinfo()`, `kernelinfo()` | `Neura.jl` | `test_kernel_helpers_describe_the_session`, runtests |
| `import REPL` so `@doc` renders | `session_loop.jl` | probe |
| Session-module name scrubbed from display, output, warnings and errors | `session_loop.jl`, `Neura.jl` | `test_kernel_helpers_describe_the_session` |
| Errors: runs of library frames collapsed, stdlib paths shortened, frame lines capped at 160 chars, rendered via `invokelatest` (no world-age warning) | `Neura.jl` | probes p6/p10 |
| Hints: shell syntax in backticks; `$` in a string (literal `\$`, `sh"..."`, payload); reserved word as a name; offline `Pkg` (now first, not last) | `session_loop.jl` | `test_sh_literal_passes_dollar_to_the_shell`, `test_missing_package_says_there_is_no_network`, probe p10 |
| Warm-up after HELLO compiles the turn and error paths and leaves no history or binding | `session_loop.jl` | probe: first call 0.8s → 0.12s |
| bwrap's reaper is PID 1 (dropped `--as-pid-1`); the interrupt sweep excludes it | `launch_worker.py`, `session_loop.jl` | `test_finished_background_processes_are_reaped`; `test_grandchild_nesting_actually_works` updated (pid=2) |
| The tool description rewritten: shell helpers, payload, persistence, `ans`, time-limit semantics, `kernelinfo`/`varinfo` | `neurajl.ts` | typecheck + biome clean |
| StatsBase added to the trial project; depot re-prewarmed in the sandbox | `~/.neurajl-trial/project` | `using StatsBase` in 0.36s |
| `docs/OPERATOR_SURFACE.md`: the model-facing surface, each line tested | docs | — |

## 4. Remaining known issues

- **Literal `$` in strings** is still the single most frequent error. Across the Luna runs it caused 5 parse errors, each fixed in the next call thanks to the hint. It comes from Julia's syntax and can be mitigated but not removed.
- **One Julia thread.** `Threads.@threads` and CSV's parallel parse do nothing. Enabling `-t auto` is easy, but it complicates the interrupt story (tasks spawned on other threads keep running after an interrupt). Left open deliberately.
- **Time-to-first-use JIT.** The first `CSV.read` of 1.5M rows took 5.0s, against 0.25s the second time, and the first `groupby`+`combine` took 1.6s. The real fix is a custom sysimage or a precompile-workload package. Not done: it is a build-system project, not friction removal.
- **Reading `.gz` needs a detour.** CSV can't read `.gz` without CodecZlib, so Luna decompressed with `sh"gzip -dc"` (one extra call).
- **Aborts kill the kernel,** because of the one-request protocol. Fixing this would need an out-of-band interrupt channel.
- **Ephemeral turns are slow** (about 10s) and Luna never used them.
- **`@doc f` prints every method's docstring** (long output), which is Julia's own behaviour.
- **`kernelinfo()` lists JSON as "loaded"** because Neura loads it. That is true, but it isn't something the model did.

## 5. Intrinsic architectural costs (measured)

| Cost | Measurement |
|---|---|
| Non-yielding compute cannot be interrupted | SIGINT from outside segfaults Julia 1.12 in 3 of 3 attempts; SIGINT from a watchdog thread is never delivered. Such a call ends at limit + 12s with the kernel stopped and its bindings lost. |
| Stack overflow kills the kernel | Recursion depth ≥120k is fine in the turn Task, the same as the root task. Actual overflow segfaults Julia 1.12 in both. |
| Kernel startup | HELLO 3.4–3.8s (depot reflink clone + sandbox + `using Neura`). |
| First use of a package API | Seconds of JIT per session (CSV 5.0s, DataFrames groupby 1.6s). |
| Julia string syntax | `$` and `"""` are syntax. Payload and `sh"..."` cover files and shell; literal `$` in prose does not go away. |
| Ephemeral isolation | About 10s per ephemeral call (a new sandboxed process). |
| Language prior | Luna reached for Python-era APIs (`endof`), Python keywords as names (`quote`) and packages outside the inventory (StatsBase) once each per session. |

## 6. Model-discovery findings

- **What the tool description alone got across:** the working directory, persistence, and `sh"..."` for shell work. Luna used `sh"..."` 41 times across the runs and `bash()` never.
- **Payload** was ignored while only the tool-level description mentioned it: 0 of 5 runs. After one sentence was added to the `code` parameter's description, the next file-heavy run used it for every file write (6 calls, 0 errors), where the earlier run of the same scenario hand-escaped `\"\"\"`.
- **Never called** in any of the 12 runs: `kernelinfo()`, `varinfo()`, `ans`, `ephemeral`. Luna discovered the environment with `readdir`, `read` and `@show`. The card is cheap and harmless, but a strong model doesn't need it.
- **Unused Julia capability:** `Base.JuliaSyntax`, which parses with byte ranges and so allows lossless source edits. Luna instead wrote a byte-level tokenizer to rename identifiers in S5 (correct, but about 3 kB of code). This is a language-knowledge gap, not a NeuraJL defect.

## 7. State-persistence findings

The previous v4 holdout never reused a Julia binding. Here, with no instruction to do so, the fraction of calls reusing an earlier binding was:

| Scenario | Run 1 | Run 2 |
|---|---|---|
| S1 dependency graph | 15/18 | 21/26 |
| S3 1.5M-row dataset | 17/25 | 10/15 |
| S5 AST/rename | 10/18 | 9/18 |
| S4 portfolio | 3/9 | 3/8 |
| S6 slow tool | 6/21 | 2/14 |
| S2 repository repair | 0/9 | 0/12 |

- **S1 and S3:** each input was parsed once and then queried over 15–26 calls (graph objects, a DataFrame, helper functions such as `money`, `canon`, `apply_cuts`).
- **S2:** zero reuse is expected for file-editing work, where the state lives on disk.
- **Across all runs:** no state loss and no reconstruction after a kernel loss. No kernel was lost in any Luna run.

## 8. Timeout and recovery findings

- **Before:** any call that reached the limit killed the kernel.
- **After, waiting work** is interrupted at the limit with every binding intact. That covers `sleep`, `run` and `read` of processes, I/O and `wait`.
  - Processes the interrupted call started are stopped; processes earlier calls started keep running.
  - Output printed before the interrupt is returned.
  - Verified by tests and probes (p5, p6, p16).
- **In practice (S6),** the simulator takes 75s against a 60s limit.
  - Both runs made a synchronous call, were interrupted with the kernel kept, then started the jobs in the background with `run(...; wait=false)` or `sh"... &"`, polled, and finished correctly.
  - Run 1 needed two interrupted calls, run 2 one.
- **Recovery after a kernel stop:** the next call starts a new kernel. Its result begins with a notice naming the old and new epochs and saying that bindings are gone and files remain. This is unchanged and covered by tests.
- **Checkpointing:** not built. `Serialization` of every binding after each call would cost time proportional to the state on every call, and some values (tasks, handles, closures over them) do not serialize. It would be speculative without a run that actually lost a kernel; none of the 12 did.

## 9. Shell-boundary findings

| Form | Shell? | On failure | Returns | Notes |
|---|---|---|---|---|
| `sh"cmd"` | bash | returns | `ShellResult` | `$` goes to the shell; output printed and kept |
| `bash("cmd")` | bash | returns | `ShellResult` | `$x` is Julia interpolation |
| `run(`prog`)` | none | throws `ProcessFailedException` | `Process` | shell syntax inside is a parse error, with a hint |
| `read(`prog`, String)` | none | throws; stderr goes to the output | `String` | |
| `pipeline(`a`, `b`)` | none | throws | | works |
| `run(cmd; wait=false)` | — | — | `Process` | survives later interrupts; `process_running` works |

Details:
- `withenv` and the environment work. The working directory is the workspace.
- A process killed by a signal reports `128 + signal`.
- Binary output reaches the model with invalid UTF-8 replaced; `read(cmd)` gives the bytes.
- Cancellation kills only the processes the interrupted call started.
- Luna's actual usage: `sh"..."` for pipelines and Python/unittest runs, `read(Cmd([...]), String)` with `timeout 1s` for a tool it had read the source of, and `run(...; wait=false)` for long jobs.

## 10. Package and runtime findings

**Inventory:** the Julia stdlib, CSV 1.1, DataFrames 1.8, EzXML, FileIO, JSON 1.9, PNGFiles, StatsBase 0.34 (new), YAML, ZipArchives.

**Behaviour:**
- **Offline:** the worker is `--unshare-net` and `JULIA_PKG_OFFLINE`. `Pkg.add` fails in about 8s with "This kernel has no network, so Pkg.add cannot install packages. Loadable: ..." as the first line.
- **Project isolation:** `using` of anything outside the project fails with the same hint. `Pkg.activate(".")` does not hide the session packages.
- **Self-modification:** the model can't change its own authority. The project and repo are read-only, and the depot is a private clone.

**Timings:**

| Operation | Time |
|---|---|
| `using DataFrames, CSV` | 1.1s |
| All eight original project packages | under 2s |
| StatsBase | 0.36s |
| stdlibs | 0.33s |

**Prewarm:**
- `security/prewarm_depot.py` must be re-run after any change to `Neura.jl` or the project. Without it, each kernel start recompiles Neura (about 1.5s).
- Validated: after the prewarm, HELLO went back to 3.7s and first use of Test/Pkg/SparseArrays/DataFrames triggered no precompilation.

## 11. Security audit

- **Authority suite:** 27/27 after all changes.
  - C_child ⊆ C_caller.
  - Grandchild nesting.
  - Every broker category's approve and deny paths.
  - External writes checked against real host state.
  - Package management.
  - Ephemeral children cannot reach the parent.
  - `--unshare-net` is truthful: `curl` fails with no resolver, and the tool description says "no network".
- **Changes touching the boundary:**
  - **The handle.** `Neura` in the session narrowed to `request_capability` alone. This reduces the surface.
  - **The interrupt sweep.** It kills only PIDs inside the sandbox's own PID namespace, and only when the kernel can prove it is in one (it is PID 1, or its parent is PID 1 and is `bwrap`). Outside such a namespace it does nothing.
  - **Dropping `--as-pid-1`.** The "nothing outlives the worker" guarantee is unchanged: the reaper exits when julia exits and the namespace is torn down. `test_nothing_an_ephemeral_turn_starts_outlives_it` passes, including the setsid/daemon escape shapes.
  - **Payload.** Payload is data bound to a variable, never evaluated. No new mounts, capabilities or environment were given to the worker; `NEURAJL_TURN_TIMEOUT` is informational.
- **Receipts** are still observational. Nothing reads the receipt log or the provenance capsules to authorize anything, and the receipt log now holds outcomes without values.

## 12. Performance measurements

The sandbox is on NVMe/btrfs. The lab source is on `/mnt/d` (NTFS-over-FUSE), which is read only at startup.

| Measurement | Before | After |
|---|---|---|
| HELLO (sandbox + depot clone + `using Neura`) | 3.4–3.6s | 3.6–3.8s |
| First call | 0.8s | 0.12s when it arrives ≥4s after HELLO; about 2.6s back-to-back while the warm-up still runs |
| Trivial call | about 1 ms | about 1 ms |
| `sh"true"` | — | about 1 ms warm |
| 1 MB payload → file | — | 40 ms |
| Returning a 400 MB array | 14.7s | 0.43s |
| Returning a 1e6-entry Dict | 4.6s | 2.4s (construction + JIT) |
| Unbound 400 MB results ×2 | leaked 800 MB | freed; only `ans` holds the last one |
| Print 1e6 lines | — | 1.75s |
| Interrupt latency | kernel killed at the limit | limit + 0.05–0.65s, kernel kept |
| Non-yielding compute | killed at the limit | killed at limit + 12s, with an explanation |

## 13. Long-horizon stress results

| Scenario | Calls | Wall | Errors | Outcome |
|---|---|---|---|---|
| S1 dependency graph, 426 nodes, cycles, hitting sets (r1/r2) | 18 / 26 | 242 / 230s | 2 / 2 | complete report, including minimal feedback-edge analysis |
| S2 repository repair + new function + test (r1/r2) | 9 / 12 | 91 / 98s | 0 / 0 | all tests pass, including a doctest found and fixed in r2 |
| S3 1.5M events: monthly, top users, anomalies, cohort retention, summary (r1/r2) | 25 / 15 | 382 / 247s | 4 / 2 | complete, cross-checked outputs |
| S4 quotes with two hanging symbols (r1/r2) | 9 / 8 | 62 / 57s | 2 / 0 | read the tool's source, used `timeout 1s`, reported the two failures |
| S5 call graph, dead code, identifier rename outside strings/comments/docstrings (r1/r2) | 18 / 18 | 132 / 157s | 3 / 0 | verified rename; graph unchanged |
| S6 75s simulator ×3 against a 60s limit (r1/r2) | 21 / 14 | 282 / 203s | 2 / 1 (interrupts) | backgrounded after the interrupt; correct summary |

- **Kernel losses:** 0.
- **Output correctness:** I did not grade it. This is not an experiment. The final messages and files were plausible and self-checked in every run.
- **Errors, by kind:**

| Kind | Count |
|---|---|
| ParseError from a literal `$` | 5 |
| ParseError from a reserved word | 2 |
| MethodError (the model's own types or APIs, including one `\|>` into `devnull`) | 4 |
| Interrupted | 3 |
| UndefVarError (`endof`) | 1 |
| Missing package | 1 |
| "…" outside a call | 1 |
| All-underscore identifier | 1 |

## 14. Luna usability observations

- **It verifies relentlessly** (`@assert` blocks, re-reading outputs). This is where most of the repeated file reads come from, and it's a model trait.
- **It spawns RLM sub-agents for review on its own initiative.** It did so in 3 runs (S2, S3, S5). Each child gets its own NeuraJL kernel, per the factory design, and that worked.
- **It writes idiomatic, typed Julia.** Parametric containers, `do` blocks, comprehensions, `get!`/`setdiff`, DataFrames `groupby`/`combine`, `Meta.parseall` for ASTs.
- **Its slips come from Python habits.** A literal `$`, `quote` as a name, `endof`, `|>` into `devnull`, reaching for StatsBase.
- **It reads a tool's source before trusting it** (S4) and chooses timeouts itself.
- **It prefers `sh"..."` to `run(`...`)` for anything shell-like, and Julia for everything else.** Python ran only where the repository itself was Python.

## 15. Capabilities Luna repeatedly exploited

- **Persistent bindings across calls:** 10–26 calls in S1, S3 and S5.
- **Parse once, query many times:** the graph in S1, the DataFrame in S3.
- **Defining helper functions early and calling them later:** `money`, `canon`, `apply_cuts`, `make_callgraph`, `reachable_from`.
- **`sh"..."` for shell work:** 41 uses.
- **DataFrames and CSV** for the data work.
- **`Meta.parseall` and Expr walking** for the source work.
- **Background processes with polling** after an interrupt.
- **Payload,** once described in the `code` parameter.

## 16. Capabilities Luna consistently ignored

- `kernelinfo()`, `varinfo()`, `ans`: 0 of 12 runs.
- `ephemeral`: 0 of 12.
- `bash("...")`, where `sh"..."` was always chosen.
- `include`: it wrote code into calls, not files.
- `Base.JuliaSyntax`.
- `Neura.request_capability`, correctly: the ceiling is `{}`.

## 17. Where NeuraJL reduced mechanical work

- **Expensive parses were never repeated.** The S3 dataset (1.5M rows, 5s first load) and the S1 graph were built once, and every later question was a few lines against live objects. In a shell-first workflow each question re-reads or re-parses.
- **Helper functions defined early are called later** without being rewritten (S1: `canon`, `apply_cuts`; S3: `money`, `comma_int`). Later calls are only modestly shorter: in S1 run 2, calls 13–26 average 453 characters of code against 577 for calls 4–12.
- **Structured values come back rendered and stay live.** DataFrames, Dicts and tuples display compactly (`:limit`), and the model keeps the object instead of re-parsing text. None of the runs parsed printed output back into data.
- **Shell and computation interleave in one call** (`sh"gzip -dc ... > /tmp/x"; df = CSV.read(...)`), with `ShellResult` available when the status matters.
- **Waiting work is interrupted without losing state,** so S6's long jobs cost an interrupted call rather than the whole kernel.

## 18. Where NeuraJL increased mechanical work

- **String syntax.** 7 parse errors across 12 runs: literal `$` and reserved words. Each costs one extra call and a re-sent code block, often 2–4 kB of output tokens.
- **Writing another language's source** needs payload. Without it, the model escapes `\"\"\"` by hand (S2 run 1 did so correctly, but fragilely).
- **Time-to-first-use JIT** adds seconds to the first data operation of every kernel.
- **Julia-API recall errors** (`endof`, `devnull` piping), about one per session.
- **Code-rewriting tasks.** Without JuliaSyntax knowledge the model hand-rolls a tokenizer where an IPython agent would reach for `ast` and `tokenize`, which it knows well.

## 19. Recommended final doctrine and help surface

Keep it compact and executable:
- The tool description carries the persistence rule, `sh"..."`, payload, the time-limit semantics and the package list.
- The `code` parameter's description names payload for file text.
- `kernelinfo()` and `docs/OPERATOR_SURFACE.md` hold the rest.

No longer doctrine is warranted. Luna discovered everything it needed from the description plus `readdir`/`read`, and ignored the richer helpers. The two places where one more sentence changed behaviour were payload (moved into the `code` parameter) and the error hints. Future additions should follow the same pattern: a hint attached to the specific error, not a paragraph up front.

## 20. Readiness verdict

**ENGINEERING READY: yes.**
- No known correctness or security blockers.
- Every blocker and major bug found is fixed and covered by tests (37 + 11 + 27 + runtests).
- The authority fence is unchanged in strength, and the handle is narrower.

**MODEL READY: yes, with one known recurring friction.**
- A strong model discovered and operated the surface without repeated accidental friction.
- Payload, `sh"..."`, interruption and backgrounding were all used correctly once described.
- The remaining repeated error is the literal `$` in Julia strings. It is a property of the language, now caught with a targeted hint that gets it fixed in one call.

**COMPETITION READY: yes.**
- The remaining disadvantages are intrinsic and measured:
  - non-yielding compute can't be interrupted (Julia 1.12);
  - JIT time-to-first-use;
  - Julia's string syntax;
  - the model's Python prior.
- None is unfinished implementation.
- The two open items are deliberate non-changes: multithreading, and a sysimage for time-to-first-use. Both are capability decisions, not friction. If the head-to-head is meant to include data-heavy tasks, the sysimage is the one worth deciding before the freeze. It should be decided and applied the same way for any Julia-based arm (NeuraBash's machine shop is Julia too).

**Before the comparison freeze:**
1. Pin lab and NP2 commits.
2. Re-run `prewarm_depot.py` in the runner's mount layout.
3. Record the trial project manifest, which now includes StatsBase.
4. Let a separate agent own the task pool and graders, as the v4 audit recommended.

---

## "If I had to use this system for difficult agentic work tomorrow, what would still annoy me?"

1. **Every `$`.** Prices, regexes, shell variables and LaTeX all trip on Julia interpolation. The hint makes the fix quick, but it is still a round trip every few sessions.
2. **The first few seconds of every data operation in a fresh kernel.** `CSV.read` taking 5s once is fine in a long session and annoying in a short one.
3. **A runaway loop costs the whole kernel.** One accidental `while true` without I/O means waiting 72s and then rebuilding every binding. Nothing checkpoints the state.
4. **One thread.** A 36-core machine running `groupby` on one core feels wasteful, and `Threads.@threads` silently does nothing.
5. **Ephemeral mode** is too slow (about 10s) to be the scratchpad it is meant to be, so in practice it doesn't get used.

## "From engineering experience rather than benchmark results, where do I expect NeuraJL to beat a conventional IPython-style workflow, and where do I expect it to lose?"

*This is anecdotal engineering judgment from building and watching this system, not an experimental result. No comparison was run.*

**Where I expect NeuraJL to win:**
- **Long sessions over one expensive structure:** graphs, large tables, simulations, symbolic objects. Julia's persistent compiled functions and typed containers stay fast as the session grows, where Python pays interpreter cost on every loop the model writes. The S1 and S3 transcripts are what that looks like: the object is built once, and the next twenty questions are three-line calls.
- **Numeric and algorithmic work the model writes itself,** rather than calling a library for. A hand-written recursive search, a hitting-set enumeration or a cohort computation runs at compiled speed without vectorizing tricks.
- **Code that manipulates code.** `Meta.parseall`, Expr walking and `eval` into the live session make "analyse, transform, re-load, test" one loop in one process.
- **Mixed shell and compute pipelines:** `sh"..."` with a structured `ShellResult` beside live data, in one call.

**Where I expect it to lose:**
- **Short tasks:** a few calls, especially data tasks that touch pandas-equivalent APIs once. JIT latency and Python-shaped model priors dominate, and IPython's warm, familiar ecosystem wins on calls-to-done.
- **Tasks whose deliverable is Python source,** or that lean on the Python ecosystem (scikit-learn, requests, domain libraries). NeuraJL ends up writing Python files and shelling out, which gives up its advantage while paying the Julia-syntax tax.
- **Work that needs rich library breadth offline.** The Julia inventory here is deliberately small. IPython kernels typically ship with a far larger set.
- **Heavy compute with a strict per-call limit.** IPython can interrupt most runaway Python loops without losing the kernel; NeuraJL can't interrupt non-yielding Julia compute. Losing the kernel costs the most exactly where the persistent-state advantage is worth the most.
