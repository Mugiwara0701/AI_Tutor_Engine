"""
modules/heading_recognizers/exceptions.py — M4.2A: exception hierarchy
for the heading recognition framework.

Mirrors document_structure_tree/exceptions.py's convention in this
project: a single catch-all base per layer, plus small, specific
subclasses so callers can catch precisely what they care about
instead of parsing free-text messages. Only the exceptions the
framework itself needs (registration, configuration, lookup,
pipeline execution) are defined here — exceptions belonging to a
concrete recognizer's own domain logic (M4.2B/C and later) are that
milestone's concern, not this one's; they should subclass
HeadingRecognitionError rather than invent an unrelated hierarchy.
"""


class HeadingRecognitionError(Exception):
    """Base class for every error raised anywhere in the
    heading_recognizers package. Catch this to handle any framework
    failure generically."""


class RecognizerRegistrationError(HeadingRecognitionError):
    """Raised by RecognizerRegistry.register() when a recognizer
    cannot be registered as given — e.g. a duplicate name, a
    recognizer missing a required `name`/`classification`, or a
    recognizer that fails the registry's structural validation
    (see registry.py's `_validate`)."""


class RecognizerConfigurationError(HeadingRecognitionError):
    """Raised by HeadingRecognitionConfig / RecognizerFactory when a
    recognizer's configuration is missing, malformed, or internally
    inconsistent — e.g. a confidence_threshold outside [0.0, 1.0], a
    negative priority, or a factory request for a recognizer class
    that was never registered with the factory."""


class RecognizerLookupError(HeadingRecognitionError, LookupError):
    """Raised by RecognizerRegistry lookup methods when asked for a
    recognizer name/classification that is not registered. Subclasses
    LookupError as well, so existing generic `except LookupError`
    handling elsewhere still catches it without modification."""


class RecognizerExecutionError(HeadingRecognitionError):
    """Wraps an exception raised by a recognizer's own `recognize()`
    implementation. RecognitionPipeline never lets a single
    misbehaving recognizer abort a whole run — see
    HeadingRecognizer.safe_recognize() — but callers that opt out of
    that safety net (e.g. by calling `recognize()` directly during
    recognizer development) will see this instead of a raw, opaque
    exception from inside the pipeline."""

    def __init__(self, recognizer_name: str, message: str) -> None:
        self.recognizer_name = recognizer_name
        super().__init__(f"Recognizer '{recognizer_name}' failed: {message}")


class RecognitionPipelineError(HeadingRecognitionError):
    """Raised by RecognitionPipeline itself (not by an individual
    recognizer) when the pipeline cannot produce a deterministic
    result at all — e.g. an unresolvable conflict-resolution
    configuration, or an empty registry when the pipeline is
    configured to require at least one enabled recognizer."""


__all__ = [
    "HeadingRecognitionError",
    "RecognizerRegistrationError",
    "RecognizerConfigurationError",
    "RecognizerLookupError",
    "RecognizerExecutionError",
    "RecognitionPipelineError",
]
