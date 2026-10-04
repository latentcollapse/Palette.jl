# Palette

A persistent Julia operator surface for interactive work and agent harnesses.
Palette keeps bindings across calls, captures results and process output, and
revives saved state after a kernel restart with an explicit report of what
survived, changed, or was lost.

Palette supplies the execution surface. Harnesses such as Cyan provide the
agent loop, model inference, and orchestration.

## Quick start

The Julia package currently uses the import name `Neura`.

```sh
julia --project=. -e 'using Pkg; Pkg.instantiate()'
julia --project=. -e 'using Neura; execute(ExecuteCode("x = 41")); println(execute(ExecuteCode("x + 1")).result.data)'
```

For supervised, sandboxed sessions on Linux, install Julia 1.12, Python 3,
bubblewrap, and a Rust build toolchain, then build the host:

```sh
cargo build --manifest-path host/Cargo.toml --release --locked
python3 security/prewarm_depot.py --project-dir "$PWD" --host-bin "$PWD/host/target/release/palette-host"
host/target/release/palette-host session --repo-dir "$PWD" --project-dir "$PWD" --workspace-dir /absolute/path/to/workspace --state-dir /absolute/path/to/state --ceiling '{}'
```

The session speaks newline-delimited JSON on stdin/stdout. After its startup
message, send `{"request_id":"1","code":"x = 41"}` and then
`{"request_id":"2","code":"x + 1"}`. Close stdin to stop it.
Keep state outside the workspace. The plain Julia API above does not create an
OS sandbox; the supervised host does.

## Features

- Persistent bindings, functions, types, packages, and workspace files.
- Whole-call parsing before execution, bounded output, deadlines, and process cleanup.
- Snapshots with dependency-aware reconstruction and preserved data aliases/cycles.
- Per-binding source observations, content checks, and opt-in artifact freshness.
- Host-mediated capabilities, workspace routing, and one-shot approved patches.
- A repository-owned MCP adapter for clients that support local stdio servers.

## Documentation

[Plugin installation](plugins/palette/README.md) · [Operator API](docs/operator.md) · [Installation and MCP](docs/install.md) ·
[Workspaces and patches](docs/workspaces.md) · [Authority boundaries](docs/authority.md) · [Static analysis policy](docs/static-analysis.md)

## Repository layout

| Directory | Contents |
| --- | --- |
| `src/` | Julia package and operator helpers |
| `host/` | Rust supervisor and capability broker |
| `security/` | Python adapters, launcher, installation, and process conformance tests |
| `test/` | Julia package tests and fixtures |
| `scripts/` | Session entrypoint and development checks |
| `docs/` | Public installation, API, and authority documentation |
| `plugins/` | Portable plugin manifests and assets |

Rust builds Palette's host; Python supports its adapters. Additional language
kernels and SDKs are provisioned by deployments, rather than bundled with Palette.

## Development

```sh
julia --project=. -e 'using Pkg; Pkg.test()'
cargo test --manifest-path host/Cargo.toml --locked
python3 scripts/test_julia_analyzer.py
node scripts/check-test-policy.mjs
```

For the complete Linux process conformance gates, prepare a Julia environment
with this checkout plus JSON, CSV, DataFrames, EzXML, and IJulia, then run:

```sh
python3 security/verify_operator.py --project-dir /absolute/path/to/test-env --implementation both
```

CI runs package, host, Jupyter integration, workspace/patch, and process gates.
The package manifest declares Julia 1.10+; supervised development and CI are tested on Julia 1.12.

## License

MIT. See [LICENSE](LICENSE).
