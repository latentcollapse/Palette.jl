# NeuraJL overnight R&D, 2026-09-27

This was done during the 12-hour endurance run (tin1), under Matt's standing authority to fix defects and test hypotheses on NeuraJL's weak points. The live run loads Neura from the lab checkout, so all of this work ran in a separate worktree, `~/rnd/neurajl-lab-wt` on branch `rnd/closure-revival`. That worktree has its own project and depot copies (`~/.neurajl-rnd`). Nothing here reached the live run.

## Method

1. Classify every failed NeuraJL call in the endurance traces: e3–e8, the smoke run and tin1, 1,532 calls in all. `rnd/taxonomy.py` and `parse_errs.py` do this.
2. Read the live run's revival manifests and revival reports.
3. Turn each suspected weak point into a hypothesis. Test it in isolation, fix it, and prove the test fails without the fix.

## Findings and fixes

### 1. Closures were reported lost at every kernel death, but Julia can restore them

- **Hypothesis.** Julia's `Serialization` carries closures across processes, as Distributed.jl relies on, so revival's blanket refusal throws away state it could keep. This was the one area where the IPython arm's dill-based restore beat NeuraJL.
- **Evidence.** Two separate Julia processes round-trip a closure over a local, a closure with a captured `Ref` counter, a composed function, closures inside a `Dict` and inside a struct field, and aliasing between them. This works even when the defining function is not rebuilt first.
- **Two traps in the naive fix, each found by a failing test:**
  - `Serialization` sends a closure's whole type, method included, only for closures of the real `Main`. The kernel's eval module is a different module named `Main`, so its closures were sent by name.
    - A top-level lambda (`bare = x -> 2x`) then failed with "`#3#4` not defined".
    - A closure over a rebuilt function worked only because the rebuild happened to produce the same generated name.
    - **Fix:** revival writes snapshots with its own `SnapshotSerializer`, which overrides `should_send_whole_type` for the kernel module's closures only. A user's own `serialize` calls are unaffected.
  - Revival fingerprints every kernel-module type a value uses. Closure types have generated names that a new kernel reuses, so every closure was refused as "defined differently now".
    - **Fix:** closure types are not fingerprinted, because there is no definition to compare against.
    - Closure types do link bindings into one save group, so values sharing a closure type keep `===`.
- **Still refused:**
  - a closure capturing a Task: its captures are walked like struct fields;
  - a closure over a since-redefined struct;
  - a closure from a module the new kernel does not load.
- **Tests:**
  - `test_closures_come_back_with_their_captured_state` covers 14 assertions: captured locals, `Ref`, `Core.Box`, aliasing with a captured array, containers, a struct field, composition, `Base.Fix1`, a Task capture refused and a stale struct refused.
  - `test_a_revived_closure_runs_the_code_it_was_made_with` covers a redefined factory, and data lambdas next to const lambdas.
  - **Control:** with by-name serialization, both tests fail.

### 2. Regex and RegexMatch bindings were lost at every kernel death

- **Evidence.** At the 1.5 h kill, the live run lost `LOG_LINE_RE` (a `Regex`) and `issue28` (a `RegexMatch`), both refused with "it holds a pointer". The pointer is the compiled PCRE code, which `Serialization` already drops: it saves pattern and flags, and compiles again on load.
- **Fix.** A `Regex` is data.
- **Caveat.** Two bindings that share one `Regex` come back as two equal copies. Standard deserialization does not register a `Regex` for back-references, and a `Regex` cannot be mutated, so only `===` can tell. The code comment says so.
- **Test.** `test_regexes_and_matches_are_restored`.

### 3. A module defined in an included file was never rebuilt, and failed calls' `using` lines were reported as losses

- **Evidence**, from the same live revival:
  - `using JSON5Lite` at call 224 had failed (it is not a registered package), yet revival replayed it and reported "not revived: … rebuilding it failed". The model saw a loss of something it never had.
  - The module that `include("json5/src/JSON5Lite.jl")` created at call 227 was reported as "its `using`/`import` was not found". Include replay only re-ran `def` and `using` statements, and `module … end` was neither.
