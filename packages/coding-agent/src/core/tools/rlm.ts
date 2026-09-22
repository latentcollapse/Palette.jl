/**
 * Host service: RLM subagent lifecycle, reachable without an ipython kernel.
 *
 * NIRA-Prime RLM reachability spike. `_startRlmChildRun` and its siblings
 * (createRlmSession/listRlmSubagents/collectRlmChildren/deleteRlmSubagent/
 * findRlmModels/noteRlmProgress) were already substrate-neutral business
 * logic on AgentSession — the only thing tying subagent lifecycle to Python
 * was that the model could only reach it through _createKernelHostHandlers,
 * dispatched over the kernel's comm channel. This tool is the same seven
 * operations (the exact rlm.* set the kernel bridge already exposes: run,
 * create_session, list_subagents, collect, delete_subagent, find_models,
 * progress.note) reachable as an ordinary tool call instead, so a NEURA-mode
 * session (no kernel constructed at all) can spawn and manage children.
 *
 * Business logic is untouched: this calls the exact same public
 * AgentSession methods the kernel bridge calls (runRlmChild, not
 * _startRlmChildRun directly). Nothing about spawn/collect/cancel semantics
 * changed, only how the model reaches them. In particular, child construction
 * (_createInlineRlmSubagentRuntime / daemon-mode's admitRlmSubagentRuntime)
 * is not touched by this file at all.
 */
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { type Static, Type } from "typebox";
import type { ToolDefinition } from "../extensions/types.js";
import { DEFAULT_RLM_MODEL_SEARCH_LIMIT, MAX_RLM_MODEL_SEARCH_LIMIT, type RlmLifecycleHost } from "../rlm-runtime.js";
import { wrapToolDefinition } from "./tool-definition-wrapper.js";

const RLM_COLLECT_MAX_TIMEOUT_MS = 2_147_483_647;

const rlmSchema = Type.Object({
	action: Type.Union([
		Type.Literal("spawn"),
		Type.Literal("create_session"),
		Type.Literal("list"),
		Type.Literal("collect"),
		Type.Literal("delete"),
		Type.Literal("find_models"),
		Type.Literal("progress_note"),
	]),
	prompt: Type.Optional(Type.String({ description: "Task prompt. Required for 'spawn' and 'create_session'." })),
	name: Type.Optional(
		Type.String({ description: "Requested session name. Optional for 'spawn' and 'create_session'." }),
	),
	model: Type.Optional(
		Type.String({
			description:
				"Model selector, e.g. 'anthropic/claude-sonnet-4-5'. Optional for 'spawn' and 'create_session'; defaults to this session's subagent default.",
		}),
	),
	thinking: Type.Optional(
		Type.String({ description: "Thinking level for the new session. Optional for 'spawn' and 'create_session'." }),
	),
	cwd: Type.Optional(
		Type.String({ description: "Working directory for the new top-level session. Only used by 'create_session'." }),
	),
	target: Type.Optional(Type.String({ description: "Child id or name. Required for 'delete'." })),
	targets: Type.Optional(
		Type.Array(Type.String(), {
			description: "Child ids or names. For 'collect': omitted or empty means all direct children.",
		}),
	),
	timeout_ms: Type.Optional(
		Type.Number({
			description:
				"For 'collect': milliseconds to wait for the targeted children to settle before returning current snapshots. Default 0 (immediate snapshot, never blocks).",
		}),
	),
	query: Type.Optional(Type.String({ description: "Search text. Required for 'find_models'." })),
	limit: Type.Optional(Type.Number({ description: "Max results. For 'find_models'." })),
	message: Type.Optional(Type.String({ description: "Progress text. Required for 'progress_note'." })),
});

export type RlmToolInput = Static<typeof rlmSchema>;

export interface RlmToolDetails {
	action: RlmToolInput["action"];
}

export function createRlmToolDefinition(host: RlmLifecycleHost): ToolDefinition<typeof rlmSchema, RlmToolDetails> {
	return {
		name: "rlm",
		label: "rlm",
		description:
			"Manage subagents (child sessions) under this session's control: spawn one to work a task in the background, list the current roster, collect results (optionally waiting for settlement), cancel one, search available models, or create a new top-level sibling session. A spawned child is a new principal with its own model and tool access, not a shared execution context. Available regardless of which execution substrate (if any) is active in this session or in the child — this is host lifecycle state, not something any compute tool owns.",
		promptSnippet: "rlm - spawn/list/collect/cancel subagents, independent of code-execution substrate",
		parameters: rlmSchema,
		execute: async (_toolCallId, params) => {
			// Errors are thrown, not returned as an isError flag: AgentToolResult
			// has no such field. Matches agent-observe.ts/bash.ts's convention.
			let result: unknown;
			switch (params.action) {
				case "spawn": {
					if (!params.prompt) throw new Error("rlm 'spawn' requires 'prompt'");
					const kwargs: Record<string, unknown> = {};
					if (params.name !== undefined) kwargs.name = params.name;
					if (params.model !== undefined) kwargs.model = params.model;
					if (params.thinking !== undefined) kwargs.thinking = params.thinking;
					result = await host.runRlmChild(params.prompt, kwargs);
					break;
				}
				case "create_session": {
					if (!params.prompt) throw new Error("rlm 'create_session' requires 'prompt'");
					const kwargs: Record<string, unknown> = {};
					if (params.name !== undefined) kwargs.name = params.name;
					if (params.model !== undefined) kwargs.model = params.model;
					if (params.thinking !== undefined) kwargs.thinking = params.thinking;
					if (params.cwd !== undefined) kwargs.cwd = params.cwd;
					result = await host.createRlmSession(params.prompt, kwargs);
					break;
				}
				case "list":
					result = await host.listRlmSubagents();
					break;
				case "collect": {
					const timeoutMs = params.timeout_ms ?? 0;
					if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 0 || timeoutMs > RLM_COLLECT_MAX_TIMEOUT_MS) {
						throw new Error(
							`rlm 'collect' timeout_ms must be a non-negative integer up to ${RLM_COLLECT_MAX_TIMEOUT_MS}`,
						);
					}
					result = await host.collectRlmChildren(params.targets ?? [], timeoutMs);
					break;
				}
				case "delete":
					if (!params.target) throw new Error("rlm 'delete' requires 'target'");
					result = await host.deleteRlmSubagent(params.target);
					break;
				case "find_models": {
					if (!params.query) throw new Error("rlm 'find_models' requires 'query'");
					const limit = params.limit ?? DEFAULT_RLM_MODEL_SEARCH_LIMIT;
					if (!Number.isInteger(limit) || limit < 1 || limit > MAX_RLM_MODEL_SEARCH_LIMIT) {
						throw new Error(`rlm 'find_models' limit must be an integer from 1 to ${MAX_RLM_MODEL_SEARCH_LIMIT}`);
					}
					result = await host.findRlmModels(params.query, limit);
					break;
				}
				case "progress_note":
					if (!params.message) throw new Error("rlm 'progress_note' requires 'message'");
					result = host.noteRlmProgress(params.message);
					break;
			}
			return {
				content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
				details: { action: params.action },
			};
		},
	};
}

export function createRlmTool(host: RlmLifecycleHost): AgentTool<typeof rlmSchema> {
	return wrapToolDefinition(createRlmToolDefinition(host));
}
