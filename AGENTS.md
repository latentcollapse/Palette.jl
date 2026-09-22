# Operator-surface lab — agent rules

## Authorized scope

**Experiment 001 only.**

Build and prove a persistent Julia/IJulia kernel that can act as a structured
AI-agent operator surface. Produce `docs/EXPERIMENT_001_RESULTS.md` when done.

## DO NOT

- Integrate with Project Neura, NeuraBash, Prime Agent, or EnigmaOS
- Implement a kernel generator, CUDA, Lava, Mojo, or ML inference
- Build a custom scheduler, privilege/security enforcement layer, or custom Jupyter frontend/protocol
- Claim full POSIX compatibility
- Begin Experiment 002
- Hide failed experiments or invent passing test output

## ALWAYS

- Prefer Julia-native APIs over wrapping Base merely to add LOC
- Keep `exec(...)` (structured) distinct from `bash(...)` (legacy escape)
- Prefer structured kernel/Jupyter messages over scraping terminal output
- Add tests that drive the real shipped entry points
- Record exact commands and failures in `docs/EXPERIMENT_001_RESULTS.md`
- Keep commits small and reversible
- In results, document ambient Julia authority; do not imply Experiment 001 is a security boundary
- Leave privilege/security enforcement to a later experiment (do not invent a fake fence here)

## Environment notes

Host probe at lab creation (CachyOS workstation):

- Julia: see `VERSIONS.lock` / README
- This lab is independent of NeuraBash and Prime Agent
