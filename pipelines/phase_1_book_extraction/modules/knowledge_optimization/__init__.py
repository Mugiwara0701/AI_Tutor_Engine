"""
modules/knowledge_optimization — M5.4: Knowledge Optimization &
Intelligence Preparation Layer.

Transforms a MasterKnowledgePackage (M5.3) into an
OptimizedKnowledgePackage ready for Phase 2.

Builds strictly additively on top of frozen milestones:
- M5.1 — reuses ValidationResult / ValidationDiagnostic / SUCCESS.
- M5.2E — SemanticGraph models consumed indirectly via M5.3.
- M5.3  — MasterKnowledgePackage is the sole input; never modified.
"""
from __future__ import annotations

# Enums
from modules.knowledge_optimization.enums import (
    AnalyticsMetric, CacheType, LinkType, OptimizationOutcome,
    OptimizationStatus, QualityIssueSeverity, QualityIssueType,
    SearchIndexType,
)
# Models
from modules.knowledge_optimization.models import (
    DEFAULT_OPTIMIZED_MODEL_VERSION,
    CacheEntry, ConceptAnalytics, CrossChapterLink, CrossChapterLinkIndex,
    KnowledgeQualityReport, LearningAnalytics, OptimizationManifest,
    OptimizationStatistics, OptimizedIndexEntry, OptimizedKnowledgePackage,
    OptimizedRetrievalIndex, QualityIssue, RuntimeCache, SearchEntry,
    SemanticSearchIndex,
)
# Config
from modules.knowledge_optimization.config import (
    DEFAULT_OPTIMIZER_VERSION, DEFAULT_OPTIMIZED_PACKAGE_VERSION,
    KnowledgeOptimizationConfig, default_config,
)
# Exceptions
from modules.knowledge_optimization.exceptions import (
    CrossChapterLinkerError, KnowledgeOptimizationError,
    KnowledgeOptimizerError, LearningAnalyticsError,
    OptimizationSerializationError, OptimizedPackageBuildError,
    PackageValidationError, QualityAnalysisError,
    RetrievalOptimizationError, RuntimeCacheError, SemanticSearchError,
)
# Deliverable #1
from modules.knowledge_optimization.package_validator import (
    PackageValidator, default_package_validator,
)
# Deliverable #2
from modules.knowledge_optimization.knowledge_optimizer import (
    KnowledgeOptimizer, default_knowledge_optimizer,
)
# Deliverable #3
from modules.knowledge_optimization.cross_chapter_linker import (
    CrossChapterLinker, default_cross_chapter_linker,
)
# Deliverable #5
from modules.knowledge_optimization.semantic_search_builder import (
    SemanticSearchBuilder, default_semantic_search_builder,
)
# Deliverable #6
from modules.knowledge_optimization.runtime_cache_builder import (
    RuntimeCacheBuilder, default_runtime_cache_builder,
)
# Deliverable #7
from modules.knowledge_optimization.learning_analytics_builder import (
    LearningAnalyticsBuilder, default_learning_analytics_builder,
)
# Deliverable #8
from modules.knowledge_optimization.quality_analyzer import (
    KnowledgeQualityAnalyzer, default_quality_analyzer,
)
# Deliverable #10
from modules.knowledge_optimization.serializer import (
    OptimizationSerializer, SerializationResult, default_serializer,
)
# Engine
from modules.knowledge_optimization.engine import (
    KnowledgeOptimizationEngine, default_engine, optimize,
)
# Validation
from modules.knowledge_optimization.validation import (
    validate_analytics, validate_optimized_package,
    validate_retrieval_index, validate_runtime_cache,
    validate_serialization,
)

__all__ = [
    # enums
    "OptimizationOutcome", "LinkType", "CacheType", "AnalyticsMetric",
    "QualityIssueType", "QualityIssueSeverity", "SearchIndexType", "OptimizationStatus",
    # models
    "CrossChapterLink", "CrossChapterLinkIndex",
    "OptimizedIndexEntry", "OptimizedRetrievalIndex",
    "SearchEntry", "SemanticSearchIndex",
    "CacheEntry", "RuntimeCache",
    "ConceptAnalytics", "LearningAnalytics",
    "QualityIssue", "KnowledgeQualityReport",
    "OptimizationManifest", "OptimizationStatistics",
    "OptimizedKnowledgePackage",
    "DEFAULT_OPTIMIZED_MODEL_VERSION",
    # config
    "KnowledgeOptimizationConfig", "default_config",
    "DEFAULT_OPTIMIZER_VERSION", "DEFAULT_OPTIMIZED_PACKAGE_VERSION",
    # exceptions
    "KnowledgeOptimizationError", "PackageValidationError",
    "KnowledgeOptimizerError", "CrossChapterLinkerError",
    "RetrievalOptimizationError", "SemanticSearchError",
    "RuntimeCacheError", "LearningAnalyticsError",
    "QualityAnalysisError", "OptimizedPackageBuildError",
    "OptimizationSerializationError",
    # deliverables
    "PackageValidator", "default_package_validator",
    "KnowledgeOptimizer", "default_knowledge_optimizer",
    "CrossChapterLinker", "default_cross_chapter_linker",
    "SemanticSearchBuilder", "default_semantic_search_builder",
    "RuntimeCacheBuilder", "default_runtime_cache_builder",
    "LearningAnalyticsBuilder", "default_learning_analytics_builder",
    "KnowledgeQualityAnalyzer", "default_quality_analyzer",
    "OptimizationSerializer", "SerializationResult", "default_serializer",
    # engine
    "KnowledgeOptimizationEngine", "default_engine", "optimize",
    # validation
    "validate_optimized_package", "validate_retrieval_index",
    "validate_runtime_cache", "validate_analytics", "validate_serialization",
]


# Milestone 5.5: state module export.
from modules.knowledge_optimization import state  # noqa: F401
