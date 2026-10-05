"""Reject writable mounts that expose protected host paths."""
from pathlib import Path


def require_disjoint(writable, protected):
    for writable_path in writable:
        left = Path(writable_path).resolve()
        for protected_path in protected:
            right = Path(protected_path).resolve()
            if left == right or left.is_relative_to(right) or right.is_relative_to(left):
                raise PermissionError(f"Writable path {left} must not overlap protected path {right}")


def require_preserved_roots(writable, roots):
    for writable_path in writable:
        left = Path(writable_path).resolve()
        for root in roots:
            if Path(root).is_relative_to(left):
                raise PermissionError(f"Writable path {left} must not overlap sandbox root {root}")
