import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import { spawn } from "child_process";
import { type Static, Type } from "typebox";
import { waitForChildProcess } from "../../utils/child-process.js";
import { getShellEnv, killProcessTree, trackDetachedChildPid, untrackDetachedChildPid } from "../../utils/shell.js";
import type { ToolDefinition } from "../extensions/types.js";
import { OutputAccumulator } from "./output-accumulator.js";
import { wrapToolDefinition } from "./tool-definition-wrapper.js";
import { DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, formatSize } from "./truncate.js";

/**
 * NIRA-Prime integration point: exposes NeuraBash (Project-LIRA-NeuraBash) as a
 * second, additive code-execution tool alongside `ipython`, NOT a replacement.
 *
 * Scope deliberately kept narrow for this first pass:
 *  - one-shot `--neura-profile=<profile> -c <code>` per call (NeuraBash's own
 *    "ephemeral logical session by default" mode, spec RT-009), not the
 *    persistent daemon session / binding-across-calls model NeuraBash also
 *    supports. Session persistence (bindings, Forge tools surviving across
 *    calls the way IPython's kernel namespace does) is real future work, not
 *    done here — see the decision doc for why.
 *  - no RLM sub-agent spawning, no Python-skills bridge, no diff/attachment
 *    display protocol, no inter-agent messaging. ipython.ts's kernel owns all
 *    of that today; NeuraBash has no equivalent yet. Removing ipython would
 *    silently break those, so it stays.
 */

const neurabashSchema = Type.Object({
	code: Type.String({
		description:
			"NeuraBash source to execute: ordinary Bash, or Bash with `|!>` JUL stages for exact math, matrices, and typed symbolic computation. Session state does not persist between calls yet — each call is an independent, ephemeral NeuraBash invocation.",
	}),
});

export type NeurabashToolInput = Static<typeof neurabashSchema>;

export interface NeurabashToolDetails {
	exitCode?: number | null;
	durationMs?: number;
	profile?: NeurabashSecurityProfile;
}

/**
 * Security Kernel V1 profiles (docs/SECURITY_KERNEL_V1_REPORT.md in the
 * NeuraBash repo, 2026-09-21). `workspace` is the closest match to the
 * ordinary bash/ipython tools' existing read-write-cwd semantics and is the
 * default here. `inherit` is deliberately not a sandbox; it is not offered
 * as a default.
 */
export type NeurabashSecurityProfile = "readonly" | "workspace" | "sandbox";

export interface NeurabashToolOptions {
	/** Absolute path to the neurabash binary. No default: an unset/missing binary fails closed. */
	binPath?: string;
	/** Default: "workspace". */
	profile?: NeurabashSecurityProfile;
	/**
	 * Persistent Julia depot / runtime directory, reused across calls so package
	 * precompilation and the daemon actually stay warm. Defaults under
	 * `~/.prime-agent/neurabash/`. A fresh temp dir per call would work but pays
	 * NeuraBash's full cold-start cost (multi-second per the current benchmark
	 * report) on every single invocation.
	 */
	depotDir?: string;
	runtimeDir?: string;
	env?: Record<string, string>;
	/** Command timeout in seconds. Default: no timeout. */
	timeout?: number;
}

function defaultStateDir(): string {
	return join(homedir(), ".prime-agent", "neurabash");
}

function resolveEnv(options: NeurabashToolOptions | undefined): NodeJS.ProcessEnv {
	const depotDir = options?.depotDir ?? join(defaultStateDir(), "depot");
	const runtimeDir = options?.runtimeDir ?? join(defaultStateDir(), "runtime");
	for (const dir of [depotDir, runtimeDir]) {
		if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
	}
	return {
		...getShellEnv(),
		...options?.env,
		JULIA_DEPOT_PATH: depotDir,
		XDG_RUNTIME_DIR: runtimeDir,
	};
}

function resolveBinPath(options: NeurabashToolOptions | undefined): string | undefined {
	return options?.binPath ?? process.env.NEURABASH_BIN;
}

