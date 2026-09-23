import type { Usage } from "@earendil-works/pi-ai";

/** Shared mutable model request and usage ledger for one bounded experiment trial. */
export interface ModelRequestBudget {
	maxAttempts: number;
	attempts: number;
	inputTokens: number;
	outputTokens: number;
	cacheReadTokens: number;
	cacheWriteTokens: number;
	reportedCostUsd: number;
	requestErrors: number;
	exhausted: boolean;
}

export function createModelRequestBudget(maxAttempts: number): ModelRequestBudget {
	if (!Number.isSafeInteger(maxAttempts) || maxAttempts < 1) {
		throw new Error("Model request budget must be a positive safe integer");
	}
	return {
		maxAttempts,
		attempts: 0,
		inputTokens: 0,
		outputTokens: 0,
		cacheReadTokens: 0,
		cacheWriteTokens: 0,
		reportedCostUsd: 0,
		requestErrors: 0,
		exhausted: false,
	};
}

export function recordModelRequestUsage(budget: ModelRequestBudget, usage: Usage, failed: boolean): void {
	budget.inputTokens += usage.input;
	budget.outputTokens += usage.output;
	budget.cacheReadTokens += usage.cacheRead;
	budget.cacheWriteTokens += usage.cacheWrite;
	budget.reportedCostUsd += usage.cost?.total ?? 0;
	if (failed) budget.requestErrors += 1;
}
