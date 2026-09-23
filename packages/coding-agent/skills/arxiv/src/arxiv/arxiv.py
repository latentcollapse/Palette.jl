"""ArXiv MCP Integration.

Provides access to ArXiv for academic papers and research.
"""

from __future__ import annotations

import os
from typing import Any, List

from .. import McpIntegration


class ArxivIntegration(McpIntegration):
    """ArXiv MCP client integration.

    Provides access to ArXiv for:
    - Searching academic papers
    - Retrieving paper metadata
    - Downloading PDFs
    - Browsing recent submissions
    - Author searches
    """

    server = "arxiv"

    def __init__(self) -> None:
        super().__init__()
        # ArXiv API endpoint
        self.url = os.environ.get("ARXIV_ENDPOINT", "http://export.arxiv.org/api/query")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        sort_by: str = "relevance",
        sort_order: str = "descending",
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Search ArXiv for papers."""
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
            **kwargs,
        }
        return {"action": "search", "query": query, "params": params}

    async def details(self, id_list: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Get details for specific paper IDs."""
        params = {
            "id_list": ",".join(id_list),
            **kwargs,
        }
        return {"action": "details", "id_list": id_list, "params": params}

    async def download_pdf(self, paper_id: str, **kwargs: Any) -> str:
        """Get PDF download URL for a paper."""
        # ArXiv PDF URL format: https://arxiv.org/pdf/{id}.pdf
        pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
        return pdf_url

    async def recent(
        self,
        category: str = "cs.AI",
        max_results: int = 10,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Get recent papers in a category."""
        params = {
            "search_query": f"cat:{category}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            **kwargs,
        }
        return {"action": "recent", "category": category, "params": params}

    async def search_author(
        self,
        author_name: str,
        max_results: int = 10,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Search for papers by author."""
        params = {
            "search_query": f'au:"{author_name}"',
            "start": 0,
            "max_results": max_results,
            **kwargs,
        }
        return {"action": "search_author", "author": author_name, "params": params}
