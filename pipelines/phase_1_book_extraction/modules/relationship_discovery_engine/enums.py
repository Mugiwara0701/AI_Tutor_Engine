"""
modules/relationship_discovery_engine/enums.py — M5.2E: enumerated
vocabularies for the Relationship Discovery & Semantic Graph Engine.

All enums are str-based for JSON-serialization consistency with the
conventions established by M5.1 through M5.2D.
"""
from __future__ import annotations

from enum import Enum

__all__ = [
    "RelationshipType",
    "RelationshipDirection",
    "DiscoveryOutcome",
    "GraphBuildOutcome",
    "NormalizationStrategy",
    "GraphExportFormat",
    "NodeStatus",
    "EdgeStatus",
]


class RelationshipType(str, Enum):
    """
    The educational relationship type between two semantic objects.
    These map onto standard pedagogical link types used in knowledge
    representation and learning graph design.
    """

    # Knowledge relations
    DEFINES = "defines"                       # Definition → Concept
    REQUIRES = "requires"                     # Concept → Prerequisite
    ILLUSTRATES = "illustrates"               # Example → Concept
    EXPLAINS = "explains"                     # Figure → Concept
    SUPPORTS = "supports"                     # Experiment → Scientific Principle
    IMPLEMENTS = "implements"                 # Procedure → Method
    EVALUATES = "evaluates"                   # Assessment → Learning Objective
    EXTENDS = "extends"                       # Advanced Topic → Base Concept
    CONTRADICTS = "contradicts"               # Misconception → Concept
    SEQUENCES = "sequences"                   # Step A → Step B
    TRANSFERS = "transfers"                   # Transfer Task → Concept
    CONTEXTUALIZES = "contextualizes"         # Context → Concept
    REFERENCES = "references"                 # Cross-reference
    SUMMARIZES = "summarizes"                 # Summary → Content

    # Generic fallback
    RELATED_TO = "related_to"


class RelationshipDirection(str, Enum):
    """
    The directionality of a SemanticRelationship.
    """

    FORWARD = "forward"       # source → target (canonical direction)
    REVERSE = "reverse"       # target → source
    BIDIRECTIONAL = "bidirectional"


class DiscoveryOutcome(str, Enum):
    """
    Outcome of a RelationshipDiscoveryEngine run over a set of
    SemanticEnrichmentResults.
    """

    COMPLETE = "complete"       # All pairs processed, relationships discovered
    PARTIAL = "partial"         # Some pairs skipped (low confidence / unrecognized)
    EMPTY = "empty"             # No relationships discovered (e.g. single object)
    ERROR = "error"             # Unrecoverable error during discovery


class GraphBuildOutcome(str, Enum):
    """
    Outcome of the SemanticGraphBuilder run.
    """

    COMPLETE = "complete"         # Full graph built and validated
    PARTIAL = "partial"           # Graph built with some normalization warnings
    EMPTY = "empty"               # No nodes or edges could be built
    VALIDATION_FAILED = "validation_failed"
    ERROR = "error"


class NormalizationStrategy(str, Enum):
    """
    Strategy applied when normalizing duplicate or conflicting edges.
    """

    KEEP_HIGHEST_CONFIDENCE = "keep_highest_confidence"
    MERGE_EVIDENCE = "merge_evidence"
    KEEP_FIRST = "keep_first"


class GraphExportFormat(str, Enum):
    """
    Output format for GraphExporter.
    """

    DICT = "dict"       # Plain Python dict (default, fully serializable)
    JSON = "json"       # JSON string


class NodeStatus(str, Enum):
    """
    Validation status of a SemanticNode.
    """

    VALID = "valid"
    ORPHAN = "orphan"         # No edges connect to this node
    BROKEN_REFERENCE = "broken_reference"


class EdgeStatus(str, Enum):
    """
    Validation status of a SemanticEdge.
    """

    VALID = "valid"
    DUPLICATE = "duplicate"
    BROKEN_SOURCE = "broken_source"
    BROKEN_TARGET = "broken_target"
    LOW_CONFIDENCE = "low_confidence"
