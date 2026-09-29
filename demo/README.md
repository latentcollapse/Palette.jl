# Demo

The Phase 10 integration demo ended up not needing a separate directory:

- `Neura.run_demo()` (in `src/Neura.jl`) is the in-package, one-call
  demonstration -- real eval, real shell escape, real discovery, real
  receipts, run in-process.
- `scripts/real_ijulia_proof.py` is the real, out-of-process version --
  drives an actual IJulia kernel over the real Jupyter wire protocol.

This directory is kept empty rather than holding a redundant copy of either.
