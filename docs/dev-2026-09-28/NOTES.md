# NeuraJL development runs, 2026-09-28 (OpenAI key only)

## Smoke tests of the new build (lab 87344d4, NP2 c95976320)

**smoke1: the ISSUES backlog, 25 min.** 86 calls, $0.075, grade 9/13.
- The workspace map opened the first result.
- All 5 payload calls used named texts.
- The model ran every issue's test suite as a named background job (`issue1test` … `issue9test`), and the jobs line reported each one running, then finished, with a pointer to `fetch`. Nothing prompted this beyond the tool description.
- No digests appeared. That is expected: this task's failing output stays under 4,000 characters.
- **Driver bug.** The run ended three minutes early, with "no successful terminal response". A failed provider request is not kept in `session.messages`, so the recovery loop saw the model's last tool call (`toolUse`), took the turn as finished, and never re-prompted.
  - Fixed: the loop now recovers unless the last reply was a finished one (`stop` or `length`).

**smoke1b: the same task, on the fixed driver.** Exit 0, and it ran to the 25-minute deadline. 89 calls, $0.098, grade 4/13.
- 71 rate-limit retries. The organisation's 200k tokens-per-minute limit binds: each request carries up to about 57k tokens of context (cached tokens count), so only about 3 requests fit in a minute.
- Throughput in calls was the same as smoke1. The grade difference is how far each run got.

**Change for all pilots from here:**
- The context window drops from 100k to 60k, and kept-recent tokens from 16k to 12k. That is about twice the requests per minute, and more compactions, which exercises the map.
- Every arm of every A/B gets the same settings.

## p2-relay-hard controls

- The events check now runs the test 200 times, not 40. At 40 runs, a 2–15% failure rate can pass by luck.
- **Race left in, the other fixes applied:** `events_are_all_counted: 177/200`. The grade catches the race.
- The planner and db failures in that control came from applying only part of `reference_fix.sh`, not from the scenario.

## Digest A/B on relay (3 runs per arm)

| arm | solved | mean minutes | mean cost |
|---|---|---|---|
| digest on | 3/3 | 1.97 (1.6, 1.9, 2.4) | $0.0147 |
| digest off | 3/3 | 2.40 (3.1, 2.2, 1.9) | $0.0157 |

No measurable difference. Relay's failures are short, so the digest rarely fires. The discriminating test is p2-relay-hard, which has a 1,500-line build log.

## Defect: the stress merge broke the precompile workload silently (fixed, d1c557b)

- The first full suite run on the merge was invalid. It pointed at the wrong rnd directory, found no depot, and skipped almost every test while still reporting OK. `lab_suite.sh` now exits 2 when `depot/` or `project/` is missing, and prints skip counts.
- The valid run had 4 failures, all timing assertions on background jobs. Pre-merge `f1f4c5d` passed the same tests.
- **Cause:** the workload line `stress("exit $((STRESS_RUN % 2))")` is a Julia string, so `$(` interpolated. The line threw `UndefVarError`, and the workload's bare `catch` swallowed it. Every later item, the workspace map and snapshot/revival among them, went uncompiled. A trivial second call took 3.75 s.
- One hypothesis was wrong: that job-tracking tables baked into the image caused it. Resetting them in `__init__` changed nothing, so it was reverted.
- **Fix:**
  - escape the `$`: a trivial second call now takes 0.55 s;
  - the catch now logs `@warn "precompile workload stopped early"`. Red control: with the bug put back, precompiling prints the warning and names the `UndefVarError`.

## p2-relay-hard A/B (2 runs per arm, build d1c557b)

| arm | solved | minutes | requests | cost |
|---|---|---|---|---|
| full | 2/2 | 2.4, 2.2 | 41, 43 | $0.020, $0.014 |
| digest off | 2/2 | 3.3, 3.9 | 56, 59 | $0.025, $0.030 |
| map off | 2/2 | 3.9, 2.6 | 75, 47 | $0.023, $0.021 |

- **All six runs solved everything.** The race check passed 200/200 in every run, each fixed with `fetch_add`.
- **The full build used the fewest requests in both of its runs.** A mean of 42, against 57.5 with the digest off and 61 with the map off. It was also fastest, at 2.3 min against 3.6 and 3.25. With two runs per arm this is a direction, not a result.
- **The trace instrument has a red control.** The digest count is 0 in the digest-off arm and the map count is 0 in the map-off arm.
- **The stress runner was adopted 0/6 times, even though the description names it.** Luna checked the race with hand-written `for i in 1:N` loops instead. This fits the design rule: tools named only in the description go unused. Stress stays as an available tool, but it is not a gain.
- **The scenario still doesn't discriminate.** A mean of 3 minutes is too easy for Luna, and a harder task is needed to separate the arms.

