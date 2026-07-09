from .chapter_schema import (  # noqa: F401
    ChapterJSON, BBox, ExtractionMetadata, DocumentInfo, ChapterMetadata,
    ChapterStatistics, PageInfo, TopicNode, Concept, Definition, Example,
    Activity, Figure, Table, Equation, Diagram, Chart, Graph, Map, Timeline,
    Box, NoteItem, WarningItem, GraphEdge, LearningGraph, ConceptGraph,
    SemanticIndexEntry, AIMetadata, GenerationMetadata, QualityScores,
    ExtractionLogs,
)

# A1.1 -- schema-layer-only addition. Not yet used by any existing schema
# (no migration performed); exported here so it's importable as
# `schemas.CanonicalObjectBase` ahead of later migration work.
from .canonical_base import (  # noqa: F401
    CanonicalObjectBase, Provenance, CreationMetadata,
)