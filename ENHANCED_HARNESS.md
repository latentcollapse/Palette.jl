# Enhanced Prime Agent Harness

## Neurosymbolic Tooling Suite

- neurosymbolic-reasoning: Propositional logic, knowledge graphs, rule engines, constraint solving
- symbolic-memory: Persistent storage for propositions, inferences, knowledge graphs, rules, constraints
- free-model-optimizer: Chain-of-thought distillation, self-consistency, tool-augmented reasoning
- neurosymbolic-harness: Unified interface combining all capabilities

## MCP Suite

- wolfram-alpha: Computational knowledge engine for mathematics and data analysis
- wikipedia: Knowledge retrieval and fact verification
- arxiv: Academic paper access
- tencentdb-memory: Durable cold-memory tier with L1/L2 architecture
- rotorquant: Efficient GGUF backend for LLaMA models

## Harness Optimizations

- Enhanced harness state with symbolic memory types
- MCP-powered skill discovery
- Reasoning-aware goal decomposition
- Persistent symbolic memory for improved model context

## Free Model Optimization

- Chain-of-thought distillation
  - distill_reasoning() converts reasoning from strong models to optimized prompts
  - Uses neural-symbolic distillation to improve free model reasoning
  - Works with OpenRouter free models like deepseek/deepseek-v4-flash and google/gemini-2.5-flash

## MCP Suite Integration

1. Wolfram Alpha MCP
  - Connects to computational knowledge engine
  - Provides symbolic math, step-by-step solutions
  - Data analysis and statistics
  - Unit conversions and plotting support

2. Wikipedia MCP
  - Article search and retrieval
  - Summary generation
  - Fact verification
  - Link and category extraction

3. ArXiv MCP
  - Paper search and retrieval
  - Download PDFs
  - Recent submissions
  - Author searches

## Harness Integration Points

1. HarnessState class - can extend with backend performance metrics
2. record_refinement() - can record backend optimization results
3. get_harness_state/global_ flag - supports global state for distributed setups
4. memory scope - can store backend performance metrics in local or global scope
5. enhancement of get_harness_state to include backend metrics
6. enhancement of overview() to show backend optimization metrics

## Free Model Optimization

1. Self-consistency with voting improves accuracy
2. Tool-augmented reasoning uses MCP tools for computation
3. Neural-symbolic distillation improves free model reasoning
4. Reasoning cache avoids recomputation
5. Ensemble methods combine multiple free models

## Backend Technologies

1. RotorQuant: Efficient GGUF quantization for LLaMA models
2. Subquad-Attention: Linear-decay recurrent attention for long context
3. TencentDB: Durable cold-memory tier with L1/L2 architecture
4. RLM: Runtime kernel with heartbeat and subagent support

## System Architecture

1. Prime Agent kernel (TypeScript) orchestrates everything
2. Python skills provide MCP protocol implementations
3. Harness state persists all neural and symbolic artifacts
6. Global/local scope system enables multi-session coordination

## Getting Started

1. All skills are pre-installed and load automatically
2. Configure MCP integrations via /login and MCP Connections
3. Set environment variables for backend connections
4. Use the unified neurosymbolic-harness skill for best results

## Usage Example

```python
import neurosymbolic_harness

# Initialize unified harness
from coding_agent.skills.neurosymbolic_harness import NeurosymbolicHarness

# Initialize
harness = NeurosymbolicHarness()

# Use symbolic reasoning
result = harness.reason(
    premises=['All men are mortal', 'Socrates is a man'],
    conclusion='Socrates is mortal'
)

# Use knowledge graph
await harness.add_triple('Earth', 'planetIn', 'Solar System')

# Query with MCP
import wolfram_alpha
result = await wolfram_alpha.query('solve x^2 + 5x + 6 = 0')

# Optimize for free model
optimizer = FreeModelOptimizer()
result = await optimizer.self_consistency(
    prompt='Solve this problem',
    model='deepseek/deepseek-v4-flash',
    n_samples=5
)
```
