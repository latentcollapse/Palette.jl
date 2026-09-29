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

## Incident 1: every request failing instantly, fixed live (04:12–04:42 EDT)

**Symptom.** From about 3 minutes into the run, every OpenRouter request failed within about 20 ms with "Connection error.". Direct OpenAI worked until it hit the organisation's 200k tokens-per-minute cap. At that point the backup and recovery path switched to OpenRouter, which always failed. Later, api.openai.com failed the same way. By the time of the fix, 34 of the 60 allowed recoveries had been used, and the NeuraJL call count had stalled at 73.

**What was ruled out.**
- The network: curl reached both hosts in about 0.2 s.
- The request content: replaying the same context from a fresh process succeeded, with 155 KB bodies and HTTP 200.
- File-descriptor exhaustion: 34 open fds.

**Cause.** Node's inspector was opened on the live driver with SIGUSR1, and a `fetch` evaluated inside that process returned `ERR_HTTP2_INVALID_SESSION: The session has been destroyed` for both provider origins, while example.com returned 200. Node 26.8.2 bundles undici 8.10.2, which uses HTTP/2. The run's first OpenRouter request was cut mid-stream (undici "terminated", 08:12:45Z), and undici then kept the destroyed HTTP/2 session in its pool. The CLI entry point never meets this, because `cli-main.ts` installs its own dispatcher (undici 7.29 `EnvHttpProxyAgent`). The endurance driver was copied from `scripts/abc-agent.ts`, which does not install one.

**Fix.**
- In the live process, through the inspector: `setGlobalDispatcher(new EnvHttpProxyAgent({ bodyTimeout: 0, headersTimeout: 0 }))`, exactly what cli-main does. Both origins answered at once (200 and 401), the next backup retry succeeded, and the run continued in the same session. The inspector was then closed.
- The same line was added to `tools/endurance-agent.ts`. The refused and healthy failover tests were re-run on the patched driver, and both passed.

**Also affects `scripts/abc-agent.ts`.** It has no dispatcher either, so any A/B/C trial whose stream is cut can fail every request after it. That file is Codex's; this is reported here and it has not been edited.

**Test gap.** The pre-launch failover tests covered a refused connection and a blackhole, but not a stream cut mid-response. That case is what poisons the pool.

## Incident 2: finished RLM children keep their kernels (found 04:45, mitigated 04:53 EDT)

**Symptom.** At 04:11 the model spawned two RLM children from code: `ordered-dict-set-audit` and `little-dict-audit`. Both finished at 04:13. At 04:45 their sandboxed Julia kernels were still running, with no calls since 04:12.

**Cause.** `registerRlmChildSession` retains a finished child for the parent's lifetime, so that it stays addressable. The NeuraJL base-tools scope is disposed only with the session, so each child's kernel (about 0.5–0.8 GB) also lived for the rest of the run. At the observed rate this grows without bound over 12 h. The machine has 31 GB, of which 17 GB was available.

**Fix, NP2 `425c61161` (not pushed).**
- `createNeurajlBaseToolsFactory` stops a kernel that has had no call for 20 minutes (`idleStopMs`).
- The stop applies only when state is saved, so the next call revives the kernel's state. The notice says it was stopped "after 20 minutes without a call, to free its memory".
- A call in progress is never stopped.
- The real-kernel test `an idle kernel is stopped and revived on the next call; a long call is never stopped` passes (15/15 across the NeuraJL and compaction test files; `tsgo` and the test-policy check are clean).
- Negative control: with `idleStopMs: 0` the same test fails ("expected 3 to be less than 3").

**Live run.** The running driver loaded the old tool code, so `tools/reaper.py` applies the same policy from outside. It sends SIGTERM to a `session_cli` whose state directory has had no write for 20 minutes; `session_cli` tears down its sandbox on SIGTERM, as the tool's dispose does. At 04:53:57 it stopped both children's kernels, idle for 41 minutes, and available memory rose from 17 to 19 GB. Stops are logged in `runs/s12--tin1/reaper.jsonl`.

## Build change at the 4 h kill (decided 07:15, deployed 07:22 EDT)

**Why.** From 0 to 4 h, tin1 ran lab `7644239`. The overnight R&D (`docs/NEURAJL_RND_2026-09-27.md`) fixed revival defects that tin1 itself exposed at its 1.5 h kill:
- a Regex and a RegexMatch were lost;
- a failed `using` was reported lost;
- an included package module was not rebuilt.

It also made closures revivable. The fixes had passed the full lab suites: revival 27, session_cli 50, session 12, authority 27, and Julia `Pkg.test`. Each new test fails on the old source.

**What was deployed.** Lab `main` was fast-forwarded to `917b18d` at 07:22, and the trial depot was prewarmed. Five revival tests, run against the deployed build with the trial project and depot, passed at 07:25.

**Who gets the new build.** The running kernel keeps the old build. The 4 h SIGKILL (about 08:09) starts the main kernel on the new build, which revives the old build's snapshot. The two builds use the same manifest format. RLM children started after 07:22 also get the new build.

**What this does to the run's claim.** tin1 is 4 h of `7644239`, then 8 h of `917b18d`, not 12 h of one build. The later kills (6.5, 9 and 11 h) test the new revival code on a real, large state.

