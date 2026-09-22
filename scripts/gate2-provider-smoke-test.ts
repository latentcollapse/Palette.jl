/**
 * Gate 2 prerequisite: prove the OpenRouter provider path works end to end
 * with the fixed model NIRA_PRIME_GATE2_PREREGISTRATION.md will pin, BEFORE
 * any NeuraBash involvement and BEFORE Gate 2 itself.
 *
 * This is NOT Gate 2. It proves plumbing, not chassis competence: auth
 * resolves, the fixed model id is actually what answers, streaming works,
 * a real (non-faux) model can decode and execute a real tool call and see
 * its result, and the session closes cleanly. No NeuraBash tool is active
 * here — the second prompt uses the "rlm" host tool (harmless, read-only
 * "list" action, always registered regardless of substrate) specifically
 * because it requires zero setup and has zero side effects, so a tool-call
 * failure here can only mean the provider/tool-call path is broken, not
 * that the task was unsafe or expensive.
 *
 * Usage:
 *   npx tsx scripts/gate2-provider-smoke-test.ts
 *
 * Requires OPENROUTER_API_KEY resolvable via the normal AuthStorage path
 * (an "openrouter" entry in auth.json, or the OPENROUTER_API_KEY env var
 * picked up by the standard provider-config fallback) -- never printed,
 * never logged, never written anywhere by this script.
 */
import { getModel } from "@earendil-works/pi-ai";
import { getAgentDir } from "../packages/coding-agent/src/config.js";
import { AuthStorage } from "../packages/coding-agent/src/core/auth-storage.js";
import { ModelRegistry } from "../packages/coding-agent/src/core/model-registry.js";
import { createAgentSession } from "../packages/coding-agent/src/core/sdk.js";
import { SessionManager } from "../packages/coding-agent/src/core/session-manager.js";
import { SettingsManager } from "../packages/coding-agent/src/core/settings-manager.js";
import { DefaultResourceLoader } from "../packages/coding-agent/src/core/resource-loader.js";

const FIXED_PROVIDER = "openrouter";
const FIXED_MODEL_ID = "cohere/north-mini-code:free";

function fail(message: string, code: number): never {
	console.error(`[gate2-smoke] FAIL: ${message}`);
	process.exit(code);
}

const cwd = process.cwd();
const agentDir = getAgentDir();
const authStorage = AuthStorage.create();
const modelRegistry = ModelRegistry.create(authStorage);
const settingsManager = SettingsManager.create(cwd, agentDir);
const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
await resourceLoader.reload();

const model = getModel(FIXED_PROVIDER, FIXED_MODEL_ID);
if (!model) {
	fail(`getModel("${FIXED_PROVIDER}", "${FIXED_MODEL_ID}") returned nothing -- model not in the pi-ai catalog.`, 69);
}
if (model.provider !== FIXED_PROVIDER || model.id !== FIXED_MODEL_ID) {
	fail("Resolved model does not match the fixed target -- refusing to run an unpinned smoke test.", 70);
}

const authStatus = modelRegistry.getProviderAuthStatus(FIXED_PROVIDER);
if (authStatus.source === "none" || authStatus.source === "stale" || authStatus.label === "expired") {
	fail(
		`No usable OpenRouter credential (status: ${JSON.stringify(authStatus)}). ` +
			"Configure an 'openrouter' entry in auth.json or set OPENROUTER_API_KEY before running this.",
		69,
	);
}

console.log(`[gate2-smoke] fixed model: ${model.provider}/${model.id}`);
console.log(`[gate2-smoke] baseUrl: ${model.baseUrl}`);
console.log(`[gate2-smoke] auth status: source=${authStatus.source} label=${authStatus.label ?? "(none)"}`);

const { session } = await createAgentSession({
	cwd,
	agentDir,
	authStorage,
	modelRegistry,
	settingsManager,
	resourceLoader,
	model,
	sessionManager: SessionManager.create(cwd, agentDir),
	baseToolsOverride: {}, // NEURA mode: no ipython kernel constructed, matches Gate 2's actual configuration
	initialActiveToolNames: ["rlm"],
	includeGoals: false,
});

console.log(`[gate2-smoke] session model reports: ${session.model?.provider}/${session.model?.id}`);
if (session.model?.provider !== FIXED_PROVIDER || session.model?.id !== FIXED_MODEL_ID) {
	fail("Session's own reported model does not match the fixed target after construction.", 70);
}
if (session.getToolDefinition("ipython") !== undefined) {
	fail("ipython tool definition is present -- NEURA mode did not take effect for this smoke test.", 70);
}
console.log("[gate2-smoke] confirmed: no ipython tool definition (NEURA mode active)");

let sawStreamedText = false;
session.subscribe((event) => {
	if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
		sawStreamedText = true;
		process.stdout.write(event.assistantMessageEvent.delta);
	}
});

console.log("\n[gate2-smoke] --- prompt 1: plain text ---");
await session.prompt("Reply with exactly this text and nothing else: SMOKE_TEST_OK");

const lastText1 = session.getLastAssistantText();
console.log(`\n[gate2-smoke] last assistant text: ${JSON.stringify(lastText1)}`);
if (!sawStreamedText) fail("No text_delta events observed -- streaming path did not fire.", 71);
if (!lastText1?.includes("SMOKE_TEST_OK")) fail("Model did not echo the requested marker text.", 71);

console.log("\n[gate2-smoke] --- prompt 2: real tool call (rlm 'list', harmless/read-only) ---");
await session.prompt(
	"Call the rlm tool with action=\"list\" to check the current subagent roster, then tell me in one sentence how many subagents it found.",
);

const toolCalls = session.messages.filter(
	(m) => m.role === "assistant" && Array.isArray(m.content) && m.content.some((c) => c.type === "toolCall" && c.name === "rlm"),
);
const toolResults = session.messages.filter((m) => m.role === "toolResult");
console.log(`[gate2-smoke] rlm tool calls observed: ${toolCalls.length}`);
console.log(`[gate2-smoke] tool results observed: ${toolResults.length}`);
if (toolCalls.length === 0) fail("Model never attempted the rlm tool call -- tool-call decoding/offer path unproven.", 72);
if (toolResults.length === 0) fail("No tool result message was recorded -- tool execution/result-return path unproven.", 72);
const failedResult = toolResults.find((m) => m.role === "toolResult" && m.isError);
if (failedResult) fail(`Tool call returned an error result: ${JSON.stringify(failedResult)}`, 72);

console.log(`[gate2-smoke] last assistant text: ${JSON.stringify(session.getLastAssistantText())}`);

await session.disposeAsync();
console.log("\n[gate2-smoke] session disposed cleanly.");
console.log("[gate2-smoke] PASS: provider path (auth, fixed model, streaming, real tool call/result) verified.");
