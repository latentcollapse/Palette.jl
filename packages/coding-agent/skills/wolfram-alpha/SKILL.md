---
name: wolfram-alpha
description: Wolfram Alpha computational knowledge engine for symbolic mathematics, step-by-step solutions, and scientific computation.
---

# Wolfram Alpha

Access Wolfram Alpha's computational knowledge engine for symbolic mathematics, step-by-step solutions, data analysis, and scientific computation.

## Setup

1. Get a Wolfram Alpha API key from https://developer.wolframalpha.com/
2. In Prime Agent, run `/login` and select **MCP Connections**, then choose **Wolfram Alpha**
3. Or set the `WOLFRAM_APPID` environment variable

## Usage

```python
import wolfram_alpha

# Solve an equation symbolically
result = await wolfram_alpha.query("solve x^2 + 5x + 6 = 0")

# Get step-by-step solution
steps = await wolfram_alpha.step_by_step("integrate x^2 sin(x) dx")

# Compute
result = await wolfram_alpha.compute("integrate sin(x)^2 from 0 to pi")

# Data analysis
result = await wolfram_alpha.analyze("mean, median, std of [1, 2, 3, 4, 5, 6]")
```

The integration exposes tools through the MCP protocol and the results are parsed into structured Python objects.
