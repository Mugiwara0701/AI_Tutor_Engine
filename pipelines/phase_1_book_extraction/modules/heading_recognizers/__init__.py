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
HierarchicalHeadingRecognizer; M4.2C: RomanNumeralHeadingRecognizer,
AlphabeticHeadingRecognizer, ChapterNumberRecognizer,
ChapterTitleRecognizer; and any later additions) belong in new
modules inside this package, each registered with the shared
`factory` via ONE `factory.register_class(name, RecognizerClass)`
call — mirroring modules/recognizers/__init__.py's own
one-`register(...)`-call-per-recognizer convention. Nothing in
base.py, config.py, registry.py, pipeline.py, or utils.py should need
to change to add one.

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
