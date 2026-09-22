/**
 * Host service: agent observation, reachable without an ipython kernel.
 *
 * NIRA-Prime Phase 1. AgentObserveController (agent-observe.ts) was already a
 * standalone, substrate-neutral interface with zero AgentSession coupling —
 * the only thing tying it to Python was that the model could only reach it
 * through _createKernelHostHandlers, dispatched over the kernel's comm
 * channel. This tool is the same capability exposed as an ordinary tool
 * call, so a NEURA-mode session (no kernel constructed at all) can use it.
 *
 * Business logic is untouched: this calls the exact same
 * AgentObserveController methods the kernel bridge calls. Nothing about
 * observation semantics changed, only how the model reaches it.
 */
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { type Static, Type } from "typebox";
import type { AgentObserveController } from "../agent-observe.js";
import type { ToolDefinition } from "../extensions/types.js";
import { wrapToolDefinition } from "./tool-definition-wrapper.js";

const agentObserveSchema = Type.Object({
	action: Type.Union([Type.Literal("list"), Type.Literal("get"), Type.Literal("recent")]),
	target: Type.Optional(Type.String({ description: "Required for 'get' and 'recent': the agent id or name." })),
	limit: Type.Optional(Type.Number({ description: "For 'recent': max messages to return." })),
});

export type AgentObserveToolInput = Static<typeof agentObserveSchema>;

export interface AgentObserveToolDetails {
	action: "list" | "get" | "recent";
}

export function createAgentObserveToolDefinition(
	controller: AgentObserveController,
): ToolDefinition<typeof agentObserveSchema, AgentObserveToolDetails> {
	return {
		name: "agent_observe",
		label: "agent_observe",
		description:
			"Inspect other agents in this session's family: list them, get a snapshot of one, or read its recent messages. Available regardless of which execution substrate (neurabash, ipython, none) is active — this is host state, not something any compute tool owns.",
		promptSnippet: "agent_observe - list/inspect other agents in this session's family",
		parameters: agentObserveSchema,
		execute: async (_toolCallId, params) => {
			// Errors are thrown, not returned as an isError flag: AgentToolResult
			// has no such field. The agent loop is what turns a thrown error into
			// an isError toolResult message; matches bash.ts's convention.
			let result: unknown;
			switch (params.action) {
				case "list":
					result = await controller.listAgents();
					break;
				case "get":
					if (!params.target) throw new Error("agent_observe 'get' requires 'target'");
					result = await controller.getAgent(params.target);
					break;
				case "recent":
					if (!params.target) throw new Error("agent_observe 'recent' requires 'target'");
					result = await controller.recentMessages({ target: params.target, limit: params.limit });
					break;
			}
			return {
				content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
				details: { action: params.action },
			};
		},
	};
}

export function createAgentObserveTool(controller: AgentObserveController): AgentTool<typeof agentObserveSchema> {
	return wrapToolDefinition(createAgentObserveToolDefinition(controller));
}
