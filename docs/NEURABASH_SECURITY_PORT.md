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
- **`--unshare-user --disable-userns --assert-userns-disabled`, `--unshare-pid --as-pid-1`, `--cap-drop ALL`, `--new-session`, `--die-with-parent`.**
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

## Where the port did not transfer cleanly -- the depot

NeuraBash's own runtime-continuity work (`docs/RUNTIME_CONTINUITY_ARCHITECTURE_NOTE.md`
in its repo, and the `neurabash-runtime-depot.json` attestation mechanism)
solved the "every sandboxed launch recompiles from scratch" problem with a
read-only, attested, prewarmed depot layered under a writable ephemeral
overlay (`JULIA_DEPOT_PATH = writable:readonly_base`).

This pass copied that exact layering pattern -- and it did not eliminate
the cold-start tax here. A sandboxed NeuraJL worker still pays a real ~40
second precompilation cost (`JSON`'s dependency tree, mainly `Parsers`) on
every launch, even after an explicit attempt to pre-warm the real, shared,
read-only-bound `~/.julia` depot ahead of time. The precompiled cache that
attempt produced was not found valid inside the sandbox's two-entry
`JULIA_DEPOT_PATH`, and a second attempt -- precompiling *under* that exact
two-entry depot structure from the start -- triggered recompilation of
nearly the entire dependency tree including `Pkg` itself (72 seconds for
`Pkg` alone), strongly suggesting Julia's precompile-cache validity is
sensitive to the depot path structure/order in a way this pass did not
fully characterize or solve.

**This is recorded as a real, open engineering gap, not glossed over as
solved by analogy to NeuraBash.** The goal that authorized this pass said
explicitly not to assume NeuraBash's implementation is automatically
correct for Julia -- this is the concrete instance where that caution was
warranted. It did not block this pass's actual claim (authority containment
is correct regardless of cold-start time, verified in every test in
`docs/THREAT_MODEL.md`), but it is a real cost that would need solving
before NeuraJL workers are practical to launch repeatedly, the same way
NeuraBash's own depot problem was a real, still-being-worked-on cost before
this session found and reported evidence it's likely improved (see
`/mnt/d/Code Projects/Project NIRA/NIRA_PRIME_GATE2_PROVIDER_REPORT.md`
section 6, a separate, unrelated project's finding on the same underlying
Julia/NeuraBash depot mechanism, for context on how deep that rabbit hole
already goes).
