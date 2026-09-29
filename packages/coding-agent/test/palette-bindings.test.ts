import { describe, expect, it } from "vitest";
import { describeBindings } from "../src/core/tools/palette.js";

describe("describeBindings", () => {
	it("lists short sets in full, in the kernel's order", () => {
		const list = ["a (Int64, call 3)", "b (String, call 1)"];
		expect(describeBindings(list)).toBe("a (Int64, call 3), b (String, call 1)");
	});

	it("keeps the most recently set bindings within the budget and counts the rest", () => {
		// 400 bindings of ~30 characters: about 12,000 characters uncapped.
		const list = Array.from(
			{ length: 400 },
			(_, i) => `binding_${String(i).padStart(3, "0")} (Int64, call ${i + 1})`,
		);
		const text = describeBindings(list, 2000);
		expect(text.length).toBeLessThan(2100);
		expect(text).toContain("binding_399 (Int64, call 400)");
		expect(text).not.toContain("binding_000 ");
		const shown = (text.match(/\(Int64, call \d+\)/g) ?? []).length;
		expect(text).toContain(`and ${400 - shown} more set earlier (varinfo() lists them all)`);
	});

	it("keeps the kept bindings in the kernel's order", () => {
		const list = ["old (Int64, call 1)", "newest (Int64, call 9)", "newer (Int64, call 5)"];
		expect(describeBindings(list, 50)).toBe(
			"newest (Int64, call 9), newer (Int64, call 5), and 1 more set earlier (varinfo() lists them all)",
		);
	});
});
