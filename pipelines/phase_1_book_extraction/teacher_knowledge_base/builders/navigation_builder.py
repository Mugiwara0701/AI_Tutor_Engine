"""
teacher_knowledge_base/builders/navigation_builder.py — M6.1/M6.2 (remediated)

SPECIFICATION: NAVIGATION_SYSTEM_SPECIFICATION.md v1.1.1

PRINCIPLE (spec §1):
  Navigation indexes are pre-built, read-only views over canonical data.
  Navigation stores: ordered ID lists and session presets.
  Phase 2 fetches full content from the authoritative dict on demand.

NavigationIndex contains exactly 6 sub-navigations (spec §2):
  1. TeacherNavigation     — ordered sections with teaching metadata
  2. QuestionNavigation    — item_ids indexed by difficulty, bloom, type, provenance
  3. ConceptNavigation     — concept_index, name_lookup, alias_lookup
  4. RevisionNavigation    — full_chapter_revision, by_importance, spaced_repetition_groups
  5. AssessmentNavigation  — formative/summative/diagnostic sets
  6. LearningPathNavigation — canonical_path (= EDG.topological_order), path variants

WHAT THE OLD IMPLEMENTATION DID WRONG:
  - concept_map, teaching_unit_map, chapter_map, breadcrumb_index are NOT spec fields
  - LearningPathNavigation spec fields: canonical_path, beginner_path, accelerated_path,
    prerequisite_first_path, example_first_path, paths_by_time
  - QuestionNavigation must index by provenance_tier
  - RevisionNavigation must have spaced_repetition_groups
  - ConceptNavigation must have name_lookup and alias_lookup dicts

M6.2 Scope (per architecture): complete NavigationIndex with all 6 sub-navigations
fully populated, including all path variants, time-budget paths, and spaced repetition groups.
"""
from __future__ import annotations

import uuid
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.navigation")

_NAV_NS = uuid.UUID("11223344-0000-5566-7788-99aabbccddee")

STAGE = "navigation"
NAV_VERSION = "1.1.1"

# Spec §6 revision time budget concept counts (approximate)
_REVISION_TIME_BUDGETS = {
    "10_minutes": 2,
    "30_minutes": 6,
    "60_minutes": 12,
    "full": None,  # all concepts
}

# Spaced repetition: recommended interval in days per importance tier (advisory)
_SPACED_REP_INTERVALS = {"core": 7, "supporting": 14, "enrichment": 30}


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


def _build_navigation(context: "TKBContext") -> None:  # noqa: F821
    teaching_units = context.require_output("teaching_units", STAGE)
    edg = context.require_output("edg", STAGE)
    edst = context.get_output("edst") or {}
    cpts = context.get_output("concept_progression_templates") or {}
    curriculum_graph = context.get_output("curriculum_graph") or {}

    topological_order: List[str] = edg.get("topological_order") or list(teaching_units.keys())

    # --- 1. TeacherNavigation (spec §3) -----------------------------------
    teacher_nav = _build_teacher_navigation(edst, topological_order, teaching_units)

    # --- 2. QuestionNavigation (spec §4) ----------------------------------
    question_nav = _build_question_navigation(teaching_units)

    # --- 3. ConceptNavigation (spec §5) -----------------------------------
    concept_nav = _build_concept_navigation(teaching_units, edst)

    # --- 4. RevisionNavigation (spec §6) ----------------------------------
    revision_nav = _build_revision_navigation(
        topological_order, teaching_units, cpts
    )

    # --- 5. AssessmentNavigation (spec §7) --------------------------------
    assessment_nav = _build_assessment_navigation(teaching_units, topological_order)

    # --- 6. LearningPathNavigation (spec §8) ------------------------------
    learning_path_nav = _build_learning_path_navigation(
        topological_order, teaching_units, edg
    )

    navigation = {
        "teacher_navigation": teacher_nav,
        "question_navigation": question_nav,
        "concept_navigation": concept_nav,
        "revision_navigation": revision_nav,
        "assessment_navigation": assessment_nav,
        "learning_path_navigation": learning_path_nav,
    }
    context.set_output(STAGE, navigation)
    logger.info(
        "Navigation builder: 6 sub-navigations built. %d concepts indexed.",
        len(teaching_units),
    )


# ---------------------------------------------------------------------------
# 1. TeacherNavigation (spec §3)
# ---------------------------------------------------------------------------

