# NeuraJL Operator Surface

**Status:** Experiment 001 is implemented and runtime-verified (Rev 2) -- see
`docs/EXPERIMENT_001_RESULTS.md` for what's actually proven, including a real
Jupyter-wire-protocol run against a live IJulia kernel. Experiment 002
(authority/security) is tracked in `docs/EXPERIMENT_002_AUTHORITY.md`. The
assignment-brief sections below are kept for history, not as current status.

## Naming (read this first, it's been a source of confusion once already)

| Name | What it is |
|---|---|
| **NeuraJL** | The product/runtime name. What you'd call the whole thing. |
| **`Neura`** (package `Neura`, repo root as its package root) | The Julia package implementing the operator surface -- types, ops, discovery, receipts. This repo. |
| **IJulia** | NOT ours. A real, independent, decades-old package maintained by the Julia language team (`JuliaLang/IJulia.jl`). It is the current *transport* NeuraJL runs on -- a persistent Julia REPL process driven over the Jupyter wire protocol. NeuraJL is built **on** IJulia, the same way Prime Agent's Python tooling runs **on** IPython/`ipykernel` without having invented either. Do not name anything in this project "IJulia" -- besides being confusing, Julia's package registry will not allow a second package with that name. |
| **NeuraBash** | The reference/legacy operator implementation -- the original Bash-hosted `\|!>` JUL trapdoor this project's security doctrine (unbounded power, extremely bounded authority) was first proven on. NeuraJL is the same thesis on a different, more capable substrate (a real persistent language runtime instead of Bash), not a replacement built from a blank page. |

This repository was originally scaffolded as an isolated Experiment 001 lab,
deliberately outside Project Neura, NeuraBash, Prime Agent, and EnigmaOS, for
an implementer (Qwen) to complete without cross-contamination. That isolation
served its purpose; the code is now real and graduating toward product use.

## Layout

Conventional Julia package layout -- repo root is the package root:

| Path | Intent |
|------|--------|
| `Project.toml`, `src/`, `test/` | The `Neura` package itself |
| `demo/` | Empty by design -- see `demo/README.md` for where the real demos live |
| `docs/` | Experiment reports (results, authority model, threat model, capability model) |
| `scripts/` | The real IJulia integration proof, plus a retired pointer stub |
| `security/` | Sandbox launcher, capability broker, persistent session and its stdio bridge |

Before the first session on a depot, and again after Neura or the session
project changes, run `python3 security/prewarm_depot.py --project-dir <project>`.
Without it every session recompiles stdlibs on first use (`using Pkg` ~80s).
Run it with the same mounts sessions will have: a harness that puts the Julia
runtime or this repo at another path must prewarm there, or every kernel
start recompiles (~45s).

A worker's processes cannot outlive it: julia is PID 1 of its own PID
namespace, so when it exits (a finished or killed EPHEMERAL child, a closed
session) the kernel kills every descendant, however detached. Output and
files those descendants held go with the child's discarded workspace.

## Substrate clarification (read this)

**Phase 1’s “kernel” means an IJulia / Jupyter kernel** — a persistent Julia REPL
process driven over the Jupyter messaging protocol (execute requests, results,
state that survives across requests).

It does **not** mean GPU/CPU *compute* kernels or the separate private R&D track
documented as *Native Julia Kernel Autotuning* (`KernelAbstractions.jl`, CUDA backends,
autotuning control planes, `KernelTuner.jl` companions). That work is out of scope
for Experiment 001 and must not be pulled in as a dependency or Phase 1 substrate.

If a document says “kernel” without qualification in this lab, assume **IJulia**.

## Authority philosophy (same as NeuraBash)

**Unbounded power. Extremely bounded authority.**

Same thesis as NeuraBash:

- open-ended cognition  
- closed-ended authority  
- competence ≠ authorization  
- model-created machinery may increase capability; it must not increase rights  
- `C_child ⊆ C_caller` when principals or effect scopes nest  

A persistent Julia operator surface is meant to be *powerful* — invent, compose,
retain, discover, verify. That power is the point. Authority is the separate
layer: what effects may actually run, under whose grant, inside which envelope.

**Experiment 001 does not implement privilege/security enforcement** (see
NON-GOALS). That is intentional: prove the operator surface and typed ops first.
It is **not** permission to ship the story that “structured Julia made it safe.”

Do not forget the authority half just because this experiment stops at the
surface:

- Ambient Julia (`eval`, `ccall`, `run`, `Pkg`, `include`, raw `bash`) is
  ambient *power*. Until a fence exists, it is also ambient *authority* — and
  that mismatch is a known incomplete state, not the endgame.
- Structured ops and receipts are cognitive/audit machinery. They are not a
  capability grant and not a substitute for one.
- NeuraBash already did the hard R&D on closed effect vocabularies, fail-closed
  launch, sealed profiles, and child-subset rules. Porting that *doctrine* onto
  an IJulia surface is future work (attachment via contained workers and/or
  authorize-before-effect). Do not reinvent a weaker collaborative AST cage.

In `docs/EXPERIMENT_001_RESULTS.md`, state explicitly: Experiment 001
demonstrates unbounded operator power; authority bounding is deferred and must
not be papered over. If you build this much power and shrug at authority, you
are the idiot this section is for.

---

# EXPERIMENT 001 — Assignment (implement this)

Read every architecture and instruction document in this repository before
changing code.

You are implementing **EXPERIMENT 001**:

> **Can a persistent Julia/IJulia kernel function as a structured AI-agent operator surface?**

This is an experimental implementation.

**Do not integrate it into Project Neura.**

---

## PRIMARY GOAL

By the end of this run, demonstrate a persistent Julia kernel in which an
external client can:

