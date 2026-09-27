import { readFileSync } from "node:fs";
import { completeSimple, registerBuiltInApiProviders } from "../packages/ai/src/index.js";
const realFetch = globalThis.fetch;
globalThis.fetch = (async (url: any, init: any) => {
	try {
		const r = await realFetch(url, init);
		console.log("fetch", String(url), r.status, "body bytes", typeof init?.body === "string" ? init.body.length : "?");
		return r;
	} catch (e: any) {
		console.log("fetch threw", String(e?.stack).slice(0, 600)); console.log("fetch threw", String(url), e?.name, e?.message, e?.cause?.code, e?.cause?.message, "body bytes", typeof init?.body === "string" ? init.body.length : "?");
		throw e;
	}
}) as any;
try { (registerBuiltInApiProviders as any)?.(); } catch {}
const t = JSON.parse(readFileSync(process.env.TRACE!, "utf8"));
const upto = Number(process.env.UPTO);
const messages = t.messages.slice(0, upto).filter((m: any) => !(m.role === "assistant" && m.stopReason === "error"));
const key = readFileSync(process.env.KEYFILE!, "utf8").trim();
const model: any = {
	id: "openai/gpt-6-luna", name: "l", api: "openai-completions", provider: "openrouter", baseUrl: "https://openrouter.ai/api/v1",
	reasoning: true, input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 100000, maxTokens: 16000,
	thinkingLevelMap: { off: "none", minimal: "minimal", low: "low", medium: "medium", high: "high", xhigh: "xhigh", max: "max" },
	compat: { supportsDeveloperRole: false, supportsReasoningEffort: true, thinkingFormat: "openrouter", maxTokensField: "max_tokens", openRouterRouting: { only: ["openai"], allow_fallbacks: false } },
};
const r = await completeSimple(model, { systemPrompt: "Reply with ok.", messages }, { apiKey: key, maxTokens: 16000, reasoning: process.env.REASON || undefined, sessionId: "s-123", serviceTier: process.env.TIER || undefined } as any);
console.log("result", messages.length, r.stopReason, (r.errorMessage ?? "").slice(0, 200), JSON.stringify(r.content).slice(0, 100));
