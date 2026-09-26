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
