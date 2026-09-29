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
import { existsSync, mkdtempSync, readFileSync, readlinkSync, rmSync, watch, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it } from "vitest";
import { createAgentSession, createNeurajlBaseToolsFactory } from "../../src/core/sdk.js";
import { SessionManager } from "../../src/core/session-manager.js";
import { NEURAJL_RLM_REQUEST_TYPES } from "../../src/core/tools/neurajl.js";
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
					workspaceMap: false,
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
		"REAL integration: a timed-out wait keeps the kernel; compute that never yields stops it and the next call says so",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-timeout-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				workspaceMap: false,
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
				turnTimeout: 5,
				stateRoot: false,
			})("timeout-test-session");
			const tool = scope.tools.neurajl!;
			try {
				await tool.execute("t1", { code: "x = 1" }, undefined, undefined);
				const waited = tool.execute("t2", { code: "sleep(30)" }, undefined, undefined);
				await expect(waited).rejects.toThrow(/Interrupted[\s\S]*every binding are intact/);
				await expect(waited).rejects.not.toThrow(/the kernel stopped/);
				expect(textOf(await tool.execute("t3", { code: "x" }, undefined, undefined))).toBe("1");
				await expect(
					tool.execute("t4", { code: "s = 0; while true; s += 1; end" }, undefined, undefined),
				).rejects.toThrow(/the kernel stopped[\s\S]*Lost bindings: x \(Int64, call 1\)\./);
				const after = await tool.execute("t5", { code: "@isdefined(x)" }, undefined, undefined);
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
		"REAL integration: a kernel that never yields is replaced by one that revives the last completed call's state",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-revive-"));
			const stateRoot = mkdtempSync(join(tmpdir(), "neurajl-revive-state-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				workspaceMap: false,
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
				turnTimeout: 5,
				stateRoot,
			})("revive-test-session");
			const tool = scope.tools.neurajl!;
			try {
				await tool.execute("t1", { code: "x = [1, 2]; y = x; double(v) = 2v" }, undefined, undefined);
				await expect(
					tool.execute("t2", { code: "x[1] = 99; s = 0; while true; s += 1; end" }, undefined, undefined),
				).rejects.toThrow(/revives what it can of the last saved state/);
				const after = textOf(await tool.execute("t3", { code: "(x, y === x, double(x))" }, undefined, undefined));
				expect(after).toMatch(/NEW kernel .*which revived the last saved state/);
				expect(after).toMatch(/\[revival\].*end of call 1/);
				expect(after).toMatch(/restored exactly: x \(Vector\{Int64\}, call 1\), y \(Vector\{Int64\}, call 1\)/);
				expect(after).toMatch(/rebuilt from source: double \(function, call 1\)/);
				expect(after).toMatch(/=> \(\[1, 2\], true, \[2, 4\]\)$/);
			} finally {
				await scope.dispose?.();
				rmSync(workspace, { recursive: true, force: true });
				rmSync(stateRoot, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts two real sandboxed Julia kernels
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: the workspace map opens the first result and the first after a compaction",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-map-"));
			writeFileSync(join(workspace, "lib.rs"), "pub fn f() {}\n");
			const scope = createNeurajlBaseToolsFactory(workspace, {
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
				stateRoot: false,
				workspaceMap: true,
			})("map-test-session");
			const tool = scope.tools.neurajl!;
			try {
				const first = textOf(await tool.execute("t1", { code: "1 + 1" }, undefined, undefined));
				expect(first).toMatch(/^\[workspace map\] 1 files/);
				expect(first).toMatch(/Rust 1/);
				expect(first).toMatch(/2$/);
				expect(textOf(await tool.execute("t2", { code: "2 + 2" }, undefined, undefined))).not.toMatch(
					/workspace map/,
				);
				const note = await scope.stateAfterCompaction?.();
				expect(note?.content).toMatch(/Your next neurajl result opens with a map of the workspace/);
				expect(textOf(await tool.execute("t3", { code: "3" }, undefined, undefined))).toMatch(/^\[workspace map\]/);
				expect(textOf(await tool.execute("t4", { code: "4" }, undefined, undefined))).not.toMatch(/workspace map/);
			} finally {
				await scope.dispose?.();
				rmSync(workspace, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: an idle kernel is stopped and revived on the next call; a long call is never stopped",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-idle-"));
			const stateRoot = mkdtempSync(join(tmpdir(), "neurajl-idle-state-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				workspaceMap: false,
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
				stateRoot,
				idleStopMs: 4000,
			})("idle-test-session");
			const tool = scope.tools.neurajl!;
			// Kernels of this workspace only: other sessions on the host may run their own.
			const kernels = () =>
				execFileSync("pgrep", ["-f", "session_loop.jl"], { encoding: "utf8" })
					.split("\n")
					.filter((pid) => {
						try {
							return pid !== "" && readlinkSync(`/proc/${pid}/cwd`) === workspace;
						} catch {
							return false;
						}
					}).length;
			try {
				await tool.execute("t1", { code: "x = 41" }, undefined, undefined);
				// Longer than the idle limit, but a call in progress is never stopped.
				expect(textOf(await tool.execute("t2", { code: "sleep(7); x + 1" }, undefined, undefined))).toBe("42");
				const before = kernels();
				// test-policy: allow wall-clock-timer -- the feature under test is a real idle timer stopping a real kernel process
				await new Promise((resolve) => setTimeout(resolve, 20_000));
				expect(kernels()).toBeLessThan(before);
				const after = textOf(await tool.execute("t3", { code: "x" }, undefined, undefined));
				expect(after).toMatch(
					/stopped after 4 seconds without a call, to free its memory; this call ran in a NEW kernel/,
				);
				expect(after).toMatch(/41$/);
			} finally {
				await scope.dispose?.();
				rmSync(workspace, { recursive: true, force: true });
				rmSync(stateRoot, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel twice and waits out the idle limit
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: an abort mid-call stops the kernel and says so; one before the call does not",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-abort-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				workspaceMap: false,
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
			})("abort-test-session");
			const tool = scope.tools.neurajl!;
			try {
				await tool.execute("t1", { code: "x = 1" }, undefined, undefined);
				const early = new AbortController();
				early.abort();
				const before = tool.execute("t2", { code: "x" }, early.signal, undefined);
				await expect(before).rejects.toThrow(/aborted/);
				await expect(before).rejects.not.toThrow(/kernel stopped/);
				expect(textOf(await tool.execute("t3", { code: "x" }, undefined, undefined))).toBe("1");

				// The code announces it is running; the abort follows that event.
				const started = new Promise<void>((resolve) => {
					const watcher = watch(workspace, (_event, name) => {
						if (name === "started") {
							watcher.close();
							resolve();
						}
					});
				});
				const late = new AbortController();
				const during = tool.execute("t4", { code: 'touch("started"); sleep(30)' }, late.signal, undefined);
				await started;
				late.abort();
				await expect(during).rejects.toThrow(/the kernel stopped/);
				// The new kernel revives x from the state saved after t1/t3.
				const after = await tool.execute("t5", { code: "@isdefined(x)" }, undefined, undefined);
				expect(textOf(after)).toMatch(/NEW kernel[\s\S]*which revived the last saved state[\s\S]*true$/);
			} finally {
				await scope.dispose?.();
				rmSync(workspace, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel twice
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: elided output names the call whose full output the kernel kept",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-elide-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				workspaceMap: false,
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
				maxOutputChars: 400,
			})("elide-test-session");
			const tool = scope.tools.neurajl!;
			try {
				const long = textOf(
					await tool.execute("t1", { code: 'for i in 1:500; println("line ", i); end' }, undefined, undefined),
				);
				expect(long).toMatch(
					/characters elided; Neura\.output\(1\) returns everything this call printed, and ans its value/,
				);
				expect(long).not.toContain("line 250\n");
				const back = await tool.execute(
					"t2",
					{ code: 'o = Neura.output(1); (length(split(o, "\\n"; keepempty=false)), occursin("line 250\\n", o))' },
					undefined,
					undefined,
				);
				expect(textOf(back)).toBe("(500, true)");
			} finally {
				await scope.dispose?.();
				rmSync(workspace, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: after compaction the model is told what the live kernel holds",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-compact-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				workspaceMap: false,
				sessionCliPath: SESSION_CLI_PATH,
				projectDir: PROJECT_DIR,
			})("compact-test-session");
			const tool = scope.tools.neurajl!;
			try {
				await tool.execute("t1", { code: "rows = [1, 2, 3]; total(v) = sum(v)" }, undefined, undefined);
				const state = await scope.stateAfterCompaction?.();
				expect(state?.customType).toBe("neurajl_state");
				expect(state?.content).toContain("rows (Vector{Int64}, call 1), total (function, call 1)");
			} finally {
				await scope.dispose?.();
				rmSync(workspace, { recursive: true, force: true });
			}
		},
		// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel
		300_000,
	);

	// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
	it.skipIf(skipIfNeurajlUnavailable())(
		"REAL integration: dispose terminates the kernel and later calls fail",
		async () => {
			const workspace = mkdtempSync(join(tmpdir(), "neurajl-dispose-"));
			const scope = createNeurajlBaseToolsFactory(workspace, {
				workspaceMap: false,
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

	describe("REAL integration: RLM children from Julia code", () => {
		const rlmCeiling = { host_request: { allowed_types: [...NEURAJL_RLM_REQUEST_TYPES] } };

		async function rlmSession(ceiling: Record<string, unknown>, turnTimeout = 60) {
			harness = await createHarness({ tools: [] });
			const session = await buildSessionIn(harness, {
				baseToolsFactory: createNeurajlBaseToolsFactory(harness.tempDir, {
					workspaceMap: false,
					sessionCliPath: SESSION_CLI_PATH,
					projectDir: PROJECT_DIR,
					ceiling,
					turnTimeout,
					stateRoot: mkdtempSync(join(tmpdir(), "neurajl-rlm-state-")),
				}),
				initialActiveToolNames: ["neurajl"],
				includeGoals: false,
			});
			const tool = session.getToolDefinition("neurajl")!;
			let n = 0;
			const call = (code: string) => tool.execute(`t${++n}`, { code }, undefined, undefined, undefined as never);
			return { session, tool, call, harness };
		}

		// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
		it.skipIf(skipIfNeurajlUnavailable())(
			"spawns and collects in one call and across calls, reports a failing child, and keeps the parent's ceiling",
			async () => {
				const { session, tool, call, harness: h } = await rlmSession(rlmCeiling);
				expect(tool.description).toContain("Neura.rlm.spawn");
				h.setResponses([fauxAssistantMessage("forty-two")]);
				const one = textOf(
					await call(
						'h = Neura.rlm.spawn("what is 40 + 2?"; name = "adder"); ' +
							"r = only(Neura.rlm.collect(h; timeout_ms = 40_000)); (r.status, r.settled, r.answer_preview)",
					),
				);
				expect(one).toContain('("done", true, "forty-two")');
				// The child is a real child of this session, with the same substrate and ceiling.
				const rows = (await session.listRlmSubagents()).subagents;
				expect(rows.map((r) => r.session_name)).toEqual(["adder"]);
				const child = session.getRlmChildSession(rows[0]!.rlm_child_id)!;
				expect(child.getActiveToolNames()).toEqual(["neurajl"]);
				expect(child.getToolDefinition("neurajl")!.description).toBe(tool.description);

				// Spawned in one call, collected in a later one.
				h.setResponses([fauxAssistantMessage("second answer")]);
				await call('h2 = Neura.rlm.spawn("another"; name = "second"); h2.name');
				const later = textOf(await call("only(Neura.rlm.collect(h2; timeout_ms = 40_000)).answer_preview"));
				expect(later).toContain('"second answer"');
				expect(
					textOf(await call('join(sort([s.session_name for s in Neura.rlm.list_subagents()]), ",")')),
				).toContain('"adder,second"');

				// A child whose model fails: Julia reports exactly what the chassis reports.
				h.setResponses(
					Array.from({ length: 6 }, () =>
						fauxAssistantMessage("", { stopReason: "error", errorMessage: "child provider exploded" }),
					),
				);
				const failed = textOf(
					await call(
						'f = Neura.rlm.spawn("fail"; name = "failing"); r = only(Neura.rlm.collect(f; timeout_ms = 40_000)); ' +
							'string(r.rlm_child_id, "|", r.status, "|", r.error)',
					),
				);
				const [failedId, julStatus, julError] = failed.replace(/^"|"$/g, "").split("|");
				const chassis = (await session.collectRlmChildren([failedId!], 0)).results[0]!;
				expect([julStatus, julError]).toEqual([chassis.status, String(chassis.error ?? "nothing")]);
				h.setResponses([]);

				// The host's own errors reach Julia as errors.
				await expect(call('Neura.rlm.spawn("dup"; name = "adder")')).rejects.toThrow(/adder/);
				await expect(call('Neura.rlm.delete_subagent("nobody")')).rejects.toThrow(/nobody/);
				expect(textOf(await call('Neura.rlm.delete_subagent("second").session_name'))).toContain('"second"');
			},
			// test-policy: allow explicit-test-timeout -- starts real sandboxed Julia kernels for the parent and each child
			600_000,
		);

		// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
		it.skipIf(skipIfNeurajlUnavailable())(
			"without the permission nothing is spawned, and the description does not offer it",
			async () => {
				const { session, tool, call } = await rlmSession({});
				expect(tool.description).not.toContain("Neura.rlm");
				await expect(call('Neura.rlm.spawn("x"; name = "w")')).rejects.toThrow(
					/host_request not in this session's ceiling/,
				);
				expect((await session.listRlmSubagents()).subagents).toEqual([]);
			},
			// test-policy: allow explicit-test-timeout -- starts a real sandboxed Julia kernel
			300_000,
		);

		// test-policy: allow conditional-or-disabled-test -- needs bwrap and a host Julia project with Neura installed
		it.skipIf(skipIfNeurajlUnavailable())(
			"a child outlives the kernel that spawned it, and the revived kernel finds it",
			async () => {
				const { call, harness: h } = await rlmSession(rlmCeiling, 8);
				h.setResponses([fauxAssistantMessage("survived")]);
				await call('h = Neura.rlm.spawn("outlive me"; name = "survivor"); h.name');
				await expect(call("s = 0; while true; s += 1; end")).rejects.toThrow(/the kernel stopped/);
				const after = textOf(
					await call(
						'r = only(Neura.rlm.collect("survivor"; timeout_ms = 5_000)); (r.session_name, r.answer_preview)',
					),
				);
				expect(after).toMatch(/NEW kernel/);
				expect(after).toContain('("survivor", "survived")');
			},
			// test-policy: allow explicit-test-timeout -- starts real sandboxed Julia kernels and kills one
			600_000,
		);
	});
});
