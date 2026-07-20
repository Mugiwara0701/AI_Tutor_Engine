"""
teacher_knowledge_base/builders/navigation_builder.py — M6.1: Navigation
System builder.

SPECIFICATION: NAVIGATION_SYSTEM_SPECIFICATION.md

SCOPE: The Navigation System provides O(1) lookup indexes for the Phase 2
runtime. It pre-computes:
  - concept_map: concept_id -> {unit_id, chapter, breadcrumb, metadata}
  - teaching_unit_map: unit_id -> {chapter, sequence_index, concepts, ...}
  - chapter_map: chapter_key -> {unit_ids, concept_ids, sequence_range}
  - breadcrumb_index: concept_id -> breadcrumb path string for display

Navigation does NOT implement search, assessment, or adaptive routing —
those are Phase 2. It only builds the lookup structures the runtime will use.

DETERMINISM: all keys are content-derived (concept IDs, unit IDs, chapter
keys — all already deterministic from upstream builders). No new IDs generated
here — only index construction.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.navigation")

NAV_VERSION = "M6.1.0"
STAGE = "navigation"


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_navigation(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_navigation(context: "TKBContext") -> None:
    teaching_units = context.require_output("teaching_units", STAGE)
    curriculum_graph = context.require_output("curriculum_graph", STAGE)
    ekg = context.get_output("ekg") or {}
    edst = context.get_output("edst") or {}

    ekg_nodes = ekg.get("nodes") or []
    global_sequence = curriculum_graph.get("global_teaching_sequence") or []
    chapters = curriculum_graph.get("chapters") or []

    # Build lookup structures
    concept_map = _build_concept_map(ekg_nodes, teaching_units, global_sequence)
    teaching_unit_map = _build_teaching_unit_map(teaching_units, global_sequence)
    chapter_map = _build_chapter_map(chapters, teaching_units, concept_map)
    breadcrumb_index = _build_breadcrumb_index(ekg_nodes, teaching_units, chapters)

    navigation = {
        "version": NAV_VERSION,
        "concept_map": concept_map,
        "teaching_unit_map": teaching_unit_map,
        "chapter_map": chapter_map,
        "breadcrumb_index": breadcrumb_index,
        "metadata": {
            "total_concepts_indexed": len(concept_map),
            "total_units_indexed": len(teaching_unit_map),
            "total_chapters_indexed": len(chapter_map),
            "version": NAV_VERSION,
        },
    }
    context.set_output(STAGE, navigation)
    logger.info(
        "Navigation builder: indexed %d concepts, %d units, %d chapters.",
        len(concept_map), len(teaching_unit_map), len(chapter_map),
    )


def _build_concept_map(
    ekg_nodes: List[Dict[str, Any]],
    teaching_units: List[Dict[str, Any]],
    global_sequence: List[str],
) -> Dict[str, Any]:
    """concept_id -> navigation record. O(1) lookup for runtime."""
    # Build unit membership lookup
    concept_to_unit: Dict[str, str] = {}
    for unit in teaching_units:
        uid = unit["unit_id"]
        for cid in (unit.get("concepts") or []):
            concept_to_unit[str(cid)] = uid

    sequence_index = {uid: i for i, uid in enumerate(global_sequence)}

    concept_map: Dict[str, Any] = {}
    for node in ekg_nodes:
        nid = str(node.get("id") or node.get("concept_id") or node.get("enriched_id", ""))
        if not nid:
            continue
        unit_id = concept_to_unit.get(nid, "")
        chapter = str(node.get("chapter_id") or node.get("chapter") or "")
        concept_map[nid] = {
            "concept_id": nid,
            "name": str(node.get("name") or node.get("title") or nid),
            "chapter": chapter,
            "teaching_unit_id": unit_id,
            "teaching_sequence_position": sequence_index.get(unit_id, -1),
            "difficulty": node.get("pedagogical_metadata", {}).get("difficulty_level", "medium"),
            "bloom_level": node.get("pedagogical_metadata", {}).get("bloom_taxonomy_level", "understand"),
        }
    return concept_map


def _build_teaching_unit_map(
    teaching_units: List[Dict[str, Any]],
    global_sequence: List[str],
) -> Dict[str, Any]:
    """unit_id -> navigation record."""
    sequence_index = {uid: i for i, uid in enumerate(global_sequence)}
    unit_map: Dict[str, Any] = {}
    for unit in teaching_units:
        uid = unit["unit_id"]
        unit_map[uid] = {
            "unit_id": uid,
            "title": unit.get("title", ""),
            "chapter": unit.get("chapter_reference", ""),
            "global_sequence_index": sequence_index.get(uid, -1),
            "concept_ids": unit.get("concepts", []),
            "concept_count": len(unit.get("concepts", [])),
            "estimated_duration_minutes": unit.get("estimated_duration_minutes", 30),
            "difficulty_level": unit.get("difficulty_level", "medium"),
            "prerequisite_unit_ids": unit.get("prerequisite_unit_ids", []),
        }
    return unit_map


def _build_chapter_map(
    chapters: List[Dict[str, Any]],
    teaching_units: List[Dict[str, Any]],
    concept_map: Dict[str, Any],
) -> Dict[str, Any]:
    """chapter_key -> navigation record."""
    unit_lookup: Dict[str, Dict[str, Any]] = {u["unit_id"]: u for u in teaching_units}
    chapter_map: Dict[str, Any] = {}
    for chapter in chapters:
        chapter_key = str(chapter.get("chapter_key", ""))
        unit_ids = chapter.get("unit_ids") or []
        concept_ids: List[str] = []
        for uid in unit_ids:
            u = unit_lookup.get(uid) or {}
            concept_ids.extend(u.get("concepts") or [])

        chapter_map[chapter_key] = {
            "chapter_key": chapter_key,
            "unit_ids": unit_ids,
            "unit_count": len(unit_ids),
            "concept_ids": sorted(set(concept_ids)),
            "concept_count": len(set(concept_ids)),
        }
    return chapter_map


def _build_breadcrumb_index(
    ekg_nodes: List[Dict[str, Any]],
    teaching_units: List[Dict[str, Any]],
    chapters: List[Dict[str, Any]],
) -> Dict[str, str]:
    """concept_id -> breadcrumb string, e.g. 'Chapter 3 > Newton\'s Laws > Force'"""
    # Build lookups
    concept_to_unit: Dict[str, str] = {}
    unit_to_chapter: Dict[str, str] = {}
    unit_lookup: Dict[str, Dict[str, Any]] = {}

    for unit in teaching_units:
        uid = unit["unit_id"]
        unit_lookup[uid] = unit
        unit_to_chapter[uid] = str(unit.get("chapter_reference", ""))
        for cid in (unit.get("concepts") or []):
            concept_to_unit[str(cid)] = uid

    breadcrumbs: Dict[str, str] = {}
    for node in ekg_nodes:
        nid = str(node.get("id") or node.get("concept_id") or node.get("enriched_id", ""))
        if not nid:
            continue
        name = str(node.get("name") or node.get("title") or nid)
        unit_id = concept_to_unit.get(nid, "")
        chapter = unit_to_chapter.get(unit_id, "")
        unit_title = unit_lookup.get(unit_id, {}).get("title", "") if unit_id else ""
        parts = [p for p in [f"Chapter {chapter}" if chapter else "", unit_title, name] if p]
        breadcrumbs[nid] = " > ".join(parts) if parts else name
    return breadcrumbs
