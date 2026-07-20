"""
modules/master_knowledge_compiler — M5.3: the Master Knowledge Compiler.

Transforms a SemanticGraph (M5.2E) into the Master Knowledge Package —
the primary offline knowledge artifact for Phase 2.

Builds strictly additively on top of six frozen milestones:

- M5.1 (`modules.educational_object_framework`) — reuses
  ValidationResult / ValidationDiagnostic / DiagnosticSeverity / SUCCESS.
- M5.2A–M5.2C — consumed indirectly through the SemanticGraph snapshot.
- M5.2D (`modules.semantic_interpretation_engine`) — SemanticNode fields
  (semantic_role, object_type_key, node_id) are read; never modified.
- M5.2E (`modules.relationship_discovery_engine`) — SemanticGraph is the
  sole input; SemanticNode.node_id values are used as primary keys without
  regeneration.

Out of scope: LLM integration, Teacher Brain, Adaptive Tutoring,
Knowledge Graph reasoning, Personalized Learning (Phase 2+).
"""
from __future__ import annotations

# --- Enums ---
from modules.master_knowledge_compiler.enums import (
    CompilationOutcome,
    ConceptCategory,
    DependencyType,
    IndexType,
    PackageStatus,
    ProgressionStrategy,
    SerializationFormat,
    ValidationSeverity,
)

# --- Models ---
from modules.master_knowledge_compiler.models import (
    DEFAULT_PACKAGE_MODEL_VERSION,
    CompilerManifest,
    CompilerStatistics,
    CompilerVersion,
    ConceptEntry,
    ConceptIndex,
    ConceptStatistics,
    CrossReferenceEntry,
    CrossReferenceIndex,
    DependencyEdge,
    DependencyMap,
    DependencyStatistics,
    IndexEntry,
    LearningProgression,
    LearningStep,
    MasterKnowledgePackage,
    MetadataEntry,
    MetadataIndex,
    RetrievalIndex,
)

# --- Config ---
from modules.master_knowledge_compiler.config import (
    DEFAULT_COMPILER_VERSION,
    DEFAULT_PACKAGE_VERSION,
    MasterKnowledgeCompilerConfig,
    default_config,
)

# --- Exceptions ---
from modules.master_knowledge_compiler.exceptions import (
    ConceptCompilationError,
    CrossReferenceError,
    DependencyCompilationError,
    GraphReadinessError,
    LearningProgressionError,
    MasterKnowledgeCompilerError,
    MetadataCompilationError,
    PackageBuildError,
    PackageValidationError,
    RetrievalIndexError,
    SerializationError,
    StatisticsError,
)

# --- Graph Validation (Deliverable #1) ---
from modules.master_knowledge_compiler.graph_validator import (
    GraphReadinessValidator,
    default_graph_readiness_validator,
)

# --- Concept Compiler (Deliverable #2) ---
from modules.master_knowledge_compiler.concept_compiler import (
    ROLE_TO_CATEGORY,
    TYPE_TO_CATEGORY,
    ConceptCompiler,
    default_concept_compiler,
)

# --- Dependency Compiler (Deliverable #3) ---
from modules.master_knowledge_compiler.dependency_compiler import (
    DEPENDENCY_RELATIONSHIP_TYPES,
    DependencyCompiler,
    default_dependency_compiler,
)

# --- Learning Progression Compiler (Deliverable #4) ---
from modules.master_knowledge_compiler.learning_compiler import (
    LearningProgressionCompiler,
    default_learning_compiler,
)

# --- Retrieval Index Compiler (Deliverable #5) ---
from modules.master_knowledge_compiler.retrieval_compiler import (
    RetrievalIndexCompiler,
    default_retrieval_compiler,
)

# --- Metadata Compiler (Deliverable #6) ---
from modules.master_knowledge_compiler.metadata_compiler import (
    MetadataCompiler,
    default_metadata_compiler,
)

