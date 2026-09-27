/** One scored D (NeuraJL) trial. The task fixture is process.cwd(). */
import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import type { AssistantMessage, Model } from "@earendil-works/pi-ai";
import { AuthStorage } from "../packages/coding-agent/src/core/auth-storage.js";
import { ModelRegistry } from "../packages/coding-agent/src/core/model-registry.js";
import { DefaultResourceLoader } from "../packages/coding-agent/src/core/resource-loader.js";
import { createAgentSession } from "../packages/coding-agent/src/core/sdk.js";
import { SessionManager } from "../packages/coding-agent/src/core/session-manager.js";
import { SettingsManager } from "../packages/coding-agent/src/core/settings-manager.js";
import { createModelRequestBudget } from "../packages/coding-agent/src/core/model-request-budget.js";
import { createNeurajlBaseToolsFactory } from "../packages/coding-agent/src/core/tools/neurajl.js";

const promptFile = process.env.ABC_PROMPT_FILE;
const traceFile = process.env.ABC_TRACE_FILE;
const agentDir = process.env.ABC_AGENT_DIR;
const rlmSessionDir = process.env.ABC_RLM_SESSION_DIR;
const sessionCliPath = process.env.NEURAJL_SESSION_CLI;
const projectDir = process.env.NEURAJL_PROJECT_DIR;
const repoDir = process.env.NEURAJL_REPO_DIR;
const maxOutputChars = Number(process.env.ABC_NEURAJL_MAX_OUTPUT_CHARS);
if (!promptFile || !traceFile || !agentDir || !rlmSessionDir || !sessionCliPath || !projectDir || !repoDir) {
	throw new Error("Missing A/B/C trial configuration");
}
if (!Number.isSafeInteger(maxOutputChars) || maxOutputChars <= 0) throw new Error("Invalid NeuraJL output cap");
const configuredBaseUrl = process.env.ABC_BASE_URL;
const modelId = process.env.ABC_MODEL ?? "nvidia/nemotron-3-ultra-550b-a55b:free";
const requestedProvider = process.env.ABC_MODEL_PROVIDER;
const requestedApi = process.env.ABC_MODEL_API;
const directOpenAI = requestedProvider === "openai" || requestedApi === "openai-responses" || modelId === "gpt-6-luna";
const openRouterLuna = modelId === "openai/gpt-6-luna";
const luna = directOpenAI || openRouterLuna;
const localBaseUrl = configuredBaseUrl && !configuredBaseUrl.includes("openrouter.ai") && !directOpenAI && !openRouterLuna
	? configuredBaseUrl
	: undefined;
