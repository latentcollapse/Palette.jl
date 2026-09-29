# Drivers

These run Palette inside NP2 against a live model. They are copied from where they run (`~/.palette-runs/`) so the working versions are saved.

| File | What it is |
|---|---|
| `endurance-agent.ts` | The NP2 driver. It lives at NP2 `scripts/.endurance-agent.ts`, run with `tsx`. It builds a Palette-only session and runs the prompt and the follow-up queue, with a recovery loop, a stall watchdog and a deadline. |
| `endurance12.py` | The long-run supervisor (tin1–tin4). It sets up the workspace and scenario, delivers follow-ups and teammate interventions, kills the kernel on schedule, enforces the cost cap, and grades at checkpoints. |
| `pilot.py` | A single short run of one scenario, graded with the scenario's `grade.sh`. |

## Settings as of 2026-09-28

- **Context:** 100k window, 8k output, 16k kept tail.
- **Retries:** 6, from a 2 s base; a stated server wait of up to 60 s is honoured.
- **Failover:** OpenRouter only with `--backup`.
- **Workspaces:** on NVMe.

The reasons are in `docs/dev-2026-09-28/NOTES.md`.

## The race fix in `endurance-agent.ts`

`settle()` waits until the session is neither retrying nor streaming before judging a turn. Before this, `waitForHeadlessIdle` could return between a retry's sleep and its re-issued request, and each such return became a recovery (all 19 in tin3).

Keys are read from files outside the repository; these scripts contain none.
