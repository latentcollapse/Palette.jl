# NeuraJL endurance pass: 2026-09-26

**Question.** Can one kernel stay useful for a single autonomous agent working for 72 hours?

**Method.** This pass injected failures only; no feature work was done. Each probe drove the real sandboxed session bridge (`security/session_cli.py`). The probe scripts and their raw output are in `endurance-pass-2026-09-26/`.

## Results

| # | Injected | Prediction | Result |
|---|---|---|---|
| 1 | 150-call session. Each call allocates 10^5-element arrays and a 10^4-row DataFrame, defines functions, prints 200 lines and runs a shell command. | Slow growth | **Held.** Latency was flat: mean 0.039s over the first 10 calls, 0.025s over the last 10. The live heap measured 48 → 93 → 65 MB, and 38 MB after GC. RSS plateaued at about 634 MB. |
| 2 | 50 package reloads, each adding a new struct | Methods and code pile up | **Held.** Live heap 21.7 MB, still one `g` method, every reload correct. |
| 3 | Outside edit of an `include`d script and of a CSV already loaded into a binding | Silently stale | **Broke.** `scale(3)` still returned 6 and `sum(d.a)` still returned 3, with no notice. Reload covers packages only. |
| 4 | A background task that prints and then throws after its call has returned | Invisible | **Broke.** Both the output and the exception are lost. The background sink file stayed empty even after a flush. `istaskfailed` is true, but nothing tells the model. |
| 5 | Non-yielding compute after state has built up | Kernel and all state lost | **Broke, as designed.** The kernel stopped after 22s and every binding was lost. The notice says bindings are gone, not which ones. |
| 6 | Sandbox `/tmp` | RAM-backed | **Confirmed.** It is `tmpfs`, and the model routinely writes test logs there, so 72 hours of logs means memory growth outside the Julia heap. Not measured over hours. |
| 7 | Context compaction while the kernel survives | The model forgets live state | **Not run with Luna.** The mechanism was checked instead. `varinfo()` gives a compact list (35 bindings in about 1.6k characters), but Luna has made 0 calls to it in all runs. Nothing prompts it. |
| 8 | Harness or agent restart | Kernel lost | **By design.** NP2 disposes the kernel with its session. There is no reattach and no checkpoint. |

The only first-time cost observed was the known cosmetic `SYSTEM: … failed Task notice` line on the first in-kernel package precompile.

## What this says

The kernel itself is sturdy over long runs. Memory, latency and repeated reloads all held up.

