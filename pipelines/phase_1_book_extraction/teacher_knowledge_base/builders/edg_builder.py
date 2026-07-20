"""
teacher_knowledge_base/builders/edg_builder.py — M6.1: Enriched Dependency
Graph (EDG) builder.

SPECIFICATION: ENRICHED_DEPENDENCY_GRAPH_SPECIFICATION.md

SCOPE: The EDG enriches the Phase E2 DependencyGraph (or derives it from the
KnowledgeGraph when E2 is absent) with teaching-specific dependency metadata:
  - dependency_type classification for teaching (hard/soft/optional)
  - teaching_impact_score per dependency edge
  - concept_readiness_ordering (topological, deterministic)
  - cycle detection results (documented, never silently resolved)

SOURCE: Phase E2 DependencyGraph (preferred) or Phase C KnowledgeGraph
(fallback, derives dependencies from prerequisite edges).

DETERMINISM: node and edge IDs are UUID5 derived from content + artifact_id.
Ordering is topological (Kahn's) with alphabetic tie-breaking.
"""
from __future__ import annotations

import json
import uuid
import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

from ..exceptions import TKBBuilderError
from ..loaders import require_knowledge_graph

logger = logging.getLogger("teacher_knowledge_base.builders.edg")

EDG_VERSION = "M6.1.0"
_EDG_NAMESPACE = uuid.UUID("ABCDEF12-3456-7890-ABCD-EF1234567890".lower())

