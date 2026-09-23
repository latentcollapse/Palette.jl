/** One scored A/B/C trial. The task fixture is process.cwd(). */
import { readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import type { Model } from "@earendil-works/pi-ai";
import { AuthStorage } from "../packages/coding-agent/src/core/auth-storage.js";
import { ModelRegistry } from "../packages/coding-agent/src/core/model-registry.js";
import { DefaultResourceLoader } from "../packages/coding-agent/src/core/resource-loader.js";
import { createAgentSession } from "../packages/coding-agent/src/core/sdk.js";
import { SessionManager } from "../packages/coding-agent/src/core/session-manager.js";
import { SettingsManager } from "../packages/coding-agent/src/core/settings-manager.js";
import { createModelRequestBudget } from "../packages/coding-agent/src/core/model-request-budget.js";
import { createNeurabashOperatorTools } from "../packages/coding-agent/src/core/tools/neurabash-session.js";

const promptFile = process.env.ABC_PROMPT_FILE;
const traceFile = process.env.ABC_TRACE_FILE;
const agentDir = process.env.ABC_AGENT_DIR;
const binPath = process.env.NEURABASH_BIN;
const rootPath = process.env.NEURABASH_ROOT;
if (!promptFile || !traceFile || !agentDir || !binPath || !rootPath) throw new Error("Missing A/B/C trial configuration");
const configuredBaseUrl = process.env.ABC_BASE_URL;
const localBaseUrl = configuredBaseUrl && !configuredBaseUrl.includes("openrouter.ai") ? configuredBaseUrl : undefined;
const requestBaseUrl = configuredBaseUrl ?? "https://openrouter.ai/api/v1";
const modelId = process.env.ABC_MODEL ?? "cohere/north-mini-code:free";
if (!localBaseUrl && modelId !== "cohere/north-mini-code:free") throw new Error("OpenRouter condition requires the pinned model");
const model: Model<"openai-completions"> = {
	id: modelId,
	name: modelId,
	api: "openai-completions",
	provider: localBaseUrl ? "local-llamacpp" : "openrouter",
	baseUrl: requestBaseUrl,
	reasoning: false,
	input: ["text"],
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
	contextWindow: localBaseUrl ? 8192 : 256000,
	maxTokens: 2048,
	compat: {
		supportsDeveloperRole: false,
		maxTokensField: "max_tokens",
		...(localBaseUrl ? {} : { openRouterRouting: { only: ["cohere"], allow_fallbacks: false } }),
	},
};

const cwd = process.cwd();
const retryPolicy = {
	enabled: true,
	maxRetries: 3,
	baseDelayMs: 2000,
	jitter: false,
	provider: {
		timeoutMs: 180000,
		maxRetryDelayMs: 12000,
		waitForUsage: { enabled: false },
	},
};
const compactionSettings = localBaseUrl
	? { enabled: true, reserveTokens: 2560, keepRecentTokens: 3072 }
	: { enabled: true, reserveTokens: 2560, keepRecentTokens: 16000 };
const toolTimeoutMs = 60000;
writeFileSync(`${agentDir}/settings.json`, `${JSON.stringify({ retry: retryPolicy, compaction: compactionSettings }, null, 2)}\n`);
const keyFile = process.env.ABC_OPENROUTER_KEY_FILE;
let openRouterKey = keyFile ? readFileSync(keyFile, "utf8").trim() : undefined;
delete process.env.ABC_OPENROUTER_KEY_FILE;
if (keyFile) unlinkSync(keyFile);
if (!localBaseUrl && !openRouterKey) throw new Error("OpenRouter key was not provided to the trial process");
const authStorage = AuthStorage.inMemory();
if (localBaseUrl) authStorage.setRuntimeApiKey("local-llamacpp", "local");
else if (openRouterKey) authStorage.setRuntimeApiKey("openrouter", openRouterKey);
openRouterKey = undefined;
const modelRegistry = ModelRegistry.create(authStorage);
const settingsManager = SettingsManager.create(cwd, agentDir);
const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
await resourceLoader.reload();
const started = Date.now();
const modelRequestBudget = createModelRequestBudget(60);
const sessionManager = SessionManager.inMemory(cwd);
const { session } = await createAgentSession({
	cwd,
	agentDir,
	authStorage,
	modelRegistry,
	settingsManager,
	resourceLoader,
	model,
	sessionManager,
	baseToolsFactory: createNeurabashOperatorTools(cwd, {
		binPath,
		rootPath,
		profile: "workspace",
		timeoutMs: toolTimeoutMs,
	}),
	initialActiveToolNames: ["neurabash", "neurabash_session"],
	allowedToolNames: ["neurabash", "neurabash_session"],
	includeGoals: false,
	modelRequestBudget,
});
let error: string | undefined;
let assistantCalls = 0;
const persistTrace = () => {
	const temporaryTraceFile = `${traceFile}.tmp`;
	writeFileSync(
		temporaryTraceFile,
		JSON.stringify(
			{
				stack: "nira-neurabash",
				model: `${model.provider}/${model.id}`,
				started,
				ended: Date.now(),
				retryPolicy,
				contextPolicy: { contextWindow: model.contextWindow, maxOutputTokens: model.maxTokens, compaction: compactionSettings },
				routePolicy: localBaseUrl ? null : { only: ["cohere"], allow_fallbacks: false },
				toolTimeoutMs,
				modelRequestBudget,
				activeTools: session.getActiveToolNames(),
				assistantCalls,
				messages: session.messages,
				rawSessionEntries: sessionManager.getBranch(),
				error,
			},
			null,
			2,
		),
	);
	renameSync(temporaryTraceFile, traceFile);
};
const unsubscribe = session.subscribe((event) => {
	if (event.type === "message_end" && event.message.role === "assistant") {
		assistantCalls += 1;
	}
	if (event.type === "message_end") persistTrace();
});
try {
	if (session.getToolDefinition("ipython")) throw new Error("IPython leaked into NeuraBash condition");
	await session.prompt(readFileSync(promptFile, "utf8"));
} catch (cause) {
	error = cause instanceof Error ? cause.message : String(cause);
} finally {
	unsubscribe();
	await session.disposeAsync();
	persistTrace();
}
if (error) {
	console.error(error);
	process.exitCode = 1;
}
