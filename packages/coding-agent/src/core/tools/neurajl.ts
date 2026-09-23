import { spawn } from "child_process";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { type Static, Type } from "typebox";
import type { SessionBaseToolsFactory } from "../agent-session.js";
import type { ToolDefinition } from "../extensions/types.js";
import { getShellEnv, killProcessTree, trackDetachedChildPid, untrackDetachedChildPid } from "../../utils/shell.js";
import { wrapToolDefinition } from "./tool-definition-wrapper.js";

/**
 * NIRA-Prime integration point: exposes NeuraJL (ijulia-operator-lab) as this
 * fork's operator surface, via `baseToolsFactory` rather than
 * `baseToolsOverride` -- deliberately, not the boundary
 * docs/NIRA_OPERATOR_SURFACE_STAGING.md names, because `baseToolsFactory` is
 * built for exactly this shape (construct once per agent session, including
 * per RLM child, with an explicit `dispose`) and NeuraJL's whole thesis this
 * pass is real session persistence -- `baseToolsOverride` shares one static
 * tool map across however many sessions ask for it, which would mean every
 * agent session (and every RLM child) silently sharing ONE Julia kernel's
 * mutable bindings. That is exactly the failure mode NeuraJL's own
 * C_child ⊆ C_caller authority model exists to prevent one level down
 * (see ijulia-operator-lab/docs/THREAT_MODEL.md); reusing `baseToolsOverride`
 * here would reintroduce the same problem at the chassis layer instead.
 *
 * Unlike `neurabash.ts`'s current first pass (explicitly one-shot,
 * "session persistence... is real future work, not done here"), this tool
 * spawns ONE persistent `security/session_cli.py` process per agent session
 * (via `baseToolsFactory`'s per-session construction) and keeps it alive for
 * that session's whole lifetime -- real bindings, real compiled methods,
 * surviving across tool calls the way `ipython`'s kernel does, backed by
 * NeuraJL's own adversarially-tested persistent session
 * (ijulia-operator-lab/security/session.py's `NeuraSession`).
 *
 * Scope deliberately kept narrow, matching `neurabash.ts`'s own stated first
 * pass: no RLM sub-agent spawning surfaced through THIS tool (RLM already
 * gets its own base-tool override per child per `baseToolsFactory`'s own
 * contract -- a child session gets its OWN NeuraJL process, not this
 * parent's), no Python-skills bridge, no diff/attachment display protocol.
 * `ipython.ts`'s kernel owns all of that today; this tool intentionally
 * replaces it for the NeuraJL condition (see the staging doc: "omit the
 * IPython kernel rather than merely leave it inactive").
 */

const neurajlSchema = Type.Object({
	code: Type.String({
		description:
			"Julia source to evaluate in this agent session's persistent NeuraJL kernel. Real bindings, functions, and compiled methods survive across calls within this session (and are isolated from every other session/RLM child, each of which gets its own kernel). Full, unrestricted Julia language power -- eval, ccall, metaprogramming, Base, Pkg -- runs OS-sandboxed; broker-mediated host effects (filesystem writes outside the workspace, network, package installs) are gated by this session's fixed capability ceiling, not by anything in this tool call.",
	}),
	ephemeral: Type.Optional(
		Type.Boolean({
			description:
				"Run this code in a real, disposable, OS-sandboxed CHILD process instead of the persistent kernel -- for throwaway/generated helper code you do not want to leave bindings or compiled methods behind in the session's own mind. Defaults to false (persistent). Ephemeral code gets NO broker-mediated authority by default (network/filesystem/package access), regardless of what the persistent session itself is allowed -- an unusual need for one is a signal the code belongs in the persistent kernel instead, not a reason to widen this flag's default.",
		}),
	),
});

export type NeurajlToolInput = Static<typeof neurajlSchema>;

export interface NeurajlToolDetails {
	success: boolean;
	epoch?: string;
	durationMs?: number;
}

