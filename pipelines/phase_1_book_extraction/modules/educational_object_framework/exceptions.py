"""
modules/educational_object_framework/exceptions.py — M5.1: exception
hierarchy for the educational object processing framework.

Mirrors modules/heading_canonicalization/exceptions.py's convention
exactly (itself modeled on modules/heading_recognizers/exceptions.py):
a single catch-all base per layer, plus small, specific subclasses so
callers can catch precisely what they care about. Only the exceptions
the framework itself needs (registration, configuration, lookup,
pipeline execution) are defined here — exceptions belonging to a
concrete processor's own domain logic (M5.2 and later — equation,
figure, table, diagram, example, activity, definition, glossary
processors) should subclass EducationalObjectFrameworkError rather
than invent an unrelated hierarchy.
"""


class EducationalObjectFrameworkError(Exception):
    """Base class for every error raised anywhere in the
    educational_object_framework package. Catch this to handle any
    framework failure generically."""


class ProcessorRegistrationError(EducationalObjectFrameworkError):
    """Raised by ProcessorRegistry.register() when a processor cannot
    be registered as given — e.g. a duplicate name, a processor
    missing a required `name`, or one that fails the registry's
    structural validation."""


class ProcessorConfigurationError(EducationalObjectFrameworkError):
    """Raised by EducationalObjectFrameworkConfig when a processor's
    configuration is missing, malformed, or internally inconsistent —
    e.g. a negative priority."""


class ProcessorLookupError(EducationalObjectFrameworkError, LookupError):
    """Raised by ProcessorRegistry lookup methods when asked for a
    processor name that is not registered. Subclasses LookupError as
    well, so existing generic `except LookupError` handling elsewhere
    still catches it without modification."""


class ProcessorExecutionError(EducationalObjectFrameworkError):
    """Wraps an exception raised by a processor's own `process()`
    implementation. ProcessingPipeline never lets a single
    misbehaving processor abort a whole run — see
    EducationalObjectProcessor.safe_process() — but callers that opt
    out of that safety net (e.g. by calling `process()` directly
    during processor development) will see this instead of a raw,
    opaque exception from inside the pipeline."""

    def __init__(self, processor_name: str, message: str) -> None:
        self.processor_name = processor_name
        super().__init__(f"Processor '{processor_name}' failed: {message}")


class ProcessingPipelineError(EducationalObjectFrameworkError):
    """Raised by ProcessingPipeline itself (not by an individual
    processor) when the pipeline cannot produce a deterministic
    result at all — e.g. an empty registry when the pipeline is
    configured to require at least one enabled processor."""


class ProcessingResultValidationError(EducationalObjectFrameworkError):
    """Raised by `models.ProcessingResult` / `context.ProcessingContext`
    constructors when a value is structurally invalid (e.g. an empty
    processor name, a negative level). Distinct from a *processing
    failure recorded for a processor* (a normal, non-exceptional
    outcome represented by a FAILED `AttemptRecord`) — this exception
    means the model or context object itself could not be constructed
    at all."""


__all__ = [
    "EducationalObjectFrameworkError",
    "ProcessorRegistrationError",
    "ProcessorConfigurationError",
    "ProcessorLookupError",
    "ProcessorExecutionError",
    "ProcessingPipelineError",
    "ProcessingResultValidationError",
]
