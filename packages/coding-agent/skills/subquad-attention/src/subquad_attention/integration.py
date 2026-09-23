"""SubQuadAttention Integration for Prime Agent.

Provides local model memory with:
- SQLite FTS5 archive
- Warm memory cache
- Durable L1 storage
- Long-context memory
- Citation-aware retrieval
"""

from __future__ import annotations

import os
import json
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import McpIntegration


class SubQuadAttention(McpIntegration):
    """SubQuadAttention MCP client integration.

    Provides local model memory with SQLite FTS5 archive, warm memory cache,
    durable L1 storage, and long-context memory.
    """

    server = "subquad-attention"

    def __init__(self) -> None:
        super().__init__()
        self.db_path = os.environ.get("SUBQUAD_DB", str(Path.home() / ".prime" / "agent" / "subquad.db"))
        self.server_url = os.environ.get("SUBQUAD_SERVER_URL", "")
        self.scope = os.environ.get("SUBQUAD_SCOPE", "default")
        self.max_chars = int(os.environ.get("SUBQUAD_MAX_CHARS", "8000"))
        self.retrieval_mode = os.environ.get("SUBQUAD_RETRIEVAL_MODE", "expanded")

    def _run_cli(self, args: List[str], *, timeout: int = 60) -> Dict[str, Any]:
        """Run the subquad-attention CLI and return parsed JSON output."""
        cmd = [
            "python3",
            str(Path("/mnt/d/Code Projects/subquad-attention/python/memory_archive.py")),
            "--db",
            self.db_path,
            *args,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                return {"status": "error", "returncode": result.returncode, "stderr": result.stderr.strip()}
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"status": "error", "stdout": result.stdout.strip()}
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "timeout"}
        except FileNotFoundError:
            return {"status": "error", "error": "subquad-attention CLI not found"}

    async def ingest(self, text: str, source: str, *, scope: Optional[str] = None) -> Dict[str, Any]:
        """Ingest text into the memory archive."""
        scope_value = scope or self.scope
        result = self._run_cli(["ingest", "-", "--source", source, "--scope", scope_value])
        # The CLI reads from stdin, so this is a placeholder
        return {"status": "ingest_requested", "source": source, "scope": scope_value, "note": "Use CLI directly for file ingestion"}

    async def search(self, query: str, *, scope: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Search the memory archive."""
        scope_value = scope or self.scope
        return self._run_cli(["search", query, "--scope", scope_value, "--limit", str(limit)])

    async def context(self, query: str, *, scope: Optional[str] = None, max_chars: Optional[int] = None) -> Dict[str, Any]:
        """Retrieve context for a query."""
        scope_value = scope or self.scope
        chars = max_chars or self.max_chars
        return self._run_cli(["context", query, "--scope", scope_value, "--max-chars", str(chars)])

    async def ask(self, query: str, *, scope: Optional[str] = None, url: Optional[str] = None, budget: int = 1024) -> Dict[str, Any]:
        """Ask a question using the memory archive and local model server."""
        scope_value = scope or self.scope
        server = url or self.server_url
        if not server:
            return {"status": "error", "message": "No local model server URL configured"}
        return self._run_cli(["ask", query, "--scope", scope_value, "--url", server, "--budget", str(budget)])

    async def stats(self, *, scope: Optional[str] = None) -> Dict[str, Any]:
        """Get archive statistics."""
        scope_value = scope or self.scope
        return self._run_cli(["stats", "--scope", scope_value])

    async def backup(self, *, scope: Optional[str] = None, output: Optional[str] = None) -> Dict[str, Any]:
        """Create a backup of the memory archive."""
        scope_value = scope or self.scope
        args = ["backup", "--scope", scope_value]
        if output:
            args += ["--output", output]
        return self._run_cli(args)

    async def restore(self, backup_path: str, *, scope: Optional[str] = None) -> Dict[str, Any]:
        """Restore a memory archive backup."""
        scope_value = scope or self.scope
        return self._run_cli(["restore", backup_path, "--scope", scope_value])

    async def clear(self, *, scope: Optional[str] = None) -> Dict[str, Any]:
        """Clear the memory archive."""
        scope_value = scope or self.scope
        return self._run_cli(["clear", "--scope", scope_value])

    async def get_metrics(self) -> Dict[str, Any]:
        """Get memory system metrics."""
        stats = await self.stats()
        return {
            "status": "metrics_available",
            "db_path": self.db_path,
            "scope": self.scope,
            "retrieval_mode": self.retrieval_mode,
            "stats": stats,
        }