export interface NeurajlToolOptions {
	/** Absolute path to security/session_cli.py in the ijulia-operator-lab checkout. No default: unset fails closed at first use, not silently. */
	sessionCliPath?: string;
	/** Absolute path to the ijulia-operator-lab checkout itself (session_cli.py's --repo-dir). Defaults to session_cli.py's own parent's parent. */
	repoDir?: string;
	/** A Julia dev project with Neura (dev-installed) + IJulia available -- see ijulia-operator-lab/docs/EXPERIMENT_002_AUTHORITY.md's Naming section for how one is built. No default: unset fails closed. */
	projectDir?: string;
	/** Python interpreter to run session_cli.py with. Default: "python3". */
	pythonBin?: string;
	/**
	 * This session's own capability ceiling -- see
	 * ijulia-operator-lab/docs/CAPABILITY_MODEL.md. Default: `{}` (full
	 * language power inside the sandbox, zero broker-mediated authority).
	 * An empty ceiling is a deliberate, safe default for a first
	 * integration pass, not an oversight -- widen it only for a condition
	 * that specifically needs a broker-mediated capability.
	 */
	ceiling?: Record<string, unknown>;
	/** Grant the top-level worker raw network access (bypassing broker mediation for network specifically). Default: false. Distinct from the `network_access` broker capability, which stays broker-mediated regardless of this flag. */
	network?: boolean;
	/** Per-turn timeout in seconds, forwarded to NeuraSession's own turn_timeout. Default: 60. */
	turnTimeout?: number;
	/** How long to wait for the child process's HELLO line before giving up. Default: 30s (real cold-start: a fresh depot clone plus a fresh sandboxed Julia launch, not free). */
	startupTimeoutMs?: number;
}

interface PendingTurn {
	resolve: (msg: Record<string, unknown>) => void;
	reject: (err: Error) => void;
}

function resolveSessionCliPath(options?: NeurajlToolOptions): string {
	const path = options?.sessionCliPath ?? process.env.NEURAJL_SESSION_CLI;
	if (!path) {
		throw new Error(
			"neurajl: session_cli.py path not configured (options.sessionCliPath / NEURAJL_SESSION_CLI). " +
				"Point it at <ijulia-operator-lab checkout>/security/session_cli.py before this tool can start a session.",
		);
	}
	return path;
}

function resolveProjectDir(options?: NeurajlToolOptions): string {
	const dir = options?.projectDir ?? process.env.NEURAJL_PROJECT_DIR;
	if (!dir) {
		throw new Error(
			"neurajl: no Julia dev project configured (options.projectDir / NEURAJL_PROJECT_DIR) -- " +
				"see ijulia-operator-lab/docs/EXPERIMENT_002_AUTHORITY.md's Naming section for how to build one " +
				"(Neura dev-installed + IJulia).",
		);
	}
	return dir;
}

/**
 * Starts one persistent `session_cli.py` process, wires its newline-JSON
 * stdio protocol to a request-id-keyed promise map, and returns the ready
 * `{tools, dispose}` pair `SessionBaseToolsFactory` expects.
 *
 * Session identity is explicit here too, not assumed: this function does not
 * resolve until the child's own HELLO line (carrying its own real epoch,
 * generated by NeuraSession itself, not by this process) has been read --
 * mirroring the same discipline `security/session.py`'s `NeuraSession`
 * already holds toward `scripts/session_loop.jl`, one layer further out.
 */
