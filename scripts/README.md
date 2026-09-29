# Scripts

- `real_ijulia_proof.py` -- the real Phase 10 integration demo: launches a
  live IJulia kernel, drives it over the actual Jupyter wire protocol, and
  proves cross-request state persistence. See its own docstring for setup.
- `ijulia_test_harness.jl` -- retired; kept only as a pointer to where the
  real tests actually live (`test/runtests.jl` and `real_ijulia_proof.py`
  above). Its own docstring explains why.

Run the test suite with `julia --project=. -e 'using Pkg; Pkg.test()'` from
the repo root -- no separate script needed for that.
