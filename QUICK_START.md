# Quick Start: Enhanced Prime Agent Harness

## 1. First Steps

```bash
cd /mnt/d/Code Projects/prime-agent
./prime-agent.sh "What can you do with the enhanced harness?"
```

## 2. Try Symbolic Reasoning

```
import neurosymbolic_harness
harness = NeurosymbolicHarness()
result = harness.truth_table("A => (B => A)")
print(result)
```

## 3. Use Free Model Optimizer

```
import free_model_optimizer
optimizer = FreeModelOptimizer()
result = await optimizer.self_consistency(
    prompt="Explain photosynthesis in simple terms",
    model="deepseek/deepseek-v4-flash",
    n_samples=3
)
```

## 4. Explore MCP Integrations

```
import wolfram_alpha
await wolfram_alpha.query("integrate sin(x) dx")

import wikipedia
await wikipedia.summary("Quantum Computing")
```

## 5. Check Harness Statistics

```
import neurosymbolic_harness
harness = NeurosymbolicHarness()
print(harness.get_statistics())
```

## Best Practices

1. Use symbolic reasoning for logic and verification
2. Use tool-augmented reasoning for computation
3. Cache free model responses with reasoning cache
4. Store insights in symbolic memory for reuse

## Available Models

Free models that work well:
- deepseek/deepseek-v4-flash
- google/gemini-2.5-flash
- meta-llama/llama-3.2-3b-instruct
- openai/gpt-4o-mini
- openrouter/free

## Next Steps

1. Explore all the new skills
2. Create your own MCP integrations
3. Build composite workflows
4. Share knowledge graphs across sessions
5. Optimize your free model usage