async function startNeurajlSession(
	cwd: string,
	options: NeurajlToolOptions | undefined,
): Promise<{ tool: AgentTool<typeof neurajlSchema, NeurajlToolDetails>; dispose: () => Promise<void> }> {
	const cliPath = resolveSessionCliPath(options);
	const projectDir = resolveProjectDir(options);
	const pythonBin = options?.pythonBin ?? process.env.NEURAJL_PYTHON ?? "python3";
	const startupTimeoutMs = options?.startupTimeoutMs ?? 30_000;

	const args = [cliPath, "--project-dir", projectDir, "--ceiling", JSON.stringify(options?.ceiling ?? {})];
	if (options?.repoDir) args.push("--repo-dir", options.repoDir);
	if (options?.network) args.push("--network");
	if (options?.turnTimeout) args.push("--turn-timeout", String(options.turnTimeout));

	const child = spawn(pythonBin, args, { cwd, env: getShellEnv(), stdio: ["pipe", "pipe", "pipe"] });
	if (child.pid) trackDetachedChildPid(child.pid);

	const pending = new Map<string, PendingTurn>();
	let nextRequestId = 0;
	let dead = false;
	let deadReason = "";
	let stdoutBuffer = "";
	let stderrTail = "";

	const failAllPending = (reason: string) => {
		dead = true;
		deadReason = reason;
		for (const waiter of pending.values()) waiter.reject(new Error(reason));
		pending.clear();
	};

	child.stderr?.on("data", (chunk: Buffer) => {
		stderrTail = (stderrTail + chunk.toString("utf8")).slice(-4000);
	});

	const helloPromise = new Promise<Record<string, unknown>>((resolveHello, rejectHello) => {
		let resolved = false;
		const timeoutHandle = setTimeout(() => {
			if (resolved) return;
			resolved = true;
			rejectHello(
				new Error(`neurajl: session process did not send HELLO within ${startupTimeoutMs}ms. stderr: ${stderrTail}`),
			);
		}, startupTimeoutMs);

		child.stdout?.on("data", (chunk: Buffer) => {
			stdoutBuffer += chunk.toString("utf8");
			let newlineIndex: number;
			// biome-ignore lint: while-assignment is the clearest shape for draining a growing buffer line by line
			while ((newlineIndex = stdoutBuffer.indexOf("\n")) !== -1) {
				const line = stdoutBuffer.slice(0, newlineIndex);
				stdoutBuffer = stdoutBuffer.slice(newlineIndex + 1);
				if (!line.trim()) continue;

				let message: Record<string, unknown>;
				try {
					message = JSON.parse(line);
				} catch {
					continue; // a malformed line from the bridge is not this tool's problem to surface as a turn result
				}

				if (!resolved) {
					resolved = true;
					clearTimeout(timeoutHandle);
					if (message.kind === "HELLO") resolveHello(message);
					else rejectHello(new Error(`neurajl: unexpected first line from session_cli.py: ${line}`));
					continue;
				}

				const requestId = message.request_id !== undefined && message.request_id !== null ? String(message.request_id) : undefined;
				const waiter = requestId !== undefined ? pending.get(requestId) : undefined;
				if (waiter) {
					pending.delete(requestId as string);
					waiter.resolve(message);
				}
			}
		});
	});

	child.on("exit", (code) => {
		if (child.pid) untrackDetachedChildPid(child.pid);
		failAllPending(`neurajl: session process exited (code ${code}). stderr: ${stderrTail}`);
	});
	child.on("error", (err) => {
		failAllPending(`neurajl: session process failed to start: ${err.message}`);
	});

	await helloPromise;

	async function turn(code: string, ephemeral: boolean | undefined): Promise<Record<string, unknown>> {
		if (dead) throw new Error(deadReason);
		const requestId = String(++nextRequestId);
		const request: Record<string, unknown> = { request_id: requestId, code };
		if (ephemeral) request.ephemeral = true;
		const responsePromise = new Promise<Record<string, unknown>>((resolve, reject) => {
			pending.set(requestId, { resolve, reject });
		});
		child.stdin?.write(`${JSON.stringify(request)}\n`);
		return responsePromise;
	}

	const definition: ToolDefinition<typeof neurajlSchema, NeurajlToolDetails> = {
		name: "neurajl",
		label: "neurajl",
		description:
			"Execute Julia code in this session's own persistent NeuraJL kernel: real state, real compiled methods, surviving across calls (unlike a one-shot interpreter invocation). Prefer this over guessing at numerical, symbolic, or structured computation in-context. Set `ephemeral: true` for disposable generated code you deliberately do not want to leave behind in the persistent kernel's own namespace. Does not support spawning sub-agents, file diffs, or image attachments.",
		promptSnippet: "neurajl - persistent, stateful Julia kernel with a broker-mediated authority fence",
		executionMode: "sequential",
		parameters: neurajlSchema,
		execute: async (_toolCallId, params) => {
			const started = Date.now();
			let response: Record<string, unknown>;
			try {
				response = await turn(params.code, params.ephemeral);
			} catch (err) {
				const message = err instanceof Error ? err.message : String(err);
				return { content: [{ type: "text", text: `NeuraJL session error: ${message}` }], details: { success: false }, isError: true };
			}

			const success = response.success === true;
			const errorText = typeof response.error === "string" ? response.error : undefined;
			const data = response.data;
			const text = success
				? data === null || data === undefined
					? "(no output)"
					: typeof data === "string"
						? data
						: JSON.stringify(data)
				: `Error: ${errorText ?? "unknown error"}`;

			const details: NeurajlToolDetails = {
				success,
				epoch: typeof response.epoch === "string" ? response.epoch : undefined,
				durationMs: Date.now() - started,
			};
			return { content: [{ type: "text", text }], details, isError: !success };
		},
	};

	return {
		tool: wrapToolDefinition(definition),
		dispose: async () => {
			try {
				child.stdin?.end();
			} catch {
				// already closed; nothing to do
			}
			await new Promise<void>((resolve) => {
				const forceKillTimeout = setTimeout(() => {
					if (child.pid) killProcessTree(child.pid);
					resolve();
				}, 5000);
				child.once("exit", () => {
					clearTimeout(forceKillTimeout);
					resolve();
				});
			});
		},
	};
}