## Afternoon (Matt's go-ahead): tin3, stress demoted, p3-relay-large

- **tin3** runs on the fixed harness: 60k context, 6 retries from 10 s, no OpenRouter, workspace on NVMe. Budget: $5.61 on the account, with $1.50 in reserve.
- **Stress removed from the NP2 tool description.** It was never committed as a revert: the unpushed commit that added it was dropped instead. `Neura.stress` stays in the kernel.
- **p3-relay-large** is at `~/.neurajl-runs/harness/njl/scenarios/p3-relay-large`. It is p2's 7 bugs plus 6 features from `SPEC.md`:
  - Rust quantiles and backoff;
  - a TypeScript query-string codec;
  - OCaml FFD packing;
  - a SQL priority migration and query;
  - a Go INI parser.
- **p3 controls:**
  - the reference solution passes every stage, 200/200 on the race;
  - the untouched fixture fails every real stage (`load` always passes; it only generates noise);
  - features alone leave the old bugs failing;
  - an edited test is caught.
- **Two authoring defects caught by the controls before any pilot ran:**
  - the spec and a test disagreed on indented key lines;
  - p2's `check.sh` inserted rows without naming columns, which broke once migration 003 added two. That would have made p3 unsolvable.
- **Next:** one calibration run on p3 after tin3 (they share the token limit), then the A/B if it runs 20+ minutes.

## tin3 finding: a 60k context causes a compaction loop

- **Symptom:** compactions went from 17 in hour 1 to 47 in hour 2, and cost doubled.
- **Cause:**
  - Every request carries about 30k tokens of fixed overhead: the system prompt, tool descriptions, the compaction summary and the harness state.
  - Compaction triggers at 60k − 16k reserved output = 44k.
  - Once the 12k kept-recent window refills, the context sits at the threshold. In two bursts (19:44–19:48 and 19:58–20:01 UTC) it compacted after nearly every tool call.
- **Cost:** each compaction breaks the prompt cache, so cached input drops to 1,510 tokens and the rest is billed at full price.
- **The workspace map adds to it:** by design, it opens the first result after every compaction.
- **Lesson:** shrinking the context to stay under OpenAI's per-minute token limit (200k) traded rate-limit errors for compaction loops.
- **Fix for the next run:**
  - a context of about 100k;
  - client-side pacing: a rolling one-minute token bucket, plus the server's retry-after;
  - output reserve 8k.
- tin3 was left running as-is. Its compactions under pressure are continuity data too.

## tin3 result (ended at 3.9 h by the $2.50 cost cap)

- **Grades:**
  - issues 13/13, batches 11/11 and 5/5;
  - textkit 61/61; json5 perfect; toml 45/45 valid and 15/15 invalid;
  - health checks 6/6 sessions ok.
- **Ports: 934, over 4 complete ports** (fnmatch, difflib, base64, format), with **no partial ports**. tin2 had 17 complete, with many half-done.
- **Continuity held:**
  - 255 compactions and a kernel kill at 1.5 h, with no broken work;
  - 19 recoveries, against 60 for tin2;
  - no OpenRouter traffic.
- **Throughput was lost to the compaction loop.** Uncached input came to 14.1M tokens, against tin2's 1.9M.
- **Budget:** about $3.10 left on the account.

## QA audit on tin1–3: the compaction loop's real cause (fixed, NP2 `021440738`)

The 60k window was not the whole story. After a compaction, the context was often still above the trigger: late in tin3, the first request after a compaction was 62–66k tokens, against a 44k trigger.

**Cause, found in the entries:**
- NeuraJL writes a `neurajl_state` note after every compaction. The notes were a median 4.8k characters each, one per compaction, and none was ever dropped.
- A kept tail that spanned several compactions carried a stack of them: 52k characters on average, and 19 notes in context at the last entry.
- `findCutPoint` counts only `type === "message"` entries toward `keepRecentTokens`, so the notes were outside the budget.
- More compactions meant more notes in the tail, which meant still more compactions.

**Fix:**
- Only the newest note reaches the model, the same rule as for the harness digest.
- Custom messages now count toward the kept budget.