export function createNeurabashToolDefinition(
	cwd: string,
	options?: NeurabashToolOptions,
): ToolDefinition<typeof neurabashSchema, NeurabashToolDetails> {
	const profile = options?.profile ?? "workspace";

	return {
		name: "neurabash",
		label: "neurabash",
		description:
			"Execute code through NeuraBash: ordinary Bash, or Bash extended with the native `|!>` typed trapdoor into Julia for exact math, matrix/vector operations, and (as the standard library grows) broader symbolic computation. Runs sandboxed under NeuraBash's Security Kernel V1. Prefer this over guessing at arithmetic or symbolic manipulation in-context; prefer `ipython` for RLM sub-agent spawning, Python skills, and anything needing session state to persist across calls.",
		promptSnippet: "neurabash - sandboxed Bash + typed Julia (|!>) for exact computation",
		executionMode: "sequential",
		parameters: neurabashSchema,
		execute: async (_toolCallId, params, signal) => {
			const binPath = resolveBinPath(options);
			if (!binPath || !existsSync(binPath)) {
				throw new Error(
					`neurabash binary not found (checked NEURABASH_BIN / options.binPath: ${binPath ?? "(unset)"}). NeuraBash must be built (scripts/build.sh in the NeuraBash repo) and NEURABASH_BIN pointed at build/bin/neurabash before this tool can run.`,
				);
			}

			const env = resolveEnv(options);
			const started = Date.now();
			const output = new OutputAccumulator({ tempFilePrefix: "prime-agent-neurabash" });

			const exitCode = await new Promise<number | null>((resolve, reject) => {
				const child = spawn(binPath, [`--neura-profile=${profile}`, "-c", params.code], {
					cwd,
					env,
					stdio: ["ignore", "pipe", "pipe"],
				});
				if (child.pid) trackDetachedChildPid(child.pid);

				let timeoutHandle: NodeJS.Timeout | undefined;
				let timedOut = false;
				if (options?.timeout) {
					timeoutHandle = setTimeout(() => {
						timedOut = true;
						if (child.pid) killProcessTree(child.pid);
					}, options.timeout * 1000);
				}

				child.stdout?.on("data", (d: Buffer) => output.append(d));
				child.stderr?.on("data", (d: Buffer) => output.append(d));

				const onAbort = () => {
					if (child.pid) killProcessTree(child.pid);
				};
				if (signal) {
					if (signal.aborted) onAbort();
					else signal.addEventListener("abort", onAbort, { once: true });
				}

				waitForChildProcess(child)
					.then((code) => {
						if (child.pid) untrackDetachedChildPid(child.pid);
						if (timeoutHandle) clearTimeout(timeoutHandle);
						if (signal) signal.removeEventListener("abort", onAbort);
						if (signal?.aborted) {
							reject(new Error("aborted"));
							return;
						}
						if (timedOut) {
							reject(new Error(`timeout:${options?.timeout}`));
							return;
						}
						resolve(code);
					})
					.catch((err) => {
						if (child.pid) untrackDetachedChildPid(child.pid);
						if (timeoutHandle) clearTimeout(timeoutHandle);
						if (signal) signal.removeEventListener("abort", onAbort);
						reject(err);
					});
			}).catch((err: unknown) => {
				output.finish();
				const snapshot = output.snapshot();
				const text = snapshot.content || "";
				if (err instanceof Error && err.message === "aborted") {
					throw new Error(`${text ? `${text}\n\n` : ""}NeuraBash execution aborted`);
				}
				if (err instanceof Error && err.message.startsWith("timeout:")) {
					throw new Error(`${text ? `${text}\n\n` : ""}NeuraBash execution timed out after ${options?.timeout}s`);
				}
				throw err;
			});

			output.finish();
			const snapshot = output.snapshot();
			await output.closeTempFile();
			let text = snapshot.content || "(no output)";
			if (snapshot.truncation.truncated) {
				text += `\n\n[Output truncated at ${formatSize(DEFAULT_MAX_BYTES)} / ${DEFAULT_MAX_LINES} lines. Full output: ${snapshot.fullOutputPath}]`;
			}

			const details: NeurabashToolDetails = { exitCode, durationMs: Date.now() - started, profile };
			// PIPE-005 in the NeuraBash spec: a typed Error returned as data exits 0.
			// Only a genuinely raised/nonzero shell status is a tool error here.
			const isError = exitCode !== 0 && exitCode !== null;
			return { content: [{ type: "text", text }], details, isError };
		},
	};
}

export function createNeurabashTool(cwd: string, options?: NeurabashToolOptions): AgentTool<typeof neurabashSchema> {
	return wrapToolDefinition(createNeurabashToolDefinition(cwd, options));
}
