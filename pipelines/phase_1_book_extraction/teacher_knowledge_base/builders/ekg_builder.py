"""
teacher_knowledge_base/builders/ekg_builder.py — M6.1: Enriched Knowledge
Graph (EKG) builder.

SPECIFICATION: ENRICHED_KNOWLEDGE_GRAPH_SPECIFICATION.md

SCOPE: The EKG enriches the Phase C KnowledgeGraph with teaching annotations —
pedagogical difficulty tags, Bloom's taxonomy levels, misconception flags,
teaching prerequisite ordering, and concept relationship weights — without
modifying the source graph structure.

Source graph nodes and edges are preserved verbatim. Enrichment adds:
  - per-node: pedagogical metadata, bloom_level, misconceptions, teaching hints
  - per-edge: relationship_type, teaching_weight, directionality_for_teaching
  - graph-level: learning_paths, concept_clusters, difficulty_distribution

DETERMINISM: enriched node/edge IDs are UUID5 derived from the source ID
and the artifact_id — no random values.
"""
from __future__ import annotations

import json
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..exceptions import TKBBuilderError
from ..loaders import require_knowledge_graph, extract_concepts

logger = logging.getLogger("teacher_knowledge_base.builders.ekg")

EKG_VERSION = "M6.1.0"
_EKG_NAMESPACE = uuid.UUID("87654321-4321-8765-4321-876543218765")

STAGE = "ekg"

# Bloom's taxonomy level heuristics (keyword-based, lightweight)
_BLOOM_KEYWORDS: Dict[str, List[str]] = {
    "remember": ["define", "list", "recall", "name", "state", "identify"],
    "understand": ["explain", "describe", "summarize", "interpret", "classify"],
    "apply": ["solve", "use", "calculate", "demonstrate", "apply", "compute"],
    "analyze": ["compare", "differentiate", "examine", "break down", "analyze"],
    "evaluate": ["justify", "critique", "assess", "evaluate", "judge"],
    "create": ["design", "construct", "formulate", "develop", "create"],
}


def build(context: "TKBContext") -> None:  # noqa: F821
    """Main entry point. Reads from context.compiler_artifacts, writes
    output to context via context.set_output('ekg', ...)."""
    import time
    t0 = time.monotonic()
    try:
        _build_ekg(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_ekg(context: "TKBContext") -> None:
    artifacts = context.compiler_artifacts

    try:
        kg = require_knowledge_graph(artifacts)
    except Exception as exc:
        context.diagnostics.add_warning(
            STAGE,
            "KnowledgeGraph not found — building minimal EKG from concept list.",
            str(exc),
        )
        concepts = extract_concepts(artifacts)
        kg = _synthetic_kg_from_concepts(concepts)

    artifact_id = context.metadata.artifact_id
    enriched_nodes = _enrich_nodes(kg, artifact_id)
    enriched_edges = _enrich_edges(kg, artifact_id)
    learning_paths = _compute_learning_paths(enriched_nodes, enriched_edges)
    concept_clusters = _compute_concept_clusters(enriched_nodes, enriched_edges)

    ekg = {
        "version": EKG_VERSION,
        "enrichment_applied": True,
        "source": "KnowledgeGraph",
        "nodes": enriched_nodes,
        "edges": enriched_edges,
        "learning_paths": learning_paths,
        "concept_clusters": concept_clusters,
        "difficulty_distribution": _compute_difficulty_distribution(enriched_nodes),
        "enrichment_metadata": {
            "total_enriched_nodes": len(enriched_nodes),
            "total_enriched_edges": len(enriched_edges),
            "total_learning_paths": len(learning_paths),
            "total_clusters": len(concept_clusters),
            "bloom_distribution": _compute_bloom_distribution(enriched_nodes),
            "version": EKG_VERSION,
        },
    }
    context.set_output(STAGE, ekg)
    logger.info(
        "EKG builder: %d enriched nodes, %d enriched edges, %d learning paths.",
        len(enriched_nodes), len(enriched_edges), len(learning_paths),
    )


def _enrich_nodes(kg: Dict[str, Any], artifact_id: str) -> List[Dict[str, Any]]:
    source_nodes = kg.get("nodes") or kg.get("concept_nodes") or []
    enriched: List[Dict[str, Any]] = []
    for node in source_nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("concept_id") or node.get("name", ""))
        enriched_id = str(uuid.uuid5(_EKG_NAMESPACE, f"{artifact_id}:node:{node_id}"))
        bloom = _infer_bloom_level(node)
        difficulty = _infer_difficulty(node)
        enriched.append({
            **node,
            "enriched_id": enriched_id,
            "enrichment_version": EKG_VERSION,
            "pedagogical_metadata": {
                "bloom_taxonomy_level": bloom,
                "difficulty_level": difficulty,
                "misconception_flags": _extract_misconceptions(node),
                "teaching_hints": _extract_teaching_hints(node),
                "prerequisite_ordering_weight": _compute_prereq_weight(node),
                "estimated_mastery_time_minutes": _estimate_mastery_time(difficulty),
            },
        })
    # Stable sort by id
    enriched.sort(key=lambda n: str(n.get("id") or n.get("concept_id") or n.get("enriched_id", "")))
    return enriched


