"""
teacher_knowledge_base/builders/runtime_index_builder.py — M6.1: Runtime
Index builder.

SPECIFICATION: RUNTIME_API_SPECIFICATION.md (runtime_indexes section)

SCOPE: Runtime indexes provide the pre-computed lookup structures the Phase 2
runtime API needs for O(1) / O(log n) access patterns. All indexes are built
from the outputs of earlier pipeline stages — no new computation, only
index construction.

INDEXES PRODUCED (per RUNTIME_API_SPECIFICATION.md):
  - concept_by_id: concept_id -> full concept record (from EKG)
  - teaching_unit_by_id: unit_id -> full unit record
  - concept_by_chapter: chapter_key -> [concept_ids] (sorted)
  - prerequisite_index: concept_id -> [prerequisite_concept_ids]
  - dependent_index: concept_id -> [dependent_concept_ids] (inverse of prereqs)
  - learning_path_index: concept_id -> {next_concepts, previous_concepts}
  - teaching_unit_by_chapter: chapter_key -> [unit_ids] (in sequence order)
  - progression_template_by_concept: concept_id -> [template_ids]

PERFORMANCE NOTE: all indexes are built in one pass each (O(n)) and stored
as plain dicts for O(1) Python dict lookup in the runtime. The runtime API
never rebuilds these indexes — they are frozen at build time.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.runtime_index")

RI_VERSION = "M6.1.0"
STAGE = "runtime_indexes"


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_runtime_indexes(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_runtime_indexes(context: "TKBContext") -> None:
    ekg = context.require_output("ekg", STAGE)
    teaching_units = context.require_output("teaching_units", STAGE)
    curriculum_graph = context.require_output("curriculum_graph", STAGE)
    cpt = context.get_output("concept_progression_templates") or []

    ekg_nodes = ekg.get("nodes") or []
    ekg_edges = ekg.get("edges") or []
    learning_paths = ekg.get("learning_paths") or []
    global_sequence = curriculum_graph.get("global_teaching_sequence") or []

    # --- Build each index -----------------------------------------------
    concept_by_id = _build_concept_by_id(ekg_nodes)
    teaching_unit_by_id = _build_teaching_unit_by_id(teaching_units)
    concept_by_chapter = _build_concept_by_chapter(ekg_nodes)
    prerequisite_index = _build_prerequisite_index(ekg_nodes, ekg_edges)
    dependent_index = _build_dependent_index(prerequisite_index)
    learning_path_index = _build_learning_path_index(learning_paths, ekg_nodes)
    teaching_unit_by_chapter = _build_teaching_unit_by_chapter(teaching_units, global_sequence)
    progression_template_by_concept = _build_progression_template_by_concept(cpt)

    runtime_indexes = {
        "version": RI_VERSION,
        "concept_by_id": concept_by_id,
        "teaching_unit_by_id": teaching_unit_by_id,
        "concept_by_chapter": concept_by_chapter,
        "prerequisite_index": prerequisite_index,
        "dependent_index": dependent_index,
        "learning_path_index": learning_path_index,
        "teaching_unit_by_chapter": teaching_unit_by_chapter,
        "progression_template_by_concept": progression_template_by_concept,
        "metadata": {
            "total_concepts_indexed": len(concept_by_id),
            "total_units_indexed": len(teaching_unit_by_id),
            "total_chapters_indexed": len(concept_by_chapter),
            "total_prerequisite_entries": sum(len(v) for v in prerequisite_index.values()),
            "total_learning_path_entries": len(learning_path_index),
            "version": RI_VERSION,
        },
    }
    context.set_output(STAGE, runtime_indexes)
    logger.info(
        "Runtime Index builder: %d concepts, %d units, %d chapters indexed.",
        len(concept_by_id), len(teaching_unit_by_id), len(concept_by_chapter),
    )


def _build_concept_by_id(ekg_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """concept_id -> full enriched concept record."""
    index: Dict[str, Any] = {}
    for node in ekg_nodes:
        nid = str(node.get("id") or node.get("concept_id") or node.get("enriched_id", ""))
        if nid:
            index[nid] = node
    return index


def _build_teaching_unit_by_id(teaching_units: List[Dict[str, Any]]) -> Dict[str, Any]:
    """unit_id -> full teaching unit record."""
    return {u["unit_id"]: u for u in teaching_units if u.get("unit_id")}


def _build_concept_by_chapter(ekg_nodes: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """chapter_key -> sorted list of concept_ids in that chapter."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for node in ekg_nodes:
        chapter = str(node.get("chapter_id") or node.get("chapter") or "ungrouped")
        nid = str(node.get("id") or node.get("concept_id") or node.get("enriched_id", ""))
        if nid:
            groups[chapter].append(nid)
    return {ch: sorted(ids) for ch, ids in sorted(groups.items())}


