# Installation and MCP

The Linux supervised runtime requires Julia, Python 3, bubblewrap, and a built
Rust host. Julia dependencies are defined by `Project.toml`; Rust dependencies
are locked in `host/Cargo.lock`. Instantiate the Julia project and build the host
before installing the adapter. Additional packages must be provisioned by the
host, not silently downloaded inside an offline worker.

See the [portable plugin setup](../plugins/palette/README.md) for Agent Plugins manifests, a repository marketplace, and a generic MCP launcher.

## Local stdio plugin

```sh
python3 security/install_operator_plugin.py \
  --plugin-dir /absolute/path/to/plugin \
  --workspace-dir /absolute/path/to/workspace \
  --repo-dir /absolute/path/to/Palette
```

The installer creates a Codex-compatible manifest and MCP configuration. It
checks the local build and preserves configuration when updating an existing
Palette entry. The client must separately support and enable that plugin format.
Installing these files does not register a remote ChatGPT connection.

The adapter's entrypoint is `security/operator_workspace_router.py`. It exposes
`palette`, `palette_control`, `palette_workspace`, and `palette_patch`. See
[workspace routing](workspaces.md) before sharing it between conversations.

| Environment variable | Purpose |
| --- | --- |
| `PALETTE_REPO` | Runtime source checkout |
| `PALETTE_HOST` | Built host executable |
| `OPERATOR_WORKSPACE` | Default legacy workspace |
| `PALETTE_STATE_DIR` | Legacy snapshots, outside the worker workspace |
| `PALETTE_WORKSPACE_STATE_ROOT` | Routed world registry and snapshots |
| `PALETTE_PATCH_ROOTS` | Trusted administrator's JSON mapping of writable targets |
| `JULIA_DEPOT_PATH` | Provisioned Julia depot |
| `JULIA_PKG_OFFLINE` | Julia's offline package policy |

Restart the adapter to load updated runtime code. Refresh client tool discovery
when the tool schema changes. Reusing a connection does not require creating a
second plugin registration.

## Remote clients

A remote MCP client needs a supported transport or tunnel to this local service.
Palette does not provision a cloud service or bundle client credentials. Keep
transport credentials outside workers. Runtime source updates and client
connection registration are separate operations.
