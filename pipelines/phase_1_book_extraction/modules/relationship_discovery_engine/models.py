"""
modules/relationship_discovery_engine/models.py — M5.2E: the core
immutable, versioned, serializable relationship and graph data models.

Design philosophy:
- Every model is a frozen dataclass (immutable after construction).
- Every model exposes `to_dict()` for deterministic JSON serialization.
- No model subclasses or modifies any M5.1–M5.2D model.
- SemanticAnchor.anchor_id (from M5.2D) is used as the node identifier
  in the graph — never regenerated.
- SemanticGraph is the final output for M5.3 consumption.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from modules.relationship_discovery_engine.enums import (
    DiscoveryOutcome,
    EdgeStatus,
    GraphBuildOutcome,
    GraphExportFormat,
    NodeStatus,
    RelationshipDirection,
    RelationshipType,
)
from modules.relationship_discovery_engine.exceptions import RelationshipDiscoveryError

__all__ = [
    # Confidence
    "RelationshipEvidence",
    "RelationshipConfidence",
    # Relationships
    "SemanticRelationship",
    "RelationshipDiscoveryResult",
    # Graph
    "SemanticNode",
    "SemanticEdge",
    "GraphMetadata",
    "GraphStatistics",
    "SemanticGraph",
    # Version
    "DEFAULT_GRAPH_VERSION",
]

DEFAULT_GRAPH_VERSION = "1.0.0"


def _frozen_tuple(value) -> tuple:
    if value is None:
        return ()
    return tuple(value)


def _frozen_mapping(value) -> Mapping[str, Any]:
    if value is None:
        return {}
    return dict(value)


# ---------------------------------------------------------------------------
# Confidence models (Deliverable #3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelationshipEvidence:
    """
    A single piece of evidence contributing to a RelationshipConfidence.

    Attributes:
        label:    Short label (e.g. "source_role_match").
        weight:   Contribution weight in [0.0, 1.0].
        passed:   Whether this evidence item was satisfied.
        detail:   Optional explanatory note.
    """

    label: str
    weight: float
    passed: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise RelationshipDiscoveryError("RelationshipEvidence.label must not be empty.")
        if not 0.0 <= self.weight <= 1.0:
            raise RelationshipDiscoveryError(
                f"RelationshipEvidence.weight must be in [0.0, 1.0]; got {self.weight!r}."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "weight": self.weight,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RelationshipConfidence:
    """
    Confidence in a SemanticRelationship, derived from:
    - source SemanticAnchor confidence
    - target SemanticAnchor confidence
    - discovery evidence

    Attributes:
        value:              Aggregate score in [0.0, 1.0].
        source_confidence:  Source anchor confidence value.
        target_confidence:  Target anchor confidence value.
        evidence:           Evidence items that produced the score.
    """

    value: float
    source_confidence: float
    target_confidence: float
    evidence: Tuple[RelationshipEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise RelationshipDiscoveryError(
                f"RelationshipConfidence.value must be in [0.0, 1.0]; got {self.value!r}."
            )
        object.__setattr__(self, "evidence", _frozen_tuple(self.evidence))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source_confidence": self.source_confidence,
            "target_confidence": self.target_confidence,
            "evidence": [e.to_dict() for e in self.evidence],
        }


# ---------------------------------------------------------------------------
# Relationship models (Deliverable #1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticRelationship:
    """
    An immutable, directional semantic relationship between two
    educational objects identified by their SemanticAnchor IDs.

    M5.2D's SemanticAnchor.anchor_id values are used as source/target.
    They are NEVER regenerated here.

    Attributes:
        relationship_id:    Deterministic UUID5 for this relationship edge.
        source_anchor_id:   anchor_id of the source SemanticAnchor (M5.2D).
        target_anchor_id:   anchor_id of the target SemanticAnchor (M5.2D).
        relationship_type:  The educational relationship type.
        direction:          Canonical edge direction.
        confidence:         RelationshipConfidence for this edge.
        discovery_rule:     The rule key that produced this relationship.
        metadata:           Pass-through metadata (frozen mapping).
        version:            Schema version.
    """

    relationship_id: str
    source_anchor_id: str
    target_anchor_id: str
    relationship_type: RelationshipType
    direction: RelationshipDirection
    confidence: RelationshipConfidence
    discovery_rule: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_GRAPH_VERSION

    def __post_init__(self) -> None:
        if not self.relationship_id:
            raise RelationshipDiscoveryError("SemanticRelationship.relationship_id must not be empty.")
        if not self.source_anchor_id:
            raise RelationshipDiscoveryError("SemanticRelationship.source_anchor_id must not be empty.")
        if not self.target_anchor_id:
            raise RelationshipDiscoveryError("SemanticRelationship.target_anchor_id must not be empty.")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_anchor_id": self.source_anchor_id,
            "target_anchor_id": self.target_anchor_id,
            "relationship_type": self.relationship_type.value,
            "direction": self.direction.value,
            "confidence": self.confidence.to_dict(),
            "discovery_rule": self.discovery_rule,
            "metadata": dict(self.metadata),
            "version": self.version,
        }


@dataclass(frozen=True)
class RelationshipDiscoveryResult:
    """
    Top-level output of the RelationshipDiscoveryEngine for a set of
    SemanticEnrichmentResults.

    Attributes:
        outcome:            Overall discovery outcome.
        relationships:      All discovered SemanticRelationship objects.
        object_keys:        The object_keys processed.
        diagnostics:        Ordered diagnostic strings.
        version:            Result schema version.
    """

    outcome: DiscoveryOutcome
    relationships: Tuple[SemanticRelationship, ...]
    object_keys: Tuple[str, ...]
    diagnostics: Tuple[str, ...]
    version: str = DEFAULT_GRAPH_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "relationships", _frozen_tuple(self.relationships))
        object.__setattr__(self, "object_keys", _frozen_tuple(self.object_keys))
        object.__setattr__(self, "diagnostics", _frozen_tuple(self.diagnostics))

    def is_complete(self) -> bool:
        return self.outcome == DiscoveryOutcome.COMPLETE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "relationships": [r.to_dict() for r in self.relationships],
            "object_keys": list(self.object_keys),
            "diagnostics": list(self.diagnostics),
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Graph models (Deliverable #4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticNode:
    """
    A node in the SemanticGraph, backed by a M5.2D SemanticAnchor.

    The node_id is the SemanticAnchor.anchor_id — never regenerated.

    Attributes:
        node_id:            SemanticAnchor.anchor_id (M5.2D, never regenerated).
        object_key:         The educational object's key.
        object_type_key:    The EducationalObjectType key.
        semantic_role:      The dominant SemanticRole (as string value).
        confidence:         Anchor confidence value.
        pattern_key:        Structural pattern key (may be None).
        status:             Validation status (VALID / ORPHAN / BROKEN_REFERENCE).
        metadata:           Pass-through metadata.
        version:            Schema version.
    """

    node_id: str
    object_key: str
    object_type_key: str
    semantic_role: str
    confidence: float
    pattern_key: Optional[str] = None
    status: NodeStatus = NodeStatus.VALID
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_GRAPH_VERSION

    def __post_init__(self) -> None:
        if not self.node_id:
            raise RelationshipDiscoveryError("SemanticNode.node_id must not be empty.")
        if not self.object_key:
            raise RelationshipDiscoveryError("SemanticNode.object_key must not be empty.")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "object_key": self.object_key,
            "object_type_key": self.object_type_key,
            "semantic_role": self.semantic_role,
            "confidence": self.confidence,
            "pattern_key": self.pattern_key,
            "status": self.status.value,
            "metadata": dict(self.metadata),
            "version": self.version,
        }


@dataclass(frozen=True)
class SemanticEdge:
    """
    A directed edge in the SemanticGraph.

    Attributes:
        edge_id:            Matches SemanticRelationship.relationship_id.
        source_node_id:     Source SemanticNode.node_id.
        target_node_id:     Target SemanticNode.node_id.
        relationship_type:  RelationshipType value string.
        direction:          RelationshipDirection value string.
        confidence:         Aggregate confidence value.
        discovery_rule:     The rule that produced this edge.
        status:             Validation status.
        version:            Schema version.
    """

    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship_type: str
    direction: str
    confidence: float
    discovery_rule: str = ""
    status: EdgeStatus = EdgeStatus.VALID
    version: str = DEFAULT_GRAPH_VERSION

    def __post_init__(self) -> None:
        if not self.edge_id:
            raise RelationshipDiscoveryError("SemanticEdge.edge_id must not be empty.")
        if not self.source_node_id:
            raise RelationshipDiscoveryError("SemanticEdge.source_node_id must not be empty.")
        if not self.target_node_id:
            raise RelationshipDiscoveryError("SemanticEdge.target_node_id must not be empty.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relationship_type": self.relationship_type,
            "direction": self.direction,
            "confidence": self.confidence,
            "discovery_rule": self.discovery_rule,
            "status": self.status.value,
            "version": self.version,
        }


@dataclass(frozen=True)
class GraphMetadata:
    """
    Metadata for a SemanticGraph.

    Attributes:
        graph_id:       Deterministic UUID5 from the sorted set of node_ids.
        engine_version: The M5.2E engine version that produced this graph.
        source_count:   Number of SemanticEnrichmentResults consumed.
        description:    Optional description.
        version:        Graph schema version.
    """

    graph_id: str
    engine_version: str
    source_count: int
    description: str = ""
    version: str = DEFAULT_GRAPH_VERSION

    def __post_init__(self) -> None:
        if not self.graph_id:
            raise RelationshipDiscoveryError("GraphMetadata.graph_id must not be empty.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "engine_version": self.engine_version,
            "source_count": self.source_count,
            "description": self.description,
            "version": self.version,
        }


@dataclass(frozen=True)
class GraphStatistics:
    """
    Aggregate statistics for a SemanticGraph.

    Attributes:
        node_count:         Total number of SemanticNodes.
        edge_count:         Total number of SemanticEdges.
        orphan_count:       Nodes with no edges.
        duplicate_edges_removed:
                            Edges removed during normalization.
        relationship_type_counts:
                            Mapping of RelationshipType.value → count.
        average_confidence: Mean edge confidence.
        min_confidence:     Minimum edge confidence.
        max_confidence:     Maximum edge confidence.
    """

    node_count: int
    edge_count: int
    orphan_count: int = 0
    duplicate_edges_removed: int = 0
    relationship_type_counts: Mapping[str, int] = field(default_factory=dict)
    average_confidence: float = 0.0
    min_confidence: float = 0.0
    max_confidence: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "relationship_type_counts",
            _frozen_mapping(self.relationship_type_counts)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "orphan_count": self.orphan_count,
            "duplicate_edges_removed": self.duplicate_edges_removed,
            "relationship_type_counts": dict(self.relationship_type_counts),
            "average_confidence": self.average_confidence,
            "min_confidence": self.min_confidence,
            "max_confidence": self.max_confidence,
        }


@dataclass(frozen=True)
class SemanticGraph:
    """
    The canonical semantic graph — the final output of M5.2E and the
    input to M5.3.

    All node IDs are SemanticAnchor.anchor_id values from M5.2D.
    They are never regenerated here.

    Attributes:
        nodes:      Tuple of SemanticNode objects (ordered by node_id).
        edges:      Tuple of SemanticEdge objects (ordered by edge_id).
        metadata:   GraphMetadata for this graph instance.
        statistics: GraphStatistics aggregate.
        outcome:    GraphBuildOutcome.
        diagnostics: Ordered diagnostic strings from build + validation.
        version:    Graph schema version.
    """

    nodes: Tuple[SemanticNode, ...]
    edges: Tuple[SemanticEdge, ...]
    metadata: GraphMetadata
    statistics: GraphStatistics
    outcome: GraphBuildOutcome
    diagnostics: Tuple[str, ...]
    version: str = DEFAULT_GRAPH_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", _frozen_tuple(self.nodes))
        object.__setattr__(self, "edges", _frozen_tuple(self.edges))
        object.__setattr__(self, "diagnostics", _frozen_tuple(self.diagnostics))

    def is_complete(self) -> bool:
        return self.outcome == GraphBuildOutcome.COMPLETE

    def node_ids(self) -> FrozenSet[str]:
        return frozenset(n.node_id for n in self.nodes)

    def edge_ids(self) -> FrozenSet[str]:
        return frozenset(e.edge_id for e in self.edges)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata.to_dict(),
            "statistics": self.statistics.to_dict(),
            "outcome": self.outcome.value,
            "diagnostics": list(self.diagnostics),
            "version": self.version,
        }
