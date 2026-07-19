"""
modules/relationship_discovery_engine — M5.2E: the Relationship
Discovery & Semantic Graph Engine.

The FINAL milestone of the M5.2 Educational Semantic Intelligence
Layer.  Builds strictly additively on top of five frozen milestones:

- M5.1 (`modules.educational_object_framework`) — reuses
  ValidationResult / ValidationDiagnostic / DiagnosticSeverity / SUCCESS
  directly; never duplicates them.
- M5.2A (`modules.educational_taxonomy`) — reads EducationalObjectType
  keys via SemanticObject.object_type_key; never modifies TaxonomyRegistry.
- M5.2B (`modules.subject_profile_framework`) — reads
  SubjectContribution relationship_hints indirectly via the
  SemanticEnrichmentResult.structural_snapshot; never writes back.
- M5.2C (`modules.structural_understanding_engine`) — consumed
  indirectly via SemanticEnrichmentResult.structural_snapshot; never
  modifies M5.2C.
- M5.2D (`modules.semantic_interpretation_engine`) — consumes
  SemanticEnrichmentResult and SemanticAnchor as primary inputs; uses
  SemanticAnchor.anchor_id as immutable graph node IDs (never
  regenerated); never modifies M5.2D.

Out of scope: Knowledge Graph reasoning, LLM integration, Master JSON
generation, Teacher Brain, Adaptive tutoring (M5.3+).

Public API:

    Enums:
        RelationshipType, RelationshipDirection, DiscoveryOutcome,
        GraphBuildOutcome, NormalizationStrategy, GraphExportFormat,
        NodeStatus, EdgeStatus                              — enums.py

    Models:
        RelationshipEvidence, RelationshipConfidence
        SemanticRelationship, RelationshipDiscoveryResult
        SemanticNode, SemanticEdge, GraphMetadata, GraphStatistics,
        SemanticGraph
        DEFAULT_GRAPH_VERSION                               — models.py

    Config:
        RelationshipDiscoveryEngineConfig, default_config,
        DEFAULT_ENGINE_VERSION                              — config.py

    Exceptions:
        RelationshipDiscoveryError and subclasses           — exceptions.py

    Rules:
        RelationshipRule, RELATIONSHIP_RULES, lookup_rule   — rules.py

    Relationship Discovery (Deliverable #1):
        RelationshipResolver, default_relationship_resolver — relationship_resolver.py
        RelationshipClassifier, default_relationship_classifier
                                                            — relationship_classifier.py
        RelationshipBuilder, default_relationship_builder,
        RELATIONSHIP_NAMESPACE                              — relationship_builder.py

    Relationship Validation (Deliverable #2):
        RelationshipValidator, default_relationship_validator
                                                            — relationship_validator.py

    Confidence Propagation (Deliverable #3):
        ConfidencePropagator, default_confidence_propagator — confidence_propagator.py

    Graph Construction (Deliverable #4):
        SemanticGraphBuilder, default_graph_builder,
        GRAPH_NAMESPACE                                     — graph_builder.py

    Graph Normalization (Deliverable #5):
        GraphNormalizer, default_graph_normalizer           — graph_normalizer.py

    Graph Validation (Deliverable #6):
        GraphIntegrityValidator, default_graph_integrity_validator
                                                            — graph_integrity_validator.py

    Graph Export (Deliverable #7):
        GraphExporter, GraphExportArtifact, default_graph_exporter
                                                            — graph_exporter.py

    Engine:
        RelationshipDiscoveryEngine, default_engine, discover
                                                            — engine.py

    Validation:
        validate_discovery_result, validate_graph_export_ready,
        validate_confidence_propagation                     — validation.py
"""
from __future__ import annotations

# --- Enums ---
from modules.relationship_discovery_engine.enums import (
    DiscoveryOutcome,
    EdgeStatus,
    GraphBuildOutcome,
    GraphExportFormat,
    NodeStatus,
    NormalizationStrategy,
    RelationshipDirection,
    RelationshipType,
)

# --- Models ---
from modules.relationship_discovery_engine.models import (
    DEFAULT_GRAPH_VERSION,
    GraphMetadata,
    GraphStatistics,
    RelationshipConfidence,
    RelationshipDiscoveryResult,
    RelationshipEvidence,
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
    SemanticRelationship,
)

# --- Config ---
from modules.relationship_discovery_engine.config import (
    DEFAULT_ENGINE_VERSION,
    RelationshipDiscoveryEngineConfig,
    default_config,
)

# --- Exceptions ---
from modules.relationship_discovery_engine.exceptions import (
    ConfidencePropagationError,
    GraphBuildError,
    GraphExportError,
    GraphIntegrityError,
    GraphNormalizationError,
    RelationshipClassificationError,
    RelationshipDiscoveryEngineError,
    RelationshipDiscoveryError,
    RelationshipResolutionError,
    RelationshipValidationError,
)

