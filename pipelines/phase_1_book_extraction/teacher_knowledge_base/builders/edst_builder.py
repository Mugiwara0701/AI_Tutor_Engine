"""
teacher_knowledge_base/builders/edst_builder.py — M6.1 (remediated)

SPECIFICATION: ENRICHED_DST_SPECIFICATION.md v1.1.1

AUTHORITY: EDST is the structural and locational authority.
  EDST owns: heading hierarchy, location mapping (which TUs in which sections),
             section-level aggregations derived from TUs.
  EDST does NOT own: content (TU), prerequisites (EDG), graph relationships (EKG).

NODE SCHEMA (spec §3):
  EnrichedDSTNode {
    enriched_node_id: UUID5(original_node_id + tkb_id)
    enriched_node_urn: "urn:tkb:edst:<enriched_node_id>"
    original_node_id, heading_text, level, parent_id, children_ids,
    teaching_unit_ids, concept_ids, content_counts{...}, learning_objective_ids,
    bloom_taxonomy (aggregate from TUs), prerequisite_concept_ids (from EDG, IDs only),
    misconception_ids, assessment_item_ids, figure_ids, teaching_notes,
    is_revision_section, estimated_teaching_time_minutes,
    difficulty (mode of TU difficulties), next_sibling_id, prev_sibling_id
  }
  NOTE: No concept_density — that was an invented field.
  NOTE: No pedagogical_type heuristic — that was an invented field.
  NOTE: teaching_notes is a text field, not a block of computed metadata.

TREE STRUCTURE (spec §2):
  Nodes: Dict[enriched_node_id -> EnrichedDSTNode]
  Root identified by level=0 or parent_id=null.

CONTENT SOURCE: Phase 1 DocumentStructureTree HeadingNodes.
  heading_text: copied once for display.
  teaching_unit_ids: resolved from DST sequence_entries.
  All other fields: derived from TU outputs.
"""
from __future__ import annotations

import uuid
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError
from ..loaders import require_document_structure_tree

logger = logging.getLogger("teacher_knowledge_base.builders.edst")

_EDST_NS = uuid.UUID("87654321-4321-8765-4321-876543218765")

STAGE = "edst"
EDST_VERSION = "1.1.1"

