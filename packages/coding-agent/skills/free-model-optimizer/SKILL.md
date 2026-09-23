---
name: free-model-optimizer
description: Optimize reasoning for free OpenRouter models using chain-of-thought distillation, self-consistency, and tool-augmented reasoning.
---

# Free Model Optimizer

Techniques to make free OpenRouter models punch above their weight:
- Chain-of-thought distillation and prompt optimization
- Self-consistency with majority voting
- Tool-augmented reasoning (use MCP tools for computation)
- Neural-symbolic distillation (use symbolic reasoning to improve neural outputs)
- Ensemble methods with multiple free models
- Reasoning cache for repeated patterns

## Setup

Configure free models in Prime Agent (OpenRouter free tier models like `deepseek/deepseek-v4-flash`, `google/gemini-2.5-flash`, `meta-llama/llama-3.2-3b-instruct`, etc.)

## Usage

```python
import free_model_optimizer

# Run self-consistency with multiple passes
result = await free_model_optimizer.self_consistency(
    prompt="Solve this math problem...",
    model="deepseek/deepseek-v4-flash",
    n_samples=5,
    temperature=0.7
)

# Use tool-augmented reasoning
result = await free_model_optimizer.tool_augmented_reasoning(
    prompt="Calculate the integral of x^2 from 0 to 1",
    model="google/gemini-2.5-flash",
    tools=["wolfram_alpha", "knowledge_graph"]
)

# Neural-symbolic distillation
improved_prompt = await free_model_optimizer.distill_reasoning(
    prompt="Prove that sqrt(2) is irrational",
    model="meta-llama/llama-3.2-3b-instruct"
)

# Cache and reuse reasoning
cached = await free_model_optimizer.cached_reasoning(
    prompt="What is the capital of France?",
    model="openrouter/free"
)
```
