# Turbocharge opportunities

Not bugs. Real architecture/quality improvements surfaced during audits,
kept separate from confirmed defects (which get fixed immediately and
land in `docs/THREAT_MODEL.md`/commit messages instead). Nothing here is
scheduled -- this is a standing scratchpad, added to whenever an audit
surfaces something worth doing later.

## From the 2026-09-23 external review (Codex)

1. **Typed capability handles.** Replace raw paths/dicts in requests with
   immutable typed specs and opaque broker-issued handles. Would have
   made the `spawn_child_worker` path-injection bug structurally
   impossible rather than needing a targeted fix, and reduces prompt
   serialization overhead for the model driving turns.
2. **Broker-owned async child lifecycle.** `start_child`/`poll_child`/
   `cancel_child`/`collect_child` with process groups, deadlines, quotas.
   Today's `spawn_child_worker` is synchronous-only (the broker blocks
   until the child's one-shot script exits) -- fine for the current
   ephemeral-tool use case, a real limit for anything long-running.
3. **Transactional durable turns.** Evaluate a turn in a draft module,
   produce a typed state delta, commit explicitly. Makes a failed turn's
   partial bindings (confirmed: they persist in `eval_module` today, just
   not exposed via the variable index) recoverable/inspectable instead of
   silently-there-but-invisible.
4. **A real framed protocol** for the session loop -- versioned
   length-prefix framing, cancellation, deadlines, structured errors --
   instead of newline-delimited JSON plus "parse the last non-blank stdout
   line" for ephemeral results. NeuraBash's NBR2 framing
   (`Project-LIRA-NeuraBash/julia/bin/daemon.jl`) is the reference shape;
   reuse the lesson, not the specific protocol.
5. **Reproducible package generations.** Resolve package specs to content
   hashes, build in a disposable no-network builder, atomically switch the
   worker to a new immutable depot generation. `package_management` today
   allowlists by name/version but has no tree-hash/signed-snapshot/content
   pin -- the broker runs real, unsandboxed `Pkg.add` with real network
   access on nothing stronger than a name match.
6. **Receipt-linked provenance.** Content-addressed capsules linked to
   session epoch, parent request, ceiling digest, depot generation, and
   the broker receipt that authorized the effect. Today's capsule (see
   `record_tool_capsule`) is real and mechanical but standalone -- no
   cryptographic chain back to *why* it was allowed to run.

## From the 2026-09-23 self-audit (Claude)

7. **`session_loop.jl`'s ephemeral child script is string-templated Julia
   source**, not a real function call. It works (verified: `repr(code)`
   is a genuinely safe re-escape, not string-building a shell command),
   but it's fragile to maintain -- every change to the child-side JSON
   response shape means editing a `string(...)` concatenation of Julia
   source text. A named function in `Neura.jl` (e.g.
   `Neura.run_and_report_json(code::String)`) that the child script just
   calls would remove the string-templating entirely.
8. **`session.py` is one dedicated OS process per session, no
   multiplexing** -- correct and simple, but doesn't amortize a sandboxed
   Julia worker's startup cost across many logical sessions the way
   NeuraBash's daemon does. Only worth revisiting if per-session process
   overhead becomes a real cost at the scale Prime-Agent eventually runs
   at; premature to build now.
9. **`OperationResult.error::Union{Nothing, Any}`** is semantically just
   `Any` (`Any` already includes `Nothing`) -- harmless, but the type
   signature doesn't communicate "optional" the way it reads like it
   should. Minor; touches a public struct's exported API, so bundle with
   another reason to touch it rather than a standalone edit.

## Still-open, confirmed-real, deliberately not fixed yet

- `external_fs_write`'s resolve-then-write TOCTOU/symlink race. Real in
  principle; needs actual `O_NOFOLLOW`-based file operations to close
  correctly, not a quick patch. Exploitability requires an independent,
  co-located attacker racing the exact target path at the exact moment --
  the sandboxed worker has no independent way to plant a symlink there
  itself through anything this broker exposes today.
- Broker Unix socket has no authentication beyond filesystem reachability
  of its bind-mounted path, no per-connection rate limiting, no receipt
  log rotation or fsync guarantee.
