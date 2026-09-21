/**
 * NIRA Stage 0 spike: can a session be built around NeuraBash instead of the
 * ipython kernel without diffuse edits to agent-session.ts?
 *
 * This does not exercise real NeuraBash or real ipython — both tools are
 * stubs. The point is structural: does baseToolsOverride actually skip
 * kernel construction end to end, and does the REPL_CONTROL_PROMPT doctrine
 * disappear on its own once ipython is absent from the active tool list.
 */
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";
import { afterEach, describe, expect, it } from "vitest";
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

describe("NIRA Stage 0: substrate modes", () => {
	let harness: Harness | undefined;

	afterEach(() => {
		harness?.cleanup();
		harness = undefined;
	});

	it("NEURA mode: baseToolsOverride excludes ipython from construction and doctrine", async () => {
		harness = await createHarness({
			tools: [stubTool("neurabash")],
		});

		const activeNames = harness.session.getActiveToolNames();
		expect(activeNames).toContain("neurabash");
		expect(activeNames).not.toContain("ipython");
		expect(harness.session.systemPrompt).not.toContain(REPL_DOCTRINE_MARKER);
	});

	it("DUAL mode: both tools active means the REPL doctrine is still present", async () => {
		harness = await createHarness({
			tools: [stubTool("neurabash"), stubTool("ipython")],
		});

		const activeNames = harness.session.getActiveToolNames();
		expect(activeNames).toContain("neurabash");
		expect(activeNames).toContain("ipython");
		// hasIpython is name-based, so the doctrine reappears even for a stub —
		// this is the confound: the prompt does not know NeuraBash exists as a
		// preferred substrate unless something (an extension, Stage 1's own
		// prompt) says so.
		expect(harness.session.systemPrompt).toContain(REPL_DOCTRINE_MARKER);
	});

	it("LEGACY mode (default, no override): ipython is present as usual", async () => {
		harness = await createHarness({
			tools: [stubTool("ipython")],
		});

		expect(harness.session.getActiveToolNames()).toEqual(["ipython"]);
		expect(harness.session.systemPrompt).toContain(REPL_DOCTRINE_MARKER);
	});
});
