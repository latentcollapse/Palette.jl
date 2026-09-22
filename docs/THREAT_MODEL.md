# NeuraJL Threat Model — Experiment 002

**Date:** 2026-09-22. Scope: the authority fence around a contained NeuraJL worker, per `docs/EXPERIMENT_002_AUTHORITY.md`.

## Adversary model

**The model driving the worker is assumed fully adversarial with respect to authority, not competence.** It is not assumed malicious in the sense of trying to damage anything for its own sake -- it is assumed to have full, legitimate reasons to want to use `eval`, `ccall`, `run`, `Base`, `Pkg`, metaprogramming, and reflection for real work, and to potentially attempt something that reaches outside its intended authority envelope either by mistake, by taking a shortcut, or by genuinely trying to escalate. The fence must hold regardless of intent, because intent is not observable and must not be relied on.

**Explicitly rejected as a defense:** trusting the model to call a "nice" API (`Neura.request_capability`) instead of the raw language facility that would achieve the same effect. Every capability test in this document was run twice in spirit -- once through the cooperative API, once by attempting the same effect directly (`write`, `Sockets.connect`, `run`, `ccall`) -- and the direct attempts were tested first, not assumed to fail because a nicer path existed.

## In scope

Architectural bypass: can Julia language power (as used from inside the sandbox, cooperatively or adversarially) reach outside the intended authority envelope?

## Out of scope (explicitly, per the goal that authorized this work)

Kernel exploitation (CVE-hunting against the Linux kernel, bubblewrap, or the container runtime itself). This threat model assumes the kernel's namespace/capability primitives work as documented. If they don't, that's a kernel bug, not an architecture bug, and is a different, much larger, separate investigation.

## Trust domains

1. **Contained NeuraJL worker** -- a real, unrestricted `julia`/IJulia process. Full language semantics. OS-level bounded (bubblewrap: user/PID/IPC/net namespace isolation, no ambient credentials, bounded filesystem view). See `security/launch_worker.py`.
2. **Host capability broker** -- a separate process, outside the worker's namespace entirely, reachable only through one bind-mounted Unix socket. Owns all privileged host effects. See `security/broker.py`.

## A methodological finding that shaped how every test below is read

Two early "escape" attempts (`write` to `/tmp/...` and to an unbound `/home/mattc/...` path) both returned success from inside the sandbox. Both were false positives: `--tmpfs /tmp` gives the sandbox its own ephemeral, non-persistent `/tmp`, and bubblewrap auto-creates ephemeral parent directories for bind-mount targets (here, a `/home/mattc/` directory that exists only to host the `.julia` mount point) -- writes to sibling paths inside those land on the sandbox's own throwaway root, not the real host filesystem. Both were confirmed false by checking the real host filesystem afterward, from outside the sandbox, and finding nothing there.

**Rule applied for the rest of this project, not just this pass:** an in-sandbox "success" is not evidence of anything about the fence, in either direction, until verified from outside. Every "escape blocked" claim below was checked this way, not just trusted from the worker's own stdout.

## Adversarial tests run (real, on this machine, 2026-09-22)

