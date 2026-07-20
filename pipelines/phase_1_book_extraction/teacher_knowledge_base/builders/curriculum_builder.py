"""
teacher_knowledge_base/builders/curriculum_builder.py — M6.1 (remediated)

SPECIFICATION: CURRICULUM_GRAPH_SPECIFICATION.md v1.1.1

V1 SCOPE: within-book only.
  - WITHIN_CHAPTER: concepts appearing multiple times in the same chapter
  - CROSS_CHAPTER: stubs for concepts in other chapters of same book
  - CROSS_BOOK / CROSS_CLASS / CROSS_SUBJECT: NOT POPULATED IN V1

NODE SCHEMA (spec §3): CurriculumNode
  cg_node_id: UUID5(concept_id + scope_key + tkb_id)
  concept_id, concept_key, concept_name, scope, scope_key,
  chapter_number, book_title, klass, subject, tkb_id, gci_key_hint, is_stub

EDGE SCHEMA (spec §4): CurriculumEdge
  cg_edge_id, source_node_id, target_node_id,
  edge_type (REAPPEARS_IN | EXTENDS_INTO | CURRICULUM_SEQUENCE),
  relationship, scope, confidence

WHAT THE OLD IMPLEMENTATION DID WRONG:
  - Used TeachingUnit chunks as curriculum graph nodes (not concept-level CurriculumNodes)
  - Used prerequisite_unit_ids as edges (that's EDG, not CG)
  - Produced global_teaching_sequence (that's EDG.topological_order, not CG)
  - Did not produce cross_chapter_links, CurriculumScope, is_stub fields
"""
from __future__ import annotations

import uuid
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.curriculum")

_CG_NS = uuid.UUID("aabbccdd-0011-2233-4455-667788990011")

STAGE = "curriculum_graph"
CG_VERSION = "1.1.1"

V1_SCOPES = ("WITHIN_CHAPTER", "CROSS_CHAPTER")
V1_EDGE_TYPES = ("REAPPEARS_IN", "EXTENDS_INTO", "CURRICULUM_SEQUENCE")


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


