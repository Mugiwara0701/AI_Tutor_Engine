"""
teacher_knowledge_base/builders/teaching_unit_builder.py — M6.1: Teaching
Unit builder.

SPECIFICATION: TEACHING_UNIT_SPECIFICATION.md

SCOPE: TeachingUnits are the primary instructional atoms of the TKB.
Each TeachingUnit corresponds to a coherent, teachable cluster of concepts
drawn from the EKG. TeachingUnits are:
  - Deterministic: same concept clustering always produces same TeachingUnit IDs
  - Self-contained: each unit carries all information needed to teach it
  - Ordered: units have a canonical teaching sequence derived from the EDG
    readiness ordering

WHAT A TEACHING UNIT CONTAINS (per TEACHING_UNIT_SPECIFICATION.md):
  - unit_id (UUID5, deterministic)
  - title, description
  - concepts (list of concept IDs in this unit)
  - prerequisites (list of unit IDs that must be taught first)
  - learning_objectives (derived from concept Bloom levels)
  - teaching_sequence (ordered concept IDs within the unit)
  - estimated_duration_minutes
  - difficulty_level
  - bloom_levels (set of levels present in the unit)
  - chapter_reference
  - navigation_hint

INPUT: EKG output (from ekg stage), EDG readiness order (from edg stage).
"""
from __future__ import annotations

import json
import uuid
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.teaching_unit")

TU_VERSION = "M6.1.0"
_TU_NAMESPACE = uuid.UUID("fedcba98-7654-3210-fedc-ba9876543210")

STAGE = "teaching_units"

