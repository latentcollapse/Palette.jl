# NIRA

NIRA is an agent harness whose model works in a persistent, sandboxed **Julia** environment ([Palette](https://github.com/latentcollapse/palette-operator-lab)), including recursive sub-agents started from Julia code, with no IPython kernel and no Python privilege layer between the model and the chassis. "NIRA" is the working name during Project NIRA; the finished system will be called **Cyan**.

**NIRA is a fork and refactor of [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent)** by Prime Intellect, which is itself built on Mario Zechner's [`pi`](https://github.com/earendil-works/pi). Their agent loop, sessions and compaction, provider layer, RLM orchestration and terminal interface are the chassis NIRA keeps. Thank you to Prime Intellect and to Mario Zechner for that work, and for releasing it under the MIT License.

## What NIRA changes

- **Julia operator surface.** The model's code tool is Palette: a persistent Julia kernel in a bubblewrap sandbox whose state survives kernel death and compaction, with authority mediated by a host-side capability broker. See `packages/coding-agent/src/core/tools/palette.ts`.
- **Sub-agents from Julia.** `Neura.rlm.spawn`, `collect`, `list_subagents`, `find_models`, `progress_note`, `delete_subagent` and `create_session` reach the chassis's existing RLM orchestration through the kernel's broker. The permission is off unless the session's ceiling names it.
- **Harness fixes found in long runs**: compaction that could loop on stacked state notes, retry waits the provider states only in its error text, and encrypted reasoning that token estimates ignored. The research record is in the [lab repository](https://github.com/latentcollapse/palette-operator-lab).

## Names still inherited

The command (`prime-agent`), the config directory (`~/.prime/agent`), `PRIME_AGENT_*` environment variables and package names are compatibility surfaces: renaming them breaks existing installs and configuration, so they move in one staged migration when the Cyan name takes effect (see `REBRAND.md`). Prime Intellect's inference service remains available as a model provider under its own name.

## Build and run from source

Node.js 22.8.0 or newer:

```bash
npm ci
cd /path/to/project
/path/to/this/repo/prime-agent.sh
```

Palette needs `bwrap`, Julia 1.12 and the lab checkout; see the lab repository's README.

## Upstream documentation

The upstream documentation still applies to the chassis: [usage](packages/coding-agent/docs/usage.md), [long-running agents](packages/coding-agent/docs/long-running-agents.md), [RLM](packages/coding-agent/docs/rlm.md), [providers](packages/coding-agent/docs/providers.md), [architecture](packages/coding-agent/docs/architecture.md).

## License

MIT; see [LICENSE](LICENSE). The copyright notices of Mario Zechner and Prime Intellect are kept, as the license requires.

## Citing the upstream work

```bibtex
@article{karten2026prime,
  title={Prime Agent: A Self-Improving RLM Harness},
  author={Karten, Seth and Zhang, Alex L. and Thomas, Kevin and Müller, Sebastian and Bakouch, Elie and Auras, Daniel and Senghaas, Mika and Obeid, Fares and Dunas, Konstantin and Hagemann, Johannes and Jaghouar, Sami},
  journal={arXiv preprint arXiv:2608.23552},
  year={2026}
}
```
