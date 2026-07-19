"""
modules/subject_profile_framework/validation.py — M5.2B: Subject
Profile Registry-wide integrity validation.

Reuses `modules.educational_object_framework.validation`'s
`ValidationResult` / `ValidationDiagnostic` / `DiagnosticSeverity`
contracts directly — same integration point M5.2A's own
`validation.py` already establishes — rather than defining a third,
parallel validation shape. No new validation *shape* is introduced
here, only the Subject Profile Framework-specific *checks* that
produce M5.1's existing shape.

Scope: validates a `SubjectProfileRegistry`'s own internal integrity
(subject_key / object-identifier uniqueness, version format,
deterministic serialization, and that every registered contribution's
`EducationalObjectType` still resolves in the taxonomy it was
registered into) — it does NOT validate any concrete extracted
educational object instance against a subject profile; that is
processor-level validation, out of scope for this milestone.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import TYPE_CHECKING, List

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)
from modules.educational_taxonomy.exceptions import TaxonomyLookupError

if TYPE_CHECKING:
    from modules.subject_profile_framework.registry import SubjectProfileRegistry

#: Same "MAJOR.MINOR.PATCH" shape `EducationalObjectType.version` /
#: `SubjectContribution.version` / `SubjectProfile.version` are all
#: documented (but not constructor-enforced) to follow — checked here,
#: not at construction time, mirroring M5.2A's own choice to keep this
#: an integrity *check* rather than a hard constructor requirement.
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def validate_subject_profile_registry(registry: "SubjectProfileRegistry") -> ValidationResult:
    """Runs every Subject Profile Registry integrity check against
    `registry` and returns one aggregate `ValidationResult`. Never
    raises for an ordinary integrity problem — that is what the
    returned diagnostics are for."""
    diagnostics: List[ValidationDiagnostic] = []
    diagnostics.extend(_check_subject_key_uniqueness(registry))
    diagnostics.extend(_check_object_identifier_uniqueness(registry))
    diagnostics.extend(_check_version_format(registry))
    diagnostics.extend(_check_taxonomy_consistency(registry))
    diagnostics.extend(_check_deterministic_serialization(registry))
    if not diagnostics:
        return SUCCESS
    return ValidationResult(diagnostics=tuple(diagnostics))


def _check_subject_key_uniqueness(registry: "SubjectProfileRegistry") -> List[ValidationDiagnostic]:
    """Belt-and-suspenders re-check of what
    `SubjectProfileRegistry.register()` already enforces at
    registration time."""
    counts = Counter(p.subject_key for p in registry.all_profiles())
    duplicates = [key for key, count in counts.items() if count > 1]
    if not duplicates:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="subject_profile.duplicate_subject_key",
            message=f"Subject key '{key}' is registered more than once.",
        )
        for key in sorted(duplicates)
    ]


def _check_object_identifier_uniqueness(registry: "SubjectProfileRegistry") -> List[ValidationDiagnostic]:
    """Belt-and-suspenders re-check of the cross-profile object
    identifier (key or alias) uniqueness `register()` already
    enforces."""
    counts: Counter = Counter()
    for contribution in registry.all_contributions():
        counts[contribution.object_type.key] += 1
        for alias in contribution.object_type.aliases:
            counts[alias] += 1
    duplicates = [identifier for identifier, count in counts.items() if count > 1]
    if not duplicates:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="subject_profile.duplicate_object_identifier",
            message=f"Object identifier '{identifier}' is registered more than once across profiles.",
        )
        for identifier in sorted(duplicates)
    ]


def _check_version_format(registry: "SubjectProfileRegistry") -> List[ValidationDiagnostic]:
    """Warns (does not error) on a profile or contribution version
    that does not follow the repository's own "MAJOR.MINOR.PATCH"
    convention — a non-conforming version is not structurally invalid
    (nothing rejects it at construction time), but is worth surfacing
    for version-compatibility purposes."""
    diagnostics: List[ValidationDiagnostic] = []
    for profile in registry.all_profiles():
        if not _VERSION_PATTERN.match(profile.version):
            diagnostics.append(
                ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="subject_profile.non_semver_profile_version",
                    message=(
                        f"Subject profile '{profile.subject_key}' version "
                        f"'{profile.version}' does not follow MAJOR.MINOR.PATCH."
                    ),
                )
            )
    for contribution in registry.all_contributions():
        if not _VERSION_PATTERN.match(contribution.version):
            diagnostics.append(
                ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="subject_profile.non_semver_contribution_version",
                    message=(
                        f"Contribution '{contribution.object_type.key}' (subject "
                        f"'{contribution.subject_key}') version '{contribution.version}' "
                        "does not follow MAJOR.MINOR.PATCH."
                    ),
                )
            )
    return diagnostics


def _check_taxonomy_consistency(registry: "SubjectProfileRegistry") -> List[ValidationDiagnostic]:
    """Confirms every registered contribution's `EducationalObjectType`
    still resolves in the taxonomy registry it was registered into —
    guards against the taxonomy having been mutated directly (e.g. an
    external `unregister()` call against the same `TaxonomyRegistry`
    instance) since this `SubjectProfileRegistry` registered it."""
    diagnostics: List[ValidationDiagnostic] = []
    for contribution in registry.all_contributions():
        try:
            registry.taxonomy.get(contribution.object_type.key)
        except TaxonomyLookupError:
            diagnostics.append(
                ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="subject_profile.taxonomy_drift",
                    message=(
                        f"Contribution '{contribution.object_type.key}' (subject "
                        f"'{contribution.subject_key}') is no longer resolvable in its "
                        "taxonomy registry."
                    ),
                )
            )
    return diagnostics


def _check_deterministic_serialization(registry: "SubjectProfileRegistry") -> List[ValidationDiagnostic]:
    """Confirms that serializing `registry` twice in a row produces
    byte-identical JSON — the Subject Profile Framework's
    serialization contract (see `models.SubjectProfile.to_dict()` /
    `models.SubjectContribution.to_dict()`)."""
    first = json.dumps([p.to_dict() for p in registry.all_profiles()], sort_keys=True)
    second = json.dumps([p.to_dict() for p in registry.all_profiles()], sort_keys=True)
    if first == second:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="subject_profile.nondeterministic_serialization",
            message="Serializing the Subject Profile Registry twice in a row produced different output.",
        )
    ]


__all__ = [
    "validate_subject_profile_registry",
]
