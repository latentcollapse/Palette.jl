# NIRA-Prime NeuraJL Surface Staging

## Implanted (2026-09-23)

The NeuraJL adapter is real and end-to-end proven, not staged-only anymore:

- `packages/coding-agent/src/core/tools/neurajl.ts` -- `createNeurajlBaseToolsFactory(cwd, options)`, a `SessionBaseToolsFactory` (constructs once per agent session, including once per RLM child, with a real `dispose`), not `baseToolsOverride` -- see the module's own docstring for why: `baseToolsOverride` shares one static tool map across every session that asks for it, which would mean every agent session (and every RLM child) silently sharing ONE Julia kernel's mutable bindings. `baseToolsFactory` was added to `agent-session.ts` specifically for persistent operator runtimes and is the correct fit.
- Exported from the real public entry point: `tools/index.ts` -> `sdk.ts` (`createNeurajlBaseToolsFactory`), alongside `createNeurabashTool`.
- Bridges to `ijulia-operator-lab/security/session_cli.py` (new in that repo), a thin persistent stdio wrapper around the already-adversarially-tested `NeuraSession` -- one `python3 session_cli.py` process per agent session, spawned once, driven for that session's whole lifetime via newline-JSON turns, not shelled out fresh per call.
- `packages/coding-agent/test/suite/neurajl-substrate-modes.test.ts` -- through the real `createAgentSession` entry point, not stubs, for the two tests that matter most: state persisting across SEPARATE tool calls (the one thing NeuraBash's own first-pass adapter explicitly does not do yet -- "each call is an independent, ephemeral invocation"), and `dispose` actually terminating the underlying process, not just being a no-op.

**A real, serious bug was found and fixed building this bridge, in `ijulia-operator-lab` itself, not in this fork:** every `subprocess.run(["julia", ...])` call in that codebase that didn't explicitly set `stdin=` inherited the caller's own stdin -- and `julia -e ...` (confirmed, unlike e.g. `/bin/true`) silently breaks the caller's own subsequent reads from that same stdin. Invisible in every prior one-shot caller; fatal for `session_cli.py`, whose own broker (running in a background thread inside the SAME process) calls exactly this code path for every single ephemeral turn. A model's first `ephemeral: true` call in a real chassis session would have silently broken every turn after it. Fixed at the source (`ijulia-operator-lab` commit `fc0f727`), not worked around here.

**Known gap, not fixed this pass:** the chassis-wide `npm run build`/`tsgo --noEmit` typecheck fails for reasons unrelated to this change -- `@earendil-works/pi-agent-core` and `@earendil-works/pi-ai` have no built `dist/` in this checkout at all, which breaks module resolution for every file that imports them, including the already-shipped `neurabash.ts`. `npm run test` (vitest) is unaffected (esbuild transpilation, not a full program type-check) and is what actually verified this work -- 95 pre-existing test failures exist in this checkout across unrelated areas (daemon-supervisor, extensions-discovery, mcp-catalog, model-registry, release-signatures -- all consistent with the same unbuilt-dependency root cause), none touching neurajl/neurabash/sdk.ts/tools/index.ts.

## Frozen chassis

- Shared base branch: `nira-prime/base`
- Base commit: `c2951292a32d7980c65c9c012de1b7f6e036f3c6`
- Surface branch: `operator-surface/neurajl`
- Prime-Agent is retained only as `prime-agent-upstream`; this branch does not track it.

## Host boundary

`baseToolsFactory` (see above), not `baseToolsOverride` -- both exist on the shared base as of `e91b10f50`. NeuraJL's session omits the IPython kernel entirely, per the original intent below, but does so via the factory boundary built for persistent runtimes rather than the static-override one.

For the eventual comparison, expose only the NeuraJL tool in this fork's substrate-mode session. Do not activate the NeuraBash adapter or IPython as alternate execution paths during the NeuraJL condition. Keep host-side RLM and agent observe/message services substrate-neutral.

## Rebase discipline

Keep commits on this branch limited to NeuraJL adapter, configuration, and integration tests. Put approved host/chassis changes on `nira-prime/base` in both forks, then rebase this branch explicitly:

```bash
git switch nira-prime/base
# apply and verify an approved NIRA-Prime host change
git switch operator-surface/neurajl
git rebase nira-prime/base
```

Do not pull or rebase Prime-Agent `main` into the experiment. Cherry-pick selected upstream ideas into the NIRA-Prime base only after review, and apply corresponding host changes to both comparison forks.
