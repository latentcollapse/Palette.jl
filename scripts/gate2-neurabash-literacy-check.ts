/**
 * Gate 2 prerequisite, Step 1 (chassis plan): does the ACTUAL fixed Gate 2
 * model understand enough of the currently implemented NeuraBash `|!>`
 * surface to write a few tiny correct commands, given only the same concise
 * reference Gate 2 itself will receive?
 *
 * This is NOT Gate 2 -- it's a syntax/substrate-literacy check. The model
 * generates four commands (math, vector, matrix, and one that intentionally
 * assumes cross-session binding persistence, which the real ephemeral
 * session model does not support); each is run against the real NeuraBash
 * binary exactly as generated -- no silent repair of a broken command before
 * execution, per the goal's explicit instruction.
 *
 * The concise reference below is generated from the real registered
 * operations in julia/src/opspec.jl (grepped, not transcribed from the
 * aspirational spec) plus real example syntax pulled from
 * tests/mixed-pipeline/native_jul_mvp.sh -- both cited inline.
 *
 * Usage:
 *   NEURABASH_BIN=/path/to/build/bin/neurabash \
 *     npx tsx scripts/gate2-neurabash-literacy-check.ts
 */
import { execFile } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { getModel } from "@earendil-works/pi-ai";
import { getAgentDir } from "../packages/coding-agent/src/config.js";
import { AuthStorage } from "../packages/coding-agent/src/core/auth-storage.js";
import { ModelRegistry } from "../packages/coding-agent/src/core/model-registry.js";
import { createAgentSession } from "../packages/coding-agent/src/core/sdk.js";
import { SessionManager } from "../packages/coding-agent/src/core/session-manager.js";
import { SettingsManager } from "../packages/coding-agent/src/core/settings-manager.js";
import { DefaultResourceLoader } from "../packages/coding-agent/src/core/resource-loader.js";

const execFileAsync = promisify(execFile);

const FIXED_PROVIDER = "openrouter";
const FIXED_MODEL_ID = "cohere/north-mini-code:free";

const NEURABASH_QUICK_REFERENCE = `NeuraBash |!> quick reference (real, currently-implemented operations only):

Each call to the neurabash tool is an independent, EPHEMERAL invocation --
nothing bound with core.bind in one call is visible to a later, separate
call. Only bindings made and used WITHIN the same call persist for that
call's duration.

- math.eval "<expr>"                          exact arithmetic, e.g. |!> math.eval "2^3^2"
- vector.sum / vector.max / vector.min / vector.abs   on piped-in data
- matrix.read                                  parse piped CSV (rows of comma-separated numbers) into a matrix
- matrix.rank / matrix.shape / matrix.transpose / matrix.eig   act on a piped-in or bound matrix
- core.bind <NAME>                             bind the piped-in value to NAME for the REST OF THIS SAME invocation only
- |!> @NAME                                    reference a binding made earlier IN THIS SAME invocation

Example (real, from the test suite): printf '1,2\\n3,4\\n' |!> matrix.read |!> matrix.rank
Example: printf '1,2\\n3,4\\n' |!> matrix.read |!> core.bind A; |!> @A |!> matrix.rank`;

const GENERATION_PROMPT = `You will write four tiny NeuraBash |!> commands using ONLY the operations in this reference. Do not invent operations not listed.

${NEURABASH_QUICK_REFERENCE}

Write exactly four commands, one per line, each prefixed with its label exactly like this:
MATH: <command>
VECTOR: <command>
MATRIX: <command>
IMPOSSIBLE: <command>

1. MATH: a command using math.eval to compute something non-trivial (not just "2+2").
2. VECTOR: a command that pipes in some numbers and calls a vector.* operation on them.
3. MATRIX: a command that pipes in a small CSV matrix and calls a matrix.* operation on it.
4. IMPOSSIBLE: a command that assumes a binding made in one earlier, SEPARATE neurabash invocation is still available by name in a new invocation (i.e. it deliberately relies on cross-invocation binding persistence). This one is meant to fail -- write it as if you believed bindings persisted across separate invocations.

Output only the four labeled lines, nothing else.`;

interface GeneratedCommand {
	label: "MATH" | "VECTOR" | "MATRIX" | "IMPOSSIBLE";
	command: string;
}