**Checks:**
- Build-context tests 18/18; compaction and session-manager 191/191; NeuraJL real-kernel tests 41/41 (with the environment set, so none skipped); `tsgo` clean; biome clean; test policy passes.
- Red controls: both new build-context tests and the new `findCutPoint` test fail without their fix.
- `extensions-discovery` and `catalog-assets` fail 20/27 with or without the change, so those failures were already there.
- Replay of tin3's real entries at its last entry: 19 notes and 272k characters before the fix, 1 note and 140k characters after.

**Still open:**
1. **Encrypted reasoning** (`thinkingSignature`, 140k+ characters in context) is invisible to `estimateTokens`. Whether OpenAI bills it by length is unknown; the next run should compare reported input tokens against the estimate.
2. **The summary budget** is 0.8 × `reserveTokens` (about 13k tokens), not tied to the window size. At small windows, the summary alone takes a large share.
3. **The note's list of bindings is unbounded:** 7.4k characters at 1,000+ bindings. Only one note is now sent, but the list should still be capped.
4. **Harness pacing** (the server's retry-after and a token bucket) is still to build.

The regression of post-compaction size on content type was inconclusive (R² = 0.17) and is not used as evidence.

## Open tickets, closed (NP2 local commits; driver and harness on NVMe)

1. **Binding list capped** (`1ea0071be`). The compaction note and the lost-bindings notice now list at most 2,000 characters. Past that, the most recently set bindings are kept, the rest are counted, and the note points to `varinfo()`. Red control: the cap tests fail without it.
2. **Summary budget: closed with no change.** `historySummaryCompletionBudget` caps the summary's *output*; it is not a length target.
   - Lowering it would cut summaries off mid-sentence.
   - On a reasoning model, it could return an empty summary, because the cap also covers reasoning tokens.
   - tin3's summaries ran from 0.35k to 6.8k tokens, with no upward trend: under 7% of a 100k window.
3. **Retries and pacing.** The real defects were not in the pacing itself:
   - **The server's stated wait was never used** (`1339109a9`). OpenAI's TPM errors carry "try again in 578ms" in the text, with no header, so every retry slept the flat 10 s base. The wait is now parsed from the text. Red control done.
   - **A driver race turned retries into recoveries.** All 19 of tin3's recoveries fired 10.0 s ± 25 ms after a retry began. `waitForHeadlessIdle` returned in the gap between the retry's sleep and its re-issued request, so the recovery prompt replaced the retry. The driver now waits until neither retrying nor streaming. In tin4, retries reach attempts 2–6, where tin3 had only attempt 1.
   - **A latent trap:** `maxRetryDelayMs` 12 s makes any longer server wait fail the turn. It is now 60 s.
   - **Settings, both runners:** a 100k window, 8k output, a 16k kept tail, and a 2 s retry base.
   - **Token bucket not built.** The server states the exact wait, and retries now honour it.
4. **Encrypted reasoning is billed** (`326061256`).
   - **Measurement:** on tin4's first 53 consecutive requests, before any compaction, the growth in billed input fits text plus signatures at R² 0.958. Text alone fits at 0.546.
   - **Rates:** 0.13 tokens per signature character, and 0.32 per text character.
   - **The gap:** signatures outweighed text, 258k to 192k characters, and `estimateTokens` ignored them.
   - **Fix:** signatures now count at one token per 8 characters. Red control done.
   - **The instrument had failed twice first.** Rebuilding each request's context from the entries fit at R² ≈ 0. The cause was one entry pooling RLM child usage (60k input + 599k cached) and failed requests reporting zero usage. Differencing consecutive successful requests in the linear stretch before any compaction worked.

**Suites:** 243 tests pass across compaction, session-manager, provider-retry, bindings and the NeuraJL real-kernel suites, with none skipped. `tsgo` and biome are clean.

**tin4 live check:** 1 compaction in 33 minutes (tin3: 17 in its first hour). The kill at 0.42 h went through. There was 1 recovery, a legitimate one after 6 rate-limited attempts.

**tin4 final (45 min, $0.16):**
- 147 NeuraJL calls, the same pace as tin3's first 45 minutes.
- **2 compactions**, against about 13 for tin3 in the same span.
- 1 recovery, a legitimate one; 130 retries absorbed the rate limit. The kernel kill went through.
- **Grades:** 12/13 issues. The 13th is the requirement change delivered at minute 23, still in progress at the deadline. The batch, json5 and toml zeros are follow-ups the 45 minutes never reached; no follow-up had started.
- The compaction loop is gone, and retries no longer become recoveries.
