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

M4.3B adds the first concrete canonicalizers — `NumberingSystemDetector`,
`RomanNumeralCanonicalizer`, `ArabicNumeralCanonicalizer`, and
`DevanagariNumeralCanonicalizer` (see `numeral_canonicalizers.py`) —
each implementing `base.HeadingCanonicalizer` and registered into
`default_registry` via one `register(...)` call below, mirroring
`modules.heading_recognizers`'s own registration convention. Later
milestones (a title normalizer, a structural validator) follow the
same pattern. Nothing in `base.py`, `config.py`, `registry.py`, or
`pipeline.py` needed to change to add these.

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
    StructuralValidator,
    PRECEDING_LEVEL_METADATA_KEY           — structural_validation.py

M4.3D adds `StructuralValidator` (see `structural_validation.py`) —
validates the *relationships between* already-canonicalized headings
(number sequence, hierarchy, canonical consistency) and records the
outcome via `CanonicalHeading.validation_status`/`diagnostics` plus a
structured `ValidationResult` under
`metadata["structural_validation"]`. It never rewrites recognition or
canonicalization output, only the validation placeholders M4.3A
already defined for exactly this purpose. Registered into
`default_registry` below, one more `register(...)` call, same
convention as M4.3B.
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
from modules.heading_canonicalization.numeral_canonicalizers import (
    ArabicNumeralCanonicalizer,
    DevanagariNumeralCanonicalizer,
    NumberingSystemDetector,
    RomanNumeralCanonicalizer,
)
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
from modules.heading_canonicalization.structural_validation import (
    PRECEDING_LEVEL_METADATA_KEY,
    StructuralValidator,
)
from modules.heading_canonicalization.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

# -- M4.3B: register the number-system canonicalizer family ---------------------
#
# One `register(...)` call per canonicalizer, same convention
# `heading_recognizers/__init__.py` uses for its own recognizer
# family. `NumberingSystemDetector` must run before the three
# numeral-specific canonicalizers so `heading.numbering_system` is
# already populated when they check it — its lower `default_priority`
# (10 vs. 20) guarantees that ordering via
# `CanonicalizerRegistry.all_canonicalizers()`'s own
# (priority, registration-order) sort, regardless of the order
# `register()` is called in below.
register(NumberingSystemDetector())
register(RomanNumeralCanonicalizer())
register(ArabicNumeralCanonicalizer())
register(DevanagariNumeralCanonicalizer())

# -- M4.3D: register the structural validator ---------------------
#
# Same one-line registration convention as M4.3B above. `default_priority`
# (200) already guarantees `StructuralValidator` runs after every M4.3B
# canonicalizer regardless of registration order, so it always sees each
# heading's final canonical_number/numbering_system/canonical_type.
register(StructuralValidator())

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
    # M4.3B numeral canonicalizers
    "NumberingSystemDetector",
    "RomanNumeralCanonicalizer",
    "ArabicNumeralCanonicalizer",
    "DevanagariNumeralCanonicalizer",
    # M4.3D structural validation
    "StructuralValidator",
    "PRECEDING_LEVEL_METADATA_KEY",
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
