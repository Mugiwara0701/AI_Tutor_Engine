"""
modules/canonical.py — Phase A shared infrastructure.

Two things live here, both purely additive (no PDF/model work, no
mutation of Stage A-E's own logic):

  1. `canonical_fields()` builds the A1/A2 common envelope
     (id/urn/object_type/schema_version/subject/chapter_reference/
     topic_ids/concept_ids/provenance/extraction_confidence/
     validation_status/duplicate_lineage/creation_metadata) that every
     canonical educational object dict in pipeline.py gets merged with,
     matching schemas/chapter_schema.py's CanonicalObjectBase /
     Provenance / CreationMetadata models. Centralizing this here (rather
     than repeating the same ~12-key dict literal at every one of the
     dozen call sites in pipeline.py) is what "use inheritance rather
     than copy-paste fields" means at the assembly-code level, not just
     in the Pydantic class hierarchy.

  2. `resolve_concept_ids()` is the A4 canonical-concept-reference lookup:
     given a list of human-readable concept names and the chapter's
     name->id registry, returns the stable concept ids (silently
     dropping names that aren't in the registry -- concept linkage is
     best-effort enrichment, not a hard validation gate).

Nothing here calls the VLM, mutates Stage A-E block state, or changes any
extraction decision -- it only shapes already-extracted data into the
Phase A schema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import SCHEMA_VERSION
from modules.pdf_parser import make_urn


def resolve_concept_ids(names: List[str], concept_name_to_id: Dict[str, str]) -> List[str]:
    """A4 — canonical concept references. Looks up each concept NAME
    (case-insensitively) against the chapter's concept registry
    (name.lower() -> concept id, built once in pipeline.py from
    concept_registry) and returns the stable concept ids, in first-seen
    order, deduplicated. Names that never made it into the registry (e.g.
    mentioned by one recognizer's output but never surfaced by
    process_topic_semantics for any topic) are silently skipped rather
    than raising."""
    out: List[str] = []
    for n in names or []:
        key = str(n).strip().lower()
        if not key:
            continue
        cid = concept_name_to_id.get(key)
        if cid and cid not in out:
            out.append(cid)
    return out


def canonical_fields(
    *,
    object_id: str,
    object_type: str,
    namespace: str,
    urn_parts: List[str],
    subject: Optional[str] = None,
    chapter_reference: Optional[str] = None,
    topic_ids: Optional[List[str]] = None,
    concept_ids: Optional[List[str]] = None,
    source_page: Optional[int] = None,
    source_block_id: Optional[str] = None,
    source_heading: Optional[str] = None,
    section: Optional[str] = None,
    bounding_box: Optional[Dict[str, Any]] = None,
    extraction_stage: Optional[str] = None,
    recognizer: Optional[str] = None,
    evidence_span: Optional[str] = None,
    extraction_method: str = "deterministic",
    confidence: float = 0.0,
    validation_status: str = "unvalidated",
    duplicate_lineage: Optional[List[Dict[str, Any]]] = None,
    generator: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns the A1/A2 common-base dict, to be merged into (via
    `obj.update(canonical_fields(...))` or `{**canonical_fields(...),
    **extra_fields}`) every canonical educational object's output dict.

    `object_id` is ALWAYS an id the caller already generated
    deterministically via modules.pdf_parser.make_id -- this function
    never mints ids itself. It only builds the urn + surrounding envelope
    around an id that already exists, so there is exactly one identity
    strategy (make_id/make_urn), never two competing ones.
    """
    return {
        "id": object_id,
        "urn": make_urn(namespace, *urn_parts),
        "object_type": object_type,
        "schema_version": SCHEMA_VERSION,
        "subject": subject,
        "chapter_reference": chapter_reference,
        "topic_ids": topic_ids or [],
        "concept_ids": concept_ids or [],
        "provenance": {
            "source_page": source_page,
            "source_block_id": source_block_id,
            "source_heading": source_heading,
            "section": section,
            "bounding_box": bounding_box,
            "extraction_stage": extraction_stage,
            "recognizer": recognizer,
            "evidence_span": evidence_span,
            "extraction_method": extraction_method,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "extraction_confidence": confidence,
        "validation_status": validation_status,
        "duplicate_lineage": duplicate_lineage or [],
        "creation_metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "compiler_version": SCHEMA_VERSION,
            "generator": generator,
        },
    }