# --- Rules ---
from modules.relationship_discovery_engine.rules import (
    RELATIONSHIP_RULES,
    RelationshipRule,
    lookup_rule,
)

# --- Relationship Discovery (Deliverable #1) ---
from modules.relationship_discovery_engine.relationship_resolver import (
    RelationshipResolver,
    default_relationship_resolver,
)
from modules.relationship_discovery_engine.relationship_classifier import (
    ClassificationResult,
    RelationshipClassifier,
    default_relationship_classifier,
)
from modules.relationship_discovery_engine.relationship_builder import (
    RELATIONSHIP_NAMESPACE,
    RelationshipBuilder,
    default_relationship_builder,
)

# --- Relationship Validation (Deliverable #2) ---
from modules.relationship_discovery_engine.relationship_validator import (
    RelationshipValidator,
    default_relationship_validator,
)

# --- Confidence Propagation (Deliverable #3) ---
from modules.relationship_discovery_engine.confidence_propagator import (
    ConfidencePropagator,
    default_confidence_propagator,
)

# --- Graph Construction (Deliverable #4) ---
from modules.relationship_discovery_engine.graph_builder import (
    GRAPH_NAMESPACE,
    SemanticGraphBuilder,
    default_graph_builder,
)

# --- Graph Normalization (Deliverable #5) ---
from modules.relationship_discovery_engine.graph_normalizer import (
    GraphNormalizer,
    default_graph_normalizer,
)

# --- Graph Validation (Deliverable #6) ---
from modules.relationship_discovery_engine.graph_integrity_validator import (
    GraphIntegrityValidator,
    default_graph_integrity_validator,
)

# --- Graph Export (Deliverable #7) ---
from modules.relationship_discovery_engine.graph_exporter import (
    GraphExportArtifact,
    GraphExporter,
    default_graph_exporter,
)

# --- Engine ---
from modules.relationship_discovery_engine.engine import (
    RelationshipDiscoveryEngine,
    default_engine,
    discover,
)

# --- Validation ---
from modules.relationship_discovery_engine.validation import (
    validate_confidence_propagation,
    validate_discovery_result,
    validate_graph_export_ready,
)

__all__ = [
    # enums
    "RelationshipType",
    "RelationshipDirection",
    "DiscoveryOutcome",
    "GraphBuildOutcome",
    "NormalizationStrategy",
    "GraphExportFormat",
    "NodeStatus",
    "EdgeStatus",
    # models
    "RelationshipEvidence",
    "RelationshipConfidence",
    "SemanticRelationship",
    "RelationshipDiscoveryResult",
    "SemanticNode",
    "SemanticEdge",
    "GraphMetadata",
    "GraphStatistics",
    "SemanticGraph",
    "DEFAULT_GRAPH_VERSION",
    # config
    "RelationshipDiscoveryEngineConfig",
    "default_config",
    "DEFAULT_ENGINE_VERSION",
    # exceptions
    "RelationshipDiscoveryError",
    "RelationshipResolutionError",
    "RelationshipClassificationError",
    "RelationshipValidationError",
    "ConfidencePropagationError",
    "GraphBuildError",
    "GraphNormalizationError",
    "GraphIntegrityError",
    "GraphExportError",
    "RelationshipDiscoveryEngineError",
    # rules
    "RelationshipRule",
    "RELATIONSHIP_RULES",
    "lookup_rule",
    # relationship discovery (Deliverable #1)
    "RelationshipResolver",
    "default_relationship_resolver",
    "ClassificationResult",
    "RelationshipClassifier",
    "default_relationship_classifier",
    "RELATIONSHIP_NAMESPACE",
    "RelationshipBuilder",
    "default_relationship_builder",
    # relationship validation (Deliverable #2)
    "RelationshipValidator",
    "default_relationship_validator",
    # confidence propagation (Deliverable #3)
    "ConfidencePropagator",
    "default_confidence_propagator",
    # graph construction (Deliverable #4)
    "SemanticGraphBuilder",
    "default_graph_builder",
    "GRAPH_NAMESPACE",
    # graph normalization (Deliverable #5)
    "GraphNormalizer",
    "default_graph_normalizer",
    # graph validation (Deliverable #6)
    "GraphIntegrityValidator",
    "default_graph_integrity_validator",
    # graph export (Deliverable #7)
    "GraphExporter",
    "GraphExportArtifact",
    "default_graph_exporter",
    # engine
    "RelationshipDiscoveryEngine",
    "default_engine",
    "discover",
    # validation
    "validate_discovery_result",
    "validate_graph_export_ready",
    "validate_confidence_propagation",
]
