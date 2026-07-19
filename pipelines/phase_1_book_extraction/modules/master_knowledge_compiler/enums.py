"""
modules/master_knowledge_compiler/enums.py — M5.3: enumerated
vocabularies for the Master Knowledge Compiler.
"""
from __future__ import annotations

from enum import Enum

__all__ = [
    "CompilationOutcome",
    "ConceptCategory",
    "IndexType",
    "PackageStatus",
    "DependencyType",
    "ProgressionStrategy",
    "SerializationFormat",
    "ValidationSeverity",
]


class CompilationOutcome(str, Enum):
    """Overall outcome of a compiler stage or the full pipeline."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"
    VALIDATION_FAILED = "validation_failed"
    ERROR = "error"


class ConceptCategory(str, Enum):
    """
    Educational category of a compiled concept — derived from
    SemanticNode.semantic_role / object_type_key (M5.2D/M5.2E).
    Never re-interpreted here.
    """
    CONCEPT = "concept"
    DEFINITION = "definition"
    PRINCIPLE = "principle"
    LAW = "law"
    FORMULA = "formula"
    THEOREM = "theorem"
    HYPOTHESIS = "hypothesis"
    RULE = "rule"
    EXAMPLE = "example"
    FIGURE = "figure"
    TABLE = "table"
    EXPERIMENT = "experiment"
    PROCEDURE = "procedure"
    ASSESSMENT = "assessment"
    OTHER = "other"


class IndexType(str, Enum):
    """The type of a RetrievalIndex entry."""
    CONCEPT = "concept"
    SEMANTIC_ROLE = "semantic_role"
    EDUCATIONAL_ROLE = "educational_role"
    TAXONOMY = "taxonomy"
    SUBJECT = "subject"
    PREREQUISITE = "prerequisite"
    RELATIONSHIP = "relationship"


class PackageStatus(str, Enum):
    """Lifecycle status of a MasterKnowledgePackage."""
    DRAFT = "draft"
    VALIDATED = "validated"
    SEALED = "sealed"       # Immutable, ready for Phase 2
    CORRUPTED = "corrupted"


class DependencyType(str, Enum):
    """Type of a dependency edge in the DependencyMap."""
    PREREQUISITE = "prerequisite"
    REQUIRES = "requires"
    BUILDS_ON = "builds_on"
    ENABLES = "enables"


class ProgressionStrategy(str, Enum):
    """Strategy used to order the LearningProgression."""
    TOPOLOGICAL = "topological"         # Dependency-respecting topological sort
    CONFIDENCE_WEIGHTED = "confidence_weighted"


class SerializationFormat(str, Enum):
    """Output format for MasterJSONSerializer."""
    JSON = "json"
    DICT = "dict"


class ValidationSeverity(str, Enum):
    """Severity levels mirroring M5.1's DiagnosticSeverity for use in enums."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
