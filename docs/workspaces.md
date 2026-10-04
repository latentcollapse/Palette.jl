# Using routed Palette worlds and approved patches

Palette ships these reusable MCP adapters for independent execution worlds and exact approved patches.

## Choose a world

Call `palette_workspace` with action=create, workspace_id=your-lab, context_id=a-stable-unique-key, scope=thread. Include workspace_id and context_id on subsequent palette and palette_control calls. Context-active routing also works, and attachment persists across router restart. Explicit workspace_id wins. Missing both fields uses the visibly identified shared legacy world; it does not automatically create an isolated thread.

Scope thread compares caller-supplied keys. It prevents accidental collisions, not impersonation by a caller who knows the key. Project scope shares a world for the same canonical project folder; open is an explicit cross-project sharing choice. Project files stay shared even when execution worlds are independent.

Close retains the saved state. Another router may attach the same metadata but cannot execute a world until the current owner closes it. Ownership locks are outside the worker mount and inherited by the adapter; abrupt router death cannot immediately admit a second writer. The adapter handles EOF and normal teardown before releasing ownership. Uncertain calls are not automatically retried.

PALETTE_MAX_LIVE_WORKSPACES defaults to 4 per router. On reaching the cap, close a world before starting another. Inactivity beyond PALETTE_WORKSPACE_IDLE_SECONDS (default 900) retires worlds on subsequent requests. This is opportunistic idle retirement, not a background garbage collector. Tasks, channels and other non-revivable objects remain subject to the existing revival contract.

## Approve one exact patch

A trusted local operator configures PALETTE_PATCH_ROOTS as JSON mapping target names to canonical source directories. This mapping is outside Julia and is not set by tool arguments. Patch storage defaults to the router registry's patches directory, outside all worker mounts.

Use palette_patch action=read, target=palette-core, path=security/example.py to inspect bounded UTF-8 content and its SHA-256. Use action=prepare with target and changes, where each change is exactly `{path, before_sha256, content}`. Null before_sha256 means create a file. Existing parent directories are required. The response includes the full review diff, digest, expiry and request_id.

Use action=apply with request_id in the same logical workspace. When the client advertises MCP form elicitation, the broker asks the client to present an explicit confirmation for the exact digest and review diff. Accepting that form authorizes one attempt. Client-confirmed approval is not proof of a named human's identity; this relies on a trusted MCP client honoring user interaction. Julia and model-supplied tool arguments cannot mint grants.

If the client does not support confirmation, the request remains pending. An explicitly authorized local administrator can inspect and approve it:

```
python3 security/patch_broker.py --storage /actual/registry/patches review REQUEST_ID
python3 security/patch_broker.py --storage /actual/registry/patches approve REQUEST_ID --digest REVIEWED_SHA256
```

Then repeat action=apply. A future grant must be authorized explicitly; merely requesting a patch is not permission for Codex or another agent to approve it on the user's behalf.

Grants expire after 15 minutes and bind the exact change set, root filesystem identity, target, and workspace. They are consumed before the helper runs, including failed and uncertain attempts. Before hashes are checked before any mutation and again before each replacement. Writes use a Linux Landlock-confined helper with descriptor-relative, no-symlink paths. Git metadata, traversal, hardlinks, deletion, renaming and creating directory trees are outside this first version. Landlock ABI >=3 is mandatory; unsupported hosts refuse application.

Individual replacements are atomic. A multi-file patch is not an all-or-nothing transaction. Use a quiescent source checkout; brokers sharing a canonical target serialize through a sibling lock across registries. Arbitrary unmanaged host writers do not participate in that lock. The host must be able to create this sibling lock. Partial completion lists committed paths and hashes and cannot be replayed with the same grant. Receipts survive the Julia world and record authority, timing, scope, digests and outcome.

Targets should be a separate source checkout. Editing that checkout does not deploy it: tests and a controlled installation switch remain separate actions. Do not allow the deployed adapter's own directory as a patch target.

## Deployment

The installer now generates operator_workspace_router.py as the entrypoint. Existing plugin configuration and optional toolchain environment are preserved. Keep the legacy OPERATOR_WORKSPACE and PALETTE_STATE_DIR unchanged when migrating an existing desk; choose a PALETTE_WORKSPACE_STATE_ROOT outside the worker's file mounts.

The MCP surface is palette, palette_control, palette_workspace, palette_patch. Client tool discovery may need refreshing after switching the entrypoint. Actual Chat confirmation availability must be established from its initialize capabilities and an interaction; local protocol tests alone do not prove the Chat UI.
