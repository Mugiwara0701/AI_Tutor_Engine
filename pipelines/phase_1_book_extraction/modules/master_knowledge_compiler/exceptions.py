"""
modules/master_knowledge_compiler/exceptions.py — M5.3 exception
hierarchy for the Master Knowledge Compiler.
"""
from __future__ import annotations

__all__ = [
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
]


class MasterKnowledgeCompilerError(Exception):
    """Base for all M5.3 errors."""


class GraphReadinessError(MasterKnowledgeCompilerError):
    """Raised when the input SemanticGraph is not ready for compilation."""


class ConceptCompilationError(MasterKnowledgeCompilerError):
    """Raised when concept compilation fails."""


class DependencyCompilationError(MasterKnowledgeCompilerError):
    """Raised when dependency compilation fails."""


class LearningProgressionError(MasterKnowledgeCompilerError):
    """Raised when learning progression ordering fails."""


class RetrievalIndexError(MasterKnowledgeCompilerError):
    """Raised when retrieval index compilation fails."""


class MetadataCompilationError(MasterKnowledgeCompilerError):
    """Raised when metadata compilation fails."""


class CrossReferenceError(MasterKnowledgeCompilerError):
    """Raised when cross-reference building fails."""


class StatisticsError(MasterKnowledgeCompilerError):
    """Raised when statistics computation fails."""


class SerializationError(MasterKnowledgeCompilerError):
    """Raised when Master JSON serialization fails."""


class PackageBuildError(MasterKnowledgeCompilerError):
    """Raised when the MasterKnowledgePackage cannot be assembled."""


class PackageValidationError(MasterKnowledgeCompilerError):
    """Raised when the MasterKnowledgePackage fails validation."""
