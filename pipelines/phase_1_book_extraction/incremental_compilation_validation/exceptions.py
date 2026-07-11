"""
incremental_compilation_validation/exceptions.py — Phase E5.1:
exception hierarchy for the Incremental Compilation Validation layer.

Mirrors incremental_compilation/exceptions.py's own convention exactly,
one package over: small, specific exception classes so a caller can
catch precisely what it cares about instead of parsing free-text
messages.
"""


class IncrementalCompilationValidationError(Exception):
    """Base class for every error raised anywhere in the
    incremental_compilation_validation package. Mirrors
    incremental_compilation.exceptions.IncrementalCompilationError's
    role as the one catch-all ancestor for its own layer."""


class InvalidIncrementalCompilationPlanError(IncrementalCompilationValidationError):
    """Describes an `incremental_compilation_plan` argument that is
    neither `None` nor a dict shaped like
    incremental_compilation.plan.IncrementalCompilationPlan's own
    output (i.e. missing one of its own fields this package reads).

    NOTE ON ACTUAL RUNTIME BEHAVIOUR: mirrors
    incremental_compilation.exceptions.InvalidChangeDetectionReportError's
    own precedent exactly -- this class is instantiated (for its
    message) inside validator.py's own input-validation helper, but
    that helper always catches it itself and never lets it propagate --
    like Phase E4, Phase E5.1 is a read-only reporting pass, and a
    malformed IncrementalCompilationPlan must degrade to a `missing_plan`
    / `malformed_plan` finding (surfaced via the returned report's own
    `errors` list) rather than abort the whole chapter's build."""

    def __init__(self, reason: str):
        super().__init__(
            f"incremental_compilation_validation: invalid "
            f"`incremental_compilation_plan` argument -- {reason}"
        )
        self.reason = reason