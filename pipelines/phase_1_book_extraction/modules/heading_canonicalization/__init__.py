"""
modules/heading_canonicalization — M4.3A: foundation framework for
deterministic heading canonicalization.

This package is FRAMEWORK ONLY (M4.3A's scope), exactly as
`modules.heading_recognizers` was framework-only for M4.2A. It defines
the canonical heading model, execution context, pipeline, extension
interface, configuration, registry, and validation contracts every
concrete canonicalizer will use — but implements no concrete
canonicalization logic itself (no Roman/Arabic/Devanagari numeral
conversion, no title normalization, no structural validation rules;
see each module's own docstring and this package's `README.md` for
the full "Out of Scope" list).

Sibling relationship to `modules.heading_recognizers`: that package
answers "is this line of source text a heading, and if so what kind
and what level" (M4.2); this package answers the next question —
"given a recognized heading, what is its stable canonical
representation, ready for deterministic normalization" (M4.3).
`models.CanonicalHeading.from_recognition()` is the one bridge between
the two: it adapts a `heading_recognizers.base.RecognitionResult`
(plus the `RecognitionContext` that produced it) into a
`CanonicalHeading` with every canonicalization placeholder left at its
default. Nothing in `heading_recognizers` was read for anything beyond
that adapter's type hints, and nothing there was modified.

Concrete canonicalizers (M4.3B and later — RomanNumeralCanonicalizer,
ArabicNumeralCanonicalizer, DevanagariNumeralCanonicalizer, a title
normalizer, a structural validator) belong in new modules inside this
package, each implementing `base.HeadingCanonicalizer` and registered
into `default_registry` via one `register(...)` call — mirroring
`modules.heading_recognizers`'s own registration convention. Nothing
in `base.py`, `config.py`, `registry.py`, or `pipeline.py` should need
to change to add these.

Public API:
    CanonicalHeading                      — models.py
    ValidationDiagnostic, ValidationResult, SUCCESS
                                           — validation.py
    CanonicalizationContext,
    CanonicalizationFailure,
    HeadingCanonicalizer                  — base.py
    HeadingCanonicalizationConfig,
    CanonicalizerSettings, default_config — config.py
    CanonicalizerRegistry, default_registry,
    register, unregister, get,
    enabled_canonicalizers, all_canonicalizers
                                           — registry.py
    CanonicalizationPipeline,
    CanonicalizationPipelineResult,
    AttemptRecord                         — pipeline.py
    CanonicalHeadingType, NumberingSystem,
    ValidationStatus, ValidationSeverity,
    CanonicalizerState,
    CanonicalizationOutcome               — enums.py
    HeadingCanonicalizationError and subclasses
                                           — exceptions.py
"""
from modules.heading_canonicalization.base import (
    CanonicalizationContext,
    CanonicalizationFailure,
    HeadingCanonicalizer,
)
from modules.heading_canonicalization.config import (
    CanonicalizerSettings,
    HeadingCanonicalizationConfig,
    default_config,
)
from modules.heading_canonicalization.enums import (
    CanonicalHeadingType,
    CanonicalizationOutcome,
    CanonicalizerState,
    NumberingSystem,
    ValidationSeverity,
    ValidationStatus,
)
from modules.heading_canonicalization.exceptions import (
    CanonicalHeadingValidationError,
    CanonicalizationPipelineError,
    CanonicalizerConfigurationError,
    CanonicalizerExecutionError,
    CanonicalizerLookupError,
    CanonicalizerRegistrationError,
    HeadingCanonicalizationError,
)
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.pipeline import (
    AttemptRecord,
    CanonicalizationPipeline,
    CanonicalizationPipelineResult,
)
from modules.heading_canonicalization.registry import (
    CanonicalizerRegistry,
    all_canonicalizers,
    default_registry,
    enabled_canonicalizers,
    get,
    register,
    unregister,
)
from modules.heading_canonicalization.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

__all__ = [
    # models
    "CanonicalHeading",
    # validation
    "ValidationDiagnostic",
    "ValidationResult",
    "SUCCESS",
    # base
    "CanonicalizationContext",
    "CanonicalizationFailure",
    "HeadingCanonicalizer",
    # config
    "HeadingCanonicalizationConfig",
    "CanonicalizerSettings",
    "default_config",
    # registry
    "CanonicalizerRegistry",
    "default_registry",
    "register",
    "unregister",
    "get",
    "enabled_canonicalizers",
    "all_canonicalizers",
    # pipeline
    "CanonicalizationPipeline",
    "CanonicalizationPipelineResult",
    "AttemptRecord",
    # enums
    "CanonicalHeadingType",
    "NumberingSystem",
    "ValidationStatus",
    "ValidationSeverity",
    "CanonicalizerState",
    "CanonicalizationOutcome",
    # exceptions
    "HeadingCanonicalizationError",
    "CanonicalizerRegistrationError",
    "CanonicalizerConfigurationError",
    "CanonicalizerLookupError",
    "CanonicalizerExecutionError",
    "CanonicalizationPipelineError",
    "CanonicalHeadingValidationError",
]
