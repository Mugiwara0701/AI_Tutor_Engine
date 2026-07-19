"""
modules/educational_object_framework/registry.py — M5.1: processor
registration, validation, lookup, ordering, and lifecycle management.

Mirrors modules/heading_canonicalization/registry.py exactly, applied
to `EducationalObjectProcessor` instead of `HeadingCanonicalizer`: a
small stateful class (processors are individually enable/disable-able
and ordered by a configurable priority), plus a module-level default
instance (`default_registry`) so most call sites can use the plain
function API below without constructing their own registry — and, per
the M5.1 spec's performance requirement ("avoid rebuilding registries
... reuse singleton components"), so a future integration point can
depend on one shared registry instance across a whole run instead of
constructing a fresh one per object.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from modules.educational_object_framework.base import EducationalObjectProcessor
from modules.educational_object_framework.config import (
    EducationalObjectFrameworkConfig,
    default_config,
)
from modules.educational_object_framework.enums import ProcessorState
from modules.educational_object_framework.exceptions import (
    ProcessorLookupError,
    ProcessorRegistrationError,
)

logger = logging.getLogger("ncert_pipeline.educational_object_framework")


def _validate_processor(processor: EducationalObjectProcessor) -> None:
    """Structural validation applied to every processor at
    registration time — catches an incomplete/misconfigured processor
    immediately rather than letting it fail confusingly the first
    time the pipeline calls it."""
    if not isinstance(processor, EducationalObjectProcessor):
        raise ProcessorRegistrationError(
            f"Object {processor!r} is not an EducationalObjectProcessor instance."
        )
    if not getattr(processor, "name", None) or not isinstance(processor.name, str):
        raise ProcessorRegistrationError(
            f"Processor {type(processor).__name__} must declare a non-empty string `name`."
        )
    if not callable(getattr(processor, "process", None)):
        raise ProcessorRegistrationError(
            f"Processor '{processor.name}' must implement a callable `process()`."
        )


class ProcessorRegistry:
    """Tracks every registered processor, its lifecycle state, and the
    priority order `ProcessingPipeline` should invoke them in.
    Registration order is preserved as a stable tie-breaker whenever
    two processors share a priority, so pipeline output is
    deterministic across runs for a given registration sequence —
    identical contract to
    `heading_canonicalization.registry.CanonicalizerRegistry`."""

    def __init__(self, config: Optional[EducationalObjectFrameworkConfig] = None) -> None:
        self._config = config or default_config()
        self._processors: Dict[str, EducationalObjectProcessor] = {}
        self._state: Dict[str, ProcessorState] = {}
        self._order: List[str] = []  # registration order, for stable tie-breaking

    # -- registration --------------------------------------------------

    def register(self, processor: EducationalObjectProcessor) -> None:
        """Registers `processor`, keyed by its own `name`. Raises
        ProcessorRegistrationError on structural problems or a
        duplicate name — callers that intend to replace an existing
        registration must call `unregister()` first."""
        _validate_processor(processor)
        if processor.name in self._processors:
            raise ProcessorRegistrationError(
                f"A processor named '{processor.name}' is already registered "
                f"({type(self._processors[processor.name]).__name__}); "
                f"call unregister('{processor.name}') first to replace it."
            )
        self._processors[processor.name] = processor
        self._order.append(processor.name)
        settings = self._config.settings_for(processor.name)
        self._state[processor.name] = (
            ProcessorState.ENABLED if settings.enabled else ProcessorState.DISABLED
        )
        logger.debug(
            "Registered educational object processor '%s' (%s).",
            processor.name, self._state[processor.name].value,
        )

    def unregister(self, name: str) -> None:
        """Removes a processor entirely (not the same as disabling it
        — a disabled processor is still registered and still appears
        in `all_processors()`; an unregistered one is gone)."""
        if name not in self._processors:
            raise ProcessorLookupError(f"No processor named '{name}' is registered.")
        del self._processors[name]
        del self._state[name]
        self._order.remove(name)

    # -- lifecycle --------------------------------------------------

    def enable(self, name: str) -> None:
        self._require(name)
        self._state[name] = ProcessorState.ENABLED

    def disable(self, name: str) -> None:
        self._require(name)
        self._state[name] = ProcessorState.DISABLED

    def mark_failed(self, name: str) -> None:
        """Called when a processor raises repeatedly / unrecoverably
        during a run — distinct from DISABLED (an operator choice) so
        diagnostics can tell the two apart. A FAILED processor is
        still registered but is treated as not-enabled by
        `is_enabled()`."""
        self._require(name)
        self._state[name] = ProcessorState.FAILED

    def state_of(self, name: str) -> ProcessorState:
        self._require(name)
        return self._state[name]

    def is_enabled(self, name: str) -> bool:
        return self.state_of(name) == ProcessorState.ENABLED

    # -- lookup / ordering --------------------------------------------------

    def get(self, name: str) -> EducationalObjectProcessor:
        self._require(name)
        return self._processors[name]

    def all_processors(self) -> List[EducationalObjectProcessor]:
        """All registered processors (any lifecycle state), in a
        stable, deterministic order: ascending
        `ProcessorSettings.priority`, then registration order for
        ties. This is the single ordering `ProcessingPipeline` relies
        on for deterministic output."""
        def sort_key(name: str) -> tuple:
            priority = self._config.settings_for(name).priority
            return (priority, self._order.index(name))

        ordered_names = sorted(self._processors.keys(), key=sort_key)
        return [self._processors[n] for n in ordered_names]

    def enabled_processors(self) -> List[EducationalObjectProcessor]:
        """Same ordering as `all_processors()`, filtered to only
        ENABLED processors — what `ProcessingPipeline` actually
        iterates over."""
        return [p for p in self.all_processors() if self.is_enabled(p.name)]

    def registered_names(self) -> List[str]:
        return list(self._order)

    def __contains__(self, name: str) -> bool:
        return name in self._processors

    def __len__(self) -> int:
        return len(self._processors)

    def _require(self, name: str) -> None:
        if name not in self._processors:
            raise ProcessorLookupError(f"No processor named '{name}' is registered.")

    @property
    def config(self) -> EducationalObjectFrameworkConfig:
        return self._config

    def with_config(self, config: EducationalObjectFrameworkConfig) -> "ProcessorRegistry":
        """Returns a NEW registry with the same registered processors
        (same instances, same registration order) but re-derived
        lifecycle state from `config`. The current registry is left
        untouched."""
        new_registry = ProcessorRegistry(config=config)
        for name in self._order:
            new_registry.register(self._processors[name])
        return new_registry


# -- module-level default registry + convenience functions --------------------------------------------------
#
# Mirrors heading_canonicalization.registry's plain-function
# ergonomics for the common case of "one registry for the whole
# process" — also satisfies the M5.1 spec's "singleton-friendly"
# registry requirement: `default_registry` is constructed once, at
# import time, and every M5.2 processor registers into this same
# instance. Code that needs an isolated registry (e.g. tests) should
# construct its own ProcessorRegistry() instead of using these.

default_registry = ProcessorRegistry()


def register(processor: EducationalObjectProcessor) -> None:
    default_registry.register(processor)


def unregister(name: str) -> None:
    default_registry.unregister(name)


def get(name: str) -> EducationalObjectProcessor:
    return default_registry.get(name)


def enabled_processors() -> List[EducationalObjectProcessor]:
    return default_registry.enabled_processors()


def all_processors() -> List[EducationalObjectProcessor]:
    return default_registry.all_processors()


__all__ = [
    "ProcessorRegistry",
    "default_registry",
    "register",
    "unregister",
    "get",
    "enabled_processors",
    "all_processors",
]
