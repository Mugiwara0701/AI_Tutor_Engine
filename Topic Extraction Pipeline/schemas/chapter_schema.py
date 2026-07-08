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
    concepts: List[str] = Field(default_factory=list)
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


class Concept(BaseModel):
    """Canonical Concept Registry entry. One record per distinct concept
    name in the chapter (deduped case-insensitively at build time -- see
    pipeline.py's concept_registry) so downstream phases can treat id/urn
    as a stable reference regardless of how many topics mention the
    concept. `topic` (singular) is kept only for backward compatibility
    with existing consumers; `topics` is the canonical, complete list."""
    id: str
    urn: Optional[str] = None
    name: str
    aliases: List[str] = Field(default_factory=list)
    importance: str = "medium"
    topic: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    page: Optional[int] = None
    related_concepts: List[str] = Field(default_factory=list)


class Definition(BaseModel):
    term: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    topic: Optional[str] = None


class Example(BaseModel):
    title: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    example_type: str = "worked_example"
    semantic_description: str = ""


class Activity(BaseModel):
    id: str
    activity_type: str  # Activity / Think / Observe / Try / Discuss / Experiment
    title: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


class Figure(BaseModel):
    id: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    title: str = ""
    caption: str = ""
    figure_type: str = "figure"
    semantic_description: str = ""
    educational_purpose: str = ""
    concepts: List[str] = Field(default_factory=list)
    related_topics: List[str] = Field(default_factory=list)
    importance: str = "medium"
    difficulty: str = "medium"
    animation_candidate: bool = False
    confidence: float = 0.0


class Table(BaseModel):
    id: str
    title: str = ""
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    rows: int = 0
    columns: int = 0
    table_type: str = "data_table"
    semantic_description: str = ""
    educational_purpose: str = ""
    concepts: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class Equation(BaseModel):
    id: str
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
    pass


class Chart(Figure):
    pass


class Graph(Figure):
    pass


class Map(Figure):
    pass


class Timeline(Figure):
    pass


class Box(BaseModel):
    id: str
    box_type: str  # Did You Know / Important / Note / Remember / Case Study / Box
    title: str = ""
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


class NoteItem(BaseModel):
    id: str
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


class WarningItem(BaseModel):
    id: str
    warning_type: str  # Warning / Caution / Remember / Important
    page: Optional[int] = None
    bbox: Optional[BBox] = None
    semantic_description: str = ""


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

    schema_version: str = "1.0.0"
    extraction_metadata: ExtractionMetadata = Field(default_factory=ExtractionMetadata)
    document: DocumentInfo = Field(default_factory=DocumentInfo)
    chapter_metadata: ChapterMetadata = Field(default_factory=ChapterMetadata)
    chapter_statistics: ChapterStatistics = Field(default_factory=ChapterStatistics)
    pages: List[PageInfo] = Field(default_factory=list)
    topic_tree: List[Dict[str, Any]] = Field(default_factory=list)
    topics: List[TopicNode] = Field(default_factory=list)
    concepts: List[Concept] = Field(default_factory=list)
    glossary: List[Dict[str, Any]] = Field(default_factory=list)
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
