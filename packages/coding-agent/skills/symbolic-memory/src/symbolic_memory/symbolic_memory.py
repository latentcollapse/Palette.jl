"""Symbolic Memory Implementation for Prime Agent.

Extends the persistent harness with symbolic reasoning storage capabilities
designed to work with the neurosymbolic reasoning toolkit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..harness import get_harness_state, HarnessState, HarnessEntry


@dataclass
class PropositionalMemory:
    """Store logical propositions with their truth values and provenance."""

    proposition: str
    truth_value: bool | None  # True, False, or None for unknown
    confidence: float = 1.0  # 0.0 to 1.0
    source: str = "reasoning"  # where this came from
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceResult:
    """Store the result of a logical inference."""

    premises: List[str]
    conclusion: str
    inference_type: str  # deduction, induction, abduction, etc.
    valid: bool  # whether the inference is logically valid
    sound: bool | None  # whether premises are true (if known)
    chain: List[str] = field(default_factory=list)  # step-by-step reasoning
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGraphSnapshot:
    """Store a snapshot of a knowledge graph."""

    name: str
    triples: List[tuple[str, str, str]]  # (subject, predicate, object)
    node_count: int
    edge_count: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class SymbolicMemory:
    """Symbolic memory manager for Prime Agent harness.

    This class provides methods to store and retrieve symbolic reasoning
    artifacts in the persistent harness state.
    """

    def __init__(self, harness_state: Optional[HarnessState] = None):
        self.harness = harness_state or get_harness_state()
        self._ensure_symbolic_memory_setup()

    def _ensure_symbolic_memory_setup(self) -> None:
        """Ensure the harness has the necessary symbolic memory entries."""
        # Create path entries if they don't exist
        paths = ["propositions", "inferences", "knowledge_graphs", "rules", "constraints"]
        for path in paths:
            entry = self.harness.get("memory", f"symbolic-{path}", global_=False)
            if entry is None:
                self.harness.create_memory(
                    title=f"Symbolic {path.title()}",
                    content=f"Storage for symbolic {path}",
                    id=f"symbolic-{path}",
                    path="symbolic",
                    metadata={"type": f"symbolic-{path}"},
                )

    # ============================================================
    # Propositional Memory
    # ============================================================

    def store_proposition(
        self,
        proposition: str,
        truth_value: bool | None = None,
        confidence: float = 1.0,
        source: str = "reasoning",
        metadata: Optional[Dict[str, Any]] = None,
        *,
        global_: bool = False,
    ) -> str:
        """Store a logical proposition in symbolic memory.

        Returns the entry ID.
        """
        entry_id = f"prop_{hash(proposition) & 0x7FFFFFFF:08x}"
        memory = PropositionalMemory(
            proposition=proposition,
            truth_value=truth_value,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
        )

        entry = self.harness.upsert(
            "memory",
            title=f"Proposition: {proposition[:50]}...",
            content=json.dumps(memory.__dict__, indent=2),
            id=entry_id,
            path="symbolic/propositions",
            metadata=memory.__dict__,
            global_=global_,
        )
        return entry.id

    def get_proposition(self, proposition: str, *, global_: bool = False) -> Optional[PropositionalMemory]:
        """Retrieve a proposition by its text."""
        entry_id = f"prop_{hash(proposition) & 0x7FFFFFFF:08x}"
        entry = self.harness.get("memory", entry_id, global_=global_)
        if entry and entry.path == "symbolic/propositions":
            try:
                data = json.loads(entry.content)
                return PropositionalMemory(**data)
            except Exception:
                return None
        return None

    def query_propositions(
        self,
        truth_value: bool | None = None,
        min_confidence: float = 0.0,
        source: Optional[str] = None,
        *,
        global_: bool = False,
    ) -> List[PropositionalMemory]:
        """Query propositions matching criteria."""
        entries = self.harness.list("memory", global_=global_)
        results = []
        for entry in entries:
            if entry.path != "symbolic/propositions":
                continue
            try:
                data = json.loads(entry.content)
                prop = PropositionalMemory(**data)
                if truth_value is not None and prop.truth_value != truth_value:
                    continue
                if prop.confidence < min_confidence:
                    continue
                if source is not None and prop.source != source:
                    continue
                results.append(prop)
            except Exception:
                continue
        return results

    # ============================================================
    # Inference Result Storage
    # ============================================================

    def store_inference(
        self,
        premises: List[str],
        conclusion: str,
        inference_type: str = "deduction",
        valid: bool = True,
        sound: Optional[bool] = None,
        chain: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        global_: bool = False,
    ) -> str:
        """Store an inference result in symbolic memory.

        Returns the entry ID.
        """
        entry_id = f"inf_{hash(str(premises) + conclusion) & 0x7FFFFFFF:08x}"
        result = InferenceResult(
            premises=premises,
            conclusion=conclusion,
            inference_type=inference_type,
            valid=valid,
            sound=sound,
            chain=chain or [],
            metadata=metadata or {},
        )

        entry = self.harness.upsert(
            "memory",
            title=f"Inference: {' → '.join(premises[-2:])} => {conclusion[:30]}...",
            content=json.dumps(result.__dict__, indent=2),
            id=entry_id,
            path="symbolic/inferences",
            metadata=result.__dict__,
            global_=global_,
        )
        return entry.id

    def get_inference_history(self, *, global_: bool = False, limit: int = 100) -> List[InferenceResult]:
        """Get recent inference results."""
        entries = self.harness.list("memory", global_=global_)
        results = []
        # Sort by timestamp descending (newest first)
        sorted_entries = sorted(
            [e for e in entries if e.path == "symbolic/inferences"],
            key=lambda e: e.updated_at,
            reverse=True,
        )
        for entry in sorted_entries[:limit]:
            try:
                data = json.loads(entry.content)
                results.append(InferenceResult(**data))
            except Exception:
                continue
        return results

    # ============================================================
    # Knowledge Graph Storage
    # ============================================================

    def store_knowledge_graph(
        self,
        name: str,
        triples: List[tuple[str, str, str]],
        metadata: Optional[Dict[str, Any]] = None,
        *,
        global_: bool = False,
    ) -> str:
        """Store a knowledge graph snapshot.

        Returns the entry ID.
        """
        entry_id = f"kg_{hash(name) & 0x7FFFFFFF:08x}"
        snapshot = KnowledgeGraphSnapshot(
            name=name,
            triples=triples,
            node_count=len({s for s, _, o in triples} | {o for _, _, o in triples}),
            edge_count=len(triples),
            metadata=metadata or {},
        )

        entry = self.harness.upsert(
            "memory",
            title=f"Knowledge Graph: {name}",
            content=json.dumps(snapshot.__dict__, indent=2),
            id=entry_id,
            path="symbolic/knowledge_graphs",
            metadata=snapshot.__dict__,
            global_=global_,
        )
        return entry.id

    def get_knowledge_graph(self, name: str, *, global_: bool = False) -> Optional[KnowledgeGraphSnapshot]:
        """Retrieve a knowledge graph by name."""
        entry_id = f"kg_{hash(name) & 0x7FFFFFFF:08x}"
        entry = self.harness.get("memory", entry_id, global_=global_)
        if entry and entry.path == "symbolic/knowledge_graphs":
            try:
                data = json.loads(entry.content)
                return KnowledgeGraphSnapshot(**data)
            except Exception:
                return None
        return None

    # ============================================================
    # Rule Storage
    # ============================================================

    def store_rule(
        self,
        antecedent: str,
        consequent: str,
        confidence: float = 1.0,
        source: str = "learned",
        metadata: Optional[Dict[str, Any]] = None,
        *,
        global_: bool = False,
    ) -> str:
        """Store a logical rule (antecedent implies consequent)."""
        entry_id = f"rule_{hash(antecedent + consequent) & 0x7FFFFFFF:08x}"
        rule_data = {
            "antecedent": antecedent,
            "consequent": consequent,
            "confidence": confidence,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        entry = self.harness.upsert(
            "memory",
            title=f"Rule: {antecedent[:30]}... => {consequent[:30]}...",
            content=json.dumps(rule_data, indent=2),
            id=entry_id,
            path="symbolic/rules",
            metadata=rule_data,
            global_=global_,
        )
        return entry.id

    # ============================================================
    # Constraint Solution Storage
    # ============================================================

    def store_constraint_solution(
        self,
        problem: str,
        solution: Dict[str, Any],
        method: str = "linear_programming",
        metadata: Optional[Dict[str, Any]] = None,
        *,
        global_: bool = False,
    ) -> str:
        """Store a constraint satisfaction solution."""
        entry_id = f"cstr_{hash(problem) & 0x7FFFFFFF:08x}"
        solution_data = {
            "problem": problem,
            "solution": solution,
            "method": method,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        entry = self.harness.upsert(
            "memory",
            title=f"Constraint Solution: {problem[:50]}...",
            content=json.dumps(solution_data, indent=2),
            id=entry_id,
            path="symbolic/constraints",
            metadata=solution_data,
            global_=global_,
        )
        return entry.id

    # ============================================================
    # Utility Methods
    # ============================================================

    def clear_symbolic_memory(self, path: str, *, global_: bool = False) -> int:
        """Clear all entries in a symbolic memory path.

        Returns number of entries cleared.
        """
        entries = self.harness.list("memory", global_=global_)
        cleared = 0
        for entry in entries:
            if entry.path == f"symbolic/{path}":
                self.harness.delete("memory", entry.id, global_=global_)
                cleared += 1
        return cleared

    def get_statistics(self, *, global_: bool = False) -> Dict[str, Any]:
        """Get statistics about symbolic memory usage."""
        entries = self.harness.list("memory", global_=global_)
        stats = {
            "propositions": 0,
            "inferences": 0,
            "knowledge_graphs": 0,
            "rules": 0,
            "constraints": 0,
        }
        for entry in entries:
            if entry.path.startswith("symbolic/"):
                path_part = entry.path.split("/", 1)[1]
                if path_part in stats:
                    stats[path_part] += 1
        stats["total"] = sum(stats.values())
        return stats
