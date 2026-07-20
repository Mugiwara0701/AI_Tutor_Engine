"""
teacher_knowledge_base/builders/runtime_index_builder.py — M6.1/M6.2 (remediated)

SPECIFICATION: RUNTIME_API_SPECIFICATION.md v1.1.1

7 REQUIRED INDEXES (spec §2):
  1. concept_lookup_index    — {by_id, by_key, by_name} -> ConceptNavEntry
  2. semantic_search_index   — {entries[], total_entries} (BM25-ready, lexical v1)
  3. prerequisite_index      — {by_concept -> PrerequisiteIndexEntry}
  4. teaching_retrieval_index — {by_concept_id, by_section_id, by_difficulty, by_importance}
  5. revision_retrieval_index — {by_concept_id, formula_ids_ordered, definition_index, core_concept_ids}
  6. assessment_retrieval_index — {by_concept_id, by_difficulty, by_bloom_level, by_type, by_provenance_tier, chapter_test_item_ids, assessment_item_location}
  7. curriculum_traversal_index — {by_concept_id, cross_chapter}

ID-ONLY RULE (spec §2, AUTHORITY_MATRIX §7.2):
  Indexes store IDs and short lookup keys ONLY.
  No full-object copies (except SemanticSearchEntry.display_text for BM25 matching).
  Full objects fetched from their canonical owner on demand.

WHAT THE OLD IMPLEMENTATION DID WRONG:
  - dependent_index: not a spec field
  - learning_path_index: not a spec field (that's navigation.learning_path_navigation)
  - teaching_unit_by_chapter: not a spec field
  - progression_template_by_concept: not a spec field
  - concept_by_id: wrong name — should be concept_lookup_index.by_id

M6.2 Scope:
  - semantic_search_index with pre-tokenized entries (lexical BM25 v1)
  - assessment_retrieval_index with assessment_item_location for reverse lookup
  - All 7 indexes fully populated
"""
from __future__ import annotations

import uuid
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.runtime_index")

_RI_NS = uuid.UUID("deadbeef-0000-1234-5678-abcdef012345")

STAGE = "runtime_indexes"
RI_VERSION = "1.1.1"


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


def _build_runtime_indexes(context: "TKBContext") -> None:  # noqa: F821
    teaching_units = context.require_output("teaching_units", STAGE)
    edg = context.require_output("edg", STAGE)
    edst = context.get_output("edst") or {}
    curriculum_graph = context.get_output("curriculum_graph") or {}
    navigation = context.get_output("navigation") or {}

    # --- 1. concept_lookup_index (spec §2, §4) ----------------------------
    concept_lookup_index = _build_concept_lookup_index(teaching_units, edst)

    # --- 2. semantic_search_index (spec §2, §9, v1 lexical BM25) ---------
    semantic_search_index = _build_semantic_search_index(teaching_units)

    # --- 3. prerequisite_index (spec §2, §7) ------------------------------
    prerequisite_index = _build_prerequisite_index(teaching_units, edg)

    # --- 4. teaching_retrieval_index (spec §2, §5) ------------------------
    teaching_retrieval_index = _build_teaching_retrieval_index(teaching_units, edst)

    # --- 5. revision_retrieval_index (spec §2) ----------------------------
    revision_retrieval_index = _build_revision_retrieval_index(
        teaching_units, edg
    )

    # --- 6. assessment_retrieval_index (spec §2, §8) ----------------------
    assessment_retrieval_index = _build_assessment_retrieval_index(teaching_units, navigation)

    # --- 7. curriculum_traversal_index (spec §2) --------------------------
    curriculum_traversal_index = _build_curriculum_traversal_index(curriculum_graph)

    runtime_indexes = {
        "concept_lookup_index": concept_lookup_index,
        "semantic_search_index": semantic_search_index,
        "prerequisite_index": prerequisite_index,
        "teaching_retrieval_index": teaching_retrieval_index,
        "revision_retrieval_index": revision_retrieval_index,
        "assessment_retrieval_index": assessment_retrieval_index,
        "curriculum_traversal_index": curriculum_traversal_index,
    }
    context.set_output(STAGE, runtime_indexes)
    logger.info(
        "Runtime Index builder: 7 indexes built. %d concepts indexed, %d search entries.",
        len(teaching_units),
        len(semantic_search_index.get("entries") or []),
    )


# ---------------------------------------------------------------------------
# 1. concept_lookup_index
# ---------------------------------------------------------------------------

