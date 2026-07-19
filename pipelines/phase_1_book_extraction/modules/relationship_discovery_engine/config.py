"""
modules/relationship_discovery_engine/config.py — M5.2E: immutable,
versioned configuration for the Relationship Discovery & Semantic
Graph Engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from modules.relationship_discovery_engine.enums import NormalizationStrategy

__all__ = [
    "RelationshipDiscoveryEngineConfig",
    "default_config",
    "DEFAULT_ENGINE_VERSION",
]

DEFAULT_ENGINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class RelationshipDiscoveryEngineConfig:
    """
    Immutable configuration for the Relationship Discovery & Semantic
    Graph Engine.

    Attributes:
        version:                    Engine version string.
        min_relationship_confidence:
                                    Minimum confidence score for a
                                    SemanticRelationship to be included
                                    in the graph (default 0.10).
        min_node_confidence:        Minimum anchor confidence to admit a
                                    node into the graph (default 0.10).
        normalization_strategy:     How duplicate edges are resolved
                                    (default KEEP_HIGHEST_CONFIDENCE).
        detect_cycles:              If True, cycle detection is run and
                                    flagged in graph validation (default True).
        allow_self_loops:           If True, source == target edges are
                                    permitted (default False).
        strict_graph_validation:    If True, broken references are errors
                                    rather than warnings (default False).
        extra:                      Reserved for future extension.
    """

    version: str = DEFAULT_ENGINE_VERSION
    min_relationship_confidence: float = 0.10
    min_node_confidence: float = 0.10
    normalization_strategy: NormalizationStrategy = NormalizationStrategy.KEEP_HIGHEST_CONFIDENCE
    detect_cycles: bool = True
    allow_self_loops: bool = False
    strict_graph_validation: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_relationship_confidence <= 1.0:
            raise ValueError(
                f"min_relationship_confidence must be in [0.0, 1.0]; "
                f"got {self.min_relationship_confidence!r}."
            )
        if not 0.0 <= self.min_node_confidence <= 1.0:
            raise ValueError(
                f"min_node_confidence must be in [0.0, 1.0]; "
                f"got {self.min_node_confidence!r}."
            )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "min_relationship_confidence": self.min_relationship_confidence,
            "min_node_confidence": self.min_node_confidence,
            "normalization_strategy": self.normalization_strategy.value,
            "detect_cycles": self.detect_cycles,
            "allow_self_loops": self.allow_self_loops,
            "strict_graph_validation": self.strict_graph_validation,
            "extra": dict(self.extra),
        }


#: Module-level singleton.
default_config = RelationshipDiscoveryEngineConfig()
