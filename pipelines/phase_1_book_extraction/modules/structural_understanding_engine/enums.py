"""
modules/structural_understanding_engine/enums.py — M5.2C: closed
vocabularies for the Structural Understanding Engine.

Mirrors this repository's existing convention (see
`modules.educational_object_framework.enums`,
`modules.educational_taxonomy.enums`,
`modules.subject_profile_framework.enums`): str-backed `Enum`s,
JSON-serializable via `.value`, directly comparable against the
equivalent string.
"""
from __future__ import annotations

from enum import Enum


class ProfileLifecycleState(str, Enum):
    """The lifecycle a Subject Profile passes through under M5.2C's
    `ProfileActivationManager`. This lifecycle belongs entirely to
    M5.2C — `modules.subject_profile_framework.models.SubjectProfile`
    and `.registry.SubjectProfileRegistry` carry no lifecycle state of
    their own and are not modified to add one.

    REGISTERED -> VALIDATED -> ACTIVE -> INACTIVE -> UNREGISTERED,
    with INACTIVE able to return to ACTIVE (reactivation, re-checking
    compatibility) and VALIDATED able to fall back to REGISTERED (a
    profile whose contributions changed underneath it and must be
    re-validated). UNREGISTERED is terminal.
    """

    REGISTERED = "registered"
    VALIDATED = "validated"
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNREGISTERED = "unregistered"


class CompatibilityOutcome(str, Enum):
    """The outcome of one taxonomy-compatibility check performed by
    `compatibility.CompatibilityValidator`. Distinct from M5.1's
    `DiagnosticSeverity` (which grades a single diagnostic) — this is
    the coarse pass/fail shape a caller checks before deciding whether
    to proceed with activation at all."""

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNRESOLVABLE = "unresolvable"


class AnalysisOutcome(str, Enum):
    """The outcome of one `StructuralUnderstandingEngine.analyze()`
    call against a `StructuralObject`. Mirrors the
    EXECUTED/NO_RESULT/FAILED shape `educational_object_framework
    .enums.ProcessingOutcome` already establishes, narrowed to what
    structural analysis (never object-specific processing) can
    produce."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNRECOGNIZED_PATTERN = "unrecognized_pattern"


__all__ = [
    "ProfileLifecycleState",
    "CompatibilityOutcome",
    "AnalysisOutcome",
]