const requestBaseUrl = configuredBaseUrl ?? (directOpenAI ? "https://api.openai.com/v1" : "https://openrouter.ai/api/v1");
const routeProvider = process.env.ABC_OPENROUTER_PROVIDER;
const contextWindow = Number(process.env.ABC_CONTEXT_WINDOW ?? (localBaseUrl ? 16_384 : 256_000));
const maxOutputTokens = Number(process.env.ABC_MAX_OUTPUT_TOKENS ?? (localBaseUrl ? 2048 : 65_536));
const modelProvider = localBaseUrl ? "local-llamacpp" : directOpenAI ? "openai" : "openrouter";
const modelApi = localBaseUrl ? "openai-completions" : directOpenAI ? "openai-responses" : "openai-completions";
const reasoningEffort = process.env.ABC_REASONING_EFFORT ?? (luna ? "max" : undefined);
const serviceTier = process.env.ABC_SERVICE_TIER ?? (luna ? "default" : undefined);
if (!Number.isSafeInteger(maxOutputTokens) || maxOutputTokens <= 0 || maxOutputTokens >= contextWindow) {
	throw new Error("Invalid A/B/C output token limit");
}
const ipythonMaxOutputChars = Number(process.env.ABC_IPYTHON_MAX_OUTPUT_CHARS ?? 12_000);
if (directOpenAI && modelId !== "gpt-6-luna") throw new Error("Direct OpenAI condition requires the frozen gpt-6-luna model");
if (directOpenAI && requestedProvider && requestedProvider !== "openai") throw new Error("Direct Luna condition requires provider openai");
if (directOpenAI && requestedApi && requestedApi !== "openai-responses") throw new Error("Direct Luna condition requires API openai-responses");
if (openRouterLuna && requestedProvider && requestedProvider !== "openrouter") throw new Error("OpenRouter Luna condition requires provider openrouter");
if (openRouterLuna && requestedApi && requestedApi !== "openai-completions") throw new Error("OpenRouter Luna condition requires API openai-completions");
if (luna && reasoningEffort !== "max") throw new Error("Luna condition requires reasoning effort max");
if (luna && serviceTier !== "default") throw new Error("Luna condition requires service tier default");
if (!localBaseUrl && !luna && modelId !== "nvidia/nemotron-3-ultra-550b-a55b:free") {
	throw new Error("OpenRouter condition requires the selected Nemotron free model");
}
if (!Number.isSafeInteger(contextWindow) || contextWindow <= 2048) throw new Error("Invalid A/B/C context window");
if (!Number.isSafeInteger(ipythonMaxOutputChars) || ipythonMaxOutputChars <= 0) throw new Error("Invalid IPython output cap");
const lunaThinkingLevelMap = {
	off: "none",
	minimal: "minimal",
	low: "low",
	medium: "medium",
	high: "high",
	xhigh: "xhigh",
	max: "max",
};
const model: Model<any> = {
	id: modelId,
	name: modelId,
	api: modelApi,
	provider: modelProvider,
	baseUrl: requestBaseUrl,
	reasoning: !localBaseUrl,
	input: ["text"],
	cost: luna
		? { input: 0.10, output: 0.50, cacheRead: 0.01, cacheWrite: 0.125 }
		: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
	contextWindow,
	maxTokens: maxOutputTokens,
	...(directOpenAI
		? {
				thinkingLevelMap: lunaThinkingLevelMap,
				compat: { sendSessionIdHeader: false, supportsLongCacheRetention: true },
			}
		: {
				...(openRouterLuna ? { thinkingLevelMap: lunaThinkingLevelMap } : {}),
				compat: {
					supportsDeveloperRole: false,
					...(openRouterLuna ? { supportsReasoningEffort: true } : {}),
					thinkingFormat: "openrouter",
					maxTokensField: "max_tokens",
					...(localBaseUrl || !routeProvider
						? {}
						: { openRouterRouting: { only: [routeProvider], allow_fallbacks: false } }),
				},
			}),
};
const cwd = process.cwd();
const retryPolicy = {
	enabled: true,
	maxRetries: Number(process.env.ABC_MAX_RETRIES ?? 3),
	baseDelayMs: Number(process.env.ABC_RETRY_BASE_MS ?? 2000),
	jitter: false,
	provider: {
		timeoutMs: 180000,
		maxRetryDelayMs: 12000,
		waitForUsage: { enabled: false },
	},
};
const compactionSettings = localBaseUrl
	? { enabled: true, reserveTokens: 2560, keepRecentTokens: 3072 }
	: { enabled: true, reserveTokens: maxOutputTokens + 4096, keepRecentTokens: Number(process.env.ABC_KEEP_RECENT_TOKENS ?? 16000) };
