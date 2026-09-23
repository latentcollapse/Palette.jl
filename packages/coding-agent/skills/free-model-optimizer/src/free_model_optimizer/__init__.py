"""Free Model Optimizer for Prime Agent.

Provides techniques to enhance reasoning capabilities of free OpenRouter models:
- Self-consistency with majority voting
- Tool-augmented reasoning
- Neural-symbolic distillation
- Reasoning caching
- Ensemble methods
"""

from .optimizer import FreeModelOptimizer

__all__ = ["FreeModelOptimizer"]