def _build_concept_lookup_index(
    teaching_units: Dict[str, Any],
    edst: Dict[str, Any],
) -> Dict[str, Any]:
    """ConceptNavEntry (200 bytes max per entry — IDs and metadata only)."""
    edst_nodes = edst.get("nodes") or {}
    concept_to_edst: Dict[str, List[str]] = defaultdict(list)
    for node in (edst_nodes.values() if isinstance(edst_nodes, dict) else edst_nodes):
        if isinstance(node, dict):
            nid = str(node.get("enriched_node_id") or "")
            for cid in (node.get("teaching_unit_ids") or node.get("concept_ids") or []):
                if nid:
                    concept_to_edst[str(cid)].append(nid)

    by_id: Dict[str, Any] = {}
    by_key: Dict[str, str] = {}
    by_name: Dict[str, str] = {}

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
            "teaching_unit_id": unit_id,   # reference identifier
            # Note: teaching_units dict keyed by concept_id; use concept_id for lookups
            "edst_node_ids": edst_node_ids,
            "ekg_node_id": ekg_node_id,
            "edg_node_id": edg_node_id,
            "difficulty": str(tu.get("difficulty") or ""),
            "importance": str(tu.get("importance") or "core"),
        }
        by_id[concept_id] = entry
        if concept_key:
            by_key[concept_key] = concept_id
        by_name[concept_name.lower()] = concept_id

    return {"by_id": by_id, "by_key": by_key, "by_name": by_name}


# ---------------------------------------------------------------------------
# 2. semantic_search_index (lexical v1, BM25-ready)
# ---------------------------------------------------------------------------

def _build_semantic_search_index(
    teaching_units: Dict[str, Any],
) -> Dict[str, Any]:
    """Pre-tokenized entries for BM25 over display_text (spec §2, §9).
    'Semantic' = entry-type-aware search, NOT vector similarity in v1.
    No embedding vectors in v1 (embedding_model = null in serialization_metadata)."""
    entries: List[Dict[str, Any]] = []

    for concept_id, tu in teaching_units.items():
        unit_id = str(tu.get("unit_id") or concept_id)
        concept_name = str(tu.get("title") or concept_id)
        definition_text = str(tu.get("definition", {}).get("text") or "")

        # Concept entry
        display_text = f"{concept_name}: {definition_text}"[:500]
        entries.append({
            "entry_id": concept_id,
            "entry_type": "concept",
            "display_text": display_text,
            "concept_ids": [concept_id],
            "unit_id": unit_id,
        })

        # Definition entry (if different from concept display_text)
        if definition_text:
            entries.append({
                "entry_id": f"def:{concept_id}",
                "entry_type": "definition",
                "display_text": definition_text[:300],
                "concept_ids": [concept_id],
                "unit_id": unit_id,
            })

        # Example entries
        for example in (tu.get("examples") or []) + (tu.get("worked_examples") or []):
            eid = str(example.get("example_id") or "")
            if not eid:
                continue
            ex_text = str(example.get("title") or "") + " " + str(example.get("body") or "")
            entries.append({
                "entry_id": eid,
                "entry_type": "example",
                "display_text": ex_text[:300],
                "concept_ids": [concept_id] + [
                    str(cr.get("concept_id") or "")
                    for cr in (example.get("concept_refs") or [])
                    if isinstance(cr, dict)
                ],
                "unit_id": unit_id,
            })

        # Formula entries
        for formula in (tu.get("formulae") or []):
            fid = str(formula.get("formula_id") or "")
            if not fid:
                continue
            f_text = str(formula.get("name") or "") + " " + str(formula.get("expression") or "")
            entries.append({
                "entry_id": fid,
                "entry_type": "formula",
                "display_text": f_text[:200],
                "concept_ids": [concept_id],
                "unit_id": unit_id,
            })

        # Activity entries
        for act in (tu.get("activities") or []):
            aid = str(act.get("activity_id") or "")
            if not aid:
                continue
            a_text = str(act.get("title") or "") + " " + str(act.get("description") or "")
            entries.append({
                "entry_id": aid,
                "entry_type": "activity",
                "display_text": a_text[:300],
                "concept_ids": [concept_id],
                "unit_id": unit_id,
            })

        # Figure entries
        for fig in (tu.get("figures") or []):
            fid = str(fig.get("figure_id") or "")
            if not fid:
                continue
            fig_text = str(fig.get("caption") or "") + " " + str(fig.get("semantic_description") or "")
            entries.append({
                "entry_id": fid,
                "entry_type": "figure",
                "display_text": fig_text[:300],
                "concept_ids": [concept_id],
                "unit_id": unit_id,
            })

    return {"entries": entries, "total_entries": len(entries)}


# ---------------------------------------------------------------------------
# 3. prerequisite_index
# ---------------------------------------------------------------------------

