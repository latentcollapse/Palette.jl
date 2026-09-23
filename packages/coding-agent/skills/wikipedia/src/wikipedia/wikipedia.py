"""Wikipedia MCP Integration.

Provides access to Wikipedia for knowledge retrieval and fact verification.
"""

from __future__ import annotations

import os
from typing import Any

from .. import McpIntegration


class WikipediaIntegration(McpIntegration):
    """Wikipedia MCP client integration.

    Provides access to Wikipedia for:
    - Article search and retrieval
    - Summary generation
    - Fact verification
    - Link and category extraction
    - Multilingual support
    """

    server = "wikipedia"

    def __init__(self) -> None:
        super().__init__()
        # Wikipedia API endpoint
        self.url = os.environ.get("WIKIPEDIA_ENDPOINT", "https://en.wikipedia.org/w/api.php")

    async def search(self, query: str, limit: int = 10, **kwargs: Any) -> List[Dict[str, Any]]:
        """Search Wikipedia for articles."""
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
            **kwargs,
        }
        return {"action": "search", "query": query, "params": params}

    async def summary(self, title: str, sentences: int = 5, **kwargs: Any) -> str:
        """Get a summary of a Wikipedia article."""
        params = {
            "action": "query",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "exsentences": sentences,
            "titles": title,
            "format": "json",
            **kwargs,
        }
        return {"action": "summary", "title": title, "params": params}

    async def page(self, title: str, **kwargs: Any) -> Dict[str, Any]:
        """Get full content of a Wikipedia article."""
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": True,
            "titles": title,
            "format": "json",
            **kwargs,
        }
        return {"action": "page", "title": title, "params": params}

    async def links(self, title: str, **kwargs: Any) -> List[str]:
        """Get links from a Wikipedia article."""
        params = {
            "action": "query",
            "prop": "links",
            "pllimit": "max",
            "titles": title,
            "format": "json",
            **kwargs,
        }
        return {"action": "links", "title": title, "params": params}

    async def categories(self, title: str, **kwargs: Any) -> List[str]:
        """Get categories for a Wikipedia article."""
        params = {
            "action": "query",
            "prop": "categories",
            "cllimit": "max",
            "titles": title,
            "format": "json",
            **kwargs,
        }
        return {"action": "categories", "title": title, "params": params}

    async def verify_fact(self, statement: str, **kwargs: Any) -> Dict[str, Any]:
        """Verify a fact by searching Wikipedia."""
        # Search for key terms in the statement
        # This is a simplified implementation
        params = {
            "action": "query",
            "list": "search",
            "srsearch": statement,
            "srlimit": 5,
            "format": "json",
            **kwargs,
        }
        return {"action": "verify_fact", "statement": statement, "params": params}
