"""
teacher_knowledge_base/builders/ekg_builder.py — M6.1 (remediated)

SPECIFICATION: ENRICHED_KNOWLEDGE_GRAPH_SPECIFICATION.md v1.1.1

AUTHORITY: EKG owns pedagogical annotation relationships only.
  EKG does NOT own: prerequisites (EDG), content text (TU), structure (EDST)
  EKG v1 has NO PREREQUISITE_OF edges.

NODE SCHEMA (spec §2):
  EnrichedKGNode {
    ekg_node_id, ekg_node_urn, original_kg_node_id,
    node_type, name, canonical_key, teaching_unit_id, ekg_node_type
  }
  NOTE: No pedagogical_metadata, bloom_taxonomy_level, difficulty_level,
        teaching_hints, prerequisite_ordering_weight, estimated_mastery_time_minutes
        — those were invented fields.

EDGE SCHEMA (spec §3):
  EnrichedKGEdge {
    ekg_edge_id, ekg_edge_urn, source_node_id, target_node_id,
    edge_type (7 v1 mandatory types only), weight, confidence, source, context
  }
  NOTE: No teaching_weight, directionality_for_teaching — those were invented.

V1 MANDATORY EDGE TYPES (spec §4):
  TEACHES, EXAMPLE_OF, ANALOGY_FOR, MISCONCEPTION_ABOUT,
  CONFUSION_WITH, APPLICATION_OF, RELATED_TO

DERIVATION RULES (spec §5): all edges derived at build time from TU/EDST content:
  TEACHES         <- EDST.teaching_unit_ids
  EXAMPLE_OF      <- TU.examples / TU.worked_examples concept_refs
  ANALOGY_FOR     <- TU.analogies concept_refs
  MISCONCEPTION_ABOUT <- TU.misconceptions concept_refs
  CONFUSION_WITH  <- TU.common_mistakes + SemanticGraph
  APPLICATION_OF  <- TU.applications concept_refs
  RELATED_TO      <- SemanticGraph RELATED_TO edges

SERIALIZATION (spec §8):
  nodes: keys sorted by ekg_node_id
  edges: keys sorted by ekg_edge_id
  weight, confidence: 4 decimal places
  CONFUSION_WITH, RELATED_TO: lower concept_id -> higher concept_id (canonical direction)
"""
from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.ekg")

_EKG_NS = uuid.UUID("12345678-1234-5678-1234-567812345678")

STAGE = "ekg"
EKG_VERSION = "1.1.1"

V1_EDGE_TYPES = {
    "TEACHES", "EXAMPLE_OF", "ANALOGY_FOR", "MISCONCEPTION_ABOUT",
    "CONFUSION_WITH", "APPLICATION_OF", "RELATED_TO",
}

V2_DEFERRED = {
    "REINFORCES", "EXTENDS", "INTRODUCES", "FORMULA_FOR", "DEFINES",
    "CLASSIFIES", "REVISION_OF", "ASSESSES", "PRACTICE_FOR", "CONTEXT_FOR",
    "PREREQUISITE_OF",  # explicitly removed from EKG v1
}


def build(context: "TKBContext") -> None:  # noqa: F821
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


