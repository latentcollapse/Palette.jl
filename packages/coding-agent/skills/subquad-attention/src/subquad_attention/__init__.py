"""SubQuadAttention integration for Prime Agent.

Local model memory system with:
- SQLite FTS5 archive
- Warm memory cache
- Durable L1 storage
- Long-context memory
- Citation-aware retrieval
"""

from .integration import SubQuadAttention

__all__ = ["SubQuadAttention"]
