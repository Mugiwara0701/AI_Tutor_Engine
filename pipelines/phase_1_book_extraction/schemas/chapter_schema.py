"""
chapter_schema.py — the single source of truth for what a Chapter JSON must
contain. Every field the task spec lists is represented here so json_writer
can never silently drop a section, and validator can catch a missing/mis
typed field before it hits disk.

Design choice: sections that are naturally lists-of-records (figures, tables,
concepts, ...) use typed sub-models. Sections whose internal shape is more
free-form per the spec (ai_metadata, generation_metadata, quality,
extraction_logs) use permissive dict-friendly models with `extra="allow"`
so we satisfy "never remove any field" without over-constraining content
that's meant to be somewhat flexible.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class Loose(BaseModel):
    """Base class for sections whose exact keys can grow (ai_metadata etc.)."""
    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------
# Small shared shapes
# --------------------------------------------------------------------------
class BBox(BaseModel):
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    page: int = 0


# --------------------------------------------------------------------------
# Phase A — Foundation Layer (A1 Common Canonical Base Model, A2 Unified
# Provenance Model). See modules/pdf_parser.make_id / make_urn for the A3
# identity strategy these two models assume (deterministic id/urn, never
# random), and modules/canonical.py for the assembly-time helper that
# builds these shapes so pipeline.py doesn't repeat the same dict literal
# per object type.
# --------------------------------------------------------------------------
class Provenance(BaseModel):
    """A2 — Unified Provenance Model. Every canonical educational object
    exposes exactly this shape (via CanonicalObjectBase.provenance)
    instead of each object type inventing its own ad-hoc subset of "where
    did this come from" fields. All fields are optional/defaulted because
    not every object type has a meaningful value for every field (e.g. a
    content_blocks.py-detected Activity has no `recognizer` name; an
    object built before Stage A runs has no `source_block_id` yet).
    `extraction_method` records whether the value came from deterministic
    code, the VLM, or both, independent of `recognizer`/`extraction_stage`
    (which record *where* in the pipeline, not *how*)."""
    model_config = ConfigDict(extra="allow")

    source_page: Optional[int] = None
    source_block_id: Optional[str] = None
    source_heading: Optional[str] = None
    section: Optional[str] = None
    bounding_box: Optional[BBox] = None
    extraction_stage: Optional[str] = None
    recognizer: Optional[str] = None
    evidence_span: Optional[str] = None
    extraction_method: str = "deterministic"  # "deterministic" | "vlm" | "hybrid"
    confidence: float = 0.0
    timestamp: Optional[str] = None


class CreationMetadata(Loose):
    """Part of A1's base model. Loose (extra="allow") because compiler-run
    metadata is expected to grow (e.g. multi-board/multilingual run flags)
    without every historical object needing a new required field."""
    created_at: Optional[str] = None
    compiler_version: str = "1.0.0"
    generator: Optional[str] = None


class CanonicalObjectBase(BaseModel):
    """A1 — Common Canonical Base Model. Every canonical educational
    object (Concept, Definition, Formula/Equation, Figure, Table, Diagram,
    Chart, Graph, Box, Note, Warning, Example, Activity, Glossary Entry,
    ...) inherits this instead of redeclaring the same identity/
    provenance/lineage fields per class -- "avoid duplication across
    schema classes; use inheritance rather than copy-paste fields" (Phase
    A roadmap, A1). Concrete subclasses below add only the fields specific
    to their own educational meaning (e.g. Figure.caption, Equation.latex).

    IDENTITY STRATEGY (A3, see modules/pdf_parser.py for the generators):
    `id` and `urn` are both deterministic -- derived from stable inputs
    (chapter title/slug, object kind, and either a content-derived key or
    a stable positional index), never a random UUID/timestamp -- so
    recompiling the same chapter content reproduces the same id/urn.
    `id` is the short, hash-suffixed local identifier (make_id); `urn` is
    the globally-unique, hierarchical reference (make_urn), stable across
    recompilations unless the underlying educational content's meaning
    actually changes (i.e. unless the inputs slugify() differently).

    NOT every field is populated by every producer yet -- Stage A-E's own
    block/educational-object output (AnnotatedBlock / EducationalObject
    below) is explicitly OUT of scope for Phase A (the roadmap says do not
    redesign Stage A-E) and keeps its existing Loose shape unchanged.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    urn: Optional[str] = None
    object_type: str = "educational_object"
    # Fallback only -- modules/canonical.py::canonical_fields() always sets
    # this explicitly from config.SCHEMA_VERSION on every real object it
    # builds. Kept in sync with that constant (see Fix 2 / MIGRATIONS.md)
    # so a model constructed without canonical_fields() doesn't report a
    # stale version.
    schema_version: str = "2.0.0"
    subject: Optional[str] = None
    chapter_reference: Optional[str] = None
    topic_ids: List[str] = Field(default_factory=list)
    concept_ids: List[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    extraction_confidence: float = 0.0
    validation_status: str = "unvalidated"
    duplicate_lineage: List[Dict[str, Any]] = Field(default_factory=list)
    creation_metadata: CreationMetadata = Field(default_factory=CreationMetadata)


class ExtractionMetadata(Loose):
    pipeline_version: str = "1.0.0"
    extracted_at: Optional[str] = None
    source_pdf: Optional[str] = None
    ocr_engine: Optional[str] = None
    vlm_model: Optional[str] = None
    processing_time_seconds: Optional[float] = None


class DocumentInfo(Loose):
    book_title: str = "untitled-book"
    subject: str = "unknown"
    klass: str = Field(default="unknown", alias="class")
    board: str = "NCERT"
    language: List[str] = Field(default_factory=lambda: ["en"])
    # Phase 1 Final Metadata Architecture Refinement: canonical cover
    # metadata (never overwrites book_title above) + the two derived
    # identities (educational_identity, storage_identity). All optional
    # and None by default -- a book with no distinguishing cover metadata
    # (the common, single-part case) simply leaves these unset.
    book_subtitle: Optional[str] = None
    book_part: Optional[str] = None
    book_volume: Optional[str] = None
    book_edition: Optional[str] = None
    educational_identity: Optional[str] = None
    storage_identity: Optional[str] = None
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ChapterMetadata(Loose):
    chapter_number: Union[int, str] = 0
    chapter_title: str = "untitled-chapter"
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    toc_matched: bool = False


class ChapterStatistics(Loose):
    total_pages: int = 0
    total_words: int = 0
    total_topics: int = 0
    total_figures: int = 0
    total_tables: int = 0
    total_equations: int = 0


class PageInfo(BaseModel):
    page_number: int
    width: Optional[float] = None
    height: Optional[float] = None
    word_count: int = 0
    has_figures: bool = False
    has_tables: bool = False
    has_equations: bool = False
    ocr_confidence: Optional[float] = None


class TopicNode(BaseModel):
    id: str
    title: str
    numbering: Optional[str] = None
    level: int = 1
    parent: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    bbox: Optional[BBox] = None
    reading_order: int = 0
    keywords: List[str] = Field(default_factory=list)
    # A4 -- canonical concept references: `concepts` now holds concept IDs
    # (the canonical reference), never bare names. `concept_names` is the
    # derived, human-readable counterpart -- useful for readability, but
    # NOT the reference other objects should link against. Pre-Phase-A
    # JSON had `concepts` holding names; this is a deliberate, documented
    # meaning change of that field's contents (not its shape -- still
    # List[str]) per roadmap A4 ("the canonical reference should always
    # be the concept ID").
    #
    # SCHEMA VERSIONING (Fix 2, Phase A finalization): this is a semantic
    # (MAJOR) schema change per config.SCHEMA_VERSION's versioning policy --
    # same field name/shape, but a consumer reading old JSON's `concepts` as
    # names would now silently get ids instead. schema_version was bumped
    # 1.0.0 -> 2.0.0 for exactly this reason. See MIGRATIONS.md at the repo
    # root for the full migration note (how to read display names now, how
    # to cross-reference against the top-level `concepts[]` array, etc.).
    concepts: List[str] = Field(default_factory=list)
    concept_names: List[str] = Field(default_factory=list)
    definitions: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    activities: List[str] = Field(default_factory=list)
    figures: List[str] = Field(default_factory=list)
    tables: List[str] = Field(default_factory=list)
    equations: List[str] = Field(default_factory=list)
    diagrams: List[str] = Field(default_factory=list)
    charts: List[str] = Field(default_factory=list)
    graphs: List[str] = Field(default_factory=list)
    maps: List[str] = Field(default_factory=list)
    timelines: List[str] = Field(default_factory=list)
    boxes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    semantic_summary: str = ""
    visual_summary: str = ""
    detected_entities: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    related_topics: List[str] = Field(default_factory=list)
    next_topics: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class Concept(CanonicalObjectBase):
    """Canonical Concept Registry entry. One record per distinct concept
    name in the chapter (deduped case-insensitively at build time -- see
    pipeline.py's concept_registry) so downstream phases can treat id/urn
    as a stable reference regardless of how many topics mention the
    concept. `topic` (singular) is kept only for backward compatibility
    with existing consumers; `topics` is the canonical, complete list."""
    object_type: str = "concept"
    name: str
    aliases: List[str] = Field(default_factory=list)
    importance: str = "medium"
    topic: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    page: Optional[int] = None
    related_concepts: List[str] = Field(default_factory=list)


class Definition(CanonicalObjectBase):
    object_type: str = "definition"
    term: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    topic: Optional[str] = None


class Example(CanonicalObjectBase):
    object_type: str = "example"
    title: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    example_type: str = "worked_example"
    semantic_description: str = ""


class Activity(CanonicalObjectBase):
    object_type: str = "activity"
    activity_type: str  # Activity / Think / Observe / Try / Discuss / Experiment
    title: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


class Figure(CanonicalObjectBase):
    object_type: str = "figure"
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    title: str = ""
    caption: str = ""
    figure_type: str = "figure"
    semantic_description: str = ""
    educational_purpose: str = ""
    # A4: kept for backward compatibility (previously the only concept
    # link this object had, and never actually populated by pipeline.py).
    # `concept_ids` (inherited from CanonicalObjectBase) is now the
    # canonical reference; `concepts` is treated as the human-readable
    # derived list going forward, same spirit as TopicNode.concept_names.
    concepts: List[str] = Field(default_factory=list)
    related_topics: List[str] = Field(default_factory=list)
    importance: str = "medium"
    difficulty: str = "medium"
    animation_candidate: bool = False
    confidence: float = 0.0


class Table(CanonicalObjectBase):
    object_type: str = "table"
    title: str = ""
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    rows: int = 0
    columns: int = 0
    table_type: str = "data_table"
    semantic_description: str = ""
    educational_purpose: str = ""
    concepts: List[str] = Field(default_factory=list)  # see Figure.concepts note
    confidence: float = 0.0


class Equation(CanonicalObjectBase):
    object_type: str = "equation"
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    latex: str = ""
    spoken_form: str = ""
    variables: List[str] = Field(default_factory=list)
    semantic_meaning: str = ""
    confidence: float = 0.0


class Diagram(Figure):
    """Diagrams/charts/graphs/maps/timelines share the figure-like shape;
    kept as distinct subclasses so json_writer can still emit them under
    their own top-level schema keys per the spec."""
    object_type: str = "diagram"


class Chart(Figure):
    object_type: str = "chart"


class Graph(Figure):
    object_type: str = "graph"


class Map(Figure):
    object_type: str = "map"


class Timeline(Figure):
    object_type: str = "timeline"


class Box(CanonicalObjectBase):
    object_type: str = "box"
    box_type: str  # Did You Know / Important / Note / Remember / Case Study / Box
    title: str = ""
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


class NoteItem(CanonicalObjectBase):
    object_type: str = "note"
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


class WarningItem(CanonicalObjectBase):
    object_type: str = "warning"
    warning_type: str  # Warning / Caution / Remember / Important
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


class GlossaryEntry(CanonicalObjectBase):
    """A1/A5: glossary entries were previously plain free-form dicts
    (`glossary: List[Dict[str, Any]]` on ChapterJSON below) with no id/urn
    at all. Promoted to a canonical object like every other Glossary Entry
    example in the roadmap. Stores only the term, never definition text,
    per the existing copyright guardrail (see content_blocks.py /
    README.md) -- unchanged behavior, just now identity-bearing."""
    object_type: str = "glossary_entry"
    term: str
    topic: Optional[str] = None
    page: Optional[int] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship_type: str = "related_to"
    weight: float = 1.0


class LearningGraph(Loose):
    nodes: List[str] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


class ConceptGraph(Loose):
    nodes: List[str] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


class SemanticIndexEntry(BaseModel):
    concept: str
    topics: List[str] = Field(default_factory=list)
    definitions: List[str] = Field(default_factory=list)
    figures: List[str] = Field(default_factory=list)
    tables: List[str] = Field(default_factory=list)
    equations: List[str] = Field(default_factory=list)


class AIMetadata(Loose):
    chapter_type: str = ""
    knowledge_density: str = ""
    overall_complexity: str = ""
    visual_dependency: str = ""
    formula_dependency: str = ""
    memory_dependency: str = ""
    calculation_dependency: str = ""
    real_world_relevance: str = ""
    important_concepts: List[str] = Field(default_factory=list)
    likely_confusing_concepts: List[str] = Field(default_factory=list)
    visual_priority_topics: List[str] = Field(default_factory=list)
    concept_progression: List[str] = Field(default_factory=list)
    interdisciplinary_links: List[str] = Field(default_factory=list)


class GenerationMetadata(Loose):
    """Phase 1 may describe the KNOWLEDGE (which visuals the chapter's
    content structurally favors, which real-world domains it draws on) --
    it must not prescribe PEDAGOGY. `teacher_style` (how to teach) and
    `quiz_focus_topics` (what to assess) were phase leakage: both are
    later-phase decisions, not facts about the chapter's knowledge
    content, and were removed. Loose (extra="allow") means old JSON that
    still carries these keys continues to validate; they're just no
    longer produced going forward."""
    preferred_visual_types: List[str] = Field(default_factory=list)
    visual_priority: List[str] = Field(default_factory=list)
    real_world_domains: List[str] = Field(default_factory=list)


class QualityScores(Loose):
    ocr: float = 0.0
    heading: float = 0.0
    layout: float = 0.0
    table: float = 0.0
    figure: float = 0.0
    equation: float = 0.0
    overall: float = 0.0


class ExtractionLogs(Loose):
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    missing_figures: List[str] = Field(default_factory=list)
    ocr_failures: List[str] = Field(default_factory=list)
    parser_messages: List[str] = Field(default_factory=list)
    processing_time: Optional[float] = None


class AnnotatedBlock(Loose):
    """One Stage A/B/C block (geometry + classification + priority),
    included for lineage/debugging alongside the full semantic Master JSON
    below. Single source of truth: schemas/educational_objects_schema.py
    imports this same class rather than redeclaring it, so the two schemas
    can't drift apart."""
    block_id: str
    parent: Optional[str] = None
    block_type: str = "Ambiguous"
    priority: str = "medium"
    confidence: float = 0.0
    page: int = 0
    page_end: Optional[int] = None
    bbox: BBox = Field(default_factory=BBox)
    child_block_ids: List[str] = Field(default_factory=list)


class EducationalObject(Loose):
    """One Stage D/E output record (see AnnotatedBlock docstring re: single
    source of truth). Shape intentionally varies a bit by
    `educational_object_type` -- Loose (`extra="allow"`) lets each type
    carry its own extra fields without every type needing every field."""
    id: str
    block_id: str
    block_type: str
    priority: str
    educational_object_type: str
    page: int = 0
    page_end: Optional[int] = None
    bbox: BBox = Field(default_factory=BBox)
    confidence: float = 0.0
    source: str = "deterministic"
    duplicate_lineage: List[Dict[str, Any]] = Field(default_factory=list)


class ValidationReport(Loose):
    input_count: int = 0
    output_count: int = 0
    removed_duplicate_formulas: int = 0
    removed_duplicate_definitions: int = 0
    removed_bare_arithmetic: int = 0
    warnings: List[str] = Field(default_factory=list)


class ChapterJSON(BaseModel):
    """Top-level Phase-1 Chapter JSON. Field order here is the field order
    the spec lists; every section is present even when empty ([] or {}).

    `blocks` / `educational_objects` / `validation_report` are additive
    fields (regression-fix restoration, see REGRESSION_AUDIT.md): they fold
    the Stage A-E block/educational-object output produced by the
    "optimization" pass into the same Master JSON that already carries
    topics/concepts/learning_graph/etc., instead of that output living in a
    separate, narrower document that replaced the Master JSON entirely.
    Every pre-existing field/consumer is unaffected -- these three are pure
    additions."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Fallback only -- json_writer.py always sets this explicitly from
    # config.SCHEMA_VERSION when assembling the real document. Kept in sync
    # with that constant (see Fix 2 / MIGRATIONS.md: 1.0.0 -> 2.0.0 for the
    # TopicNode.concepts semantic change).
    schema_version: str = "2.0.0"
    extraction_metadata: ExtractionMetadata = Field(default_factory=ExtractionMetadata)
    document: DocumentInfo = Field(default_factory=DocumentInfo)
    chapter_metadata: ChapterMetadata = Field(default_factory=ChapterMetadata)
    chapter_statistics: ChapterStatistics = Field(default_factory=ChapterStatistics)
    pages: List[PageInfo] = Field(default_factory=list)
    topic_tree: List[Dict[str, Any]] = Field(default_factory=list)
    topics: List[TopicNode] = Field(default_factory=list)
    concepts: List[Concept] = Field(default_factory=list)
    glossary: List[GlossaryEntry] = Field(default_factory=list)
    definitions: List[Definition] = Field(default_factory=list)
    examples: List[Example] = Field(default_factory=list)
    activities: List[Activity] = Field(default_factory=list)
    figures: List[Figure] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    equations: List[Equation] = Field(default_factory=list)
    diagrams: List[Diagram] = Field(default_factory=list)
    charts: List[Chart] = Field(default_factory=list)
    graphs: List[Graph] = Field(default_factory=list)
    maps: List[Map] = Field(default_factory=list)
    timelines: List[Timeline] = Field(default_factory=list)
    boxes: List[Box] = Field(default_factory=list)
    notes: List[NoteItem] = Field(default_factory=list)
    warnings: List[WarningItem] = Field(default_factory=list)
    blocks: List[AnnotatedBlock] = Field(default_factory=list)
    educational_objects: List[EducationalObject] = Field(default_factory=list)
    validation_report: ValidationReport = Field(default_factory=ValidationReport)
    learning_graph: LearningGraph = Field(default_factory=LearningGraph)
    concept_graph: ConceptGraph = Field(default_factory=ConceptGraph)
    semantic_index: List[SemanticIndexEntry] = Field(default_factory=list)
    ai_metadata: AIMetadata = Field(default_factory=AIMetadata)
    generation_metadata: GenerationMetadata = Field(default_factory=GenerationMetadata)
    quality: QualityScores = Field(default_factory=QualityScores)
    extraction_logs: ExtractionLogs = Field(default_factory=ExtractionLogs)