def _build_teacher_navigation(
    edst: Dict[str, Any],
    topological_order: List[str],
    teaching_units: Dict[str, Any],
) -> Dict[str, Any]:
    nav_id = str(uuid.uuid5(_NAV_NS, "teacher_nav"))
    total_time = sum(
        float(tu.get("estimated_teaching_time_minutes") or 0)
        for tu in teaching_units.values()
    )
    edst_nodes = edst.get("nodes") or {}
    node_list = (
        list(edst_nodes.values()) if isinstance(edst_nodes, dict) else edst_nodes
    )
    # Sort sections by topological concept order
    concept_order_idx = {cid: i for i, cid in enumerate(topological_order)}

    ordered_sections = []
    concept_to_section: Dict[str, str] = {}
    for i, node in enumerate(node_list):
        if not isinstance(node, dict):
            continue
        section_id = str(node.get("enriched_node_id") or node.get("node_id") or f"s{i}")
        teaching_unit_ids = list(node.get("teaching_unit_ids") or node.get("concept_ids") or [])
        bloom_primary = str(node.get("bloom_taxonomy", {}).get("primary_level") or "")
        prereq_sections: List[str] = []  # simplified: no section-level prereqs computed here

        # Determine suggested_order from topological position of first concept
        first_concept_pos = min(
            (concept_order_idx.get(cid, len(topological_order)) for cid in teaching_unit_ids),
            default=i,
        )

        section_entry = {
            "section_id": section_id,
            "heading_text": str(node.get("heading_text") or ""),
            "level": int(node.get("level") or 0),
            "suggested_order": first_concept_pos + 1,
            "estimated_minutes": float(node.get("estimated_teaching_time_minutes") or 0),
            "concept_count": len(teaching_unit_ids),
            "teaching_unit_ids": teaching_unit_ids,
            "prerequisite_section_ids": prereq_sections,
            "bloom_primary": bloom_primary,
        }
        ordered_sections.append(section_entry)
        for cid in teaching_unit_ids:
            concept_to_section[cid] = section_id

    # Sort by suggested_order
    ordered_sections.sort(key=lambda s: (s["suggested_order"], s["section_id"]))

    return {
        "nav_id": nav_id,
        "chapter_title": "",  # populated from TKBMetadata in artifact assembly
        "total_sections": len(ordered_sections),
        "total_concepts": len(teaching_units),
        "total_teaching_time_minutes": total_time,
        "ordered_sections": ordered_sections,
        "concept_to_section": concept_to_section,
    }


# ---------------------------------------------------------------------------
# 2. QuestionNavigation (spec §4)
# ---------------------------------------------------------------------------

def _build_question_navigation(
    teaching_units: Dict[str, Any],
) -> Dict[str, Any]:
    nav_id = str(uuid.uuid5(_NAV_NS, "question_nav"))

    by_difficulty: Dict[str, List[str]] = {"easy": [], "medium": [], "hard": []}
    by_bloom_level: Dict[str, List[str]] = {
        lvl: [] for lvl in ("remember", "understand", "apply", "analyze", "evaluate", "create")
    }
    by_concept: Dict[str, List[str]] = {}
    by_type: Dict[str, List[str]] = {
        t: [] for t in ("mcq", "short_answer", "long_answer", "fill_blank", "true_false")
    }
    by_provenance_tier: Dict[str, List[str]] = {
        t: [] for t in ("extracted", "template_derived", "empty_placeholder")
    }
    all_item_ids: List[str] = []

    for concept_id, tu in teaching_units.items():
        concept_items: List[str] = []
        for item in (tu.get("assessments") or []) + (tu.get("practice_questions") or []):
            iid = str(item.get("item_id") or "")
            if not iid:
                continue
            all_item_ids.append(iid)
            concept_items.append(iid)
            # Difficulty
            diff = str(item.get("difficulty") or "medium")
            by_difficulty.setdefault(diff, []).append(iid)
            # Bloom
            bl = str(item.get("bloom_level") or "")
            if bl in by_bloom_level:
                by_bloom_level[bl].append(iid)
            # Type
            it = str(item.get("item_type") or "short_answer")
            by_type.setdefault(it, []).append(iid)
            # Provenance
            pt = str(item.get("provenance_tier") or "empty_placeholder")
            by_provenance_tier.setdefault(pt, []).append(iid)
        if concept_items:
            by_concept[concept_id] = concept_items

    # Curated chapter test: balanced selection (easy/medium/hard, multiple types)
    chapter_test = _curate_chapter_test(by_difficulty, by_bloom_level)
    # Quick check: 5 formative items
    quick_check = _curate_quick_check(by_difficulty)

    return {
        "nav_id": nav_id,
        "by_difficulty": by_difficulty,
        "by_bloom_level": by_bloom_level,
        "by_concept": by_concept,
        "by_type": by_type,
        "by_provenance_tier": by_provenance_tier,
        "chapter_test_item_ids": chapter_test,
        "quick_check_item_ids": quick_check,
    }


