---
name: symbolic-memory
description: Symbolic memory extensions for the Prime Agent harness - store logical propositions, inference results, and graph knowledge.
---

# Symbolic Memory

Enhances the Prime Agent persistent harness with symbolic reasoning capabilities:
- Store logical propositions and their truth values
- Cache inference results from symbolic reasoning
- Maintain working knowledge graphs
- Record rule-based reasoning chains
- Track constraint satisfaction solutions

## Usage

```python
import symbolic_memory

# Store a logical proposition
await symbolic_memory.store_proposition("snow is white", True, "Philosophical observation")

# Store an inference result
result = await symbolic_memory.infer_and_store(
    premises=["All men are mortal", "Socrates is a man"],
    conclusion="Socrates is mortal"
)

# Store knowledge graph triples
await symbolic_memory.store_triple("Earth", "planetIn", "Solar System")

# Query symbolic memory
propositions = await symbolic_memory.query_propositions(truth_value=True)
inferences = await symbolic_memory.get_inference_history()
graph_stats = await symbolic_memory.get_graph_statistics()
```