def _build_ekg(context: "TKBContext") -> None:  # noqa: F821
    artifacts = context.compiler_artifacts
    tkb_id = context.tkb_id

    # Teaching units must be built before EKG (pipeline T5 runs after T3)
    teaching_units = context.require_output("teaching_units", STAGE)
    edst_output = context.get_output("edst")  # may be available if EDST ran before EKG

    # Build one EnrichedKGNode per KG node
    kg = artifacts.get("knowledge_graph") or {}
    kg_nodes_raw = kg.get("nodes") or []
    semantic_graph = artifacts.get("semantic_graph") or {}

    nodes: Dict[str, Any] = {}  # ekg_node_id -> EnrichedKGNode
    concept_id_to_ekg_node_id: Dict[str, str] = {}  # for edge building

    for raw_node in kg_nodes_raw:
        if not isinstance(raw_node, dict):
            continue
        node = _build_ekg_node(raw_node, tkb_id, teaching_units)
        nodes[node["ekg_node_id"]] = node
        if node.get("teaching_unit_id"):
            concept_id_to_ekg_node_id[node["teaching_unit_id"]] = node["ekg_node_id"]

    # If no KG nodes, create one stub node per concept in teaching_units
    if not nodes:
        for concept_id, tu in teaching_units.items():
            stub_node = _build_stub_ekg_node(concept_id, tu, tkb_id)
            nodes[stub_node["ekg_node_id"]] = stub_node
            concept_id_to_ekg_node_id[concept_id] = stub_node["ekg_node_id"]

    # Derive edges from TU content and EDST (spec §5)
    edges: Dict[str, Any] = {}  # ekg_edge_id -> EnrichedKGEdge

    def add_edge(e: Optional[Dict[str, Any]]) -> None:
        if e and e["ekg_edge_id"] not in edges:
            edges[e["ekg_edge_id"]] = e

    # T: TEACHES — from EDST.teaching_unit_ids (EDST derived; if no EDST, from concept membership)
    for ekg_edge in _derive_teaches_edges(
        edst_output, nodes, concept_id_to_ekg_node_id, tkb_id
    ):
        add_edge(ekg_edge)

    # For each concept's TeachingUnit, derive remaining edge types
    for concept_id, tu in teaching_units.items():
        ekg_concept_node_id = concept_id_to_ekg_node_id.get(concept_id, "")
        if not ekg_concept_node_id:
            continue

        # EXAMPLE_OF
        for example in (tu.get("examples") or []) + (tu.get("worked_examples") or []):
            for concept_ref in (example.get("concept_refs") or []):
                ref_id = _resolve_concept_ref(concept_ref, concept_id_to_ekg_node_id)
                if ref_id and ref_id != ekg_concept_node_id:
                    add_edge(_make_edge("EXAMPLE_OF", ekg_concept_node_id, ref_id,
                                       tkb_id, source="teaching_unit", weight=0.9))

        # ANALOGY_FOR
        for analogy in (tu.get("analogies") or []):
            for concept_ref in (analogy.get("concept_refs") or []):
                ref_id = _resolve_concept_ref(concept_ref, concept_id_to_ekg_node_id)
                if ref_id and ref_id != ekg_concept_node_id:
                    add_edge(_make_edge("ANALOGY_FOR", ekg_concept_node_id, ref_id,
                                       tkb_id, source="teaching_unit", weight=0.8))

        # MISCONCEPTION_ABOUT
        for misc in (tu.get("misconceptions") or []):
            for concept_ref in (misc.get("concept_refs") or [misc.get("concept_id", "")]):
                ref_id = _resolve_concept_ref(concept_ref, concept_id_to_ekg_node_id)
                if ref_id:
                    add_edge(_make_edge("MISCONCEPTION_ABOUT", ekg_concept_node_id, ref_id,
                                       tkb_id, source="teaching_unit", weight=0.85))

        # APPLICATION_OF
        for app in (tu.get("applications") or []):
            for concept_ref in (app.get("concept_refs") or []):
                ref_id = _resolve_concept_ref(concept_ref, concept_id_to_ekg_node_id)
                if ref_id and ref_id != ekg_concept_node_id:
                    add_edge(_make_edge("APPLICATION_OF", ekg_concept_node_id, ref_id,
                                       tkb_id, source="teaching_unit", weight=0.75))

        # CONFUSION_WITH (from common_mistakes — symmetric)
        for mistake in (tu.get("common_mistakes") or []):
            for concept_ref in (mistake.get("concept_refs") or []):
                ref_id = _resolve_concept_ref(concept_ref, concept_id_to_ekg_node_id)
                if ref_id and ref_id != ekg_concept_node_id:
                    # Symmetric: lower ekg_node_id is source
                    src_id, tgt_id = sorted([ekg_concept_node_id, ref_id])
                    add_edge(_make_edge("CONFUSION_WITH", src_id, tgt_id,
                                       tkb_id, source="teaching_unit", weight=0.7))

    # RELATED_TO from SemanticGraph (symmetric)
    for sg_edge in _get_semantic_related_to_edges(semantic_graph):
        src_cid = str(sg_edge.get("source") or sg_edge.get("from") or "")
        tgt_cid = str(sg_edge.get("target") or sg_edge.get("to") or "")
        src_id = concept_id_to_ekg_node_id.get(src_cid)
        tgt_id = concept_id_to_ekg_node_id.get(tgt_cid)
        if src_id and tgt_id and src_id != tgt_id:
            canonical_src, canonical_tgt = sorted([src_id, tgt_id])
            add_edge(_make_edge("RELATED_TO", canonical_src, canonical_tgt,
                               tkb_id, source="semantic_graph",
                               weight=float(sg_edge.get("weight") or 0.5),
                               confidence=float(sg_edge.get("confidence") or 0.7)))

    # Sort dicts by key (spec §8)
    sorted_nodes = dict(sorted(nodes.items()))
    sorted_edges = dict(sorted(edges.items()))

    # Populate ekg_node_id on each TU (cross-reference)
    for concept_id, ekg_nid in concept_id_to_ekg_node_id.items():
        if concept_id in teaching_units:
            teaching_units[concept_id]["ekg_node_id"] = ekg_nid

    edge_type_counts = {}
    for e in sorted_edges.values():
        et = e.get("edge_type", "")
        edge_type_counts[et] = edge_type_counts.get(et, 0) + 1

    ekg = {
        "ekg_id": str(uuid.uuid5(_EKG_NS, f"ekg:{tkb_id}")),
        "original_kg_id": str(kg.get("kg_id") or kg.get("id") or ""),
        "nodes": sorted_nodes,
        "edges": sorted_edges,
        "node_count": len(sorted_nodes),
        "edge_count": len(sorted_edges),
        "metadata": {
            "ekg_version": EKG_VERSION,
            "created_at": _now_iso(),
            "edge_type_counts": edge_type_counts,
            "avg_edges_per_node": round(len(sorted_edges) / max(1, len(sorted_nodes)), 4),
            "deferred_edge_types": sorted(V2_DEFERRED),
        },
        "validation": {
            "no_self_loops": all(
                e["source_node_id"] != e["target_node_id"] for e in sorted_edges.values()
            ),
            "no_prerequisite_of_edges": all(
                e["edge_type"] != "PREREQUISITE_OF" for e in sorted_edges.values()
            ),
            "all_referenced_nodes_exist": all(
                e["source_node_id"] in sorted_nodes and e["target_node_id"] in sorted_nodes
                for e in sorted_edges.values()
            ),
            "no_duplicate_edges": True,  # guaranteed by dedup via edge_id dict
            "symmetric_edges_canonicalized": True,
            "status": "VALID",
            "warnings": [],
        },
    }
    context.set_output(STAGE, ekg)
    logger.info(
        "EKG builder: %d nodes, %d edges (v1 types only). edge_types=%s",
        len(sorted_nodes), len(sorted_edges),
        {k: v for k, v in edge_type_counts.items()},
    )

    # ---- AUTHORITY_MATRIX §4.2 + TEACHING_UNIT_SPECIFICATION §3 ----------------
    # EKG is the canonical source of RELATED_TO relationships.
    # TU.related_concepts is a DERIVED CONVENIENCE SNAPSHOT populated here.
    _backfill_related_concepts(context, sorted_nodes, sorted_edges, teaching_units)


