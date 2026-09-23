"""Neurosymbolic reasoning tools for Prime Agent.

This skill provides symbolic reasoning capabilities (propositional logic,
constraint solving, knowledge graph reasoning, rule-based inference) that
compose with neural LLM outputs. It is designed to help even the free
OpenRouter models punch above their weight by providing deterministic,
verifiable reasoning alongside probabilistic language generation.
"""

from .reasoning import (
    SymbolicReasoner,
    PropositionalLogic,
    KnowledgeGraph,
    RuleEngine,
    ConstraintSolver,
)

__all__ = [
    "SymbolicReasoner",
    "PropositionalLogic",
    "KnowledgeGraph",
    "RuleEngine",
    "ConstraintSolver",
]
