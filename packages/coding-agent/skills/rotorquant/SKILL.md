---
name: rotorquant
description: RotorQuant backend integration for efficient LLaMA model inference on modest hardware.
---

# RotorQuant

Integrates with the RotorQuant backend for efficient LLaMA model inference.
Provides optimization pathways for models like Ornith 1.5 35B A3B on modest hardware.

## Setup

1. Ensure RotorQuant/LLaMA GGUF backend is installed and configured
2. Set environment variables for the GGUF model path and backend
3. In Prime Agent, configure the backend via `/settings`

## Usage

```python
import rotorquant

# Initialize the RotorQuant backend
backend = await rotorquant.initialize()

# Load a GGUF model optimized for RotorQuant
model = await backend.load_model("ornith-1.5-35b-a3b.gguf")

# Run inference with optimization
result = await backend.inference("What is quantum computing?")

# Check backend metrics
metrics = await backend.get_metrics()

# Quantization optimization
optimized = await backend.optimize_quantization("q4_k_m")
```