| # | Attempt | Facility used | Result | Verified how |
|---|---|---|---|---|
| 1 | Outbound HTTP via subprocess | `run(\`curl ...\`)` | Blocked -- exit code 6 (could not resolve host) | Process exit code; no network namespace to resolve or route through |
| 2 | Outbound HTTP via raw sockets | `Sockets.connect` | Blocked -- `ENETUNREACH` | Direct `IOError`, kernel-level rejection, no DNS step even needed |
| 3 | Outbound via `ccall`-driven language power | `ccall(:getpid, ...)` (proves ccall works at all) then `Sockets.connect` | `ccall` succeeds (`getpid()==1`, confirming real PID-namespace isolation as a side effect); the connect attempt still fails identically to #2 | Same `ENETUNREACH` |
| 4 | Read a sensitive host file | `read("/etc/shadow", String)` | Blocked -- file does not exist in the sandbox's view at all (not "permission denied": genuinely absent) | `SystemError: ... No such file or directory` |
| 5 | Write to sandbox-local ephemeral storage | `write("/tmp/escaped.txt", ...)` | "Succeeded" in-sandbox; **confirmed absent from the real host `/tmp` afterward** | `ls`/`find` from outside the sandbox, after it exited |
| 6 | Write to an unbound host-adjacent path | `write("/home/mattc/definitely-not-approved-$$.txt", ...)` | "Succeeded" in-sandbox; **confirmed absent from the real host `/home/mattc/` afterward** | Same, from outside |
| 7 | Write to a genuinely read-only bound path | `write("/usr/definitely-not-approved.txt", ...)` | Blocked -- `Read-only file system` | Direct `SystemError` |
| 8 | Positive control: write inside the bounded workspace | `write("<workspace>/inside-workspace.txt", ...)` | Succeeded, and **confirmed present on the real host** at the expected path with the expected content | `cat` from outside the sandbox |
| 9 | `eval`-based escape attempt vs. direct code | `Core.eval(Main, Meta.parse("run(\`curl ...\`)"))` | Fails identically to attempt #1 -- same process, same failure | Same exit code |
| 10 | `eval` result equivalence | `1+1` direct vs. `Core.eval(Main, Meta.parse("1 + 1"))` | Identical (`2 == 2`) -- eval grants no extra power, and no less | Direct comparison in the same script |
| 11 | Subprocess inherits the same network restriction | `read(\`sh -c "curl ... \|\| echo NO_NETWORK_IN_CHILD"\`, String)` | Child correctly reports no network | stdout captured from the child |
| 12 | Broker-mediated approved write | `Neura.request_capability("external_fs_write", ...)` inside the ceiling | Approved; file **confirmed present on the real host**, exact byte count matched | `cat` from outside |
| 13 | Broker-mediated denied write | Same, path outside the ceiling's `allowed_dirs` | Denied with a specific reason; **confirmed absent on the real host** | `ls` from outside, file not found |
| 14 | Broker-mediated denied network | `Neura.request_capability("network_access", ...)` while ceiling says `allowed: false` | Denied | Response + receipt |
| 15 | Direct bypass of the broker for the same effect the ceiling denies | Raw `write("/etc/direct-bypass-attempt.txt", ...)` right after a denied broker request | Blocked exactly like #6/#7 -- the broker is not a backdoor that widens what the sandbox otherwise permits | `ls` from outside, absent |
| 16 | Worker attempts to construct its own, less-restricted sandbox | `run(\`bwrap --unshare-user --uid 0 --gid 0 -- ...\`)` from inside the worker | Blocked at the kernel level -- `ENOSPC: nesting depth or /proc/sys/user/max_*_namespaces exceeded` | Bubblewrap's own stderr, a real kernel rejection, not an application-level check |
| 17 | Nested child worker requesting a wider ceiling than its parent | `Neura.request_capability("spawn_child_worker", ceiling={network_access: allowed=true}, ...)` from a worker whose own ceiling has no network | Denied by the broker's subset check before any child was launched | Response + receipt |
| 18 | Nested child worker requesting a genuine subset of its parent's ceiling | Same, ceiling narrowed to a real subdirectory of the parent's allowed dir | Approved; broker actually launched a **second, independent** bwrap sandbox; child reported `pid=1` (its own PID namespace, not the parent's) | Response body, receipt, and the child's own `getpid()` output |

Every row's outcome was checked against real, independent evidence (host filesystem state, process exit codes, kernel error text, a second process's own PID) -- not against what the worker's own script claimed.

## Known gaps (honest, not buried)

- **Depot cold-start performance, scoped more precisely than first suspected.** A sandboxed launch running plain Base-only Julia (no `using Neura`) is fast -- the 8 tests in `security/test_authority.py`'s `TestSandboxContainment` class run in ~7 seconds total, real sandboxes included. The cost is specific to `using Neura`, which (as of this pass) pulls in `JSON` transitively for `request_capability`: that triggers a real, uncached ~35-40s precompilation of `JSON`'s own dependency tree (mainly `Parsers`) on every sandboxed launch, because the writable depot overlay (`--tmpfs /run/neurajl/depot`) is fresh every time and an attempt to pre-warm the real, read-only-bound `~/.julia` depot ahead of time did not eliminate it. This project hit the same class of problem NeuraBash's own depot work has been fighting, but narrower than first framed. Not a security question: correctness was verified in every test above regardless of the cold-start tax. See `docs/NEURABASH_SECURITY_PORT.md`.
- **Only two of the eight-plus capability categories are fully implemented and adversarially tested end to end** (`external_fs_write`, `network_access`, plus `spawn_child_worker` for the nesting case). The rest are defined in `docs/CAPABILITY_MODEL.md` with their intended enforcement point, explicitly marked NOT YET PROVEN.
- **The broker's Unix socket currently has no authentication beyond filesystem access to the bind-mounted path.** Anything with access to that one path inside the sandbox can send requests; there's no per-request signing or session-token check distinguishing "the worker" from "anything else that ended up inside the same sandbox." For a single-worker-per-broker session (the only configuration tested), this doesn't currently matter, but it would if multiple untrusted processes ever shared one sandbox.
- **Nested child workers were tested to exactly one level.** The subset-check logic (`ceiling_is_subset`) is recursive in principle (a grandchild's request would be checked against whatever ceiling the child was actually granted), but a real grandchild-level launch was not performed this pass.
