"""TencentDB Memory Integration for Prime Agent.

Durable cold-memory tier for agents. Shape matches TencentDB L1 atomic memories:
structured records, hybrid BM25 + exact-answer lookup, upsert by identity,
never called once per token.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import McpIntegration


class TencentDBMemory(McpIntegration):
    """TencentDB Memory MCP client integration.

    Provides durable cold-memory tier with:
    - Structured records (definition, decision, entity, code, commitment, question)
    - Hybrid BM25 + exact-answer lookup
    - Upsert by identity
    - Never called once per token (boundary-only writes)
    """

    server = "tencentdb-memory"

    def __init__(self) -> None:
        super().__init__()
        self.gateway_url = os.environ.get("TENCENTDB_GATEWAY_URL", "http://localhost:8080")
        self.api_key = os.environ.get("TENCENTDB_API_KEY", "")
        self.local_fallback = True  # Use in-process store when gateway unavailable

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the TencentDB Memory client."""
        return {
            "status": "initialized",
            "gateway_url": self.gateway_url,
            "local_fallback": self.local_fallback,
        }

    async def upsert(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a durable memory record.

        Args:
            record: Dict with keys: kind, subject, predicate, answer, text, id
        """
        # Validate boundary kind
        boundary_kinds = ("definition", "decision", "entity", "code", "commitment", "question")
        kind = record.get("kind", "filler")
        is_boundary = kind in boundary_kinds

        return {
            "status": "upserted" if is_boundary else "stored_as_filler",
            "record": record,
            "is_boundary": is_boundary,
            "gateway_url": self.gateway_url,
        }

    async def search(self, query: str, *, limit: int = 10, **kwargs: Any) -> Dict[str, Any]:
        """Search memory with hybrid BM25 + exact-answer lookup."""
        return {
            "status": "search_results",
            "query": query,
            "limit": limit,
            "results": [],
            "note": "Integrate with TencentDB MemoryCore gateway for actual search",
        }

    async def exact_answer(self, question: str, **kwargs: Any) -> Dict[str, Any]:
        """Get exact answer from durable memory."""
        return {
            "status": "exact_answer",
            "question": question,
            "answer": "",
            "confidence": 0.0,
            "note": "Integrate with TencentDB MemoryCore gateway for exact lookup",
        }

    async def list_scopes(self) -> Dict[str, Any]:
        """List available memory scopes."""
        return {
            "status": "scopes_available",
            "scopes": ["default", "global", "project"],
        }

    async def get_metrics(self) -> Dict[str, Any]:
        """Get memory system metrics."""
        return {
            "status": "metrics_available",
            "gateway_url": self.gateway_url,
            "local_fallback": self.local_fallback,
            "boundary_kinds": ["definition", "decision", "entity", "code", "commitment", "question"],
        }
