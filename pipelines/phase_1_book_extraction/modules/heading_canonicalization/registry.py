"""
modules/heading_canonicalization/registry.py — M4.3A: canonicalizer
registration, validation, lookup, ordering, and lifecycle management.

Mirrors modules/heading_recognizers/registry.py exactly, applied to
`HeadingCanonicalizer` instead of `HeadingRecognizer`: a small
stateful class (canonicalizers are individually enable/disable-able
and ordered by a configurable priority), plus a module-level default
instance (`default_registry`) so most call sites can use the plain
function API below without constructing their own registry.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from modules.heading_canonicalization.base import HeadingCanonicalizer
from modules.heading_canonicalization.config import HeadingCanonicalizationConfig, default_config
from modules.heading_canonicalization.enums import CanonicalizerState
from modules.heading_canonicalization.exceptions import (
    CanonicalizerLookupError,
    CanonicalizerRegistrationError,
)

logger = logging.getLogger("ncert_pipeline.heading_canonicalization")


def _validate_canonicalizer(canonicalizer: HeadingCanonicalizer) -> None:
    """Structural validation applied to every canonicalizer at
    registration time — catches an incomplete/misconfigured
    canonicalizer immediately rather than letting it fail confusingly
    the first time the pipeline calls it."""
    if not isinstance(canonicalizer, HeadingCanonicalizer):
        raise CanonicalizerRegistrationError(
            f"Object {canonicalizer!r} is not a HeadingCanonicalizer instance."
        )
    if not getattr(canonicalizer, "name", None) or not isinstance(canonicalizer.name, str):
        raise CanonicalizerRegistrationError(
            f"Canonicalizer {type(canonicalizer).__name__} must declare a non-empty string `name`."
        )
    if not callable(getattr(canonicalizer, "canonicalize", None)):
        raise CanonicalizerRegistrationError(
            f"Canonicalizer '{canonicalizer.name}' must implement a callable `canonicalize()`."
        )


class CanonicalizerRegistry:
    """Tracks every registered canonicalizer, its lifecycle state, and
    the priority order `CanonicalizationPipeline` should invoke them
    in. Registration order is preserved as a stable tie-breaker
    whenever two canonicalizers share a priority, so pipeline output
    is deterministic across runs for a given registration sequence —
    identical contract to
    `heading_recognizers.registry.RecognizerRegistry`."""

    def __init__(self, config: Optional[HeadingCanonicalizationConfig] = None) -> None:
        self._config = config or default_config()
        self._canonicalizers: Dict[str, HeadingCanonicalizer] = {}
        self._state: Dict[str, CanonicalizerState] = {}
        self._order: List[str] = []  # registration order, for stable tie-breaking

    # -- registration --------------------------------------------------

    def register(self, canonicalizer: HeadingCanonicalizer) -> None:
        """Registers `canonicalizer`, keyed by its own `name`. Raises
        CanonicalizerRegistrationError on structural problems or a
        duplicate name — callers that intend to replace an existing
        registration must call `unregister()` first."""
        _validate_canonicalizer(canonicalizer)
        if canonicalizer.name in self._canonicalizers:
            raise CanonicalizerRegistrationError(
                f"A canonicalizer named '{canonicalizer.name}' is already registered "
                f"({type(self._canonicalizers[canonicalizer.name]).__name__}); "
                f"call unregister('{canonicalizer.name}') first to replace it."
            )
        self._canonicalizers[canonicalizer.name] = canonicalizer
        self._order.append(canonicalizer.name)
        settings = self._config.settings_for(canonicalizer.name)
        self._state[canonicalizer.name] = (
            CanonicalizerState.ENABLED if settings.enabled else CanonicalizerState.DISABLED
        )
        logger.debug(
            "Registered heading canonicalizer '%s' (%s).",
            canonicalizer.name, self._state[canonicalizer.name].value,
        )

    def unregister(self, name: str) -> None:
        """Removes a canonicalizer entirely (not the same as disabling
        it — a disabled canonicalizer is still registered and still
        appears in `all_canonicalizers()`; an unregistered one is
        gone)."""
        if name not in self._canonicalizers:
            raise CanonicalizerLookupError(f"No canonicalizer named '{name}' is registered.")
        del self._canonicalizers[name]
        del self._state[name]
        self._order.remove(name)

    # -- lifecycle --------------------------------------------------

    def enable(self, name: str) -> None:
        self._require(name)
        self._state[name] = CanonicalizerState.ENABLED

    def disable(self, name: str) -> None:
        self._require(name)
        self._state[name] = CanonicalizerState.DISABLED

    def mark_failed(self, name: str) -> None:
        """Called when a canonicalizer raises repeatedly / unrecoverably
        during a run — distinct from DISABLED (an operator choice) so
        diagnostics can tell the two apart. A FAILED canonicalizer is
        still registered but is treated as not-enabled by
        `is_enabled()`."""
        self._require(name)
        self._state[name] = CanonicalizerState.FAILED

    def state_of(self, name: str) -> CanonicalizerState:
        self._require(name)
        return self._state[name]

    def is_enabled(self, name: str) -> bool:
        return self.state_of(name) == CanonicalizerState.ENABLED

    # -- lookup / ordering --------------------------------------------------

    def get(self, name: str) -> HeadingCanonicalizer:
        self._require(name)
        return self._canonicalizers[name]

    def all_canonicalizers(self) -> List[HeadingCanonicalizer]:
        """All registered canonicalizers (any lifecycle state), in a
        stable, deterministic order: ascending
        `CanonicalizerSettings.priority`, then registration order for
        ties. This is the single ordering `CanonicalizationPipeline`
        relies on for deterministic output."""
        def sort_key(name: str) -> tuple:
            priority = self._config.settings_for(name).priority
            return (priority, self._order.index(name))

        ordered_names = sorted(self._canonicalizers.keys(), key=sort_key)
        return [self._canonicalizers[n] for n in ordered_names]

    def enabled_canonicalizers(self) -> List[HeadingCanonicalizer]:
        """Same ordering as `all_canonicalizers()`, filtered to only
        ENABLED canonicalizers — what `CanonicalizationPipeline`
        actually iterates over."""
        return [c for c in self.all_canonicalizers() if self.is_enabled(c.name)]

    def registered_names(self) -> List[str]:
        return list(self._order)

    def __contains__(self, name: str) -> bool:
        return name in self._canonicalizers

    def __len__(self) -> int:
        return len(self._canonicalizers)

    def _require(self, name: str) -> None:
        if name not in self._canonicalizers:
            raise CanonicalizerLookupError(f"No canonicalizer named '{name}' is registered.")

    @property
    def config(self) -> HeadingCanonicalizationConfig:
        return self._config

    def with_config(self, config: HeadingCanonicalizationConfig) -> "CanonicalizerRegistry":
        """Returns a NEW registry with the same registered
        canonicalizers (same instances, same registration order) but
        re-derived lifecycle state from `config`. The current registry
        is left untouched."""
        new_registry = CanonicalizerRegistry(config=config)
        for name in self._order:
            new_registry.register(self._canonicalizers[name])
        return new_registry


# -- module-level default registry + convenience functions --------------------------------------------------
#
# Mirrors heading_recognizers.registry's plain-function ergonomics for
# the common case of "one registry for the whole process". Code that
# needs an isolated registry (e.g. tests) should construct its own
# CanonicalizerRegistry() instead of using these.

default_registry = CanonicalizerRegistry()


def register(canonicalizer: HeadingCanonicalizer) -> None:
    default_registry.register(canonicalizer)


def unregister(name: str) -> None:
    default_registry.unregister(name)


def get(name: str) -> HeadingCanonicalizer:
    return default_registry.get(name)


def enabled_canonicalizers() -> List[HeadingCanonicalizer]:
    return default_registry.enabled_canonicalizers()


def all_canonicalizers() -> List[HeadingCanonicalizer]:
    return default_registry.all_canonicalizers()


__all__ = [
    "CanonicalizerRegistry",
    "default_registry",
    "register",
    "unregister",
    "get",
    "enabled_canonicalizers",
    "all_canonicalizers",
]
