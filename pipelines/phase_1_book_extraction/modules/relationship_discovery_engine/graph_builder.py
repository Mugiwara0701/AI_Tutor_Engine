"""
modules/relationship_discovery_engine/graph_builder.py — M5.2E
Deliverable #4: Semantic Graph Construction.

Builds a SemanticGraph from:
- A list of SemanticEnrichmentResults (M5.2D) → SemanticNodes
- A RelationshipDiscoveryResult → SemanticEdges

SemanticAnchor.anchor_id values are used as node IDs — never regenerated.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.relationship_discovery_engine.config import (
    RelationshipDiscoveryEngineConfig,
    default_config,
)
from modules.relationship_discovery_engine.enums import (
    EdgeStatus,
    GraphBuildOutcome,
    NodeStatus,
)
from modules.relationship_discovery_engine.exceptions import GraphBuildError
from modules.relationship_discovery_engine.models import (
    DEFAULT_GRAPH_VERSION,
    GraphMetadata,
    GraphStatistics,
    RelationshipDiscoveryResult,
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)

__all__ = [
    "SemanticGraphBuilder",
    "default_graph_builder",
    "GRAPH_NAMESPACE",
]

# Stable UUID namespace for graph_id generation (UUID5).
GRAPH_NAMESPACE = uuid.UUID("c3d4e5f6-a7b8-9012-cdef-123456789012")


def _deterministic_graph_id(node_ids: List[str]) -> str:
    name = "|".join(sorted(node_ids))
    return str(uuid.uuid5(GRAPH_NAMESPACE, name or "empty"))


class SemanticGraphBuilder:
    """
    Constructs a SemanticGraph from SemanticEnrichmentResults and a
    RelationshipDiscoveryResult.

    SemanticAnchor.anchor_id values (M5.2D) are used as node IDs.
    They are never regenerated.
    """

    def __init__(
        self,
        config: Optional[RelationshipDiscoveryEngineConfig] = None,
    ) -> None:
        self._cfg = config or default_config

    def build(
        self,
        enrichment_results: List[object],
        discovery_result: RelationshipDiscoveryResult,
        description: str = "",
    ) -> SemanticGraph:
        """
        Build a SemanticGraph.

        Parameters
        ----------
        enrichment_results:
            SemanticEnrichmentResult objects from M5.2D.
        discovery_result:
            RelationshipDiscoveryResult from RelationshipDiscoveryEngine.
        description:
            Optional human-readable description of this graph instance.
        """
        diagnostics: List[str] = []

        # --- Build nodes ---
        nodes_by_id: Dict[str, SemanticNode] = {}
        for result in enrichment_results:
            node = self._result_to_node(result)
            if node is not None:
                if node.node_id in nodes_by_id:
                    diagnostics.append(
                        f"Duplicate node_id {node.node_id!r} from "
                        f"object_key={getattr(result, 'object_key', '?')!r} — skipped."
                    )
                    continue
                nodes_by_id[node.node_id] = node

        # --- Build edges from relationships ---
        edges: List[SemanticEdge] = []
        for rel in discovery_result.relationships:
            # Filter by min confidence
            if rel.confidence.value < self._cfg.min_relationship_confidence:
                diagnostics.append(
                    f"Relationship {rel.relationship_id!r} below confidence "
                    f"threshold ({rel.confidence.value:.4f} < "
                    f"{self._cfg.min_relationship_confidence}) — excluded."
                )
                continue

            src_ok = rel.source_anchor_id in nodes_by_id
            tgt_ok = rel.target_anchor_id in nodes_by_id
            status = EdgeStatus.VALID
            if not src_ok:
                status = EdgeStatus.BROKEN_SOURCE
                diagnostics.append(
                    f"Edge {rel.relationship_id!r}: source node "
                    f"{rel.source_anchor_id!r} not found."
                )
            if not tgt_ok:
                status = EdgeStatus.BROKEN_TARGET
                diagnostics.append(
                    f"Edge {rel.relationship_id!r}: target node "
                    f"{rel.target_anchor_id!r} not found."
                )

            edges.append(SemanticEdge(
                edge_id=rel.relationship_id,
                source_node_id=rel.source_anchor_id,
                target_node_id=rel.target_anchor_id,
                relationship_type=rel.relationship_type.value,
                direction=rel.direction.value,
                confidence=rel.confidence.value,
                discovery_rule=rel.discovery_rule,
                status=status,
            ))

        # --- Determine node connectivity (for orphan detection) ---
        connected_ids: Set[str] = set()
        for e in edges:
            if e.status == EdgeStatus.VALID:
                connected_ids.add(e.source_node_id)
                connected_ids.add(e.target_node_id)

        final_nodes: List[SemanticNode] = []
        for node_id, node in nodes_by_id.items():
            if node_id not in connected_ids:
                # Mark as orphan (but still include in graph)
                import dataclasses
                node = dataclasses.replace(node, status=NodeStatus.ORPHAN)
            final_nodes.append(node)

        # Deterministic ordering
        final_nodes.sort(key=lambda n: n.node_id)
        edges.sort(key=lambda e: e.edge_id)

        # --- Statistics ---
        stats = self._compute_statistics(
            nodes=final_nodes,
            edges=edges,
            orphan_ids=set(n.node_id for n in final_nodes if n.status == NodeStatus.ORPHAN),
        )

        # --- Metadata ---
        graph_id = _deterministic_graph_id([n.node_id for n in final_nodes])
        metadata = GraphMetadata(
            graph_id=graph_id,
            engine_version=self._cfg.version,
            source_count=len(enrichment_results),
            description=description,
            version=DEFAULT_GRAPH_VERSION,
        )

        # --- Outcome ---
        outcome = self._determine_outcome(final_nodes, edges, diagnostics)

        return SemanticGraph(
            nodes=tuple(final_nodes),
            edges=tuple(edges),
            metadata=metadata,
            statistics=stats,
            outcome=outcome,
            diagnostics=tuple(diagnostics),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _result_to_node(self, result: object) -> Optional[SemanticNode]:
        """Convert a SemanticEnrichmentResult to a SemanticNode."""
        anchor = getattr(result, "anchor", None)
        if anchor is None:
            return None
        anchor_conf = getattr(getattr(anchor, "confidence", None), "value", 0.0)
        if anchor_conf < self._cfg.min_node_confidence:
            return None

        sem_obj = getattr(result, "semantic_object", None)
        object_type_key = ""
        if sem_obj is not None:
            object_type_key = getattr(sem_obj, "object_type_key", "") or ""

        semantic_role = getattr(anchor, "semantic_role", None)
        semantic_role_str = (
            str(semantic_role.value) if hasattr(semantic_role, "value") else str(semantic_role or "unknown")
        )

        return SemanticNode(
            node_id=anchor.anchor_id,
            object_key=getattr(result, "object_key", ""),
            object_type_key=object_type_key,
            semantic_role=semantic_role_str,
            confidence=anchor_conf,
            pattern_key=getattr(anchor, "pattern_key", None),
            status=NodeStatus.VALID,
        )

    @staticmethod
    def _compute_statistics(
        nodes: List[SemanticNode],
        edges: List[SemanticEdge],
        orphan_ids: Set[str],
    ) -> GraphStatistics:
        type_counts: Dict[str, int] = defaultdict(int)
        confidences = [e.confidence for e in edges if e.status == EdgeStatus.VALID]

        for e in edges:
            type_counts[e.relationship_type] += 1

        avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        min_conf = round(min(confidences), 4) if confidences else 0.0
        max_conf = round(max(confidences), 4) if confidences else 0.0

        return GraphStatistics(
            node_count=len(nodes),
            edge_count=len(edges),
            orphan_count=len(orphan_ids),
            relationship_type_counts=dict(type_counts),
            average_confidence=avg_conf,
            min_confidence=min_conf,
            max_confidence=max_conf,
        )

    @staticmethod
    def _determine_outcome(
        nodes: List[SemanticNode],
        edges: List[SemanticEdge],
        diagnostics: List[str],
    ) -> GraphBuildOutcome:
        if not nodes and not edges:
            return GraphBuildOutcome.EMPTY
        broken = any(
            e.status in (EdgeStatus.BROKEN_SOURCE, EdgeStatus.BROKEN_TARGET)
            for e in edges
        )
        if broken:
            return GraphBuildOutcome.PARTIAL
        return GraphBuildOutcome.COMPLETE


#: Module-level singleton.
default_graph_builder = SemanticGraphBuilder()
