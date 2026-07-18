"""
modules/heading_recognizers/registry.py — M4.2A: recognizer
registration, validation, lookup, ordering, and lifecycle management.

Unlike modules/recognizers/registry.py (a plain block_type -> [recognizer]
map with no lifecycle concept, appropriate for that framework's
stateless, always-on recognizers), heading recognizers are
individually enable/disable-able and ordered by a configurable
priority — so this registry is a small stateful class rather than a
bare module-level dict. A module-level default instance is still
provided (`default_registry`) so most call sites can use the plain
function API below without constructing their own registry, mirroring
the ergonomics of the Stage D registry's `register`/`candidates_for`.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

from modules.heading_recognizers.base import HeadingRecognizer
from modules.heading_recognizers.config import HeadingRecognitionConfig, default_config
from modules.heading_recognizers.enums import RecognizerState
from modules.heading_recognizers.exceptions import RecognizerLookupError, RecognizerRegistrationError

logger = logging.getLogger("ncert_pipeline.heading_recognizers")


def _validate_recognizer(recognizer: HeadingRecognizer) -> None:
    """Structural validation applied to every recognizer at
    registration time — catches an incomplete/misconfigured
    recognizer immediately rather than letting it fail confusingly
    the first time the pipeline calls it."""
    if not isinstance(recognizer, HeadingRecognizer):
        raise RecognizerRegistrationError(
            f"Object {recognizer!r} is not a HeadingRecognizer instance."
        )
    if not getattr(recognizer, "name", None) or not isinstance(recognizer.name, str):
        raise RecognizerRegistrationError(
            f"Recognizer {type(recognizer).__name__} must declare a non-empty string `name`."
        )
    if recognizer.classification is None:
        raise RecognizerRegistrationError(
            f"Recognizer '{recognizer.name}' must declare a `classification`."
        )
    if not callable(getattr(recognizer, "recognize", None)):
        raise RecognizerRegistrationError(
            f"Recognizer '{recognizer.name}' must implement a callable `recognize()`."
        )


class RecognizerRegistry:
    """Tracks every registered heading recognizer, its lifecycle
    state, and the priority order RecognitionPipeline should invoke
    them in. Registration order is preserved as a stable tie-breaker
    whenever two recognizers share a priority, so pipeline output is
    deterministic across runs for a given registration sequence
    (M4.2A's "deterministic execution" requirement starts here, not
    just in the pipeline itself)."""

    def __init__(self, config: Optional[HeadingRecognitionConfig] = None) -> None:
        self._config = config or default_config()
        self._recognizers: Dict[str, HeadingRecognizer] = {}
        self._state: Dict[str, RecognizerState] = {}
        self._order: List[str] = []  # registration order, for stable tie-breaking

    # -- registration --------------------------------------------------

    def register(self, recognizer: HeadingRecognizer) -> None:
        """Registers `recognizer`, keyed by its own `name`. Raises
        RecognizerRegistrationError on structural problems or a
        duplicate name — callers that intend to replace an existing
        registration must call `unregister()` first, so accidental
        double-registration (e.g. a module imported twice) is caught
        rather than silently overwriting."""
        _validate_recognizer(recognizer)
        if recognizer.name in self._recognizers:
            raise RecognizerRegistrationError(
                f"A recognizer named '{recognizer.name}' is already registered "
                f"({type(self._recognizers[recognizer.name]).__name__}); "
                f"call unregister('{recognizer.name}') first to replace it."
            )
        self._recognizers[recognizer.name] = recognizer
        self._order.append(recognizer.name)
        settings = self._config.settings_for(recognizer.name)
        self._state[recognizer.name] = (
            RecognizerState.ENABLED if settings.enabled else RecognizerState.DISABLED
        )
        logger.debug("Registered heading recognizer '%s' (%s).", recognizer.name, self._state[recognizer.name].value)

    def unregister(self, name: str) -> None:
        """Removes a recognizer entirely (not the same as disabling
        it — a disabled recognizer is still registered and still
        appears in `all_recognizers()`; an unregistered one is gone)."""
        if name not in self._recognizers:
            raise RecognizerLookupError(f"No recognizer named '{name}' is registered.")
        del self._recognizers[name]
        del self._state[name]
        self._order.remove(name)

    # -- lifecycle --------------------------------------------------

    def enable(self, name: str) -> None:
        self._require(name)
        self._state[name] = RecognizerState.ENABLED

    def disable(self, name: str) -> None:
        self._require(name)
        self._state[name] = RecognizerState.DISABLED

    def mark_failed(self, name: str) -> None:
        """Called by RecognitionPipeline when a recognizer raises
        repeatedly / unrecoverably during a run — distinct from
        DISABLED (an operator choice) so diagnostics can tell the two
        apart. A FAILED recognizer is still registered but is treated
        as not-enabled by `is_enabled()`."""
        self._require(name)
        self._state[name] = RecognizerState.FAILED

    def state_of(self, name: str) -> RecognizerState:
        self._require(name)
        return self._state[name]

    def is_enabled(self, name: str) -> bool:
        return self.state_of(name) == RecognizerState.ENABLED

    # -- lookup / ordering --------------------------------------------------

    def get(self, name: str) -> HeadingRecognizer:
        self._require(name)
        return self._recognizers[name]

    def all_recognizers(self) -> List[HeadingRecognizer]:
        """All registered recognizers (any lifecycle state), in a
        stable, deterministic order: ascending
        RecognizerSettings.priority, then registration order for
        ties. This is the single ordering RecognitionPipeline relies
        on for deterministic output."""
        def sort_key(name: str) -> tuple:
            priority = self._config.settings_for(name).priority
            return (priority, self._order.index(name))

        ordered_names = sorted(self._recognizers.keys(), key=sort_key)
        return [self._recognizers[n] for n in ordered_names]

    def enabled_recognizers(self) -> List[HeadingRecognizer]:
        """Same ordering as `all_recognizers()`, filtered to only
        ENABLED recognizers — what RecognitionPipeline actually
        iterates over."""
        return [r for r in self.all_recognizers() if self.is_enabled(r.name)]

    def registered_names(self) -> List[str]:
        return list(self._order)

    def __contains__(self, name: str) -> bool:
        return name in self._recognizers

    def __len__(self) -> int:
        return len(self._recognizers)

    def _require(self, name: str) -> None:
        if name not in self._recognizers:
            raise RecognizerLookupError(f"No recognizer named '{name}' is registered.")

    @property
    def config(self) -> HeadingRecognitionConfig:
        return self._config

    def with_config(self, config: HeadingRecognitionConfig) -> "RecognizerRegistry":
        """Returns a NEW registry with the same registered recognizers
        (same instances, same registration order) but re-derived
        lifecycle state from `config`. The current registry is left
        untouched — mirrors the immutable-config convention used
        throughout this framework, applied to the one piece of
        registry state (enabled/disabled) that config actually
        drives."""
        new_registry = RecognizerRegistry(config=config)
        for name in self._order:
            new_registry.register(self._recognizers[name])
        return new_registry


# -- module-level default registry + convenience functions --------------------------------------------------
#
# Mirrors modules/recognizers/registry.py's plain-function ergonomics
# for the common case of "one registry for the whole process". Code
# that needs an isolated registry (e.g. tests) should construct its
# own RecognizerRegistry() instead of using these.

default_registry = RecognizerRegistry()


def register(recognizer: HeadingRecognizer) -> None:
    default_registry.register(recognizer)


def unregister(name: str) -> None:
    default_registry.unregister(name)


def get(name: str) -> HeadingRecognizer:
    return default_registry.get(name)


def enabled_recognizers() -> List[HeadingRecognizer]:
    return default_registry.enabled_recognizers()


def all_recognizers() -> List[HeadingRecognizer]:
    return default_registry.all_recognizers()


__all__ = [
    "RecognizerRegistry",
    "default_registry",
    "register",
    "unregister",
    "get",
    "enabled_recognizers",
    "all_recognizers",
]