def _enrich_edges(kg: Dict[str, Any], artifact_id: str) -> List[Dict[str, Any]]:
    source_edges = kg.get("edges") or kg.get("relationships") or []
    enriched: List[Dict[str, Any]] = []
    for edge in source_edges:
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("source") or edge.get("from") or "")
        tgt = str(edge.get("target") or edge.get("to") or "")
        edge_type = str(edge.get("type") or edge.get("relationship_type") or "related")
        edge_key = f"{artifact_id}:edge:{src}:{tgt}:{edge_type}"
        enriched_id = str(uuid.uuid5(_EKG_NAMESPACE, edge_key))
        enriched.append({
            **edge,
            "enriched_id": enriched_id,
            "enrichment_version": EKG_VERSION,
            "relationship_type": edge_type,
            "teaching_weight": _compute_teaching_weight(edge_type),
            "directionality_for_teaching": _compute_directionality(edge_type),
        })
    # Stable sort by source, target
    enriched.sort(
        key=lambda e: (
            str(e.get("source") or e.get("from") or ""),
            str(e.get("target") or e.get("to") or ""),
        )
    )
    return enriched


def _infer_bloom_level(node: Dict[str, Any]) -> str:
    """Infers Bloom's taxonomy level from node fields. Falls back to 'understand'."""
    explicit = node.get("bloom_level") or node.get("bloom_taxonomy_level")
    if explicit:
        return str(explicit).lower()
    text = " ".join([
        str(node.get("description") or ""),
        str(node.get("title") or node.get("name") or ""),
        str(node.get("learning_objective") or ""),
    ]).lower()
    for level, keywords in _BLOOM_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return level
    return "understand"


def _infer_difficulty(node: Dict[str, Any]) -> str:
    """Returns 'easy', 'medium', or 'hard'."""
    explicit = node.get("difficulty") or node.get("difficulty_level")
    if explicit:
        d = str(explicit).lower()
        if d in ("easy", "low", "basic", "introductory"):
            return "easy"
        if d in ("hard", "high", "advanced", "complex"):
            return "hard"
        return "medium"
    # Heuristic from prerequisite count
    prereq_count = len(node.get("prerequisites") or [])
    if prereq_count == 0:
        return "easy"
    if prereq_count <= 2:
        return "medium"
    return "hard"


def _extract_misconceptions(node: Dict[str, Any]) -> List[str]:
    mc = node.get("misconceptions") or node.get("common_errors") or []
    if isinstance(mc, list):
        return [str(m) for m in mc]
    if isinstance(mc, str) and mc:
        return [mc]
    return []


def _extract_teaching_hints(node: Dict[str, Any]) -> List[str]:
    hints = node.get("teaching_hints") or node.get("pedagogical_notes") or []
    if isinstance(hints, list):
        return [str(h) for h in hints]
    if isinstance(hints, str) and hints:
        return [hints]
    return []


def _compute_prereq_weight(node: Dict[str, Any]) -> float:
    """Higher weight = teach earlier (more concepts depend on this one)."""
    prereq_count = len(node.get("prerequisites") or [])
    dependents_count = len(node.get("dependents") or node.get("enables") or [])
    return round(1.0 + (dependents_count * 0.5) - (prereq_count * 0.1), 3)


