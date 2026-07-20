"""
teacher_knowledge_base/builders/edst_builder.py — M6.1: Enriched Document
Structure Tree (EDST) builder.

SPECIFICATION: ENRICHED_DST_SPECIFICATION.md

SCOPE: The EDST enriches the Phase A DocumentStructureTree with teaching
metadata — pedagogical annotations, concept density, teaching time estimates,
prerequisite pointers, and cross-reference links — without modifying the
source DST. The original DST structure is preserved verbatim; enrichment
adds new fields alongside existing ones.

WHAT THIS DOES NOT DO (per M6.1 scope §):
  - Does not re-run Phase A DST extraction.
  - Does not modify the Chapter JSON structure.
  - Does not implement Phase 2 runtime queries.

DETERMINISM: all IDs derived from content using UUID5. No random UUIDs.
Nodes sorted by chapter then by position_index for stable output.
"""
from __future__ import annotations

import hashlib
import json
import uuid
import logging
from typing import Any, Dict, List, Optional

from ..exceptions import TKBBuilderError
from ..loaders import require_document_structure_tree, extract_concepts

logger = logging.getLogger("teacher_knowledge_base.builders.edst")

EDST_VERSION = "M6.1.0"
_EDST_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

STAGE = "edst"


def build(context: "TKBContext") -> None:  # noqa: F821
    """Main entry point. Reads from context.compiler_artifacts, writes
    output to context via context.set_output('edst', ...)."""
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


def _build_edst(context: "TKBContext") -> None:
    artifacts = context.compiler_artifacts
    concepts = extract_concepts(artifacts)

    # Load DST — raises TKBLoaderError if absent
    try:
        dst = require_document_structure_tree(artifacts)
    except Exception as exc:
        context.diagnostics.add_warning(
            STAGE,
            "DocumentStructureTree not found — building minimal EDST from concept list.",
            str(exc),
        )
        dst = _synthetic_dst_from_concepts(concepts, context.metadata.chapter_ids)

    nodes = _enrich_dst_nodes(dst, concepts, context)
    enrichment_metadata = _build_enrichment_metadata(nodes, concepts)

    edst = {
        "version": EDST_VERSION,
        "enrichment_applied": True,
        "source": "DocumentStructureTree",
        "nodes": nodes,
        "enrichment_metadata": enrichment_metadata,
    }
    context.set_output(STAGE, edst)
    logger.info(
        "EDST builder: produced %d enriched nodes from %d DST source nodes.",
        len(nodes), len(dst.get("nodes") or dst.get("chapters") or []),
    )


def _enrich_dst_nodes(
    dst: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    context: "TKBContext",
) -> List[Dict[str, Any]]:
    """Enriches each DST node with teaching metadata. Returns stable-sorted list."""
    source_nodes = (
        dst.get("nodes")
        or dst.get("chapters")
        or dst.get("sections")
        or []
    )

    # Build a quick lookup: concept_id -> concept dict
    concept_lookup: Dict[str, Dict[str, Any]] = {}
    for c in concepts:
        if isinstance(c, dict):
            cid = c.get("id") or c.get("concept_id") or c.get("name", "")
            if cid:
                concept_lookup[str(cid)] = c

    enriched: List[Dict[str, Any]] = []
    for node in source_nodes:
        if not isinstance(node, dict):
            continue
        enriched.append(_enrich_node(node, concept_lookup, context.metadata.artifact_id))

    # Stable sort: by chapter_number then position_index
    enriched.sort(
        key=lambda n: (
            n.get("chapter_number", 0),
            n.get("position_index", 0),
            n.get("id", ""),
        )
    )
    return enriched


