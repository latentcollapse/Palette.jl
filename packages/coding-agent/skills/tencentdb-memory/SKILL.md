---
name: tencentdb-memory
description: TencentDB Agent Memory integration for durable, hierarchical memory with L1/L2 tiers.
---

# TencentDB Agent Memory

Durable cold-memory tier for agents. Shape matches TencentDB L1 atomic memories:
structured records, hybrid BM25 + exact-answer lookup, upsert by identity,
never called once per token.

## Setup

1. Run TencentDB MemoryCore (see `/mnt/d/Code Projects/tencentdb-memory/TencentDB-Agent-Memory-feat-server_team/MemoryCore/`)
2. Configure the MemoryCore gateway URL
3. In Prime Agent, run `/login` and select **MCP Connections**, then choose **TencentDB Memory**

## Usage

```python
import tencentdb_memory

# Initialize the TencentDB memory client
memory = await tencentdb_memory.initialize()

# Upsert a durable memory record
await memory.upsert({
    "kind": "decision",
    "subject": "Project Alpha",
    "predicate": "status",
    "answer": "approved",
    "text": "Project Alpha was approved by the steering committee",
    "id": "decision-001"
})

# Search for records
results = await memory.search("Project Alpha status")

# Get exact answer
answer = await memory.exact_answer("What is the status of Project Alpha?")
```
