# IJulia Operator Surface — Experiment 001 Lab

**Status:** Lab scaffold only. Experiment 001 is **not** implemented here yet.

This repository is a clean workspace for Qwen (or any implementer) to complete
**Experiment 001**. It is deliberately **outside** Project Neura, NeuraBash,
Prime Agent, and EnigmaOS.

---

## How to start

```bash
git clone git@github.com:latentcollapse/ijulia-operator-lab.git
cd ijulia-operator-lab
# Read AGENTS.md, then this README in full.
# Implement Experiment 001 in-tree; do not integrate with Neura/Prime/NeuraBash.
```

Host environment at scaffold time: Julia was available (`julia --version` —
see `VERSIONS.lock`). You may need `IJulia` / Jupyter client packages; install
them inside this project’s Julia environment as you implement Phase 1.

Suggested layout to grow into (already stubbed):

| Path | Intent |
|------|--------|
| `OperatorSurface.jl/` | Julia package for types, ops, discovery, receipts |
| `src/` | Thin entry / clients if needed |
| `tests/` | Persistence, ops, discovery, receipts, failures |
| `demo/` | One-command integration demo (Phase 10) |
| `docs/` | Audit + results (you write these) |
| `scripts/` | Helpers to start kernel / run demo |

## Substrate clarification (read this)

**Phase 1’s “kernel” means an IJulia / Jupyter kernel** — a persistent Julia REPL
process driven over the Jupyter messaging protocol (execute requests, results,
state that survives across requests).

It does **not** mean GPU/CPU *compute* kernels or the separate private R&D track
documented as *Native Julia Kernel Autotuning* (`KernelAbstractions.jl`, CUDA backends,
autotuning control planes, `KernelTuner.jl` companions). That work is out of scope
for Experiment 001 and must not be pulled in as a dependency or Phase 1 substrate.

If a document says “kernel” without qualification in this lab, assume **IJulia**.

## Security warning (read this too)

A persistent Julia kernel with `find` / `grep` / `exec` / `bash` / `kill` is a
**high-power surface**. It can read the filesystem, launch processes, and keep
mutable state across turns. That is the point of the experiment. It is also why
you must not treat a successful Experiment 001 demo as a finished product.

**Experiment 001 does not implement privilege or security enforcement** (see
NON-GOALS). That is intentional: prove the operator surface first.

Do **not** forget the authority problem just because it is out of scope here:

- Open-ended cognition and closed-ended authority are separate layers.
- Model competence is not authorization. Structured ops and receipts are not a fence.
- Ambient Julia (`eval`, `ccall`, `run`, `Pkg`, `include`, raw `bash`) is a
  capability grant until something explicit says otherwise.
- NeuraBash already did the hard R&D on this thesis (closed effect vocabulary,
  `C_child ⊆ C_caller`, fail-closed launch, sealed profiles). Porting that
  *doctrine* to an IJulia operator surface is future work — likely a later
  experiment — and it will need a real attachment point (contained workers
  and/or authorize-before-effect), not vibes.

In `docs/EXPERIMENT_001_RESULTS.md`, call out ambient authority and what a
follow-on fence would have to wrap. Do not ship the narrative that “typed ops
made it safe.”

If you give something this much power and skip that note, you are the idiot
the title of this section is for.

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