def _enrich_node(
    node: Dict[str, Any],
    concept_lookup: Dict[str, Dict[str, Any]],
    artifact_id: str,
) -> Dict[str, Any]:
    """Produces one enriched DST node. Never modifies the source node."""
    # Deterministic node ID
    node_key = json.dumps(
        {
            "chapter": node.get("chapter_number") or node.get("chapter"),
            "title": node.get("title") or node.get("name", ""),
            "position": node.get("position_index", 0),
        },
        sort_keys=True, separators=(",", ":"),
    )
    enriched_id = str(uuid.uuid5(_EDST_NAMESPACE, f"{artifact_id}:{node_key}"))

    # Concepts referenced in this node
    node_concept_ids = _extract_concept_refs(node)
    node_concepts = [concept_lookup[c] for c in node_concept_ids if c in concept_lookup]
    concept_density = len(node_concepts)

    # Teaching time estimate: 5 min per concept baseline, min 10 min per node
    teaching_time_minutes = max(10, concept_density * 5)

    return {
        **node,  # Preserve all original DST fields verbatim
        "enriched_id": enriched_id,
        "enrichment_version": EDST_VERSION,
        "teaching_metadata": {
            "concept_ids": node_concept_ids,
            "concept_density": concept_density,
            "teaching_time_estimate_minutes": teaching_time_minutes,
            "pedagogical_type": _classify_node_type(node),
            "prerequisite_concept_ids": _extract_prerequisite_ids(node_concepts),
            "cross_references": [],  # populated by EKG builder via runtime index
        },
    }


def _extract_concept_refs(node: Dict[str, Any]) -> List[str]:
    """Extracts concept IDs referenced in a DST node from any field name
    this codebase uses for concept references."""
    refs = []
    for key in ("concept_ids", "concepts", "concept_list", "related_concepts"):
        val = node.get(key) or []
        if isinstance(val, list):
            refs.extend(str(v) for v in val if v)
        elif isinstance(val, str) and val:
            refs.append(val)
    return sorted(set(refs))


def _extract_prerequisite_ids(concepts: List[Dict[str, Any]]) -> List[str]:
    """Collects prerequisite concept IDs from a list of concept dicts."""
    prereqs: List[str] = []
    for c in concepts:
        for key in ("prerequisites", "prerequisite_ids", "depends_on"):
            val = c.get(key) or []
            if isinstance(val, list):
                prereqs.extend(str(v) for v in val if v)
    return sorted(set(prereqs))


def _classify_node_type(node: Dict[str, Any]) -> str:
    """Heuristic node type classification from DST node fields."""
    node_type = str(node.get("type") or node.get("node_type") or "").lower()
    title = str(node.get("title") or node.get("name") or "").lower()
    if "chapter" in node_type or "chapter" in title:
        return "chapter"
    if "section" in node_type:
        return "section"
    if "exercise" in node_type or "exercise" in title or "problem" in title:
        return "exercise"
    if "summary" in node_type or "summary" in title:
        return "summary"
    return "content"


def _build_enrichment_metadata(
    nodes: List[Dict[str, Any]],
    concepts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_concepts_referenced = len(
        set(cid for n in nodes for cid in n.get("teaching_metadata", {}).get("concept_ids", []))
    )
    return {
        "total_enriched_nodes": len(nodes),
        "total_concepts_referenced": total_concepts_referenced,
        "total_source_concepts": len(concepts),
        "node_types": _count_node_types(nodes),
        "enrichment_strategy": "concept_density+teaching_time",
        "version": EDST_VERSION,
    }


def _count_node_types(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for n in nodes:
        t = n.get("teaching_metadata", {}).get("pedagogical_type", "content")
        counts[t] = counts.get(t, 0) + 1
    return counts


def _synthetic_dst_from_concepts(
    concepts: List[Dict[str, Any]],
    chapter_ids: List[str],
) -> Dict[str, Any]:
    """Builds a minimal synthetic DST from the concept list when no real
    DST is available. Used as fallback — records a warning, not an error."""
    nodes = []
    for i, ch_id in enumerate(chapter_ids):
        ch_concepts = [
            c for c in concepts
            if str(c.get("chapter_id") or c.get("chapter") or "") == str(ch_id)
        ]
        nodes.append({
            "id": str(ch_id),
            "chapter_number": i + 1,
            "title": f"Chapter {i + 1}",
            "type": "chapter",
            "position_index": i,
            "concept_ids": [str(c.get("id") or c.get("concept_id") or "") for c in ch_concepts],
        })
    return {"nodes": nodes, "source": "synthetic_from_concepts"}
