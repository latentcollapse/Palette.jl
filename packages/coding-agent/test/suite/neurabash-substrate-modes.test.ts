/**
 * NIRA Stage 0 spike: can a session be built around NeuraBash instead of the
 * ipython kernel without diffuse edits to agent-session.ts?
 *
 * Constructed through createAgentSession (sdk.js) — the real public entry
 * point — not direct AgentSession construction. An earlier version of this
 * test went through the harness's direct-construction path and never
 * exercised the SDK plumbing (baseToolsOverride forwarding through sdk.ts /
 * agent-session-services.ts) that Stage 0 actually added. That gap was
 * caught by adversarial review; this version closes it.
 *
 * Real NeuraBash and real ipython are still not exercised — both are stubs.
 * The point remains structural: does the public entry point actually skip
 * kernel construction end to end, and does REPL_CONTROL_PROMPT doctrine
 * disappear on its own once ipython is absent from the active tool list.
 */
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it } from "vitest";
import type { AgentSessionMessageController } from "../../src/core/agent-messages.js";
import type { AgentObserveController } from "../../src/core/agent-observe.js";
import { createAgentSession } from "../../src/core/sdk.js";
import { SessionManager } from "../../src/core/session-manager.js";
import { createTestResourceLoader } from "../utilities.js";
import { createHarness, type Harness } from "./harness.js";

const REPL_DOCTRINE_MARKER = "persistent Python REPL";

function stubTool(name: string): AgentTool {
	return {
		name,
		label: name,
		description: `stub ${name} tool for structural testing`,
		parameters: Type.Object({ code: Type.String() }),
		execute: async () => ({ content: [{ type: "text", text: "" }], details: undefined }),
	};
}