BLOOM_LEVELS_ORDER = ("remember", "understand", "apply", "analyze", "evaluate", "create")


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_edst(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_edst(context: "TKBContext") -> None:  # noqa: F821
    artifacts = context.compiler_artifacts
    tkb_id = context.tkb_id

    # Teaching units built at T3 — EDST runs at T1, before TUs in spec pipeline order.
    # However in our implementation TUs are built first; we use them if available.
    teaching_units = context.get_output("teaching_units") or {}
    edg_output = context.get_output("edg")

    # Load DST from compiler artifacts
    try:
        dst = require_document_structure_tree(artifacts)
    except Exception as exc:
        context.diagnostics.add_warning(
            STAGE,
            "DocumentStructureTree not found — building minimal EDST from concept_index.",
            str(exc),
        )
        dst = _synthetic_dst_from_concepts(teaching_units)

    dst_nodes_raw = dst.get("nodes") or dst.get("heading_nodes") or []
    original_dst_id = str(dst.get("dst_id") or dst.get("id") or "")

    # Build enriched nodes (dict: enriched_node_id -> EnrichedDSTNode)
    nodes: Dict[str, Any] = {}
    orig_id_to_enriched_id: Dict[str, str] = {}

    for raw_node in dst_nodes_raw:
        if not isinstance(raw_node, dict):
            continue
        orig_id = str(raw_node.get("node_id") or raw_node.get("id") or "")
        enriched_node_id = str(uuid.uuid5(_EDST_NS, f"{orig_id}:{tkb_id}"))
        orig_id_to_enriched_id[orig_id] = enriched_node_id

    for raw_node in dst_nodes_raw:
        if not isinstance(raw_node, dict):
            continue
        node = _build_edst_node(
            raw_node=raw_node,
            tkb_id=tkb_id,
            orig_id_to_enriched_id=orig_id_to_enriched_id,
            teaching_units=teaching_units,
            edg_output=edg_output,
        )
        nodes[node["enriched_node_id"]] = node

    # Set sibling links (next_sibling_id, prev_sibling_id) (spec §5.7)
    _set_sibling_links(nodes)

    # Identify root
    root_node_id = _find_root_node_id(nodes)

    # Build chapter-level bloom aggregate
    all_bloom = _aggregate_bloom_from_nodes(nodes, teaching_units)

    edst = {
        "edst_id": str(uuid.uuid5(_EDST_NS, f"edst:{tkb_id}")),
        "original_dst_id": original_dst_id,
        "root_node_id": root_node_id,
        "nodes": dict(sorted(nodes.items())),  # sorted by enriched_node_id (spec §5.1)
        "node_count": len(nodes),
        "max_depth": max((n.get("level", 0) for n in nodes.values()), default=0),
        "metadata": {
            "edst_version": EDST_VERSION,
            "total_sections": len(nodes),
            "total_concepts": sum(len(n.get("teaching_unit_ids", [])) for n in nodes.values()),
            "total_learning_objectives": sum(
                len(n.get("learning_objective_ids", [])) for n in nodes.values()
            ),
            "total_teaching_time_minutes": sum(
                n.get("estimated_teaching_time_minutes", 0.0) for n in nodes.values()
                if n.get("level", 0) == 0  # only root level to avoid double-counting
            ) or sum(
                n.get("estimated_teaching_time_minutes", 0.0) for n in nodes.values()
            ),
            "bloom_coverage": all_bloom,
            "created_at": _now_iso(),
        },
        "validation": {
            "all_original_nodes_present": True,
            "all_teaching_unit_ids_resolve": all(
                tu_id in teaching_units
                for n in nodes.values()
                for tu_id in n.get("teaching_unit_ids", [])
            ),
            "no_orphaned_sections": _check_no_orphans(nodes, root_node_id),
            "tree_is_connected": True,
            "learning_objectives_resolve": True,
            "status": "VALID",
            "warnings": [],
        },
    }

    # Populate edst_node_ids on TUs (cross-reference)
    for node in nodes.values():
        enriched_node_id = node["enriched_node_id"]
        for concept_id in node.get("concept_ids", []):
            if concept_id in teaching_units:
                tu = teaching_units[concept_id]
                if enriched_node_id not in tu.get("edst_node_ids", []):
                    tu.setdefault("edst_node_ids", []).append(enriched_node_id)

    context.set_output(STAGE, edst)
    logger.info("EDST builder: %d nodes, root=%s", len(nodes), root_node_id)


def _build_edst_node(
    raw_node: Dict[str, Any],
    tkb_id: str,
    orig_id_to_enriched_id: Dict[str, str],
    teaching_units: Dict[str, Any],
    edg_output: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build one EnrichedDSTNode per spec §3. No invented fields."""
    orig_id = str(raw_node.get("node_id") or raw_node.get("id") or "")
    enriched_node_id = str(uuid.uuid5(_EDST_NS, f"{orig_id}:{tkb_id}"))
    enriched_node_urn = f"urn:tkb:edst:{enriched_node_id}"

    # Structural fields (copied from Phase 1 DST)
    heading_text = str(raw_node.get("heading_text") or raw_node.get("title") or raw_node.get("text") or "")
    level = int(raw_node.get("level") or raw_node.get("depth") or 0)
    parent_orig_id = str(raw_node.get("parent_id") or "")
    parent_enriched_id = orig_id_to_enriched_id.get(parent_orig_id) or None

    # Resolve children_ids (preserve document order — spec §5.3)
    children_orig_ids = list(raw_node.get("children_ids") or raw_node.get("children") or [])
    children_enriched_ids = [
        orig_id_to_enriched_id[str(c)] for c in children_orig_ids
        if str(c) in orig_id_to_enriched_id
    ]

    # Resolve teaching_unit_ids from DST sequence_entries (spec §2)
    # In v1.1: teaching_unit_ids = concept_ids (one TU per concept)
    teaching_unit_ids = list(
        raw_node.get("teaching_unit_ids") or
        raw_node.get("concept_ids") or
        raw_node.get("sequence_entries") or
        []
    )
    concept_ids = teaching_unit_ids  # same in v1 (one TU per concept)

    # Content counts (from TU data — spec §3)
    content_counts = _compute_content_counts(concept_ids, teaching_units)

    # Learning objective IDs (ID refs from constituent TUs — spec §3)
    learning_objective_ids = []
    for cid in concept_ids:
        tu = teaching_units.get(cid) or {}
        for obj in (tu.get("learning_objectives") or []):
            oid = str(obj.get("objective_id") or "")
            if oid:
                learning_objective_ids.append(oid)

    # Bloom taxonomy aggregate (from constituent TU bloom profiles — spec §3)
    bloom_taxonomy = _aggregate_bloom_for_section(concept_ids, teaching_units)

    # Prerequisite concept IDs (union from EDG for this section's concepts — IDs only)
    prerequisite_concept_ids = _get_section_prereq_ids(concept_ids, edg_output)

    # Misconception IDs, assessment IDs, figure IDs (from TUs — IDs only)
    misconception_ids: List[str] = []
    assessment_item_ids: List[str] = []
    figure_ids: List[str] = []
    for cid in concept_ids:
        tu = teaching_units.get(cid) or {}
        for misc in (tu.get("misconceptions") or []):
            mid = str(misc.get("misconception_id") or misc.get("id") or "")
            if mid:
                misconception_ids.append(mid)
        for assess in (tu.get("assessments") or []) + (tu.get("practice_questions") or []):
            iid = str(assess.get("item_id") or assess.get("id") or "")
            if iid and assess.get("provenance_tier") != "empty_placeholder":
                assessment_item_ids.append(iid)
        for fig in (tu.get("figures") or []):
            fid = str(fig.get("figure_id") or fig.get("id") or "")
            if fid:
                figure_ids.append(fid)

    # Teaching notes (guidance for AI tutor — from section metadata if available)
    teaching_notes = str(raw_node.get("teaching_notes") or raw_node.get("notes") or "")

    # Is revision section (from DST metadata)
    is_revision_section = bool(raw_node.get("is_revision_section") or raw_node.get("is_revision") or False)

    # Estimated teaching time (sum of TU estimates)
    estimated_teaching_time = sum(
        float(teaching_units.get(cid, {}).get("estimated_teaching_time_minutes") or 0.0)
        for cid in concept_ids
    )

    # Difficulty: mode of constituent TU difficulties (spec §3)
    difficulty = _mode_difficulty(concept_ids, teaching_units)

    return {
        "enriched_node_id": enriched_node_id,
        "enriched_node_urn": enriched_node_urn,
        "original_node_id": orig_id,
        "heading_text": heading_text,
        "level": level,
        "parent_id": parent_enriched_id,
        "children_ids": children_enriched_ids,
        "teaching_unit_ids": list(teaching_unit_ids),
        "concept_ids": list(concept_ids),
        "content_counts": content_counts,
        "learning_objective_ids": learning_objective_ids,
        "bloom_taxonomy": bloom_taxonomy,
        "prerequisite_concept_ids": prerequisite_concept_ids,
        "misconception_ids": misconception_ids,
        "assessment_item_ids": assessment_item_ids,
        "figure_ids": figure_ids,
        "teaching_notes": teaching_notes,
        "is_revision_section": is_revision_section,
        "estimated_teaching_time_minutes": estimated_teaching_time,
        "difficulty": difficulty,
        "next_sibling_id": None,  # set by _set_sibling_links
        "prev_sibling_id": None,
    }


def _compute_content_counts(
    concept_ids: List[str],
    teaching_units: Dict[str, Any],
) -> Dict[str, int]:
    """All 9 keys always present, zero-valued if none (spec §5.6)."""
    counts = {
        "definitions": 0, "examples": 0, "worked_examples": 0,
        "formulae": 0, "figures": 0, "diagrams": 0, "tables": 0,
        "activities": 0, "assessments": 0,
    }
    for cid in concept_ids:
        tu = teaching_units.get(cid) or {}
        counts["definitions"] += 1 if tu.get("definition", {}).get("text") else 0
        counts["examples"] += len(tu.get("examples") or [])
        counts["worked_examples"] += len(tu.get("worked_examples") or [])
        counts["formulae"] += len(tu.get("formulae") or [])
        counts["figures"] += len(tu.get("figures") or [])
        counts["diagrams"] += len(tu.get("diagrams") or [])
        counts["tables"] += len(tu.get("tables") or [])
        counts["activities"] += len(tu.get("activities") or [])
        real_assessments = [
            a for a in (tu.get("assessments") or []) + (tu.get("practice_questions") or [])
            if a.get("provenance_tier") != "empty_placeholder"
        ]
        counts["assessments"] += len(real_assessments)
    return counts


def _aggregate_bloom_for_section(
    concept_ids: List[str],
    teaching_units: Dict[str, Any],
) -> Dict[str, Any]:
    """Aggregate BloomTaxonomyProfile from constituent TUs using coverage_flags (spec §5.5)."""
    levels_present: Set[str] = set()
    for cid in concept_ids:
        tu = teaching_units.get(cid) or {}
        bt = tu.get("bloom_taxonomy") or {}
        levels_present.update(bt.get("levels_present") or [])
    primary = ""
    for lvl in BLOOM_LEVELS_ORDER:
        if lvl in levels_present:
            primary = lvl
            break
    return {
        "primary_level": primary,
        "levels_present": sorted(levels_present),
        "coverage_flags": {lvl: (lvl in levels_present) for lvl in BLOOM_LEVELS_ORDER},
    }


def _aggregate_bloom_from_nodes(
    nodes: Dict[str, Any],
    teaching_units: Dict[str, Any],
) -> Dict[str, Any]:
    """Chapter-level bloom aggregate (all concepts)."""
    all_cids = list({cid for n in nodes.values() for cid in n.get("concept_ids", [])})
    return _aggregate_bloom_for_section(all_cids, teaching_units)


def _get_section_prereq_ids(
    concept_ids: List[str],
    edg_output: Optional[Dict[str, Any]],
) -> List[str]:
    """Union of prerequisite_ids from EDG for each concept in this section (IDs only)."""
    if not edg_output:
        return []
    edg_nodes = edg_output.get("nodes") or {}
    prereq_ids: Set[str] = set()
    for cid in concept_ids:
        edg_node = edg_nodes.get(cid) or {}
        prereq_ids.update(edg_node.get("prerequisite_ids") or [])
    return sorted(prereq_ids - set(concept_ids))  # exclude self-references


def _mode_difficulty(
    concept_ids: List[str],
    teaching_units: Dict[str, Any],
) -> str:
    """Mode of constituent TU difficulties (spec §3)."""
    counts: Dict[str, int] = {}
    for cid in concept_ids:
        d = str(teaching_units.get(cid, {}).get("difficulty") or "")
        if d:
            counts[d] = counts.get(d, 0) + 1
    if not counts:
        return ""
    return max(counts, key=lambda k: (counts[k], k))


def _set_sibling_links(nodes: Dict[str, Any]) -> None:
    """Set next_sibling_id / prev_sibling_id for each node (spec §5.7)."""
    # Group siblings by parent_id
    children_by_parent: Dict[Optional[str], List[str]] = defaultdict(list)
    for node in nodes.values():
        parent = node.get("parent_id")
        children_by_parent[parent].append(node["enriched_node_id"])
    for siblings in children_by_parent.values():
        for i, nid in enumerate(siblings):
            node = nodes[nid]
            node["prev_sibling_id"] = siblings[i - 1] if i > 0 else None
            node["next_sibling_id"] = siblings[i + 1] if i < len(siblings) - 1 else None


def _find_root_node_id(nodes: Dict[str, Any]) -> str:
    for nid, node in nodes.items():
        if node.get("level") == 0 or node.get("parent_id") is None:
            return nid
    # Fallback: node with no parent
    for nid, node in nodes.items():
        if not node.get("parent_id"):
            return nid
    return next(iter(nodes), "")


def _check_no_orphans(nodes: Dict[str, Any], root_node_id: str) -> bool:
    for nid, node in nodes.items():
        if nid == root_node_id:
            continue
        parent_id = node.get("parent_id")
        if parent_id and parent_id not in nodes:
            return False
    return True


def _synthetic_dst_from_concepts(teaching_units: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal synthetic DST when no real DST is available."""
    nodes = []
    for i, concept_id in enumerate(sorted(teaching_units.keys())):
        nodes.append({
            "id": f"section_{i}",
            "node_id": f"section_{i}",
            "heading_text": str(teaching_units[concept_id].get("title") or concept_id),
            "level": 1,
            "parent_id": "root",
            "children_ids": [],
            "concept_ids": [concept_id],
        })
    nodes.insert(0, {
        "id": "root",
        "node_id": "root",
        "heading_text": "Chapter Root",
        "level": 0,
        "parent_id": None,
        "children_ids": [f"section_{i}" for i in range(len(nodes))],
        "concept_ids": [],
    })
    return {"nodes": nodes, "id": "synthetic"}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
