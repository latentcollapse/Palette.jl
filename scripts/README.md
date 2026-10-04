# Development scripts

- `session_loop.jl`: persistent worker entrypoint used by the host and launcher.
- `julia_analyzer.py`: approximate static preflight; real Julia tests are authoritative.
- `test_julia_analyzer.py`: preflight regression controls.
- `check-test-policy.mjs`: incremental test hygiene gate.
- `real_ijulia_proof.py`: integration with a live IJulia kernel over Jupyter/ZMQ.

Run process conformance through `security/verify_operator.py`.
