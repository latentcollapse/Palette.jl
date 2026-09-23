# NIRA-Prime NeuraJL Surface Staging

This branch is reserved for the NeuraJL operator surface. It prepares the chassis only; it does not implement or install NeuraJL.

## Frozen chassis

- Shared base branch: `nira-prime/base`
- Base commit: `c2951292a32d7980c65c9c012de1b7f6e036f3c6`
- Surface branch: `operator-surface/neurajl`
- Prime-Agent is retained only as `prime-agent-upstream`; this branch does not track it.

## Host boundary

The existing public `createAgentSession` path accepts `baseToolsOverride` and `initialActiveToolNames`. The intended NeuraJL adapter should be an `AgentTool` supplied through that boundary, so a NeuraJL session can omit the IPython kernel rather than merely leave it inactive. RLM child sessions already receive the parent's base-tool override.

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