def _estimate_mastery_time(difficulty: str) -> int:
    return {"easy": 15, "medium": 30, "hard": 60}.get(difficulty, 30)


def _compute_teaching_weight(edge_type: str) -> float:
    weights = {
        "prerequisite": 1.0,
        "enables": 0.9,
        "related": 0.5,
        "similar": 0.4,
        "contrasts": 0.6,
        "applies": 0.8,
        "generalizes": 0.7,
        "specializes": 0.7,
    }
    return weights.get(edge_type.lower(), 0.5)


def _compute_directionality(edge_type: str) -> str:
    directed_types = {"prerequisite", "enables", "applies", "generalizes", "specializes"}
    return "directed" if edge_type.lower() in directed_types else "undirected"


def _compute_learning_paths(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Computes linear learning paths by topological ordering through
    prerequisite edges. Returns sorted, stable list."""
    # Build adjacency: prerequisite edges define the ordering
    from collections import defaultdict, deque
    in_degree: Dict[str, int] = defaultdict(int)
    adj: Dict[str, List[str]] = defaultdict(list)
    node_ids = {str(n.get("id") or n.get("concept_id") or n.get("enriched_id", "")) for n in nodes}

    for edge in edges:
        if str(edge.get("relationship_type", "")).lower() in ("prerequisite", "enables"):
            src = str(edge.get("source") or edge.get("from") or "")
            tgt = str(edge.get("target") or edge.get("to") or "")
            if src in node_ids and tgt in node_ids:
                adj[src].append(tgt)
                in_degree[tgt] += 1

    # Kahn's algorithm — deterministic (sort queue for stability)
    queue = deque(sorted(nid for nid in node_ids if in_degree.get(nid, 0) == 0))
    path_order: List[str] = []
    while queue:
        current = queue.popleft()
        path_order.append(current)
        for neighbor in sorted(adj[current]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if not path_order:
        return []

    return [
        {
            "path_id": str(uuid.uuid5(_EKG_NAMESPACE, f"path:{'->'.join(path_order)}")),
            "concept_sequence": path_order,
            "length": len(path_order),
            "path_type": "prerequisite_topological",
        }
    ]


def _compute_concept_clusters(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Groups concepts into clusters by shared chapter or topic tag."""
    from collections import defaultdict
    clusters: Dict[str, List[str]] = defaultdict(list)
    for node in nodes:
        chapter = str(node.get("chapter_id") or node.get("chapter") or "ungrouped")
        nid = str(node.get("id") or node.get("concept_id") or node.get("enriched_id", ""))
        if nid:
            clusters[chapter].append(nid)

    result: List[Dict[str, Any]] = []
    for chapter_key in sorted(clusters.keys()):
        concept_ids = sorted(clusters[chapter_key])
        cluster_id = str(uuid.uuid5(_EKG_NAMESPACE, f"cluster:{chapter_key}"))
        result.append({
            "cluster_id": cluster_id,
            "cluster_key": chapter_key,
            "concept_ids": concept_ids,
            "size": len(concept_ids),
        })
    return result


def _compute_difficulty_distribution(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    for n in nodes:
        d = n.get("pedagogical_metadata", {}).get("difficulty_level", "medium")
        dist[d] = dist.get(d, 0) + 1
    return dist


def _compute_bloom_distribution(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for n in nodes:
        b = n.get("pedagogical_metadata", {}).get("bloom_taxonomy_level", "understand")
        dist[b] = dist.get(b, 0) + 1
    return dist


def _synthetic_kg_from_concepts(concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds minimal KG from concept list when no real KG is available."""
    nodes = []
    for c in concepts:
        if isinstance(c, dict):
            nodes.append({
                "id": str(c.get("id") or c.get("concept_id") or c.get("name", "")),
                "name": str(c.get("name") or c.get("title") or ""),
                "chapter_id": str(c.get("chapter_id") or c.get("chapter") or ""),
                "prerequisites": c.get("prerequisites") or [],
            })
    return {"nodes": nodes, "edges": [], "source": "synthetic_from_concepts"}
