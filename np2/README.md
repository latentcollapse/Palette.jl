# NP2 saves (NIRA-Prime with NeuraJL)

NP2 is a fork of [PrimeIntellect-ai/prime-agent](https://github.com/PrimeIntellect-ai/prime-agent) with NeuraJL as its operator surface. Its remote belongs to someone else and is never pushed to. The local work lives here as patch series against public upstream commits.

| Series | Branch | Upstream base | Patches |
|---|---|---|---|
| `patches/operator-surface-neurajl/` | `operator-surface/neurajl` (main line; contains `nira-prime/base`) | `298cf406e446aa5e7205af9a108c45762f3ba380` | 45 |
| `patches/battleground-neurajl/` | `battleground/neurajl` (earlier line, diverged) | `e311d6495124cf0bdc629c813fc97a39a9a3054d` | 10 |

## Restore

```sh
git clone https://github.com/PrimeIntellect-ai/prime-agent.git np2 && cd np2
git checkout -b operator-surface/neurajl 298cf406e446aa5e7205af9a108c45762f3ba380
git am /path/to/neurajl-operator-lab/np2/patches/operator-surface-neurajl/*.patch
```

For the other line, use the other base and series.

**Verified 2026-09-28.** Each series was applied to a clean checkout of its base with `git am`. The resulting tree was identical to the real branch tip, file for file. `git am` warns about whitespace; that is expected.

## Left out

- **Four `hlx_*.tar.gz` archives** (90 MB), committed in "capture local Prime-Agent battleground baseline" (2026-09-23). They are source snapshots of the HLX project, not NP2 code. They are excluded from the patches, so the restored tree lacks exactly these four files.
- **A full git bundle** of all three branches, archives included, kept locally: `~/.neurajl-runs/backups/np2-branches-2026-09-28.bundle`.
- **`scripts/abc-agent.ts`** has uncommitted changes. That file is Codex's and is not included.

The patches were scanned for key patterns (OpenAI, OpenRouter, GitHub, AWS, Slack, private keys): none found.
