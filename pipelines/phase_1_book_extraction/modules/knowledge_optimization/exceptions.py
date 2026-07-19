"""
modules/knowledge_optimization/exceptions.py — M5.4 exception hierarchy.
"""
from __future__ import annotations

__all__ = [
    "KnowledgeOptimizationError",
    "PackageValidationError",
    "KnowledgeOptimizerError",
    "CrossChapterLinkerError",
    "RetrievalOptimizationError",
    "SemanticSearchError",
    "RuntimeCacheError",
    "LearningAnalyticsError",
    "QualityAnalysisError",
    "OptimizedPackageBuildError",
    "OptimizationSerializationError",
]


class KnowledgeOptimizationError(Exception):
    """Base for all M5.4 errors."""

class PackageValidationError(KnowledgeOptimizationError):
    """Raised when the input MasterKnowledgePackage fails validation."""

class KnowledgeOptimizerError(KnowledgeOptimizationError):
    """Raised during concept deduplication / optimization."""

class CrossChapterLinkerError(KnowledgeOptimizationError):
    """Raised during cross-chapter link generation."""

class RetrievalOptimizationError(KnowledgeOptimizationError):
    """Raised during retrieval index optimization."""

class SemanticSearchError(KnowledgeOptimizationError):
    """Raised during semantic search index preparation."""

class RuntimeCacheError(KnowledgeOptimizationError):
    """Raised during runtime cache generation."""

class LearningAnalyticsError(KnowledgeOptimizationError):
    """Raised during analytics computation."""

class QualityAnalysisError(KnowledgeOptimizationError):
    """Raised during quality analysis."""

class OptimizedPackageBuildError(KnowledgeOptimizationError):
    """Raised when the OptimizedKnowledgePackage cannot be assembled."""

class OptimizationSerializationError(KnowledgeOptimizationError):
    """Raised during deterministic serialization."""
