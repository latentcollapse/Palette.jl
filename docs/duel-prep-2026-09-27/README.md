# Duel prep, step 1: environment parity (2026-09-27)

The duel is NeuraJL against the steelmanned IPython arm, on a polyglot repo (Rust, TypeScript, OCaml, SQL, shell). Both arms must reach the same toolchains, or the duel measures the environment instead of the operator surface.

## Before

`probe/toolchain_probe.py` was run inside a NeuraJL kernel:
- `cargo` and `rustc` are the rustup shim, and fail with "no default is configured", because `HOME` is `/run/neurajl/home`.
- `PATH` is `/usr/bin:/bin` plus Julia.
- `tsc`, `ocaml`, `dune` and `psql` are unreachable.
- There is no network.
- `whoami` and `id -un` fail, because there is no passwd entry for uid 1000.

`probe/ipython_probe.mts` runs code through Prime-Agent-Control's real IPython tool, with no model. In the environment the A/B/C runner gives it (host `PATH`, a per-trial `HOME`):
- the same rustup failure;
- no `tsc` and no `dune`;
- but the whole host `PATH` and network access.

Neither arm could build the duel's languages. They also differed in ways that would have skewed the result.

## The parity design

1. **One toolchain**, pinned by `toolchain/pixi.lock` and built into `~/.neurajl-runs/toolchains/polyglot` (3.2 GB, conda-forge):
   - rust with cargo, nodejs with typescript, ocaml with dune and findlib, postgresql, sqlite, python, go, git, make;
   - `bin` links to the environment's `bin`;
   - `task-env` holds the environment's activation (`OCAMLLIB`, `GOROOT`, `CONDA_PREFIX`, …) as `KEY=VALUE` lines. It is data, not shell: load it, do not `source` it, because its values contain spaces.
2. **NeuraJL** (lab `a368608`):
   - `NIRA_TASK_TOOLS` mounts the toolchain read-only and puts it first on `PATH`; this was already there.
   - `NIRA_TASK_ENV` is new: it sets the activation, except for the variables the sandbox owns (`PATH`, `HOME`, `USER`, `JULIA_*`, …).
   - A passwd and group entry for uid 1000 (`neura`), plus `USER` and `LOGNAME`.
   - Test: `test_task_environment_and_a_named_user_reach_the_kernel`, covering the persistent kernel and ephemeral children.
3. **The IPython arm** (`probe/parity_env.py`):
   - The driver process gets `PATH=<toolchain>/bin:/usr/bin:/bin`, the same activation, `USER`/`LOGNAME=neura`, and `PRIME_AGENT_KERNEL_PYTHON`. Without the last one, the kernel runtime is not found once `PATH` is minimal.
   - The driver must be started with the **host `node` by absolute path**; otherwise the toolchain's Node 26.10 replaces the host's 26.8.2.

## After

`probe/build_script.sh` builds and runs each language. It was run in both arms, through the arms' own tools:

| | Rust (cargo) | TypeScript (tsc + node) | OCaml (dune) | SQLite | Go | PostgreSQL (initdb, server, psql) |
|---|---|---|---|---|---|---|
| NeuraJL | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| IPython arm | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Lab suites on `a368608`: revival 28, session_cli 51, session 12, authority 27, Julia `Pkg.test`, all passing.

## Remaining parity rules for the duel harness

- **Temporary files.** NeuraJL's `/tmp` is private to each session. The IPython kernel is unsandboxed, so it uses the host `/tmp`, which is shared and persists across trials; a leftover `/tmp/pg` from one probe broke the next. Give the IPython arm its own `TMPDIR` per trial, clear it afterwards, and keep hardcoded `/tmp` paths out of the duel repo.
- **Network.** NeuraJL has none by default, and the IPython arm has the host's. Choose one policy for both:
  - both offline, with dependencies vendored: fairest, but the IPython kernel cannot easily be cut off without breaking its localhost channel;
  - both online: NP2 already supports `network: true`.
- **Identity.** In the IPython arm `USER` is `neura` but `whoami` is `mattc`, because it runs under the real uid. That is cosmetic, unless the repo reads the username.
- **Same limits for both arms:** a 60 s call limit, unless both get the same per-call timeout (step 3), and a 12,000-character output cap.
