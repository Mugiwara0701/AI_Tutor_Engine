"""
modules/semantic_interpretation_engine/config.py — M5.2D: configuration
for the Semantic Interpretation & Enrichment Engine.

Immutable, versioned, and serializable — consistent with M5.1–M5.2C
config conventions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "SemanticInterpretationEngineConfig",
    "default_config",
    "DEFAULT_ENGINE_VERSION",
]

DEFAULT_ENGINE_VERSION = "1.0.0"

# Confidence thresholds (inclusive lower bounds for each band)
_DEFAULT_HIGH_THRESHOLD: float = 0.80
_DEFAULT_MEDIUM_THRESHOLD: float = 0.50
_DEFAULT_LOW_THRESHOLD: float = 0.20


@dataclass(frozen=True)
class SemanticInterpretationEngineConfig:
    """
    Immutable configuration for the SemanticInterpretationEngine and
    SemanticEnrichmentEngine.

    Attributes:
        version:               Semantic version string for this config snapshot.
        high_confidence_threshold:
                               Minimum score for ConfidenceLevel.HIGH  (default 0.80).
        medium_confidence_threshold:
                               Minimum score for ConfidenceLevel.MEDIUM (default 0.50).
        low_confidence_threshold:
                               Minimum score for ConfidenceLevel.LOW    (default 0.20).
        strict_anchor_uniqueness:
                               If True, duplicate anchor_ids raise SemanticAnchorError
                               during validation (default True).
        require_all_roles_for_complete:
                               If True, EnrichmentOutcome.COMPLETE requires every
                               required pattern role to be present (default True).
        extra:                 Reserved for future extension; never read by the engine.
    """

    version: str = DEFAULT_ENGINE_VERSION
    high_confidence_threshold: float = _DEFAULT_HIGH_THRESHOLD
    medium_confidence_threshold: float = _DEFAULT_MEDIUM_THRESHOLD
    low_confidence_threshold: float = _DEFAULT_LOW_THRESHOLD
    strict_anchor_uniqueness: bool = True
    require_all_roles_for_complete: bool = True
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.low_confidence_threshold
                <= self.medium_confidence_threshold
                <= self.high_confidence_threshold
                <= 1.0):
            raise ValueError(
                "Confidence thresholds must satisfy "
                "0.0 <= low <= medium <= high <= 1.0; "
                f"got low={self.low_confidence_threshold}, "
                f"medium={self.medium_confidence_threshold}, "
                f"high={self.high_confidence_threshold}"
            )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "high_confidence_threshold": self.high_confidence_threshold,
            "medium_confidence_threshold": self.medium_confidence_threshold,
            "low_confidence_threshold": self.low_confidence_threshold,
            "strict_anchor_uniqueness": self.strict_anchor_uniqueness,
            "require_all_roles_for_complete": self.require_all_roles_for_complete,
            "extra": dict(self.extra),
        }


#: Module-level singleton — callers import this rather than
#: constructing their own unless they need a non-default config.
default_config = SemanticInterpretationEngineConfig()
