"""
modules/structural_understanding_engine/exceptions.py — M5.2C:
exception hierarchy for the Structural Understanding Engine.

Mirrors `modules.subject_profile_framework.exceptions`'s /
`modules.educational_taxonomy.exceptions`'s convention exactly: a
single catch-all base per layer, plus small, specific subclasses so
callers can catch precisely what they care about. This is a
deliberately separate hierarchy from `SubjectProfileFrameworkError` and
`EducationalTaxonomyError` — M5.2C failures (hint resolution, taxonomy
compatibility, lifecycle transitions, structural analysis) are a
different concern from either frozen package, even though this
package wraps both.
"""


class StructuralUnderstandingEngineError(Exception):
    """Base class for every error raised anywhere in the
    structural_understanding_engine package. Catch this to handle any
    M5.2C failure generically."""


class HintResolutionError(StructuralUnderstandingEngineError):
    """Raised by `HintResolver` when a `SubjectContribution`'s raw
    `Mapping[str, Any]` hint field cannot be resolved into its typed
    M5.2C hint model — e.g. a known key holds a value of the wrong
    type."""


class StructuralPatternError(StructuralUnderstandingEngineError):
    """Raised by `patterns.StructuralPatternRegistry` when a
    `StructuralPattern` cannot be registered (duplicate key,
    structurally invalid component list) or a lookup fails."""


class StructuralAnalysisError(StructuralUnderstandingEngineError):
    """Raised by `StructuralObject` / `StructuralUnderstandingEngine`
    when a value is structurally invalid at construction time (e.g. an
    empty `pattern_key`) — distinct from a normal, non-exceptional
    *analysis outcome* (missing components are reported as
    `ValidationDiagnostic`s, not exceptions)."""


class TaxonomyCompatibilityError(StructuralUnderstandingEngineError):
    """Raised by `compatibility.TaxonomyCompatibility` when a
    version-range declaration is malformed (e.g. `minimum_supported_version`
    greater than `maximum_supported_version`), or by
    `CompatibilityValidator` when asked to validate against a taxonomy
    entry that cannot be resolved at all."""


class ProfileLifecycleError(StructuralUnderstandingEngineError):
    """Raised by `lifecycle.ProfileActivationManager` when an illegal
    lifecycle transition is attempted (e.g. activating a profile that
    has not been validated) or when asked about a subject_key it has
    no lifecycle record for."""


__all__ = [
    "StructuralUnderstandingEngineError",
    "HintResolutionError",
    "StructuralPatternError",
    "StructuralAnalysisError",
    "TaxonomyCompatibilityError",
    "ProfileLifecycleError",
]
