"""Unified Neurosymbolic Harness Implementation.

Combines symbolic reasoning, knowledge graphs, rule engines, constraint
solving, and free-model optimization into a single coherent harness.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .reasoning import PropositionalLogic, KnowledgeGraph, RuleEngine, ConstraintSolver
from .symbolic_memory import SymbolicMemory
from .free_model_optimizer import FreeModelOptimizer


class NeurosymbolicHarness:
    """Unified neurosymbolic harness.

    Provides a coherent interface for:
    - Symbolic reasoning
    - Knowledge graph reasoning
    - Rule-based expert systems
    - Constraint solving
    - Free-model reasoning optimization
    - Persistent symbolic memory
    """

    def __init__(self, harness_state: Optional[Any] = None):
        self.harness_state = harness_state
        self.logic = PropositionalLogic()
        self.graph = KnowledgeGraph()
        self.rules = RuleEngine()
        self.solver = ConstraintSolver()
        self.memory = SymbolicMemory(harness_state)
        self.optimizer = FreeModelOptimizer(harness_state)

    # ============================================================
    # Symbolic Reasoning
    # ============================================================

    def truth_table(self, formula: str) -> Dict[str, Any]:
        """Generate a truth table for a propositional formula."""
        return self.logic.truth_table(formula)

    def is_satisfiable(self, formula: str) -> bool:
        """Check if a propositional formula is satisfiable."""
        return self.logic.is_satisfiable(formula)

    def is_tautology(self, formula: str) -> bool:
        """Check if a propositional formula is a tautology."""
        return self.logic.is_tautology(formula)

    def implies(self, antecedent: str, consequent: str) -> bool:
        """Check if antecedent implies consequent."""
        return self.logic.implies(antecedent, consequent)

    # ============================================================
    # Knowledge Graph
    # ============================================================

    def add_triple(self, subject: str, predicate: str, obj: str) -> None:
        """Add a triple to the knowledge graph."""
        self.graph.add_triple(subject, predicate, obj)
        self.memory.store_knowledge_graph(
            name="active_knowledge_graph",
            triples=self.graph.triples,
            metadata={"source": "neurosymbolic_harness"},
        )

    def query_graph(self, subject: str | None = None, predicate: str | None = None, obj: str | None = None) -> List[Tuple[str, str, str]]:
        """Query the knowledge graph."""
        return self.graph.query(subject, predicate, obj)

    def find_path(self, start: str, end: str, max_depth: int = 10) -> List[List[str]]:
        """Find paths in the knowledge graph."""
        return self.graph.find_paths(start, end, max_depth)

    def transitive_closure(self) -> Dict[str, set[str]]:
        """Compute transitive closure of the knowledge graph."""
        return self.graph.transitive_closure()

    # ============================================================
    # Rule-Based Reasoning
    # ============================================================

    def add_rule(self, antecedent: str, consequent: str) -> None:
        """Add a rule to the rule engine."""
        self.rules.add_rule(antecedent, consequent)
        self.memory.store_rule(antecedent, consequent, source="neurosymbolic_harness")

    def add_fact(self, fact: str) -> None:
        """Add a fact to the rule engine."""
        self.rules.add_fact(fact)
        self.memory.store_proposition(fact, truth_value=True, source="neurosymbolic_harness")

    def infer(self) -> List[str]:
        """Run forward chaining inference."""
        return self.rules.infer()

    # ============================================================
    # Constraint Solving
    # ============================================================

    def solve_constraints(self, constraints: List[Dict[str, Any]], variables: Optional[List[str]] = None) -> Dict[str, Any] | None:
        """Solve a set of constraints."""
        self.solver.constraints = constraints
        if variables:
            self.solver.variables = variables
        solution = self.solver.solve()
        if solution and "solution" in solution:
            self.memory.store_constraint_solution(
                problem=json.dumps(constraints),
                solution=solution["solution"],
                method="constraint_solver",
            )
        return solution

    # ============================================================
    # Free Model Optimization
    # ============================================================

    def optimize_for_free_model(self, prompt: str, model: str) -> str:
        """Optimize a prompt for a free model."""
        return self.optimizer.distill_reasoning(prompt, model)

    def cached_reasoning(self, prompt: str, model: str, temperature: float = 0.7) -> str:
        """Get cached reasoning or return a cache miss signal."""
        return self.optimizer.cached_reasoning(prompt, model, temperature)

    # ============================================================
    # Statistics and Maintenance
    # ============================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive harness statistics."""
        memory_stats = self.memory.get_statistics()
        cache_stats = self.optimizer.get_cache_statistics()
        return {
            "memory": memory_stats,
            "cache": cache_stats,
            "knowledge_graph": {
                "triples": len(self.graph.triples),
                "subjects": len(self.graph._subjects),
                "predicates": len(self.graph._predicates),
                "objects": len(self.graph._objects),
            },
            "rules": len(self.rules.rules),
            "facts": len(self.rules.facts),
            "constraints": len(self.solver.constraints),
        }

    def clear_all(self) -> None:
        """Clear all symbolic memory."""
        for path in ["propositions", "inferences", "knowledge_graphs", "rules", "constraints"]:
            self.memory.clear_symbolic_memory(path)
        self.optimizer.clear_cache()
