# Contributing to Palette

Palette owns its Julia operator API, supervised host, portable MCP adapters, and
public documentation. Harness orchestration and deployment-specific language
kernels belong in separate projects.

Start with the [README](README.md), [installation guide](docs/install.md), and
[development rules](AGENTS.md). Work on a feature branch and describe a concrete
trigger, resulting behavior, and actual verification in the pull request.
Preserve supported behavior and keep changes focused.

Run Julia package tests for Julia changes, Rust tests for host changes, and each
modified test file directly. Adapter and process changes need real integration
checks against the affected host implementations. The full Linux verification
entrypoint is `runtime/security/verify_operator.py`; its test environment must
use this checkout. Required checks must pass before merging. Whole-package JET
analysis currently follows the [advisory policy](docs/static-analysis.md).

Keep internal experiments, raw run receipts, exploratory reports, and development
research in the gitignored `.archive/` or a private external archive. Preserve
revisions, environment versions, hashes, attribution, and failed attempts for
future research publication. Public `docs/` should explain supported behavior,
installation, and limits. Never include credentials or private deployment state.

The optional [operator briefing](BRAIN_BLAST.md) helps users discover how to work
in a persistent Julia world; its examples should stay executable and its claims
should match the current implementation.
