"""
modules/knowledge_optimization/enums.py — M5.4: enumerated vocabularies
for the Knowledge Optimization & Intelligence Preparation Layer.
"""
from __future__ import annotations
from enum import Enum

__all__ = [
    "OptimizationOutcome",
    "LinkType",
    "CacheType",
    "AnalyticsMetric",
    "QualityIssueType",
    "QualityIssueSeverity",
    "SearchIndexType",
    "OptimizationStatus",
]


class OptimizationOutcome(str, Enum):
    COMPLETE = "complete"
    PARTIAL  = "partial"
    EMPTY    = "empty"
    FAILED   = "failed"


class LinkType(str, Enum):
    RELATED_CONCEPT  = "related_concept"
    PREREQUISITE     = "prerequisite"
    SUCCESSOR        = "successor"
    REINFORCING      = "reinforcing"
    CONTRASTING      = "contrasting"
    CROSS_CHAPTER    = "cross_chapter"
    CROSS_BOOK       = "cross_book"
    GLOSSARY         = "glossary"


class CacheType(str, Enum):
    CONCEPT_LOOKUP         = "concept_lookup"
    DEPENDENCY_TRAVERSAL   = "dependency_traversal"
    RELATED_CONCEPTS       = "related_concepts"
    LEARNING_PATH          = "learning_path"
    EDUCATIONAL_OBJECTS    = "educational_objects"
    PREREQUISITE_CHAIN     = "prerequisite_chain"


class AnalyticsMetric(str, Enum):
    PREREQUISITE_DEPTH   = "prerequisite_depth"
    DEPENDENCY_COMPLEXITY = "dependency_complexity"
    CONCEPT_CENTRALITY   = "concept_centrality"
    CONCEPT_CONNECTIVITY = "concept_connectivity"
    LEARNING_PATH_LENGTH = "learning_path_length"
    CONCEPT_IMPORTANCE   = "concept_importance"
    GRAPH_DENSITY        = "graph_density"
    ORPHAN_RATIO         = "orphan_ratio"
    CLUSTER_COUNT        = "cluster_count"


class QualityIssueType(str, Enum):
    ISOLATED_CONCEPT       = "isolated_concept"
    CIRCULAR_DEPENDENCY    = "circular_dependency"
    UNREACHABLE_CONCEPT    = "unreachable_concept"
    WEAK_CROSS_LINKING     = "weak_cross_linking"
    MISSING_EXAMPLES       = "missing_examples"
    SPARSE_ASSESSMENTS     = "sparse_assessments"
    INCONSISTENT_METADATA  = "inconsistent_metadata"
    LOW_CONFIDENCE         = "low_confidence"
    DUPLICATE_CONCEPT      = "duplicate_concept"
    MISSING_PREREQUISITES  = "missing_prerequisites"


class QualityIssueSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


class SearchIndexType(str, Enum):
    EXACT       = "exact"
    NORMALIZED  = "normalized"
    ALIAS       = "alias"
    KEYWORD     = "keyword"
    ROLE_BASED  = "role_based"


class OptimizationStatus(str, Enum):
    DRAFT     = "draft"
    VALIDATED = "validated"
    OPTIMIZED = "optimized"
    SEALED    = "sealed"
