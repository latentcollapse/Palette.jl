# Porting NeuraBash's security doctrine to NeuraJL

What was reused, what was redesigned, and one place the port genuinely did
not transfer cleanly -- written honestly, per the goal's own instruction not
to assume NeuraBash's exact implementation is automatically correct for
Julia.

## Reused directly (doctrine, verified still true here)

- **OS-level containment, not a language blacklist.** NeuraBash's own README
  already states this explicitly, and it's the one piece of doctrine this
  pass leaned on hardest: the fence lives outside the interpreter (bubblewrap
  namespace isolation), not inside it (no in-language `authorize()` wrapper
  pretending to be a security boundary). Confirmed for Julia specifically,
  not assumed: `eval`, `ccall`, `run`, and raw sockets were each tested as an
  escape vector, and each failed at the kernel/namespace level, identically
  to a direct attempt -- see `docs/THREAT_MODEL.md` rows 1-11.
- **`--clearenv`, no ambient credentials.** Directly reused in
  `security/launch_worker.py`'s bwrap invocation -- an explicit, minimal
  environment, nothing inherited from the host process by default.
- **`--unshare-user --disable-userns --assert-userns-disabled`, `--unshare-pid` (NeuraBash also passes `--as-pid-1`; NeuraJL does not, so that bwrap's reaper collects orphaned processes), `--cap-drop ALL`, `--new-session`, `--die-with-parent`.**
  The exact same flag set NeuraBash's `scripts/security_launcher.py` uses,
  for the same reasons. Not reinvented, copied because it's already correct.
- **Bounded filesystem view via explicit bind mounts, read-only by default.**
  Same principle, same mechanism.
- **"Authorize before effect, execute, receipt after."** The literal phrase
  and its ordering come from this project's existing doctrine (see the root
  README's Authority philosophy section, itself echoing NeuraBash). Reused
  as the broker's request-handling order, not reinterpreted.
- **The `C_child ⊆ C_caller` principle itself** -- not NeuraBash-specific,
  but part of the same "unbounded power, extremely bounded authority"
  thesis this whole project holds. Implemented fresh for NeuraJL's specific
  nested-worker shape (`security/broker.py`'s `ceiling_is_subset`), not
  copied from anywhere, because NeuraBash doesn't currently have a nested-
  child-authority story to copy in the first place -- this is new ground.

## Redesigned, not copied (the substrate is genuinely different)

- **The broker is a separate host process, not a kernel-host-handler
  bridge.** NeuraBash's equivalent host-mediation lives inside
  `_createKernelHostHandlers`-style RPC over an IPython kernel's comm
  channel (in the Prime-Agent integration layer, not NeuraBash itself) or,
  within NeuraBash's own repo, its Python `security_launcher.py`/daemon
  processes. NeuraJL's worker isn't hosted inside any larger agent runtime
  yet, so there's no existing comm channel to reuse -- the broker here is
  its own small, standalone process with its own Unix-socket protocol,
  built for this pass specifically.
- **One-request-per-connection JSON over a bind-mounted Unix socket**,
  not NeuraBash's NBR2 frame protocol. Simpler, because the requirements
  are simpler (no persistent binding state to negotiate across calls yet --
  see `docs/CAPABILITY_MODEL.md`'s "bounded long-running children" gap).
  This is very likely too simple for a real product eventually (no
  multiplexing, no session resumption), and is explicitly not claimed to be
  more than what it is: enough to prove the architecture, not a finished
  transport.
- **Capability ceiling as an explicit JSON object with named categories**,
  rather than NeuraBash's security-profile names (`readonly`/`workspace`/
  `sandbox`). NeuraJL's ceiling is deliberately per-category and
  composable (a session can have `external_fs_write` for one specific
  directory and nothing else) rather than one of three fixed presets. This
  is a real design difference, not just a naming one, and was a deliberate
  choice for this pass -- whether it's the right choice long-term is an
  open question, not settled by this experiment.

## Where the port did not transfer cleanly -- the depot (now solved, differently)

NeuraBash's own runtime-continuity work (`docs/RUNTIME_CONTINUITY_ARCHITECTURE_NOTE.md`
in its repo, and the `neurabash-runtime-depot.json` attestation mechanism)
solved the "every sandboxed launch recompiles from scratch" problem with a
read-only, attested, prewarmed depot layered under a writable ephemeral
overlay (`JULIA_DEPOT_PATH = writable:readonly_base`).

This pass initially copied that exact layering pattern, and it did not
eliminate the cold-start tax here -- a sandboxed NeuraJL worker paid a real
~40 second precompilation cost (`JSON`'s dependency tree, mainly `Parsers`)
on every launch regardless of how thoroughly the read-only base depot was
prewarmed. That was reported as an open, unsolved gap for one session.

**Root cause, found later by direct reproduction (`JULIA_DEBUG=loading`,
outside any sandbox, no bwrap involved):** a `JULIA_DEPOT_PATH` whose
*first* entry is a fresh, empty, writable directory changes the "desired
build_id" Julia computes for stdlib dependencies (observed concretely on
`TOML`). That mismatch is not cosmetic -- it cascades and invalidates every
downstream cache that recorded the old build_id, forcing `Parsers`/`JSON`/
etc. to recompile from scratch on every single launch, independent of how
good the read-only base depot is. This reproduces with a plain two-entry
`JULIA_DEPOT_PATH` and a completely unsandboxed `julia` process -- it was
never a bubblewrap-specific interaction, and NeuraBash's own layering
pattern was never going to solve it on Julia's substrate no matter how
carefully ported, because the problem is upstream of the sandbox entirely.

**The fix that actually works: don't layer -- clone.** Each worker gets a
real, independent copy of the depot (`cp -a --reflink=auto`, near-free on a
copy-on-write filesystem like btrfs -- confirmed via a canary-file test
that a write inside one worker's clone never appears in the shared source
depot) bound as the *single* `JULIA_DEPOT_PATH` entry, at the depot's own
real path inside the sandbox (package source paths are embedded as
absolutes in the precompiled cache, so the guest path has to match, not
just the clone's content). One entry means no build_id-mismatch cascade;
a real independent clone means no shared-depot corruption risk. Measured
end to end through the real `security/launch_worker.py` code path (not a
synthetic benchmark): ~41s -> ~4.4s for a cold `using Neura` launch, all 19
of `security/test_authority.py`'s adversarial tests still passing (they
launch real sandboxes; the whole suite dropped from what would have been a
~13-minute floor to 78s), and Julia's own 55-assertion `Pkg.test()` suite
unaffected (this change never touches `src/Neura.jl`). See
`security/launch_worker.py`'s `_clone_depot` docstring for the full
mechanism.

**Still open, honestly:** the reflink path is only proven fast on btrfs.
`cp --reflink=auto` falls back to a real byte-for-byte copy on a
filesystem without CoW support, which is still correct but would reintroduce
a real (if bounded and one-time-per-launch, not per-package) cost --
not yet measured on such a filesystem because this project's actual disks
are btrfs. This pass did not need NeuraBash's depot-attestation mechanism
at all; whether a future package-management capability (see
`CAPABILITY_MODEL.md`'s NOT YET PROVEN row) needs anything like it is a
separate, still-open question.
