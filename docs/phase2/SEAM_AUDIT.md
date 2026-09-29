# Phase 2 seam audit (2026-09-28)

**The invariant, as it now stands:** the same NIRA chassis hosts a model whose persistent, native operator environment is Julia, including RLM sub-agent orchestration, with no IPython dependency and no Python privilege layer.

## Evidence

- **The chassis, on the Rust host.** NP2's NeuraJL real-kernel suite passes 13/13 on `neurajl-host`, with no session_cli configured. It covers:
  - `Neura.rlm` spawn and collect, in one call and across calls;
  - a failing child, reported exactly as the chassis reports it;
  - no permission, meaning no child and no mention of it in the description;
  - a child that outlives its kernel and is found after revival.
- **Nothing Python ran.** A process census over that run sampled the Rust session 324 times, and a Python host or kernel (`session_cli.py`, `security/*`, ipykernel, `prime-agent-runtime`) never.
- **The same run, wider.** 430 NP2 tests across 19 files pass on the Rust host.
- **The lab's own suites pass on both hosts:**

  | Suite | Tests |
  |---|---|
  | revival | 32 |
  | session_cli | 56 |
  | session | 12 |
  | authority | 27 |
  | host bridge | 11 |
  | Julia `Pkg.test` | 18 testsets |

  `security/host_adapter.py` points every session, worker and broker the tests use at the binary, so the adversarial authority tests exercise the Rust broker.
- **Red controls:**
  - with the Rust broker's write allowlist disabled, the denial test fails;
  - without NP2's host-request dispatch, a spawn times out;
  - without the type allowlist, two bridge tests fail.
- **Live:** tin5 (40 min, a kernel kill included) and tin6 (30 min, NeuraJL only) ran Luna on the Rust host with the RLM permission. Both solved 13/13 issues, and no Python host or kernel ran. Adoption is reported in `FREEZE_AND_HANDOFF.md`: with both routes, Luna used the chassis's `rlm` tool. Julia-route adoption is not yet measured.

## The seams closed

| Seam | Now | Commits |
|---|---|---|
| RLM from the kernel | `Neura.rlm.*` → broker category `host_request` (off by default; `allowed_types` only; receipted; a child's types must be an explicit subset) → mid-call host request → the chassis's existing TypeScript RLM handlers. No second implementation. | lab `1dee19f`; NP2 `f61ac8e57` |
| Kernel ↔ host messaging | A general mid-call mechanism, not RLM-specific. Stdin is read on its own thread; one output lock; late replies are dropped; a host disconnect fails every waiter; a request times out before its call would. Ephemeral workers get no host. | lab `1dee19f` |
| Python privilege layer | `neurajl-host` (Rust) replaces session_cli.py, session.py, broker.py, launch_worker.py and prewarm_depot.py, with every hardening fix kept. NP2 uses it when `hostBin`/`NEURAJL_HOST_BIN` is set. | lab `3011473`; NP2 `5b49f13a8` |

**The Rust port is about authority, not speed.** Per-call latency is 1.81 ms against 2.05 ms (median of 30), and startup is 1.3 s against 1.4 s. Julia dominates both.

## Python that remains, classified

### 1. Migrate to Julia (belongs in the persistent operator substrate)

**Thin skill wrappers.** These are the upstream skills that only make a host request:
- `agent-message` (`agent_message.send`);
- `agent-observe` (`agent_observe.get`/`list`);
- `compact` (`compact.run`/`status`);
- `goal` (`goal.get`/`create`/`complete`);
- `refine` (`refine.run`/`status`);
- `rlm-heartbeat` (`rlm_heartbeat.*`);
- `model.info`, from `attach-image`.

The mechanism is already general, so each needs only a `Neura.*` wrapper and its types added to the session's `allowed_types`. There is no new transport. Port them when a NeuraJL session needs the capability.

**MCP tool calls.** Today they run in the Python REPL's `mcp` object (`prime-agent-runtime/src/rlm/mcp.py`). The TypeScript `McpManager` only manages configuration and connections. The system prompt offers MCP only to IPython sessions, so a NeuraJL model is not misled, but it has no MCP access.

The seam is the same shape as RLM: `mcp.list_tools` and `mcp.call_tool` as host-request types, served by a TypeScript MCP client in the chassis, with a `Neura.mcp` wrapper. This is **the next seam**.

### 2. Migrate to Rust (lifecycle, authority, supervision)

**Done:** the lab's host layer (above).

**Remaining:**
- `security/session_cli.py`, `session.py`, `broker.py`, `launch_worker.py` and `prewarm_depot.py` stay for one release, as the reference implementation the conformance suite also runs against.
- Delete them once NP2's default is the Rust host.

### 3. Retain (replacing it buys nothing)

- **`prime-agent-runtime/src/rlm/`** (6.1k lines: repl, bash, harness, mcp, the Windows job helper). This is the IPython kernel's runtime. A NeuraJL session never loads it; the census confirms none ran. It serves the IPython surface, which is set aside as the conventional-stack surface, not removed.
- **`scripts/evals`, `scripts/benchmarks`** (6.8k lines): offline measurement tooling.
- **Lab `julia_analyzer.py`**: a CI pre-check, before the authoritative `Pkg.test`.
- **`.github/scripts/discussion-notifier`**, **`scripts/render-logo.py`**: repository tooling.
- **The lab's Python tests and `host_adapter.py`**: test drivers. They judge the host; they are not the host.

### 4. Delete, or archive as superseded

- **Lab `scripts/real_ijulia_proof.py` and `scripts/ijulia_test_harness.jl`:** Experiment 001 (the IJulia era), superseded by NeuraJL. Archive them with the research record; CI still runs their job.
- **NP2 `harness_check.py`:** a one-off check from the 2026-09-23 baseline that lists skills that no longer exist (`linear`, `notion`).
- **Local-only skills** added in the 2026-09-23 baseline and never upstream: `arxiv`, `free-model-optimizer`, `knowledge-graph`, `neurosymbolic`, `neurosymbolic-harness`, `rotorquant`, `subquad-attention`, `symbolic-memory`, `tencentdb-memory`, `wikipedia`, `wolfram-alpha`. They run only in IPython. Matt should decide per skill: keep as research, port, or drop. Not deleted here.

## TypeScript candidates, at a higher bar

**None extracted.** The one measurement taken says the host boundary is not a bottleneck. No TypeScript component was shown to be one either:
- The retry, compaction and estimate defects found in the long runs were fixed in place, surgically, with tests.
- Nothing measured points at provider streaming, session storage or the agent loop as a cost.

Revisit only with a measurement.

## Found on the way, not fixed (chassis behaviour, shared by both kernels)

**A child whose model fails partway is reported `done` with no answer.** Only a child that fails to *start* is reported `error`. `Neura.rlm.collect` reports exactly what the chassis reports, as the Python kernel does. Whether the chassis should report a mid-run model failure as `error` is a chassis decision, not a seam.
