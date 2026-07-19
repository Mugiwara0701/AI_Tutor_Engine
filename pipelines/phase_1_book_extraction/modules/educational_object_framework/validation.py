"""
modules/educational_object_framework/validation.py — M5.1: validation
helper contracts for the educational object processing framework.

Defines the *shape* validation results take (success / warnings /
errors / diagnostics), not any validation *rule* — mirrors
`heading_canonicalization.validation`'s own "contracts, not rules"
scope exactly. Per the M5.1 spec ("validation helpers", not
object-specific validation logic — cross-object validation is
explicitly out of scope, belonging to a later milestone), no code in
this module inspects `ProcessingContext.current_object` or a
`ProcessingResult`'s content — a concrete processor (M5.2) is what
will actually populate a `ValidationResult` from whatever validation
it performs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from modules.educational_object_framework.enums import DiagnosticSeverity


@dataclass(frozen=True)
class ValidationDiagnostic:
    """One validation finding. Distinct from the free-form
    `ProcessingResult.diagnostics` strings (which are informal,
    human-readable notes from any processor) — a
    `ValidationDiagnostic` is a structured record with a machine-
    readable `code` and severity, produced specifically by validation
    logic (a concrete processor, or a future cross-object validator,
    both out of M5.1's scope)."""

    severity: DiagnosticSeverity
    code: str
    message: str
    processor_name: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.severity, DiagnosticSeverity):
            raise ValueError(
                f"ValidationDiagnostic.severity must be a DiagnosticSeverity, got {type(self.severity).__name__}."
            )
        if not self.code:
            raise ValueError("ValidationDiagnostic.code must be non-empty.")
        if not self.message:
            raise ValueError("ValidationDiagnostic.message must be non-empty.")


@dataclass(frozen=True)
class ValidationResult:
    """The full outcome of validating something — what a concrete
    processor's own validation step would attach to a
    `ProcessingResult` (e.g. via `metadata` or `execution_metadata`;
    this framework does not prescribe where). Kept as a value object
    distinct from any coarse status field so a caller can reason about
    *why* something is or isn't valid, not just *that* it is.

    `status`-equivalent information is derived via the properties
    below rather than stored redundantly, so it can never disagree
    with `diagnostics` itself — mirrors
    `heading_canonicalization.validation.ValidationResult` exactly.
    """

    diagnostics: Tuple[ValidationDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def is_success(self) -> bool:
        return not any(d.severity == DiagnosticSeverity.ERROR for d in self.diagnostics)

    @property
    def has_errors(self) -> bool:
        return any(d.severity == DiagnosticSeverity.ERROR for d in self.diagnostics)

    @property
    def has_warnings(self) -> bool:
        return any(d.severity == DiagnosticSeverity.WARNING for d in self.diagnostics)

    def errors(self) -> Tuple[ValidationDiagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == DiagnosticSeverity.ERROR)

    def warnings(self) -> Tuple[ValidationDiagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == DiagnosticSeverity.WARNING)

    def merged_with(self, other: "ValidationResult") -> "ValidationResult":
        """Combines two validation results into one, preserving
        diagnostic order (`self` first, then `other`). Neither input
        is mutated."""
        return ValidationResult(diagnostics=self.diagnostics + other.diagnostics)


#: A reusable, pre-built empty success result — the value a concrete
#: processor's own validation step can return unmodified for "nothing
#: to complain about".
SUCCESS = ValidationResult()


__all__ = [
    "ValidationDiagnostic",
    "ValidationResult",
    "SUCCESS",
]
