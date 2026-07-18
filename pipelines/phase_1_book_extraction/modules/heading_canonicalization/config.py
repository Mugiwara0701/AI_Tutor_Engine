"""
modules/heading_canonicalization/config.py — M4.3A: framework
configuration.

Mirrors modules/heading_recognizers/config.py's approach exactly (per
the M4.3A spec's requirement #7: "Support framework configuration
using the existing configuration approach. Do not introduce a second
configuration system.") — a data-driven, immutable settings object
rather than inline constants or if/else branching. A canonicalizer has
no confidence score to threshold (unlike a recognizer, it either
applies or doesn't — see `base.HeadingCanonicalizer.canonicalize()`),
so this config carries `enabled`/`priority`/`extra` per canonicalizer
but no `confidence_threshold` field.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional

from modules.heading_canonicalization.exceptions import CanonicalizerConfigurationError

# Framework-wide defaults. Concrete canonicalizers may be given a
# per-canonicalizer override via CanonicalizerSettings; this is only
# the fallback when no override is present.
DEFAULT_PRIORITY: int = 100


@dataclass(frozen=True)
class CanonicalizerSettings:
    """Per-canonicalizer configuration, looked up by the
    canonicalizer's own `name`. Immutable — callers that need a
    variant call `with_overrides()` and get a new instance back
    rather than mutating this one. Mirrors
    `heading_recognizers.config.RecognizerSettings`, minus the
    confidence-threshold field a canonicalizer has no use for."""

    name: str
    enabled: bool = True
    priority: int = DEFAULT_PRIORITY
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise CanonicalizerConfigurationError("CanonicalizerSettings.name must be a non-empty string.")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise CanonicalizerConfigurationError(
                f"CanonicalizerSettings({self.name}).priority must be an int, got {type(self.priority).__name__}."
            )
        object.__setattr__(self, "extra", dict(self.extra))

    def with_overrides(self, **changes: Any) -> "CanonicalizerSettings":
        return replace(self, **changes)


@dataclass(frozen=True)
class HeadingCanonicalizationConfig:
    """Immutable, framework-wide configuration. Built once (via
    `default_config()` or a caller-supplied variant) and threaded
    through `CanonicalizerRegistry` / `CanonicalizationPipeline` —
    neither of which ever mutate it; all "change a setting" operations
    return a new `HeadingCanonicalizationConfig` via
    `with_canonicalizer_settings` / `with_feature_toggle`."""

    canonicalizer_settings: Mapping[str, CanonicalizerSettings] = field(default_factory=dict)
    feature_toggles: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonicalizer_settings", dict(self.canonicalizer_settings))
        object.__setattr__(self, "feature_toggles", dict(self.feature_toggles))

    def settings_for(self, canonicalizer_name: str) -> CanonicalizerSettings:
        """Returns this canonicalizer's settings, or a
        framework-default `CanonicalizerSettings` (enabled, default
        priority) if none was configured explicitly — future
        canonicalizers therefore work out of the box with zero
        configuration required."""
        existing = self.canonicalizer_settings.get(canonicalizer_name)
        if existing is not None:
            return existing
        return CanonicalizerSettings(name=canonicalizer_name, enabled=True, priority=DEFAULT_PRIORITY)

    def is_feature_enabled(self, feature_name: str, default: bool = False) -> bool:
        return bool(self.feature_toggles.get(feature_name, default))

    def with_canonicalizer_settings(self, settings: CanonicalizerSettings) -> "HeadingCanonicalizationConfig":
        """Returns a new config with `settings` merged in (added or
        replacing any existing entry for the same name)."""
        merged: Dict[str, CanonicalizerSettings] = dict(self.canonicalizer_settings)
        merged[settings.name] = settings
        return replace(self, canonicalizer_settings=merged)

    def with_feature_toggle(self, feature_name: str, enabled: bool) -> "HeadingCanonicalizationConfig":
        merged: Dict[str, bool] = dict(self.feature_toggles)
        merged[feature_name] = enabled
        return replace(self, feature_toggles=merged)


def default_config(
    canonicalizer_settings: Optional[Mapping[str, CanonicalizerSettings]] = None,
    feature_toggles: Optional[Mapping[str, bool]] = None,
) -> HeadingCanonicalizationConfig:
    """Convenience factory for the framework's default configuration.
    Every argument is optional so `default_config()` alone is always a
    valid, usable configuration."""
    return HeadingCanonicalizationConfig(
        canonicalizer_settings=dict(canonicalizer_settings or {}),
        feature_toggles=dict(feature_toggles or {}),
    )


__all__ = [
    "DEFAULT_PRIORITY",
    "CanonicalizerSettings",
    "HeadingCanonicalizationConfig",
    "default_config",
]
