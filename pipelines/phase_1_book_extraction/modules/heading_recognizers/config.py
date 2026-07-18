"""
modules/heading_recognizers/config.py — M4.2A: framework configuration.

Deliberately a data-driven, immutable settings object rather than
inline constants or if/else branching — the same philosophy
stage_c_priority.py documents for its own DEFAULT_PRIORITY_MAP: a
caller (or a future config file/env override) can adjust thresholds,
priorities, and feature toggles per deployment or per recognizer
without touching framework or recognizer code. Nothing in this
module hard-codes a concrete recognizer name; RecognizerSettings
entries are looked up by whatever `name` a recognizer declares.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional

from modules.heading_recognizers.enums import ConflictResolutionStrategy
from modules.heading_recognizers.exceptions import RecognizerConfigurationError

# Framework-wide defaults. Concrete recognizers may be given a
# per-recognizer override via RecognizerSettings; these are only the
# fallback when no override is present.
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.5
DEFAULT_PRIORITY: int = 100
DEFAULT_CONFLICT_RESOLUTION = ConflictResolutionStrategy.HIGHEST_CONFIDENCE


def _validate_unit_interval(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RecognizerConfigurationError(f"{field_name} must be a number, got {type(value).__name__}.")
    if not (0.0 <= float(value) <= 1.0):
        raise RecognizerConfigurationError(f"{field_name} must be within [0.0, 1.0], got {value!r}.")


@dataclass(frozen=True)
class RecognizerSettings:
    """Per-recognizer configuration, looked up by the recognizer's own
    `name`. Immutable — callers that need a variant call
    `with_overrides()` and get a new instance back rather than
    mutating this one, so a RecognizerSettings handed to one
    recognizer instance can never be silently changed by another."""

    name: str
    enabled: bool = True
    priority: int = DEFAULT_PRIORITY
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise RecognizerConfigurationError("RecognizerSettings.name must be a non-empty string.")
        _validate_unit_interval(self.confidence_threshold, f"RecognizerSettings({self.name}).confidence_threshold")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise RecognizerConfigurationError(
                f"RecognizerSettings({self.name}).priority must be an int, got {type(self.priority).__name__}."
            )
        # MappingProxyType-ify defensively so `extra` can't be mutated
        # through a reference held elsewhere after construction.
        object.__setattr__(self, "extra", dict(self.extra))

    def with_overrides(self, **changes: Any) -> "RecognizerSettings":
        return replace(self, **changes)


@dataclass(frozen=True)
class HeadingRecognitionConfig:
    """Immutable, framework-wide configuration. Built once (via
    `default_config()` or a caller-supplied variant) and threaded
    through RecognizerFactory / RecognizerRegistry / RecognitionPipeline
    — none of which ever mutate it; all "change a setting" operations
    return a new HeadingRecognitionConfig via `with_recognizer_settings`
    / `with_feature_toggle`."""

    global_confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    conflict_resolution: ConflictResolutionStrategy = DEFAULT_CONFLICT_RESOLUTION
    recognizer_settings: Mapping[str, RecognizerSettings] = field(default_factory=dict)
    feature_toggles: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_unit_interval(self.global_confidence_threshold, "HeadingRecognitionConfig.global_confidence_threshold")
        if not isinstance(self.conflict_resolution, ConflictResolutionStrategy):
            raise RecognizerConfigurationError(
                "HeadingRecognitionConfig.conflict_resolution must be a ConflictResolutionStrategy, "
                f"got {type(self.conflict_resolution).__name__}."
            )
        object.__setattr__(self, "recognizer_settings", dict(self.recognizer_settings))
        object.__setattr__(self, "feature_toggles", dict(self.feature_toggles))

    def settings_for(self, recognizer_name: str) -> RecognizerSettings:
        """Returns this recognizer's settings, or a framework-default
        RecognizerSettings (enabled, default priority/threshold) if
        none was configured explicitly — future recognizers therefore
        work out of the box with zero configuration required."""
        existing = self.recognizer_settings.get(recognizer_name)
        if existing is not None:
            return existing
        return RecognizerSettings(
            name=recognizer_name,
            enabled=True,
            priority=DEFAULT_PRIORITY,
            confidence_threshold=self.global_confidence_threshold,
        )

    def is_feature_enabled(self, feature_name: str, default: bool = False) -> bool:
        return bool(self.feature_toggles.get(feature_name, default))

    def with_recognizer_settings(self, settings: RecognizerSettings) -> "HeadingRecognitionConfig":
        """Returns a new config with `settings` merged in (added or
        replacing any existing entry for the same name)."""
        merged: Dict[str, RecognizerSettings] = dict(self.recognizer_settings)
        merged[settings.name] = settings
        return replace(self, recognizer_settings=merged)

    def with_feature_toggle(self, feature_name: str, enabled: bool) -> "HeadingRecognitionConfig":
        merged: Dict[str, bool] = dict(self.feature_toggles)
        merged[feature_name] = enabled
        return replace(self, feature_toggles=merged)


def default_config(
    global_confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    conflict_resolution: ConflictResolutionStrategy = DEFAULT_CONFLICT_RESOLUTION,
    recognizer_settings: Optional[Mapping[str, RecognizerSettings]] = None,
    feature_toggles: Optional[Mapping[str, bool]] = None,
) -> HeadingRecognitionConfig:
    """Convenience factory for the framework's default configuration.
    Every argument is optional so `default_config()` alone is always a
    valid, usable configuration."""
    return HeadingRecognitionConfig(
        global_confidence_threshold=global_confidence_threshold,
        conflict_resolution=conflict_resolution,
        recognizer_settings=dict(recognizer_settings or {}),
        feature_toggles=dict(feature_toggles or {}),
    )


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_PRIORITY",
    "DEFAULT_CONFLICT_RESOLUTION",
    "RecognizerSettings",
    "HeadingRecognitionConfig",
    "default_config",
]
