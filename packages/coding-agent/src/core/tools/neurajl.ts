import { spawn } from "child_process";
import { readFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { type Static, Type } from "typebox";
import { getShellEnv, killProcessTree, trackDetachedChildPid, untrackDetachedChildPid } from "../../utils/shell.js";
import type { SessionBaseToolsFactory } from "../agent-session.js";
import type { ToolDefinition } from "../extensions/types.js";
import { wrapToolDefinition } from "./tool-definition-wrapper.js";

/**
 * NIRA-Prime integration point: exposes NeuraJL (neurajl-operator-lab) as this
 * fork's operator surface.
 *
 * It uses `baseToolsFactory`, not `baseToolsOverride`: the factory builds tools
 * once per agent session (including each RLM child) with a dispose hook, so
 * every session gets its own Julia kernel. A shared override map would let
 * every session and RLM child mutate one kernel's bindings, the same failure
 * NeuraJL's C_child ⊆ C_caller model prevents one level down.
 *
 * Each session drives one `security/session_cli.py` process over
 * newline-delimited JSON. That process owns a bubblewrap-contained Julia
 * worker whose working directory is the agent's own `cwd`, bound writable.
 *
 * A worker that dies (turn timeout, abort, crash) is not silently replaced.
 * The next call starts a new kernel and its result says, first, that every
 * earlier binding is gone and which epoch replaced which.
 */

const neurajlSchema = Type.Object({
	code: Type.String({
		description: `Julia source to evaluate in this session's persistent NeuraJL kernel. The working directory is the task workspace. Bindings, functions and compiled methods survive across calls. Everything printed (println, @show, @warn, display, output of run(\`cmd\`) and sh"cmd") is returned along with the value of the last expression. To write a file's full text (source code, JSON, CSV), put the text in payload and call write(path, PAYLOAD) instead of embedding it in a Julia string literal.`,
	}),
	payload: Type.Optional(
		Type.String({
			description:
				"Text bound as PAYLOAD for this call only, such as the complete contents of a file to write with write(path, PAYLOAD). It is not parsed as Julia, so quotes, triple quotes, $ and backslashes need no escaping.",
		}),
	),
	ephemeral: Type.Optional(
		Type.Boolean({
			description:
				"Run this code in a fresh, disposable Julia process instead of the persistent kernel: it sees none of the kernel's bindings, leaves none behind, and cannot see the task workspace. Starting it takes several seconds. Defaults to false.",
		}),
	),
});

export type NeurajlToolInput = Static<typeof neurajlSchema>;

export interface NeurajlToolDetails {
	success: boolean;
	epoch?: string;
	restartedFromEpoch?: string;
	durationMs?: number;
	outputTruncated?: boolean;
}

export interface NeurajlToolOptions {
	/** Absolute path to security/session_cli.py. Unset fails closed at first use. */
	sessionCliPath?: string;
	/** The neurajl-operator-lab checkout (session_cli.py's --repo-dir). Defaults to session_cli.py's grandparent. */
	repoDir?: string;
	/** A Julia project with Neura dev-installed. Unset fails closed at first use. */
	projectDir?: string;
	/** Python interpreter for session_cli.py. Default: "python3". */
	pythonBin?: string;
	/** This session's capability ceiling (see CAPABILITY_MODEL.md). Default `{}`: no broker-mediated authority. */
	ceiling?: Record<string, unknown>;
	/** Give the worker raw network access. Default: false. */
	network?: boolean;
	/**
	 * Per-turn limit in seconds. The worker interrupts a call still waiting at the limit and keeps the kernel;
	 * NeuraSession kills a worker that has not answered 12s later (compute that never yields). Default: 60.
	 */
	turnTimeout?: number;
	/** How long to wait for the kernel's HELLO. Default: 180s, since a cold `using Neura` precompile takes ~40s. */
	startupTimeoutMs?: number;
	/** Model-visible characters per result; the middle of longer output is elided. Default: unlimited. */
	maxOutputChars?: number;
	/**
	 * Directory under which each session's kernel saves its state after every completed call, one
	 * subdirectory per session id, so a kernel that replaces it (after a crash, a kill, or a resumed
	 * session) revives it. Default: `neurajl-state` in the OS temp directory. `false` turns saving off.
	 */
	stateRoot?: string | false;
}

interface PendingTurn {
	resolve: (msg: Record<string, unknown>) => void;
	reject: (err: Error) => void;
}

interface NeurajlKernel {
	epoch: string;
	/** This kernel found a saved state and revives it; its first reply says what it could and could not. */
	revival: boolean;
	isDead: () => boolean;
	turn: (
		code: string,
		options: { ephemeral?: boolean; payload?: string },
		signal: AbortSignal | undefined,
	) => Promise<Record<string, unknown>>;
	dispose: () => Promise<void>;
}

function requiredSetting(value: string | undefined, name: string): string {
	if (!value) throw new Error(`neurajl: ${name} is not configured`);
	return value;
}

export function truncateMiddle(
	text: string,
	maxChars: number | undefined,
	fullText?: string,
): { text: string; truncated: boolean } {
	if (maxChars === undefined || text.length <= maxChars) return { text, truncated: false };
	const notice = `\n[... ${text.length - maxChars} characters elided${fullText ? `; ${fullText}` : ""} ...]\n`;
	const keep = Math.max(0, maxChars - notice.length);
	const head = Math.ceil(keep / 2);
	return { text: text.slice(0, head) + notice + text.slice(text.length - (keep - head)), truncated: true };
}

export function formatNeurajlResponse(response: Record<string, unknown>): string {
	const parts: string[] = [];
	const output = typeof response.output === "string" ? response.output.trimEnd() : "";
	if (output) parts.push(output);
	if (response.success === true) {
		const display =
			typeof response.display === "string"
				? response.display
				: response.data === null || response.data === undefined
					? undefined
					: typeof response.data === "string"
						? response.data
						: JSON.stringify(response.data);
		if (display !== undefined) parts.push(output ? `=> ${display}` : display);
	} else {
		parts.push(`Error: ${typeof response.error === "string" ? response.error : "unknown error"}`);
	}
	return parts.join("\n") || "(no output)";
}

async function startKernel(
	cwd: string,
	options: NeurajlToolOptions | undefined,
	stateDir: string | undefined,
): Promise<NeurajlKernel> {
	const cliPath = requiredSetting(options?.sessionCliPath ?? process.env.NEURAJL_SESSION_CLI, "session_cli.py path");
	const projectDir = requiredSetting(
		options?.projectDir ?? process.env.NEURAJL_PROJECT_DIR,
		"Julia project directory",
	);
	const pythonBin = options?.pythonBin ?? process.env.NEURAJL_PYTHON ?? "python3";
	const startupTimeoutMs = options?.startupTimeoutMs ?? 180_000;

	const args = [
		"-u",
		cliPath,
		"--project-dir",
		projectDir,
		"--ceiling",
		JSON.stringify(options?.ceiling ?? {}),
		"--workspace-dir",
		cwd,
		"--startup-timeout",
		String(startupTimeoutMs / 1000),
	];
	if (options?.repoDir) args.push("--repo-dir", options.repoDir);
	if (options?.network) args.push("--network");
	if (options?.turnTimeout) args.push("--turn-timeout", String(options.turnTimeout));
	if (stateDir) args.push("--state-dir", stateDir);

	const child = spawn(pythonBin, args, { cwd, env: getShellEnv(), stdio: ["pipe", "pipe", "pipe"] });
	if (child.pid) trackDetachedChildPid(child.pid);

	const pending = new Map<string, PendingTurn>();
	let nextRequestId = 0;
	let deadReason: string | undefined;
	let stdoutBuffer = "";
	let stderrTail = "";
	let resolveHello: (message: Record<string, unknown>) => void = () => {};
	let rejectHello: (error: Error) => void = () => {};
	const helloPromise = new Promise<Record<string, unknown>>((resolve, reject) => {
		resolveHello = resolve;
		rejectHello = reject;
	});
	let helloSeen = false;

	const markDead = (reason: string) => {
		if (deadReason === undefined) deadReason = reason;
		if (!helloSeen) rejectHello(new Error(reason));
		for (const waiter of pending.values()) waiter.reject(new Error(reason));
		pending.clear();
	};
	// The reply that reports the death is still delivered; only later turns fail.
	const markDeadAfterReply = (reason: string) => {
		if (deadReason === undefined) deadReason = reason;
	};
	const exited = new Promise<void>((resolve) => child.once("close", () => resolve()));

	child.stderr?.on("data", (chunk: Buffer) => {
		stderrTail = (stderrTail + chunk.toString("utf8")).slice(-4000);
	});
	child.stdout?.on("data", (chunk: Buffer) => {
		stdoutBuffer += chunk.toString("utf8");
		let newlineIndex = stdoutBuffer.indexOf("\n");
		while (newlineIndex !== -1) {
			const line = stdoutBuffer.slice(0, newlineIndex);
			stdoutBuffer = stdoutBuffer.slice(newlineIndex + 1);
			newlineIndex = stdoutBuffer.indexOf("\n");
			if (!line.trim()) continue;
			let message: Record<string, unknown>;
			try {
				message = JSON.parse(line);
			} catch {
				markDead(`neurajl: bridge sent a non-JSON line: ${line.slice(0, 200)}`);
				child.kill("SIGTERM");
				return;
			}
			if (!helloSeen) {
				helloSeen = true;
				if (message.kind === "HELLO" && typeof message.epoch === "string") resolveHello(message);
				else {
					const reason = `neurajl: kernel failed to start: ${String(message.error ?? line)}`;
					rejectHello(new Error(reason));
					markDead(reason);
				}
				continue;
			}
			const requestId =
				message.request_id === undefined || message.request_id === null ? undefined : String(message.request_id);
			const waiter = requestId === undefined ? undefined : pending.get(requestId);
			if (message.session_dead === true) markDeadAfterReply(String(message.error ?? "neurajl: kernel stopped"));
			if (waiter && requestId !== undefined) {
				pending.delete(requestId);
				waiter.resolve(message);
			}
		}
	});
	// "close", not "exit": the bridge writes its final response and exits at
	// once, and "exit" can fire before that last stdout chunk is delivered.
	child.on("close", (code, signal) => {
		if (child.pid) untrackDetachedChildPid(child.pid);
		markDead(`neurajl: kernel process exited (${signal ?? code}). stderr: ${stderrTail}`);
	});
	child.on("error", (err) => markDead(`neurajl: kernel process failed to start: ${err.message}`));

	const startupTimer = setTimeout(() => {
		markDead(`neurajl: kernel did not start within ${startupTimeoutMs}ms. stderr: ${stderrTail}`);
		child.kill("SIGTERM");
	}, startupTimeoutMs + 5000);
	let hello: Record<string, unknown>;
	try {
		hello = await helloPromise;
	} finally {
		clearTimeout(startupTimer);
	}

	// session_cli.py tears down its sandbox and depot clone on stdin EOF or
	// SIGTERM. SIGKILL is the last resort because it skips that cleanup.
	const stop = async () => {
		if (child.exitCode !== null || child.signalCode !== null) return;
		child.stdin?.end();
		const graceful = await Promise.race([exited.then(() => true), sleep(10_000).then(() => false)]);
		if (graceful) return;
		child.kill("SIGTERM");
		const terminated = await Promise.race([exited.then(() => true), sleep(20_000).then(() => false)]);
		if (!terminated && child.pid) killProcessTree(child.pid);
	};

	return {
		epoch: String(hello.epoch),
		revival: hello.revival === true,
		isDead: () => deadReason !== undefined,
		turn: (code, { ephemeral, payload }, signal) => {
			if (deadReason !== undefined) return Promise.reject(new Error(deadReason));
			if (signal?.aborted) return Promise.reject(new Error("neurajl: aborted"));
			const requestId = String(++nextRequestId);
			const request: Record<string, unknown> = { request_id: requestId, code };
			if (ephemeral) request.ephemeral = true;
			if (payload !== undefined) request.payload = payload;
			return new Promise<Record<string, unknown>>((resolve, reject) => {
				// The protocol is one request, one response, in order. A turn
				// abandoned mid-flight leaves the kernel busy with no way to
				// resynchronize, so an abort ends this kernel.
				const onAbort = () => {
					markDead("neurajl: turn aborted; kernel stopped");
					child.kill("SIGTERM");
				};
				signal?.addEventListener("abort", onAbort, { once: true });
				pending.set(requestId, {
					resolve: (message) => {
						signal?.removeEventListener("abort", onAbort);
						resolve(message);
					},
					reject: (error) => {
						signal?.removeEventListener("abort", onAbort);
						reject(error);
					},
				});
				child.stdin?.write(`${JSON.stringify(request)}\n`);
			});
		},
		dispose: stop,
	};
}

const KERNEL_STOPPED =
	"[neurajl: the kernel stopped. Output printed during this call and every binding, function and loaded package are gone; files written to the workspace remain. The next call starts a new kernel.]";
const KERNEL_STOPPED_REVIVING =
	"[neurajl: the kernel stopped. Output printed during this call is gone; files written to the workspace remain. The next call starts a new kernel, which revives what it can of the state at the end of the last completed call and says what it could not.]";

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms).unref?.());
}