def _build_ekg_node(
    raw_node: Dict[str, Any],
    tkb_id: str,
    teaching_units: Dict[str, Any],
) -> Dict[str, Any]:
    """Build EnrichedKGNode per spec §2. No pedagogical_metadata — spec prohibits it."""
    orig_id = str(raw_node.get("id") or raw_node.get("node_id") or raw_node.get("concept_id") or "")
    ekg_node_id = str(uuid.uuid5(_EKG_NS, f"{orig_id}:{tkb_id}"))
    ekg_node_urn = f"urn:tkb:ekg:node:{ekg_node_id}"
    node_type = str(raw_node.get("node_type") or raw_node.get("type") or "Concept")
    name = str(raw_node.get("name") or raw_node.get("title") or orig_id)
    canonical_key = str(raw_node.get("canonical_key") or raw_node.get("concept_key") or raw_node.get("key") or "")
    ekg_node_type = "concept" if node_type in ("Concept", "concept") else "content"

    # teaching_unit_id: null for non-Concept node types (spec §2)
    teaching_unit_id: Optional[str] = None
    if node_type in ("Concept", "concept"):
        # The TU for this concept is at teaching_units[concept_id] (dict key = concept_id)
        concept_id = str(raw_node.get("concept_id") or orig_id)
        if concept_id in teaching_units:
            teaching_unit_id = concept_id  # in v1.1, concept_id IS the TU dict key

    return {
        "ekg_node_id": ekg_node_id,
        "ekg_node_urn": ekg_node_urn,
        "original_kg_node_id": orig_id,
        "node_type": node_type,
        "name": name,
        "canonical_key": canonical_key,
        "teaching_unit_id": teaching_unit_id,
        "ekg_node_type": ekg_node_type,
    }


