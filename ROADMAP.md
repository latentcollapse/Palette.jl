# Palette — Specification and Roadmap

**Status:** active. This document is the contract for what Palette is and the
sequence for getting it there. It supersedes the monolithic stack-direction
conversation that previously carried the architecture; where the two disagree,
this wins.

---

## 1. What Palette is

Palette is the **operator surface** — the execution environment an agent works
inside. Cyan is the agent. Colors go on a palette.

An agent harness normally gives its model a shell or a notebook kernel. Every
call starts from nothing, the model re-derives state it already established, and
the Python or Node privilege layer sits between the model and the machine.
Palette replaces that with a **persistent Julia kernel** whose bindings survive
the call, the kernel dying, and context compaction, mediated by an explicit
capability broker.

| Layer | Language | Responsibility |
| --- | --- | --- |
| Chassis | TypeScript | Agent loop, sessions, compaction, providers, RLM, TUI |
| **Palette** | Julia | The model's execution environment: persistent symbolic state |
| Palette host | Rust | Sandbox launch, session supervision, capability broker |
| Broker & launch | Python | Capability negotiation, bwrap isolation, depot prewarm |

### The load-bearing properties

1. **Bindings outlive the call.** A result bound in call *n* is still bound in
   call *n+1*. The model stops re-deriving what it already knows.
2. **State survives kernel death.** A dead kernel revives what it can from saved
   state and reports exactly what was restored, rebuilt, or lost. Loss is never
   silent.
3. **Sub-agents spawn from Julia.** `Neura.rlm.spawn` reaches the chassis's
   existing RLM orchestration through the kernel's broker.
4. **Authority is explicit.** Competence is not authorization. Nothing
   self-grants a capability.
5. **The model's surface gets simpler as the substrate gets richer.** Five
   awkward operations should collapse into one operator, not five.

### Naming

| Name | Scope |
| --- | --- |
| `Cyan` | The agent and harness |
| `Palette` | The operator surface (product name) |
| `Neura` | The Julia package that implements it |
| `palette-host` | The Rust crate: sandbox, session, broker |
| `IJulia` | Kernel transport — **not ours**, third party |
| `NeuraBash` | Reference implementation, retained for comparison |

A repository was merged on 2026-09-29 (`2ae03ea1c`). The operator surface was
previously developed as a separate lab (`neurajl-operator-lab`, 83 commits) and
implanted into the chassis through the `np2` patch chain. Both histories are
preserved; the consolidation repaired a driver import that only resolved while
the two sat side by side.

---

## 2. Architecture

```
model  ──▶  palette (tool)         packages/coding-agent/src/core/tools/palette.ts
                │
                │  host_request over a unix socket
                ▼
           broker                  security/broker.py
                │  grants within the session ceiling
                ▼
           session_cli             security/session_cli.py
                │
                ▼
        ┌───────────────────────┐
        │  Neura (Julia kernel) │   src/
        │  bindings, revival,   │
        │  RLM, workspace map   │
        └───────────────────────┘
                │
           bwrap sandbox
```

The ceiling is the key control. A session declares which host request types it
may use; the broker grants nothing beyond it. `PALETTE_RLM_REQUEST_TYPES` is
the default deny-by-default list — if a request type is not named, the kernel
cannot reach the host at all.

---

## 3. Verification status

Measured 2026-09-29, from the consolidated repository.

| Gate | Result |
| --- | --- |
| Chassis unit tests (`vitest`, 3 suites) | **47/47 pass** |
| Live kernel integration (13 tests) | **12/13 pass**, 1 load-induced timeout |
| Julia package suite | **41/41 pass** |
| Pre-commit gate | **all green** — biome, test-policy, installer, push-guard (31 cases), browser-smoke |

### Known issue: host timeouts under load

`rlm.delete_subagent` failed with `the agent host did not answer within 55s`
when three suites ran concurrently. Isolated re-runs did not reproduce a
functional failure. **Treat the 55s host deadline as a fragile constant** — it
is a wall-clock timeout on a loaded machine, and the RLM path fans out to
sub-processes, so it is the most likely thing to flake in CI.

**Action:** instrument the deadline before raising it. If the host is simply slow
rather than stuck, the fix is a progress-aware deadline, not a longer timeout.

---

## 4. Roadmap

Ordered. Each stage names its exit condition, because a stage without one is a
wish.

### Stage 1 — Close the rename *(in progress)*

The rename is complete in live code. Remaining:

- `docs/` — 74 experiment records still carry the old name.
- `np2/patches/` — 55 patches across two series still carry it.
- The GitHub repo `latentcollapse/neurajl-operator-lab` is referenced in the
  README and should be renamed to match, or the link should point at `Cyan`.