- **Fixes:**
  - `module` is a definition, and its name is recorded, so include replay rebuilds it.
  - For a failed call, a definition entry is kept only if something it binds exists afterwards. A function defined before the error is kept; a `using` that never took effect is dropped.
- **Test.** `test_an_included_module_comes_back_and_a_failed_using_is_not_a_loss` reproduces the live-run sequence exactly.

### 4. The quoting tax is the largest failure class, and it fails loudly

About a third of all failed calls come from one habit: writing file text (Julia or Python source) as a Julia string literal, instead of passing it through `payload`. The counts, over 136 failed calls out of 1,532:

| Mechanism | Failed calls | What the model saw |
|---|---|---|
| `$K`, `$new`, `$key` in source text interpolated in the kernel | 13 of the 18 `UndefVarError`s | "`K` not defined", with no word about interpolation |
| A docstring's `"""` ends the enclosing string, and the rest runs as code | 5, in 5 of 8 runs | `invalid keyword argument name "last::Bool"`, a lowering error far from the cause |
| Other parse errors (`$` in strings, juxtaposed strings, escapes) | about 26 | a `ParseError`, sometimes with the existing `$` hint |

Other measurements:
- `payload` is used in 3% of calls.
- 183 calls write files through triple-quoted Julia literals.
- Calls that embed a docstring inside a triple-quoted literal fail 33% of the time, against 8% for all other calls.
- **Silent corruption was measured and is absent.** A parser-based detector for interpolation into source-like text that a successful call wrote to a file finds **0 of 1,467** successful calls. It was validated on a synthetic positive, which it found, and an escaped negative, which it did not flag. Every interpolation into embedded source hit an undefined name and failed loudly.

**Fixes (hints only).** A hint teaches `payload` at the first failure, which is when Luna adopts it; before, the model never met a hint for these errors.
- **Docstring.** When the error's line lies in the text a docstring's quotes leaked, the hint names the line the string began on, the line that ended it, and `payload`.
  - It fires on 5 of the 136 failed calls, all true cases.
  - An earlier, looser detector fired on 14, including a kernel kill and an assertion failure, and was rejected.
- **Interpolation.** An undefined name that the call interpolates into a string gets a hint naming the interpolation, `\$name` and `payload`. It fires on 13 of the 18 `UndefVarError`s and on none of the other 5.
- **Tests:**
  - `test_a_docstring_that_ends_an_enclosing_string_is_named`, with a negative case;
  - `test_an_undefined_name_interpolated_into_file_text_is_named`, with a negative case.
- **Not measured yet:** whether the hints change behaviour, that is, whether Luna switches to `payload` after the first hinted failure. That needs a model run on the new build, after tin1 ends.

**Corrections made while measuring.**
- I first estimated the quoting tax at about 3% of calls from a regex count. That missed the lowering errors and the undefined names.
- I then attributed the undefined names to "method-body code run at top level". Reading the code showed they are interpolation.
- Both claims were in this draft before the evidence was read. The numbers above are the checked ones.

### 5. Do the hints change behaviour? A pilot says no

**Design:**
- The s11 OrderedCollections ISSUES task: the one on which the docstring failure happened in 5 of 8 endurance runs.
- OpenRouter Luna, the same NP2 driver, 4 runs per arm, run in two rounds of 2 per arm.
- The hints arm runs `rnd/closure-revival`.
- The control arm runs lab `7644239`: in round 1 on the lab checkout, in round 2 on a worktree pinned there after the lab had moved.

Tools: `docs/rnd-2026-09-27/pilot.py`, `pilot_analyze.py`.

**Results:**