const toolTimeoutMs = 60000;
writeFileSync(`${agentDir}/settings.json`, `${JSON.stringify({ retry: retryPolicy, compaction: compactionSettings }, null, 2)}\n`);
const keyFile = directOpenAI ? process.env.ABC_OPENAI_KEY_FILE : process.env.ABC_OPENROUTER_KEY_FILE;
let providerKey = keyFile ? readFileSync(keyFile, "utf8").trim() : undefined;
delete process.env.ABC_OPENAI_KEY_FILE;
delete process.env.ABC_OPENROUTER_KEY_FILE;
if (keyFile) unlinkSync(keyFile);
if (!localBaseUrl && !providerKey) {
	throw new Error((directOpenAI ? "OpenAI" : "OpenRouter") + " key was not provided to the trial process");
}
const authStorage = AuthStorage.inMemory();
if (localBaseUrl) authStorage.setRuntimeApiKey("local-llamacpp", "local");
else if (providerKey) authStorage.setRuntimeApiKey(modelProvider, providerKey);
providerKey = undefined;
const modelRegistry = ModelRegistry.create(authStorage);
const settingsManager = SettingsManager.create(cwd, agentDir);
const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
await resourceLoader.reload();
const started = Date.now();
const modelRequestBudget = createModelRequestBudget(Number(process.env.ABC_MAX_REQUESTS ?? 60));
const sessionManager = SessionManager.inMemory(cwd);
const { session } = await createAgentSession({
	cwd,
	agentDir,
	authStorage,
	modelRegistry,
	settingsManager,
	resourceLoader,
	model,
	thinkingLevel: luna ? "max" : undefined,
	serviceTier: luna ? "default" : undefined,
	sessionManager,
	baseToolsFactory: createNeurajlBaseToolsFactory(cwd, {
		sessionCliPath,
		projectDir,
		repoDir,
		turnTimeout: toolTimeoutMs / 1000,
		maxOutputChars,
	}),
	initialActiveToolNames: ["neurajl", "rlm"],
	allowedToolNames: ["neurajl", "rlm"],
	rlmSessionDir,
	includeGoals: true,
	modelRequestBudget,
});
const activeTools = [...session.getActiveToolNames()].sort();
let error: string | undefined;
let assistantCalls = 0;
const persistTrace = () => {
	const temporaryTraceFile = `${traceFile}.tmp`;
	writeFileSync(
		temporaryTraceFile,
		JSON.stringify(
			{
				stack: "nira-neurajl",
				operatorTools: ["neurajl"],
				sharedTools: ["rlm"],
				toolInventory: activeTools,
				model: model.provider + "/" + model.id,
				modelConfig: {
					provider: model.provider,
					api: model.api,
					modelId: model.id,
					reasoningEffort: luna ? "max" : null,
					serviceTier: luna ? "default" : null,
					contextWindowTokens: model.contextWindow,
					maxOutputTokens: model.maxTokens,
					temperature: "omitted",
					topP: "omitted",
					pricing: luna
						? { inputPerMillion: 0.10, outputPerMillion: 0.50, cacheReadPerMillion: 0.01, cacheWritePerMillion: 0.125 }
						: null,
				},
				started,
				ended: Date.now(),
				retryPolicy,
				contextPolicy: { contextWindow: model.contextWindow, maxOutputTokens: model.maxTokens, compaction: compactionSettings },
				routePolicy: localBaseUrl || !routeProvider ? null : { only: [routeProvider], allow_fallbacks: false },
				toolTimeoutMs,
				toolOutputCapChars: maxOutputChars,
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
	if (JSON.stringify(activeTools) !== JSON.stringify(["neurajl", "rlm"])) {
		throw new Error(`NeuraJL tool inventory mismatch: ${activeTools.join(", ")}`);
	}
	if (session.getToolDefinition("ipython")) throw new Error("IPython leaked into NeuraJL condition");
	if (!session.getToolDefinition("neurajl")) throw new Error("NeuraJL operator surface is missing");
	if (process.env.ABC_PREFLIGHT_ONLY === "1") {
		console.log(JSON.stringify({ preflight: true, stack: "nira-neurajl", activeTools }));
	} else {
		await session.prompt(readFileSync(promptFile, "utf8"));
		await session.waitForHeadlessIdle();
		// Endurance runs: further work arrives in the same session once the previous batch is done.
		for (const followUp of (process.env.ABC_FOLLOWUP_PROMPTS ?? "").split(":").filter(Boolean)) {
			if (process.env.ABC_FOLLOWUP_HOOK) execFileSync(process.env.ABC_FOLLOWUP_HOOK, [followUp], { stdio: "inherit" });
			await session.prompt(readFileSync(followUp, "utf8"));
			await session.waitForHeadlessIdle();
		}
		const terminalAssistant = [...session.messages].reverse().find(
			(message): message is AssistantMessage => message.role === "assistant",
		);
		if (!terminalAssistant || (terminalAssistant.stopReason !== "stop" && terminalAssistant.stopReason !== "length") || terminalAssistant.errorMessage) {
			throw new Error("Trial ended without a successful terminal assistant response; see the raw trace");
		}
	}
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