**Exit:** zero occurrences of the old name outside the historical charter.

> **Do not blind-sed the patch chain.** Patch `0014` creates
> `tools/neurajl.ts`; later patches modify it by path. Renaming inside the
> series without renaming the diff headers consistently will break `git am`. The
> chain must be rewritten as a unit and re-verified by applying it to a clean
> upstream checkout.

### Stage 2 — SDK packaging

Palette is a turnkey harness, so it ships as an installable product.

- [ ] One-command install (`./install.sh` or a bootstrap) that provisions
      Node 22.8+, Julia 1.12, and `bwrap`, and verifies each.
- [ ] A single `palette doctor` command that reports the state of every
      prerequisite and every kernel path, and fails loudly rather than silently
      degrading.
- [ ] Configuration resolution: today every consumer exports `PALETTE_*` by
      hand. Provide a single discovery mechanism.
- [ ] Version identity. The nano-lock direction wants artifacts to declare
      `Cyan <version>`, `profile SHA-...`, `battery SHA-...`. That requires
      content-derived identity that does **not** move when a name moves — the
      D22 lesson.
- [ ] Semantic versioning across the rename boundary, with the breaking changes
      (tool name, state type, env vars) called out in a migration note.

**Exit:** a clean machine can go from clone to running kernel in one command,
and `palette doctor` is green.

### Stage 3 — Surface simplification

The property that matters is that the model's conceptual surface gets *simpler*
as the substrate gets richer. Current friction, from the probe signals:

- Project state is re-derived rather than retained across sessions.
- Cross-module dependency reasoning is manual.
- Long-horizon planning has no durable representation.

**Action:** for each, ask the governing question — *can this decision be removed
from the model entirely?* A symbolic persistent handle beats a re-read; one
operator beats five equivalent pathways.

**Exit:** each of the three has either become a substrate primitive or has a
recorded decision explaining why it cannot.

### Stage 4 — Measured capability transfer

The thesis is that a smaller model inherits capability once reasoning moves into
the substrate. That is an empirical claim and needs an experiment, not an
assertion.

- [ ] Battery ladder: cheap API class, strong API class, local dense, local MoE.
- [ ] Conditions: model-only, model+generic harness, model+Cyan, model+Palette.
- [ ] Fixed: same task set, budget, reasoning effort, quantization, modalities.
- [ ] Measure quality, success rate, cost, tokens, retries, wall-clock.

**Exit:** a measured amplification curve, with the confidence interval stated.

> Note on statistical power: the current measured levers are n=6 and n=4, and
> one of them (0/4 → 4/4) is a **floor effect** — it cannot improve further.
> Finding a third lever with real headroom matters more than extending either
> existing one.

### Stage 5 — Recursive hardening

Friction discovered in one generation becomes substrate machinery that changes
what the next generation has to reason about. The signal is not "is this
version better" but **how the shape of complaints changes**.

- [ ] Friction taxonomy fixed *before* the first long run, so data across runs
      shares a vocabulary.
- [ ] A read-only observer whose remit is evidence, not repair. It may not
      influence the worker, suggest architecture, or editorialize.
- [ ] Isolated worktrees per change; never patch the live branch.
- [ ] Promotion thresholds declared in advance.

**Exit:** a generation lineage where friction demonstrably migrates rather than
repeats.

---

## 5. Invariants

These are not preferences. Violating one is a bug.

1. **No fake verification.** Never report a passing run that did not happen.
2. **Tests drive real entry points.** A test that stubs the thing it claims to
   test is not a test.
3. **Unbounded power, extremely bounded authority.** `exec(...)` stays distinct
   from `bash(...)`.
4. **Loss is never silent.** If state cannot be revived, say so explicitly.
5. **Small reversible commits.**
6. **Canonical machinery stays boring.** Adaptation lands in profiles, never in
   the canonical configuration.

---

## 6. Open questions

| # | Question |
| --- | --- |
| 1 | Should `Agents.jl` — the standing definitions of stances and sub-harnesses — be a Julia package, a data file, or both? |
| 2 | What is the canonical friction taxonomy, and who owns it? |
| 3 | Should the np2 patch chain be kept byte-exact as provenance, or rewritten to reproduce the current tree? Both have costs. |
| 4 | How does profile identity get hashed so it survives a rename? |
| 5 | What is the promotion policy for substrate changes made by the hardening loop? |
| 6 | Platform kits: the current commitment is no external engine runtime, ever. Does that hold for consoles and XR, or do those get a platform-native bridge? |
