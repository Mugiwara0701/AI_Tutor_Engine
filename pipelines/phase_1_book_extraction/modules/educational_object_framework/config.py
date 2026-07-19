"""
modules/educational_object_framework/config.py — M5.1: framework
configuration.

Mirrors modules/heading_canonicalization/config.py's approach exactly
(per the M5.1 spec's requirement: "Reuse the existing configuration
approach. Do NOT introduce another configuration mechanism.") — a
data-driven, immutable settings object rather than inline constants or
if/else branching, exactly as `heading_canonicalization.config`
mirrored `heading_recognizers.config` before it. This is deliberately
a per-package config module, not a shared one — the same convention
every existing framework package in this repository already follows
(`heading_recognizers/config.py`, `heading_canonicalization/config.py`
each define their own settings/config types); introducing a single
shared config module across packages would itself be a second
configuration mechanism, which the spec explicitly rules out.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional

from modules.educational_object_framework.exceptions import ProcessorConfigurationError

# Framework-wide defaults. Concrete processors may be given a
# per-processor override via ProcessorSettings; this is only the
# fallback when no override is present.
DEFAULT_PRIORITY: int = 100


@dataclass(frozen=True)
class ProcessorSettings:
    """Per-processor configuration, looked up by the processor's own
    `name`. Immutable — callers that need a variant call
    `with_overrides()` and get a new instance back rather than
    mutating this one. Mirrors
    `heading_canonicalization.config.CanonicalizerSettings`."""

    name: str
    enabled: bool = True
    priority: int = DEFAULT_PRIORITY
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ProcessorConfigurationError("ProcessorSettings.name must be a non-empty string.")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ProcessorConfigurationError(
                f"ProcessorSettings({self.name}).priority must be an int, got {type(self.priority).__name__}."
            )
        object.__setattr__(self, "extra", dict(self.extra))

    def with_overrides(self, **changes: Any) -> "ProcessorSettings":
        return replace(self, **changes)


@dataclass(frozen=True)
class EducationalObjectFrameworkConfig:
    """Immutable, framework-wide configuration. Built once (via
    `default_config()` or a caller-supplied variant) and threaded
    through `ProcessorRegistry` / `ProcessingPipeline` — neither of
    which ever mutate it; all "change a setting" operations return a
    new `EducationalObjectFrameworkConfig` via
    `with_processor_settings` / `with_feature_toggle`."""

    processor_settings: Mapping[str, ProcessorSettings] = field(default_factory=dict)
    feature_toggles: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "processor_settings", dict(self.processor_settings))
        object.__setattr__(self, "feature_toggles", dict(self.feature_toggles))

    def settings_for(self, processor_name: str) -> ProcessorSettings:
        """Returns this processor's settings, or a framework-default
        `ProcessorSettings` (enabled, default priority) if none was
        configured explicitly — future processors therefore work out
        of the box with zero configuration required."""
        existing = self.processor_settings.get(processor_name)
        if existing is not None:
            return existing
        return ProcessorSettings(name=processor_name, enabled=True, priority=DEFAULT_PRIORITY)

    def is_feature_enabled(self, feature_name: str, default: bool = False) -> bool:
        return bool(self.feature_toggles.get(feature_name, default))

    def with_processor_settings(self, settings: ProcessorSettings) -> "EducationalObjectFrameworkConfig":
        """Returns a new config with `settings` merged in (added or
        replacing any existing entry for the same name)."""
        merged: Dict[str, ProcessorSettings] = dict(self.processor_settings)
        merged[settings.name] = settings
        return replace(self, processor_settings=merged)

    def with_feature_toggle(self, feature_name: str, enabled: bool) -> "EducationalObjectFrameworkConfig":
        merged: Dict[str, bool] = dict(self.feature_toggles)
        merged[feature_name] = enabled
        return replace(self, feature_toggles=merged)


def default_config(
    processor_settings: Optional[Mapping[str, ProcessorSettings]] = None,
    feature_toggles: Optional[Mapping[str, bool]] = None,
) -> EducationalObjectFrameworkConfig:
    """Convenience factory for the framework's default configuration.
    Every argument is optional so `default_config()` alone is always a
    valid, usable configuration."""
    return EducationalObjectFrameworkConfig(
        processor_settings=dict(processor_settings or {}),
        feature_toggles=dict(feature_toggles or {}),
    )


__all__ = [
    "DEFAULT_PRIORITY",
    "ProcessorSettings",
    "EducationalObjectFrameworkConfig",
    "default_config",
]
