# 12-hour NeuraJL endurance run (tin1)

Started 2026-09-27 04:09 EDT; deadline 12 h. Live checkpoints are appended hourly to `checkpoints.md` in this directory.

## Setup

- **Driver**: `tools/endurance-agent.ts`. This is an isolated copy of NP2's `scripts/abc-agent.ts`, which is left untouched. The model is `gpt-6-luna` at reasoning effort max, with a 100k-token context and 16k-token output.
- **Primary route**: direct OpenAI, via the Responses API.
- **Backup route**: OpenRouter pinned to OpenAI, via the Chat Completions API.
- **Failover, three layers**:
  1. The session's own `providerBackupModel` re-issues a failed request on the backup at once. The next prompt goes back to the primary.
  2. A stall watchdog aborts a request that makes no progress for 10 minutes. A failed request or a retry does not count as progress.
  3. A recovery loop handles a turn that still ends in `error` or `aborted`. It switches route and re-prompts with a continue message, at most 60 times per run.
- **Queue**: the initial ISSUES.md prompt comes first. After it come 10 existing follow-ups (json5, toml, textkit, logs and maintenance). Then 32 ports of Python stdlib modules to Julia, which appear in `scenario/p*.txt`. Last come 8 open-ended verification passes (`scenario/h*.txt`), there so the queue cannot run dry before the deadline.
- **Interventions**:
  - Kernel SIGKILL at 1.5, 4, 6.5, 9 and 11 h.
  - A requirements change appended to ISSUES.md at 70 NeuraJL calls.
  - A teammate comment in `src/` at 150 calls.
  - A teammate header comment on the oldest port file at 5 h.
- **State**:
  - Revival state lives on disk at `~/.neurajl-endurance-state/tin1`, not in tmpfs.
  - Julia is pinned to 1.12.6 through `NEURAJL_JULIA_BIN`.
  - A cost cap of $9 is enforced by the supervisor.

## Port grading

`tools/ports/spec.py` holds CPython 3.14.7 adapters. They generate 2,903 hidden golden cases across the 32 ports, of which 186 expect an exception. Prompts show at most four examples per port.

`tools/ports/grade_ports.jl` loads each port file into a fresh module and compares results:

- floats within a relative tolerance of 1e-9;
- floats exactly for `numeric`, `random` and `struct`.

Each port is graded in its own Julia process with a 300-second timeout. The goldens are held back from this repo until the run ends, because the lab repo is readable by the agent's sandbox.

Controls, all run before launch:

| Control | Score |
|---|---|
| Empty workspace | 0/2903 |
| Stub returning `nothing` for every function | 2/2903 (the two cases whose answer is None) |
| Julia shims that answer every call through CPython (`make_shims.py`) | 2903/2903 |

The oracle control caught a real defect: `quote` is a Julia keyword. The API was renamed to `shell_quote` and `url_quote`.

## Pre-launch verification

`tools/failover_test.py` runs a small real task: sum of squares written to `answer.txt`.

| Case | Primary route | What happened | Answer |
|---|---|---|---|
| refused | port 9 | native backup retry to OpenRouter | 338350 |
| blackhole | a server that accepts connections and never answers | 60 s stall abort, then recovery on OpenRouter | 338350 |
| healthy | direct OpenAI | 0 retries, 0 recoveries, all on direct OpenAI | 338350 |

In all three cases both key files were unlinked by the driver.

The smoke test was a 12-minute run of the full supervisor on fnmatch and shlex:

- fnmatch scored 178/178 and shlex 41/41.
- The kernel SIGKILL at 3 min was followed by a new-epoch revival report.
- The teammate port edit and three checkpoints were written.
- The deadline abort worked.
- Cost was $0.11.

The smoke test also found that the OpenAI organisation is limited to 200k tokens per minute. Requests that hit the limit were served by the backup route, as designed.
