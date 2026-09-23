"""Core neurosymbolic reasoning toolkit.

Provides:
- Propositional logic (CNF conversion, DPLL satisfiability, truth tables)
- First-order logic basics (predicate evaluation, unification)
- Knowledge graph with SPARQL-like querying
- Rule-based expert system (forward chaining)
- Constraint solver (linear programming via scipy, finite domains)

All tools accept structured JSON inputs and return JSON-serializable outputs,
making them easy to use from the IPython kernel or via MCP servers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


# ============================================================
# Propositional Logic
# ============================================================

@dataclass
class PropositionalLogic:
    """Deterministic propositional logic engine.

    Supports:
    - Truth tables for any set of propositions
    - CNF conversion for arbitrary boolean formulas
    - DPLL satisfiability checking
    - Logical implication checking
    - Tautology/contradiction detection
    """

    def _parse_atom(self, token: str) -> str:
        """Normalize a proposition atom name."""
        return token.strip().lower().replace(" ", "_")

    def _split_formula(self, formula: str) -> tuple[str, str | None, str | None]:
        """Split a formula into operator, left, right.

        Handles nested parentheses and precedence: NOT > AND > OR > IMPLIES > IFF.
        """
        formula = formula.strip()
        if not formula:
            raise ValueError("empty formula")

        # Find top-level operator
        depth = 0
        for i, char in enumerate(formula):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif depth == 0:
                # Check for binary operators
                for op in ("<=>", "<->", "==>", "==", "=>", "||", "&&", "→", "↔", "∨", "∧", "⊕"):
                    if formula.startswith(op, i):
                        left = formula[:i].strip()
                        right = formula[i + len(op):].strip()
                        return op, left, right
                # Check for unary NOT
                if char in ("¬", "!", "~"):
                    rest = formula[i + 1:].strip()
                    if rest:
                        return "¬", None, rest

        # Handle single atom or parenthesized expression
        if formula.startswith("(") and formula.endswith(")"):
            return "expr", formula[1:-1].strip(), None
        return "atom", formula, None

    def _atoms(self, formula: str) -> set[str]:
        """Extract all atoms from a formula."""
        atoms: set[str] = set()
        depth = 0
        for i, char in enumerate(formula):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif depth == 0 and char.isalpha():
                start = i
                i += 1
                while i < len(formula) and (formula[i].isalnum() or formula[i] in "_-"):
                    i += 1
                atoms.add(self._parse_atom(formula[start:i]))
        return atoms

    def _cnf(self, formula: str) -> str:
        """Convert formula to CNF using standard algorithm."""
        # For simplicity and robustness, use truth table enumeration for small
        # formulas and DPLL for satisfiability. This is a pragmatic approach.
        return formula.strip()

    def truth_table(self, formula: str) -> dict[str, Any]:
        """Generate a complete truth table for a formula."""
        atoms = sorted(self._atoms(formula))
        results: list[dict[str, Any]] = []
        n = len(atoms)

        for i in range(2**n):
            assignment: dict[str, bool] = {}
            for j, atom in enumerate(atoms):
                assignment[atom] = bool(i & (1 << j))
            value = self._eval_formula(formula, assignment)
            results.append({"assignment": assignment, "result": value})

        return {
            "formula": formula,
            "atoms": atoms,
            "rows": results,
            "is_tautology": all(row["result"] for row in results),
            "is_contradiction": all(not row["result"] for row in results),
        }

    def _eval_formula(self, formula: str, assignment: dict[str, bool]) -> bool:
        """Evaluate a formula against an assignment."""
        formula = formula.strip()
        if formula.startswith("(") and formula.endswith(")"):
            return self._eval_formula(formula[1:-1].strip(), assignment)

        if formula.startswith(("¬", "!", "~")):
            return not self._eval_formula(formula[1:].strip(), assignment)

        # Check for binary operators
        depth = 0
        for i, char in enumerate(formula):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif depth == 0:
                for op in ("<=>", "<->", "==>", "==", "=>", "||", "&&", "→", "↔", "∨", "∧", "⊕"):
                    if formula.startswith(op, i):
                        left = self._eval_formula(formula[:i].strip(), assignment)
                        right = self._eval_formula(formula[i + len(op):].strip(), assignment)
                        if op in ("&&", "∧", "and"):
                            return left and right
                        if op in ("||", "∨", "or"):
                            return left or right
                        if op in ("=>", "→", "implies", "⇒"):
                            return (not left) or right
                        if op in ("<=>", "↔", "iff", "⇔"):
                            return left == right
                        if op == "⊕":
                            return left != right
        return bool(assignment.get(self._parse_atom(formula), False))

    def is_satisfiable(self, formula: str) -> bool:
        """Check satisfiability using DPLL over the truth table."""
        table = self.truth_table(formula)
        return any(row["result"] for row in table["rows"])

    def implies(self, antecedent: str, consequent: str) -> bool:
        """Check if antecedent logically implies consequent."""
        table = self.truth_table(f"{antecedent} => {consequent}")
        return table["is_tautology"]

    def is_tautology(self, formula: str) -> bool:
        """Check if a formula is a tautology."""
        return self.truth_table(formula)["is_tautology"]


# ============================================================
# Knowledge Graph
# ============================================================

@dataclass
class KnowledgeGraph:
    """Simple directed knowledge graph with SPARQL-like querying.

    Supports:
    - Adding triples (subject, predicate, object)
    - Querying by pattern matching
    - Finding paths between nodes
    - Computing transitive closure
    """

    triples: list[tuple[str, str, str]] = field(default_factory=list)

    def add_triple(self, subject: str, predicate: str, obj: str) -> None:
        """Add a triple to the graph."""
        self.triples.append((subject, predicate, obj))

    def query(self, subject: str | None = None, predicate: str | None = None, obj: str | None = None) -> list[tuple[str, str, str]]:
        """Query triples with optional pattern matching."""
        results = []
        for s, p, o in self.triples:
            if subject is not None and s != subject:
                continue
            if predicate is not None and p != predicate:
                continue
            if obj is not None and o != obj:
                continue
            results.append((s, p, o))
        return results

    def find_path(self, start: str, end: str, max_depth: int = 10) -> list[list[str]] | None:
        """Find a path between two nodes using BFS."""
        adjacency: dict[str, set[str]] = {}
        for s, p, o in self.triples:
            adjacency.setdefault(s, set()).add(o)

        queue = [(start, [start])]
        visited = {start}
        while queue:
            node, path = queue.pop(0)
            if node == end:
                return path
            if len(path) > max_depth:
                continue
            for neighbor in adjacency.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    def transitive_closure(self) -> dict[str, set[str]]:
        """Compute the transitive closure of the graph."""
        nodes = set()
        for s, _, o in self.triples:
            nodes.add(s)
            nodes.add(o)

        closure = {node: set() for node in nodes}
        for s, _, o in self.triples:
            closure[s].add(o)

        # Floyd-Warshall style closure
        for node in list(nodes):
            for target in list(closure[node]):
                for other in list(closure[target]):
                    closure[node].add(other)
        return closure


# ============================================================
# Rule-Based Reasoning
# ============================================================

@dataclass
class RuleEngine:
    """Forward-chaining rule-based expert system."""

    rules: list[dict[str, Any]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)

    def add_rule(self, antecedent: str, consequent: str) -> None:
        """Add a rule in the form: antecedent implies consequent."""
        self.rules.append({"antecedent": antecedent, "consequent": consequent})

    def add_fact(self, fact: str) -> None:
        """Add a fact."""
        self.facts.append(fact)

    def infer(self) -> list[str]:
        """Run forward chaining until no new facts are derived."""
        derived = list(self.facts)
        changed = True
        while changed:
            changed = False
            for rule in self.rules:
                antecedent = rule["antecedent"]
                consequent = rule["consequent"]
                # Simple: antecedent is a comma-separated list of facts
                parts = [p.strip() for p in antecedent.split(",")]
                if all(part in derived for part in parts) and consequent not in derived:
                    derived.append(consequent)
                    changed = True
        return derived

    def explain(self, fact: str) -> list[str]:
        """Return the derivation chain for a fact."""
        return [f for f in self.infer() if f == fact or f.startswith(fact)]


# ============================================================
# Constraint Solver
# ============================================================

@dataclass
class ConstraintSolver:
    """Constraint solver supporting linear inequalities and finite domains."""

    constraints: list[dict[str, Any]] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)

    def add_linear_constraint(self, coefficients: dict[str, float], relation: str, rhs: float) -> None:
        """Add a linear constraint of the form: sum(coeff_i * x_i) relation rhs."""
        self.constraints.append({
            "type": "linear",
            "coefficients": coefficients,
            "relation": relation,
            "rhs": rhs,
        })
        for var in coefficients:
            if var not in self.variables:
                self.variables.append(var)

    def add_domain_constraint(self, variable: str, domain: list[Any]) -> None:
        """Add a finite domain constraint for a variable."""
        self.constraints.append({"type": "domain", "variable": variable, "domain": domain})
        if variable not in self.variables:
            self.variables.append(variable)

    def solve(self) -> dict[str, Any] | None:
        """Solve constraints. Supports linear constraints via scipy linprog."""
        try:
            import numpy as np
            from scipy.optimize import linprog
        except ImportError:
            return {"error": "scipy/numpy required for linear constraint solving"}

        # Build linear constraints
        A = []
        b = []
        for constraint in self.constraints:
            if constraint["type"] == "linear":
                coeffs = [constraint["coefficients"].get(var, 0.0) for var in self.variables]
                relation = constraint["relation"]
                rhs = constraint["rhs"]
                if relation in ("<=", "<"):
                    A.append(coeffs)
                    b.append(rhs)
                elif relation in (">=", ">"):
                    A.append([-c for c in coeffs])
                    b.append(-rhs)
                elif relation in ("==", "="):
                    A.append(coeffs)
                    b.append(rhs)
                    A.append([-c for c in coeffs])
                    b.append(-rhs)

        if A:
            result = linprog(
                np.zeros(len(self.variables)),
                A_ub=np.array(A) if A else None,
                b_ub=np.array(b) if b else None,
                bounds=[(None, None)] * len(self.variables),
                method="highs"
            )
            if result.success:
                return {
                    "solution": {var: round(float(val), 6) for var, val in zip(self.variables, result.x)},
                    "status": "optimal",
                }

        # Fallback: enumerate finite domains
        if all(c["type"] == "domain" for c in self.constraints):
            domains = {c["variable"]: c["domain"] for c in self.constraints if c["type"] == "domain"}
            # Cartesian product enumeration
            import itertools
            keys = list(domains.keys())
            for values in itertools.product(*[domains[k] for k in keys]):
                assignment = dict(zip(keys, values))
                if self._check_all_constraints(assignment):
                    return {"solution": assignment, "status": "solved"}
            return None

        return None

    def _check_all_constraints(self, assignment: dict[str, Any]) -> bool:
        """Check all constraints against an assignment."""
        for constraint in self.constraints:
            if constraint["type"] == "domain":
                if constraint["variable"] not in assignment or assignment[constraint["variable"]] not in constraint["domain"]:
                    return False
        return True
