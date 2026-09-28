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
