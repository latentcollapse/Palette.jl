#!/usr/bin/env python3
"""
Regression tests for julia_analyzer.py's CI-facing exit code.

Found by direct testing, not inferred: deleting a Phase-required struct
entirely (ShellEscape) from a copy of src/Neura.jl still exited 0 from
`julia_analyzer.py src/Neura.jl --verbose` -- the exact invocation
.github/workflows/julia-ci.yml's "Run static analysis preflight" step
uses. Two independent bugs caused this: required-component issues were
capped at Severity.WARNING (never ERROR), and validate_phases() extended
a self.all_issues list nothing else in the file ever read, instead of the
self.parser.issues list get_summary()'s error count actually reads. A gate
that cannot fail on the one thing it exists to check is not a gate --
this locks in that it now can.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
REAL_SRC = REPO_DIR / "src" / "Neura.jl"
ANALYZER = REPO_DIR / "julia_analyzer.py"


def _run(path: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ANALYZER), str(path), *extra_args],
        capture_output=True, text=True,
    )


def test_real_source_passes_clean():
    r = _run(REAL_SRC, "--verbose")
    assert r.returncode == 0, r.stdout + r.stderr


def test_deleted_required_struct_fails_the_gate():
    src = REAL_SRC.read_text()
    mutated = re.sub(r"struct ShellEscape.*?\nend\n", "", src, flags=re.S)
    assert "struct ShellEscape" not in mutated, "test setup itself failed to remove the struct"
    with tempfile.TemporaryDirectory() as tmp:
        mutated_path = Path(tmp) / "Neura.jl"
        mutated_path.write_text(mutated)
        r = _run(mutated_path, "--verbose")
        assert r.returncode == 1, f"expected the gate to fail; got exit 0.\n{r.stdout}"
        assert "ShellEscape" in r.stdout


def test_json_mode_reports_the_same_error():
    src = REAL_SRC.read_text()
    mutated = re.sub(r"struct ShellEscape.*?\nend\n", "", src, flags=re.S)
    with tempfile.TemporaryDirectory() as tmp:
        mutated_path = Path(tmp) / "Neura.jl"
        mutated_path.write_text(mutated)
        r = _run(mutated_path, "--json")
        import json
        payload = json.loads(r.stdout)
        assert payload["errors"] >= 1
        assert any("ShellEscape" in i["message"] for i in payload["issues"] if i["severity"] == "ERROR")


if __name__ == "__main__":
    test_real_source_passes_clean()
    test_deleted_required_struct_fails_the_gate()
    test_json_mode_reports_the_same_error()
    print("all julia_analyzer.py regression tests passed")
