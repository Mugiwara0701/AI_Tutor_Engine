"""
modules/semantic_interpretation_engine/compatibility_interpreter.py —
M5.2D Deliverable #2: Rich Compatibility Reporting.

Wraps M5.2C's CompatibilityValidator without modifying it.  The
CompatibilityInterpreter calls the existing validator and translates
its boolean outcome + ValidationResult into a richer CompatibilityResult
that includes severity, reason, affected components, and a suggested
resolution.
"""
from __future__ import annotations

from typing import Optional, Tuple

from modules.structural_understanding_engine.compatibility import (
    DEFAULT_COMPATIBILITY,
    CompatibilityValidator,
)
from modules.structural_understanding_engine.enums import CompatibilityOutcome

from modules.semantic_interpretation_engine.enums import CompatibilitySeverity
from modules.semantic_interpretation_engine.exceptions import CompatibilityInterpretationError
from modules.semantic_interpretation_engine.models import CompatibilityResult

__all__ = [
    "CompatibilityInterpreter",
    "default_compatibility_interpreter",
]


def _default_validator() -> CompatibilityValidator:
    """Build a CompatibilityValidator backed by M5.2A's default_taxonomy."""
    from modules.educational_taxonomy.registry import default_taxonomy
    return CompatibilityValidator(
        taxonomy_registry=default_taxonomy,
        compatibility=DEFAULT_COMPATIBILITY,
    )


class CompatibilityInterpreter:
    """
    Wraps M5.2C's CompatibilityValidator to produce CompatibilityResult.

    Does NOT subclass CompatibilityValidator.
    """

    def __init__(self, validator: Optional[CompatibilityValidator] = None) -> None:
        self._validator = validator if validator is not None else _default_validator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def interpret_object_type(self, object_type: object) -> CompatibilityResult:
        """
        Produce a CompatibilityResult for *object_type*
        (an ``EducationalObjectType`` from M5.2A).

        Parameters
        ----------
        object_type:
            ``modules.educational_taxonomy.models.EducationalObjectType``.
            Typed as ``object`` to avoid importing M5.2A here directly;
            the underlying validator handles type enforcement.
        """
        try:
            outcome = self._validator.outcome_for_object_type(object_type)  # type: ignore[arg-type]
            validation = self._validator.validate_object_type(object_type)  # type: ignore[arg-type]
        except Exception as exc:
            raise CompatibilityInterpretationError(
                f"CompatibilityValidator raised an unexpected error: {exc}"
            ) from exc

        type_key = getattr(object_type, "key", "")
        type_version = getattr(object_type, "version", "")

        compatible = outcome == CompatibilityOutcome.COMPATIBLE
        severity, reason, suggestion = self._explain(
            outcome=outcome,
            type_key=type_key,
            type_version=type_version,
            compatibility=self._validator.compatibility,
        )

        error_messages = tuple(
            d.message for d in validation.diagnostics
            if hasattr(d, "message")
        )

        return CompatibilityResult(
            compatible=compatible,
            severity=severity,
            reason=reason,
            affected_components=error_messages if not compatible else (),
            suggested_resolution=suggestion,
            object_type_key=type_key,
            object_type_version=type_version,
        )

    def interpret_profile(self, profile: object) -> CompatibilityResult:
        """
        Produce a CompatibilityResult for an entire SubjectProfile.

        Parameters
        ----------
        profile:
            ``modules.subject_profile_framework.models.SubjectProfile``.
        """
        try:
            validation = self._validator.validate_profile(profile)  # type: ignore[arg-type]
        except Exception as exc:
            raise CompatibilityInterpretationError(
                f"CompatibilityValidator.validate_profile raised an unexpected error: {exc}"
            ) from exc

        compatible = not validation.has_errors()
        severity = CompatibilitySeverity.OK if compatible else CompatibilitySeverity.ERROR
        if compatible and validation.has_warnings():
            severity = CompatibilitySeverity.WARNING

        error_messages = tuple(
            d.message for d in validation.diagnostics
            if hasattr(d, "message")
        )

        reason = (
            "All contributions are compatible."
            if compatible and not validation.has_warnings()
            else (
                "Some contributions have warnings."
                if compatible
                else "One or more contributions are incompatible."
            )
        )

        suggestion = (
            ""
            if compatible and not validation.has_warnings()
            else (
                "Review warnings and consider updating affected object type versions."
                if compatible
                else (
                    "Update the affected SubjectContribution object types to versions "
                    f"within the supported range "
                    f"[{self._validator.compatibility.minimum_supported_version}, "
                    f"{self._validator.compatibility.maximum_supported_version}]."
                )
            )
        )

        return CompatibilityResult(
            compatible=compatible,
            severity=severity,
            reason=reason,
            affected_components=error_messages,
            suggested_resolution=suggestion,
            object_type_key="",
            object_type_version="",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _explain(
        *,
        outcome: CompatibilityOutcome,
        type_key: str,
        type_version: str,
        compatibility: object,
    ) -> Tuple[CompatibilitySeverity, str, str]:
        min_v = getattr(compatibility, "minimum_supported_version", "?")
        max_v = getattr(compatibility, "maximum_supported_version", "?")

        if outcome == CompatibilityOutcome.COMPATIBLE:
            return (
                CompatibilitySeverity.OK,
                f"Object type {type_key!r} (v{type_version}) is compatible.",
                "",
            )
        if outcome == CompatibilityOutcome.TOO_OLD:
            return (
                CompatibilitySeverity.ERROR,
                (
                    f"Object type {type_key!r} version {type_version!r} is below the "
                    f"minimum supported version {min_v!r}."
                ),
                (
                    f"Upgrade the EducationalObjectType {type_key!r} to at least "
                    f"version {min_v}."
                ),
            )
        if outcome == CompatibilityOutcome.TOO_NEW:
            return (
                CompatibilitySeverity.ERROR,
                (
                    f"Object type {type_key!r} version {type_version!r} exceeds the "
                    f"maximum supported version {max_v!r}."
                ),
                (
                    f"Downgrade the EducationalObjectType {type_key!r} to at most "
                    f"version {max_v}, or update the engine compatibility settings."
                ),
            )
        # UNKNOWN or unexpected
        return (
            CompatibilitySeverity.WARNING,
            f"Compatibility outcome for {type_key!r} is {outcome.value!r}.",
            "Inspect the CompatibilityValidator configuration.",
        )


#: Module-level singleton.
default_compatibility_interpreter = CompatibilityInterpreter()
