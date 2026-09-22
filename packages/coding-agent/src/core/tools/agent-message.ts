/**
 * Host service: inter-agent messaging, reachable without an ipython kernel.
 *
 * NIRA-Prime Phase 1. Same shape as agent-observe.ts: AgentSessionMessageController
 * was already standalone and substrate-neutral. This tool exposes the same
 * capability the kernel bridge's agent_message.* handlers already provide,
 * so a NEURA-mode session can reach it without ipython existing at all.
 * Business logic untouched — calls the same controller methods.
 */
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { type Static, Type } from "typebox";
import type { AgentFamilyRelationship, AgentSessionMessageController } from "../agent-messages.js";
import type { ToolDefinition } from "../extensions/types.js";
import { wrapToolDefinition } from "./tool-definition-wrapper.js";

const RECEIVER_ROLES: AgentFamilyRelationship[] = ["parent", "sibling", "child"];

const agentMessageSchema = Type.Object({
	action: Type.Union([Type.Literal("list_agents"), Type.Literal("send")]),
	target: Type.Optional(Type.String({ description: "Required for 'send': the recipient agent id or name." })),
	message: Type.Optional(Type.String({ description: "Required for 'send': the message body." })),
	receiverRole: Type.Optional(Type.Union(RECEIVER_ROLES.map((r) => Type.Literal(r)))),
});

export type AgentMessageToolInput = Static<typeof agentMessageSchema>;

export interface AgentMessageToolDetails {
	action: "list_agents" | "send";
}

export function createAgentMessageToolDefinition(
	controller: AgentSessionMessageController,
): ToolDefinition<typeof agentMessageSchema, AgentMessageToolDetails> {
	return {
		name: "agent_message",
		label: "agent_message",
		description:
			"List agents in this session's family, or send a message to one (parent, sibling, or child). Available regardless of which execution substrate is active — messaging is host state, not owned by any compute tool.",
		promptSnippet: "agent_message - list agents / send a message to a parent, sibling, or child",
		parameters: agentMessageSchema,
		execute: async (_toolCallId, params) => {
			// Errors are thrown, not returned as an isError flag: AgentToolResult
			// has no such field. The agent loop is what turns a thrown error into
			// an isError toolResult message; matches bash.ts's convention.
			let result: unknown;
			switch (params.action) {
				case "list_agents":
					result = await controller.listAgents();
					break;
				case "send":
					if (!params.target) throw new Error("agent_message 'send' requires 'target'");
					if (!params.message) throw new Error("agent_message 'send' requires 'message'");
					result = await controller.sendAgentMessage({
						target: params.target,
						message: params.message,
						receiverRole: params.receiverRole,
					});
					break;
			}
			return {
				content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
				details: { action: params.action },
			};
		},
	};
}

export function createAgentMessageTool(
	controller: AgentSessionMessageController,
): AgentTool<typeof agentMessageSchema> {
	return wrapToolDefinition(createAgentMessageToolDefinition(controller));
}
