"""
teacher_knowledge_base/builders/curriculum_builder.py — M6.1: Curriculum
Graph builder.

SPECIFICATION: CURRICULUM_GRAPH_SPECIFICATION.md

SCOPE: The CurriculumGraph is a high-level graph over TeachingUnits.
Nodes = TeachingUnits. Edges = prerequisite relationships between units
(derived from unit.prerequisite_unit_ids). The curriculum graph provides
the overall course structure for teacher planning.

GRAPH STRUCTURE:
  - nodes: one per TeachingUnit (with teaching metadata summary)
  - edges: prerequisite edges between TeachingUnits
  - chapters: grouping of TeachingUnits by chapter
  - global_teaching_sequence: linear topological order of all units
  - metadata: graph statistics

DETERMINISM: all IDs derived from content (TeachingUnit IDs already
deterministic). Edge IDs are UUID5 of (source_unit_id, target_unit_id).
Ordering: topological with alphabetic tie-breaking.
"""
from __future__ import annotations

import json
import uuid
import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.curriculum")

CG_VERSION = "M6.1.0"
_CG_NAMESPACE = uuid.UUID("aabbccdd-eeff-0011-2233-445566778899")

STAGE = "curriculum_graph"


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_curriculum_graph(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_curriculum_graph(context: "TKBContext") -> None:
    teaching_units = context.require_output("teaching_units", STAGE)
    artifact_id = context.metadata.artifact_id

    cg_nodes = _build_cg_nodes(teaching_units)
    cg_edges = _build_cg_edges(teaching_units, artifact_id)
    chapters = _build_chapter_groups(teaching_units)
    global_sequence = _compute_global_teaching_sequence(cg_nodes, cg_edges)

    curriculum_graph = {
        "version": CG_VERSION,
        "nodes": cg_nodes,
        "edges": cg_edges,
        "chapters": chapters,
        "global_teaching_sequence": global_sequence,
        "metadata": {
            "total_units": len(cg_nodes),
            "total_edges": len(cg_edges),
            "total_chapters": len(chapters),
            "version": CG_VERSION,
            "graph_type": "directed_acyclic_teaching_graph",
        },
    }
    context.set_output(STAGE, curriculum_graph)
    logger.info(
        "Curriculum Graph builder: %d unit-nodes, %d edges, %d chapters.",
        len(cg_nodes), len(cg_edges), len(chapters),
    )


def _build_cg_nodes(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One curriculum graph node per TeachingUnit."""
    nodes = []
    for unit in units:
        nodes.append({
            "unit_id": unit["unit_id"],
            "title": unit.get("title", ""),
            "chapter_reference": unit.get("chapter_reference", ""),
            "teaching_sequence_index": unit.get("teaching_sequence_index", 0),
            "concept_count": len(unit.get("concepts", [])),
            "difficulty_level": unit.get("difficulty_level", "medium"),
            "estimated_duration_minutes": unit.get("estimated_duration_minutes", 30),
            "bloom_levels": unit.get("bloom_levels", []),
        })
    nodes.sort(key=lambda n: (n.get("teaching_sequence_index", 999), n.get("unit_id", "")))
    return nodes


def _build_cg_edges(units: List[Dict[str, Any]], artifact_id: str) -> List[Dict[str, Any]]:
    """Curriculum graph edges = prerequisite_unit_ids relationships."""
    edges = []
    seen: Set[str] = set()
    for unit in units:
        tgt = unit["unit_id"]
        for src in (unit.get("prerequisite_unit_ids") or []):
            edge_key = f"{src}:{tgt}"
            if edge_key not in seen:
                seen.add(edge_key)
                edge_id = str(uuid.uuid5(_CG_NAMESPACE, f"{artifact_id}:cg:edge:{edge_key}"))
                edges.append({
                    "edge_id": edge_id,
                    "source_unit_id": src,
                    "target_unit_id": tgt,
                    "relationship": "prerequisite",
                })
    edges.sort(key=lambda e: (e.get("source_unit_id", ""), e.get("target_unit_id", "")))
    return edges


def _build_chapter_groups(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Groups TeachingUnits by chapter for curriculum-level navigation."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for unit in units:
        chapter = str(unit.get("chapter_reference") or "ungrouped")
        groups[chapter].append(unit["unit_id"])
    result = []
    for chapter_key in sorted(groups.keys()):
        unit_ids = groups[chapter_key]
        result.append({
            "chapter_key": chapter_key,
            "unit_ids": unit_ids,
            "unit_count": len(unit_ids),
        })
    return result


def _compute_global_teaching_sequence(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[str]:
    """Topological sort of all TeachingUnits by prerequisite edges.
    Returns stable list of unit_ids in teaching order."""
    in_degree: Dict[str, int] = defaultdict(int)
    adj: Dict[str, List[str]] = defaultdict(list)
    all_ids: Set[str] = {n["unit_id"] for n in nodes}

    for e in edges:
        src = e.get("source_unit_id", "")
        tgt = e.get("target_unit_id", "")
        if src in all_ids and tgt in all_ids:
            adj[src].append(tgt)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

    for uid in all_ids:
        in_degree.setdefault(uid, 0)

    queue = deque(sorted(uid for uid in all_ids if in_degree[uid] == 0))
    order: List[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for neighbor in sorted(adj[current]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Append any remaining (in case of cycles — already documented by EDG builder)
    remaining = sorted(uid for uid in all_ids if uid not in set(order))
    order.extend(remaining)
    return order