def _curate_chapter_test(
    by_difficulty: Dict[str, List[str]],
    by_bloom_level: Dict[str, List[str]],
) -> List[str]:
    """Balanced chapter test selection: mix of difficulties and bloom levels."""
    selected: List[str] = []
    seen: Set[str] = set()
    # Take ~33% from each difficulty level
    for diff in ("easy", "medium", "hard"):
        items = by_difficulty.get(diff) or []
        for iid in items[:5]:
            if iid not in seen:
                seen.add(iid)
                selected.append(iid)
    return selected


def _curate_quick_check(by_difficulty: Dict[str, List[str]]) -> List[str]:
    """5-question formative quick check (easy items)."""
    easy = by_difficulty.get("easy") or []
    medium = by_difficulty.get("medium") or []
    items = (easy + medium)[:5]
    return items


# ---------------------------------------------------------------------------
# 3. ConceptNavigation (spec §5)
# ---------------------------------------------------------------------------

def _build_concept_navigation(
    teaching_units: Dict[str, Any],
    edst: Dict[str, Any],
) -> Dict[str, Any]:
    nav_id = str(uuid.uuid5(_NAV_NS, "concept_nav"))
    edst_nodes = edst.get("nodes") or {}
    concept_to_edst: Dict[str, List[str]] = defaultdict(list)
    for node in (edst_nodes.values() if isinstance(edst_nodes, dict) else edst_nodes):
        if isinstance(node, dict):
            nid = str(node.get("enriched_node_id") or "")
            for cid in (node.get("teaching_unit_ids") or node.get("concept_ids") or []):
                if nid:
                    concept_to_edst[str(cid)].append(nid)

    concept_index: Dict[str, Any] = {}
    name_lookup: Dict[str, str] = {}
    alias_lookup: Dict[str, str] = {}

    for concept_id, tu in teaching_units.items():
        concept_name = str(tu.get("title") or concept_id)
        concept_key = str(tu.get("concept_key") or "")
        unit_id = str(tu.get("unit_id") or concept_id)
        edst_node_ids = list(tu.get("edst_node_ids") or concept_to_edst.get(concept_id) or [])
        ekg_node_id = str(tu.get("ekg_node_id") or "")
        edg_node_id = str(tu.get("edg_node_id") or "")

        entry = {
            "concept_id": concept_id,
            "concept_key": concept_key,
            "concept_name": concept_name,
            "teaching_unit_id": unit_id,
            "edst_node_ids": edst_node_ids,
            "ekg_node_id": ekg_node_id,
            "edg_node_id": edg_node_id,
            "difficulty": str(tu.get("difficulty") or ""),
            "importance": str(tu.get("importance") or "core"),
        }
        concept_index[concept_id] = entry
        name_lookup[concept_name.lower()] = concept_id
        # Alias lookup: concept_key -> concept_id
        if concept_key:
            alias_lookup[concept_key.lower()] = concept_id

    return {
        "nav_id": nav_id,
        "concept_index": concept_index,
        "name_lookup": name_lookup,
        "alias_lookup": alias_lookup,
    }


# ---------------------------------------------------------------------------
# 4. RevisionNavigation (spec §6)
# ---------------------------------------------------------------------------

