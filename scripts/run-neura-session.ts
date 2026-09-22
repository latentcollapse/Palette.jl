/**
 * Gate 2 driver: launch a real Prime Agent session in NEURA mode.
 *
 * This is deliberately not a permanent CLI flag. baseToolsOverride takes
 * actual AgentTool instances, and Prime's CLI args are string/boolean flags
 * with no existing pattern for passing objects through — threading a
 * research-only mode through that whole pipeline would be exactly the kind
 * of infrastructure-before-evidence this project has been careful to avoid
 * today. This script calls the real createAgentSession entry point
 * directly instead.
 *
 * Usage:
 *   NEURABASH_BIN=/path/to/build/bin/neurabash \
 *     npx tsx scripts/run-neura-session.ts "your task prompt" [--profile workspace|readonly|sandbox]
 *
 * What this actually exercises, matching CHASSIS_DECISION_PLAN_2026-09-21.md
 * Gate 2: no ipython kernel constructed (baseToolsOverride), no
 * REPL_CONTROL_PROMPT doctrine (hasIpython computed from the real active
 * tool list), goals off (includeGoals: false — an active goal in this mode
 * throws rather than silently degrading, see agent-session.ts). Each call
 * to the neurabash tool is still ephemeral (Gate 3, NeuraBash-side
 * persistent session client, is not built yet) — report results as
 * "ephemeral NeuraBash vs. persistent IPython", not unqualified, per the
 * plan's named confound.
 */
import { getAgentDir } from "../packages/coding-agent/src/config.js";
import { AuthStorage } from "../packages/coding-agent/src/core/auth-storage.js";
import { ModelRegistry } from "../packages/coding-agent/src/core/model-registry.js";
import { createAgentSession } from "../packages/coding-agent/src/core/sdk.js";
import { createNeurabashTool } from "../packages/coding-agent/src/core/tools/neurabash.js";
import { SessionManager } from "../packages/coding-agent/src/core/session-manager.js";
import { SettingsManager } from "../packages/coding-agent/src/core/settings-manager.js";
import { findInitialModel } from "../packages/coding-agent/src/core/model-resolver.js";
import { DefaultResourceLoader } from "../packages/coding-agent/src/core/resource-loader.js";

const args = process.argv.slice(2);
const profileIdx = args.indexOf("--profile");
const profile = profileIdx >= 0 ? (args[profileIdx + 1] as "workspace" | "readonly" | "sandbox") : "workspace";
const promptText = args.filter((a, i) => a !== profile && i !== profileIdx).join(" ").trim();

if (!promptText) {
	console.error('Usage: npx tsx scripts/run-neura-session.ts "task prompt" [--profile workspace|readonly|sandbox]');
	process.exit(64);
}

if (!process.env.NEURABASH_BIN) {
	console.error(
		"NEURABASH_BIN is not set. This is a real Gate 2 prerequisite, not an implementation detail:" +
			" if it's unset, neurabash.ts fails closed with a text error, and a model that handles that" +
			" gracefully would pass the letter of the test while NeuraBash never actually ran. Set it to" +
			" a real built binary before counting this run.",
	);
	process.exit(69);
}

const cwd = process.cwd();
const agentDir = getAgentDir();
const authStorage = AuthStorage.create();
const modelRegistry = ModelRegistry.create(authStorage);
const settingsManager = SettingsManager.create(cwd, agentDir);
const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
await resourceLoader.reload();

const { model } = await findInitialModel({ modelRegistry, settingsManager });
if (!model) {
	console.error("No model available. Configure a provider (see packages/coding-agent/docs/providers.md) first.");
	process.exit(69);
}

console.log(`[run-neura-session] model=${model.provider}/${model.id} profile=${profile} cwd=${cwd}`);

const { session } = await createAgentSession({
	cwd,
	agentDir,
	authStorage,
	modelRegistry,
	settingsManager,
	resourceLoader,
	model,
	sessionManager: SessionManager.create(cwd, agentDir),
	baseToolsOverride: { neurabash: createNeurabashTool(cwd, { profile }) },
	initialActiveToolNames: ["neurabash"],
	includeGoals: false,
});

console.log(`[run-neura-session] active tools: ${session.getActiveToolNames().join(", ")}`);
console.log(`[run-neura-session] ipython tool definition present: ${session.getToolDefinition("ipython") !== undefined}`);

session.subscribe((event) => {
	if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
		process.stdout.write(event.assistantMessageEvent.delta);
	}
});

await session.prompt(promptText);

console.log("\n\n[run-neura-session] --- transcript ---");
for (const msg of session.messages) {
	console.log(JSON.stringify(msg, null, 2));
}