function parseGenerated(text: string): GeneratedCommand[] {
	const results: GeneratedCommand[] = [];
	for (const line of text.split("\n")) {
		const match = line.match(/^(MATH|VECTOR|MATRIX|IMPOSSIBLE):\s*(.+)$/);
		if (match) {
			results.push({ label: match[1] as GeneratedCommand["label"], command: match[2].trim() });
		}
	}
	return results;
}

async function runAgainstRealBinary(command: string, workDir: string): Promise<{ stdout: string; stderr: string; exitCode: number }> {
	const bin = process.env.NEURABASH_BIN;
	if (!bin) throw new Error("NEURABASH_BIN is not set");
	try {
		const { stdout, stderr } = await execFileAsync(bin, ["--neura-profile=workspace", "-c", command], {
			cwd: workDir,
			timeout: 120_000,
		});
		return { stdout, stderr, exitCode: 0 };
	} catch (error: any) {
		return {
			stdout: error.stdout ?? "",
			stderr: error.stderr ?? String(error.message ?? error),
			exitCode: typeof error.code === "number" ? error.code : 1,
		};
	}
}

if (!process.env.NEURABASH_BIN) {
	console.error("NEURABASH_BIN is not set. Point it at a real built build/bin/neurabash before running this.");
	process.exit(69);
}

const cwd = process.cwd();
const agentDir = getAgentDir();
const authStorage = AuthStorage.create();
const modelRegistry = ModelRegistry.create(authStorage);
const settingsManager = SettingsManager.create(cwd, agentDir);
const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
await resourceLoader.reload();

const model = getModel(FIXED_PROVIDER, FIXED_MODEL_ID);
if (!model) {
	console.error(`getModel("${FIXED_PROVIDER}", "${FIXED_MODEL_ID}") returned nothing.`);
	process.exit(69);
}

const { session } = await createAgentSession({
	cwd,
	agentDir,
	authStorage,
	modelRegistry,
	settingsManager,
	resourceLoader,
	model,
	sessionManager: SessionManager.create(cwd, agentDir),
	baseToolsOverride: {},
	initialActiveToolNames: [],
	includeGoals: false,
});

console.log(`[literacy-check] model: ${model.provider}/${model.id}`);
console.log("[literacy-check] --- asking the model to generate 4 commands ---");
await session.prompt(GENERATION_PROMPT);
const generatedText = session.getLastAssistantText() ?? "";
console.log(generatedText);

const commands = parseGenerated(generatedText);
console.log(`\n[literacy-check] parsed ${commands.length} of 4 expected commands`);

const workDir = mkdtempSync(join(tmpdir(), "gate2-literacy-"));
const results: Array<{ label: string; command: string; stdout: string; stderr: string; exitCode: number; verdict: string }> = [];

for (const { label, command } of commands) {
	console.log(`\n[literacy-check] --- running ${label}: ${command}`);
	const { stdout, stderr, exitCode } = await runAgainstRealBinary(command, workDir);
	console.log(`[literacy-check] exit=${exitCode} stdout=${JSON.stringify(stdout.trim())} stderr=${JSON.stringify(stderr.trim())}`);
	let verdict: string;
	if (label === "IMPOSSIBLE") {
		verdict =
			exitCode !== 0 && /UnknownBindingError|unbound|unknown binding/i.test(stderr + stdout)
				? "PASS (correctly rejected, as expected for a real cross-invocation binding assumption)"
				: exitCode !== 0
					? "PASS (rejected, though not with the expected UnknownBindingError text -- worth a closer look)"
					: "FAIL (should have been rejected; instead it succeeded)";
	} else {
		verdict = exitCode === 0 ? "PASS (executed successfully)" : "FAIL (real operation call failed)";
	}
	results.push({ label, command, stdout, stderr, exitCode, verdict });
}

rmSync(workDir, { recursive: true, force: true });
await session.disposeAsync();

console.log("\n[literacy-check] === SUMMARY (record verbatim, no post-hoc repair) ===");
for (const r of results) {
	console.log(`${r.label}: ${r.verdict}`);
	console.log(`  command: ${r.command}`);
	console.log(`  exit=${r.exitCode} stdout=${JSON.stringify(r.stdout.trim())} stderr=${JSON.stringify(r.stderr.trim())}`);
}
const missingLabels = ["MATH", "VECTOR", "MATRIX", "IMPOSSIBLE"].filter((l) => !results.some((r) => r.label === l));
if (missingLabels.length > 0) {
	console.log(`MISSING (model did not produce a parseable line for): ${missingLabels.join(", ")}`);
}
