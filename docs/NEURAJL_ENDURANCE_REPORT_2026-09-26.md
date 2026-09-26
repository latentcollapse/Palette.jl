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