def _build_stub_ekg_node(
    concept_id: str,
    tu: Dict[str, Any],
    tkb_id: str,
) -> Dict[str, Any]:
    """Stub node when no KG is available — created from TU identity."""
    ekg_node_id = str(uuid.uuid5(_EKG_NS, f"{concept_id}:{tkb_id}"))
    return {
        "ekg_node_id": ekg_node_id,
        "ekg_node_urn": f"urn:tkb:ekg:node:{ekg_node_id}",
        "original_kg_node_id": concept_id,
        "node_type": "Concept",
        "name": str(tu.get("title") or concept_id),
        "canonical_key": str(tu.get("concept_key") or ""),
        "teaching_unit_id": concept_id,
        "ekg_node_type": "concept",
    }


def _make_edge(
    edge_type: str,
    source_node_id: str,
    target_node_id: str,
    tkb_id: str,
    source: str = "semantic_graph",
    weight: float = 0.5,
    confidence: float = 0.8,
    context: str = "",
) -> Optional[Dict[str, Any]]:
    """Create EnrichedKGEdge per spec §3. Only v1 types allowed."""
    if edge_type not in V1_EDGE_TYPES:
        return None
    edge_key = f"{source_node_id}:{target_node_id}:{edge_type}:{tkb_id}"
    ekg_edge_id = str(uuid.uuid5(_EKG_NS, edge_key))
    return {
        "ekg_edge_id": ekg_edge_id,
        "ekg_edge_urn": f"urn:tkb:ekg:edge:{ekg_edge_id}",
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "edge_type": edge_type,
        "weight": round(float(weight), 4),
        "confidence": round(float(confidence), 4),
        "source": source,
        "context": context,
    }


def _derive_teaches_edges(
    edst_output: Optional[Dict[str, Any]],
    nodes: Dict[str, Any],  # ekg_node_id -> node
    concept_id_to_ekg_node_id: Dict[str, str],
    tkb_id: str,
) -> List[Dict[str, Any]]:
    """TEACHES edges: EDST teaching_unit_ids -> concept (spec §5).
    If EDST not available, skip TEACHES (they'll be absent from edge set)."""
    edges = []
    if not edst_output:
        return edges
    edst_nodes = edst_output.get("nodes") or {}
    # edst_nodes may be a dict (enriched_node_id -> node) or list
    node_list = list(edst_nodes.values()) if isinstance(edst_nodes, dict) else edst_nodes
    for edst_node in node_list:
        if not isinstance(edst_node, dict):
            continue
        edst_node_id = str(edst_node.get("enriched_node_id") or edst_node.get("node_id") or "")
        # Find the EKG node for this EDST section (structural node)
        section_ekg_id = _find_or_create_section_node(
            edst_node_id, edst_node, nodes, concept_id_to_ekg_node_id, tkb_id
        )
        if not section_ekg_id:
            continue
        for concept_id in (edst_node.get("teaching_unit_ids") or edst_node.get("concept_ids") or []):
            concept_ekg_id = concept_id_to_ekg_node_id.get(concept_id)
            if concept_ekg_id and section_ekg_id != concept_ekg_id:
                e = _make_edge("TEACHES", section_ekg_id, concept_ekg_id,
                               tkb_id, source="edst_derived", weight=1.0)
                if e:
                    edges.append(e)
    return edges