// Names under [deps] in the session project's Project.toml. Neura is the
// kernel itself, not something a turn loads.
function projectPackages(projectDir: string | undefined): string[] {
	if (!projectDir) return [];
	let text: string;
	try {
		text = readFileSync(join(projectDir, "Project.toml"), "utf8");
	} catch {
		return [];
	}
	const deps = /^\[deps\]\s*$([\s\S]*?)(?=^\[|(?![\s\S]))/m.exec(text)?.[1] ?? "";
	return [...deps.matchAll(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=/gm)].map((m) => m[1]).filter((name) => name !== "Neura");
}

function neurajlDescription(options: NeurajlToolOptions | undefined): string {
	const timeout = options?.turnTimeout ?? 60;
	const packages = projectPackages(options?.projectDir ?? process.env.NEURAJL_PROJECT_DIR);
	const loadable = ["the Julia standard library", ...packages].join(", ");
	return [
		"Execute Julia in this session's persistent NeuraJL kernel. The working directory is the task workspace; read and edit files with Julia's file I/O. Bindings, functions, types and loaded packages persist across calls, and ans is the last call's value. Printed output and the last expression's value are returned.",
		'Shell: sh"cmd" (or bash("cmd")) runs bash, so pipes, globs, redirects and && work, and returns ShellResult(exitcode, stdout, stderr) after printing the output. In sh"..." the $ belongs to the shell; in an ordinary "..." string it is Julia interpolation. run(`prog args`) starts one program without a shell.',
		"To write a file's text, put the text in payload and call write(path, PAYLOAD): the payload is not parsed as Julia, so it needs no escaping.",
		"A package loaded from the workspace is reloaded when its source files change, so code and tests run in the kernel see your edits.",
		`Each call may run for ${timeout}s. Waiting work (sleep, run, reading a process or file) is then interrupted and the kernel keeps every binding; compute that never yields cannot be interrupted, so the kernel stops and the next call starts a fresh one and says so.`,
		`Loadable packages: ${loadable}.${options?.network ? "" : " There is no network access, so Pkg.add cannot install more."} kernelinfo() describes the kernel; varinfo() lists your bindings.`,
	].join(" ");
}

/**
 * `SessionBaseToolsFactory` for NeuraJL: one kernel per agent session,
 * including each RLM child, started when the session's tools are built so
 * that its startup overlaps the model's first request.
 */
export function createNeurajlBaseToolsFactory(cwd: string, options?: NeurajlToolOptions): SessionBaseToolsFactory {
	return (sessionId: string) => {
		const stateRoot = options?.stateRoot ?? join(tmpdir(), "neurajl-state");
		const stateDir = stateRoot === false ? undefined : join(stateRoot, sessionId.replace(/[^A-Za-z0-9._-]/g, "_"));
		let kernelPromise: Promise<NeurajlKernel> | undefined;
		let lastEpoch: string | undefined;
		let disposed = false;
		// The kernel lists its bindings in every reply. When it dies, the
		// model is told which ones were lost, so it can rebuild what it needs
		// instead of relying on its own memory of the session.
		let lastBindings: string[] = [];
		const lostBindings = () => (lastBindings.length === 0 ? "" : ` Lost bindings: ${lastBindings.join(", ")}.`);
		const stoppedNotice = () => (stateDir ? KERNEL_STOPPED_REVIVING : `${KERNEL_STOPPED}${lostBindings()}`);

		// Returns the live kernel, starting one if none exists or the last one
		// died. `restartedFrom` names the dead kernel's epoch.
		async function liveKernel(): Promise<{ kernel: NeurajlKernel; restartedFrom?: string }> {
			if (disposed) throw new Error("neurajl: session disposed");
			if (kernelPromise) {
				const current = await kernelPromise.catch(() => undefined);
				if (current && !current.isDead()) return { kernel: current };
				if (current) await current.dispose();
			}
			const restartedFrom = lastEpoch;
			kernelPromise = startKernel(cwd, options, stateDir);
			const kernel = await kernelPromise;
			lastEpoch = kernel.epoch;
			return { kernel, restartedFrom };
		}

		// Started lazily, the first call waited for the whole startup (~3s).
		// A start that fails here is retried by that first call, which then
		// reports the failure.
		liveKernel().catch(() => undefined);

		const definition: ToolDefinition<typeof neurajlSchema, NeurajlToolDetails> = {
			name: "neurajl",
			label: "neurajl",
			description: neurajlDescription(options),
			promptSnippet: "neurajl - persistent Julia kernel in the task workspace, OS-sandboxed",
			executionMode: "sequential",
			parameters: neurajlSchema,
			// The agent loop marks a tool result as an error only when execute
			// throws; an `isError` field on a returned result is ignored.
			execute: async (_toolCallId, params, signal) => {
				const started = Date.now();
				const { kernel, restartedFrom } = await liveKernel();
				const notice =
					restartedFrom === undefined
						? ""
						: kernel.revival
							? `[neurajl: the previous kernel (epoch ${restartedFrom}) stopped; this call ran in a NEW kernel (epoch ${kernel.epoch}), which revived the state saved at the end of the last completed call. Its report below says what was restored, rebuilt, or lost.]\n`
							: `[neurajl: the previous kernel (epoch ${restartedFrom}) stopped; this call ran in a NEW kernel (epoch ${kernel.epoch}). All earlier bindings, functions and loaded packages are gone.${lostBindings()} Files written to the workspace remain.]\n`;
				let response: Record<string, unknown>;
				try {
					response = await kernel.turn(
						params.code,
						{ ephemeral: params.ephemeral, payload: params.payload },
						signal,
					);
				} catch (err) {
					const stopped = kernel.isDead() ? `\n${stoppedNotice()}` : "";
					throw new Error(`${notice}${err instanceof Error ? err.message : String(err)}${stopped}`);
				}
				// The kernel keeps what each call printed, so elided output can be
				// read back in pieces instead of recomputed.
				const fullText =
					typeof response.call === "number"
						? `Neura.output(${response.call}) returns everything this call printed${response.success === true ? ", and ans its value" : ""}`
						: undefined;
				const { text, truncated } = truncateMiddle(
					formatNeurajlResponse(response),
					options?.maxOutputChars,
					fullText,
				);
				if (response.session_dead === true) throw new Error(`${notice}${text}\n${stoppedNotice()}`);
				if (Array.isArray(response.bindings)) lastBindings = response.bindings.map(String);
				if (response.success !== true) throw new Error(`${notice}${text}`);
				return {
					content: [{ type: "text", text: `${notice}${text}` }],
					details: {
						success: true,
						epoch: kernel.epoch,
						restartedFromEpoch: restartedFrom,
						durationMs: Date.now() - started,
						outputTruncated: truncated,
					},
				};
			},
		};

		return {
			tools: { neurajl: wrapToolDefinition(definition) },
			// Compaction drops the calls that built the kernel's state; the
			// kernel keeps it. Without this the model no longer knew what it had.
			stateAfterCompaction: async () => {
				// Experiment switch: suppresses the note for an A/B of its effect.
				if (process.env.NEURAJL_COMPACTION_NOTE === "0") return null;
				const kernel = kernelPromise ? await kernelPromise.catch(() => undefined) : undefined;
				if (!kernel || kernel.isDead()) return null;
				const detail =
					lastBindings.length > 0
						? ` These bindings are defined (with the call that last set each): ${lastBindings.join(", ")}.`
						: " You have not defined any bindings yet.";
				return {
					customType: "neurajl_state",
					content: `[neurajl-state]\n\nYour NeuraJL kernel persisted through compaction; its bindings, functions, types and loaded packages are still available.${detail}`,
				};
			},
			dispose: async () => {
				disposed = true;
				if (!kernelPromise) return;
				const kernel = await kernelPromise.catch(() => undefined);
				await kernel?.dispose();
			},
		};
	};
}
