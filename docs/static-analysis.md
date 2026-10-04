# Static analysis policy

Julia package tests, Aqua, real operator conformance, workspace adapters, and the
Jupyter integration are required gates. Whole-package JET remains advisory while
its findings are investigated.

The release verification on Julia 1.12.6 reduced JET findings from 87 to 77
(the earlier baseline was 81 in the same dependency environment). It exposed a
real `OperatorVocabulary` default-constructor bug, now covered by regression
assertions. Explicit dictionary and replay-index types, and a local singleton
state reference, removed the other ten reports in total.

The remaining reports have not all been classified. Dynamic payload parsing,
reflection, and runtime value types need individual investigation; a report is
not dismissed just because runtime tests pass. Reproduce suspected defects,
fix real failures with owning regression tests, and narrow inference where the
API can express its types accurately. Do not replace these paths with blanket
suppression or treat a decreasing count as proof of correctness.

JET can become a required gate after supported Julia/dependency versions have a
reviewed baseline and findings can reliably distinguish new defects. Until then,
its complete CI output stays visible even when the optional step fails.