/**
 * `SessionBaseToolsFactory` for NeuraJL -- see the module docstring above for
 * why this is the right boundary (not `baseToolsOverride`). Called once per
 * agent session, including once per RLM child (each getting its own,
 * independent NeuraJL process/kernel -- never sharing the parent's mutable
 * bindings), per `baseToolsFactory`'s own documented contract in
 * agent-session.ts.
 */
export function createNeurajlBaseToolsFactory(cwd: string, options?: NeurajlToolOptions): SessionBaseToolsFactory {
	return (_sessionId: string) => {
		let sessionPromise: ReturnType<typeof startNeurajlSession> | undefined;

		function ensureStarted() {
			if (!sessionPromise) sessionPromise = startNeurajlSession(cwd, options);
			return sessionPromise;
		}

		// The tool registered here is a thin proxy: AgentSession needs a real
		// tool object synchronously (`baseToolsFactory` is not async), but
		// starting the actual NeuraJL process is. The first real call lazily
		// starts it and every call (including the first) awaits readiness
		// before sending a turn -- callers see a normal async tool call, not
		// a two-phase "start, then use" API.
		const proxyDefinition: ToolDefinition<typeof neurajlSchema, NeurajlToolDetails> = {
			name: "neurajl",
			label: "neurajl",
			description:
				"Execute Julia code in this session's own persistent NeuraJL kernel: real state, real compiled methods, surviving across calls (unlike a one-shot interpreter invocation). Prefer this over guessing at numerical, symbolic, or structured computation in-context. Set `ephemeral: true` for disposable generated code you deliberately do not want to leave behind in the persistent kernel's own namespace. Does not support spawning sub-agents, file diffs, or image attachments.",
			promptSnippet: "neurajl - persistent, stateful Julia kernel with a broker-mediated authority fence",
			executionMode: "sequential",
			parameters: neurajlSchema,
			execute: async (toolCallId, params, signal, onUpdate, ctx) => {
				const { tool } = await ensureStarted();
				return tool.execute(toolCallId, params, signal, onUpdate, ctx as never);
			},
		};

		return {
			tools: { neurajl: wrapToolDefinition(proxyDefinition) },
			dispose: async () => {
				if (!sessionPromise) return; // never actually started -- nothing to clean up
				const { dispose } = await sessionPromise;
				await dispose();
			},
		};
	};
}
