---
name: arxiv
description: ArXiv MCP integration for accessing academic papers and research.
---

# ArXiv

Access ArXiv for academic papers, preprints, and research articles.

## Setup

No API key required. ArXiv provides open access to scientific papers.

In Prime Agent, run `/login` and select **MCP Connections**, then choose **ArXiv**

## Usage

```python
import arxiv

# Search for papers
papers = await arxiv.search(
    query="transformer neural networks",
    max_results=10,
    sort_by="relevance"
)

# Get paper details
details = await arxiv.details(id_list=["2305.12345", "2306.67890"])

# Download PDF
pdf_url = await arxiv.download_pdf(id="2305.12345")

# Get recent papers in a category
recent = await arxiv.recent(category="cs.LL", max_results=5)

# Search by author
author_papers = await arxiv.search_author("Attention Is All You Need", max_results=10)
```
