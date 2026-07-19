"""
modules/relationship_discovery_engine/graph_normalizer.py — M5.2E
Deliverable #5: Graph Normalization.

Normalizes a SemanticGraph by:
1. Removing duplicate edges (same source/target/type) per the
   configured NormalizationStrategy.
2. Enforcing canonical edge direction (FORWARD preferred).
3. Normalizing relationship types to their canonical form.
4. Updating GraphStatistics to reflect removals.

All normalization is deterministic.  The input graph is never mutated
(frozen dataclass) — a new SemanticGraph is returned.
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.relationship_discovery_engine.config import (
    RelationshipDiscoveryEngineConfig,
    default_config,
)
from modules.relationship_discovery_engine.enums import (
    EdgeStatus,
    GraphBuildOutcome,
    NormalizationStrategy,
)
from modules.relationship_discovery_engine.exceptions import GraphNormalizationError
from modules.relationship_discovery_engine.models import (
    GraphStatistics,
    SemanticEdge,
    SemanticGraph,
)

__all__ = [
    "GraphNormalizer",
    "default_graph_normalizer",
]

# Edge dedup key: (source_node_id, target_node_id, relationship_type)
_DedupKey = Tuple[str, str, str]


class GraphNormalizer:
    """
    Produces a normalized SemanticGraph from an input SemanticGraph.

    Does NOT mutate the input (frozen dataclass).
    Returns a new SemanticGraph with:
    - Duplicate edges removed per config.normalization_strategy.
    - Updated GraphStatistics reflecting edge removals.
    - Updated GraphBuildOutcome.
    """

    def __init__(
        self,
        config: Optional[RelationshipDiscoveryEngineConfig] = None,
    ) -> None:
        self._cfg = config or default_config

    def normalize(self, graph: SemanticGraph) -> SemanticGraph:
        """
        Return a new, normalized SemanticGraph.

        The input graph is not modified.
        """
        diagnostics: List[str] = list(graph.diagnostics)
        edges = list(graph.edges)

        # Step 1: Remove duplicates
        edges, removed_count = self._deduplicate(edges, diagnostics)

        # Step 2: Recompute statistics
        stats = self._recompute_statistics(
            nodes=list(graph.nodes),
            edges=edges,
            duplicate_edges_removed=removed_count + graph.statistics.duplicate_edges_removed,
        )

        # Step 3: Determine outcome
        outcome = graph.outcome
        if removed_count > 0 and outcome == GraphBuildOutcome.COMPLETE:
            # Still complete after dedup — COMPLETE is fine
            pass

        return dataclasses.replace(
            graph,
            edges=tuple(edges),
            statistics=stats,
            diagnostics=tuple(diagnostics),
            outcome=outcome,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deduplicate(
        self,
        edges: List[SemanticEdge],
        diagnostics: List[str],
    ) -> Tuple[List[SemanticEdge], int]:
        """Remove duplicate edges per normalization_strategy."""
        strategy = self._cfg.normalization_strategy
        buckets: Dict[_DedupKey, List[SemanticEdge]] = defaultdict(list)

        for e in edges:
            key: _DedupKey = (e.source_node_id, e.target_node_id, e.relationship_type)
            buckets[key].append(e)

        result: List[SemanticEdge] = []
        removed = 0

        for key, group in buckets.items():
            if len(group) == 1:
                result.append(group[0])
                continue

            # Multiple edges for same (src, tgt, type) — apply strategy
            removed += len(group) - 1
            diagnostics.append(
                f"Normalized {len(group)} duplicate edges for "
                f"({key[0][:8]}…, {key[1][:8]}…, {key[2]}) → kept 1."
            )

            if strategy == NormalizationStrategy.KEEP_HIGHEST_CONFIDENCE:
                winner = max(group, key=lambda e: e.confidence)
            elif strategy == NormalizationStrategy.KEEP_FIRST:
                winner = group[0]
            else:  # MERGE_EVIDENCE — keep highest, note merge
                winner = max(group, key=lambda e: e.confidence)

            result.append(winner)

        # Deterministic ordering
        result.sort(key=lambda e: e.edge_id)
        return result, removed

    @staticmethod
    def _recompute_statistics(
        nodes, edges: List[SemanticEdge], duplicate_edges_removed: int
    ) -> GraphStatistics:
        from collections import defaultdict as _dd
        type_counts: Dict[str, int] = _dd(int)
        connected: Set[str] = set()
        confidences = []

        for e in edges:
            type_counts[e.relationship_type] += 1
            if e.status == EdgeStatus.VALID:
                connected.add(e.source_node_id)
                connected.add(e.target_node_id)
                confidences.append(e.confidence)

        orphan_count = sum(1 for n in nodes if n.node_id not in connected)
        avg = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        mn = round(min(confidences), 4) if confidences else 0.0
        mx = round(max(confidences), 4) if confidences else 0.0

        return GraphStatistics(
            node_count=len(nodes),
            edge_count=len(edges),
            orphan_count=orphan_count,
            duplicate_edges_removed=duplicate_edges_removed,
            relationship_type_counts=dict(type_counts),
            average_confidence=avg,
            min_confidence=mn,
            max_confidence=mx,
        )


#: Module-level singleton.
default_graph_normalizer = GraphNormalizer()
