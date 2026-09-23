---
name: wikipedia
description: Wikipedia MCP integration for knowledge retrieval and fact verification.
---

# Wikipedia

Access Wikipedia for knowledge retrieval, fact verification, and general information.

## Setup

1. No API key required for basic read access
2. In Prime Agent, run `/login` and select **MCP Connections**, then choose **Wikipedia**
3. Configure rate limits and language preferences via settings if needed

## Usage

```python
import wikipedia

# Search for articles
results = await wikipedia.search("quantum computing", limit=10)

# Get article summary
summary = await wikipedia.summary("Machine Learning", sentences=5)

# Get full article content
content = await wikipedia.page("Artificial Intelligence")

# Get links from an article
links = await wikipedia.links("Neural Network")

# Get categories
categories = await wikipedia.categories("Deep Learning")

# Verify a fact
fact_check = await wikipedia.verify_fact("The speed of light is 299,792,458 meters per second")
```