describe("NIRA Stage 0: substrate modes (via createAgentSession)", () => {
	let harness: Harness | undefined;

	afterEach(() => {
		harness?.cleanup();
		harness = undefined;
	});

	async function buildSession(overrides: Parameters<typeof createAgentSession>[0]) {
		// createHarness gives us a faux model/authStorage cheaply; we then call
		// the real public createAgentSession ourselves instead of using
		// harness.session, so the SDK plumbing under test actually runs.
		harness = await createHarness({ tools: [] });
		const result = await createAgentSession({
			cwd: harness.tempDir,
			authStorage: harness.authStorage,
			model: harness.getModel(),
			resourceLoader: createTestResourceLoader(),
			sessionManager: SessionManager.inMemory(),
			settingsManager: harness.settingsManager,
			...overrides,
		});
		return result.session;
	}

	it("NEURA mode: baseToolsOverride reaches AgentSession through the public entry point", async () => {
		const session = await buildSession({
			baseToolsOverride: { neurabash: stubTool("neurabash") },
			initialActiveToolNames: ["neurabash"],
			includeGoals: false,
		});

		const activeNames = session.getActiveToolNames();
		expect(activeNames).toContain("neurabash");
		expect(activeNames).not.toContain("ipython");
		// The ipython tool DEFINITION must be absent from the registry, not just
		// inactive — this is the actual "kernel not constructed" observable,
		// not merely "kernel present but unselected".
		expect(session.getToolDefinition("ipython")).toBeUndefined();
		expect(session.systemPrompt).not.toContain(REPL_DOCTRINE_MARKER);
	});

	it("LEGACY mode: the true default (no override, no explicit tools) still builds ipython", async () => {
		const session = await buildSession({});

		expect(session.getActiveToolNames()).toEqual(["ipython"]);
		expect(session.getToolDefinition("ipython")).toBeDefined();
		expect(session.systemPrompt).toContain(REPL_DOCTRINE_MARKER);
	});

	it("DUAL mode: both tools active means the REPL doctrine is still present", async () => {
		const session = await buildSession({
			baseToolsOverride: { neurabash: stubTool("neurabash"), ipython: stubTool("ipython") },
			initialActiveToolNames: ["neurabash", "ipython"],
		});

		const activeNames = session.getActiveToolNames();
		expect(activeNames).toContain("neurabash");
		expect(activeNames).toContain("ipython");
		// hasIpython is name-based, so the doctrine reappears even for a stub —
		// this is the confound: the prompt does not know NeuraBash exists as a
		// preferred substrate unless something (an extension, a later prompt)
		// says so.
		expect(session.systemPrompt).toContain(REPL_DOCTRINE_MARKER);
	});

	it("NEURA mode + an active goal fails loudly instead of silently dropping ipython", async () => {
		// Regression test for the bug adversarial review found: _buildRuntime
		// used to unconditionally push "ipython" into the active tool list
		// whenever a goal was active, and setActiveToolsByName silently drops
		// unknown tool names — so a resumed goal in a baseToolsOverride session
		// believed it had ipython access and silently didn't. Fixed to throw.
		await expect(
			buildSession({
				baseToolsOverride: { neurabash: stubTool("neurabash") },
				initialActiveToolNames: ["neurabash"],
				initialGoal: { objective: "test objective" },
			}),
		).rejects.toThrow(/active goal requires the ipython tool/i);
	});

	it("IPython breakout: a NEURA session cannot execute an ipython tool call even if the model attempts one", async () => {
		// Goal section 10/16.L — the boundary must hold against an actual attempt,
		// not just against the tool being unselected. The faux model here tries
		// to call "ipython" directly, the same way a real model attempting a
		// breakout would: a raw tool_use block naming a tool the session never
		// registered.
		const session = await buildSession({
			baseToolsOverride: { neurabash: stubTool("neurabash") },
			initialActiveToolNames: ["neurabash"],
			includeGoals: false,
		});
		harness?.setResponses([
			fauxAssistantMessage(fauxToolCall("ipython", { code: "1 + 1" }), { stopReason: "toolUse" }),
			fauxAssistantMessage("acknowledged"),
		]);

		await session.prompt("try to use ipython");

		const toolResultMessages = session.messages.filter((m) => m.role === "toolResult");
		expect(toolResultMessages.length).toBeGreaterThan(0);
		const [result] = toolResultMessages;
		// The exact wording is the agent loop's, not this test's to assert — the
		// load-bearing fact is that it is an error/rejection, not a real
		// execution, and it never invoked the real ipython tool logic (there is
		// none registered to invoke).
		expect(result.isError).toBe(true);
	});

	it("host service — agent_observe works in NEURA mode with no ipython kernel", async () => {
		// Goal section 6/16.G: observation is host state (AgentObserveController
		// was already standalone, zero AgentSession coupling per the dependency
		// map). This proves it's reachable as an ordinary tool call, not just
		// theoretically substrate-neutral.
		const controller: AgentObserveController = {
			listAgents: async () => ({ agents: [{ name: "sibling-1", relationship: "sibling" }] }) as any,
			getAgent: async (target) => ({ name: target, status: "running" }) as any,
			recentMessages: async () => ({ messages: [] }) as any,
		};
		const session = await buildSession({
			baseToolsOverride: { neurabash: stubTool("neurabash") },
			initialActiveToolNames: ["neurabash", "agent_observe"],
			includeGoals: false,
			agentObserveController: controller,
		});

		expect(session.getToolDefinition("ipython")).toBeUndefined();
		const tool = session.getToolDefinition("agent_observe");
		expect(tool).toBeDefined();
		const result = await tool!.execute("t1", { action: "list" }, undefined, undefined, undefined as any);
		expect(JSON.parse((result.content[0] as { text: string }).text)).toEqual({
			agents: [{ name: "sibling-1", relationship: "sibling" }],
		});
	});

	it("host service — agent_message works in NEURA mode with no ipython kernel", async () => {
		// Goal section 6/16.F.
		let sentTo: string | undefined;
		const controller: AgentSessionMessageController = {
			listAgents: async () => ({ agents: [] }) as any,
			sendAgentMessage: async (input) => {
				sentTo = input.target;
				return { id: "msg-1", deliveryStatus: "delivered" } as any;
			},
		};
		const session = await buildSession({
			baseToolsOverride: { neurabash: stubTool("neurabash") },
			initialActiveToolNames: ["neurabash", "agent_message"],
			includeGoals: false,
			agentMessageController: controller,
		});

		expect(session.getToolDefinition("ipython")).toBeUndefined();
		const tool = session.getToolDefinition("agent_message");
		expect(tool).toBeDefined();
		const result = await tool!.execute(
			"t1",
			{ action: "send", target: "parent-1", message: "done" },
			undefined,
			undefined,
			undefined as any,
		);
		expect(sentTo).toBe("parent-1");
		expect(JSON.parse((result.content[0] as { text: string }).text)).toEqual({
			id: "msg-1",
			deliveryStatus: "delivered",
		});
	});

	it("host service — agent_observe/agent_message are absent when no controller is configured", async () => {
		// No behavior change for a session that never had these controllers —
		// the host services are additive, not a new default surface.
		const session = await buildSession({
			baseToolsOverride: { neurabash: stubTool("neurabash") },
			initialActiveToolNames: ["neurabash"],
			includeGoals: false,
		});
		expect(session.getToolDefinition("agent_observe")).toBeUndefined();
		expect(session.getToolDefinition("agent_message")).toBeUndefined();
	});
});
