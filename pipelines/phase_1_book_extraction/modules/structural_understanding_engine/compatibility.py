"""
modules/structural_understanding_engine/compatibility.py — M5.2C:
taxonomy compatibility validation.

Wraps `modules.educational_taxonomy.models.EducationalObjectType` and
`.registry.TaxonomyRegistry` (both frozen, M5.2A) — never modifies
either. `TaxonomyCompatibility` and `CompatibilityValidator` are
entirely M5.2C-owned models describing what version RANGE of the
taxonomy this Structural Understanding Engine deployment supports, and
checking a given `EducationalObjectType.version` (or every
contribution's, for a whole `SubjectProfile`) against that range
before activation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)
from modules.educational_taxonomy.exceptions import TaxonomyLookupError
from modules.structural_understanding_engine.enums import CompatibilityOutcome
from modules.structural_understanding_engine.exceptions import TaxonomyCompatibilityError

if TYPE_CHECKING:
    from modules.educational_taxonomy.models import EducationalObjectType
    from modules.educational_taxonomy.registry import TaxonomyRegistry
    from modules.subject_profile_framework.models import SubjectProfile

_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _parse_version(version: str, *, field_name: str) -> Tuple[int, int, int]:
    match = _VERSION_PATTERN.match(version)
    if not match:
        raise TaxonomyCompatibilityError(
            f"{field_name} {version!r} must be a MAJOR.MINOR.PATCH version string."
        )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


@dataclass(frozen=True)
class TaxonomyCompatibility:
    """An M5.2C-owned declaration of which `EducationalObjectType
    .version` (M5.2A) range this Structural Understanding Engine
    deployment supports.

    Attributes:
        supported_taxonomy_version: The taxonomy version this engine
            deployment was built and tested against — purely
            informational (e.g. for diagnostics/README), not itself
            part of the range check.
        minimum_supported_version: Inclusive lower bound an
            `EducationalObjectType.version` must meet.
        maximum_supported_version: Inclusive upper bound an
            `EducationalObjectType.version` must meet.
    """

    supported_taxonomy_version: str
    minimum_supported_version: str
    maximum_supported_version: str

    def __post_init__(self) -> None:
        supported = _parse_version(
            self.supported_taxonomy_version, field_name="TaxonomyCompatibility.supported_taxonomy_version"
        )
        minimum = _parse_version(
            self.minimum_supported_version, field_name="TaxonomyCompatibility.minimum_supported_version"
        )
        maximum = _parse_version(
            self.maximum_supported_version, field_name="TaxonomyCompatibility.maximum_supported_version"
        )
        if minimum > maximum:
            raise TaxonomyCompatibilityError(
                f"TaxonomyCompatibility.minimum_supported_version {self.minimum_supported_version!r} "
                f"must not be greater than maximum_supported_version {self.maximum_supported_version!r}."
            )
        if not (minimum <= supported <= maximum):
            raise TaxonomyCompatibilityError(
                f"TaxonomyCompatibility.supported_taxonomy_version {self.supported_taxonomy_version!r} "
                f"must fall within [{self.minimum_supported_version}, {self.maximum_supported_version}]."
            )

    def accepts(self, object_type_version: str) -> bool:
        """True if `object_type_version` falls within
        `[minimum_supported_version, maximum_supported_version]`
        inclusive."""
        version = _parse_version(object_type_version, field_name="object_type_version")
        minimum = _parse_version(
            self.minimum_supported_version, field_name="TaxonomyCompatibility.minimum_supported_version"
        )
        maximum = _parse_version(
            self.maximum_supported_version, field_name="TaxonomyCompatibility.maximum_supported_version"
        )
        return minimum <= version <= maximum

    def to_dict(self) -> dict:
        return {
            "supported_taxonomy_version": self.supported_taxonomy_version,
            "minimum_supported_version": self.minimum_supported_version,
            "maximum_supported_version": self.maximum_supported_version,
        }


#: A permissive, wide-open default — every "1.x.x" taxonomy version —
#: usable as a caller's starting point without having to hand-author a
#: range before anything works.
DEFAULT_COMPATIBILITY = TaxonomyCompatibility(
    supported_taxonomy_version="1.0.0",
    minimum_supported_version="1.0.0",
    maximum_supported_version="1.999.999",
)


class CompatibilityValidator:
    """Verifies `EducationalObjectType` / `SubjectProfile` compatibility
    against a `TaxonomyCompatibility` declaration and a `TaxonomyRegistry`
    — before `lifecycle.ProfileActivationManager` will allow a profile
    to move to ACTIVE. Wraps `TaxonomyRegistry.get()` for resolution;
    never mutates the registry."""

    def __init__(
        self,
        taxonomy_registry: "TaxonomyRegistry",
        compatibility: TaxonomyCompatibility = DEFAULT_COMPATIBILITY,
    ) -> None:
        self._taxonomy = taxonomy_registry
        self._compatibility = compatibility

    @property
    def compatibility(self) -> TaxonomyCompatibility:
        return self._compatibility

    def outcome_for_object_type(self, object_type: "EducationalObjectType") -> CompatibilityOutcome:
        try:
            resolved = self._taxonomy.get(object_type.key)
        except TaxonomyLookupError:
            return CompatibilityOutcome.UNRESOLVABLE
        if not self._compatibility.accepts(resolved.version):
            return CompatibilityOutcome.INCOMPATIBLE
        return CompatibilityOutcome.COMPATIBLE

    def validate_object_type(self, object_type: "EducationalObjectType") -> ValidationResult:
        """Returns a `ValidationResult` (M5.1, reused as-is) describing
        whether `object_type` both resolves in this validator's
        `TaxonomyRegistry` and falls within this validator's
        `TaxonomyCompatibility` range."""
        outcome = self.outcome_for_object_type(object_type)
        if outcome == CompatibilityOutcome.COMPATIBLE:
            return SUCCESS
        if outcome == CompatibilityOutcome.UNRESOLVABLE:
            return ValidationResult(
                diagnostics=(
                    ValidationDiagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        code="compatibility.unresolvable_object_type",
                        message=f"Object type '{object_type.key}' does not resolve in the taxonomy registry.",
                    ),
                )
            )
        return ValidationResult(
            diagnostics=(
                ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="compatibility.incompatible_object_type_version",
                    message=(
                        f"Object type '{object_type.key}' version '{object_type.version}' falls outside "
                        f"supported range [{self._compatibility.minimum_supported_version}, "
                        f"{self._compatibility.maximum_supported_version}]."
                    ),
                ),
            )
        )

    def validate_profile(self, profile: "SubjectProfile") -> ValidationResult:
        """Aggregates `validate_object_type()` across every
        contribution in `profile` — the check
        `lifecycle.ProfileActivationManager` runs before allowing a
        profile to become ACTIVE."""
        result = SUCCESS
        for contribution in profile.contributions:
            result = result.merged_with(self.validate_object_type(contribution.object_type))
        return result


__all__ = [
    "TaxonomyCompatibility",
    "DEFAULT_COMPATIBILITY",
    "CompatibilityValidator",
]
