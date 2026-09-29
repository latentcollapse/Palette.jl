# NeuraJL research phase: frozen. The chassis, handed over. (2026-09-28)

## What the architecture can now say

The same NIRA chassis can host a model whose persistent, native operator environment is Julia, including RLM sub-agent orchestration, with no IPython dependency and no Python privilege layer.

The evidence is in `SEAM_AUDIT.md`: the tests, the red controls, a process census, and a live run.

## The frozen state

| Piece | Where | Commit |
|---|---|---|
| NeuraJL kernel (`Neura`, `Neura.rlm`, revival, digest, map, stress) | lab `src/`, `scripts/session_loop.jl` | lab `main` |
| Rust host (`neurajl-host`: sandbox, session, broker) | lab `host/` | lab `3011473` |
| Python host (reference implementation, one release) | lab `security/*.py` | lab `3011473` |
| Chassis integration (NeuraJL tool, host handlers, Rust host switch) | NP2 `packages/coding-agent/src/core/tools/neurajl.ts` | NP2 `5b49f13a8`, saved as lab `np2/patches/` (45 patches, verified) |
| Endurance driver and runners | lab `drivers/` | lab `main` |
| Comparison workload, built and controlled but never run | lab `research/workloads/p3-relay-large/` | lab `b600018` |
| Research record | lab `docs/` (endurance passes, dev notes, audits) | lab `main` |

"Frozen" means the research phase is closed. NeuraJL is no longer a prototype that must justify each decision. From here, defects found in use are ordinary bug reports and pull requests against this state.

## Running the chassis on Julia, with no Python

1. Build the host once: `cd host && cargo build --release`.
2. Prewarm the depot once per depot, and again after Neura or the project changes: `neurajl-host prewarm --project-dir <project>`.
3. Point NP2 at the host: `NEURAJL_HOST_BIN=<lab>/host/target/release/neurajl-host`, with `NEURAJL_PROJECT_DIR`, `NEURAJL_REPO_DIR`, `JULIA_DEPOT_PATH` and `NEURAJL_JULIA_BIN`.
4. Grant sub-agents from Julia per session, through the ceiling:
   - `{ host_request: { allowed_types: NEURAJL_RLM_REQUEST_TYPES } }`;
   - or, in the endurance driver, `NEURAJL_RLM=1`.
   - Without it, `Neura.rlm` is denied and the tool description does not mention it.
5. Check it: `scripts/lab_suite.sh <checkout> <rnd-dir> rust` runs every lab suite against the Rust host.

## What Phase 2 (the NIRA retrofit) inherits

**The next seams, in order** (details in `SEAM_AUDIT.md`):
1. MCP tool calls as host requests, with `Neura.mcp`;
2. the thin skill wrappers (goal, compact, refine, agent-message, agent-observe, rlm-heartbeat, model.info) as `Neura.*` calls;
3. making the Rust host NP2's default, then retiring the Python reference host.

**Open decisions for Matt:**
- the local-only skills from the 2026-09-23 baseline;
- the chassis's `done` status for a child whose model failed partway;
- the timing of the Cyan rename (`REBRAND.md` in NP2).

**Budget-bound work:** the head-to-head against a steelmanned IPython, and p3's first runs.

## Adoption (measured, not assumed)

Two live Luna runs, both on the Rust host with the RLM permission granted. The ceiling the host was started with is in the census, so the tool description named `Neura.rlm`.

**tin5**: 40 min, both routes available (NeuraJL plus the chassis's `rlm` tool), a kernel kill at 20 min.
- 13/13 issues; 1 recovery; $0.14.
- Luna delegated once: it spawned a reviewer and collected it three times, **through the `rlm` tool**. Zero `Neura.rlm` calls.
- The live kill: the kernel revived truthfully on the Rust host; the child's kernel was a Rust-hosted kernel too.
- Census: 787 samples of the Rust session, none of a Python host or kernel.

**tin6**: 30 min, NeuraJL as the only tool, so `Neura.rlm` was the only route.
- 13/13 issues, 105 calls, no recoveries, $0.09.
- Zero `Neura.rlm` calls: Luna did not delegate.

**What this shows:**
- **The capability works in a live run.**
- **With both routes, Luna prefers the first-class tool.** This is the same rule seen with `stress`: a line in a description loses to a tool in the list.
- **Julia-route adoption itself is still unmeasured.** On this workload Luna delegates about once per 40 minutes (tin5), and about 12 times in tin3's 4 hours, so a 30-minute run without delegation says little either way.
- **To measure it:** a longer NeuraJL-only run, or a task that genuinely calls for delegation (for example p3's six independent features). Both are budget-bound.