STAGE = "edg"


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_edg(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_edg(context: "TKBContext") -> None:
    artifacts = context.compiler_artifacts
    artifact_id = context.metadata.artifact_id

    # Prefer Phase E2 DependencyGraph; fall back to deriving from KG
    dep_graph = (
        artifacts.get("dependency_graph")
        or artifacts.get("dependency_graph_reference")
    )

    if dep_graph and isinstance(dep_graph, dict):
        nodes, edges = _load_from_dependency_graph(dep_graph)
        source = "DependencyGraph"
    else:
        context.diagnostics.add_warning(
            STAGE,
            "Phase E2 DependencyGraph not found — deriving EDG from KnowledgeGraph prerequisites.",
        )
        try:
            kg = require_knowledge_graph(artifacts)
        except Exception as exc:
            raise TKBBuilderError(STAGE, f"Neither DependencyGraph nor KnowledgeGraph available: {exc}") from exc
        nodes, edges = _derive_from_kg(kg)
        source = "KnowledgeGraph (derived)"

    enriched_nodes = _enrich_nodes(nodes, artifact_id)
    enriched_edges = _enrich_edges(edges, artifact_id)
    cycles = _detect_cycles(enriched_nodes, enriched_edges)
    readiness_order = _compute_readiness_order(enriched_nodes, enriched_edges)

    if cycles:
        context.diagnostics.add_warning(
            STAGE,
            f"Detected {len(cycles)} dependency cycle(s) in the graph.",
            f"Cycles: {cycles[:3]}{'...' if len(cycles) > 3 else ''}",
        )

    edg = {
        "version": EDG_VERSION,
        "enrichment_applied": True,
        "source": source,
        "nodes": enriched_nodes,
        "edges": enriched_edges,
        "concept_readiness_ordering": readiness_order,
        "cycles_detected": cycles,
        "enrichment_metadata": {
            "total_enriched_nodes": len(enriched_nodes),
            "total_enriched_edges": len(enriched_edges),
            "cycle_count": len(cycles),
            "has_cycles": len(cycles) > 0,
            "dependency_type_distribution": _dep_type_distribution(enriched_edges),
            "version": EDG_VERSION,
        },
    }
    context.set_output(STAGE, edg)
    logger.info(
        "EDG builder: %d nodes, %d edges, %d cycles detected.",
        len(enriched_nodes), len(enriched_edges), len(cycles),
    )


def _load_from_dependency_graph(dep_graph: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    nodes = dep_graph.get("nodes") or dep_graph.get("concepts") or []
    edges = dep_graph.get("edges") or dep_graph.get("dependencies") or []
    return list(nodes), list(edges)


def _derive_from_kg(kg: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Derives dependency nodes and edges from KG prerequisite relationships."""
    nodes = kg.get("nodes") or kg.get("concept_nodes") or []
    edges_derived: List[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or node.get("concept_id") or "")
        for prereq in (node.get("prerequisites") or []):
            edges_derived.append({
                "source": str(prereq),
                "target": nid,
                "type": "prerequisite",
            })
    return list(nodes), edges_derived


def _enrich_nodes(nodes: List[Dict[str, Any]], artifact_id: str) -> List[Dict[str, Any]]:
    enriched = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or node.get("concept_id") or node.get("name", ""))
        enriched_id = str(uuid.uuid5(_EDG_NAMESPACE, f"{artifact_id}:edg:node:{nid}"))
        enriched.append({
            **node,
            "enriched_id": enriched_id,
            "enrichment_version": EDG_VERSION,
        })
    enriched.sort(key=lambda n: str(n.get("id") or n.get("concept_id") or n.get("enriched_id", "")))
    return enriched


def _enrich_edges(edges: List[Dict[str, Any]], artifact_id: str) -> List[Dict[str, Any]]:
    enriched = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("source") or edge.get("from") or "")
        tgt = str(edge.get("target") or edge.get("to") or "")
        edge_type = str(edge.get("type") or edge.get("relationship_type") or "dependency")
        edge_key = f"{artifact_id}:edg:edge:{src}:{tgt}:{edge_type}"
        enriched_id = str(uuid.uuid5(_EDG_NAMESPACE, edge_key))
        dep_type = _classify_dependency_type(edge_type)
        enriched.append({
            **edge,
            "enriched_id": enriched_id,
            "enrichment_version": EDG_VERSION,
            "dependency_type": dep_type,
            "teaching_impact_score": _teaching_impact(dep_type),
        })
    enriched.sort(key=lambda e: (
        str(e.get("source") or e.get("from") or ""),
        str(e.get("target") or e.get("to") or ""),
    ))
    return enriched


def _classify_dependency_type(edge_type: str) -> str:
    et = edge_type.lower()
    if et in ("prerequisite", "requires", "depends_on", "hard_dependency"):
        return "hard"
    if et in ("recommended", "suggested", "soft_dependency", "related"):
        return "soft"
    return "optional"


def _teaching_impact(dep_type: str) -> float:
    return {"hard": 1.0, "soft": 0.6, "optional": 0.3}.get(dep_type, 0.5)


def _detect_cycles(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[List[str]]:
    """Detects cycles using DFS. Returns list of cycles (each a list of node IDs).
    Documented, never resolved — per M6.1 error handling spec."""
    adj: Dict[str, List[str]] = defaultdict(list)
    node_ids: Set[str] = set()
    for n in nodes:
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        if nid:
            node_ids.add(nid)
    for e in edges:
        if str(e.get("dependency_type", "")).lower() == "hard":
            src = str(e.get("source") or e.get("from") or "")
            tgt = str(e.get("target") or e.get("to") or "")
            if src and tgt:
                adj[src].append(tgt)

    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    cycles: List[List[str]] = []

    def dfs(node: str, path: List[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        for neighbor in sorted(adj.get(node, [])):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Found cycle — record from neighbor to current end of path
                idx = path.index(neighbor) if neighbor in path else 0
                cycle = path[idx:] + [neighbor]
                if cycle not in cycles:
                    cycles.append(cycle)
        path.pop()
        rec_stack.discard(node)

    for nid in sorted(node_ids):
        if nid not in visited:
            dfs(nid, [])

    return cycles


def _compute_readiness_order(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[str]:
    """Topological order of concept IDs for teaching readiness.
    Only hard dependencies are used. Alphabetic tie-breaking for determinism.
    Returns partial order when cycles are present (cycles are excluded from
    topological sort — already documented by _detect_cycles)."""
    in_degree: Dict[str, int] = defaultdict(int)
    adj: Dict[str, List[str]] = defaultdict(list)
    node_ids: Set[str] = set()

    for n in nodes:
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        if nid:
            node_ids.add(nid)
            in_degree.setdefault(nid, 0)

    for e in edges:
        if str(e.get("dependency_type", "")).lower() == "hard":
            src = str(e.get("source") or e.get("from") or "")
            tgt = str(e.get("target") or e.get("to") or "")
            if src in node_ids and tgt in node_ids:
                adj[src].append(tgt)
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

    queue = deque(sorted(nid for nid in node_ids if in_degree.get(nid, 0) == 0))
    order: List[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for neighbor in sorted(adj[current]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return order


def _dep_type_distribution(edges: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = {"hard": 0, "soft": 0, "optional": 0}
    for e in edges:
        dt = str(e.get("dependency_type", "optional"))
        dist[dt] = dist.get(dt, 0) + 1
    return dist