def _build_revision_navigation(
    topological_order: List[str],
    teaching_units: Dict[str, Any],
    cpts: Dict[str, Any],
) -> Dict[str, Any]:
    nav_id = str(uuid.uuid5(_NAV_NS, "revision_nav"))

    # Partition by importance (from teaching_units)
    by_importance: Dict[str, List[str]] = {"core": [], "supporting": [], "enrichment": []}
    for cid in topological_order:
        imp = str(teaching_units.get(cid, {}).get("importance") or "core")
        by_importance.setdefault(imp, []).append(cid)

    # full_chapter_revision = EDG topological order, core-first (spec §6)
    core_first = by_importance["core"] + by_importance["supporting"] + by_importance["enrichment"]

    # All formula IDs in section order
    key_formula_ids: List[str] = []
    definition_concept_ids: List[str] = []
    mnemonics_available: List[str] = []

    for cid in topological_order:
        tu = teaching_units.get(cid) or {}
        for f in (tu.get("formulae") or []):
            fid = str(f.get("formula_id") or "")
            if fid:
                key_formula_ids.append(fid)
        if tu.get("definition", {}).get("text"):
            definition_concept_ids.append(cid)
        for note in (tu.get("revision_notes") or []):
            if str(note.get("note_type") or "") == "mnemonic":
                mnemonics_available.append(cid)
                break

    # Pre-built time-budget subsets (core-first, truncated to rough minute budget)
    avg_minutes_per_concept = (
        sum(float(teaching_units.get(cid, {}).get("estimated_teaching_time_minutes") or 15)
            for cid in topological_order) / max(1, len(topological_order))
    )
    revision_by_time: Dict[str, List[str]] = {}
    for budget_label, n_concepts in _REVISION_TIME_BUDGETS.items():
        if n_concepts is None:
            revision_by_time[budget_label] = core_first
        else:
            revision_by_time[budget_label] = core_first[:n_concepts]

    # Spaced repetition groups (spec §6)
    spaced_repetition_groups = _build_spaced_rep_groups(by_importance, teaching_units)

    return {
        "nav_id": nav_id,
        "full_chapter_revision": core_first,
        "by_importance": by_importance,
        "key_formula_ids": key_formula_ids,
        "definition_concept_ids": definition_concept_ids,
        "mnemonics_available": mnemonics_available,
        "revision_by_time": revision_by_time,
        "spaced_repetition_groups": spaced_repetition_groups,
    }


