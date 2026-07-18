"""
modules/heading_recognizers — M4.2A: foundation framework for
deterministic heading recognition.

This package is FRAMEWORK ONLY (M4.2A's scope). It defines the
interfaces, execution context, result models, configuration,
registry, factory, recognition pipeline, shared enums, exception
hierarchy, and shared utilities every concrete heading recognizer
will use — but implements no concrete recognizer itself.

Sibling to modules/recognizers (the Stage D Educational-Object
recognizer framework introduced in M4.1): that package answers "given
a Stage B block_type, which reusable-knowledge shape does this block
hold, and how do we extract it"; this package answers a narrower,
earlier question — "is this line of source text a heading, and if
so, what kind and what level" — independent of Stage B block typing,
PDF parsing, layout detection, or VLM inference (all explicitly out
of scope here; see each module's own docstring).

Concrete recognizers (M4.2B: NumberedHeadingRecognizer,
HierarchicalHeadingRecognizer, RomanNumeralHeadingRecognizer,
AlphabeticHeadingRecognizer, ChapterNumberRecognizer,
ChapterTitleRecognizer — the first, generic/language-independent
family, implemented in generic_recognizers.py; language-specific
families are a later milestone's concern) belong in new modules
inside this package, each registered with the shared `default_factory`
via ONE `default_factory.register_class(name, RecognizerClass)` call
below — mirroring modules/recognizers/__init__.py's own
one-`register(...)`-call-per-recognizer convention. Nothing in
base.py, config.py, registry.py, pipeline.py, or utils.py needed to
change to add these six.

`default_factory` builds `default_registry` (both re-exported below)
so callers get a ready-to-use, fully-populated
`RecognitionPipeline(default_registry)` with zero setup — a caller
wanting an isolated set of recognizers (e.g. tests) should still
construct their own RecognizerFactory/RecognizerRegistry instead.

Public API:
    HeadingRecognizer, RecognitionContext, RecognitionResult,
    FailureResult, ConfidenceInfo        — base.py
    HeadingRecognitionConfig, RecognizerSettings, default_config
                                          — config.py
    RecognizerRegistry, default_registry, register, unregister, get,
    enabled_recognizers, all_recognizers — registry.py
    RecognizerFactory                    — factory.py
    RecognitionPipeline, PipelineResult, AttemptRecord
                                          — pipeline.py
    HeadingClassification, ConflictResolutionStrategy,
    RecognizerState, RecognitionOutcome  — enums.py
    HeadingRecognitionError and subclasses
                                          — exceptions.py
    utils.*                              — utils.py (imported as a
                                            submodule; not re-exported
                                            individually here to avoid
                                            crowding this namespace —
                                            `from modules.heading_recognizers import utils`)
"""
from modules.heading_recognizers.base import (
    ConfidenceInfo,
    FailureResult,
    HeadingRecognizer,
    RecognitionContext,
    RecognitionResult,
)
from modules.heading_recognizers.config import (
    HeadingRecognitionConfig,
    RecognizerSettings,
    default_config,
)
from modules.heading_recognizers.enums import (
    ConflictResolutionStrategy,
    HeadingClassification,
    RecognitionOutcome,
    RecognizerState,
)
from modules.heading_recognizers.exceptions import (
    HeadingRecognitionError,
    RecognitionPipelineError,
    RecognizerConfigurationError,
    RecognizerExecutionError,
    RecognizerLookupError,
    RecognizerRegistrationError,
)
from modules.heading_recognizers.factory import RecognizerFactory
from modules.heading_recognizers.pipeline import (
    AttemptRecord,
    PipelineResult,
    RecognitionPipeline,
)
from modules.heading_recognizers.registry import (
    RecognizerRegistry,
    all_recognizers,
    default_registry,
    enabled_recognizers,
    get,
    register,
    unregister,
)
from modules.heading_recognizers.generic_recognizers import (
    AlphabeticHeadingRecognizer,
    ChapterNumberRecognizer,
    ChapterTitleRecognizer,
    HierarchicalHeadingRecognizer,
    NumberedHeadingRecognizer,
    RomanNumeralHeadingRecognizer,
)

# -- M4.2B: register the generic recognizer family ---------------------
#
# `default_factory` is the ONE place a new recognizer class needs to be
# registered (by name); `build_registry(default_registry)` then builds
# one instance of each and registers it into the same `default_registry`
# the plain register()/get()/all_recognizers() functions above already
# operate on, so `default_registry`/`default_factory` stay consistent
# with each other for the common "one registry for the whole process"
# case. Adding a later recognizer family (M4.2C+) is meant to require
# only more `default_factory.register_class(...)` calls here — nothing
# above this block should need to change.
default_factory = RecognizerFactory()
default_factory.register_class(NumberedHeadingRecognizer.name, NumberedHeadingRecognizer)
default_factory.register_class(HierarchicalHeadingRecognizer.name, HierarchicalHeadingRecognizer)
default_factory.register_class(RomanNumeralHeadingRecognizer.name, RomanNumeralHeadingRecognizer)
default_factory.register_class(AlphabeticHeadingRecognizer.name, AlphabeticHeadingRecognizer)
default_factory.register_class(ChapterNumberRecognizer.name, ChapterNumberRecognizer)
default_factory.register_class(ChapterTitleRecognizer.name, ChapterTitleRecognizer)
default_factory.build_registry(default_registry)

__all__ = [
    # base
    "HeadingRecognizer",
    "RecognitionContext",
    "RecognitionResult",
    "FailureResult",
    "ConfidenceInfo",
    # config
    "HeadingRecognitionConfig",
    "RecognizerSettings",
    "default_config",
    # registry
    "RecognizerRegistry",
    "default_registry",
    "register",
    "unregister",
    "get",
    "enabled_recognizers",
    "all_recognizers",
    # factory
    "RecognizerFactory",
    "default_factory",
    # M4.2B generic recognizers
    "NumberedHeadingRecognizer",
    "HierarchicalHeadingRecognizer",
    "RomanNumeralHeadingRecognizer",
    "AlphabeticHeadingRecognizer",
    "ChapterNumberRecognizer",
    "ChapterTitleRecognizer",
    # pipeline
    "RecognitionPipeline",
    "PipelineResult",
    "AttemptRecord",
    # enums
    "HeadingClassification",
    "ConflictResolutionStrategy",
    "RecognizerState",
    "RecognitionOutcome",
    # exceptions
    "HeadingRecognitionError",
    "RecognizerRegistrationError",
    "RecognizerConfigurationError",
    "RecognizerLookupError",
    "RecognizerExecutionError",
    "RecognitionPipelineError",
]
