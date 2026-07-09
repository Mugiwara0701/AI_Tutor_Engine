"""
canonical_base.py — A1.1: CanonicalObjectBase.

This introduces the common parent schema that all canonical educational
objects (concepts, figures, tables, equations, activities, etc.) will
eventually inherit from, so the metadata every one of them needs --
identity, versioning, subject/chapter placement, provenance, confidence,
and lineage -- is declared once instead of being copy-pasted per type.

SCOPE (A1.1 only): this file introduces the base class and the small
supporting sub-models it needs. It does NOT migrate any existing schema
(chapter_schema.py, educational_objects_schema.py) to inherit from it --
that migration is later work. Existing schemas, imports, and
serialization are completely untouched by this change.

Design notes:
- `CanonicalObjectBase` uses `extra="allow"` (like the existing `Loose`
  base in chapter_schema.py) so that once a concrete schema does migrate
  to inherit from it, that schema's own additional fields keep working,
  and old JSON with extra keys keeps validating.
- `Provenance` and `CreationMetadata` are intentionally permissive
  (`extra="allow"`) since their exact internal shape is expected to vary
  per object type and evolve over time -- mirrors how `ExtractionMetadata`
  / `AIMetadata` etc. are modeled in chapter_schema.py.
- `duplicate_lineage` mirrors the exact type already used on
  `EducationalObject` in chapter_schema.py (`List[Dict[str, Any]]`) so
  that a future migration of `EducationalObject` onto this base is a
  pure no-op for that field.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
    """Where a canonical object's content/claims came from (source
    document, pipeline stage, extractor, page/bbox references, etc.).
    Kept permissive since provenance shape can vary by object type and
    is expected to grow."""

    model_config = ConfigDict(extra="allow")

    source: Optional[str] = None
    stage: Optional[str] = None
    extractor: Optional[str] = None
    page: Optional[int] = None


class CreationMetadata(BaseModel):
    """When/how/by-what a canonical object was created (timestamps,
    generator identity, run id, etc.). Kept permissive for the same
    reason as `Provenance`."""

    model_config = ConfigDict(extra="allow")

    created_at: Optional[str] = None
    created_by: Optional[str] = None
    run_id: Optional[str] = None


class CanonicalObjectBase(BaseModel):
    """Common base model for all canonical educational objects.

    This is a schema-layer-only addition (A1.1). No existing object
    schema inherits from this yet -- see module docstring. It exists so
    later migrations (A1.2+) have one place to inherit shared metadata
    from instead of redeclaring these fields on every object type.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Identity
    id: str
    urn: Optional[str] = None
    object_type: str

    # Versioning
    schema_version: str = "1.0.0"
    compiler_version: Optional[str] = None

    # Placement within the book/chapter
    subject: Optional[str] = None
    chapter_reference: Optional[str] = None
    topic_ids: List[str] = Field(default_factory=list)
    concept_ids: List[str] = Field(default_factory=list)

    # Lineage / quality / lifecycle
    provenance: Provenance = Field(default_factory=Provenance)
    extraction_confidence: float = 0.0
    validation_status: str = "unvalidated"
    duplicate_lineage: List[Dict[str, Any]] = Field(default_factory=list)
    creation_metadata: CreationMetadata = Field(default_factory=CreationMetadata)