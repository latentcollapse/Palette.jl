/**
 * NIRA-Prime NeuraJL operator surface: does the chassis actually build a
 * session around it, and does the real integration (not a stub) prove the
 * one thing NeuraBash's own first-pass adapter explicitly does not yet --
 * session persistence surviving across separate tool calls?
 *
 * Structured the same way as neurabash-substrate-modes.test.ts: constructed
 * through createAgentSession (sdk.js), the real public entry point, not
 * direct AgentSession construction.
 *
 * The `baseToolsFactory` tests below use a REAL createNeurajlBaseToolsFactory
 * pointed at the actual ijulia-operator-lab checkout and a real Julia dev
 * project (skipped cleanly if either isn't configured/available -- see
 * `skipIfNeurajlUnavailable`). This is deliberate: NeuraBash's own
 * substrate-mode tests use stubs because real persistence wasn't the point
 * being proven there. Here it is the point.
 */
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { Type } from "typebox";
import { afterEach, describe, expect, it } from "vitest";
import { createAgentSession, createNeurajlBaseToolsFactory } from "../../src/core/sdk.js";
import { SessionManager } from "../../src/core/session-manager.js";
import { createTestResourceLoader } from "../utilities.js";
import { createHarness, type Harness } from "./harness.js";

const REPL_DOCTRINE_MARKER = "persistent Python REPL";

const SESSION_CLI_PATH = process.env.NEURAJL_SESSION_CLI;
const PROJECT_DIR = process.env.NEURAJL_PROJECT_DIR;

function skipIfNeurajlUnavailable(): boolean {
	if (!SESSION_CLI_PATH || !existsSync(SESSION_CLI_PATH)) return true;
	if (!PROJECT_DIR || !existsSync(PROJECT_DIR)) return true;
	try {
		execFileSync("bwrap", ["--version"], { stdio: "ignore" });
	} catch {
		return true;
	}
	return false;
}

function stubTool(name: string): AgentTool {
	return {
		name,
		label: name,
		description: `stub ${name} tool for structural testing`,
		parameters: Type.Object({ code: Type.String() }),
		execute: async () => ({ content: [{ type: "text", text: "" }], details: undefined }),
	};
}

describe("NIRA-Prime: NeuraJL substrate modes (via createAgentSession)", () => {
	let harness: Harness | undefined;

	afterEach(() => {
		harness?.cleanup();
		harness = undefined;
	});

	async function buildSession(overrides: Parameters<typeof createAgentSession>[0]) {
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

	it("NEURA mode (stub): baseToolsOverride still reaches AgentSession with a neurajl-named tool", async () => {
		const session = await buildSession({
			baseToolsOverride: { neurajl: stubTool("neurajl") },
			initialActiveToolNames: ["neurajl"],
			includeGoals: false,
		});

		const activeNames = session.getActiveToolNames();
		expect(activeNames).toContain("neurajl");
		expect(activeNames).not.toContain("ipython");
		expect(session.getToolDefinition("ipython")).toBeUndefined();
		expect(session.systemPrompt).not.toContain(REPL_DOCTRINE_MARKER);
	});

	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: baseToolsFactory starts a real NeuraJL kernel and state persists across separate tool calls",
		async () => {
			const factory = createNeurajlBaseToolsFactory(process.cwd(), {
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
			});

			const session = await buildSession({
				baseToolsFactory: factory,
				initialActiveToolNames: ["neurajl"],
				includeGoals: false,
			});

			expect(session.getToolDefinition("ipython")).toBeUndefined();
			const tool = session.getToolDefinition("neurajl");
			expect(tool).toBeDefined();

			// Turn 1: bind a variable in the persistent kernel.
			const r1 = await tool!.execute("t1", { code: "x = 42" }, undefined, undefined, undefined as never);
			expect(r1.isError).toBeFalsy();

			// Turn 2, a SEPARATE tool call: the binding must still be there --
			// this is the actual thing NeuraBash's own first-pass adapter does
			// not yet prove (its own doc: "each call is an independent,
			// ephemeral invocation").
			const r2 = await tool!.execute("t2", { code: "x + 1" }, undefined, undefined, undefined as never);
			expect(r2.isError).toBeFalsy();
			expect((r2.content[0] as { text: string }).text).toBe("43");

			// An ephemeral turn must not leak into the persistent kernel, and
			// -- the specific regression this integration found and fixed --
			// must not break the session's ability to answer the NEXT turn.
			const r3 = await tool!.execute(
				"t3",
				{ code: "helper(y) = y * 10; helper(3)", ephemeral: true },
				undefined,
				undefined,
				undefined as never,
			);
			expect(r3.isError).toBeFalsy();
			expect((r3.content[0] as { text: string }).text).toBe("30");

			const r4 = await tool!.execute("t4", { code: "x" }, undefined, undefined, undefined as never);
			expect(r4.isError).toBeFalsy();
			expect((r4.content[0] as { text: string }).text).toBe("42");

			const r5 = await tool!.execute("t5", { code: "@isdefined(helper)" }, undefined, undefined, undefined as never);
			expect(r5.isError).toBeFalsy();
			expect((r5.content[0] as { text: string }).text).toBe("false");
		},
		120_000,
	);

	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: dispose actually terminates the underlying process",
		async () => {
			const factory = createNeurajlBaseToolsFactory(process.cwd(), {
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
			});
			const scope = factory("dispose-test-session");
			const tool = scope.tools.neurajl!;

			const r1 = await tool.execute("t1", { code: "1 + 1" }, undefined, undefined, undefined as never);
			expect(r1.isError).toBeFalsy();

			await scope.dispose?.();

			// A second call after dispose must fail cleanly (the process is
			// gone), not hang -- dispose has to actually be a real teardown,
			// not a no-op that leaves the child process running.
			const r2 = await tool.execute("t2", { code: "1 + 1" }, undefined, undefined, undefined as never);
			expect(r2.isError).toBe(true);
		},
		60_000,
	);
});
