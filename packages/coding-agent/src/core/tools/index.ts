export { acpMcpToolNames, createAcpMcpToolDefinitions } from "./acp-mcp.js";
export {
	type AgentMessageToolDetails,
	type AgentMessageToolInput,
	createAgentMessageTool,
	createAgentMessageToolDefinition,
} from "./agent-message.js";
export {
	type AgentObserveToolDetails,
	type AgentObserveToolInput,
	createAgentObserveTool,
	createAgentObserveToolDefinition,
} from "./agent-observe.js";
export {
	type BashOperations,
	type BashSpawnContext,
	type BashSpawnHook,
	type BashToolDetails,
	type BashToolInput,
	type BashToolOptions,
	createBashTool,
	createBashToolDefinition,
	createLocalBashOperations,
} from "./bash.js";
export {
	createEditTool,
	createEditToolDefinition,
	type EditOperations,
	type EditToolDetails,
	type EditToolInput,
	type EditToolOptions,
} from "./edit.js";
export { withFileMutationQueue } from "./file-mutation-queue.js";
export {
	createIpythonTool,
	createIpythonToolDefinition,
	IpythonKernelProvisioner,
	type IpythonToolDetails,
	type IpythonToolInput,
	type IpythonToolOptions,
} from "./ipython.js";
export {
	createNeurabashTool,
	createNeurabashToolDefinition,
	type NeurabashSecurityProfile,
	type NeurabashToolDetails,
	type NeurabashToolInput,
	type NeurabashToolOptions,
} from "./neurabash.js";
export {
	DEFAULT_MAX_BYTES,
	DEFAULT_MAX_LINES,
	formatSize,
	type TruncationOptions,
	type TruncationResult,
	truncateHead,
	truncateLine,
	truncateTail,
} from "./truncate.js";

import type { AgentTool } from "@earendil-works/pi-agent-core";
import type { ToolDefinition } from "../extensions/types.js";
import { createIpythonToolDefinition, type IpythonToolOptions } from "./ipython.js";
import { createNeurabashToolDefinition, type NeurabashToolOptions } from "./neurabash.js";

export type Tool = AgentTool<any>;
export type ToolDef = ToolDefinition<any, any>;
export type ToolName = "ipython" | "neurabash";

export interface ToolsOptions {
	ipython?: IpythonToolOptions;
	/**
	 * NIRA-Prime: additive alongside ipython, not a replacement. See
	 * packages/coding-agent/src/core/tools/neurabash.ts for scope/rationale.
	 * Unset NEURABASH_BIN / options.neurabash.binPath means the tool exists in
	 * the registry but fails closed with a clear message on first use, rather
	 * than being silently absent.
	 */
	neurabash?: NeurabashToolOptions;
}

export function createAllToolDefinitions(cwd: string, options?: ToolsOptions): Record<ToolName, ToolDef> {
	return {
		ipython: createIpythonToolDefinition(cwd, options?.ipython),
		neurabash: createNeurabashToolDefinition(cwd, options?.neurabash),
	};
}