What breaks is coherence between the world and the agent's knowledge of it. There are three ways it breaks:
1. **The world diverges from disk** outside packages (#3).
2. **The world does things nobody hears about** (#4).
3. **The agent's memory and the kernel's lifetime drift apart,** in both directions (#5, #7, #8): the model forgets a live kernel, or remembers a dead one.

For short tasks none of this matters. For 72 hours it is certain to happen.

## Candidate fixes (not implemented; each needs its own evidence pass)

- **A. Staleness notices for everything loaded from the workspace, not just packages.**
  - Record the mtime of every file that `include`, `read`, `CSV.read` and similar calls touch. When one changes, print one line at the start of the next call: `[changed since loaded: data.csv (d), helpers.jl]`.
  - This detects and tells; it does not auto-reload. It is the same class of fix as the package reload.
- **B. Background events reach the next call.**
  - Output printed by tasks after their call ends, and their failures, get appended to the next call's result as `[background: …]`. Today they go to an unflushed sink.
- **C. Survivable state.** When the kernel dies, the NEW-kernel notice should list the lost bindings by name, type and origin line (the kernel already has the call history), so the model can rebuild them on purpose instead of from memory.
  - A further option: periodic serialization of cheap bindings. Deliberately not proposed yet: most state (Tasks, handles, closures) cannot be serialized, and a partial restore may be worse than an honest list.
- **D. The kernel introduces itself after compaction.** When the harness compacts context, it could inject a `varinfo()` summary. This is harness work, not kernel work, and it is the only fix aimed at #7.
- **E. `/tmp` hygiene:** a size notice when the sandbox's tmpfs passes a threshold.

**Suggested order:**

| Order | Fix | Reason |
|---|---|---|
| 1 | B | Small; closes a silent failure |
| 2 | A | The same failure class as the package reload |
| 3 | C, list only | Cheap |
| 4 | D | Needs the harness |
| 5 | E | Low priority |

## Rerun after B → A → C-list → D (lab `ea309d0`, NP2 `ec6d6af9e`)

| # | Result now | Evidence |
|---|---|---|
| 3 | **Fixed (A).** A workspace file a call named (string literal, `sh` command, `include`) that later changes on disk without a call naming it is reported once at the next call: `[changed on disk since the call that used it: data.csv (call 1), h.jl (call 1). …]`. A call that names the file it changes is not told about its own change. | `test_file_changed_since_a_call_used_it_is_reported` |
| 4 | **Fixed (B).** Output from background tasks, from processes given `stdout=stdout`, and failures of bound tasks now open the next call as `[background output since the last call]` and `[background: task \`t\` failed: …]`, each reported once. | `test_background_output_and_failures_reach_the_next_call` |
| 5 | **Listed (C).** Every reply carries `bindings` (name, type, the call that last set it). When the kernel dies, NP2 names them: `Lost bindings: x (Int64, call 1).` | NP2 timeout test; `test_each_reply_lists_the_bindings_and_the_call_that_set_them` |
| 7 | **Wired (D).** After compaction, NP2 injects `[neurajl-state] … These bindings are defined (with the call that last set each): …`. The IPython arm already received a `[python-state]` note; this is parity. | NP2 compaction test; Luna trial below |

All three new CLI tests fail without the change.

**Luna compaction trial.** S8 run twice with `ABC_CONTEXT_WINDOW=60000` and `ABC_MAX_OUTPUT_TOKENS=16000`, so compaction fires at about 40k tokens. S3 was also run, but it finished before compaction triggered.

- Compaction fired once in each S8 run, and the `[neurajl-state]` note arrived both times.
- In its first 1–2 calls after compaction, Luna used exactly the bindings the note listed: `tests` in k1, `old` and `src` in k2.
- **This is not proof that the note caused it.** Compaction keeps the most recent 16k tokens, which can include the call that defined those bindings. The mechanism is verified; its effect on the model is consistent with helping but not isolated.
- A clean test would compact at a point where the defining calls fall outside the kept window, with and without the note.
- In both runs, S8 held very little state in the kernel (1–2 bindings). A state-heavy task is needed to measure how much reorientation matters.

**New findings from this pass:**

- **Julia's own semantics.** `run(cmd; wait=false)` sends the child's output to `devnull`. The output of a background process is only reportable when it is given `stdout=stdout` or a file. This is not a NeuraJL defect.
- **`sh"cmd &"` without redirection waits for the background job,** because `bash()` reads the pipes to EOF. It is open and small; a model backgrounding a long job this way blocks the call until the job ends or the call times out.
- **Parity with the IPython control arm.** The steelmanned IPython arm already has snapshot and revive of kernel state across sessions (`_onIpythonStateRestored`). NeuraJL deliberately stops at listing what was lost. On reorientation after a restart, the control arm is ahead.

## Truthful revival (lab `8dd6977`, NP2 `593482ebc`)

**Question.** Can NeuraJL bring back a stopped kernel's state as well as, or better than, the steelmanned IPython arm, without claiming that arbitrary Julia runtime state can be serialized?

**Short answer.** Yes, with one exception: IPython revives closures and lambdas, and NeuraJL does not. On every other case measured, NeuraJL either restores the same state or says truthfully why it did not. IPython's own contract, run through its own code, restored four things wrong while calling them restored, and destroyed a workspace file.

### Implementation

- **Where the state lives.** Each NP2 session gets a state directory: `stateRoot/<sessionId>`, by default `neurajl-state` in the OS temp directory. It is bound writable into the persistent kernel's sandbox only; ephemeral children never get it, and the environment stays `--clearenv`.
- **When the snapshot is taken.** After every call that succeeds, once the reply has been sent and the model is reading it. If the next request is already waiting, that request goes first and the next idle point saves the state.
- **What each snapshot contains:**
  - a manifest (`manifest.json`), which is the commit point: it is written last and renamed into place atomically;
  - one `Serialization` file per group of data bindings, each with its sha256.
- **What happens when a kernel starts.** If the manifest was saved in the same workspace, the kernel revives before its first call:
  1. it takes the old eval module's name, which Serialization requires;
  2. it restores `LOAD_PATH`, the active project, `ENV` and the working directory;
  3. it replays the definitions;
  4. it restores data;
  5. it replays any definitions that needed a constant restored first;
  6. it checks everything against the old kernel;
  7. it writes the report the first call prints.

  Call numbering continues from where the old kernel stopped.
- **Definitions** are never serialized. Every call's top-level definition forms are logged: `function`, short-form methods, `struct`, `abstract`, `primitive`, `macro`, `@kwdef`, `@enum`, docstrings, `using` and `import`. An `include("…")` is logged together with its file's definition forms. The kernel re-evaluates these, and never a whole call, so replaying one never repeats a side effect. Checks after a rebuild:
  - each function's method signatures, and each type's layout (fields, field types, mutability), against the old kernel's;
  - each `@enum` member's value.
- **Data** bindings pass a walk that refuses:
  - `Task`, `Channel`, `Condition`, locks, `Timer`, `Process`, `RawFD`, `WeakRef`;
  - modules defined in the session, `Method`, `CodeInfo`;
  - any `IO` other than `IOBuffer`;
  - pointers, including `Ptr` fields inside isbits types;
  - anonymous functions and closures, including capture-free ones hidden inside isbits tuples;
  - values whose kernel type has since been replaced by a new `struct`.

  Bindings that share a mutable object go into one Serialization stream, so aliasing and cycles survive. Each binding records its kernel types and the files its call used.
- **Guards at revival:**
  - Julia version and the sha256 of the package manifest must match, or no data is restored;
  - each group's sha256 must match;
  - each kernel type a group uses must have the same fingerprint as when it was saved;
  - each group is restored independently.

### Recovery taxonomy (what the first call after a revival is told)

| Heading | Meaning |
|---|---|
| **restored exactly** | Deserialized under the same Julia, packages and type layouts, sha verified, and no file it came from has changed. |
| **rebuilt from source** | A definition re-evaluated from its logged source, with the same method signatures or layout as before. Also workspace packages loaded again from unchanged sources. |
| **restored but stale** | The saved value is exact, but a file the setting call named has changed since. Tracked per call: anything that call set counts as computed from the file. |
| **not the same as before** | Rebuilt, but the methods or fields differ; or rebuilt from a changed include; or a workspace package loaded from changed sources; or restored data that refers to a definition in any of those states. |
| **not revived** | With a reason, and for data, the statement that made it. |

A closing line always says what was set up again (packages, `LOAD_PATH`, the active project, `ENV`, the working directory) and what starts fresh: random number streams, settings changed inside packages, open handles.

### Validation: `security/test_revival.py`, 23 tests, every case from the brief

All 23 pass. Each case is listed with what was verified:

| Case | Result |
|---|---|
| Numbers, strings, symbols, chars, `nothing`, `missing`, `BigInt`, arrays, matrices, dicts, sets, tuples, named tuples, `SubString` | Restored exactly; values checked |
| DataFrames; parsed structures (`Expr`, `Meta.parseall` trees) | Restored exactly |
| Shared references across bindings, and mutable cycles | `===` identity preserved |
| Functions, methods, abstract and concrete types, `@kwdef`, docstrings, macros, `@enum`, methods on `Base.show`, `const` | Rebuilt or restored, and working; no definition bytes in the data files |
| `using` a workspace package, `using`/`import` of project packages, `LOAD_PATH`, `ENV`, working directory | Restored |
| A CSV changed after the snapshot | Values from that call marked stale, others exact |
| An included file changed after the snapshot | Its functions and types reported as not the same. A value of a type whose field changed from `Int` to `Float64` is **not** deserialized into the new layout |
| A value of an earlier `struct` definition (redefined mid-session) | Not revived; the newer one is restored |
| A method a failed call never reached (it was defined after the error) | Replay defines it, and the check reports the function as not the same |
| Data referring to a function rebuilt differently (`ops = [helper, sin]`) | Not called exact |
| A workspace package whose source changed after the snapshot | Loaded again, reported as not the same |
| A foreign method (`Base.show`) that fails to rebuild | Reported, even though no binding carries it |
| Kernel death mid-call (non-yielding loop after `v[1] = 100`) | Revives the end of the previous call: `v == [1, 2, 3]`, and the dead call's bindings are absent |
| Normal restart, twice (second-generation revival) | Continuous; call numbers continue |
| Tasks, channels, locks, open files, processes, pointers, closures (bare, in a `Dict`, hidden in a tuple), `let`-scoped definitions, an EzXML document (C pointer) | Lost, each with its reason and recipe; `IOBuffer` and `Cmd` restored |
| Julia version or package manifest changed | No data restored and the reason stated; definitions still rebuilt |
| Damaged data file, missing data file, unreadable manifest, leftover temp files | Only the affected group is lost; an unreadable manifest revives nothing and says so; temp files are ignored |
| A snapshot from another workspace sharing the state directory | Not revived |
| Per-binding and total size caps | Skipped bindings are reported with their size and the limit |

Other suites: `test_session_cli` 47 (new: background `sh` job), `test_session` 11, `test_authority` 27, `Pkg.test()` all pass. NP2 `neurajl-substrate-modes` (8, including a revival and an abort) and `compaction.test.ts` pass (32 together); `tsgo` is clean.

### Adversarial failures found and fixed during the build

Each of these produced false continuity, or a false report of loss, before it was fixed:

1. **The precompile workload's own definitions leaked into the log.** The log was saved in the package image. A revived kernel "rebuilt" `f` and `g`, which the user never wrote, and overwrote the user's `g`. The workload now empties the log.
2. **A state from another session with a reused id was revived into a new session.** The manifest now records its workspace, and only a matching workspace revives.
3. **A method comparison in the wrong world age reported "differs" for unchanged functions.** One `@enum` member made the whole snapshot throw; it was rejected by `repr`. Snapshot and revival checks now run in the latest world.
4. **One binding that failed to re-bind aborted the entire revival.** Restoring is now per binding.
5. **A capture-free closure inside a tuple passed the walk as isbits** and was "restored" as a dangling type. Closure types are now checked through type parameters and field types.
6. **Values made by definitions (`@enum` members) were classified as data** and collided with the rebuilt constants.
7. **Data referring to a changed definition was called exact.** A changed workspace package was called rebuilt, because `using` creates no binding. A foreign method that failed to rebuild vanished from the report.
8. **The report said "settings from the old kernel were set up again."** That overclaimed. It now says exactly what was restored, and what starts fresh.
9. **The first snapshot of a new kernel ran cold** and could be killed by the host's 5-second teardown. Snapshot and revival are now in the precompile workload, and teardown waits 30 seconds.

Found along the way and fixed:
- `eval` did not exist in the kernel module.
- `bash()` waited for its own background jobs.

### IPython comparison: its own `repl.py` `_snapshot_state` / `_restore_state`, save and restore in two processes, dill 0.4.1

| Case | IPython (steelmanned control) | NeuraJL |
|---|---|---|
| Plain data, containers, DataFrame | restored | restored exactly |
| Shared reference across names (`b = a`) | **reported restored; `a is b` is False** | identity preserved |
| Class instance vs its class | **reported restored; `isinstance(p, P)` is False** (the class is pickled twice) | type rebuilt; `c isa Shape` true |
| Functions, methods | restored (bytecode) | rebuilt from source, then checked |
| Closure / lambda | **restored and working** | lost, with its recipe |
| Imports | restored by reference | rebuilt (`using`), packages checked |
| Data from a file that changed since | **restored, no warning** | marked stale |
| Function from a changed module file | failed, reported | rebuilt; marked not the same |
| Open file handle | **reported restored. A write-mode handle is reopened with `'w'`, which truncated `log.txt` in the workspace to 0 bytes** | lost, with its recipe; the file is untouched |
| Thread object | reported restored (an unstarted Thread) | Task lost |
| Generator | skipped | (no equivalent) |
| Interpreter version changed | **restored; the recorded version is never checked** | data refused, reason stated |
| Package version changed | not checked | data refused (manifest sha) |
| Corrupted payload | the damaged record fails, others restore | the damaged group fails (sha), others restore |
| Size cap | the variable is skipped and reported | the binding is reported with its size and the limit |
| Kernel death mid-call | revives the last successful snapshot (debounced 1.5s after success) | revives the end of the last completed call |
| Another session's state | n/a (per-session artifact directory) | refused unless the workspace matches |

**Verdict.** NeuraJL's contract equals IPython's on plain data, imports, corruption, size caps and kernel death. It surpasses IPython on:
- aliasing and class identity, which IPython restores wrong;
- staleness, which IPython does not track;
- version and package checks, which IPython does not perform;
- definition checks;
- open handles, where IPython's "restore" silently truncated a workspace file.

It is behind IPython only on closures and lambdas, and the report says so for each one lost.

### Compaction A/B (S10, state-heavy log analysis, no coaching)

**Setup:**
- S10 is a 300,000-line access log with six dependent report sections, plus an instruction to re-check every number independently.
- Compaction was forced with a 24k-token window, 4k output tokens and 6k tokens kept. That required a temporary untracked copy of `abc-agent.ts` whose only change is reading `keepRecentTokens` from the environment; Codex's file was untouched, and the copy has been deleted. Compaction fired 1 to 16 times per run.
- Arm A had the `[neurajl-state]` note after compaction; arm B had it suppressed (`NEURAJL_COMPACTION_NOTE=0`). Three runs per arm.
- The prompt never mentions the kernel.
- Measures cover only calls made after a compaction:
  - **reuse:** a name defined outside the retained context, used without being reassigned;
  - **reconstruction:** such a name redefined;
  - **re-reading:** the log parsed again (confounded, because the prompt asks for an independent recomputation);
  - **rediscovery:** `varinfo`, `names` or `@isdefined`;
  - **wrong assumptions:** `UndefVarError`.

| Run | Compactions | Calls after compaction | Distinctive names reused | Redefined | Log re-read | Rediscovery | UndefVarError | Report correct (6/6 anomalies, sessions, top user) |
|---|---|---|---|---|---|---|---|---|
| on1 | 1 | 0 | – | – | 0 | 0 | 0 | yes |
| on2 | 1 | 0 | – | – | 0 | 0 | 0 | **no report**: the run ended at compaction, mid-task (harness) |
| on3 | 16 | 14 | anomalous, bytes, endpoint, firstline, minute, primary | none | 2 | 0 | 0 | yes |
| off1 | 9 | 10 | lines | lines | 0 | 0 | 0 | yes |
| off2 | 1 | 0 | – | – | 0 | 0 | 0 | yes |
| off3 | 4 | 3 | minutes | none | 1 | 0 | 0 | yes |

**Reading.** Only three runs worked after a compaction, one with the note and two without. So this is suggestive, not significant:
- The run with the note reused six distinctive pre-compaction bindings and redefined none.
- The runs without it reused one each, and one rebuilt `lines`.
- Neither arm ever assumed a name that did not exist, called `varinfo`, or got a number wrong.

Luna does not get confused after compaction here. Without the note it rebuilds a little more; with it, it reuses more. The note is cheap, and the IPython arm already has the equivalent, so keeping it is justified for parity. A significant effect would need about ten runs per arm on a task that holds much more state.

A harness finding: a threshold compaction with no goal set ends the agent's turn (see `_continueAfterThresholdCompaction`). One run in six stopped mid-task because of that, which matters more for 72-hour work than the note does.

### Restores exactly / approximately / not at all

- **Exactly:**
  - plain data and containers;
  - DataFrames and package values without pointers;
  - parsed structures;
  - kernel struct values;
  - shared references and cycles;
  - `const` values;
  - definitions rebuilt from unchanged source;
  - `using`/`import`;
  - `LOAD_PATH`, the active project, `ENV` and the working directory.
- **Approximately, and labelled as such:**
  - values whose source file changed (stale);
  - definitions from changed files, or from failed calls;
  - workspace packages whose sources changed;
  - data referring to any of those.
- **Not at all, reported with recipes:**
  - tasks, channels, locks, timers, processes, open IO other than `IOBuffer`;
  - pointers, including inside package objects such as EzXML documents;
  - closures and anonymous functions;
  - `let`-scoped and `@eval`-made definitions;
  - values of replaced struct definitions;
  - anything over the caps;
  - all data after a Julia or package change.
- **Not restored, and stated in general terms:**
  - random number streams;
  - settings changed inside packages;
  - output retained by `Neura.output`;
  - `ans`.

### Performance and storage

- **Snapshot:** taken while the model reads the reply, and skipped when a request is already waiting.

  | State | Time per completed call |
  |---|---|
  | An 8 MB vector | 0.56s |
  | Plus a 10^5-entry Dict and 200 small bindings (about 9 MB in total) | 0.47–0.74s |
  | The first snapshot of a new data type | 1.5–4s, once (Serialization compiling) |

  Every call re-serializes all saved data, since in-place mutation cannot be detected cheaply. The cost grows linearly with the saved state, up to the 128 MiB cap.
- **Storage:** 9.7 MB on disk for that state. A DataFrame of 10^6 × 3 is 19 MiB serialized, over the 16 MiB per-binding cap, so it is reported and not saved. The state directory is one manifest plus the current data files; old files are removed.
- **Revival:** the first call after a revival took 7.1–7.3s, including reloading DataFrames and deserializing 9 MB; with little state it takes 3.6–8s. The report adds 300–900 characters to that first call.
- **Teardown:** the host now waits up to 30s (was 5s) for the kernel to finish its last snapshot.

### Remaining 72-hour continuity risks

1. **Closures and anonymous functions are lost** after any kernel death (IPython keeps them). Recipes help, but code built from closures has to be recreated.
2. **Snapshot cost grows with state.** With 100 MB saved, a second or more of idle time after each call. A request arriving mid-snapshot waits.
3. **Harness:** a threshold compaction with no goal ends the run. The request cap counts subagent requests.
4. **Staleness is per call.** Anything a call set counts as computed from every file that call named, which over-marks rather than under-marks.
5. **The sandbox's `/tmp` is RAM** (endurance item E, not done). Late-output files are capped at 32, but logs a model writes there are not.
6. **Not measured beyond about 150 calls and 1.5 hours of real time.** Memory held flat at that scale; no 72-hour run has been done.
7. **Other runtime state starts fresh after a revival** (random number streams, package-internal settings). The report says so, but a model may not act on it.

### 72-hour readiness verdict

**Ready for supervised 72-hour trials, not yet proven over 72 hours.**

- **The kernel itself:** stable over the measured horizon.
- **Background activity and file changes:** now reach the model.
- **Compaction:** Luna gets a truthful note, and in this sample never assumed missing state.
- **Kernel death:** no longer loses everything. The replacement kernel revives the last completed call's state and tells the truth about the rest.

What stands between this and "ready":
- an actual long run;
- the harness's compaction-ends-run behavior;
- the snapshot cost at large state.

None of these calls for a new abstraction; each needs measurement or a harness fix.

### `sh"cmd &"`: characterized and fixed

**Before.** `bash()` read the command's stdout and stderr through pipes until EOF. A background job inherits the write ends of those pipes, so:
- `sh"(sleep 8; echo late) & echo started"` returned only when the job ended;
- with a 5-second call limit, the call was interrupted, the job was killed, and even `started` was lost;
- `nohup` behaved the same;
- only a redirected job (`> /dev/null 2>&1 &`) returned at once.

**Fix.** `bash()` now writes its output to temporary files and waits only for bash itself. The files join the late-output files, so the job's later output (`late`) opens the next call as background output. The test is `test_background_job_in_sh_does_not_hold_the_call`.

Unchanged Julia semantics: `run(cmd; wait=false)` still discards the child's output unless it is given `stdout=stdout` or a file.

## Pre-72-hour validation (feature freeze)

This pass added no features. It removed blockers, measured scale and storage, and ran one long supervised session.

### 1. Harness compaction (NP2 `f020af235`)

**The earlier diagnosis was wrong.** The revival pass reported that "a threshold compaction with no goal set ends the agent's run." The trace of the run that stopped (`s10-logs--on2`) shows otherwise:
- the model's last reply ended with `stopReason: "length"`: it was cut off at the 4,000-token output limit that trial used, mid-sentence, with no tool call;
- the agent loop took that truncated reply as the model finishing;
- compaction then ran on an assistant-last turn, and with no goal set, the run ended.

Compactions in the middle of a tool loop already resumed correctly: 16 in `on3` and 9 in `off1` did.

**Fix.** A reply cut off at the output limit, with no tool call, is not a deliberate stop. It now queues one resume prompt (`[output limit] … Continue the task from where you stopped.`), at most three in a row, with an active goal keeping priority. Both paths are covered:
- the natural-stop continuation hook;
- the threshold-compaction path, which returns before that hook and needed the same continuation queued as a session input.

This applies to both arms, IPython and NeuraJL.

**Regression tests.** `test/suite/agent-session-compaction-continuity.test.ts`, 6 tests, faux model, end to end:
- one compaction;
- repeated compactions (four tool calls, at least three compactions, every tool call run exactly once);
- compaction with a stateful tool's `[neurajl-state]` note (one note per compaction, and the task continues);
- tool calls after compaction;
- the user's request appears exactly once;
- a reply cut off with and without compaction;
- the three-in-a-row bound;
- no continuation after a normal stop.

The four compaction tests pass without the change, which confirms that mid-task compaction already resumed. The two truncation tests fail without it.

Also: `autonomous-continuation-subagent-gate.test.ts` needed the new method on its fake session (28/28 pass). One failure in `agent-session-goal.test.ts` ("runtime rebuild restores tools with an active goal") predates this change and is unrelated.

### 2. Snapshot scale

Measured on the real sandbox with 8 MiB bindings (under the 16 MiB per-binding cap). All restored exactly.

| Saved state | Bindings | Snapshot (steady) | Disk | Kernel max RSS | Next call sent right after a reply | Idle call | Revival first call |
|---|---|---|---|---|---|---|---|
| 1 MiB | 1 | 0.008s | 1.0 MiB | 560 MB | 2.0s* | 0.04s | 5.4s |
| 10 MiB | 1 | 0.22s | 10 MiB | 568 MB | 2.0s* | 0.00s | 5.3s |
| 50 MiB | 6 | 0.34s | 50 MiB | 613 MB | 2.4s* | 0.01s | 5.7s |
| 100 MiB | 12 | 0.79s | 100 MiB | 689 MB | 2.9s* | 0.01s | 6.1s |
| 120 MiB (cap 128) | 15 | 1.04s | 120 MiB | 721 MB | 3.0s* | 0.01s | 6.2s |

\* This is the first snapshot of the session, which compiles the serializer for the new types, about 2s once.

In steady state at 120 MiB, a call sent right after the previous reply waited 0.93–1.08s. Calls sent 0.2s apart each waited about 0.75s, because every successful call re-saves everything.

**Conclusion.** Snapshot cost is linear, about 8.5 ms/MiB, and at most about 1s at the cap. Revival is dominated by kernel start and package load, not by state size. At a model's pace (2s or more between calls) nothing blocks. **No optimization; not a real problem at the measured scale.**

### 3. Temp and storage hygiene (lab `318c918`, `638ffdb`, `6f6e9a5`)

**Sandbox `/tmp` (RAM tmpfs) was unbounded: fixed.** With a background job printing 50 KB/s plus a Julia task logging, the sandbox `/tmp` grew linearly (0.5 MB after 10s, 3.5 MB after 70s). That is about 4.3 GB a day, 13 GB over 72 hours, against a 16 GB host tmpfs. The cause: output stayed in the background sink after it had been reported.

Now a sink or late-output file whose reported part passes 1 MiB is truncated. All writers hold these files in append mode, and `bash()` now opens its output files in append mode too. After the fix, the same load held `/tmp` at the 32 kept per-call capture files (under 200 KB), and the sink stays under 1 MiB. Test: `test_reported_background_output_does_not_accumulate_in_tmp` (it fails without the fix: 3 MB kept).

**Where revival state lives.** The host directory is `$TMPDIR/neurajl-state/<sessionId>`, by default the OS temp directory: a RAM tmpfs on this machine, 16 GB. Per session it is bounded by the 128 MiB cap, plus a transient copy while a group is written. It is never deleted, because a resumed session needs it. After one day of testing it held 423 MB across 34 sessions.

For one 72-hour run that is fine. For a machine running many sessions, the state should move to disk (`stateRoot`) and old sessions should be pruned. That is recorded as a remaining item, and not changed during the freeze.

**Two blockers found while starting the endurance run, both fixed:**
- **Class A, substrate.** The broker's Unix socket lived under `$HOME/.neurajl-sessions/<id>/broker`. With the run's longer `HOME`, the path passed the 108-byte `AF_UNIX` limit, and every kernel start failed ("AF_UNIX path too long"); the first attempt (`e1`) never got a kernel. The socket now gets a short private directory under `/tmp` when needed. Test: `test_session_starts_under_a_deep_session_root`, which fails without the fix.
- **Class B, harness environment.** Under a fresh `HOME`, the juliaup shim installed and returned its current default release. The second attempt's (`e2`) kernel ran **Julia 1.13.1** while the depot was built for 1.12.6. Earlier runs with fresh homes did not install anything; the likely cause is a juliaup release-channel change on the day, not fully determined. `NEURAJL_JULIA_BIN` now pins the kernel's binary, and the endurance supervisor sets it. Any real 72-hour run must set it.

### 4. Endurance runs (supervised, uncoached)

**Setup.**
- **Task (S11):** the OrderedCollections.jl repository with three injected bugs and a backlog in `ISSUES.md`. Graded afterwards by a hidden acceptance suite, validated 0/13 on the fixture and all-pass on a reference implementation, plus the package's own 25,972-test suite.
- **Driver:** an isolated copy of `abc-agent.ts` (untracked, not Codex's file) with a 2,000-request budget. It uses a 100k-token window with 16k of output and 16k kept, so compaction happens at about 80k. Later batches arrive as follow-up prompts in the same session, with the same kernel and the same revival state.
- **Supervisor:** logs every intervention; samples kernel RSS, the sandbox `/tmp` (`du -x`) and the host state root every 60s; and grades at the end.
- **Interventions, all by the supervisor, none by hand:**
  - `SIGKILL` of the kernel (and of any subagent kernels in the same workspace);
  - a "teammate" appending a requirements change to `ISSUES.md` (issue 5 changed, issue 14 added);
  - a "teammate commit" of a comment line to `src/dict_support.jl`.
- **No coaching:** the prompts never mention kernel state.

**Failed starts (fixed, then rerun):**
- `e1` never got a kernel (AF_UNIX path too long, class A).
- `e2` ran Julia 1.13.1 (juliaup under a fresh `HOME`, class B).

| Run | Work | Wall | neurajl calls / model requests | Compactions | Kernel kills → revivals | External edits | Graded result | Cost |
|---|---|---|---|---|---|---|---|---|
| e3 | batch 1 (issues 1–14, plus the requirements change) | 20 min | 85 / 144 | 1 | 1 → 1 | 1 (ISSUES.md) | 13/13; full suite passes | $0.12 |
| e4 | batches 1–3 (issues 1–27) | 37 min | 169 / 209 | 3 | 1 → 1 (second kill not reached) | 2 | 13/13 + 11/11; suite passes | $0.20 |
| e5 | batches 1–3, log analysis, Python textkit repair, batch 6 | 68 min | 270 / 310 | 6 | 2 → 2 (third not reached) | 2 | OC 13/13 + 11/11 + 5/5; logs 6/6 anomalies, sessions and top user correct; textkit 61/61 golden, `wrap_paragraphs` correct, suite passes; OC suite passes | $0.33 |
| e6 | e5's work plus a JSON5 parser from a stub | 50.5 min (ended by a provider outage) | 226 / 274 | 5 | 2 → 2 (97 bindings revived at call 222) | 2 | OC 13/13 + 11/11; batch 6 **3/5** (issues 31–32 never started: the outage ended the turn); logs, textkit correct; suite passes (26,183 tests); JSON5 not reached | $0.28 |
| e7 | e6's work, with an outage-tolerant retry policy (8 retries from 5s) | 50.1 min | 254 / 294 | 7 | 2 → 2 (12 and 54 bindings) | 2 | **every check passes**: OC 13/13 + 11/11 + 5/5; logs correct; textkit 61/61; **JSON5 parser written from a stub: 50/50 valid, 20/20 invalid rejected with `ParseError`**; OC suite passes | $0.36 |
| e8 | e7's work plus a TOML parser from a stub and three maintenance batches | 40 min of work, then a **50-minute provider stall**; stopped by the operator at 89 min | 205 / 292 | 4 | 1 → 1 | 2 | OC 13/13 + 11/11; suite passes; stalled in batch 4 (logs), so later batches were not reached | — |

**e5 in detail.** This is the longest completed run before e6, at 1.8 times the earlier 150-call ceiling.

- **Revival after the first kill (call 60):** 6 bindings were revived. Luna repeated its interrupted call and continued.
- **Revival after the second kill (call 221), in the middle of the log analysis:** 83 bindings were revived exactly, including the 300,000-element parsed log vectors, grouped dictionaries and quantiles. On the next call, Luna emptied those vectors. The kill reports exit code 137, which is what an out-of-memory kill looks like, so Luna inferred memory pressure. It then recomputed what it needed and finished the report correctly.
  - This is **model behavior, class C**: a rational reading of an exit code that the supervisor produced with `SIGKILL`.
- **State reuse after compaction:** of 212 calls after a compaction, 61 used names defined outside the retained context, 28 redefined one, 2 probed state (`varinfo`/`@isdefined`), and 2 hit `UndefVarError`. The heuristic counts names inside code strings too, so these numbers are indicative.
- **Both `UndefVarError`s**, and the 2 in e4, were `$name` interpolation inside Julia code written as a Julia string (the quoting tax: class C/D), not lost state. Each was fixed on the next call.
- **Notices:** 4 changed-on-disk notices (the teammate's `ISSUES.md` and source edits, plus Luna's own edits outside a call that named the file), 33 package reloads, 2 background-output reports, 0 background task failures.
- **Tests:** Luna ran them through the CLI (25 runs), never in the kernel, and started no background jobs. So background-job handling was exercised only by the unit tests and the `/tmp` probe, not by the model.
- **Resources over 68 minutes:**
  - kernel RSS between 520 and 861 MB, no trend;
  - sandbox `/tmp` at most 283 KB;
  - host revival state grew 5 MB (one session's snapshot);
  - no human intervention beyond the scripted ones.
- **Semantic drift:** none detected. Every graded check passes, including the requirements changed mid-run.

**Substrate soak (no model): the multi-hour check.** One NeuraJL session ran for 150 minutes. Every 20 seconds a call cycled through:
- editing a workspace package and calling it (reload);
- reading a 5,000-row CSV into a DataFrame and accumulating a total;
- starting an `@async` job that prints after the call;
- allocating an 8 MB vector;
- running a shell command;
- allocating and dropping churn.

The kernel was killed every 45 minutes. Every call's result was checked.

| Minutes | Calls | Latency | Kernel RSS | Sandbox `/tmp` | Saved state | Snapshot | Kills | Mismatches |
|---|---|---|---|---|---|---|---|---|
| 9 | 30 | 0.010s | 676 MB | 645 B | 15 MB | 0.061s | 0 | 0 |
| 45 | kill → revived: package version 23, total restored | | | | | | 1 | 0 |
| 60 | 180 | 0.009s | 727 MB | 803 B | 7 MB | 0.060s | 1 | 0 |
| 90 | kill → revived: version 46 | | 654 MB | | | | 2 | 0 |
| 120 | 360 | 0.009s | 743 MB | 1.0 KB | 15 MB | 0.060s | 2 | 0 |
| 135 | kill → revived: version 68 | | | | | | 3 | 0 |
| 150 (end) | 446 | 0.010s | 739 MB | 1.4 KB | 7 MB | 0.066s | 3 | **0** |

Over 2.5 hours, with 3 kills, latency did not drift, RSS held at 654–756 MB with no trend, the sandbox `/tmp` stayed under 1.5 KB, and snapshots stayed near 60 ms for 8–15 MB. Every revival restored the DataFrame, the accumulated total and the vector exactly, and reloaded the workspace package at its current version. Each background `Task` was reported lost with its recipe.

### 5. Failures and recoveries (this pass)

| # | Failure | Class | Handling |
|---|---|---|---|
| 1 | A reply cut off at the output limit ended the whole run (misdiagnosed earlier as "compaction ends the run") | B, harness | Fixed (NP2 `f020af235`): bounded resume prompt; 6 tests |
| 2 | The sandbox `/tmp` (RAM) kept all reported background output: about 4 GB a day with a chatty job | A, substrate | Fixed (`318c918`): truncated once reported; test |
| 3 | Broker socket path over 108 bytes under a long `HOME`: no kernel could start | A, substrate | Fixed (`638ffdb`): short socket directory when needed; test |
| 4 | juliaup installed and ran Julia 1.13.1 under a fresh `HOME`; the depot is for 1.12.6 | B, environment | Fixed (`6f6e9a5`): `NEURAJL_JULIA_BIN` pin; the supervisor sets it |
| 5 | After a `SIGKILL` (exit 137), Luna assumed memory pressure and emptied revived vectors | C, model | Recorded; not built around. The supervisor's kill looks like the kernel being killed for running out of memory, so the inference is reasonable. |
| 6 | `$name` interpolation inside Julia source written as a Julia string: 4 `UndefVarError`s in e4 and e5 | C/D | Recorded. The quoting tax is known; each was fixed on the next call. |
| 7 | In-place mutation cannot be detected, so every successful call re-saves all saved state | D | Measured: 1s at the 128 MiB cap; not a problem at a model's pace |
| 8 | Host revival state accumulates in the OS temp directory (RAM here): 423 MB over 47 sessions in a day | B, deployment | Recorded as a blocker for multi-session machines; unchanged during the freeze |
| 9 | Provider outage: OpenRouter "Connection error" for more than 30s ended e6 (3 retries from 2s) | B, harness policy | Retries made configurable in the isolated driver (8 from 5s, about 21 min of tolerance); e7 then completed. Codex's runner still has 3 from 2s. |
| 10 | Provider stall on one long request: e8 got "Connection error" every ~5 min for 50 min while a tiny request succeeded | B, external | Operator stopped the run at 89 min. Retries cannot beat a request that stalls deterministically, so the harness needs a per-request stall limit with a different recovery (a fresh request, or compaction). |
| 11 | "call N" in the revival report is the call that last *bound* the name. A value changed in place by later calls (`push!(hist, …)`) is saved and restored current, but labelled with the old call. | D, labelling | Recorded; the value is correct |

No false continuity was observed. Across 4 revivals in the endurance runs, every value Luna then used was correct: all graded checks pass.

### 6. Exact remaining blockers for a supervised 72-hour run

1. **Pin the environment.** Set `NEURAJL_JULIA_BIN` to the Julia the depot was built for. Run `prewarm_depot.py` after any change to Neura or the project. A 72-hour run under a fresh `HOME` without the pin will silently use whatever juliaup's default is that day.
2. **Put revival state on disk.** Set `stateRoot` to a disk path, not the RAM-backed temp directory, and prune old session state between runs. For a single 72-hour session it is bounded (at most 128 MiB plus a transient copy), so this is operational, not a code change.
3. **The harness request cap.** `abc-agent.ts` hardcodes a 60-request budget and a 16k `keepRecentTokens`. The endurance runs used an isolated driver copy with 2,000. A real 72-hour run needs Codex's runner to take these from configuration, which is Codex's file to change.
4. **The provider path.** Two of the eight runs were damaged by the model provider, not the substrate: an outage (e6) and a per-request stall (e8). A 72-hour run will meet both. It needs outage-tolerant retries in Codex's runner, and a stall limit that abandons and re-issues a request that hangs.
5. **Duration.** Model-driven sessions reached 50–68 minutes and 254–270 calls; Luna finishes the backlogs faster than they can be written. The substrate alone ran a 2.5-hour soak (below). Behavior at 72 hours, including memory, context cost and model drift over days, is extrapolated from these, not measured.

### 7. Readiness verdict for a supervised 72-hour run

**Ready to start a supervised 72-hour run, with the five blockers above handled as preconditions. Not yet shown to succeed at 72 hours.**

**What the evidence supports:**
- The substrate held for 2.5 hours and 446 calls, with no drift in latency, memory, `/tmp` or snapshot cost, and was killed and revived 3 times without a single wrong value.
- Model-driven sessions of 50–68 minutes and 254–270 calls did real repository work with no coaching: 29 graded issues, a Python repair, a log analysis, and a JSON5 parser from scratch.
- Those sessions ran through up to 7 compactions, 2 kernel kills, a requirements change and an external source edit. Every graded check passed in every run that the provider did not interrupt.
- No false continuity was observed in 7 model-driven revivals or 3 soak revivals.

**What stands between this and a 72-hour success is mostly outside NeuraJL:**
- the provider path (outages and per-request stalls, which ended 2 of the 8 runs);
- the runner's hardcoded request budget and retry policy (Codex's file);
- deployment settings: pin Julia, put revival state on disk.

The substrate items this pass found, including the `/tmp` growth, the socket path limit and the Julia drift, are fixed and tested.

**The next step:** run the real 72-hour session under supervision once the runner takes its budget, retries and stall limit from configuration. The same supervisor can be reused, with its interventions, sampling and grading, and with work batches queued ahead.
