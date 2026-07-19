"""
modules/knowledge_optimization/engine.py — M5.4: the
KnowledgeOptimizationEngine — top-level pipeline coordinator.

Consumes a MasterKnowledgePackage (M5.3) and produces a sealed,
immutable OptimizedKnowledgePackage ready for Phase 2.

Pipeline:
  1. PackageValidator           → validate input M5.3 package
  2. KnowledgeOptimizer         → OptimizedRetrievalIndex
  3. CrossChapterLinker         → CrossChapterLinkIndex
  4. SemanticSearchBuilder      → SemanticSearchIndex
  5. RuntimeCacheBuilder        → RuntimeCache
  6. LearningAnalyticsBuilder   → LearningAnalytics
  7. KnowledgeQualityAnalyzer   → KnowledgeQualityReport
  8. Package assembly           → OptimizedKnowledgePackage (sealed)
  9. OptimizationSerializer     → SerializationResult

Nothing in M5.1–M5.3 is modified.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from modules.knowledge_optimization.config import (
    KnowledgeOptimizationConfig, default_config,
)
from modules.knowledge_optimization.cross_chapter_linker import (
    CrossChapterLinker, default_cross_chapter_linker,
)
from modules.knowledge_optimization.enums import OptimizationOutcome, OptimizationStatus
from modules.knowledge_optimization.exceptions import (
    KnowledgeOptimizationError, OptimizedPackageBuildError,
)
from modules.knowledge_optimization.knowledge_optimizer import (
    KnowledgeOptimizer, default_knowledge_optimizer,
)
from modules.knowledge_optimization.learning_analytics_builder import (
    LearningAnalyticsBuilder, default_learning_analytics_builder,
)
from modules.knowledge_optimization.models import (
    DEFAULT_OPTIMIZED_MODEL_VERSION,
    OptimizationManifest,
    OptimizationStatistics,
    OptimizedKnowledgePackage,
)
from modules.knowledge_optimization.package_validator import (
    PackageValidator, default_package_validator,
)
from modules.knowledge_optimization.quality_analyzer import (
    KnowledgeQualityAnalyzer, default_quality_analyzer,
)
from modules.knowledge_optimization.runtime_cache_builder import (
    RuntimeCacheBuilder, default_runtime_cache_builder,
)
from modules.knowledge_optimization.semantic_search_builder import (
    SemanticSearchBuilder, default_semantic_search_builder,
)
from modules.knowledge_optimization.serializer import (
    OptimizationSerializer, SerializationResult, default_serializer,
)

__all__ = [
    "KnowledgeOptimizationEngine",
    "default_engine",
    "optimize",
]

# Stable namespace for optimized_package_id (UUID5)
_OPT_NAMESPACE = uuid.UUID("e5f6a7b8-c9d0-1234-ef01-345678901234")


def _opt_package_id(source_package_id: str, optimizer_version: str) -> str:
    return str(uuid.uuid5(_OPT_NAMESPACE, f"{source_package_id}:{optimizer_version}"))


class KnowledgeOptimizationEngine:
    """
    Top-level M5.4 engine.  Accepts a MasterKnowledgePackage and
    produces a sealed OptimizedKnowledgePackage.

    Usage:
        engine = KnowledgeOptimizationEngine()
        opt_pkg = engine.optimize(master_package)
        result  = engine.serialize(opt_pkg)
    """

    def __init__(
        self,
        config: Optional[KnowledgeOptimizationConfig] = None,
        validator: Optional[PackageValidator] = None,
        optimizer: Optional[KnowledgeOptimizer] = None,
        linker: Optional[CrossChapterLinker] = None,
        search_builder: Optional[SemanticSearchBuilder] = None,
        cache_builder: Optional[RuntimeCacheBuilder] = None,
        analytics_builder: Optional[LearningAnalyticsBuilder] = None,
        quality_analyzer: Optional[KnowledgeQualityAnalyzer] = None,
        serializer: Optional[OptimizationSerializer] = None,
    ) -> None:
        self._cfg           = config or default_config
        self._validator     = validator or PackageValidator(config=self._cfg)
        self._optimizer     = optimizer or KnowledgeOptimizer(config=self._cfg)
        self._linker        = linker or CrossChapterLinker(config=self._cfg)
        self._search        = search_builder or SemanticSearchBuilder(config=self._cfg)
        self._cache         = cache_builder or RuntimeCacheBuilder(config=self._cfg)
        self._analytics     = analytics_builder or LearningAnalyticsBuilder(config=self._cfg)
        self._quality       = quality_analyzer or KnowledgeQualityAnalyzer(config=self._cfg)
        self._serializer    = serializer or default_serializer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(self, package: object) -> OptimizedKnowledgePackage:
        """Full pipeline: validate → optimize → assemble → seal."""
        diagnostics: List[str] = []
        try:
            return self._run_pipeline(package, diagnostics)
        except KnowledgeOptimizationError:
            raise
        except Exception as exc:
            raise OptimizedPackageBuildError(
                f"Unexpected error in KnowledgeOptimizationEngine: {exc}"
            ) from exc

    def serialize(self, package: OptimizedKnowledgePackage) -> SerializationResult:
        return self._serializer.serialize(package)

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(
        self, package: object, diagnostics: List[str]
    ) -> OptimizedKnowledgePackage:

        # 1. Validate
        vr = self._validator.validate(package)
        if vr.diagnostics:
            diagnostics.extend(
                f"[Validation] {d.code}: {d.message}" for d in vr.diagnostics
            )
            if vr.has_errors:
                raise OptimizedPackageBuildError(
                    "Input MasterKnowledgePackage failed validation: "
                    + "; ".join(d.message for d in vr.diagnostics if d.severity.value == "error")
                )

        # 2. Optimized retrieval index
        retrieval_index = self._optimizer.optimize(package)

        # 3. Cross-chapter links
        cross_chapter_links = self._linker.build(package)

        # 4. Semantic search index
        search_index = self._search.build(package)

        # 5. Runtime cache
        runtime_cache = self._cache.build(package)

        # 6. Analytics
        analytics = self._analytics.build(package)

        # 7. Quality report
        quality_report = self._quality.analyze(package)

        # 8. Manifest + Statistics
        manifest_obj = getattr(package, "manifest", None)
        source_pkg_id = getattr(manifest_obj, "package_id", "") if manifest_obj else ""
        source_graph_id = getattr(manifest_obj, "graph_id", "") if manifest_obj else ""

        opt_pkg_id = _opt_package_id(source_pkg_id, self._cfg.optimizer_version)

        quality_issues = quality_report.total_issues
        outcome = (
            OptimizationOutcome.COMPLETE
            if quality_issues <= self._cfg.quality_issue_threshold
            else OptimizationOutcome.PARTIAL
        )
        if not retrieval_index.entries:
            outcome = OptimizationOutcome.EMPTY

        statistics = OptimizationStatistics(
            total_concepts_optimized=len(retrieval_index.entries),
            total_cross_links=cross_chapter_links.total_links,
            total_retrieval_entries=retrieval_index.total_entries,
            total_search_entries=search_index.total_entries,
            total_cache_entries=runtime_cache.total_entries,
            total_quality_issues=quality_issues,
            optimizer_version=self._cfg.optimizer_version,
            optimized_package_version=self._cfg.optimized_package_version,
            source_package_id=source_pkg_id,
            overall_outcome=outcome,
        )

        manifest = OptimizationManifest(
            optimized_package_id=opt_pkg_id,
            source_package_id=source_pkg_id,
            source_graph_id=source_graph_id,
            optimizer_version=self._cfg.optimizer_version,
            optimized_package_version=self._cfg.optimized_package_version,
            status=OptimizationStatus.SEALED,
            diagnostics=tuple(diagnostics),
        )

        return OptimizedKnowledgePackage(
            manifest=manifest,
            cross_chapter_links=cross_chapter_links,
            retrieval_index=retrieval_index,
            search_index=search_index,
            runtime_cache=runtime_cache,
            analytics=analytics,
            quality_report=quality_report,
            statistics=statistics,
            source_package_id=source_pkg_id,
            outcome=outcome,
        )


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

default_engine = KnowledgeOptimizationEngine()


def optimize(package: object) -> OptimizedKnowledgePackage:
    """Convenience function: optimize via the module-level default engine."""
    return default_engine.optimize(package)
