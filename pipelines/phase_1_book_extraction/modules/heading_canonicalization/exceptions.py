"""
modules/heading_canonicalization/exceptions.py — M4.3A: exception
hierarchy for the heading canonicalization framework.

Mirrors modules/heading_recognizers/exceptions.py's convention
exactly (itself modeled on document_structure_tree/exceptions.py): a
single catch-all base per layer, plus small, specific subclasses so
callers can catch precisely what they care about. Only the exceptions
the framework itself needs (registration, configuration, lookup,
pipeline execution) are defined here — exceptions belonging to a
concrete canonicalizer's own domain logic (M4.3B and later) should
subclass HeadingCanonicalizationError rather than invent an unrelated
hierarchy.
"""


class HeadingCanonicalizationError(Exception):
    """Base class for every error raised anywhere in the
    heading_canonicalization package. Catch this to handle any
    framework failure generically."""


class CanonicalizerRegistrationError(HeadingCanonicalizationError):
    """Raised by CanonicalizerRegistry.register() when a canonicalizer
    cannot be registered as given — e.g. a duplicate name, a
    canonicalizer missing a required `name`, or one that fails the
    registry's structural validation."""


class CanonicalizerConfigurationError(HeadingCanonicalizationError):
    """Raised by HeadingCanonicalizationConfig / CanonicalizerFactory
    when a canonicalizer's configuration is missing, malformed, or
    internally inconsistent — e.g. a negative priority, or a factory
    request for a canonicalizer class that was never registered with
    the factory."""


class CanonicalizerLookupError(HeadingCanonicalizationError, LookupError):
    """Raised by CanonicalizerRegistry lookup methods when asked for a
    canonicalizer name that is not registered. Subclasses LookupError
    as well, so existing generic `except LookupError` handling
    elsewhere still catches it without modification."""


class CanonicalizerExecutionError(HeadingCanonicalizationError):
    """Wraps an exception raised by a canonicalizer's own
    `canonicalize()` implementation. CanonicalizationPipeline never
    lets a single misbehaving canonicalizer abort a whole run — see
    HeadingCanonicalizer.safe_canonicalize() — but callers that opt
    out of that safety net (e.g. by calling `canonicalize()` directly
    during canonicalizer development) will see this instead of a raw,
    opaque exception from inside the pipeline."""

    def __init__(self, canonicalizer_name: str, message: str) -> None:
        self.canonicalizer_name = canonicalizer_name
        super().__init__(f"Canonicalizer '{canonicalizer_name}' failed: {message}")


class CanonicalizationPipelineError(HeadingCanonicalizationError):
    """Raised by CanonicalizationPipeline itself (not by an individual
    canonicalizer) when the pipeline cannot produce a deterministic
    result at all — e.g. an empty registry when the pipeline is
    configured to require at least one enabled canonicalizer."""


class CanonicalHeadingValidationError(HeadingCanonicalizationError):
    """Raised by `models.CanonicalHeading` / `validation` constructors
    when a value is structurally invalid (e.g. a validation status
    that isn't a `ValidationStatus`, a negative level). Distinct from
    a *validation failure recorded on a heading* (a normal,
    non-exceptional outcome represented by `ValidationResult` /
    `ValidationStatus.ERROR`) — this exception means the model or
    validation object itself could not be constructed at all."""


__all__ = [
    "HeadingCanonicalizationError",
    "CanonicalizerRegistrationError",
    "CanonicalizerConfigurationError",
    "CanonicalizerLookupError",
    "CanonicalizerExecutionError",
    "CanonicalizationPipelineError",
    "CanonicalHeadingValidationError",
]