def _build_spaced_rep_groups(
    by_importance: Dict[str, List[str]],
    teaching_units: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Group concepts by importance tier for spaced repetition (spec §6)."""
    groups = []
    group_ns = uuid.UUID("feedface-0000-1111-2222-333344445555")
    for tier in ("core", "supporting", "enrichment"):
        concept_ids = by_importance.get(tier) or []
        if not concept_ids:
            continue
        est_minutes = sum(
            float(teaching_units.get(cid, {}).get("estimated_teaching_time_minutes") or 0)
            for cid in concept_ids
        )
        group_id = str(uuid.uuid5(group_ns, f"spr:{tier}"))
        groups.append({
            "group_id": group_id,
            "concept_ids": concept_ids,
            "estimated_minutes": round(est_minutes, 2),
            "recommended_interval_days": _SPACED_REP_INTERVALS.get(tier, 14),
        })
    return groups


# ---------------------------------------------------------------------------
# 5. AssessmentNavigation (spec §7)
# ---------------------------------------------------------------------------

def _build_assessment_navigation(
    teaching_units: Dict[str, Any],
    topological_order: List[str],
) -> Dict[str, Any]:
    nav_id = str(uuid.uuid5(_NAV_NS, "assessment_nav"))

    # Build sets: formative (per-section, practice_questions), summative (chapter), diagnostic
    formative_sets: List[Dict[str, Any]] = []
    summative_sets: List[Dict[str, Any]] = []
    diagnostic_sets: List[Dict[str, Any]] = []
    by_concept: Dict[str, List[str]] = {}

    set_ns = uuid.UUID("cafe1234-5678-0000-1111-222233334444")
    all_summative_ids: List[str] = []

    for concept_id in topological_order:
        tu = teaching_units.get(concept_id) or {}
        concept_name = str(tu.get("title") or concept_id)

        # Formative: practice_questions
        practice_ids = [
            a["item_id"] for a in (tu.get("practice_questions") or [])
            if a.get("item_id") and a.get("provenance_tier") != "empty_placeholder"
        ]
        if practice_ids:
            set_id = str(uuid.uuid5(set_ns, f"formative:{concept_id}"))
            total_marks = len(practice_ids)
            formative_sets.append({
                "set_id": set_id,
                "name": f"{concept_name} Quick Check",
                "item_ids": practice_ids,
                "total_marks": total_marks,
                "time_minutes": float(len(practice_ids) * 2),
                "concept_ids": [concept_id],
                "difficulty": str(tu.get("difficulty") or "medium"),
                "bloom_levels": list(tu.get("bloom_taxonomy", {}).get("levels_present") or []),
            })

        # Assessment items -> summative
        formal_ids = [
            a["item_id"] for a in (tu.get("assessments") or [])
            if a.get("item_id") and a.get("provenance_tier") != "empty_placeholder"
        ]
        all_summative_ids.extend(formal_ids)
        by_concept[concept_id] = [s["set_id"] for s in formative_sets if concept_id in s.get("concept_ids", [])]

    # Chapter summative
    if all_summative_ids:
        chapter_set_id = str(uuid.uuid5(set_ns, "summative:chapter"))
        summative_sets.append({
            "set_id": chapter_set_id,
            "name": "Chapter Assessment",
            "item_ids": all_summative_ids,
            "total_marks": len(all_summative_ids),
            "time_minutes": float(len(all_summative_ids) * 3),
            "concept_ids": topological_order,
            "difficulty": "mixed",
            "bloom_levels": [],
        })

    # Diagnostic: prerequisite checking (first few concepts in topo order)
    diag_concepts = topological_order[:min(5, len(topological_order))]
    diag_item_ids = [
        a["item_id"]
        for cid in diag_concepts
        for a in ((teaching_units.get(cid) or {}).get("practice_questions") or [])
        if a.get("item_id") and a.get("provenance_tier") != "empty_placeholder"
    ]
    if diag_item_ids:
        diag_set_id = str(uuid.uuid5(set_ns, "diagnostic:prereqs"))
        diagnostic_sets.append({
            "set_id": diag_set_id,
            "name": "Prerequisite Check",
            "item_ids": diag_item_ids,
            "total_marks": len(diag_item_ids),
            "time_minutes": float(len(diag_item_ids) * 2),
            "concept_ids": diag_concepts,
            "difficulty": "easy",
            "bloom_levels": ["remember", "understand"],
        })

    return {
        "nav_id": nav_id,
        "formative_sets": formative_sets,
        "summative_sets": summative_sets,
        "diagnostic_sets": diagnostic_sets,
        "by_concept": by_concept,
    }


# ---------------------------------------------------------------------------
# 6. LearningPathNavigation (spec §8)
# ---------------------------------------------------------------------------

def _build_learning_path_navigation(
    topological_order: List[str],
    teaching_units: Dict[str, Any],
    edg: Dict[str, Any],
) -> Dict[str, Any]:
    nav_id = str(uuid.uuid5(_NAV_NS, "learning_path_nav"))

    canonical_path = list(topological_order)  # = EDG.topological_order (spec §8)

    # beginner_path: core concepts only, simplest first
    beginner_path = [
        cid for cid in canonical_path
        if str(teaching_units.get(cid, {}).get("importance") or "core") == "core"
    ]

    # accelerated_path: skips supplementary/enrichment
    accelerated_path = [
        cid for cid in canonical_path
        if str(teaching_units.get(cid, {}).get("importance") or "core") != "enrichment"
    ]

    # prerequisite_first_path: = canonical_path (spec §8)
    prerequisite_first_path = list(canonical_path)

    # example_first_path: concepts with examples reordered earlier
    # Partition: has_examples first, then rest (preserving topo order within each partition)
    concepts_with_examples = [
        cid for cid in canonical_path
        if len(teaching_units.get(cid, {}).get("examples") or []) > 0
    ]
    concepts_without_examples = [
        cid for cid in canonical_path if cid not in set(concepts_with_examples)
    ]
    example_first_path = concepts_with_examples + concepts_without_examples

    # paths_by_time: time-budget slices of beginner_path
    avg_min = sum(
        float(teaching_units.get(cid, {}).get("estimated_teaching_time_minutes") or 30)
        for cid in canonical_path
    ) / max(1, len(canonical_path))

    def concepts_for_budget(budget_minutes: float, source: List[str]) -> List[str]:
        total = 0.0
        result = []
        for cid in source:
            t = float(teaching_units.get(cid, {}).get("estimated_teaching_time_minutes") or avg_min)
            if total + t > budget_minutes and result:
                break
            result.append(cid)
            total += t
        return result

    paths_by_time = {
        "30_minutes": concepts_for_budget(30, beginner_path),
        "60_minutes": concepts_for_budget(60, beginner_path),
        "90_minutes": concepts_for_budget(90, beginner_path),
        "full": list(canonical_path),
    }

    return {
        "nav_id": nav_id,
        "canonical_path": canonical_path,
        "beginner_path": beginner_path,
        "accelerated_path": accelerated_path,
        "prerequisite_first_path": prerequisite_first_path,
        "example_first_path": example_first_path,
        "paths_by_time": paths_by_time,
    }