**Not deployed.** The snapshot-yield change (branch `rnd/snapshot-yield`). Snapshots of this run's 110 MB state take 28 s, and the median call waits about 9 s for them. The change lets a waiting request go first, but it weakens the "revives the last completed call" guarantee, which one existing test enforces. It needs a design pass, not a deploy under a deadline.

### The new build in the live run

The main kernel ran the new build before the scheduled 4 h kill. At 3.56 h the model's own non-yielding compute ran past the 60 s limit twice, and the kernel was stopped each time. From then on, new kernels started on `917b18d`.

| Revival | Restored exactly | Rebuilt from source | Marked not the same | Not revived |
|---|---|---|---|---|
| 3.59 h (runaway compute) | 170 | 12, including the modules PyHeapq, PyJson and PyShlex that the model defined in included port files | – | 1 |
| 4 h (scheduled SIGKILL of 7 kernels, the main one and six RLM children) | 172 | 15, including six port modules and JSON5Lite | 2: PyHeapq and PyJson, "rebuilt from a file that changed since", which is correct because the model had edited them since including them | 1 |

- **Under the old build these modules were lost.** `module … end` in an included file was never replayed.
- **The one "not revived" item in both revivals** is the failed `using JSON5Lite` of call 224, logged by the old build before the fix. The definition log carries it forward, so it recurs at every revival in this run. New failed calls are no longer logged this way.
- **The 4 h revival call took 26.6 s:** the state is about 110 MB.

## Grader defect found and fixed at about 5.5 h

- **Defect.** `grade_ports.jl` decoded special floats (`{"__float__": "inf"}`) in expected values but passed arguments to the port raw. A Julia port was therefore called with a dict where it should have received `Inf` or `NaN`. This affects the 50 `format` cases whose argument is `inf` or `nan`, the only such cases in the goldens.
- **Why the controls missed it.** The oracle shim sent the arguments back to Python, which decoded them. The positive control never passed a decoded argument to Julia code.
- **How it was found.** A ports pilot: five of six independent `format` ports scored exactly 537/583, all failing the same `inf` cases.
- **Fix.**
  - Arguments are decoded before the call.
  - The shim re-encodes non-finite floats for its JSON trip to Python.
  - Controls afterwards: `format` scored empty 0, stub 0 and oracle 583/583.
  - The pilot's ports then scored 583/583 in five runs and 568 in one.
- **Effect on tin1.** The checkpoints up to 5 h under-report `format` by up to 50. The grader runs afresh at each checkpoint, so later checkpoints and the final grade use the fixed one.

### 6.5 h and 9 h kills, and a second deploy (13:35 EDT)

- **6.5 h kill.** The revival restored 166 bindings exactly and rebuilt 31 definitions: types, functions and six port modules. It marked 8 port modules "rebuilt from a file that changed since", which is correct.
- **9 h kill.** The revival restored 170 exactly and marked 15 changed modules.
  - The report was 23 KB, so the model saw it cut in the middle at the 12,000-character cap. The whole "rebuilt from source" list fell in the cut.
  - Luna does not call `Neura.output` to read the rest.
- **Fix** (`05becce`, merged as `cc0a79b` and deployed for the 11 h kill):
  - The report now leads with what needs attention: lost, different and stale. Rebuilt and restored-exactly come last.
  - Those two lists are shortened past 1,500 characters, first to names and then to a count. `varinfo()` has every binding.
  - Short reports keep their exact form.
- **Checks.** Full suites pass: revival 28, session_cli 50, session 12, authority 27, Julia `Pkg.test`. After the trial depot was prewarmed, the new test and the closure test also passed on the deployed build.

## End of the run: power loss at 10.0 h (14:09:51 EDT)

The machine lost power at 14:09:51, 10.0 h into the 12 h run. The kernel journal of the previous boot ends then, and the next boot was 21:47. Neither the substrate nor the harness failed.

**What was lost.** `/tmp` is RAM-backed, and it held all of the following:
- the scratchpad: the supervisor's run directory, the trace, the workspace with the model's port files, the pilot traces and the generated goldens;
- the final grading, including the ISSUES, json5, toml, textkit and logs graders, which were due to run at the deadline.

**What survived:**
- this README and `checkpoints.md` up to 10.02 h, on the lab disk;
- the tools in `tools/`: the driver, the supervisor, `spec.py` (which regenerates the goldens deterministically) and the graders;
- the revival state directories on NVMe;
- NP2, and the R&D worktrees and depots.

**The 10.02 h checkpoint is the run's final record:**

| Measure | Value |
|---|---|
| NeuraJL calls | 1,540 |
| Model requests | 2,792 |
| Compactions | 53 |
| Cost | $3.50 |
| Follow-ups started | 36 of 50 (up to `p26-strftime`) |
| Kernel kills survived | 1.5, 4, 6.5 and 9 h scheduled, plus 2 runaway stops |
| Stalls | 0 |
| Recoveries after 04:42 | 4 (38 in total) |

Ports stood at **2,621/2,903**:
- The six ports not yet reached (string, checksum, itertools, escape, emailutils, literal) account for 276 of the cases.
- On the 26 ports attempted, 2,621 of 2,627 cases pass (99.8%). 24 ports are perfect; statistics is 179/180 and fractions 65/70.
