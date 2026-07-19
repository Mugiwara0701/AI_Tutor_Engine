"""
modules/relationship_discovery_engine/graph_integrity_validator.py —
M5.2E Deliverable #6: Graph Integrity Validation.

Validates a SemanticGraph for:
- Duplicate nodes (same node_id).
- Duplicate edges (same edge_id).
- Orphan nodes (no connecting edges).
- Broken references (edge src/tgt not in node set).
- Invalid relationship types.
- Confidence consistency.
- Cycle detection (optional, per config).

Reuses M5.1's ValidationResult / ValidationDiagnostic contracts.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

from modules.relationship_discovery_engine.config import (
    RelationshipDiscoveryEngineConfig,
    default_config,
)
from modules.relationship_discovery_engine.enums import RelationshipType
from modules.relationship_discovery_engine.models import SemanticGraph

__all__ = [
    "GraphIntegrityValidator",
    "default_graph_integrity_validator",
]

_VALID_TYPES: FrozenSet[str] = frozenset(rt.value for rt in RelationshipType)


class GraphIntegrityValidator:
    """
    Validates the full structural and semantic integrity of a
    SemanticGraph using M5.1's ValidationResult contracts.
    """

    def __init__(
        self,
        config: Optional[RelationshipDiscoveryEngineConfig] = None,
    ) -> None:
        self._cfg = config or default_config

    def validate(self, graph: SemanticGraph) -> ValidationResult:
        """
        Run all integrity checks on *graph*.
        Returns SUCCESS if all checks pass, otherwise a ValidationResult
        with diagnostics.
        """
        diagnostics: List[ValidationDiagnostic] = []
        node_ids: Set[str] = set()

        # 1. Duplicate nodes
        for node in graph.nodes:
            if node.node_id in node_ids:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="GIV001",
                    message=f"Duplicate node_id {node.node_id!r} in graph.",
                    processor_name="GraphIntegrityValidator",
                ))
            else:
                node_ids.add(node.node_id)

        # 2. Duplicate edges
        edge_ids: Set[str] = set()
        for edge in graph.edges:
            if edge.edge_id in edge_ids:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="GIV002",
                    message=f"Duplicate edge_id {edge.edge_id!r} in graph.",
                    processor_name="GraphIntegrityValidator",
                ))
            else:
                edge_ids.add(edge.edge_id)

        # 3. Broken references
        for edge in graph.edges:
            sev = (
                DiagnosticSeverity.ERROR
                if self._cfg.strict_graph_validation
                else DiagnosticSeverity.WARNING
            )
            if edge.source_node_id not in node_ids:
                diagnostics.append(ValidationDiagnostic(
                    severity=sev,
                    code="GIV003",
                    message=(
                        f"Edge {edge.edge_id!r}: source node "
                        f"{edge.source_node_id!r} not found in graph nodes."
                    ),
                    processor_name="GraphIntegrityValidator",
                ))
            if edge.target_node_id not in node_ids:
                diagnostics.append(ValidationDiagnostic(
                    severity=sev,
                    code="GIV004",
                    message=(
                        f"Edge {edge.edge_id!r}: target node "
                        f"{edge.target_node_id!r} not found in graph nodes."
                    ),
                    processor_name="GraphIntegrityValidator",
                ))

        # 4. Invalid relationship types
        for edge in graph.edges:
            if edge.relationship_type not in _VALID_TYPES:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="GIV005",
                    message=(
                        f"Edge {edge.edge_id!r}: invalid relationship_type "
                        f"{edge.relationship_type!r}."
                    ),
                    processor_name="GraphIntegrityValidator",
                ))

        # 5. Confidence consistency
        for edge in graph.edges:
            if not 0.0 <= edge.confidence <= 1.0:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="GIV006",
                    message=(
                        f"Edge {edge.edge_id!r}: confidence {edge.confidence!r} "
                        f"out of range [0.0, 1.0]."
                    ),
                    processor_name="GraphIntegrityValidator",
                ))

        # 6. Orphan nodes
        connected: Set[str] = set()
        for e in graph.edges:
            connected.add(e.source_node_id)
            connected.add(e.target_node_id)

        for node in graph.nodes:
            if node.node_id not in connected:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="GIV007",
                    message=(
                        f"Node {node.node_id!r} (object_key={node.object_key!r}) "
                        f"is an orphan — no edges connect to it."
                    ),
                    processor_name="GraphIntegrityValidator",
                ))

        # 7. Cycle detection (optional)
        if self._cfg.detect_cycles:
            cycles = self._detect_cycles(graph, node_ids)
            for cycle in cycles:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="GIV008",
                    message=f"Cycle detected in graph: {' → '.join(cycle)}.",
                    processor_name="GraphIntegrityValidator",
                ))

        return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS

    # ------------------------------------------------------------------
    # Cycle detection (DFS-based, deterministic)
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_cycles(
        graph: SemanticGraph,
        node_ids: Set[str],
    ) -> List[Tuple[str, ...]]:
        """
        Detect cycles using iterative DFS.  Returns a list of cycle
        tuples (each a sequence of node_ids forming the cycle).
        Only forward edges are considered.
        """
        adjacency: Dict[str, List[str]] = defaultdict(list)
        for edge in graph.edges:
            adjacency[edge.source_node_id].append(edge.target_node_id)

        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[Tuple[str, ...]] = []

        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbour in sorted(adjacency.get(node, [])):  # sorted for determinism
                if neighbour not in visited:
                    dfs(neighbour, path)
                elif neighbour in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbour)
                    cycles.append(tuple(path[cycle_start:]))

            path.pop()
            rec_stack.discard(node)

        for nid in sorted(node_ids):  # sorted for determinism
            if nid not in visited:
                dfs(nid, [])

        return cycles


#: Module-level singleton.
default_graph_integrity_validator = GraphIntegrityValidator()