| Arm | Runs that switched to `payload` after the first quoting failure | Quoting failures per run | Calls per run | Grade |
|---|---|---|---|---|
| hints | 1 of 4 (14 of 24 later writes) | 3, 1, 2, 2 | 87, 75, 108, 61 | 11/13 in every run |
| control | 0 of 4 (one run 1 of 5) | 1, 1, 2, 2 | 65, 67, 76, 86 | 11/13 in every run |

**Reading.** Luna saw the hints: in hints-b the call right after the docstring hint moved the file text into `payload`. But 3 of 4 hinted runs kept writing inline literals after one to three hints, and quoting failures did not fall. At this sample size, the hypothesis that a precise hint moves the habit is **not supported**. The hints stay, because they are accurate and cost nothing when nothing fails.

**The remaining lever is structural.** 72 of 277 edits needed two or more snippets (old and new text), and `payload` carries one string. A `payload` that accepts several named strings is the next thing to try. It is a new abstraction, so it needs its own evidence pass.

### 5b. Named payload texts remove the quoting tax once adopted

**Hypothesis.** The hints did not move Luna because `payload` could not carry what it needed. In the hint pilot, 90% of the inline writes after the first quoting failure embedded two or more texts, an edit's old and new, and one payload string cannot hold both. In the one hinted run that switched, the edits were appends, which one string can express.

**Change:**
- Lab branch `rnd/payload-parts` (`be972d5`): `payload` may be `{name: text}`, read as `PAYLOAD["old"]`. A string payload works as before. The hints show the edit form.
- NP2 `2aaa128e2`: behind the experiment switch `NEURAJL_PAYLOAD_PARTS=1`, the schema accepts a string or an object of strings, and the descriptions say how to edit with it. With the switch off, the schema and descriptions were checked to be identical to before.
- Test: `test_named_payload_texts_carry_an_edit`.

**Pilot.** The same task and harness as finding 5, with 4 runs in a "parts" arm.

| Arm | Runs that adopted `payload` | Payload calls using named texts | Quoting failures before adoption | After adoption |
|---|---|---|---|---|
| control (4) | 0 | – | – | – |
| hints (4) | 1 | – | – | – |
| **parts (4)** | **4** | **51 of 51** | 1, 3, 1, 1 | **0, 0, 0, 0** |

- After adoption there were **no quoting failures and no inline triple-quoted writes**, in any of the four parts runs.
- Two of the four adopted without a preceding failure, at their first multi-text edit. That is proactive use, which no hints or control run showed.
- Grades were unchanged: 11/13 in all twelve pilot runs.

**Limits.**
- Four runs on one task.
- The failures before adoption remain: the model starts out with the inline habit.
- Before making it the default, the next step is a run on a different kind of work, such as the stdlib ports, where whole files are written.
- It was not deployed in tin1: the running NP2 driver has neither the switch nor the schema.

### 6. The snapshot tax, and the check for a waiting request that never worked

**Evidence, from tin1:**
- Snapshots grew with the model's state: 98 MB took 25 s at 2.5 h, and 110 MB took 28 s at 3 h.
- The median call's time rose from 0.1 s to 2–9 s as the next call waited for the snapshot. About half of one ten-minute window went to waiting.
- The existing rule "a request already waiting goes first" never fired. The input stream does not read ahead between requests, so `bytesavailable` stayed 0; that was measured in isolation.

**Fix, on branch `rnd/snapshot-yield` (`746e223` plus a follow-up), not deployed in tin1:**
- **Detecting the waiting request.** The descriptor is polled (`poll`, `POLLIN`).
  - A closed input is not a request. The snapshot then completes as the last chance to save. A first version counted `POLLHUP`, and 24 revival tests failed.
- **Giving way.** A snapshot gives way to a waiting request only when the last complete snapshot took 2 s or more, and only while the last saved call is fewer than five calls back.
  - A quick snapshot always completes, so an ordinary session still revives the last completed call.
  - A first version without the threshold broke exactly that guarantee: the existing `test_kernel_death_mid_call_revives_the_last_completed_call` failed.
