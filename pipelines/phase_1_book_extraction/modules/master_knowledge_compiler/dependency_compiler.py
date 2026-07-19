"""
modules/master_knowledge_compiler/dependency_compiler.py — M5.3
Deliverable #3: Dependency Compiler.

Extracts prerequisite/dependency relationships from SemanticGraph edges
(M5.2E) and produces a deterministic DependencyMap with topological ordering.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

from modules.master_knowledge_compiler.config import MasterKnowledgeCompilerConfig, default_config
from modules.master_knowledge_compiler.enums import CompilationOutcome, DependencyType
from modules.master_knowledge_compiler.models import (
    DependencyEdge,
    DependencyMap,
    DependencyStatistics,
)

__all__ = [
    "DependencyCompiler",
    "default_dependency_compiler",
    "DEPENDENCY_RELATIONSHIP_TYPES",
]

# Relationship types that represent educational dependencies
DEPENDENCY_RELATIONSHIP_TYPES = frozenset({
    "requires",
    "prerequisite",
    "builds_on",
    "implements",
    "sequences",
})

_REL_TYPE_TO_DEP: Dict[str, DependencyType] = {
    "requires": DependencyType.REQUIRES,
    "prerequisite": DependencyType.PREREQUISITE,
    "builds_on": DependencyType.BUILDS_ON,
    "implements": DependencyType.ENABLES,
    "sequences": DependencyType.ENABLES,
}


def _topological_sort(
    node_ids: List[str],
    edges: List[Tuple[str, str]],
) -> Tuple[List[str], bool]:
    """
    Kahn's algorithm topological sort.
    Returns (ordered_list, has_cycles).
    Tie-breaking: alphabetical by node_id for determinism.
    """
    in_degree: Dict[str, int] = {n: 0 for n in node_ids}
    adjacency: Dict[str, List[str]] = {n: [] for n in node_ids}

    for src, tgt in edges:
        if src in adjacency and tgt in adjacency:
            adjacency[src].append(tgt)
            in_degree[tgt] += 1

    queue: deque = deque(sorted(n for n in node_ids if in_degree[n] == 0))
    result: List[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbour in sorted(adjacency.get(node, [])):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    has_cycles = len(result) < len(node_ids)
    # Append remaining (cycle participants) in sorted order for determinism
    if has_cycles:
        remaining = sorted(n for n in node_ids if n not in result)
        result.extend(remaining)

    return result, has_cycles


class DependencyCompiler:
    """
    Compiles dependency relationships from a SemanticGraph into a
    DependencyMap with topological ordering.
    """

    def __init__(self, config: Optional[MasterKnowledgeCompilerConfig] = None) -> None:
        self._cfg = config or default_config

    def compile(self, graph: object) -> DependencyMap:
        nodes = getattr(graph, "nodes", ())
        edges = getattr(graph, "edges", ())

        node_ids = [getattr(n, "node_id", "") for n in nodes if getattr(n, "node_id", "")]
        dep_edges: List[DependencyEdge] = []
        topo_pairs: List[Tuple[str, str]] = []

        for edge in edges:
            rel_type = str(getattr(edge, "relationship_type", "") or "").lower()
            if rel_type not in DEPENDENCY_RELATIONSHIP_TYPES:
                continue

            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            if not src or not tgt:
                continue

            dep_type = _REL_TYPE_TO_DEP.get(rel_type, DependencyType.REQUIRES)
            dep_edges.append(DependencyEdge(
                source_node_id=src,
                target_node_id=tgt,
                dependency_type=dep_type,
                confidence=float(getattr(edge, "confidence", 0.0)),
                relationship_id=getattr(edge, "edge_id", ""),
            ))
            topo_pairs.append((src, tgt))

        # Topological sort
        topo_order, has_cycles = _topological_sort(node_ids, topo_pairs)

        # Prerequisite map: concept → its prerequisites (what it requires)
        prereq_map: Dict[str, List[str]] = defaultdict(list)
        for de in dep_edges:
            prereq_map[de.source_node_id].append(de.target_node_id)

        # Compute max depth via BFS
        max_depth = self._compute_max_depth(node_ids, topo_pairs)

        by_type: Dict[str, int] = defaultdict(int)
        for de in dep_edges:
            by_type[de.dependency_type.value] += 1

        stats = DependencyStatistics(
            total_edges=len(dep_edges),
            total_concepts=len(node_ids),
            max_depth=max_depth,
            by_dependency_type=dict(by_type),
            has_cycles=has_cycles,
        )

        outcome = CompilationOutcome.COMPLETE if dep_edges else CompilationOutcome.EMPTY

        return DependencyMap(
            edges=tuple(sorted(dep_edges, key=lambda e: (e.source_node_id, e.target_node_id))),
            prerequisite_map={k: tuple(sorted(v)) for k, v in prereq_map.items()},
            topological_order=tuple(topo_order),
            statistics=stats,
            outcome=outcome,
        )

    @staticmethod
    def _compute_max_depth(node_ids: List[str], edges: List[Tuple[str, str]]) -> int:
        """Compute the longest path depth in the DAG."""
        depth: Dict[str, int] = {n: 0 for n in node_ids}
        adjacency: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {n: 0 for n in node_ids}

        for src, tgt in edges:
            if src in depth and tgt in depth:
                adjacency[src].append(tgt)
                in_degree[tgt] += 1

        queue = deque(sorted(n for n in node_ids if in_degree[n] == 0))
        while queue:
            node = queue.popleft()
            for nbr in sorted(adjacency.get(node, [])):
                depth[nbr] = max(depth[nbr], depth[node] + 1)
                in_degree[nbr] -= 1
                if in_degree[nbr] == 0:
                    queue.append(nbr)

        return max(depth.values(), default=0)


#: Module-level singleton.
default_dependency_compiler = DependencyCompiler()
