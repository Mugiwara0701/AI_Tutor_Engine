"""
modules/heading_recognizers/factory.py — M4.2A: creates recognizer
instances from framework configuration.

The factory is what lets M4.2B/C and later milestones add a brand
new recognizer by doing ONLY two things: (1) define a
`HeadingRecognizer` subclass somewhere in this package, and (2) call
`factory.register_class(...)` once (typically from
modules/heading_recognizers/__init__.py, mirroring
modules/recognizers/__init__.py's own one-`register(...)`-call
convention) — nothing here, in registry.py, or in pipeline.py needs
to change. The factory is deliberately the ONLY place that knows how
to turn "a recognizer class + its configured settings" into a live
instance; RecognizerRegistry only ever deals in already-constructed
`HeadingRecognizer` objects.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Type

from modules.heading_recognizers.base import HeadingRecognizer
from modules.heading_recognizers.config import HeadingRecognitionConfig, RecognizerSettings, default_config
from modules.heading_recognizers.exceptions import RecognizerConfigurationError
from modules.heading_recognizers.registry import RecognizerRegistry

logger = logging.getLogger("ncert_pipeline.heading_recognizers")

# A recognizer factory function takes the resolved RecognizerSettings
# for that recognizer and returns a constructed instance. Plain class
# constructors satisfy this signature when they accept `settings=...`;
# `register_class` also accepts a bare `Type[HeadingRecognizer]` and
# wraps it, so most recognizers never need to write a factory function
# by hand.
RecognizerBuilder = Callable[[RecognizerSettings], HeadingRecognizer]


class RecognizerFactory:
    """Builds `HeadingRecognizer` instances by name, using whichever
    class/builder was registered under that name and the matching
    `RecognizerSettings` resolved from this factory's
    `HeadingRecognitionConfig`."""

    def __init__(self, config: Optional[HeadingRecognitionConfig] = None) -> None:
        self._config = config or default_config()
        self._builders: Dict[str, RecognizerBuilder] = {}

    def register_class(
        self,
        name: str,
        recognizer_cls_or_builder: "Type[HeadingRecognizer] | RecognizerBuilder",
    ) -> None:
        """Registers a recognizer class (or a custom builder function,
        for the rare recognizer whose constructor needs more than
        `settings`) under `name`. `name` must match the `name` the
        constructed recognizer instance will itself report — this is
        checked at `create()` time, not here, since a bare class
        can't be introspected for its instance attribute without
        instantiating it first."""
        if not name or not isinstance(name, str):
            raise RecognizerConfigurationError("register_class() requires a non-empty string `name`.")
        if isinstance(recognizer_cls_or_builder, type):
            if not issubclass(recognizer_cls_or_builder, HeadingRecognizer):
                raise RecognizerConfigurationError(
                    f"register_class('{name}', ...) requires a HeadingRecognizer subclass, "
                    f"got {recognizer_cls_or_builder!r}."
                )
            cls = recognizer_cls_or_builder

            def _default_builder(settings: RecognizerSettings, _cls: Type[HeadingRecognizer] = cls) -> HeadingRecognizer:
                try:
                    return _cls(settings=settings)
                except TypeError:
                    # Recognizer with a no-arg constructor (settings not
                    # needed for its logic) — still perfectly valid.
                    return _cls()

            self._builders[name] = _default_builder
        elif callable(recognizer_cls_or_builder):
            self._builders[name] = recognizer_cls_or_builder
        else:
            raise RecognizerConfigurationError(
                f"register_class('{name}', ...) requires a HeadingRecognizer subclass or a callable builder."
            )

    def registered_names(self) -> List[str]:
        return list(self._builders.keys())

    def create(self, name: str) -> HeadingRecognizer:
        """Builds one recognizer by name. Raises
        RecognizerConfigurationError if `name` was never registered
        with this factory, or if the built instance's own `.name`
        doesn't match `name` (a common copy-paste bug when adding a
        new recognizer)."""
        if name not in self._builders:
            raise RecognizerConfigurationError(
                f"No recognizer class/builder registered under '{name}'. "
                f"Known names: {sorted(self._builders.keys())!r}."
            )
        settings = self._config.settings_for(name)
        instance = self._builders[name](settings)
        if not isinstance(instance, HeadingRecognizer):
            raise RecognizerConfigurationError(
                f"Builder for '{name}' returned {instance!r}, which is not a HeadingRecognizer."
            )
        if instance.name != name:
            raise RecognizerConfigurationError(
                f"Builder registered under '{name}' produced a recognizer whose own name is "
                f"'{instance.name}' — these must match."
            )
        return instance

    def create_all(self) -> List[HeadingRecognizer]:
        """Builds every registered recognizer, in registration order."""
        return [self.create(name) for name in self._builders]

    def build_registry(self, registry: Optional[RecognizerRegistry] = None) -> RecognizerRegistry:
        """Convenience: builds every registered recognizer and
        registers each into `registry` (a fresh RecognizerRegistry
        sharing this factory's config, by default). Returns the
        registry for chaining."""
        target = registry if registry is not None else RecognizerRegistry(config=self._config)
        for recognizer in self.create_all():
            target.register(recognizer)
        return target

    @property
    def config(self) -> HeadingRecognitionConfig:
        return self._config

    def with_config(self, config: HeadingRecognitionConfig) -> "RecognizerFactory":
        """Returns a NEW factory with the same registered
        classes/builders but a different configuration — this factory
        is left untouched, mirroring the rest of the framework's
        immutable-config convention."""
        new_factory = RecognizerFactory(config=config)
        new_factory._builders = dict(self._builders)
        return new_factory


__all__ = [
    "RecognizerBuilder",
    "RecognizerFactory",
]
