"""RotorQuant Backend Integration for Prime Agent.

Provides integration with RotorQuant and ggml-backed LLaMA model inference
for efficient operation on modest hardware.
"""

from .integration import RotorQuantIntegration

__all__ = ["RotorQuantIntegration"]