# --- Cross Reference Builder (Deliverable #7) ---
from modules.master_knowledge_compiler.cross_reference_builder import (
    CrossReferenceBuilder,
    default_cross_reference_builder,
)

# --- Compiler Statistics (Deliverable #8) ---
from modules.master_knowledge_compiler.statistics import (
    CompilerStatisticsBuilder,
    default_statistics_builder,
)

# --- Serializer (Deliverable #10) ---
from modules.master_knowledge_compiler.serializer import (
    MasterJSONSerializer,
    SerializationResult,
    default_serializer,
)

# --- Engine ---
from modules.master_knowledge_compiler.engine import (
    MasterKnowledgeCompiler,
    compile_graph,
    default_compiler,
)

# --- Validation ---
from modules.master_knowledge_compiler.validation import (
    validate_concept_index,
    validate_dependency_map,
    validate_package,
    validate_retrieval_index,
    validate_serialization,
)

__all__ = [
    # enums
    "CompilationOutcome",
    "ConceptCategory",
    "DependencyType",
    "IndexType",
    "PackageStatus",
    "ProgressionStrategy",
    "SerializationFormat",
    "ValidationSeverity",
    # models
    "ConceptEntry",
    "ConceptStatistics",
    "ConceptIndex",
    "DependencyEdge",
    "DependencyStatistics",
    "DependencyMap",
    "LearningStep",
    "LearningProgression",
    "IndexEntry",
    "RetrievalIndex",
    "MetadataEntry",
    "MetadataIndex",
    "CrossReferenceEntry",
    "CrossReferenceIndex",
    "CompilerStatistics",
    "CompilerVersion",
    "CompilerManifest",
    "MasterKnowledgePackage",
    "DEFAULT_PACKAGE_MODEL_VERSION",
    # config
    "MasterKnowledgeCompilerConfig",
    "default_config",
    "DEFAULT_COMPILER_VERSION",
    "DEFAULT_PACKAGE_VERSION",
    # exceptions
    "MasterKnowledgeCompilerError",
    "GraphReadinessError",
    "ConceptCompilationError",
    "DependencyCompilationError",
    "LearningProgressionError",
    "RetrievalIndexError",
    "MetadataCompilationError",
    "CrossReferenceError",
    "StatisticsError",
    "SerializationError",
    "PackageBuildError",
    "PackageValidationError",
    # graph validation (Deliverable #1)
    "GraphReadinessValidator",
    "default_graph_readiness_validator",
    # concept compiler (Deliverable #2)
    "ConceptCompiler",
    "default_concept_compiler",
    "ROLE_TO_CATEGORY",
    "TYPE_TO_CATEGORY",
    # dependency compiler (Deliverable #3)
    "DependencyCompiler",
    "default_dependency_compiler",
    "DEPENDENCY_RELATIONSHIP_TYPES",
    # learning compiler (Deliverable #4)
    "LearningProgressionCompiler",
    "default_learning_compiler",
    # retrieval compiler (Deliverable #5)
    "RetrievalIndexCompiler",
    "default_retrieval_compiler",
    # metadata compiler (Deliverable #6)
    "MetadataCompiler",
    "default_metadata_compiler",
    # cross reference builder (Deliverable #7)
    "CrossReferenceBuilder",
    "default_cross_reference_builder",
    # statistics (Deliverable #8)
    "CompilerStatisticsBuilder",
    "default_statistics_builder",
    # serializer (Deliverable #10)
    "MasterJSONSerializer",
    "SerializationResult",
    "default_serializer",
    # engine
    "MasterKnowledgeCompiler",
    "default_compiler",
    "compile_graph",
    # validation
    "validate_concept_index",
    "validate_dependency_map",
    "validate_retrieval_index",
    "validate_package",
    "validate_serialization",
]


# Milestone 5.5: state module export, following the set_current_*()/
# get_current_*()/has_current_*()/reset_*_state() pattern every other phase uses.
from modules.master_knowledge_compiler import state  # noqa: F401
