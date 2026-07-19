"""
modules/master_knowledge_compiler/models.py — M5.3: the core
immutable, versioned, serializable compiler and package data models.

Design philosophy:
- Every model is a frozen dataclass (immutable after construction).
- Every model exposes `to_dict()` for deterministic JSON serialization.
- No model modifies any M5.1–M5.2E model.
- SemanticNode.node_id (M5.2E) is used as the primary key throughout.
  It is never regenerated.
- MasterKnowledgePackage is the final artifact for Phase 2.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from modules.master_knowledge_compiler.enums import (
    CompilationOutcome,
    ConceptCategory,
    DependencyType,
    IndexType,
    PackageStatus,
    ProgressionStrategy,
)
from modules.master_knowledge_compiler.exceptions import MasterKnowledgeCompilerError

__all__ = [
    # Concept models
    "ConceptEntry",
    "ConceptIndex",
    "ConceptStatistics",
    # Dependency models
    "DependencyEdge",
    "DependencyMap",
    "DependencyStatistics",
    # Learning progression
    "LearningStep",
    "LearningProgression",
    # Retrieval index
    "IndexEntry",
    "RetrievalIndex",
    # Metadata index
    "MetadataEntry",
    "MetadataIndex",
    # Cross reference
    "CrossReferenceEntry",
    "CrossReferenceIndex",
    # Compiler statistics (Deliverable #8)
    "CompilerStatistics",
    # Version + manifest
    "CompilerVersion",
    "CompilerManifest",
    # Master package (Deliverable #9)
    "MasterKnowledgePackage",
    # Version constant
    "DEFAULT_PACKAGE_MODEL_VERSION",
]

DEFAULT_PACKAGE_MODEL_VERSION = "1.0.0"


def _ft(value) -> tuple:
    return () if value is None else tuple(value)


def _fm(value) -> Mapping[str, Any]:
    return {} if value is None else dict(value)


# ---------------------------------------------------------------------------
# Concept models (Deliverable #2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConceptEntry:
    """
    A compiled concept entry derived from a SemanticNode (M5.2E).

    node_id is the SemanticNode.node_id (= M5.2D SemanticAnchor.anchor_id).
    It is NEVER regenerated.

    Attributes:
        node_id:            SemanticNode.node_id from M5.2E.
        object_key:         SemanticNode.object_key.
        object_type_key:    SemanticNode.object_type_key.
        semantic_role:      SemanticNode.semantic_role (string value).
        category:           Classified ConceptCategory.
        confidence:         SemanticNode.confidence.
        pattern_key:        SemanticNode.pattern_key (may be None).
        related_node_ids:   Direct neighbour node_ids from graph edges.
        version:            Schema version.
    """
    node_id: str
    object_key: str
    object_type_key: str
    semantic_role: str
    category: ConceptCategory
    confidence: float
    pattern_key: Optional[str] = None
    related_node_ids: Tuple[str, ...] = field(default_factory=tuple)
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        if not self.node_id:
            raise MasterKnowledgeCompilerError("ConceptEntry.node_id must not be empty.")
        object.__setattr__(self, "related_node_ids", _ft(self.related_node_ids))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "object_key": self.object_key,
            "object_type_key": self.object_type_key,
            "semantic_role": self.semantic_role,
            "category": self.category.value,
            "confidence": self.confidence,
            "pattern_key": self.pattern_key,
            "related_node_ids": list(self.related_node_ids),
            "version": self.version,
        }


@dataclass(frozen=True)
class ConceptStatistics:
    """Aggregate statistics for the ConceptIndex."""
    total_concepts: int
    by_category: Mapping[str, int]
    by_semantic_role: Mapping[str, int]
    average_confidence: float
    min_confidence: float
    max_confidence: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_category", _fm(self.by_category))
        object.__setattr__(self, "by_semantic_role", _fm(self.by_semantic_role))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_concepts": self.total_concepts,
            "by_category": dict(self.by_category),
            "by_semantic_role": dict(self.by_semantic_role),
            "average_confidence": self.average_confidence,
            "min_confidence": self.min_confidence,
            "max_confidence": self.max_confidence,
        }


@dataclass(frozen=True)
class ConceptIndex:
    """
    The compiled concept index — a flat, ordered tuple of ConceptEntry
    objects for direct lookup without graph traversal.
    """
    entries: Tuple[ConceptEntry, ...]
    statistics: ConceptStatistics
    outcome: CompilationOutcome
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", _ft(self.entries))

    def by_node_id(self, node_id: str) -> Optional[ConceptEntry]:
        for e in self.entries:
            if e.node_id == node_id:
                return e
        return None

    def by_category(self, category: ConceptCategory) -> Tuple[ConceptEntry, ...]:
        return tuple(e for e in self.entries if e.category == category)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "statistics": self.statistics.to_dict(),
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Dependency models (Deliverable #3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DependencyEdge:
    """A single directed dependency between two concepts."""
    source_node_id: str
    target_node_id: str
    dependency_type: DependencyType
    confidence: float
    relationship_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "dependency_type": self.dependency_type.value,
            "confidence": self.confidence,
            "relationship_id": self.relationship_id,
        }


@dataclass(frozen=True)
class DependencyStatistics:
    """Aggregate statistics for the DependencyMap."""
    total_edges: int
    total_concepts: int
    max_depth: int
    by_dependency_type: Mapping[str, int]
    has_cycles: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_dependency_type", _fm(self.by_dependency_type))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_edges": self.total_edges,
            "total_concepts": self.total_concepts,
            "max_depth": self.max_depth,
            "by_dependency_type": dict(self.by_dependency_type),
            "has_cycles": self.has_cycles,
        }


@dataclass(frozen=True)
class DependencyMap:
    """
    The compiled dependency map — all prerequisite/requires edges,
    ordered topologically.

    Attributes:
        edges:              Ordered dependency edges.
        prerequisite_map:   node_id → tuple of prerequisite node_ids.
        topological_order:  Deterministic topological ordering of node_ids.
        statistics:         Aggregate dependency statistics.
        outcome:            Compilation outcome.
    """
    edges: Tuple[DependencyEdge, ...]
    prerequisite_map: Mapping[str, Tuple[str, ...]]
    topological_order: Tuple[str, ...]
    statistics: DependencyStatistics
    outcome: CompilationOutcome
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "edges", _ft(self.edges))
        object.__setattr__(self, "topological_order", _ft(self.topological_order))
        object.__setattr__(self, "prerequisite_map", {
            k: tuple(v) for k, v in (self.prerequisite_map or {}).items()
        })

    def prerequisites_of(self, node_id: str) -> Tuple[str, ...]:
        return self.prerequisite_map.get(node_id, ())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edges": [e.to_dict() for e in self.edges],
            "prerequisite_map": {k: list(v) for k, v in self.prerequisite_map.items()},
            "topological_order": list(self.topological_order),
            "statistics": self.statistics.to_dict(),
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Learning Progression (Deliverable #4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LearningStep:
    """A single step in a LearningProgression."""
    position: int                   # 0-indexed position in sequence
    node_id: str
    object_key: str
    semantic_role: str
    concept_category: str
    prerequisite_node_ids: Tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "prerequisite_node_ids", _ft(self.prerequisite_node_ids))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "node_id": self.node_id,
            "object_key": self.object_key,
            "semantic_role": self.semantic_role,
            "concept_category": self.concept_category,
            "prerequisite_node_ids": list(self.prerequisite_node_ids),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class LearningProgression:
    """
    Deterministic ordered learning sequence.

    The sequence is produced by topological sort of the dependency graph
    (prerequisites first) with a stable tie-breaking sort on node_id.
    """
    steps: Tuple[LearningStep, ...]
    strategy: ProgressionStrategy
    total_steps: int
    outcome: CompilationOutcome
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", _ft(self.steps))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "strategy": self.strategy.value,
            "total_steps": self.total_steps,
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Retrieval Index (Deliverable #5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexEntry:
    """A single entry in a retrieval index."""
    key: str                    # The lookup key (e.g. semantic_role, taxonomy key)
    node_ids: Tuple[str, ...]   # All node_ids matching this key
    index_type: IndexType
    count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", _ft(self.node_ids))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "node_ids": list(self.node_ids),
            "index_type": self.index_type.value,
            "count": self.count,
        }


@dataclass(frozen=True)
class RetrievalIndex:
    """
    Optimized flat indexes for O(1) concept lookup without graph traversal.

    Each sub-index maps a key to a tuple of node_ids.
    """
    by_semantic_role: Mapping[str, Tuple[str, ...]]
    by_educational_role: Mapping[str, Tuple[str, ...]]
    by_taxonomy_key: Mapping[str, Tuple[str, ...]]
    by_concept_category: Mapping[str, Tuple[str, ...]]
    by_pattern_key: Mapping[str, Tuple[str, ...]]
    prerequisite_lookup: Mapping[str, Tuple[str, ...]]
    relationship_lookup: Mapping[str, Tuple[str, ...]]
    entries: Tuple[IndexEntry, ...]
    outcome: CompilationOutcome
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        def _freeze_mapping_of_tuples(m):
            return {k: tuple(v) for k, v in (m or {}).items()}

        for attr in [
            "by_semantic_role", "by_educational_role", "by_taxonomy_key",
            "by_concept_category", "by_pattern_key",
            "prerequisite_lookup", "relationship_lookup",
        ]:
            object.__setattr__(self, attr, _freeze_mapping_of_tuples(getattr(self, attr)))
        object.__setattr__(self, "entries", _ft(self.entries))

    def to_dict(self) -> Dict[str, Any]:
        def _m(d): return {k: list(v) for k, v in d.items()}
        return {
            "by_semantic_role": _m(self.by_semantic_role),
            "by_educational_role": _m(self.by_educational_role),
            "by_taxonomy_key": _m(self.by_taxonomy_key),
            "by_concept_category": _m(self.by_concept_category),
            "by_pattern_key": _m(self.by_pattern_key),
            "prerequisite_lookup": _m(self.prerequisite_lookup),
            "relationship_lookup": _m(self.relationship_lookup),
            "entries": [e.to_dict() for e in self.entries],
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Metadata Index (Deliverable #6)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetadataEntry:
    """A single structured metadata item."""
    key: str
    value: Any
    category: str       # e.g. "taxonomy", "semantic", "compiler", "version"

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value, "category": self.category}


@dataclass(frozen=True)
class MetadataIndex:
    """Compiled structured metadata — no textbook narrative."""
    taxonomy_metadata: Mapping[str, Any]
    semantic_metadata: Mapping[str, Any]
    compiler_metadata: Mapping[str, Any]
    version_metadata: Mapping[str, Any]
    entries: Tuple[MetadataEntry, ...]
    outcome: CompilationOutcome
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        for attr in ["taxonomy_metadata", "semantic_metadata",
                     "compiler_metadata", "version_metadata"]:
            object.__setattr__(self, attr, _fm(getattr(self, attr)))
        object.__setattr__(self, "entries", _ft(self.entries))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "taxonomy_metadata": dict(self.taxonomy_metadata),
            "semantic_metadata": dict(self.semantic_metadata),
            "compiler_metadata": dict(self.compiler_metadata),
            "version_metadata": dict(self.version_metadata),
            "entries": [e.to_dict() for e in self.entries],
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Cross Reference Index (Deliverable #7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CrossReferenceEntry:
    """
    Pre-resolved cross-reference for a concept node.
    All references resolve without requiring graph traversal.
    """
    node_id: str
    object_key: str
    examples: Tuple[str, ...]           # node_ids
    figures: Tuple[str, ...]            # node_ids
    experiments: Tuple[str, ...]        # node_ids
    procedures: Tuple[str, ...]         # node_ids
    assessments: Tuple[str, ...]        # node_ids
    tables: Tuple[str, ...]             # node_ids
    related: Tuple[str, ...]            # all other related node_ids

    def __post_init__(self) -> None:
        for attr in ["examples", "figures", "experiments", "procedures",
                     "assessments", "tables", "related"]:
            object.__setattr__(self, attr, _ft(getattr(self, attr)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "object_key": self.object_key,
            "examples": list(self.examples),
            "figures": list(self.figures),
            "experiments": list(self.experiments),
            "procedures": list(self.procedures),
            "assessments": list(self.assessments),
            "tables": list(self.tables),
            "related": list(self.related),
        }


@dataclass(frozen=True)
class CrossReferenceIndex:
    """Pre-resolved cross-reference map for all compiled concepts."""
    entries: Tuple[CrossReferenceEntry, ...]
    total_references: int
    outcome: CompilationOutcome
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", _ft(self.entries))

    def by_node_id(self, node_id: str) -> Optional[CrossReferenceEntry]:
        for e in self.entries:
            if e.node_id == node_id:
                return e
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "total_references": self.total_references,
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Compiler Statistics (Deliverable #8)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompilerStatistics:
    """Immutable compilation statistics."""
    total_nodes_compiled: int
    total_edges_compiled: int
    total_concepts: int
    total_dependencies: int
    total_learning_steps: int
    total_index_entries: int
    total_cross_references: int
    total_metadata_entries: int
    compilation_outcome: CompilationOutcome
    compiler_version: str
    package_version: str
    graph_node_count: int
    graph_edge_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_nodes_compiled": self.total_nodes_compiled,
            "total_edges_compiled": self.total_edges_compiled,
            "total_concepts": self.total_concepts,
            "total_dependencies": self.total_dependencies,
            "total_learning_steps": self.total_learning_steps,
            "total_index_entries": self.total_index_entries,
            "total_cross_references": self.total_cross_references,
            "total_metadata_entries": self.total_metadata_entries,
            "compilation_outcome": self.compilation_outcome.value,
            "compiler_version": self.compiler_version,
            "package_version": self.package_version,
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
        }


# ---------------------------------------------------------------------------
# Compiler Version + Manifest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompilerVersion:
    """Versioning provenance for the compiler run."""
    compiler_version: str
    package_version: str
    m5_1_version: str = "1.0.0"
    m5_2a_version: str = "1.0.0"
    m5_2b_version: str = "1.0.0"
    m5_2c_version: str = "1.0.0"
    m5_2d_version: str = "1.0.0"
    m5_2e_version: str = "1.0.0"
    m5_3_version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compiler_version": self.compiler_version,
            "package_version": self.package_version,
            "m5_1_version": self.m5_1_version,
            "m5_2a_version": self.m5_2a_version,
            "m5_2b_version": self.m5_2b_version,
            "m5_2c_version": self.m5_2c_version,
            "m5_2d_version": self.m5_2d_version,
            "m5_2e_version": self.m5_2e_version,
            "m5_3_version": self.m5_3_version,
        }


@dataclass(frozen=True)
class CompilerManifest:
    """
    Provenance manifest for a MasterKnowledgePackage.

    Attributes:
        package_id:         Deterministic UUID5 from graph_id + compiler_version.
        graph_id:           Source SemanticGraph.metadata.graph_id (M5.2E).
        graph_engine_version: Source graph engine version (M5.2E).
        graph_node_count:   Source graph node count.
        graph_edge_count:   Source graph edge count.
        compiler_version:   CompilerVersion provenance.
        diagnostics:        Compiler pipeline diagnostics.
        status:             PackageStatus.
        version:            Manifest schema version.
    """
    package_id: str
    graph_id: str
    graph_engine_version: str
    graph_node_count: int
    graph_edge_count: int
    compiler_version: CompilerVersion
    diagnostics: Tuple[str, ...]
    status: PackageStatus
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def __post_init__(self) -> None:
        if not self.package_id:
            raise MasterKnowledgeCompilerError("CompilerManifest.package_id must not be empty.")
        object.__setattr__(self, "diagnostics", _ft(self.diagnostics))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "graph_id": self.graph_id,
            "graph_engine_version": self.graph_engine_version,
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
            "compiler_version": self.compiler_version.to_dict(),
            "diagnostics": list(self.diagnostics),
            "status": self.status.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Master Knowledge Package (Deliverable #9)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MasterKnowledgePackage:
    """
    The immutable, versioned, deterministic Master Knowledge Package.

    This is the final output of M5.3 and the foundation for Phase 2
    (Teacher Brain, Adaptive Tutoring, Personalized Learning, Content
    Generation).

    All educational understanding is already compiled here. Phase 2
    consumers never need to re-run M5.1–M5.2E.

    Attributes:
        manifest:           Provenance, versioning, status.
        concept_index:      Compiled concept entries.
        dependency_map:     Prerequisite/dependency relationships.
        learning_progression: Deterministic learning sequence.
        retrieval_index:    O(1) flat indexes for all lookup dimensions.
        metadata_index:     Structured metadata (no narrative).
        cross_reference_index: Pre-resolved concept cross-references.
        statistics:         Immutable compiler statistics.
        outcome:            Overall compilation outcome.
        version:            Package schema version.
    """
    manifest: CompilerManifest
    concept_index: ConceptIndex
    dependency_map: DependencyMap
    learning_progression: LearningProgression
    retrieval_index: RetrievalIndex
    metadata_index: MetadataIndex
    cross_reference_index: CrossReferenceIndex
    statistics: CompilerStatistics
    outcome: CompilationOutcome
    version: str = DEFAULT_PACKAGE_MODEL_VERSION

    def is_complete(self) -> bool:
        return self.outcome == CompilationOutcome.COMPLETE

    def is_sealed(self) -> bool:
        return self.manifest.status == PackageStatus.SEALED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "concept_index": self.concept_index.to_dict(),
            "dependency_map": self.dependency_map.to_dict(),
            "learning_progression": self.learning_progression.to_dict(),
            "retrieval_index": self.retrieval_index.to_dict(),
            "metadata_index": self.metadata_index.to_dict(),
            "cross_reference_index": self.cross_reference_index.to_dict(),
            "statistics": self.statistics.to_dict(),
            "outcome": self.outcome.value,
            "version": self.version,
        }