# Maximum concepts per teaching unit — keeps units teachable in one session
MAX_CONCEPTS_PER_UNIT = 8
MIN_CONCEPTS_PER_UNIT = 1


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_teaching_units(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_teaching_units(context: "TKBContext") -> None:
    # Require EKG (must have run before)
    ekg = context.require_output("ekg", STAGE)
    edg = context.get_output("edg") or {}  # optional — use readiness order if available

    ekg_nodes = ekg.get("nodes") or []
    readiness_order = edg.get("concept_readiness_ordering") or []
    artifact_id = context.metadata.artifact_id

    # Group concepts by chapter for clustering
    chapter_groups = _group_by_chapter(ekg_nodes)

    # Build TeachingUnits — one or more per chapter group
    units: List[Dict[str, Any]] = []
    unit_id_map: Dict[str, str] = {}  # concept_id -> unit_id (for prerequisite linking)

    for chapter_key in sorted(chapter_groups.keys()):
        chapter_nodes = chapter_groups[chapter_key]
        # Sort nodes within chapter by readiness order
        ordered_nodes = _order_by_readiness(chapter_nodes, readiness_order)
        # Split into chunks of MAX_CONCEPTS_PER_UNIT
        chunks = _chunk_nodes(ordered_nodes, MAX_CONCEPTS_PER_UNIT)
        for chunk_idx, chunk in enumerate(chunks):
            unit = _build_unit(
                chunk=chunk,
                chapter_key=chapter_key,
                chunk_index=chunk_idx,
                artifact_id=artifact_id,
            )
            units.append(unit)
            for cid in unit["concepts"]:
                unit_id_map[cid] = unit["unit_id"]

    # Second pass: resolve prerequisite unit IDs
    units = _resolve_unit_prerequisites(units, ekg_nodes, unit_id_map)

    # Stable sort: by teaching_sequence_index then unit_id
    units.sort(key=lambda u: (u.get("teaching_sequence_index", 999), u.get("unit_id", "")))

    # Assign global sequence index
    for i, unit in enumerate(units):
        unit["teaching_sequence_index"] = i

    context.set_output(STAGE, units)
    logger.info("Teaching Unit builder: produced %d teaching units.", len(units))


def _group_by_chapter(nodes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        chapter = str(node.get("chapter_id") or node.get("chapter") or "ungrouped")
        groups[chapter].append(node)
    return dict(groups)


def _order_by_readiness(
    nodes: List[Dict[str, Any]],
    readiness_order: List[str],
) -> List[Dict[str, Any]]:
    """Sorts nodes by their position in the readiness order.
    Nodes not in the readiness order are appended alphabetically."""
    order_index = {cid: i for i, cid in enumerate(readiness_order)}
    def sort_key(n: Dict[str, Any]) -> Tuple:
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        return (order_index.get(nid, len(readiness_order)), nid)
    return sorted(nodes, key=sort_key)


def _chunk_nodes(
    nodes: List[Dict[str, Any]],
    max_size: int,
) -> List[List[Dict[str, Any]]]:
    """Splits nodes into chunks of at most max_size, never empty."""
    if not nodes:
        return []
    return [nodes[i:i + max_size] for i in range(0, len(nodes), max_size)]


def _build_unit(
    chunk: List[Dict[str, Any]],
    chapter_key: str,
    chunk_index: int,
    artifact_id: str,
) -> Dict[str, Any]:
    """Builds one TeachingUnit from a chunk of EKG nodes."""
    concept_ids = sorted(
        str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        for n in chunk
    )
    # Deterministic unit ID
    key = json.dumps(
        {"chapter": chapter_key, "chunk": chunk_index, "concepts": concept_ids},
        sort_keys=True, separators=(",", ":"),
    )
    unit_id = str(uuid.uuid5(_TU_NAMESPACE, f"{artifact_id}:{key}"))

    # Teaching sequence: concept IDs in readiness order (already ordered by caller)
    teaching_sequence = [
        str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        for n in chunk
    ]

    # Aggregate metadata from concepts
    bloom_levels = sorted(set(
        n.get("pedagogical_metadata", {}).get("bloom_taxonomy_level", "understand")
        for n in chunk
    ))
    difficulties = [
        n.get("pedagogical_metadata", {}).get("difficulty_level", "medium")
        for n in chunk
    ]
    difficulty_level = _aggregate_difficulty(difficulties)
    total_duration = sum(
        n.get("pedagogical_metadata", {}).get("estimated_mastery_time_minutes", 30)
        for n in chunk
    )

    # Learning objectives: one per Bloom level present
    learning_objectives = _derive_learning_objectives(chunk, bloom_levels)

    # Title from first concept or chapter
    first_name = str(chunk[0].get("name") or chunk[0].get("title") or concept_ids[0] if chunk else "")
    if len(chunk) == 1:
        title = first_name
    else:
        title = f"{first_name} and related concepts" if first_name else f"Chapter {chapter_key} Unit {chunk_index + 1}"

    return {
        "unit_id": unit_id,
        "version": TU_VERSION,
        "title": title,
        "description": f"Teaching unit covering {len(concept_ids)} concept(s) from chapter {chapter_key}.",
        "chapter_reference": chapter_key,
        "chunk_index": chunk_index,
        "teaching_sequence_index": chunk_index,  # will be overwritten by global sort
        "concepts": concept_ids,
        "teaching_sequence": teaching_sequence,
        "prerequisites": [],  # resolved in second pass
        "prerequisite_unit_ids": [],  # resolved in second pass
        "learning_objectives": learning_objectives,
        "bloom_levels": bloom_levels,
        "difficulty_level": difficulty_level,
        "estimated_duration_minutes": max(10, total_duration),
        "navigation_hint": {
            "chapter": chapter_key,
            "position": chunk_index,
        },
    }


def _derive_learning_objectives(
    chunk: List[Dict[str, Any]],
    bloom_levels: List[str],
) -> List[str]:
    """Generates learning objectives from concepts and Bloom levels."""
    objectives: List[str] = []
    for level in bloom_levels:
        concept_names = [
            str(n.get("name") or n.get("title") or n.get("id", ""))
            for n in chunk
            if n.get("pedagogical_metadata", {}).get("bloom_taxonomy_level") == level
        ]
        if concept_names:
            names_str = ", ".join(concept_names[:3])
            if len(concept_names) > 3:
                names_str += f" (and {len(concept_names) - 3} more)"
            objectives.append(f"Students will be able to {level}: {names_str}.")
    if not objectives:
        concept_names = [str(n.get("name") or n.get("id", "")) for n in chunk[:3]]
        objectives.append(f"Students will understand: {', '.join(concept_names)}.")
    return objectives


def _aggregate_difficulty(difficulties: List[str]) -> str:
    """Returns 'hard' if any concept is hard, 'easy' if all are easy, else 'medium'."""
    if "hard" in difficulties:
        return "hard"
    if all(d == "easy" for d in difficulties):
        return "easy"
    return "medium"


def _resolve_unit_prerequisites(
    units: List[Dict[str, Any]],
    ekg_nodes: List[Dict[str, Any]],
    unit_id_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Second pass: for each unit, finds which other units must be taught first
    based on concept-level prerequisites."""
    # Build concept prerequisite lookup from EKG nodes
    concept_prereqs: Dict[str, List[str]] = {}
    for node in ekg_nodes:
        nid = str(node.get("id") or node.get("concept_id") or node.get("enriched_id", ""))
        prereqs = node.get("pedagogical_metadata", {}).get("prerequisite_ordering_weight")
        raw_prereqs = (
            node.get("prerequisites")
            or node.get("pedagogical_metadata", {}).get("prerequisite_concept_ids")
            or []
        )
        if nid:
            concept_prereqs[nid] = [str(p) for p in raw_prereqs]

    for unit in units:
        unit_concepts: Set[str] = set(unit["concepts"])
        prereq_unit_ids: Set[str] = set()
        for cid in unit_concepts:
            for prereq_cid in concept_prereqs.get(cid, []):
                if prereq_cid not in unit_concepts:  # cross-unit prerequisite
                    prereq_unit = unit_id_map.get(prereq_cid)
                    if prereq_unit and prereq_unit != unit["unit_id"]:
                        prereq_unit_ids.add(prereq_unit)
        unit["prerequisite_unit_ids"] = sorted(prereq_unit_ids)

    return units