def _build_prerequisite_index(
    teaching_units: Dict[str, Any],
    edg: Dict[str, Any],
) -> Dict[str, Any]:
    """PrerequisiteIndexEntry per concept (spec §2). All IDs from EDG."""
    edg_nodes = edg.get("nodes") or {}
    edg_edges = edg.get("edges") or {}

    # Build dependent_lookup: concept_id -> list of concept_ids that depend on it
    dependent_lookup: Dict[str, List[str]] = defaultdict(list)
    for edge in (edg_edges.values() if isinstance(edg_edges, dict) else []):
        if isinstance(edge, dict) and edge.get("is_blocking"):
            src = str(edge.get("source_concept_id") or "")
            tgt = str(edge.get("target_concept_id") or "")
            if src and tgt:
                dependent_lookup[src].append(tgt)

    # Prerequisite chains from EDG
    prereq_chains = {
        str(ch.get("root_concept_id") or ""): ch.get("sequence") or []
        for ch in (edg.get("prerequisite_chains") or [])
        if ch.get("root_concept_id")
    }

    by_concept: Dict[str, Any] = {}
    for concept_id in teaching_units:
        node = (edg_nodes.get(concept_id) if isinstance(edg_nodes, dict) else {}) or {}
        prereq_ids = list(node.get("prerequisite_ids") or [])
        # Blocking = REQUIRES edges; soft = RECOMMENDED_BEFORE edges
        blocking_ids = []
        soft_ids = []
        for edge in (edg_edges.values() if isinstance(edg_edges, dict) else []):
            if not isinstance(edge, dict):
                continue
            tgt = str(edge.get("target_concept_id") or "")
            src = str(edge.get("source_concept_id") or "")
            if tgt == concept_id and src:
                if edge.get("edge_type") in ("REQUIRES", "GATES"):
                    blocking_ids.append(src)
                elif edge.get("edge_type") == "RECOMMENDED_BEFORE":
                    soft_ids.append(src)

        depth = int(node.get("depth") or 0)
        critical_path = prereq_chains.get(concept_id) or []

        by_concept[concept_id] = {
            "concept_id": concept_id,
            "blocking_prerequisite_ids": sorted(set(blocking_ids)),
            "soft_prerequisite_ids": sorted(set(soft_ids)),
            "dependent_ids": sorted(set(dependent_lookup.get(concept_id) or [])),
            "prerequisite_depth": depth,
            "critical_path": critical_path,
        }

    return {"by_concept": by_concept}


# ---------------------------------------------------------------------------
# 4. teaching_retrieval_index
# ---------------------------------------------------------------------------

def _build_teaching_retrieval_index(
    teaching_units: Dict[str, Any],
    edst: Dict[str, Any],
) -> Dict[str, Any]:
    """V1.1: by_concept_id stores unit_id (string), not TeachingUnit object."""
    by_concept_id: Dict[str, str] = {}
    by_section_id: Dict[str, List[str]] = {}
    by_difficulty: Dict[str, List[str]] = {"easy": [], "medium": [], "hard": []}
    by_importance: Dict[str, List[str]] = {"core": [], "supporting": [], "enrichment": []}

    edst_nodes = edst.get("nodes") or {}
    for node in (edst_nodes.values() if isinstance(edst_nodes, dict) else edst_nodes):
        if isinstance(node, dict):
            section_id = str(node.get("enriched_node_id") or "")
            if section_id:
                by_section_id[section_id] = list(
                    node.get("teaching_unit_ids") or node.get("concept_ids") or []
                )

    for concept_id, tu in teaching_units.items():
        unit_id = str(tu.get("unit_id") or concept_id)
        by_concept_id[concept_id] = unit_id

        diff = str(tu.get("difficulty") or "")
        if diff in by_difficulty:
            by_difficulty[diff].append(concept_id)

        imp = str(tu.get("importance") or "core")
        by_importance.setdefault(imp, []).append(concept_id)

    return {
        "by_concept_id": by_concept_id,
        "by_section_id": by_section_id,
        "by_difficulty": by_difficulty,
        "by_importance": by_importance,
    }


# ---------------------------------------------------------------------------
# 5. revision_retrieval_index
# ---------------------------------------------------------------------------

def _build_revision_retrieval_index(
    teaching_units: Dict[str, Any],
    edg: Dict[str, Any],
) -> Dict[str, Any]:
    """Spec §2. definition_index stores text (exception to ID-only rule — spec §7.2)."""
    by_concept_id: Dict[str, List[str]] = {}
    formula_ids_ordered: List[str] = []
    definition_index: Dict[str, str] = {}
    core_concept_ids: List[str] = []

    topo_order: List[str] = edg.get("topological_order") or list(teaching_units.keys())

    for concept_id in topo_order:
        tu = teaching_units.get(concept_id) or {}
        note_ids = [n["note_id"] for n in (tu.get("revision_notes") or []) if n.get("note_id")]
        if note_ids:
            by_concept_id[concept_id] = note_ids
        for f in (tu.get("formulae") or []):
            fid = str(f.get("formula_id") or "")
            if fid:
                formula_ids_ordered.append(fid)
        def_text = str(tu.get("definition", {}).get("text") or "")
        if def_text:
            definition_index[concept_id] = def_text
        if str(tu.get("importance") or "core") == "core":
            core_concept_ids.append(concept_id)

    return {
        "by_concept_id": by_concept_id,
        "formula_ids_ordered": formula_ids_ordered,
        "definition_index": definition_index,
        "core_concept_ids": core_concept_ids,
    }


