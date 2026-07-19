"""
modules/knowledge_optimization/learning_analytics_builder.py — M5.4
Deliverable #7: Learning Analytics.

Computes deterministic, immutable analytics metrics from the
MasterKnowledgePackage.  No LLM, no randomness.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.knowledge_optimization.config import KnowledgeOptimizationConfig, default_config
from modules.knowledge_optimization.enums import OptimizationOutcome
from modules.knowledge_optimization.models import ConceptAnalytics, LearningAnalytics

__all__ = ["LearningAnalyticsBuilder", "default_learning_analytics_builder"]


class LearningAnalyticsBuilder:
    """
    Computes learning analytics from a MasterKnowledgePackage.
    All metrics are deterministic.
    """

    def __init__(self, config: Optional[KnowledgeOptimizationConfig] = None) -> None:
        self._cfg = config or default_config

    def build(self, package: object) -> LearningAnalytics:
        ci  = getattr(package, "concept_index", None)
        dep = getattr(package, "dependency_map", None)
        lp  = getattr(package, "learning_progression", None)

        entries = getattr(ci, "entries", ()) if ci else ()
        dep_edges = getattr(dep, "edges", ()) if dep else ()
        prereq_map: Dict[str, Tuple[str, ...]] = {}
        if dep:
            prereq_map = {k: tuple(v) for k, v in (getattr(dep, "prerequisite_map", {}) or {}).items()}

        if not entries:
            return LearningAnalytics(
                per_concept=(), graph_density=0.0,
                average_prerequisite_depth=0.0, max_prerequisite_depth=0,
                average_connectivity=0.0, average_learning_path_length=0.0,
                orphan_ratio=0.0, hub_concepts=(), cluster_count=0,
                total_concepts_analyzed=0, outcome=OptimizationOutcome.EMPTY,
            )

        n = len(entries)
        node_ids = [getattr(e, "node_id", "") for e in entries]
        conf_map = {getattr(e, "node_id", ""): float(getattr(e, "confidence", 0.5)) for e in entries}

        # Connectivity (in + out degree)
        degree: Dict[str, int] = defaultdict(int)
        for edge in dep_edges:
            degree[getattr(edge, "source_node_id", "")] += 1
            degree[getattr(edge, "target_node_id", "")] += 1

        # Prerequisite depth (position in topological order)
        topo = getattr(dep, "topological_order", node_ids) if dep else node_ids
        depth_map: Dict[str, int] = {nid: i for i, nid in enumerate(topo)}

        # Mean + stddev for hub detection
        conns = [degree.get(nid, 0) for nid in node_ids]
        mean_conn = sum(conns) / n if n else 0.0
        stddev_conn = math.sqrt(sum((c - mean_conn) ** 2 for c in conns) / n) if n else 0.0
        hub_threshold = mean_conn + stddev_conn

        # Per-concept analytics
        per_concept: List[ConceptAnalytics] = []
        for nid in sorted(node_ids):
            dep_count = len(prereq_map.get(nid, ()))
            pdepth = depth_map.get(nid, 0)
            conn = degree.get(nid, 0)
            conf = conf_map.get(nid, 0.5)
            # Importance: blend of confidence + normalized connectivity
            importance = round(conf * 0.60 + min(conn / max(max(conns), 1), 1.0) * 0.40, 4)
            # Centrality proxy: normalize depth position in topo order
            centrality = round(pdepth / max(n - 1, 1), 4) if n > 1 else 0.0
            per_concept.append(ConceptAnalytics(
                node_id=nid,
                prerequisite_depth=pdepth,
                dependency_complexity=dep_count,
                centrality=centrality,
                connectivity=conn,
                importance=importance,
                is_hub=conn > hub_threshold,
            ))

        # Graph density: edges / (n*(n-1)) for directed graph
        max_edges = n * (n - 1)
        graph_density = round(len(dep_edges) / max_edges, 4) if max_edges > 0 else 0.0

        # Orphan ratio
        connected = {getattr(e, "source_node_id", "") for e in dep_edges} | \
                    {getattr(e, "target_node_id", "") for e in dep_edges}
        orphans = [nid for nid in node_ids if nid not in connected]
        orphan_ratio = round(len(orphans) / n, 4) if n else 0.0

        # Average learning path length
        lp_len = getattr(lp, "total_steps", 0) if lp else 0
        avg_path_len = round(lp_len / n, 4) if n else 0.0

        # Cluster count (connected components proxy)
        cluster_count = self._count_clusters(node_ids, dep_edges)

        hub_concepts = tuple(sorted(c.node_id for c in per_concept if c.is_hub))

        avg_depth = round(sum(c.prerequisite_depth for c in per_concept) / n, 4) if n else 0.0
        max_depth = max((c.prerequisite_depth for c in per_concept), default=0)
        avg_conn  = round(mean_conn, 4)

        return LearningAnalytics(
            per_concept=tuple(per_concept),
            graph_density=graph_density,
            average_prerequisite_depth=avg_depth,
            max_prerequisite_depth=max_depth,
            average_connectivity=avg_conn,
            average_learning_path_length=avg_path_len,
            orphan_ratio=orphan_ratio,
            hub_concepts=hub_concepts,
            cluster_count=cluster_count,
            total_concepts_analyzed=n,
            outcome=OptimizationOutcome.COMPLETE,
        )

    @staticmethod
    def _count_clusters(
        node_ids: List[str],
        edges: object,
    ) -> int:
        """Count weakly-connected components via union-find."""
        parent = {nid: nid for nid in node_ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for edge in (edges or ()):
            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            if src in parent and tgt in parent:
                union(src, tgt)

        return len(set(find(nid) for nid in node_ids))


default_learning_analytics_builder = LearningAnalyticsBuilder()
