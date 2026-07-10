"""
knowledge_graph/validation.py — Phase C0 Task 6: Graph Validation
Contracts.

SCOPE: this module defines ONLY the interfaces (abstract base classes)
a future C5 Validation phase will implement -- mirrors
compiler/validation.py's own overall shape (status/errors/warnings,
per-area summaries -- see knowledge_graph/schema.py's
`KnowledgeGraphValidationReport`, whose field set these contracts are
designed to be able to fill) WITHOUT containing a single concrete
validation rule. No method on any class below is implemented; every one
raises NotImplementedError, exactly the standard-library `abc` pattern's
intended use (a contract describing capability, not behavior).

WHY SIX SEPARATE CONTRACTS, NOT ONE: mirrors compiler/validation.py's
own internal structure, which already splits into distinct private
passes (`_validate_registry_integrity`, `_validate_reference_integrity`,
`_validate_relationship_integrity`, `_validate_compiler_state_integrity`,
`_check_id_determinism`) composed together by one
`validate_compiler_state()` entry point. This module makes that same
split explicit and public, one contract per concern, so a future C5
implementation can implement (or replace) each concern independently --
e.g. swapping in a stricter DeterminismValidator without touching
NodeValidator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .node import GraphNodeBase
from .edge import GraphEdgeBase
from .schema import KnowledgeGraph, KnowledgeGraphValidationReport, KnowledgeGraphReadinessReport


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
VALIDATION_CONTRACT_VERSION = "C0.1"


class NodeValidator(ABC):
    """Contract for validating one graph node in isolation (shape,
    required fields, node_type membership in
    knowledge_graph.node.FUTURE_NODE_TYPES, compiler_object_id/
    compiler_registry consistency, ...). The Compiler IR analogue this
    mirrors is compiler/validation.py's own
    `_validate_canonical_object_integrity()` -- same concern, one level
    up the stack (a node, not a canonical object)."""

    @abstractmethod
    def validate_node(self, node: GraphNodeBase) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts (empty if the node is valid).
        Never implemented in Phase C0."""
        raise NotImplementedError


class EdgeValidator(ABC):
    """Contract for validating one graph edge in isolation (shape,
    required fields, edge_type membership in
    knowledge_graph.edge.FUTURE_EDGE_TYPES, directed flag consistency,
    ...). Mirrors compiler/validation.py's own
    `_validate_relationship_integrity()`, one level up."""

    @abstractmethod
    def validate_edge(self, edge: GraphEdgeBase) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts (empty if the edge is valid).
        Never implemented in Phase C0."""
        raise NotImplementedError


class GraphValidator(ABC):
    """Contract for validating an entire KnowledgeGraph as a whole
    (every node + every edge together) -- the composed, top-level
    contract, analogous to compiler/validation.py's own
    `validate_compiler_state()` entry point. A concrete implementation
    is expected to internally use NodeValidator/EdgeValidator/
    IntegrityValidator/DeterminismValidator (this module's own other
    contracts) the same way `validate_compiler_state()` internally calls
    its own private per-area passes."""

    @abstractmethod
    def validate_graph(self, graph: KnowledgeGraph) -> KnowledgeGraphValidationReport:
        """Returns a fully-populated KnowledgeGraphValidationReport.
        Never implemented in Phase C0."""
        raise NotImplementedError


class IntegrityValidator(ABC):
    """Contract for cross-referential integrity: every edge's
    source_node_id/target_node_id actually resolves to a node in the
    graph's own node registry, every node's compiler_object_id/
    compiler_registry actually resolves to a real Compiler IR item, no
    duplicate node/edge ids, etc. Mirrors compiler/validation.py's own
    `_validate_reference_integrity()` +
    `_validate_compiler_state_integrity()`, combined at the graph
    level."""

    @abstractmethod
    def validate_integrity(self, graph: KnowledgeGraph) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts. Never implemented in Phase
        C0."""
        raise NotImplementedError


class DeterminismValidator(ABC):
    """Contract for confirming a graph build is deterministic: given the
    same Compiler IR input twice, the same graph (same node/edge ids,
    same urns, same fingerprint) is produced both times. Mirrors
    compiler/validation.py's own `_check_id_determinism()`, one level
    up the stack."""

    @abstractmethod
    def validate_determinism(
        self, graph_a: KnowledgeGraph, graph_b: KnowledgeGraph
    ) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts describing any divergence
        between two graphs built from the same input. Never implemented
        in Phase C0."""
        raise NotImplementedError


class ReadinessValidator(ABC):
    """Contract for the read-only readiness verdict a future C8/C9 phase
    will compute -- mirrors compiler/fingerprints.py's own
    `generate_compiler_readiness_report()`, one level up. Distinct from
    GraphValidator: readiness asks "is this graph usable downstream?"
    (a checklist of already-computed facts), not "is this graph
    internally correct?" (GraphValidator's own concern) -- the exact
    same validation/readiness split compiler/validation.py vs.
    compiler/fingerprints.py already establishes for Compiler IR."""

    @abstractmethod
    def validate_readiness(self, graph: KnowledgeGraph) -> KnowledgeGraphReadinessReport:
        """Returns a fully-populated KnowledgeGraphReadinessReport.
        Never implemented in Phase C0."""
        raise NotImplementedError