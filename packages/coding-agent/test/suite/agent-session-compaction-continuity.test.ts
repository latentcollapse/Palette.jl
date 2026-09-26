/**
 * A compaction during an active task resumes that same task: once, repeatedly,
 * with a tool that keeps its own state across compactions (as NeuraJL's kernel
 * does), with tool calls after it, and without running the user's request twice
 * or skipping any scripted step. Also: a reply cut off at the output limit is
 * resumed rather than taken as the end of the run, a bounded number of times.
 */
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionFactory } from "../../src/core/extensions/types.js";
import { createHarness, type Harness } from "./harness.js";

const PROMPT = "run the tools then summarize";

// Built when the model is called, so each reply is newer than any compaction
// before it, as a real reply would be.
const toolCallReply = () => () => fauxAssistantMessage(fauxToolCall("big", {}), { stopReason: "toolUse" });

function extensionCompaction(): ExtensionFactory {
	return (pi) => {
		pi.on("session_before_compact", async (event) => ({
			compaction: {
				summary: "auto compacted",
				firstKeptEntryId: event.preparation.firstKeptEntryId,
				tokensBefore: event.preparation.tokensBefore,
				details: { source: "extension" },
			},
		}));
	};
}

function bigTool(counter: { calls: number }) {
	return {
		name: "big",
		label: "big",
		description: "returns big text",
		parameters: Type.Object({}),
		execute: async () => {
			counter.calls += 1;
			return { content: [{ type: "text" as const, text: "x".repeat(40_000) }], details: {} };
		},
	};
}

const compacting = {
	settings: { compaction: { enabled: true, reserveTokens: 500, keepRecentTokens: 1 } },
	models: [{ id: "faux-1", contextWindow: 6_000 }],
	persistSession: true,
	extensionFactories: [extensionCompaction()],
};

describe("AgentSession: compaction continues the active task", () => {
	const harnesses: Harness[] = [];
	afterEach(() => {
		while (harnesses.length > 0) harnesses.pop()?.cleanup();
	});

	function entries(harness: Harness) {
		return harness.sessionManager.getEntries();
	}
	function userPromptCount(harness: Harness) {
		return entries(harness).filter((e) => {
			if (e.type !== "message" || e.message.role !== "user") return false;
			const c = e.message.content;
			const text = typeof c === "string" ? c : c.map((b) => (b.type === "text" ? b.text : "")).join("");
			return text.includes(PROMPT);
		}).length;
	}
	function customCount(harness: Harness, customType: string) {
		return entries(harness).filter((e) => e.type === "custom_message" && e.customType === customType).length;
	}
	function completedCompactions(harness: Harness) {
		return harness.eventsOfType("compaction_end").filter((e) => e.result).length;
	}

	it("resumes after one compaction and finishes the task", async () => {
		const counter = { calls: 0 };
		const harness = await createHarness({ ...compacting, tools: [bigTool(counter)] });
		harnesses.push(harness);
		harness.setResponses([
			toolCallReply(),
			() => fauxAssistantMessage("final answer"),
		]);
		await harness.session.prompt(PROMPT);
		await harness.session.waitForHeadlessIdle();
		expect(completedCompactions(harness)).toBeGreaterThanOrEqual(1);
		expect(harness.getPendingResponseCount()).toBe(0);
		expect(counter.calls).toBe(1);
		expect(userPromptCount(harness)).toBe(1);
	});

	it("resumes after repeated compactions, running every tool call once", async () => {
		const counter = { calls: 0 };
		const harness = await createHarness({ ...compacting, tools: [bigTool(counter)] });
		harnesses.push(harness);
		harness.setResponses([
			toolCallReply(),
			toolCallReply(),
			toolCallReply(),
			toolCallReply(),
			() => fauxAssistantMessage("final answer"),
		]);
		await harness.session.prompt(PROMPT);
		await harness.session.waitForHeadlessIdle();
		expect(completedCompactions(harness)).toBeGreaterThanOrEqual(3);
		expect(harness.getPendingResponseCount()).toBe(0);
		expect(counter.calls).toBe(4);
		expect(userPromptCount(harness)).toBe(1);
	});

	it("reports a stateful tool's state after each compaction and keeps going", async () => {
		const counter = { calls: 0 };
		const harness = await createHarness({
			...compacting,
			baseToolsFactory: () => ({
				tools: { big: bigTool(counter) },
				stateAfterCompaction: async () => ({
					customType: "neurajl_state",
					content: `[neurajl-state]\n\nBindings: calls (Int64, call ${counter.calls}).`,
				}),
			}),
		});
		harnesses.push(harness);
		harness.setResponses([
			toolCallReply(),
			toolCallReply(),
			toolCallReply(),
			() => fauxAssistantMessage("final answer"),
		]);
		await harness.session.prompt(PROMPT);
		await harness.session.waitForHeadlessIdle();
		const compactions = completedCompactions(harness);
		expect(compactions).toBeGreaterThanOrEqual(2);
		expect(customCount(harness, "neurajl_state")).toBe(compactions);
		expect(harness.getPendingResponseCount()).toBe(0);
		expect(counter.calls).toBe(3);
		expect(userPromptCount(harness)).toBe(1);
	});

	it("resumes a reply cut off at the output limit when a compaction stops the turn", async () => {
		const counter = { calls: 0 };
		const harness = await createHarness({ ...compacting, tools: [bigTool(counter)] });
		harnesses.push(harness);
		harness.setResponses([
			toolCallReply(),
			() => fauxAssistantMessage("I found six anomalies and will now write the rep", { stopReason: "length" }),
			toolCallReply(),
			() => fauxAssistantMessage("final answer"),
		]);
		await harness.session.prompt(PROMPT);
		await harness.session.waitForHeadlessIdle();
		expect(harness.getPendingResponseCount()).toBe(0);
		expect(counter.calls).toBe(2);
		expect(customCount(harness, "output_limit_continuation")).toBe(1);
		expect(userPromptCount(harness)).toBe(1);
	});

	it("resumes a reply cut off at the output limit without compaction, at most three times in a row", async () => {
		const harness = await createHarness({ models: [{ id: "faux-1", contextWindow: 200_000 }], persistSession: true });
		harnesses.push(harness);
		harness.setResponses([
			fauxAssistantMessage("part one", { stopReason: "length" }),
			fauxAssistantMessage("part two", { stopReason: "length" }),
			fauxAssistantMessage("part three", { stopReason: "length" }),
			fauxAssistantMessage("part four", { stopReason: "length" }),
			fauxAssistantMessage("never requested"),
		]);
		await harness.session.prompt(PROMPT);
		await harness.session.waitForHeadlessIdle();
		expect(customCount(harness, "output_limit_continuation")).toBe(3);
		expect(harness.getPendingResponseCount()).toBe(1);
	});

	it("does not continue a reply that ended normally", async () => {
		const harness = await createHarness({ models: [{ id: "faux-1", contextWindow: 200_000 }], persistSession: true });
		harnesses.push(harness);
		harness.setResponses([fauxAssistantMessage("done"), fauxAssistantMessage("never requested")]);
		await harness.session.prompt(PROMPT);
		await harness.session.waitForHeadlessIdle();
		expect(customCount(harness, "output_limit_continuation")).toBe(0);
		expect(harness.getPendingResponseCount()).toBe(1);
	});
});
