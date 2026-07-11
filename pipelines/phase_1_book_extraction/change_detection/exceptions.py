"""
change_detection/exceptions.py — Phase E3: exception hierarchy for the
Change Detection layer.

Mirrors dependency_graph/exceptions.py's own convention exactly, one
package over: small, specific exception classes so a caller can catch
precisely what it cares about instead of parsing free-text messages.
"""


class ChangeDetectionError(Exception):
    """Base class for every error raised anywhere in the
    change_detection package. Mirrors
    dependency_graph.exceptions.DependencyGraphError's role as the one
    catch-all ancestor for its own layer."""


class InvalidPreviousBuildError(ChangeDetectionError):
    """Describes a `previous_build` argument that is neither `None` nor
    a dict shaped like `snapshot.build_snapshot()`'s own output (i.e.
    missing or malformed `artifact_fingerprints`).

    NOTE ON ACTUAL RUNTIME BEHAVIOUR: this class is instantiated (for
    its message) inside change_detection.engine._extract_previous_
    fingerprints(), but that helper always catches it itself and never
    lets it propagate -- Phase E3 is a read-only reporting pass, and a
    malformed previous snapshot must degrade to "treat as no previous
    build" (str(exc) is appended to the returned report's own
    `warnings` list) rather than abort the whole chapter's build. So in
    the current implementation this exception is never raised to, or
    visible to, any caller of change_detection.engine.detect_changes()
    -- it exists as a distinct, catchable type (mirroring dependency_
    graph/exceptions.py's own per-error-class convention) and to give
    the internal warning message a single, well-defined wording, not as
    something a caller is expected to catch."""

    def __init__(self, reason: str):
        super().__init__(
            f"change_detection: invalid `previous_build` argument -- {reason}"
        )
        self.reason = reason