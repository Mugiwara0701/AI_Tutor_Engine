"""
modules/heading_canonicalization/validation.py — M4.3A: validation
contracts for the heading canonicalization framework.

Defines the *shape* validation results take (success / warnings /
errors / diagnostics), not any validation *rule*. Per the M4.3A spec
("Do not implement structural validation rules yet" /
"Out of Scope: sequence validation, duplicate detection, hierarchy
validation"), no code in this module inspects a `CanonicalHeading`'s
content — a future structural-validator canonicalizer (implementing
`base.HeadingCanonicalizer`) is what will actually populate a
`ValidationResult` and, from it, a heading's
`CanonicalHeading.validation_status`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from modules.heading_canonicalization.enums import ValidationSeverity, ValidationStatus


@dataclass(frozen=True)
class ValidationDiagnostic:
    """One structural-validation finding. Distinct from the free-form
    `CanonicalHeading.diagnostics` strings (which are informal,
    human-readable notes from any canonicalizer) — a
    `ValidationDiagnostic` is a structured record with a machine-
    readable `code` and severity, produced specifically by validation
    logic (a future structural-validator canonicalizer)."""

    severity: ValidationSeverity
    code: str
    message: str
    canonicalizer_name: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.severity, ValidationSeverity):
            raise ValueError(
                f"ValidationDiagnostic.severity must be a ValidationSeverity, got {type(self.severity).__name__}."
            )
        if not self.code:
            raise ValueError("ValidationDiagnostic.code must be non-empty.")
        if not self.message:
            raise ValueError("ValidationDiagnostic.message must be non-empty.")


@dataclass(frozen=True)
class ValidationResult:
    """The full outcome of validating one `CanonicalHeading` — what a
    future structural-validator canonicalizer would attach. Kept as a
    value object distinct from `CanonicalHeading.validation_status`
    (the coarse status a heading itself carries) so a validator can
    reason about *why* a heading has a given status, not just *that*
    it does; a canonicalizer that computes a `ValidationResult` is
    expected to set `CanonicalHeading.validation_status` to this
    result's own `.status` when it applies the result to a heading.

    `status` is derived, not stored redundantly: SUCCESS when there
    are no diagnostics at all, WARNING when the worst diagnostic is a
    warning, ERROR when any diagnostic is an error — so it can never
    disagree with `diagnostics` itself.
    """

    diagnostics: Tuple[ValidationDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def status(self) -> ValidationStatus:
        if any(d.severity == ValidationSeverity.ERROR for d in self.diagnostics):
            return ValidationStatus.ERROR
        if any(d.severity == ValidationSeverity.WARNING for d in self.diagnostics):
            return ValidationStatus.WARNING
        return ValidationStatus.SUCCESS

    @property
    def is_success(self) -> bool:
        return self.status == ValidationStatus.SUCCESS

    @property
    def has_errors(self) -> bool:
        return self.status == ValidationStatus.ERROR

    @property
    def has_warnings(self) -> bool:
        return any(d.severity == ValidationSeverity.WARNING for d in self.diagnostics)

    def errors(self) -> Tuple[ValidationDiagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == ValidationSeverity.ERROR)

    def warnings(self) -> Tuple[ValidationDiagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == ValidationSeverity.WARNING)

    def merged_with(self, other: "ValidationResult") -> "ValidationResult":
        """Combines two validation results (e.g. from two separate
        validator canonicalizers) into one, preserving diagnostic
        order (`self` first, then `other`). Neither input is
        mutated."""
        return ValidationResult(diagnostics=self.diagnostics + other.diagnostics)


#: A reusable, pre-built empty success result — the value a future
#: validator canonicalizer's `canonicalize()` can return unmodified
#: for "nothing to complain about", and the same value M4.3A's own
#: framework code below treats as the neutral/default validation
#: outcome wherever one is needed structurally without running any
#: actual rule.
SUCCESS = ValidationResult()


__all__ = [
    "ValidationDiagnostic",
    "ValidationResult",
    "SUCCESS",
]
