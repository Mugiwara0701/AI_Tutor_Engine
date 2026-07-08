"""
educational_objects_schema.py — schema for the narrower Stage D/E-only
output shape (Validated Educational Objects + the annotated block list),
kept for any external caller that wants that shape directly.

ARCHITECTURAL NOTE (hardening-pass correction): this module's docstring
previously claimed json_writer/validator used THIS schema as Phase 1's
primary output and that schemas/chapter_schema.py/ChapterJSON was "kept
as-is for Phase 2." That is not what pipeline.py actually does: it calls
assemble_chapter_json/write_chapter_json, which validates against and
writes ChapterJSON (chapter_schema.py) -- the full Master JSON, including
learning_graph/concept_graph/semantic_index. EducationalObjectsDocument
below, and the assemble_educational_objects_document/
write_educational_objects_json/validate_educational_objects_document
functions that build/validate it, are orphaned: no code path in
pipeline.py calls them. They are kept only for any external caller that
wants the narrower shape, not as the active pipeline output.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

from schemas.chapter_schema import (
    Loose, BBox, ExtractionMetadata, DocumentInfo, ChapterMetadata,
    AnnotatedBlock, EducationalObject, ValidationReport,
)

# AnnotatedBlock / EducationalObject / ValidationReport used to be declared
# here directly. They now live in schemas/chapter_schema.py as the single
# source of truth (chapter_schema.ChapterJSON also carries `blocks` /
# `educational_objects` / `validation_report` as additive fields -- see
# REGRESSION_AUDIT.md), and are re-imported here so this module's public
# names (`schemas.educational_objects_schema.AnnotatedBlock`, etc.) keep
# working for any existing caller.


class EducationalObjectsDocument(BaseModel):
    """Phase 1's actual output document. NOT a Chapter JSON / Master JSON:
    no learning_graph, no concept_graph, no semantic_index -- those are
    built entirely in Phase 2 from this document's `educational_objects`."""
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = "1.0.0"
    phase: str = "phase_1_educational_extraction"
    extraction_metadata: ExtractionMetadata = Field(default_factory=ExtractionMetadata)
    document: DocumentInfo = Field(default_factory=DocumentInfo)
    chapter_metadata: ChapterMetadata = Field(default_factory=ChapterMetadata)

    blocks: List[AnnotatedBlock] = Field(default_factory=list)
    educational_objects: List[EducationalObject] = Field(default_factory=list)

    validation_report: ValidationReport = Field(default_factory=ValidationReport)
    quality: Dict[str, float] = Field(default_factory=dict)
    extraction_logs: Dict[str, Any] = Field(default_factory=dict)
