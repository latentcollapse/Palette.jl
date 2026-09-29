# Morning report, 2026-09-28

The night's work followed the approved plan: smoke tests, then the A/B pilots and the stress runner, then a long run. The lab is at `main` and pushed. Details are in `NOTES.md` next to this file.

## Headline

- **Gains, as a direction rather than a result.** On the harder scenario, the full build (digest and map on) was fastest and used the fewest requests in both of its runs:

  | Arm | Mean requests | Mean minutes |
  |---|---|---|
  | Full build | 42 | 2.3 |
  | Digest off | 57.5 | 3.6 |
  | Map off | 61 | 3.25 |

  That is two runs per arm, so it is not proven. On the easy relay scenario the arms could not be told apart.
- **The long run (tin2) was correct on everything it finished, but it was cut short by the provider setup, not by NeuraJL.** Its full results are further down.
- **The stress runner was never used: 0 of 6 runs.** Luna wrote its own loops instead. This confirms the design rule again: a tool that is only named in the description goes unused.
- **Spend was about $1.80 of the $6.80.**

## Defects found and fixed

1. **The stress merge silently broke the precompile workload** (fixed in `d1c557b`).
   - A `$((…))` inside a Julia string threw an error, and a bare `catch` swallowed it.
   - Every later workload item went uncompiled: a trivial call took 3.75 s instead of 0.55 s, and 4 tests failed.
   - The catch now warns. Red control: the warning fires when the bug is put back.
2. **The suite script reported OK on a run that never happened.** Pointed at the wrong directory, every test skipped and it still said OK. It now exits 2 when the depot is missing, and prints skip counts.
3. **The long-run harness put its workspace in `/tmp`** — the same way tin1 lost its workspace. It now defaults to NVMe.
4. **The long-run harness hit OpenAI's rate limit and failed over to an OpenRouter account with no credits:**
   - OpenAI's limit is 200k tokens a minute. A 100k-token context hit it 292 times, most of them in tin2's last hour.
   - Each rate-limit error then went through 3 attempts on the OpenRouter backup, which failed with 402 every time (626 in total) and spent one of 60 recoveries.
   - Once the recoveries ran out, failed turns abandoned their work.
   - Fix: the harness now uses a 60k context, 6 retries from a 10 s base, and failover only when `--backup` is passed.
5. **The difficulty scenario (p2-relay-hard) could pass its race check by luck.** 40 runs of the race check could pass a 2–15% race by luck, so the check now runs 200 times. Red control: with the race left in, it scored 177/200.
6. **I made two mistakes in my own work, both caught:**
   - A `git commit -a` in NP2 swept in Codex's uncommitted `abc-agent.ts`. I undid it before anything else happened, and nothing was pushed.
   - I killed the first tin2 launch with `pkill -f`. That killed my own shell and left the driver spending on its own. I found it and killed it by PID.

## tin2: 3.5 h planned, ended at 2.85 h

| | |
|---|---|
| Issues | 13/13; batches 2–3: 11/11; batch 6: 5/5; test suite passes |
| textkit | 61/61 |
| json5 | 50/50 valid, 20/20 invalid |
| toml | 43/45 valid, 15/15 invalid |
| Health checks | 6/6 sessions ok |
| Ports | 1797/2903: 17 ports complete, the rest half-done or missing |
| Kernel kill at 1.5 h | the run continued |
| Compactions | 10 |
| NeuraJL calls | 359 |
| Cost | $0.86 |

The half-done ports are the rate-limit failure above, not a kernel or NeuraJL problem. Examples:
- `format` 53/583
- `pystr`: parse error, cut off mid-edit
- `base64`: a module that was never defined

Everything completed before 12:00, when the rate limit took over, is correct.

## Recommendation

1. **Re-run a 3.5 h tin3** on the fixed harness, about $1.50. This is the clean measurement tin2 should have been.
2. **Build a scenario hard enough to separate the A/B arms.** Both scenarios so far were solved in about 3 minutes. The digest and map direction needs a task that takes 20 minutes or more before it can be called a result.
3. **Decide whether to keep `stress` in the tool description.** It costs description space and was used 0 of 6 times.
