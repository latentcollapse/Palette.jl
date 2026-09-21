/**
 * NIRA Stage 0, DUAL-PREFERRED arm.
 *
 * Both `neurabash` and `ipython` stay active — this does not remove Python
 * as an option, and it does not claim NeuraBash or Julia is a categorically
 * better language than Python. It only reorders which one the model reaches
 * for first, by task shape, so the comparison has an honest "preferred but
 * not exclusive" arm alongside Stage 0's neutral-both and NeuraBash-only
 * configurations.
 *
 * Usage: copy into ~/.pi/agent/extensions/ or a project's .pi/extensions/
 * alongside a session that has both tools active
 * (initialActiveToolNames: ["neurabash", "ipython"]).
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const SUBSTRATE_PREFERENCE_NOTE = [
	"## Substrate preference (this session)",
	"",
	"Both `neurabash` and `ipython` are available. Neither is categorically better — this is a task-fit choice, not a language preference:",
	"",
	"- Reach for `neurabash` first for exact computation: arithmetic, linear algebra, symbolic manipulation, anything where a wrong-but-plausible answer is worse than a slower correct one. It executes under a real security kernel, and its typed `|!>` stages don't round-trip through text between steps.",
	"- Reach for `ipython` when the job is genuinely Python-shaped: an existing Python/data-science library is the right tool, you need a rich persistent namespace across many turns, or you're driving another system through its own Python interface.",
	"- Before building anything new in either substrate, check whether an existing operation or a previously built tool already does the job.",
	"",
	"This note exists so a comparison between substrate choices is possible. It is not an instruction to avoid Python.",
].join("\n");

export default function neurabashPreferred(pi: ExtensionAPI) {
	pi.on("before_agent_start", async (event) => {
		const { systemPrompt, systemPromptOptions } = event;
		const tools = systemPromptOptions.selectedTools ?? [];
		if (!tools.includes("neurabash") || !tools.includes("ipython")) {
			return {};
		}
		return {
			systemPrompt: `${systemPrompt}\n\n${SUBSTRATE_PREFERENCE_NOTE}\n`,
		};
	});
}
