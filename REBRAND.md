# Rebrand plan: from inherited names to Cyan

**Done (2026-09-28):**
- **README.** It states that NIRA is a fork and refactor of Prime Agent (Prime Intellect), which is built on Mario Zechner's `pi`, and it credits both.
- **LICENSE.** It keeps both upstream copyright notices, as the MIT License requires, and adds the fork's own.
- **Model-facing prompts.** They no longer tell the model it is "Prime Agent" (`core/refinement/refinement.ts`).

**Not renamed, on purpose:**
- **Prime Intellect's inference service** is a model provider that the harness supports: `PRIME_API_KEY`, `PRIME_INFERENCE_PROVIDER_ID` and `primeintellect.ai`. Its name is a fact about that provider, not this product's identity.
- **Links to upstream issues and pull requests** in comments and docs are provenance. They say where a behaviour came from.

## The compatibility surfaces (one migration, when the Cyan name takes effect)

All of these derive from `packages/coding-agent/package.json` → `piConfig` and `src/config.ts`:

| Surface | Today | Derived from |
|---|---|---|
| Command, and its name in messages | `prime-agent` (`Run: prime-agent update`, …) | `APP_NAME = piConfig.name` |
| Config directory | `~/.prime/agent` | `CONFIG_DIR_NAME = piConfig.configDir` |
| Environment variables | `PRIME_AGENT_CODING_AGENT_DIR`, `PRIME_AGENT_SESSION_DIR`, … | `envPrefix`, from `APP_NAME` |
| Launcher and installer | `prime-agent.sh`, `install.sh` (installs upstream releases) | files |
| Runtime directory | `prime-agent-runtime/` (the Python RLM shim, used only by the IPython tool) | the build's copy-assets |
| npm workspace names | `@earendil-works/pi-*` | the manifests |

**Order:**
1. **Set `piConfig.name` and `configDir`** to the new name. This changes the command, the messages and the environment prefix together.
2. **Keep reading the old locations.** On first start, if `~/.prime/agent` exists and the new directory does not, use or migrate it. Read the new environment variables first, then fall back to the old `PRIME_AGENT_*` ones, so existing configurations keep working.
3. **Point `install.sh` at this project's releases,** or remove it until there are releases. Today it installs upstream Prime Agent.
4. **Rename `prime-agent.sh`,** keeping a thin alias for one release.
5. **Leave `@earendil-works/pi-*` alone.** These are internal workspace names that nobody installs, so a rename buys nothing.
6. **Run the full check (`npm run check`) and the test suite after each step.** User-visible strings are asserted in tests, so update those together with the change.
