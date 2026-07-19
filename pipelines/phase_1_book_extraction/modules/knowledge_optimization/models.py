"""
modules/knowledge_optimization/models.py — M5.4: the core
immutable, versioned, serializable optimization data models.

All models are frozen dataclasses.  No M5.1–M5.3 model is subclassed
or mutated.  `ConceptEntry.node_id` values (from M5.3) are used as
primary keys throughout — never regenerated.

The `OptimizedKnowledgePackage` is the final Phase 2 artifact.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from modules.knowledge_optimization.enums import (
    AnalyticsMetric,
    CacheType,
    LinkType,
    OptimizationOutcome,
    OptimizationStatus,
    QualityIssueType,
    QualityIssueSeverity,
    SearchIndexType,
)
from modules.knowledge_optimization.exceptions import KnowledgeOptimizationError

__all__ = [
    # Cross-chapter linking
    "CrossChapterLink",
    "CrossChapterLinkIndex",
    # Retrieval optimization
    "OptimizedIndexEntry",
    "OptimizedRetrievalIndex",
    # Semantic search
    "SearchEntry",
    "SemanticSearchIndex",
    # Runtime cache
    "CacheEntry",
    "RuntimeCache",
    # Learning analytics
    "ConceptAnalytics",
    "LearningAnalytics",
    # Quality
    "QualityIssue",
    "KnowledgeQualityReport",
    # Package manifest + statistics
    "OptimizationManifest",
    "OptimizationStatistics",
    # Optimized package (Deliverable #9)
    "OptimizedKnowledgePackage",
    # Version constant
    "DEFAULT_OPTIMIZED_MODEL_VERSION",
]

DEFAULT_OPTIMIZED_MODEL_VERSION = "1.0.0"


def _ft(v) -> tuple:  return () if v is None else tuple(v)
def _fm(v) -> dict:   return {} if v is None else dict(v)


# ---------------------------------------------------------------------------
# Cross-Chapter Linking (Deliverable #3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CrossChapterLink:
    """A deterministic link between two concept nodes."""
    source_node_id: str
    target_node_id: str
    link_type: LinkType
    confidence: float
    hop_distance: int = 1

    def __post_init__(self) -> None:
        if not self.source_node_id:
            raise KnowledgeOptimizationError("CrossChapterLink.source_node_id must not be empty.")
        if not self.target_node_id:
            raise KnowledgeOptimizationError("CrossChapterLink.target_node_id must not be empty.")
        if not 0.0 <= self.confidence <= 1.0:
            raise KnowledgeOptimizationError(
                f"CrossChapterLink.confidence must be in [0.0, 1.0]; got {self.confidence!r}."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "link_type": self.link_type.value,
            "confidence": self.confidence,
            "hop_distance": self.hop_distance,
        }


@dataclass(frozen=True)
class CrossChapterLinkIndex:
    """All cross-chapter links for the compiled knowledge package."""
    links: Tuple[CrossChapterLink, ...]
    by_source: Mapping[str, Tuple[str, ...]]    # source_node_id → target_node_ids
    by_target: Mapping[str, Tuple[str, ...]]    # target_node_id → source_node_ids
    by_link_type: Mapping[str, Tuple[str, ...]] # link_type → source_node_ids
    total_links: int
    outcome: OptimizationOutcome
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "links", _ft(self.links))
        for attr in ("by_source", "by_target", "by_link_type"):
            object.__setattr__(self, attr,
                {k: tuple(v) for k, v in (getattr(self, attr) or {}).items()})

    def to_dict(self) -> Dict[str, Any]:
        def _m(d): return {k: list(v) for k, v in d.items()}
        return {
            "links": [l.to_dict() for l in self.links],
            "by_source": _m(self.by_source),
            "by_target": _m(self.by_target),
            "by_link_type": _m(self.by_link_type),
            "total_links": self.total_links,
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Retrieval Optimization (Deliverable #4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizedIndexEntry:
    """A single entry in the optimized retrieval index."""
    key: str
    normalized_key: str        # lowercase, stripped, for fast matching
    node_ids: Tuple[str, ...]
    index_type: SearchIndexType
    aliases: Tuple[str, ...]
    count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", _ft(self.node_ids))
        object.__setattr__(self, "aliases", _ft(self.aliases))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "normalized_key": self.normalized_key,
            "node_ids": list(self.node_ids),
            "index_type": self.index_type.value,
            "aliases": list(self.aliases),
            "count": self.count,
        }


@dataclass(frozen=True)
class OptimizedRetrievalIndex:
    """
    Multi-dimensional optimized retrieval index.

    Supports O(1) lookup by: object_key, object_type, semantic_role,
    concept_category, pattern_key, normalized_key.
    """
    by_object_key: Mapping[str, str]                # object_key → node_id
    by_object_type: Mapping[str, Tuple[str, ...]]   # type_key → node_ids
    by_semantic_role: Mapping[str, Tuple[str, ...]]
    by_concept_category: Mapping[str, Tuple[str, ...]]
    by_pattern_key: Mapping[str, Tuple[str, ...]]
    by_normalized_key: Mapping[str, Tuple[str, ...]]
    prerequisite_chains: Mapping[str, Tuple[str, ...]]  # node_id → full chain
    successor_map: Mapping[str, Tuple[str, ...]]        # node_id → successors
    entries: Tuple[OptimizedIndexEntry, ...]
    total_entries: int
    outcome: OptimizationOutcome
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def __post_init__(self) -> None:
        for attr in ("by_object_type", "by_semantic_role", "by_concept_category",
                     "by_pattern_key", "by_normalized_key",
                     "prerequisite_chains", "successor_map"):
            object.__setattr__(self, attr,
                {k: tuple(v) for k, v in (getattr(self, attr) or {}).items()})
        object.__setattr__(self, "by_object_key", _fm(self.by_object_key))
        object.__setattr__(self, "entries", _ft(self.entries))

    def lookup(self, node_id: str) -> Optional[str]:
        """Return object_key for node_id, or None."""
        for k, v in self.by_object_key.items():
            if v == node_id:
                return k
        return None

    def to_dict(self) -> Dict[str, Any]:
        def _m(d): return {k: list(v) for k, v in d.items()}
        return {
            "by_object_key": dict(self.by_object_key),
            "by_object_type": _m(self.by_object_type),
            "by_semantic_role": _m(self.by_semantic_role),
            "by_concept_category": _m(self.by_concept_category),
            "by_pattern_key": _m(self.by_pattern_key),
            "by_normalized_key": _m(self.by_normalized_key),
            "prerequisite_chains": _m(self.prerequisite_chains),
            "successor_map": _m(self.successor_map),
            "entries": [e.to_dict() for e in self.entries],
            "total_entries": self.total_entries,
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Semantic Search Index (Deliverable #5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchEntry:
    """A single entry in the semantic search index."""
    node_id: str
    search_key: str           # primary normalized search key
    aliases: Tuple[str, ...]  # additional normalized lookup keys
    keywords: Tuple[str, ...] # extracted keywords
    role_tag: str             # semantic_role value
    category_tag: str         # concept_category value
    search_rank: float        # deterministic rank in [0.0, 1.0]

    def __post_init__(self) -> None:
        object.__setattr__(self, "aliases", _ft(self.aliases))
        object.__setattr__(self, "keywords", _ft(self.keywords))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "search_key": self.search_key,
            "aliases": list(self.aliases),
            "keywords": list(self.keywords),
            "role_tag": self.role_tag,
            "category_tag": self.category_tag,
            "search_rank": self.search_rank,
        }


@dataclass(frozen=True)
class SemanticSearchIndex:
    """
    Pre-built semantic search index.

    Supports normalized key lookup, alias lookup, keyword expansion,
    and role/category filtering — no LLM, no embeddings.
    """
    entries: Tuple[SearchEntry, ...]
    key_to_node_ids: Mapping[str, Tuple[str, ...]]    # search_key → node_ids
    alias_to_node_ids: Mapping[str, Tuple[str, ...]]  # alias → node_ids
    keyword_to_node_ids: Mapping[str, Tuple[str, ...]]
    role_to_node_ids: Mapping[str, Tuple[str, ...]]
    category_to_node_ids: Mapping[str, Tuple[str, ...]]
    total_entries: int
    outcome: OptimizationOutcome
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", _ft(self.entries))
        for attr in ("key_to_node_ids", "alias_to_node_ids", "keyword_to_node_ids",
                     "role_to_node_ids", "category_to_node_ids"):
            object.__setattr__(self, attr,
                {k: tuple(v) for k, v in (getattr(self, attr) or {}).items()})

    def to_dict(self) -> Dict[str, Any]:
        def _m(d): return {k: list(v) for k, v in d.items()}
        return {
            "entries": [e.to_dict() for e in self.entries],
            "key_to_node_ids": _m(self.key_to_node_ids),
            "alias_to_node_ids": _m(self.alias_to_node_ids),
            "keyword_to_node_ids": _m(self.keyword_to_node_ids),
            "role_to_node_ids": _m(self.role_to_node_ids),
            "category_to_node_ids": _m(self.category_to_node_ids),
            "total_entries": self.total_entries,
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Runtime Cache (Deliverable #6)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CacheEntry:
    """A single pre-computed cache entry."""
    key: str
    value: Any
    cache_type: CacheType
    hit_priority: int = 0    # higher = evicted last (for Phase 2 cache managers)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "cache_type": self.cache_type.value,
            "hit_priority": self.hit_priority,
        }


@dataclass(frozen=True)
class RuntimeCache:
    """
    Pre-computed caches that eliminate repeated traversal during runtime.

    All values are deterministic.  Phase 2 systems may use these as
    read-through caches (populate on miss, but the canonical answer
    is always here).
    """
    concept_lookup: Mapping[str, str]            # node_id → object_key
    dependency_traversal: Mapping[str, Tuple[str, ...]]  # node_id → all transitive prereqs
    related_concepts: Mapping[str, Tuple[str, ...]]      # node_id → related node_ids
    learning_path: Tuple[str, ...]                       # full topological order
    educational_objects: Mapping[str, str]       # object_key → node_id
    prerequisite_chains: Mapping[str, Tuple[str, ...]]   # node_id → ordered chain
    entries: Tuple[CacheEntry, ...]
    total_entries: int
    outcome: OptimizationOutcome
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "concept_lookup", _fm(self.concept_lookup))
        object.__setattr__(self, "educational_objects", _fm(self.educational_objects))
        object.__setattr__(self, "learning_path", _ft(self.learning_path))
        object.__setattr__(self, "entries", _ft(self.entries))
        for attr in ("dependency_traversal", "related_concepts", "prerequisite_chains"):
            object.__setattr__(self, attr,
                {k: tuple(v) for k, v in (getattr(self, attr) or {}).items()})

    def to_dict(self) -> Dict[str, Any]:
        def _m(d): return {k: list(v) for k, v in d.items()}
        return {
            "concept_lookup": dict(self.concept_lookup),
            "dependency_traversal": _m(self.dependency_traversal),
            "related_concepts": _m(self.related_concepts),
            "learning_path": list(self.learning_path),
            "educational_objects": dict(self.educational_objects),
            "prerequisite_chains": _m(self.prerequisite_chains),
            "entries": [e.to_dict() for e in self.entries],
            "total_entries": self.total_entries,
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Learning Analytics (Deliverable #7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConceptAnalytics:
    """Per-concept analytics metrics."""
    node_id: str
    prerequisite_depth: int         # depth in dependency DAG
    dependency_complexity: int      # number of direct + transitive deps
    centrality: float               # normalised betweenness proxy
    connectivity: int               # number of edges (in + out)
    importance: float               # normalised composite score
    is_hub: bool                    # connectivity > mean + stddev

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "prerequisite_depth": self.prerequisite_depth,
            "dependency_complexity": self.dependency_complexity,
            "centrality": self.centrality,
            "connectivity": self.connectivity,
            "importance": self.importance,
            "is_hub": self.is_hub,
        }


@dataclass(frozen=True)
class LearningAnalytics:
    """Immutable, aggregate learning analytics for the knowledge package."""
    per_concept: Tuple[ConceptAnalytics, ...]
    graph_density: float
    average_prerequisite_depth: float
    max_prerequisite_depth: int
    average_connectivity: float
    average_learning_path_length: float
    orphan_ratio: float
    hub_concepts: Tuple[str, ...]   # node_ids with is_hub=True
    cluster_count: int
    total_concepts_analyzed: int
    outcome: OptimizationOutcome
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "per_concept", _ft(self.per_concept))
        object.__setattr__(self, "hub_concepts", _ft(self.hub_concepts))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "per_concept": [c.to_dict() for c in self.per_concept],
            "graph_density": self.graph_density,
            "average_prerequisite_depth": self.average_prerequisite_depth,
            "max_prerequisite_depth": self.max_prerequisite_depth,
            "average_connectivity": self.average_connectivity,
            "average_learning_path_length": self.average_learning_path_length,
            "orphan_ratio": self.orphan_ratio,
            "hub_concepts": list(self.hub_concepts),
            "cluster_count": self.cluster_count,
            "total_concepts_analyzed": self.total_concepts_analyzed,
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Knowledge Quality Report (Deliverable #8)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QualityIssue:
    """A single quality issue detected in the knowledge package."""
    issue_type: QualityIssueType
    severity: QualityIssueSeverity
    node_id: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "node_id": self.node_id,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class KnowledgeQualityReport:
    """Structured quality report (no narrative)."""
    issues: Tuple[QualityIssue, ...]
    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    overall_quality_score: float   # 0.0 (worst) → 1.0 (best)
    concepts_with_issues: Tuple[str, ...]
    outcome: OptimizationOutcome
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", _ft(self.issues))
        object.__setattr__(self, "concepts_with_issues", _ft(self.concepts_with_issues))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "info_count": self.info_count,
            "overall_quality_score": self.overall_quality_score,
            "concepts_with_issues": list(self.concepts_with_issues),
            "outcome": self.outcome.value,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Optimization Manifest + Statistics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizationStatistics:
    """Aggregate optimization statistics."""
    total_concepts_optimized: int
    total_cross_links: int
    total_retrieval_entries: int
    total_search_entries: int
    total_cache_entries: int
    total_quality_issues: int
    optimizer_version: str
    optimized_package_version: str
    source_package_id: str
    overall_outcome: OptimizationOutcome

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_concepts_optimized": self.total_concepts_optimized,
            "total_cross_links": self.total_cross_links,
            "total_retrieval_entries": self.total_retrieval_entries,
            "total_search_entries": self.total_search_entries,
            "total_cache_entries": self.total_cache_entries,
            "total_quality_issues": self.total_quality_issues,
            "optimizer_version": self.optimizer_version,
            "optimized_package_version": self.optimized_package_version,
            "source_package_id": self.source_package_id,
            "overall_outcome": self.overall_outcome.value,
        }


@dataclass(frozen=True)
class OptimizationManifest:
    """Provenance manifest for an OptimizedKnowledgePackage."""
    optimized_package_id: str
    source_package_id: str
    source_graph_id: str
    optimizer_version: str
    optimized_package_version: str
    status: OptimizationStatus
    diagnostics: Tuple[str, ...]
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def __post_init__(self) -> None:
        if not self.optimized_package_id:
            raise KnowledgeOptimizationError("OptimizationManifest.optimized_package_id must not be empty.")
        object.__setattr__(self, "diagnostics", _ft(self.diagnostics))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "optimized_package_id": self.optimized_package_id,
            "source_package_id": self.source_package_id,
            "source_graph_id": self.source_graph_id,
            "optimizer_version": self.optimizer_version,
            "optimized_package_version": self.optimized_package_version,
            "status": self.status.value,
            "diagnostics": list(self.diagnostics),
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# OptimizedKnowledgePackage (Deliverable #9)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizedKnowledgePackage:
    """
    The immutable, optimized, Phase 2-ready knowledge package.

    Wraps a MasterKnowledgePackage (by value / by reference) and adds
    the full optimization layer.  Phase 2 systems consume THIS package —
    they never need to re-run M5.1–M5.3.

    Attributes:
        manifest:               Provenance, versioning, status.
        cross_chapter_links:    All cross-chapter relationship links.
        retrieval_index:        Multi-dimensional optimized retrieval.
        search_index:           Semantic search preparation index.
        runtime_cache:          Pre-computed runtime traversal caches.
        analytics:              Learning analytics metrics.
        quality_report:         Structured quality report.
        statistics:             Aggregate optimization statistics.
        source_package_id:      manifest.package_id from MasterKnowledgePackage.
        outcome:                Overall optimization outcome.
        version:                Package schema version.
    """
    manifest: OptimizationManifest
    cross_chapter_links: CrossChapterLinkIndex
    retrieval_index: OptimizedRetrievalIndex
    search_index: SemanticSearchIndex
    runtime_cache: RuntimeCache
    analytics: LearningAnalytics
    quality_report: KnowledgeQualityReport
    statistics: OptimizationStatistics
    source_package_id: str
    outcome: OptimizationOutcome
    version: str = DEFAULT_OPTIMIZED_MODEL_VERSION

    def is_complete(self) -> bool:
        return self.outcome == OptimizationOutcome.COMPLETE

    def is_sealed(self) -> bool:
        return self.manifest.status == OptimizationStatus.SEALED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "cross_chapter_links": self.cross_chapter_links.to_dict(),
            "retrieval_index": self.retrieval_index.to_dict(),
            "search_index": self.search_index.to_dict(),
            "runtime_cache": self.runtime_cache.to_dict(),
            "analytics": self.analytics.to_dict(),
            "quality_report": self.quality_report.to_dict(),
            "statistics": self.statistics.to_dict(),
            "source_package_id": self.source_package_id,
            "outcome": self.outcome.value,
            "version": self.version,
        }