1. start/connect to the kernel  
2. execute Julia code  
3. preserve state across multiple requests  
4. invoke structured operator functions  
5. receive structured results  
6. inspect available operations  
7. execute a legacy shell escape explicitly  
8. interrupt/fail safely  
9. produce receipts for meaningful operations  

The result must be tested.

---

## PHASE 1 — PERSISTENT KERNEL

Establish a headless IJulia/Jupyter execution path.

Prove:

**Request 1:**

```julia
x = 41
```

**Request 2:**

```julia
x + 1
```

**Result:** `42` without restarting Julia.

Also prove persistence for:

- function definition  
- loaded package/module  
- mutable object/state  

Document the actual Jupyter messages required.

Do not scrape terminal output if structured kernel messages are available.

---

## PHASE 2 — OPERATOR TYPES

Implement small, explicit result types.

Possible examples:

- `FileRef`  
- `Match`  
- `ProcessInfo`  
- `CommandResult`  
- `OperationReceipt`  
- `OperationError`  

Names may change if a better design emerges.

Avoid giant generic dictionary blobs.

---

## PHASE 3 — JULIA-NATIVE VOCABULARY AUDIT

Before writing wrappers, inspect the Julia standard environment.

For every candidate Bash-like operation, determine whether Julia already
provides the behavior idiomatically.

Do not wrap Base functions merely to increase LOC.

Record findings in:

```text
docs/BASH_VOCABULARY_AUDIT.md
```

---

## PHASE 4 — FIRST STRUCTURED OPERATIONS

Implement a useful but bounded initial surface.

Target roughly:

**Filesystem / discovery**

- `find(...)`  
- `grep(...)`  
- `head(...)`  
- `tail(...)`  
- `which(...)`  

**Process**

- `ps(...)`  
- `kill(...)`  

**System information**

- `env(...)`  
- `du(...)`  
- `df(...)`  

**Execution**

- `exec(...)`  
- `bash(...)`  

Use existing Julia functions where appropriate.

Important:

- `exec(...)` is structured execution  
- `bash(...)` is explicit legacy escape  

They are **not** synonyms.

---

## PHASE 5 — STRUCTURED SEMANTICS

Example target behavior:

```julia
matches = grep("TODO", find(".", extension=".jl"))
```

The model should receive structured `Match` values, not have to parse grep
stdout.

Likewise:

```julia
processes = ps()
```

should return `ProcessInfo` objects.

Design for composition.

---

## PHASE 6 — DISCOVERY

Implement an introspection surface such as:

```julia
operations()
describe(:grep)
describe(:find)
capabilities()
```

A caller must be able to discover:

- operation name  
- purpose  
- arguments  
- return type  
- whether it mutates state  
- whether it launches a process  
- examples  

Do not build a giant natural-language documentation engine.

Structured metadata first.

---

## PHASE 7 — RECEIPTS

At minimum, operations which mutate files or launch processes should be
capable of returning or recording:

- operation ID  
- operation name  
- arguments  
- start/end time  
- success/failure  
- exit code if applicable  
- files affected where known  
- stderr/stdout references where appropriate  
- error information  

Keep the receipt schema boring and serializable.

---

## PHASE 8 — RAW SHELL ESCAPE

Provide one explicit legacy escape.

Conceptually:

```julia
bash(`git status --short`)
```

or the cleanest idiomatic Julia equivalent.

It must be obvious when the model has left structured operator semantics and
entered raw shell compatibility mode.

Capture:

- stdout  
- stderr  
- exit code  

Do not attempt to parse arbitrary output automatically.

---

## PHASE 9 — FAILURE BEHAVIOR

Test:

- command not found  
- nonexistent file  
- permission error where safely reproducible  
- killed subprocess  
- Julia exception  
- malformed operation arguments  
- kernel interruption  

A failed operation must not corrupt the entire persistent session whenever
reasonable.

---

## PHASE 10 — INTEGRATION DEMO

Build an automated demo equivalent to:

1. start Julia kernel  
2. create persistent variable  
3. inspect working directory  
4. find Julia files  
5. grep them for a term  
6. launch a harmless subprocess  
7. inspect its result  
8. call raw shell escape once  
9. inspect operation metadata  
10. retrieve receipts  
11. prove original Julia state still exists  

One command should run this demonstration.

---

## TEST REQUIREMENTS

Write tests for:

- persistent state  
- structured filesystem results  
- structured process results  
- discovery metadata  
- receipt serialization  
- raw shell capture  
- failure containment  

Do not claim functionality that could not be executed in your environment.

---

## NON-GOALS

Do **not** implement:

- NeuraBash integration  
- Prime-Agent integration  
- Project Neura integration  
- kernel generator  
- CUDA  
- Lava  
- Mojo  
- ML inference  
- custom scheduler  
- privilege/security enforcement  
- full POSIX compatibility  
- custom notebook frontend  
- custom Jupyter protocol  

---

## SUCCESS CRITERIA

**STRONG SUCCESS** means:

An external process can drive a persistent Julia kernel as an operator
environment, perform useful Linux/software-engineering work through a small
typed operation library, retain Julia state throughout the session, inspect
the operator surface programmatically, and fall back to raw shell execution
only when necessary.

The repo must finish in a state suitable for architectural review.

---

## WHEN FINISHED

Produce:

```text
docs/EXPERIMENT_001_RESULTS.md
```

containing:

- what works  
- exact architecture implemented  
- tests and commands run  
- failures  
- limitations  
- missing Linux semantics  
- operations that proved redundant because Julia already handled them  
- operations that genuinely benefited from structured wrappers  
- rough comparison against an IPython-style operator surface  
- recommendations for Experiment 002  

**Do NOT begin Experiment 002.**

Stop and wait for review.