- **Package-image trap.** The precompile workload called `snapshot_state!(6)` and left `LAST_SAVED_CALL = 6` baked into the package image, so the staleness bound never fired. It is now reset with the workload's other globals.
- **Naming lost calls.** A `last_call` marker is written after every completed call. When the revived snapshot is older, the revival report says: "Calls N–M completed after this state was saved: what they changed in the kernel is lost."
- **Measured.** With a 65 MB state and a 2.4 s snapshot, the next call waited 2.8 s before the fix and 0.6 s after.
- **Tests.**
  - `test_a_request_does_not_wait_for_a_slow_snapshot_until_it_is_five_calls_old`;
  - `test_a_quick_snapshot_never_gives_way`;
  - `test_calls_completed_after_the_saved_state_are_named`.
  - Full suites pass: revival 29, session_cli 50, session 12, authority 27, Julia `Pkg.test`.
- **NP2 `25f9d0528`.** The model-facing notices say "the last saved state", and the report names the call. Previously they said "the last completed call".
- **Why not deployed in tin1.** The running NP2 driver cannot pick up that notice change, so it would tell the model "the last completed call" when the state could be older.

### 7. Two hypotheses about runaway compute, both falsified

A call whose compute never yields is interrupted, then the kernel is stopped, and the next call revives the state.

**Hypothesis 1: a SIGINT could interrupt such compute in place and save the kernel.**
- Test: `docs/rnd-2026-09-27/sigint_probe2.jl`, one process per case, with the signal sent from outside as a host would.
- Results:
  - a tight integer loop and an allocating loop were not interrupted, even by a second SIGINT;
  - a floating-point loop and a large sort **segfaulted the process**.
- The current design, stopping the kernel and reviving it, is the right one.

**Hypothesis 2: the model re-runs the code that stopped the kernel.**
- Evidence: 3 runaway stops across all the traces, all in tin1.
- The next call's similarity to the one that stopped the kernel was 0.25, 0.25 and 0.06. The model changed its approach each time.
- Nothing to fix, and nothing was added.

## Negative controls

All five tests for findings 1–4 that existed at the time were run against the original source with the new test files. All five fail there, and all pass on the fixed source. The interpolation hint's test asserts text that only the new code produces.

The full lab suites on the final branch (`rnd/closure-revival`: `5723110`, then `c11d6d3`) pass:

| Suite | Tests |
|---|---|
| `test_revival` | 27 (23 before) |
| `test_session_cli` | 50 (48) |
| `test_session` | 12 |
| `test_authority` | 27 |
| Julia `Pkg.test` | passes |

A first full run caught a bug in my own change: the failed-call check read the call's result as an `OperationResult` when it is an `OperationReceipt`. Every call then counted as failed, and methods like `Base.show(...)` were dropped. Two existing revival tests caught it. It was fixed, and a test for a method of another module's function defined before an error was added.

## Harness findings (fixed and committed separately; see `docs/endurance-pass-2026-09-26/12h/README.md`)

- **Incident 1.** A destroyed HTTP/2 session was pooled by Node 26's bundled undici 8. The endurance driver now installs cli-main's dispatcher. Codex's `abc-agent.ts` has the same exposure and was not edited.
- **Incident 2.** Finished RLM children kept their kernels. Fixed by NP2 `425c61161`: an idle kernel is stopped and revived on its next call.

## Not done, and why

- **Merging into the lab checkout.** The 12-hour run loads Neura from it, so the branch is merged after the run ends, then `prewarm_depot.py` is rerun for the trial depot.
- **Regex identity across bindings.** Keeping it needs a custom read path through Serialization internals. The only thing it buys is `===` between two bindings, so it is low value.
- **Julia API errors the model makes**, such as `findfirst` on strings returning a range, and top-level method-body code. These are model fluency, not substrate. A description hint might help, but there is no adoption evidence, so it was not added (the feature-creep rule).
