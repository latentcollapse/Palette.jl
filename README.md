# Cyan

**Cyan** is an agent harness whose model works in a persistent, sandboxed
**Julia** kernel — including recursive sub-agents started from Julia code — with
no IPython kernel and no Python privilege layer between the model and the
chassis.

Cyan is a fork and refactor of [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent)
by Prime Intellect, which is itself built on Mario Zechner's
[`pi`](https://github.com/earendil-works/pi). Their agent loop, sessions and
compaction, provider layer, RLM orchestration and terminal interface are the
chassis Cyan keeps. Thank you to Prime Intellect and to Mario Zechner for that
work, and for releasing it under the MIT License.

---

## What it is

| Layer | Language | Responsibility |
| --- | --- | --- |
| Agent chassis | TypeScript | Agent loop, sessions, compaction, providers, RLM orchestration, TUI |
| **Palette** operator surface | Julia | The model's execution environment: a persistent kernel with symbolic state |
| Palette host | Rust | Sandbox launcher, persistent session supervisor, capability broker |
| Broker & launch | Python | Capability negotiation, bwrap isolation, depot prewarm |

The agent is **Cyan**. The execution surface it drives is **Palette**. Colors go
on a palette.

## The Palette operator surface

The model's code tool is `palette`: a persistent Julia kernel in a bubblewrap
sandbox whose state survives kernel death and compaction, with authority
mediated by a host-side capability broker.

- **Bindings outlive the call.** A result bound in call *n* is still bound in
  call *n+1*. The model stops re-deriving what it already knows.
- **State survives the kernel dying.** A dead kernel revives what it can from
  saved state and reports exactly what was restored, rebuilt, or lost.
- **Sub-agents from Julia.** `Neura.rlm.spawn`, `collect`, `list_subagents`,
  `find_models`, `progress_note`, `delete_subagent` and `create_session` reach
  the chassis's RLM orchestration through the kernel's broker. The permission is
  off unless the session's ceiling names it.
- **Authority is explicit.** Competence is not authorization. The broker
  mediates every capability; nothing self-grants.

### Layout

```
packages/coding-agent/    agent chassis (TypeScript)
  src/core/tools/palette.ts    the operator surface as the model sees it
src/                    Neura — the Julia package (kernel session, revival, RLM)
host/                   palette-host — Rust sandbox, session, capability broker
security/               Python broker, session CLI, bwrap launcher, prewarm
np2/patches/            the patch chain that implants the surface into the chassis
drivers/                scored experiment drivers
research/workloads/     benchmarks and the controls they are graded against
docs/                   architecture, experiments, gap registers
```

### Configuration

| Variable | Purpose |
| --- | --- |
| `PALETTE_SESSION_CLI` | Path to `security/session_cli.py` |
| `PALETTE_PROJECT_DIR` | Checkout the kernel runs against |
| `PALETTE_HOST_BIN` | Path to the `palette-host` binary (optional) |
| `PALETTE_PAYLOAD_PARTS` | `0` restores the single-string payload form for an A/B |
| `PALETTE_WORKSPACE_MAP` | `0` turns off the post-compaction workspace map |
| `PALETTE_OUTPUT_DIGEST` | `0` turns off the error digest on long failing output |
| `PALETTE_COMPACTION_NOTE` | `0` turns off the state note after compaction |

## Requirements

- **Node.js 22.8.0+** — chassis
- **Julia 1.12+** — operator surface
- **bubblewrap (`bwrap`)** — sandbox isolation
- **Python 3** — broker and launcher

## Build and run

```bash
npm ci
npm run build
./prime-agent.sh
```

## Tests

```bash
npm test                                    # chassis (vitest)
cd packages/coding-agent
npx vitest run test/suite/palette-substrate-modes.test.ts   # live kernel integration
```

The Palette Julia package:

```bash
julia --project=. -e 'using Pkg; Pkg.test()'
```

## Names still inherited from upstream

The command (`prime-agent`), the config directory (`~/.prime/agent`),
`PRIME_AGENT_*` environment variables and package names are compatibility
surfaces: renaming them breaks existing installs and configuration, so they move
in one staged migration when the Cyan name takes full effect (see
[`REBRAND.md`](REBRAND.md)). Prime Intellect's inference service remains
available as a model provider under its own name.

## Upstream documentation

The upstream documentation still applies to the chassis: [usage](packages/coding-agent/docs/usage.md),
[long-running agents](packages/coding-agent/docs/long-running-agents.md),
[RLM](packages/coding-agent/docs/rlm.md), [providers](packages/coding-agent/docs/providers.md),
[architecture](packages/coding-agent/docs/architecture.md).

## License

MIT; see [LICENSE](LICENSE). The copyright notices of Mario Zechner and Prime
Intellect are kept, as the license requires.

## Citing the upstream work

```bibtex
@article{karten2026prime,
  title={Prime Agent: A Self-Improving RLM Harness},
  author={Karten, Seth and Zhang, Alex L. and Thomas, Kevin and M{\"u}ller, Sebastian and Bakouch, Elie and Auras, Daniel and Senghaas, Mika and Obeid, Fares and Dunas, Konstantin and Hagemann, Johannes and Jaghouar, Sami},
  journal={arXiv preprint arXiv:2608.23552},
  year={2026}
}
```
