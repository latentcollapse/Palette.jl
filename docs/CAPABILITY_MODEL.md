# NeuraJL Capability Model — Experiment 002

Companion to `docs/THREAT_MODEL.md` and `docs/EXPERIMENT_002_AUTHORITY.md`.

## Core rule

**The model may REQUEST capabilities. The worker may not GRANT capabilities.**
Only the host capability broker (`security/broker.py`), running outside the
worker's OS namespace, decides. Competence is not authorization: nothing
about how well the worker can compute a request, or how legitimate the
request sounds, changes whether the broker approves it. The broker checks
one thing only -- does this request fall within this session's fixed
capability ceiling, set before the worker ever started, never mutated by a
request.

**C_child ⊆ C_caller.** When a worker requests a nested child worker, the
child's requested ceiling must be a subset of the parent's actual ceiling.
Enforced in `security/broker.py`'s `ceiling_is_subset()`, tested directly
(unit-level: 5 cases, all correct) and end to end (a real nested sandbox
launch, approved and denied cases both -- see `THREAT_MODEL.md` rows 17-18).
Unrecognized categories fail closed (denied, not silently ignored, not
silently granted).

## Effect classification

| Class | Meaning | Enforcement | Example |
|---|---|---|---|
| **A -- pure/cognitive** | Ordinary Julia computation. No host effect, no filesystem/network reach. | None -- runs at full speed, no broker round-trip. Routing this through an authorization bureaucracy would defeat the entire point (high autonomy, narrow authority, not high friction everywhere). | Arithmetic, in-memory data structures, algorithms, `eval`-based metaprogramming that stays in-process. |
| **B -- sandbox-local** | Touches the filesystem or spawns processes, but stays entirely within the sandbox's own bounded envelope. | The OS sandbox itself (bind mounts, namespace isolation) -- no broker call needed, because the boundary is already enforced below the language. | Reading/writing inside the bound workspace; spawning a subprocess that inherits the same namespace restrictions (verified: it does -- `THREAT_MODEL.md` row 11). |
| **C -- broker-mediated host effect** | Crosses the sandbox boundary: reaches the real host filesystem outside the workspace, the real network, or anything requiring host privilege. | `authorize before effect -> execute -> receipt after effect`, via `security/broker.py`. The worker never performs the effect itself -- it has no code path to. | External filesystem write, network access, spawning a child worker. |

## Capability categories

Per the goal's "at minimum investigate" list. Status is honest, not
aspirational -- PROVEN means adversarially tested end to end with
independent host-side verification (see `THREAT_MODEL.md`); PARTIALLY
PROVEN means the enforcement logic exists and was tested in isolation but
not the full integration path; NOT YET PROVEN means designed/intended here
but not implemented this pass.

| Category | Effect class | Status | Notes |
|---|---|---|---|
| **Project read** | B | PROVEN (implicit) | The repo source and dev project are bound read-only into every worker; reading them is unrestricted, writing them is blocked (`THREAT_MODEL.md` row 7 pattern, same mechanism). |
| **Project write** | B | PROVEN | The bounded workspace directory is read-write; verified both that writes land there for real (row 8) and that nothing outside it does (rows 5-7). |
| **Project-local process spawn** | B | PROVEN | Subprocess spawning inside the sandbox works and inherits the same restrictions (row 11). No broker involvement -- correctly so, per the "don't bureaucratize harmless computation" principle. |
| **External filesystem read/write** | C | PROVEN (write only) | `external_fs_write` fully implemented: authorize against `allowed_dirs`, execute on the host, receipt. Approved case (row 12) and denied case (row 13) both verified against real host state. **External read is NOT YET PROVEN** -- not implemented; same pattern would apply (an `external_fs_read` category checking a read-allowlist, broker reads the file and returns its content). |
| **Bounded long-running children** | C | PARTIALLY PROVEN | `spawn_child_worker` implements this for a bounded, synchronous case (the broker blocks until the child's one-shot script exits, per-call timeout). A genuinely long-running, asynchronously-monitored child (start now, poll/cancel later) is NOT YET PROVEN -- would need the broker to track a live child process handle across multiple requests, which the current one-request-per-connection protocol doesn't yet support. |
| **Network access** | C | PROVEN | `network_access` fully implemented: authorize against `allowed`/`allowed_hosts`, the broker performs the real HTTP request itself (the worker never does), receipt either way. Denied case tested end to end (row 14); an approved case was exercised implicitly by the broker's own `urllib` handler code path but not driven from inside a worker this pass -- the denial path is what actually matters for the adversarial claim (a worker cannot get network access it wasn't granted), and that's PROVEN. |
| **Credential access** | C | NOT YET PROVEN | No implementation. Intended shape: a category like `credential_access` where the broker itself holds the real credential (never handed to the worker at all, in any form) and performs the credentialed action on the worker's behalf -- e.g. "make this API call with the configured key," never "give me the key." This is the same principle IJulia's own kernel process never seeing a real secret would follow, extended to any future NeuraJL host-service integration. |
| **Package-management effects** | C | NOT YET PROVEN | `Pkg.add`/`Pkg.develop`/etc. from inside a running worker are not currently gated at all -- the sandbox's read-only depot means a worker-initiated `Pkg.add` would fail (can't write to a read-only depot) but this is an accident of the filesystem boundary, not a designed capability check. A real `package_management` category would need the broker to decide whether a specific package/version is allowed and perform the install into a location the worker can then use -- not designed in detail this pass. |
| **Host service invocation** | C | NOT YET PROVEN | No implementation. Intended shape: identical to `external_fs_write`/`network_access` -- a named category, a ceiling entry describing which services/operations are allowed, the broker performs the actual call. This is the general case the other C-class categories are specific instances of. |

## Ceiling format (as implemented)

A JSON object, one key per category, fixed for the life of a broker/session,
never mutated by a request:

```json
{
  "external_fs_write": {"allowed_dirs": ["/absolute/path/one", "/absolute/path/two"]},
  "network_access": {"allowed": false},
  "spawn_child_worker": {}
}
```

`spawn_child_worker` itself has no direct ceiling shape -- its check is
"is the requested child ceiling a subset of *this whole ceiling object*,"
not a separate allowlist.

## What "the model may request, the worker may not grant" means concretely

There is exactly one function in `src/Neura.jl` that can reach a Class-C
effect: `request_capability(category, params)`. It performs no host effect
itself -- it sends a request over a socket and returns whatever the broker
sends back. Every actual Class-C effect (the file write, the HTTP request,
the child spawn) happens in `security/broker.py`, in a process the worker
cannot reach except through that one socket, and cannot influence except by
sending a request the broker is free to deny. This was adversarially tested,
not just asserted: `THREAT_MODEL.md` row 15 shows that bypassing
`request_capability` entirely and attempting the same effect directly still
fails, identically to a denied broker request.
