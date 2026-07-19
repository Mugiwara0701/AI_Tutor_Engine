"""
modules/structural_understanding_engine/config.py — M5.2C: engine
configuration.

Mirrors `modules.educational_object_framework.config`'s approach
exactly (itself mirroring `heading_canonicalization.config`): a
data-driven, immutable settings object rather than inline constants or
if/else branching. Deliberately a per-package config module, not a
shared one — the same convention every existing framework package in
this repository already follows.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional

from modules.structural_understanding_engine.exceptions import (
    StructuralUnderstandingEngineError,
)


class StructuralUnderstandingEngineConfigError(StructuralUnderstandingEngineError):
    """Raised when a `StructuralUnderstandingEngineConfig` value is
    malformed."""


#: Framework-wide default: whether a `StructuralAnalysisResult` missing
#: a required component is treated as an ERROR (strict) or a WARNING
#: (lenient) diagnostic when no per-contribution `ValidationHints`
#: override says otherwise.
DEFAULT_STRICT_STRUCTURAL_VALIDATION: bool = True


@dataclass(frozen=True)
class StructuralUnderstandingEngineConfig:
    """Immutable, engine-wide configuration. Built once (via
    `default_config()` or a caller-supplied variant) and threaded
    through `StructuralUnderstandingEngine` / `ProfileActivationManager`
    — neither of which ever mutate it; all "change a setting"
    operations return a new config via `with_feature_toggle` /
    `with_extra`."""

    strict_structural_validation: bool = DEFAULT_STRICT_STRUCTURAL_VALIDATION
    feature_toggles: Mapping[str, bool] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.strict_structural_validation, bool):
            raise StructuralUnderstandingEngineConfigError(
                "StructuralUnderstandingEngineConfig.strict_structural_validation "
                f"must be a bool, got {type(self.strict_structural_validation).__name__}."
            )
        object.__setattr__(self, "feature_toggles", dict(self.feature_toggles))
        object.__setattr__(self, "extra", dict(self.extra))

    def is_feature_enabled(self, feature_name: str, default: bool = False) -> bool:
        return bool(self.feature_toggles.get(feature_name, default))

    def with_feature_toggle(self, feature_name: str, enabled: bool) -> "StructuralUnderstandingEngineConfig":
        merged: Dict[str, bool] = dict(self.feature_toggles)
        merged[feature_name] = enabled
        return replace(self, feature_toggles=merged)

    def with_extra(self, **changes: Any) -> "StructuralUnderstandingEngineConfig":
        merged: Dict[str, Any] = dict(self.extra)
        merged.update(changes)
        return replace(self, extra=merged)


def default_config(
    strict_structural_validation: bool = DEFAULT_STRICT_STRUCTURAL_VALIDATION,
    feature_toggles: Optional[Mapping[str, bool]] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> StructuralUnderstandingEngineConfig:
    """Convenience factory for the engine's default configuration.
    Every argument is optional so `default_config()` alone is always a
    valid, usable configuration."""
    return StructuralUnderstandingEngineConfig(
        strict_structural_validation=strict_structural_validation,
        feature_toggles=dict(feature_toggles or {}),
        extra=dict(extra or {}),
    )


__all__ = [
    "DEFAULT_STRICT_STRUCTURAL_VALIDATION",
    "StructuralUnderstandingEngineConfig",
    "StructuralUnderstandingEngineConfigError",
    "default_config",
]
