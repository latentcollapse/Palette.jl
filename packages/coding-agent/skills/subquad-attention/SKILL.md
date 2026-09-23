---
name: subquad-attention
description: Local model memory system with SQLite archive, warm cache, durable L1, and long-context memory.
---

# SubQuadAttention

Persistent text memory for local models, with a separate Julia research track
for recurrent attention. Early development.

The Python runtime keeps original documents and conversation turns in SQLite.
It retrieves source excerpts for a question, fits them into a bounded prompt,
and checks that the answering model's citations refer to evidence it received.
SQLite preserves superseded decisions and their original evidence across restarts.

## Run it

Python 3.10+ with SQLite FTS5 is enough for storage and retrieval. No pip
dependencies required. Run these commands from the repository root:

```bash
python3 python/memory_archive.py --db data/memory.db ingest conversation.txt --source session-001
python3 python/memory_archive.py --db data/memory.db context 'release decision' --max-chars 8000
python3 python/memory_archive.py --db data/memory.db ask 'When is the release?' --url http://127.0.0.1:8777
```

`ask` needs a running llama-server. The `context` command returns an evidence
packet for other model hosts, whose integrations must apply their own tokenizer
and reserve space for the rest of the prompt and the answer.

The [usage guide](docs/MVP.md) covers corrections, immutable citations, backups,
project scopes, and optional query expansion. Backups contain all stored scopes
and history. Keep them private.

## Tests

```bash
python3 -m unittest discover -s test -p 'test_archive.py' -v
bash scripts/verify.sh --live
```

The full verifier also requires Julia and the local model server. It checks
the recurrent kernel, archive restart retention over a million-word synthetic
corpus, and small session scenarios involving paraphrases and conflicting
decisions. Known-bad controls are included.

The current retrieval-only run over all 500 cleaned LongMemEval-S questions
reached 95.6% answer-session Recall_any@5 and 82.4% Recall_all@5. This is a
local metric over a 32-chunk candidate pool, not an official leaderboard run.
The [evaluation report](docs/EVALUATION.md) includes confidence intervals,
per-category failures, controls, dataset hashes, and the limits on those numbers.

These are regression tests. They establish neither drift-free long-running
reasoning nor a native million-token model context. Ranked keyword retrieval
is the default, and questions with no useful vocabulary overlap can still miss
their evidence.

## Research

The Julia recurrence has numerical-equivalence and scaling tests. It is separate
from the Python retrieval path and has not been inserted into a pretrained
model's attention layers. Actual RotorQuant compression and TencentDB storage
integration remain unfinished.

The [historical experiments](docs/HISTORICAL_EXPERIMENTS.md) preserve the earlier
results and their limitations, including synthetic event counts and calculated
KV sizes that should not be read as native model-context measurements.
