# NIRA-Prime overnight session — decision doc

**For:** Matt, morning of 2026-09-21
**From:** Claude, autonomous overnight pass per your instruction to fork/modify Prime Agent into NIRA-Prime while you slept
**Bottom line:** did not rip out IPython tonight. Added NeuraBash as a second, additive tool instead, on its own branch. Here's exactly why, what's real, and what needs your call.

---

## TL;DR

- `neurabash-integration` branch on `prime-agent`, one commit, ahead of a now-updated `main`. Adds a `neurabash` tool alongside `ipython` — not a replacement.
- Did not remove IPython. The kernel it drives turned out to be the backbone for RLM sub-agent spawning, the Python skills system, file-edit diffs, image attachments, and cross-session state — NeuraBash has no equivalent for any of that yet. Removing it tonight would have broken Prime Agent, not upgraded it.
- Verified Security Kernel V1 landed in NeuraBash overnight (real bubblewrap sandboxing, not stub fail-closed). Also independently found it does NOT reproduce cleanly in a fresh environment right now — a real Julia precompile error under the sandboxed profile. Evidence below.
- Cleaned up two rounds of self-inflicted git debris from my own interrupted pulls (details below, so you're not confused by anything that looks off in repo history/reflog).
- `main` is now fully up to date with `origin/main` (284 commits), and `neurabash-integration` is rebased cleanly on top of it — including a real conflict (upstream had refactored `tools/index.ts` in the same window, dropping the old `createTool`/`allToolNames` switch-dispatch pattern entirely in favor of just `createAllToolDefinitions`; resolved by following the new shape, not blending both).
- `npm run check` is **clean**: biome, `tsgo --noEmit`, installer, push-guard, and browser-smoke all pass. Took two passes — `npm install` was needed after the dependency bump, and `npm run check` itself caught two real bugs in my first draft (`OutputAccumulator`'s API had changed upstream in the same 284 commits, and an early-exit path didn't satisfy `AgentToolResult`'s type). Both fixed properly, not suppressed, in a second commit. Two commits total on `neurabash-integration`, not merged to `main`, not pushed.

---

## What actually shipped

`packages/coding-agent/src/core/tools/neurabash.ts` — a new tool, modeled on the existing `bash.ts` (simple spawn-and-capture), not `ipython.ts` (persistent ZMQ kernel). Wired into the `ToolName` registry in `tools/index.ts` and re-exported from `sdk.ts`, exactly the way `ipython` already is. Confirmed `agent-session.ts` builds its default tool set via `createAllToolDefinitions`, so `neurabash` is live by default in a session, not opt-in-only.

Scope, deliberately narrow:

- One-shot `--neura-profile=workspace -c <code>` per call — NeuraBash's own "ephemeral session" mode (spec §RT-009), not the persistent daemon/binding-across-calls model it also supports.
- No session state persists between calls yet. Each call is independent.
- Fails closed with a clear message if `NEURABASH_BIN` isn't set or the binary doesn't exist, rather than silently doing nothing.
- Uses a persistent `JULIA_DEPOT_PATH`/`XDG_RUNTIME_DIR` under `~/.prime-agent/neurabash/` (not fresh temp dirs per call) so package precompilation and daemon warm-start actually pay off across calls instead of every call eating full cold-start cost.

This is committed on `neurabash-integration`, one commit, not touching `main`. `main` itself needed real repair first (below) before I'd trust building on it.

## Why IPython wasn't removed

You said "the only real constraint is the fork and installing the new shell." I went and actually read `ipython.ts` and `kernel/index.ts` before touching anything, and the scope is much bigger than a code-exec tool:

- **RLM sub-agent spawning.** The kernel bootstraps a Python `rlm` module (`rlm.run`, `find_models`, `list_subagents`, `delete_subagent`) — this is how Prime Agent spawns and manages recursive sub-agents from inside executed code. `docs/rlm.md`, `docs/rlm-runtime.md` in this repo cover it.
- **A Python skills bridge** — dynamically-imported skill modules wrapped as callables inside the kernel namespace.
- **File-edit diffs** surfaced back to the host via a dedicated MIME type (`application/vnd.prime-agent.diff+json`) — this is how the `edit` skill shows you diffs.
- **Image/media attachments** via another dedicated MIME type.
- **Inter-agent messaging** — parent/sibling/child message routing, also through the kernel's comm channel.
- **Cross-session state.** The kernel namespace is dill-serialized to disk and revived on session resume (`state-snapshot.ts`) — variables, imports, and loaded data survive a `/reload`.

NeuraBash has none of these today. Its own audit doc (read yesterday, still true) marks raw Julia entry, most of the standard library, and the full effect/security model as MISSING or PARTIAL. Pulling `ipython.ts` out tonight would have silently broken sub-agent spawning, skills, diffs, and state persistence — not a shell upgrade, a regression, discovered days later. That's exactly the kind of foundational choice you told me to flag instead of guess on.

Keeping both tools live is also just the right experimental design, independent of the safety argument: you can't observe whether an agent naturally reaches for NeuraBash differently than IPython if IPython isn't there to compare against. Once Cognitive Control Plane V1's discovery/escalation logic exists, this is the actual test rig for it.

## Security Kernel V1 — verified, with a real caveat

Read `docs/SECURITY_KERNEL_V1_REPORT.md` (dated today) in the NeuraBash repo. Real, substantial change since yesterday: bubblewrap-backed sandboxing with `readonly`/`workspace`/`sandbox` profiles, host-enforced (can't read outside secrets, can't escape the workspace, can't touch host devices, fails closed on anything unsupported — `inherit` explicitly not presented as a sandbox).

I didn't take the report's word for it. Ran `tests/security/launcher_smoke.py` myself: **PASS**. Then ran `tests/security/security_v1.py` (the real negative-control suite) myself: **failed**, with a genuine Julia precompile error —

```
ERROR: LoadError: ArgumentError: Package NeuraBash does not have Unicode in its dependencies:
- You may have a partially installed environment. Try `Pkg.instantiate()` ...
```

This happened under a fresh, throwaway `JULIA_DEPOT_PATH` I created for the test run — most likely I skipped a required `Pkg.instantiate()`/precompile step that a properly bootstrapped depot would have already done, not a broken sandbox per se. But I didn't chase it down further tonight, so I'm reporting exactly what happened rather than the report's clean claim. Before trusting Security Kernel V1 for anything real (including wiring `neurabash.ts` above to actually run), reproduce `security_v1.py` cleanly first, ideally with the depot NeuraBash's own `scripts/install.sh`/`build.sh` produces rather than an ad hoc directory.

## Repo repair (so nothing looks mysterious later)

`prime-agent` was 284 commits behind `origin/main` (`PrimeIntellect-ai/prime-agent`) and there was a live stale process (PID 1455153) from a previous session. You confirmed it shouldn't be running; killed cleanly, no orphans.

The pull itself went badly, entirely my fault: I let my own tool's default timeout kill `git pull` mid-checkout, twice, which left the working tree with a pile of half-applied tracked-file changes (looked like mass deletions — they weren't, just an interrupted checkout) and, separately, debris untracked files at paths the real merge also wants to create. I verified the tracked-file "damage" was 100% self-inflicted checkout debris (cross-checked against `git diff --name-only HEAD origin/main`, exact match) before running `git checkout -- .` to clear it — not touching anything that looked like real organic work, and AGENTS.md's own git rules are why I checked twice before doing that. Two batches of untracked debris (confirmed by mtime clustering, both within seconds of my own pull attempts) got removed the same way. Your actual pre-existing untracked skill directories (`neurosymbolic-harness`, `symbolic-memory`, `tencentdb-memory`, `wolfram-alpha`, etc.) and the `hlx_*` evidence tarballs were untouched throughout — checkout never touches untracked files, and their mtimes predate tonight by days.

Final clean pull is running as I write this, backgrounded, no artificial timeout this time. If you're reading this and it's still not done: it's almost certainly still running, not stuck — this disk (`/mnt/d`, NTFS-over-FUSE) took over 3 minutes just for the checkout phase on the first attempt. Check `git status` on `main`; if it says "up to date," it finished clean.

## Open items — your call

1. **Reproduce `security_v1.py` cleanly** before trusting Security Kernel V1 as a real boundary for anything, including actually running `neurabash.ts` for real. I didn't have time to chase the precompile error to ground tonight.
2. **`neurabash-integration` is rebased, checked clean, and committed (2 commits) — but not merged to `main`, not pushed.** Your call on when it's ready. Nothing runtime-tested yet: no live kernel/session has actually invoked this tool end-to-end, only statically checked. First real test needs `NEURABASH_BIN` pointed at a built `build/bin/neurabash` and item 1 resolved first.
3. **Where should the NeuraBash binary/depot actually live?** `neurabash.ts` reads `NEURABASH_BIN` from the environment with no default, and defaults the Julia depot to `~/.prime-agent/neurabash/`. Both are first guesses, not considered decisions — NeuraBash's own build/packaging story is itself still in flux (Codex is mid-pass on it), so I didn't want to hardcode a path into a moving target.
4. **Full IPython removal is a real future project, not abandoned** — it needs NeuraBash to grow raw Julia entry, a skills-equivalent, and either a sub-agent-spawning primitive or a decision that RLM spawning moves elsewhere first. That's downstream of Cognitive Control Plane V1 and Discovery V1, not something to force before those exist.

---

## **Wacky ideas — capability boosts for NIRA-Prime beyond NeuraBash itself**

**Give NeuraBash a route into the same RLM sub-agent primitive IPython's kernel already exposes, instead of building a second one.** `rlm.run`/`list_subagents`/`delete_subagent` already exist as a host-request bridge over the Jupyter comm channel. NeuraBash's `shell.*` namespace (spec §3) is the natural place for a `shell.spawn_subagent` operation that calls the exact same host handler IPython uses today — one sub-agent primitive shared by both tools, instead of NeuraBash reinventing its own.

**Let the workspace execution ledger (from the Cognitive Control Plane conversation) double as Prime Agent's own trace/session history.** Prime Agent already has `docs/long-running-agents.md`, a daemon protocol, session managers, `agent-traces-git-context.test.ts` — there may already be a structured event log in this codebase that's 80% of what Failure Archaeologist/Oracle Splitter need. Worth checking before building a second one inside NeuraBash from scratch.

**The `%%bash` magic cell in IPython and NeuraBash's own Bash-as-DEPTH-0 are doing almost the same job today, badly duplicated.** Once NeuraBash's `shell.*` namespace is real, `applyShellSettingsToBashMagicCell`'s command-prefix/shell-path logic in `ipython.ts` could become a thin wrapper over NeuraBash instead of its own separate implementation — one bash-execution path instead of two slightly-different ones living side by side.

**Prime Agent's `executionMode: "sequential"` constraint on ipython (single-threaded kernel, no parallel calls) doesn't have to apply to NeuraBash.** NeuraBash's JUL workers are process-visible per-segment (spec RT-001) — there's no architectural reason `neurabash` calls couldn't run with `executionMode: "concurrent"` once the security/resource-limit story is solid, meaning an agent could genuinely parallelize independent symbolic computations instead of queueing them behind one kernel. Worth an explicit decision once Security Kernel V1's resource limits are proven, not before.

---

Sleep well. Ping me when you're back — I'll pick up wherever the pull/rebase/check items landed.
