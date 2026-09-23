---
name: neurosymbolic-harness
description: Unified neurosymbolic harness for Prime Agent - combines symbolic reasoning, knowledge graphs, rule engines, constraint solving, and free-model optimization.
---

# Neurosymbolic Harness

Unified neurosymbolic harness that combines:
- Symbolic reasoning (propositional logic, first-order logic)
- Knowledge graph reasoning
- Rule-based expert systems
- Constraint solving
- Free-model reasoning optimization
- MCP-powered tool integration
- Persistent symbolic memory

## Setup

All dependencies are built-in. No external setup required.

## Usage

```python
import neurosymbolic_harness

# Initialize the unified harness
harness = await neurosymbolic_harness.initialize()

# Use symbolic reasoning
result = await harness.reason(
    premises=["All men are mortal", "Socrates is a man"],
    conclusion="Socrates is mortal"
)

# Use knowledge graph
await harness.add_triple("Earth", "planetIn", "Solar System")
path = await harness.find_path("Earth", "Milky Way")

# Use constraint solving
solution = await harness.solve_constraints(
    variables=["x", "y"],
    constraints=[
        {"x": 1, "y": 2, "relation": "<=", "rhs": 10},
        {"x": 1, "y": -1, "relation": ">=", "rhs": 0},
    ]
)

# Optimize for free models
optimized = await harness.optimize_for_free_model(
    prompt="Solve this problem...",
    model="openrouter/free"
)

# Get harness statistics
stats = await harness.get_statistics()
```