# ---------------------------------------------------------------------------
# 6. assessment_retrieval_index
# ---------------------------------------------------------------------------

def _build_assessment_retrieval_index(
    teaching_units: Dict[str, Any],
    navigation: Dict[str, Any],
) -> Dict[str, Any]:
    """Includes assessment_item_location for reverse lookup (spec §2)."""
    by_concept_id: Dict[str, List[str]] = {}
    by_difficulty: Dict[str, List[str]] = {"easy": [], "medium": [], "hard": []}
    by_bloom_level: Dict[str, List[str]] = defaultdict(list)
    by_type: Dict[str, List[str]] = defaultdict(list)
    by_provenance_tier: Dict[str, List[str]] = defaultdict(list)
    assessment_item_location: Dict[str, Dict[str, Any]] = {}

    for concept_id, tu in teaching_units.items():
        concept_item_ids: List[str] = []
        for is_practice, items in [(False, tu.get("assessments") or []),
                                    (True, tu.get("practice_questions") or [])]:
            for item in items:
                iid = str(item.get("item_id") or "")
                if not iid or iid == "":
                    continue
                concept_item_ids.append(iid)
                assessment_item_location[iid] = {
                    "concept_id": concept_id,
                    "is_practice": is_practice,
                }
                diff = str(item.get("difficulty") or "medium")
                by_difficulty.setdefault(diff, []).append(iid)
                bl = str(item.get("bloom_level") or "")
                if bl:
                    by_bloom_level[bl].append(iid)
                it = str(item.get("item_type") or "short_answer")
                by_type[it].append(iid)
                pt = str(item.get("provenance_tier") or "empty_placeholder")
                by_provenance_tier[pt].append(iid)
        if concept_item_ids:
            by_concept_id[concept_id] = concept_item_ids

    # chapter_test_item_ids from QuestionNavigation if available
    qnav = navigation.get("question_navigation") or {}
    chapter_test_item_ids = list(qnav.get("chapter_test_item_ids") or [])
    if not chapter_test_item_ids:
        # Fallback: take a mix from by_difficulty
        for diff in ("easy", "medium", "hard"):
            chapter_test_item_ids.extend((by_difficulty.get(diff) or [])[:3])

    return {
        "by_concept_id": by_concept_id,
        "by_difficulty": dict(by_difficulty),
        "by_bloom_level": dict(by_bloom_level),
        "by_type": dict(by_type),
        "by_provenance_tier": dict(by_provenance_tier),
        "chapter_test_item_ids": chapter_test_item_ids,
        "assessment_item_location": assessment_item_location,
    }


# ---------------------------------------------------------------------------
# 7. curriculum_traversal_index
# ---------------------------------------------------------------------------

def _build_curriculum_traversal_index(
    curriculum_graph: Dict[str, Any],
) -> Dict[str, Any]:
    """Spec §2. by_concept_id -> edge_ids; cross_chapter -> link_ids."""
    by_concept_id: Dict[str, List[str]] = defaultdict(list)
    cross_chapter: List[str] = []

    cg_nodes = curriculum_graph.get("nodes") or {}
    cg_edges = curriculum_graph.get("edges") or {}

    # Build concept_id -> node_id lookup
    concept_to_cg_node: Dict[str, str] = {}
    for nid, node in (cg_nodes.items() if isinstance(cg_nodes, dict) else []):
        cid = str(node.get("concept_id") or "")
        if cid:
            concept_to_cg_node[cid] = nid

    for edge_id, edge in (cg_edges.items() if isinstance(cg_edges, dict) else []):
        src_nid = str(edge.get("source_node_id") or "")
        tgt_nid = str(edge.get("target_node_id") or "")
        # Find concept_ids for source and target
        for nid, node in (cg_nodes.items() if isinstance(cg_nodes, dict) else []):
            if nid == src_nid:
                cid = str(node.get("concept_id") or "")
                if cid:
                    by_concept_id[cid].append(edge_id)

    for link in (curriculum_graph.get("cross_chapter_links") or []):
        lid = str(link.get("link_id") or "")
        if lid:
            cross_chapter.append(lid)

    return {
        "by_concept_id": dict(by_concept_id),
        "cross_chapter": cross_chapter,
    }
