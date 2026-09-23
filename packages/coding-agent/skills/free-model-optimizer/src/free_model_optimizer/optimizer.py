"""Free Model Optimizer Implementation.

Techniques to make free OpenRouter models punch above their weight.
"""

from __future__ import annotations

import json
import hashlib
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Import harness for caching
try:
    from ..harness import get_harness_state, HarnessState
except ImportError:
    # Fallback when running standalone
    class MockHarness:
        pass
    get_harness_state = lambda: MockHarness()


@dataclass
class ReasoningCacheEntry:
    """Cached reasoning result."""
    prompt_hash: str
    prompt: str
    model: str
    response: str
    confidence: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    usage_count: int = 0


@dataclass
class SelfConsistencyResult:
    """Result of self-consistency voting."""
    responses: List[str]
    final_answer: str
    vote_distribution: Dict[str, int]
    confidence: float
    model: str
    temperature: float
    n_samples: int


class FreeModelOptimizer:
    """Optimizer for free OpenRouter models."""

    def __init__(self, harness_state: Optional[Any] = None):
        self.harness = harness_state or get_harness_state()
        self._ensure_cache_setup()

    def _ensure_cache_setup(self) -> None:
        """Ensure the harness has the reasoning cache."""
        entry = self.harness.get("memory", "reasoning-cache", global_=False)
        if entry is None:
            self.harness.create_memory(
                title="Reasoning Cache",
                content="Cache for reasoning results to avoid recomputation",
                id="reasoning-cache",
                path="optimizer",
                metadata={"type": "reasoning-cache"},
            )

    def _hash_prompt(self, prompt: str, model: str, temperature: float) -> str:
        """Create a hash for a prompt+model+temperature combination."""
        key = f"{prompt}|{model}|{temperature}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    async def cached_reasoning(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        *,
        global_: bool = False,
    ) -> str:
        """Get a cached response or run the model and cache the result.

        Args:
            prompt: The prompt to send to the model
            model: Model identifier
            temperature: Sampling temperature
            global_: Whether to use global cache

        Returns:
            The model's response (from cache or fresh)
        """
        prompt_hash = self._hash_prompt(prompt, model, temperature)

        # Try to get from cache
        cache_entry = self.harness.get("memory", f"cache_{prompt_hash}", global_=global_)
        if cache_entry:
            try:
                data = json.loads(cache_entry.content)
                cached = ReasoningCacheEntry(**data)
                cached.usage_count += 1
                # Update the cache entry
                self.harness.upsert(
                    "memory",
                    title=f"Cache: {prompt[:50]}...",
                    content=json.dumps(cached.__dict__, indent=2),
                    id=f"cache_{prompt_hash}",
                    path="optimizer/cache",
                    metadata=cached.__dict__,
                    global_=global_,
                )
                return cached.response
            except Exception:
                pass

        # If not in cache, return a signal to run the model
        # The actual model call should be done by the agent
        return f"__CACHE_MISS__:{prompt_hash}"

    def store_in_cache(
        self,
        prompt: str,
        model: str,
        temperature: float,
        response: str,
        confidence: float = 1.0,
        *,
        global_: bool = False,
    ) -> None:
        """Store a response in the reasoning cache."""
        prompt_hash = self._hash_prompt(prompt, model, temperature)
        entry = ReasoningCacheEntry(
            prompt_hash=prompt_hash,
            prompt=prompt,
            model=model,
            response=response,
            confidence=confidence,
        )

        self.harness.upsert(
            "memory",
            title=f"Cache: {prompt[:50]}...",
            content=json.dumps(entry.__dict__, indent=2),
            id=f"cache_{prompt_hash}",
            path="optimizer/cache",
            metadata=entry.__dict__,
            global_=global_,
        )

    async def self_consistency(
        self,
        prompt: str,
        model: str,
        n_samples: int = 5,
        temperature: float = 0.7,
        vote_extractor: Optional[str] = None,
    ) -> SelfConsistencyResult:
        """Run self-consistency by sampling multiple responses and voting.

        Args:
            prompt: The prompt to send to the model
            model: Model identifier
            n_samples: Number of samples to generate
            temperature: Sampling temperature
            vote_extractor: Optional function to extract vote from response

        Returns:
            SelfConsistencyResult with the voted answer
        """
        # This would call the model n_samples times
        # For now, return a structured template
        return SelfConsistencyResult(
            responses=[],
            final_answer="",
            vote_distribution={},
            confidence=0.0,
            model=model,
            temperature=temperature,
            n_samples=n_samples,
        )

    async def tool_augmented_reasoning(
        self,
        prompt: str,
        model: str,
        tools: List[str],
        max_iterations: int = 3,
    ) -> Dict[str, Any]:
        """Run tool-augmented reasoning.

        The model can call tools (MCP integrations) to get exact answers
        for computation, lookup, etc., rather than hallucinating.

        Args:
            prompt: The prompt
            model: Model identifier
            tools: List of available tool names (e.g., ["wolfram_alpha", "knowledge_graph"])
            max_iterations: Maximum tool-use iterations

        Returns:
            Dict with the final answer and tool usage trace
        """
        return {
            "status": "tool_augmented_reasoning_available",
            "prompt": prompt,
            "model": model,
            "available_tools": tools,
            "max_iterations": max_iterations,
            "note": "Integrate with Prime Agent's tool calling system",
        }

    async def distill_reasoning(
        self,
        prompt: str,
        model: str,
        target_model: Optional[str] = None,
    ) -> str:
        """Distill reasoning from a stronger model into a prompt for a weaker model.

        Uses chain-of-thought examples from a capable model to create
        few-shot prompts for the free model.

        Args:
            prompt: The reasoning task
            model: Source model (stronger)
            target_model: Target model (weaker/free)

        Returns:
            Optimized prompt for the target model
        """
        return f"""Optimized prompt for {target_model or model}:

{prompt}

Think step by step:
1. Identify the key concepts and relationships
2. Break down the problem into smaller subproblems
3. Solve each subproblem using logical reasoning
4. Combine the results
5. Verify the final answer

[Include relevant examples from symbolic reasoning if available]"""

    async def ensemble_reasoning(
        self,
        prompt: str,
        models: List[str],
        aggregator: str = "majority_vote",
    ) -> Dict[str, Any]:
        """Run multiple models and aggregate their answers.

        Args:
            prompt: The prompt
            models: List of model identifiers
            aggregator: How to combine answers ("majority_vote", "weighted", "best_of")

        Returns:
            Aggregated result
        """
        return {
            "status": "ensemble_reasoning_available",
            "prompt": prompt,
            "models": models,
            "aggregator": aggregator,
            "note": "Integrate with Prime Agent's multi-model calling",
        }

    def get_cache_statistics(self, *, global_: bool = False) -> Dict[str, Any]:
        """Get cache usage statistics."""
        entries = self.harness.list("memory", global_=global_)
        cache_entries = [e for e in entries if e.path == "optimizer/cache"]
        total_usage = 0
        for entry in cache_entries:
            try:
                data = json.loads(entry.content)
                total_usage += data.get("usage_count", 0)
            except Exception:
                pass
        return {
            "total_entries": len(cache_entries),
            "total_usage": total_usage,
        }

    def clear_cache(self, *, global_: bool = False) -> int:
        """Clear the reasoning cache."""
        entries = self.harness.list("memory", global_=global_)
        cleared = 0
        for entry in entries:
            if entry.path == "optimizer/cache":
                self.harness.delete("memory", entry.id, global_=global_)
                cleared += 1
        return cleared