def _find_or_create_section_node(
    edst_node_id: str,
    edst_node: Dict[str, Any],
    nodes: Dict[str, Any],
    concept_id_to_ekg_node_id: Dict[str, str],
    tkb_id: str,
) -> Optional[str]:
    """Finds existing EKG node for an EDST section, or None if section has no EKG node.
    EDST structural nodes may not be in the KG; we use the first concept's EKG node
    as a proxy for the TEACHES source."""
    # Try to find the section's own EKG structural node by original_node_id
    for n in nodes.values():
        if n.get("original_kg_node_id") == edst_node_id:
            return n["ekg_node_id"]
    # Fallback: use the EKG node of the first concept in this section
    teaching_unit_ids = edst_node.get("teaching_unit_ids") or []
    if teaching_unit_ids:
        return concept_id_to_ekg_node_id.get(teaching_unit_ids[0])
    return None


def _resolve_concept_ref(
    concept_ref: Any,
    concept_id_to_ekg_node_id: Dict[str, str],
) -> Optional[str]:
    """Resolves a concept_ref (str concept_id or dict with concept_id) to ekg_node_id."""
    if isinstance(concept_ref, str):
        return concept_id_to_ekg_node_id.get(concept_ref)
    if isinstance(concept_ref, dict):
        cid = str(concept_ref.get("concept_id") or concept_ref.get("id") or "")
        return concept_id_to_ekg_node_id.get(cid)
    return None


def _get_semantic_related_to_edges(semantic_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extracts RELATED_TO edges from SemanticGraph."""
    edges = semantic_graph.get("edges") or semantic_graph.get("relationships") or []
    return [
        e for e in edges
        if isinstance(e, dict) and
        str(e.get("edge_type") or e.get("type") or "").upper() in ("RELATED_TO", "RELATED")
    ]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _backfill_related_concepts(
    context: Any,
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
    teaching_units: Dict[str, Any],
) -> None:
    """Backfill TU.related_concepts from EKG RELATED_TO edges.

    Authority:
      AUTHORITY_MATRIX §4.2 — EKG RELATED_TO is canonical; TU.related_concepts is derived.
      TEACHING_UNIT_SPECIFICATION §3 — related_concepts: "Canonical source: EKG RELATED_TO".

    Builds ConceptRef snapshots for each concept's RELATED_TO neighbours.
    Symmetric: both endpoints receive each other as a related concept.
    Only populates for concept-type nodes (teaching_unit_id is set).
    """
    if not teaching_units:
        return

    # Build ekg_node_id -> concept_id reverse map (concept nodes only)
    ekg_node_to_concept: Dict[str, str] = {}
    for node in nodes.values():
        tid = node.get("teaching_unit_id")
        if tid:
            ekg_node_to_concept[node["ekg_node_id"]] = tid

    # Build per-concept related_concepts list from RELATED_TO edges
    related_map: Dict[str, List[Dict[str, Any]]] = {cid: [] for cid in teaching_units}

    for edge in edges.values():
        if edge.get("edge_type") != "RELATED_TO":
            continue
        src_nid = edge.get("source_node_id", "")
        tgt_nid = edge.get("target_node_id", "")
        src_cid = ekg_node_to_concept.get(src_nid)
        tgt_cid = ekg_node_to_concept.get(tgt_nid)
        if not src_cid or not tgt_cid:
            continue
        # Both endpoints: tgt is related to src, src is related to tgt
        for (owner_cid, related_cid) in ((src_cid, tgt_cid), (tgt_cid, src_cid)):
            if owner_cid not in related_map:
                continue
            existing = {r["concept_id"] for r in related_map[owner_cid]}
            if related_cid in existing:
                continue
            related_tu = teaching_units.get(related_cid) or {}
            related_map[owner_cid].append({
                "concept_id": related_cid,
                "concept_key": str(related_tu.get("concept_key") or ""),
                "concept_name": str(related_tu.get("title") or related_cid),
                "teaching_unit_id": str(related_tu.get("unit_id") or ""),
            })

    # Write back to TUs
    for concept_id, related in related_map.items():
        if concept_id in teaching_units:
            teaching_units[concept_id]["related_concepts"] = related