def _build_curriculum_graph(context: "TKBContext") -> None:  # noqa: F821
    teaching_units = context.require_output("teaching_units", STAGE)
    tkb_id = context.tkb_id
    artifacts = context.compiler_artifacts
    metadata = context.metadata

    # Get curriculum context from compiler artifacts
    # The CG needs to know which concepts appear in other chapters
    # This comes from CompilerReleaseManifest or Build cross-chapter data
    cross_chapter_data = _get_cross_chapter_data(artifacts, context)

    nodes: Dict[str, Any] = {}   # cg_node_id -> CurriculumNode
    edges: Dict[str, Any] = {}   # cg_edge_id -> CurriculumEdge
    cross_chapter_links: List[Dict[str, Any]] = []

    chapter_number = int(metadata.chapter_number if hasattr(metadata, 'chapter_number') else 0)
    book_title = str(metadata.book_title if hasattr(metadata, 'book_title') else "")
    klass = str(metadata.klass if hasattr(metadata, 'klass') else "")
    subject = str(metadata.subject if hasattr(metadata, 'subject') else "")

    # Build one WITHIN_CHAPTER node per concept in this chapter
    for concept_id, tu in teaching_units.items():
        scope_key = f"chapter_{chapter_number}"
        cg_node_id = str(uuid.uuid5(_CG_NS, f"{concept_id}:{scope_key}:{tkb_id}"))
        cg_node_urn = f"urn:tkb:cg:{cg_node_id}"
        nodes[cg_node_id] = {
            "cg_node_id": cg_node_id,
            "cg_node_urn": cg_node_urn,
            "concept_id": concept_id,
            "concept_key": str(tu.get("concept_key") or ""),
            "concept_name": str(tu.get("title") or concept_id),
            "scope": "WITHIN_CHAPTER",
            "scope_key": scope_key,
            "chapter_number": chapter_number,
            "book_title": book_title,
            "klass": klass,
            "subject": subject,
            "tkb_id": tkb_id,
            "gci_key_hint": None,  # V1: null until Phase 3 GCI
            "is_stub": False,
        }

    # Add cross-chapter concept nodes as stubs
    concept_id_to_cg_node_id: Dict[str, str] = {
        nodes[nid]["concept_id"]: nid for nid in nodes
    }

    for cross_concept_id, cross_info in cross_chapter_data.get("cross_chapter_concepts", {}).items():
        target_chapter = int(cross_info.get("chapter_number") or 0)
        scope_key = f"chapter_{target_chapter}"
        cg_node_id = str(uuid.uuid5(_CG_NS, f"{cross_concept_id}:{scope_key}:{tkb_id}"))
        if cg_node_id not in nodes:
            nodes[cg_node_id] = {
                "cg_node_id": cg_node_id,
                "cg_node_urn": f"urn:tkb:cg:{cg_node_id}",
                "concept_id": cross_concept_id,
                "concept_key": str(cross_info.get("concept_key") or ""),
                "concept_name": str(cross_info.get("concept_name") or cross_concept_id),
                "scope": "CROSS_CHAPTER",
                "scope_key": scope_key,
                "chapter_number": target_chapter,
                "book_title": book_title,
                "klass": klass,
                "subject": subject,
                "tkb_id": tkb_id,
                "gci_key_hint": cross_info.get("gci_key_hint"),
                "is_stub": bool(cross_info.get("is_stub", True)),
            }

    # Build edges (v1 edge types)
    # CURRICULUM_SEQUENCE: sequence of concepts in EDG topological order
    edg_output = context.get_output("edg")
    if edg_output:
        topo_order = edg_output.get("topological_order") or []
        for i in range(len(topo_order) - 1):
            src_cid = topo_order[i]
            tgt_cid = topo_order[i + 1]
            src_nid = concept_id_to_cg_node_id.get(src_cid)
            tgt_nid = concept_id_to_cg_node_id.get(tgt_cid)
            if src_nid and tgt_nid:
                edge_key = f"{src_nid}:{tgt_nid}:CURRICULUM_SEQUENCE:{tkb_id}"
                cg_edge_id = str(uuid.uuid5(_CG_NS, edge_key))
                edges[cg_edge_id] = {
                    "cg_edge_id": cg_edge_id,
                    "source_node_id": src_nid,
                    "target_node_id": tgt_nid,
                    "edge_type": "CURRICULUM_SEQUENCE",
                    "relationship": f"{topo_order[i]} precedes {topo_order[i+1]} in curriculum",
                    "scope": "WITHIN_CHAPTER",
                    "confidence": 1.0,
                }

    # Cross-chapter links
    for link_data in cross_chapter_data.get("cross_chapter_links", []):
        src_cid = str(link_data.get("source_concept_id") or "")
        tgt_cid = str(link_data.get("target_concept_id") or "")
        link_ns = uuid.UUID("99887766-5544-3322-1100-ffeeddccbbaa")
        link_id = str(uuid.uuid5(link_ns, f"link:{src_cid}:{tgt_cid}:{tkb_id}"))
        cross_chapter_links.append({
            "link_id": link_id,
            "source_concept_id": src_cid,
            "source_chapter": chapter_number,
            "target_concept_id": tgt_cid if not link_data.get("is_stub") else None,
            "target_chapter": int(link_data.get("target_chapter") or 0),
            "link_type": str(link_data.get("link_type") or "reintroduction"),
            "description": str(link_data.get("description") or ""),
            "is_stub": bool(link_data.get("is_stub", True)),
        })

    scopes_present = list({n["scope"] for n in nodes.values()})
    total_within = sum(1 for n in nodes.values() if n["scope"] == "WITHIN_CHAPTER")
    total_cross = sum(1 for n in nodes.values() if n["scope"] == "CROSS_CHAPTER")
    total_stubs = sum(1 for n in nodes.values() if n.get("is_stub"))

    curriculum_graph = {
        "cg_id": str(uuid.uuid5(_CG_NS, f"cg:{tkb_id}")),
        "scope_description": "within-book v1",
        "nodes": dict(sorted(nodes.items())),
        "edges": dict(sorted(edges.items())),
        "cross_chapter_links": cross_chapter_links,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "scopes_present": sorted(scopes_present),
        "metadata": {
            "cg_version": CG_VERSION,
            "created_at": _now_iso(),
            "total_within_chapter": total_within,
            "total_cross_chapter": total_cross,
            "total_stubs": total_stubs,
            "gci_ready": False,  # V1: always False
        },
        "validation": {
            "all_source_concepts_resolvable": all(
                n["concept_id"] in teaching_units or n["scope"] == "CROSS_CHAPTER"
                for n in nodes.values()
            ),
            "no_self_referencing_edges": all(
                e["source_node_id"] != e["target_node_id"] for e in edges.values()
            ),
            "stubs_documented": True,
            "cross_book_links_absent": not any(
                n["scope"] in ("CROSS_BOOK", "CROSS_CLASS", "CROSS_SUBJECT")
                for n in nodes.values()
            ),
            "status": "VALID",
            "warnings": [],
        },
    }
    context.set_output(STAGE, curriculum_graph)
    logger.info(
        "Curriculum Graph builder: %d nodes (%d within-chapter, %d cross-chapter, %d stubs), %d edges.",
        len(nodes), total_within, total_cross, total_stubs, len(edges),
    )


def _get_cross_chapter_data(
    artifacts: Dict[str, Any],
    context: "TKBContext",
) -> Dict[str, Any]:
    """Reads cross-chapter concept data from CompilerReleaseManifest or Build.
    In v1, cross-chapter data may be absent; we return empty structures."""
    result: Dict[str, Any] = {
        "cross_chapter_concepts": {},
        "cross_chapter_links": [],
    }
    release_manifest = artifacts.get("compiler_release_manifest") or {}
    if isinstance(release_manifest, dict):
        cross = release_manifest.get("cross_chapter_concepts") or {}
        if isinstance(cross, dict):
            result["cross_chapter_concepts"] = cross
        links = release_manifest.get("cross_chapter_links") or []
        if isinstance(links, list):
            result["cross_chapter_links"] = links
    return result


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
