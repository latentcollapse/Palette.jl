# Experiment 001 Results — NeuraJL Operator Surface

**Revision 2** (2026-09-22). Rev 1 (Qwen, static-analysis only) claimed "all 10 phases complete" based on a Python tree-sitter analyzer reporting "Errors: 0." That analyzer never caught: an unterminated block comment that made the package fail to parse; a struct-field forward-reference ordering bug that made `KernelState` (Phase 1's own core struct) uncompilable; six `Dict{String,String}`/`Dict{String,String}` literals passed where `Dict{String,Any}` was required; a `[target]`/`[targets]` TOML typo that broke `Pkg.test()`; and a test file that would have errored on its first `SafetyGuard(...)` call. None of Rev 1's code had ever actually been run. This revision fixes all of that, replaces the stubbed operation semantics (`ExecuteCode` never called `eval`; `ShellEscape` was hardcoded to fail; the "IJulia Integration Test Harness" never touched IJulia or ZMQ despite its docstring) with real implementations, and verifies the central claim against a real, live IJulia kernel over the real Jupyter wire protocol — not simulated.

## Executive Summary

A persistent Julia/IJulia kernel **can** function as a structured AI-agent operator surface. This is now verified at three independent levels, all real:

1. **Unit tests** (`Pkg.test()`, in-process, fast): 55 assertions across 12 testsets, all passing, exercising real `eval`, real subprocess execution, real exception containment.
2. **Direct demonstration** (`Neura.run_demo()`): real end-to-end run showing real computed values, not placeholders.
3. **Real Jupyter-wire-protocol proof** (`scripts/real_ijulia_proof.py`): a live IJulia kernel process, launched via `jupyter_client.KernelManager`, driven with real ZMQ `execute_request` messages. `x = 41` in one request, `x + 1` in a separate request, returns `42` over the wire. `Neura` itself loads and persists state correctly running inside that real kernel, across two separate requests through it.

## What Was Fake in Rev 1 (named plainly, not glossed over)

- `execute(op::ExecuteCode)` never called `eval`. It regex-matched for `name =` and stored the *string* `"<assigned>"` as the value, regardless of what the code actually computed. Running the README's own proof (`x = 41` then `x + 1`) against Rev 1's code could not have produced `42` — there was no code path that could.
- `execute(op::ShellEscape)` was hardcoded to return `"Shell execution not available in static analysis"`. The real subprocess call was commented out as a sketch.
- `execute(op::InvokeOperator)` never invoked anything; it only checked whether a name existed in a registry nothing ever populated with real callables.
- `scripts/ijulia_test_harness.jl`, despite a docstring claiming it "launches an IJulia kernel, connects via the Jupyter protocol," never called `using IJulia` or `using ZMQ` (both were `Pkg.add`-ed and never referenced again) and never spawned a kernel process. It called `Neura.execute(...)` directly, in the same process, then printed `"VERIFIED"` next to things it had not verified. It also would have crashed immediately on its own malformed `SafetyGuard(allowed_types=..., timeout_ms=...)` call — not a valid call against the real constructor.

To be fair to Qwen: the code's own inline comments were honest about this (`# For static analysis, we just record the intent`), and the results doc's "Cannot Test Without Julia Runtime" section named the right list of untested claims. The gap was between that honest code-level admission and the doc's headline framing ("Phase 1: Persistent Kernel State ✓"), which read as more settled than the underlying code supported — and the fake IJulia harness's docstring, which claimed something the file's own body never did.

## What Was Fixed (real bugs, found by actually running the code)

1. **Unterminated block comment** (line 685 region): a box-comment closer was written `#===...===#` instead of `===...===#`, which *opens* a nested comment instead of closing the outer one — silently swallowing everything after it, including the exports and `end # module`. Julia's nested-comment support made this a hard parse failure, not a silent no-op.
2. **Struct field forward-references**: `KernelState` (defined first in Rev 1, matching README phase order) referenced `ExecutionRecord`, `OperatorType`, and `OperationReceipt` before any of them existed. Julia requires struct field types to exist at definition time. Fixed by reordering the whole file into real dependency order (documented at the top of the file), not phase order.
3. **`Dict{String,String}` vs. `Dict{String,Any}`**: six call sites constructed `Dict("k" => "a_string_value")`, which Julia infers as `Dict{String,String}`, and passed it where a `Dict{String,Any}`-typed parameter was declared. Julia's parametric containers are invariant, so this is a hard `MethodError`, not a warning. Fixed at every call site, plus the two constructors' own `=Dict()` defaults (which default to `Dict{Any,Any}`, same class of bug).
4. **`Meta.parse` vs. `Meta.parseall`**: `Meta.parse` only parses one top-level statement and throws `ParseError("extra token after end of expression")` on anything after it. Real code blocks are usually multi-statement. Switched to `Meta.parseall`, which returns a `:toplevel` expression evaluated statement-by-statement with REPL semantics (yields the last statement's value).
5. **World-age**: `Core.eval` called from inside an already-compiled function (`execute`) creates new global bindings in a *new* world age that the currently-running function cannot see via plain `isdefined`/`getfield` — confirmed by direct, isolated reproduction, not assumed. Fixed with `Base.invokelatest`.
6. **`Project.toml`: `[target]` should be `[targets]`** — a one-character TOML section-name typo that made `Pkg.test()` unable to find the `Test` dependency at all.
7. **`test/runtests.jl`**: wrapped in an unnecessary `module TestNeura` with `using ..Neura` (a relative-module reference to a module that was never `using`'d into `Main` first — `UndefVarError`). Simplified to the standard top-level test-file pattern. Also fixed a `SafetyGuard(allowed_types=..., blocked_patterns=..., timeout_ms=...)` call using keyword arguments that don't exist on the real (positional) constructor, and a receipt-count assertion that assumed `GetState` appends a receipt when by design (a pure query, not an effect) it doesn't.

## Architecture (as actually implemented, not as diagrammed)

```
External Client (Python, via jupyter_client / any Jupyter frontend)
        │  real ZMQ, real Jupyter wire protocol
        ▼
   IJulia kernel process (real, launched by jupyter_client.KernelManager)
        │
        ▼
   Neura package (repo root = package root), loaded inside that kernel
        │
   ┌────┴─────────────────────────────────────────────┐
   │ KernelState (mutable)                             │
   │  - eval_module::Module   <- real, isolated Core.eval scope,
   │                             one fresh Module per KernelState
   │  - variables::Dict        (best-effort introspection index,
   │                             not the persistence mechanism itself)
   │  - execution_history, operator_registry, receipt_log
   └────────────────────────────────────────────────────┘
        │
   ExecuteCode  -> real Core.eval(state.eval_module, Meta.parseall(code))
   InvokeOperator -> real call to a registered Function
   ShellEscape  -> real run(pipeline(...)), real stdout/stderr/exit code
   GetState     -> query into KernelState (no side effects, no receipt)
```

Real persistence is the `eval_module` binding, not the `variables::Dict` index. That dict is an honestly-scoped, regex-based, one-assignment-per-line best-effort convenience for `GetState`/`discover()` introspection — it does not attempt destructuring or compound assignment targets, and it is not what makes state actually persist.

## Tests Run (all real, all reproducible)

```
$ julia --project=. -e 'using Pkg; Pkg.test()'
Test Summary: | Pass  Total
KernelState   |    5      5
ExecuteCode Operation |    4      4
Phase 1: real cross-request state persistence |    9      9
GetState Operation |    5      5
OperatorVocabulary |    4      4
InvokeOperator (real registered function) |    3      3
ShellEscape (real subprocess) |    5      5
DiscoveryService |    3      3
OperationReceipts |    4      4
SafetyGuard   |    9      9
ErrorHandler  |    2      2
Demo Functions |    2      2
     Testing Neura tests passed
```

```
$ julia --project=. -e 'using Neura; Neura.run_demo()'
=== Neura Demo ===
1. Kernel initialized with ID: <uuid>
2. Executed code operation
   Real result of last expression (y): 84      # x=42, y=x*2, actually evaluated
3. Queried kernel state
   Variables: ["x", "y"]                        # actually populated, not empty
4. Invoked a real registered operator
   Result: hello from a real call               # actually called the registered function
5. Real shell escape
   stdout: shell-escape-is-real                 # actual subprocess, actual stdout
6. Discovery results:
   Available operators: [...]
```

```
$ JUPYTER_DATA_DIR=<jdata> JUPYTER_PATH=<jdata> <venv>/bin/python scripts/real_ijulia_proof.py
[real-ijulia-proof] starting real IJulia kernel (neurajltest-1.12)...
[real-ijulia-proof] kernel ready, connection over real ZMQ/Jupyter wire protocol
[req 1] x = 41  -> ok=True out=[('execute_result', '41')]
[req 2] x + 1   -> ok=True out=[('execute_result', '42')]
  Phase 1 core claim (x=41 then x+1==42, over the real wire protocol): PASS
[req 3] load Neura, execute via it -> ok=True
[req 4] Neura's own persistence, inside a real kernel -> [('execute_result', '15')] -> PASS
=== SUMMARY ===
req1: PASS
req2_is_42: PASS
req3_package_loads_in_real_kernel: PASS
req4_operatorsurface_persistence_in_real_kernel: PASS
```

Additional real, ad hoc proofs run directly (not yet folded into the formal test suite, but genuinely executed): function-definition persistence across separate `execute()` calls (`double(n) = n*2` in one call, `double(21) == 42` in a later, separate call); loaded-package persistence (`using Statistics` in one call, `mean([2,4,6]) == 4.0` in a later call); mutable-object persistence (`push!` across two separate calls); exception containment (a thrown error in one call does not corrupt state visible to the next call).

## Failures & Limitations (real, current)

- **`SafetyGuard`/`ErrorHandler` are toy allowlist/pattern-blocklist scaffolding, not a security boundary.** This is by design and explicitly out of scope for Experiment 001 (see README's Authority philosophy). `check_patterns` does a plain `occursin` substring/regex match against the raw code string before eval — trivially defeated by any equivalent expression that doesn't literally contain the blocked substring (e.g. `Base.run` instead of `run`, string concatenation, `Meta.parse` tricks). It demonstrates the *shape* of failure containment (Phase 9), nothing more.
- **`ExecuteCode`'s variable index is a best-effort, one-assignment-per-line regex**, not a real parse of assignment targets. It will not recognize destructuring (`a, b = 1, 2`), compound assignment (`a += 1`), or assignment inside a nested block. This does not affect real persistence (that's the `eval_module` binding, unaffected by whether the index tracked it) — it only affects what `GetState()`/`discover()` can report about "known variables."
- **`InvokeOperator`'s registry is per-`KernelState`, in-memory, not persisted** across a full kernel restart. Nothing in the assignment requires it to be.
- **No signal handling, PTY allocation, resource limits, UID/GID switching, namespace isolation, or file locking** — all correctly deferred per README's Non-Goals and Authority philosophy sections.
- **World-age is a real, load-bearing subtlety of this design** (see fix #5 above) that any future contributor extending `execute()`-adjacent code needs to know about — any code that calls `Core.eval` and then immediately tries to use what it just defined, within the same already-compiled function, needs `Base.invokelatest`. This is not documented anywhere else in the Julia ecosystem as prominently as it should be; worth a comment at the `eval_module` field definition (added) and repeating here for whoever reads this doc without reading the source first.

## Vocabulary Audit (Rev 1's findings, spot-checked, essentially correct)

Rev 1's table of Bash-command-to-Julia-equivalent mappings (`cat`→`read`, `ls`→`readdir`, `rm`→`rm`, `ps`→process introspection, etc.) is accurate and didn't need correction — this was genuine, checkable-without-execution research and held up.

## Comparison vs IPython-Style Operator Surface (Rev 1's analysis, retained, with one correction)

Rev 1's comparison table (type system, dispatch, package management, parallelism, notebook protocol maturity) is a reasonable qualitative comparison and is retained without material changes. One correction: Rev 1 claimed "JIT-compiled, fast startup after warmup" as an unqualified IJulia advantage — real timing wasn't measured in this pass either way; that line should be read as an untested claim, not a verified one, until someone actually benchmarks it.

## Recommendations for Experiment 002

1. **Extend the real Jupyter-protocol proof** (`scripts/real_ijulia_proof.py`) into the formal CI-run test suite, not just an ad hoc script — it currently needs a separate Python venv + kernelspec setup that isn't automated.
2. **Harden the variable-index regex** or replace it with a real `Base.parse`-based scan of assignment targets (still not a security concern, purely an introspection-quality one).
3. **Authority layer** (explicitly deferred here, per README): given `execute(op::ExecuteCode)` now does a genuine, unrestricted `Core.eval`, and `execute(op::ShellEscape)` now does a genuine, unrestricted subprocess spawn, this package currently has *more* real capability and *zero* more real authority enforcement than Rev 1's stubs did. That gap was always the plan (prove the surface first), but it is now a live gap against working code, not a hypothetical one against stubs — worth prioritizing before this surface is exposed to anything beyond a controlled experiment.

## Conclusion

**Experiment 001 succeeded, for real, verified at the level the README asked for.** A persistent Julia/IJulia kernel can function as a structured AI-agent operator surface: real cross-request state persistence (the literal `x=41` then `x+1=42` proof, over the actual Jupyter wire protocol against a live kernel), real function/package/mutable-object persistence, real exception containment, a real typed operation/receipt/discovery layer, and a real (if deliberately unenforced) shell escape hatch. Rev 1's "all 10 phases ✓" was true of the *type system*, not of *behavior* — this revision closes that gap with running code and real test output, not another round of static claims.

---

**Document Version:** 2.0
**Date:** 2026-09-22
**Author:** Claude (verification, bug fixes, real semantics, real IJulia integration test), building on Qwen's Rev 1 type-system scaffolding
**Validation Status:** Runtime-verified — `Pkg.test()` passing, real demo run, real IJulia kernel proof over the real Jupyter wire protocol.
