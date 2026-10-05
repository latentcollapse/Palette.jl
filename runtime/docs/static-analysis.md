# Static analysis policy

Julia package tests, Aqua, real operator conformance, workspace adapters, and the
Jupyter integration are required gates. Whole-package JET remains advisory while
its findings are investigated; the complete optional CI output stays visible.

Reproduce suspected defects and fix real failures with owning regression tests.
Narrow inference where the API can express its types accurately. Do not dismiss
a report simply because runtime tests pass, use blanket suppression, or treat a
decreasing finding count as proof of correctness. Remaining findings are not all
classified.

JET can become a required gate after supported Julia/dependency versions have a
reviewed baseline and findings can reliably distinguish new defects. Raw finding
inventories, experimental triage, and run receipts belong in the private research
archive. Public documentation records the supported verification policy.
