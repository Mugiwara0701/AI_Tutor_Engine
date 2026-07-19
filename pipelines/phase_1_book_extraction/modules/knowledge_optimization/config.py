"""
modules/knowledge_optimization/config.py — M5.4: immutable configuration
for the Knowledge Optimization & Intelligence Preparation Layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "KnowledgeOptimizationConfig",
    "default_config",
    "DEFAULT_OPTIMIZER_VERSION",
    "DEFAULT_OPTIMIZED_PACKAGE_VERSION",
]

DEFAULT_OPTIMIZER_VERSION         = "1.0.0"
DEFAULT_OPTIMIZED_PACKAGE_VERSION = "1.0.0"


@dataclass(frozen=True)
class KnowledgeOptimizationConfig:
    """
    Immutable configuration for the KnowledgeOptimizer pipeline.

    Attributes:
        optimizer_version:          Semantic version of this optimizer.
        optimized_package_version:  Version stamped on the output package.
        min_confidence_threshold:   Concepts below this are flagged as LOW_CONFIDENCE.
        cross_link_max_hops:        Max graph hops when discovering cross-chapter links.
        min_cross_links_per_concept:Warning threshold for weak cross-linking.
        enable_cycle_detection:     Run cycle detection during quality analysis.
        enable_semantic_search:     Build semantic search index.
        quality_issue_threshold:    Max quality issues before outcome is PARTIAL.
        extra:                      Reserved for future extension.
    """
    optimizer_version: str           = DEFAULT_OPTIMIZER_VERSION
    optimized_package_version: str   = DEFAULT_OPTIMIZED_PACKAGE_VERSION
    min_confidence_threshold: float  = 0.30
    cross_link_max_hops: int         = 3
    min_cross_links_per_concept: int = 1
    enable_cycle_detection: bool     = True
    enable_semantic_search: bool     = True
    quality_issue_threshold: int     = 50
    extra: Mapping[str, Any]         = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence_threshold <= 1.0:
            raise ValueError(
                f"min_confidence_threshold must be in [0.0, 1.0]; "
                f"got {self.min_confidence_threshold!r}."
            )
        if self.cross_link_max_hops < 1:
            raise ValueError(f"cross_link_max_hops must be >= 1; got {self.cross_link_max_hops!r}.")

    def to_dict(self) -> dict:
        return {
            "optimizer_version": self.optimizer_version,
            "optimized_package_version": self.optimized_package_version,
            "min_confidence_threshold": self.min_confidence_threshold,
            "cross_link_max_hops": self.cross_link_max_hops,
            "min_cross_links_per_concept": self.min_cross_links_per_concept,
            "enable_cycle_detection": self.enable_cycle_detection,
            "enable_semantic_search": self.enable_semantic_search,
            "quality_issue_threshold": self.quality_issue_threshold,
            "extra": dict(self.extra),
        }


#: Module-level singleton.
default_config = KnowledgeOptimizationConfig()
