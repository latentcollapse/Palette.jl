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
 * pointed at the actual neurajl-operator-lab checkout and a real Julia dev
 * project (skipped cleanly if either isn't configured/available -- see
 * `skipIfNeurajlUnavailable`). This is deliberate: NeuraBash's own
 * substrate-mode tests use stubs because real persistence wasn't the point
 * being proven there. Here it is the point.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
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
		return buildSessionIn(harness, overrides);
	}

	async function buildSessionIn(harness: Harness, overrides: Parameters<typeof createAgentSession>[0]) {
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

	function textOf(result: { content: unknown[] }): string {
		return (result.content[0] as { text: string }).text;
	}

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: state persists across calls, in the task workspace, with printed output returned",
		async () => {
			harness = await createHarness({ tools: [] });
			writeFileSync(join(harness.tempDir, "marker.txt"), "from-host");
			const session = await buildSessionIn(harness, {
				baseToolsFactory: createNeurajlBaseToolsFactory(harness.tempDir, {
					sessionCliPath: SESSION_CLI_PATH,
					projectDir: PROJECT_DIR,
				}),
				initialActiveToolNames: ["neurajl"],
				includeGoals: false,
			});
			expect(session.getToolDefinition("ipython")).toBeUndefined();
			const tool = session.getToolDefinition("neurajl")!;
			const call = (id: string, params: { code: string; ephemeral?: boolean }) =>
				tool.execute(id, params, undefined, undefined, undefined as never);

			expect(textOf(await call("t1", { code: "x = 42" }))).toBe("42");
			expect(textOf(await call("t2", { code: "x + 1" }))).toBe("43");

			// Printed output used to be parsed as a protocol line and kill the session.
			expect(textOf(await call("t3", { code: 'println("hello"); run(`echo child`); 7' }))).toMatch(
				/hello[\s\S]*=> 7|child[\s\S]*=> 7/,
			);
			expect(textOf(await call("t4", { code: "x" }))).toBe("42");

			expect(textOf(await call("t5", { code: 'read("marker.txt", String)' }))).toBe('"from-host"');
			await call("t6", { code: 'write("from-julia.txt", "written")' });
			expect(readFileSync(join(harness.tempDir, "from-julia.txt"), "utf8")).toBe("written");

			await expect(call("t7", { code: 'error("boom")' })).rejects.toThrow(/boom/);

			// An ephemeral turn runs in a disposable child and leaves nothing behind.
			expect(textOf(await call("t8", { code: "helper(y) = y * 10; helper(3)", ephemeral: true }))).toBe("30");
			expect(textOf(await call("t9", { code: "@isdefined(helper)" }))).toBe("false");
			expect(textOf(await call("t10", { code: "x" }))).toBe("42");
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel; a cold precompile alone takes ~40s
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: a timed-out turn stops the kernel and the next call says it runs in a new one",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-timeout-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
				turnTimeout: 5,
			})("timeout-test-session");
			const tool = scope.tools.neurajl!;
			try {
				await tool.execute("t1", { code: "x = 1" }, undefined, undefined);
				await expect(tool.execute("t2", { code: "sleep(30)" }, undefined, undefined)).rejects.toThrow(
					/turn_timeout/,
				);
				const after = await tool.execute("t3", { code: "@isdefined(x)" }, undefined, undefined);
				expect(textOf(after)).toMatch(/NEW kernel[\s\S]*false$/);
			} finally {
				await scope.dispose?.();
				rmSync(workspace, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel; a cold precompile alone takes ~40s
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: dispose terminates the kernel and later calls fail",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-dispose-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
			})("dispose-test-session");
			const tool = scope.tools.neurajl!;
			try {
				expect(textOf(await tool.execute("t1", { code: "1 + 1" }, undefined, undefined))).toBe("2");
				await scope.dispose?.();
				await expect(tool.execute("t2", { code: "1 + 1" }, undefined, undefined)).rejects.toThrow(/disposed/);
			} finally {
				rmSync(workspace, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel; a cold precompile alone takes ~40s
		300_000,
	);
});
