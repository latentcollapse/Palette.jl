# Experiment 002 — Unbounded Cognition / Bounded Authority

**Date:** 2026-09-22. Branch: `main` (local commits, not yet pushed -- no push access from this environment; see below). Builds on Experiment 001 (`docs/EXPERIMENT_001_RESULTS.md`, Rev 2, runtime-verified).

## Research question

Can NeuraJL retain an unrestricted, persistent Julia cognitive workspace
while enforcing a real authority boundary below the language?

## Answer

**Yes**, demonstrated with a real, working, adversarially-tested minimal
implementation. The narrowest architecture that did this:

```
model
  |
contained NeuraJL worker (real julia/IJulia process, full language power)
  |  OS-level namespace isolation (bubblewrap) -- the actual boundary
  |  one narrow channel out: a bind-mounted Unix socket
  v
host capability broker (separate process, outside the worker's namespace)
  |  authorize (against a fixed, pre-set ceiling) -> execute -> receipt
  v
real host effects (filesystem outside the workspace, network, nested workers)
```

No in-language blacklist. No "collaborative AST cage." `eval`, `ccall`,
`run`, raw sockets, metaprogramming, and reflection all work, unrestricted,
inside the worker -- and none of them reach outside the sandbox's OS-level
boundary, verified by adversarial testing with independent host-side checks
for every claim (`docs/THREAT_MODEL.md`).

## What was built

| Component | File | Lines | Role |
|---|---|---|---|
| Contained worker launcher | `security/launch_worker.py` | 159 | Builds the bubblewrap sandbox: namespace isolation, bounded filesystem, no ambient credentials, network off by default. Reuses NeuraBash's proven flag set (see `docs/NEURABASH_SECURITY_PORT.md`). |
| Host capability broker | `security/broker.py` | 271 | Runs outside the sandbox. Unix-socket JSON protocol, two fully-implemented capability categories (`external_fs_write`, `network_access`) plus `spawn_child_worker` with real `C_child ⊆ C_caller` enforcement, append-only receipt log. |
| Worker-side client | `src/Neura.jl`, `request_capability()` | +50 net (incl. new `JSON`/`Sockets` deps) | The only code path in the package that can reach a broker-mediated effect. Performs no effect itself. |
| Executable test suite | `security/test_authority.py` | 340 | 19 real tests, no mocks: 5 fast ceiling-subset-logic tests (no sandbox), 8 real-sandbox containment tests, 5 real broker-mediated tests, 1 real nested-worker test. All 19 pass. |

770 lines of new Python (430 implementation + 340 tests), 50 net lines
added to the existing, already-tested `Neura` package. No changes to
Experiment 001's proven behavior -- `Pkg.test()` is still 55/55 after every
change in this pass (reverified, not assumed).

## What's PROVEN, PARTIALLY PROVEN, NOT YET PROVEN

Full detail and exact evidence in `docs/THREAT_MODEL.md`; summary:

**PROVEN** (adversarially tested, independently verified from outside the sandbox):
- The worker has genuinely unrestricted language power inside the sandbox (`eval`, `ccall`, `run`, subprocess spawning all work; `eval`'d code has identical power and identical failure modes to directly-typed code).
- Network access is blocked at the kernel level regardless of mechanism (`run`, raw `Sockets.connect`, subprocess-inherited) -- not a policy, a missing network namespace.
- Filesystem access outside the bounded workspace is blocked -- either the path doesn't exist in the sandbox's view at all (strongest case: sensitive host files), or it's read-only, or a write "succeeds" into the sandbox's own ephemeral, non-persistent storage and is confirmed absent from the real host afterward.
- The broker-mediated path works correctly both ways: an approved request produces a real, verified host-side effect; a denied request produces neither the effect nor any trace of it on the host.
- Bypassing the cooperative client and attempting a denied effect directly still fails, identically -- the broker is not a backdoor that widens the sandbox.
- The worker cannot construct its own, differently-configured sandbox (a real kernel-level rejection: `ENOSPC`, nesting depth exceeded) -- self-expansion of authority is blocked below the application layer, not by convention.
- Nested child workers: a request for a wider ceiling than the parent's is denied before any child is launched; a request for a genuine subset is approved and a real, independent second sandbox is launched (confirmed via the child's own separate PID namespace).

**PARTIALLY PROVEN:**
- `spawn_child_worker` / bounded long-running children: the synchronous, one-shot case is fully proven; an async start-now-poll-later child lifecycle is designed-for but not built.
- `network_access`'s *approved* path (the broker actually performing an outbound request on the worker's behalf) exercises real code but wasn't driven end-to-end from inside a worker this pass -- the denial path, which is what the adversarial claim actually rests on, is fully proven.

**NOT YET PROVEN:**
- External filesystem *read* (only write is implemented).
- Credential access, package-management effects, host service invocation as their own categories (design intent documented in `docs/CAPABILITY_MODEL.md`, no implementation).
- Depot cold-start performance is unsolved, but scoped narrower than first suspected: plain Base-only sandboxed launches are fast (8 real sandbox launches in ~7s, `security/test_authority.py`'s `TestSandboxContainment`); the ~35-40s tax is specific to scripts that `using Neura` (which pulls in `JSON` transitively for `request_capability`). This is a real, open engineering gap, honestly recorded in `docs/NEURABASH_SECURITY_PORT.md`, not a security gap. It does not affect the correctness of any claim above; it does affect whether repeated Neura-loading sandboxed launches are currently practical.
- Multi-level (grandchild) nesting -- the subset-check logic is recursive in principle but was only exercised one level deep.
- Broker socket has no request authentication beyond filesystem reachability -- fine for one worker per broker (the only configuration tested), an open question for anything more.

## Phase B — Experiment 001, reverified before this work started

Per the goal's explicit gate, reverified fresh at the start of this pass,
not assumed from memory: package parses, loads, `Pkg.test()` 55/55, real
Jupyter-wire-protocol proof against a live IJulia kernel still passes
(`x=41` then `x+1==42` over real ZMQ). Static tooling (`julia_analyzer.py`)
was already correctly demoted to preflight-only in the prior pass -- no
changes needed there.

## Phase A — repo graduation

Flattened the package to a conventional Julia layout (`Project.toml`/`src`/
`test` at repo root, matching how real Julia package repos are shaped).
Removed two dead scaffold artifacts (a duplicate `tests/` placeholder, a
`.gitignore` rule that was silently shadowing the real `test/` directory).
Added an explicit naming table distinguishing NeuraJL (product) / `Neura`
(package) / IJulia (real upstream transport, not ours) / NeuraBash
(reference implementation) -- see the root README.

## Operational note

This environment has no SSH access to push to the real GitHub remote (a
recurring, already-known limitation this session -- see the NIRA-Prime
Gate 2 provider report for the same finding on a different repo). All work
in this experiment is committed locally only. Matt will need to pull or add
push access for this to reach the real repo.

## Recommendation

The goal's own stop condition: once a minimal real authority fence is
demonstrated, stop. It's demonstrated. The next experiment, per the goal's
own framing, is **NeuraJL vs. NeuraBash** -- head-to-head, on the actual
operator-surface question (which substrate makes the model more capable)
and eventually the full-system question (which does so without giving away
the house). Before that comparison is meaningful, the two open items most
worth closing first are the depot cold-start cost (makes repeated
experiment runs painfully slow otherwise) and expanding the capability
category coverage enough that a real task-shaped comparison (not just
adversarial probes) can run through the broker for whatever categories that
task actually needs.

No CUDA, no kernel autotuning, no ML features, no additional operator
commands, and no Prime integration were added or attempted in this pass,
per the goal's explicit instruction.