def _build_prerequisite_index(
    ekg_nodes: List[Dict[str, Any]],
    ekg_edges: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """concept_id -> sorted list of prerequisite concept_ids.
    Built from both EKG node prerequisite fields and prerequisite edges."""
    index: Dict[str, List[str]] = defaultdict(list)

    # From node fields
    for node in ekg_nodes:
        nid = str(node.get("id") or node.get("concept_id") or node.get("enriched_id", ""))
        if not nid:
            continue
        # pedagogical_metadata.prerequisite_concept_ids (from EKG builder)
        prereqs = (
            node.get("pedagogical_metadata", {}).get("prerequisite_concept_ids")
            or node.get("prerequisites")
            or []
        )
        for p in prereqs:
            pid = str(p)
            if pid and pid not in index[nid]:
                index[nid].append(pid)

    # From prerequisite edges
    for edge in ekg_edges:
        if str(edge.get("relationship_type", "")).lower() in ("prerequisite", "requires"):
            src = str(edge.get("source") or edge.get("from") or "")
            tgt = str(edge.get("target") or edge.get("to") or "")
            if src and tgt and src not in index[tgt]:
                index[tgt].append(src)

    return {k: sorted(set(v)) for k, v in index.items()}


def _build_dependent_index(
    prerequisite_index: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """concept_id -> sorted list of concept_ids that depend on this concept.
    This is the inverse of the prerequisite_index, built in one pass."""
    dependent: Dict[str, List[str]] = defaultdict(list)
    for concept_id, prereqs in prerequisite_index.items():
        for prereq_id in prereqs:
            dependent[prereq_id].append(concept_id)
    return {k: sorted(set(v)) for k, v in dependent.items()}


def _build_learning_path_index(
    learning_paths: List[Dict[str, Any]],
    ekg_nodes: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """concept_id -> {next_concepts: [...], previous_concepts: [...], path_ids: [...]}
    For each concept in each learning path, records its immediate neighbors."""
    node_ids: Set[str] = set()
    for n in ekg_nodes:
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        if nid:
            node_ids.add(nid)

    index: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"next_concepts": [], "previous_concepts": [], "path_ids": []}
    )

    for lp in learning_paths:
        path_id = str(lp.get("path_id") or "")
        sequence = lp.get("concept_sequence") or []
        for i, cid in enumerate(sequence):
            cid_str = str(cid)
            if cid_str not in index:
                index[cid_str] = {"next_concepts": [], "previous_concepts": [], "path_ids": []}
            if path_id and path_id not in index[cid_str]["path_ids"]:
                index[cid_str]["path_ids"].append(path_id)
            if i + 1 < len(sequence):
                next_cid = str(sequence[i + 1])
                if next_cid not in index[cid_str]["next_concepts"]:
                    index[cid_str]["next_concepts"].append(next_cid)
            if i > 0:
                prev_cid = str(sequence[i - 1])
                if prev_cid not in index[cid_str]["previous_concepts"]:
                    index[cid_str]["previous_concepts"].append(prev_cid)

    # Sort for determinism
    return {
        k: {
            "next_concepts": sorted(v["next_concepts"]),
            "previous_concepts": sorted(v["previous_concepts"]),
            "path_ids": sorted(v["path_ids"]),
        }
        for k, v in index.items()
    }


def _build_teaching_unit_by_chapter(
    teaching_units: List[Dict[str, Any]],
    global_sequence: List[str],
) -> Dict[str, List[str]]:
    """chapter_key -> list of unit_ids in teaching sequence order."""
    sequence_index = {uid: i for i, uid in enumerate(global_sequence)}
    chapter_units: Dict[str, List[str]] = defaultdict(list)
    for unit in teaching_units:
        chapter = str(unit.get("chapter_reference") or "ungrouped")
        chapter_units[chapter].append(unit["unit_id"])
    return {
        ch: sorted(ids, key=lambda uid: sequence_index.get(uid, 999))
        for ch, ids in sorted(chapter_units.items())
    }


def _build_progression_template_by_concept(
    templates: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """concept_id -> list of template_ids that include this concept."""
    index: Dict[str, List[str]] = defaultdict(list)
    for template in templates:
        tid = str(template.get("template_id", ""))
        if not tid:
            continue
        for cid in (template.get("core_sequence") or []):
            cid_str = str(cid)
            if tid not in index[cid_str]:
                index[cid_str].append(tid)
    return {k: sorted(v) for k, v in index.items()}
