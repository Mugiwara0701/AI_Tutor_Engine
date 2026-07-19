"""
modules/structural_understanding_engine/validation.py — M5.2C:
structural-pattern-registry-wide integrity validation.

Reuses `modules.educational_object_framework.validation`'s
`ValidationResult` / `ValidationDiagnostic` / `DiagnosticSeverity`
contracts directly — same integration point M5.2A's and M5.2B's own
`validation.py` modules already establish — rather than defining a
fourth, parallel validation shape. No new validation *shape* is
introduced here, only the M5.2C-specific *checks* that produce M5.1's
existing shape.

Scope: validates a `StructuralPatternRegistry`'s own internal
integrity (pattern-key uniqueness, deterministic serialization) — it
does NOT validate any concrete `StructuralObject` instance; that is
`engine.StructuralUnderstandingEngine.analyze()`'s job.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING, List

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

if TYPE_CHECKING:
    from modules.structural_understanding_engine.patterns import StructuralPatternRegistry


def validate_structural_pattern_registry(registry: "StructuralPatternRegistry") -> ValidationResult:
    """Runs every structural-pattern-registry integrity check against
    `registry` and returns one aggregate `ValidationResult`. Never
    raises for an ordinary integrity problem — that is what the
    returned diagnostics are for."""
    diagnostics: List[ValidationDiagnostic] = []
    diagnostics.extend(_check_pattern_key_uniqueness(registry))
    diagnostics.extend(_check_deterministic_serialization(registry))
    if not diagnostics:
        return SUCCESS
    return ValidationResult(diagnostics=tuple(diagnostics))


def _check_pattern_key_uniqueness(registry: "StructuralPatternRegistry") -> List[ValidationDiagnostic]:
    """Belt-and-suspenders re-check of what
    `StructuralPatternRegistry.register()` already enforces at
    registration time."""
    counts = Counter(p.pattern_key for p in registry.all_patterns())
    duplicates = [key for key, count in counts.items() if count > 1]
    if not duplicates:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="structural_understanding.duplicate_pattern_key",
            message=f"Structural pattern key '{key}' is registered more than once.",
        )
        for key in sorted(duplicates)
    ]


def _check_deterministic_serialization(registry: "StructuralPatternRegistry") -> List[ValidationDiagnostic]:
    """Confirms that serializing `registry` twice in a row produces
    byte-identical JSON — the same serialization contract
    `educational_taxonomy.validation` / `subject_profile_framework
    .validation` already establish for their own registries."""
    first = json.dumps([p.to_dict() for p in registry.all_patterns()], sort_keys=True)
    second = json.dumps([p.to_dict() for p in registry.all_patterns()], sort_keys=True)
    if first == second:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="structural_understanding.nondeterministic_serialization",
            message="Serializing the Structural Pattern Registry twice in a row produced different output.",
        )
    ]


__all__ = [
    "validate_structural_pattern_registry",
]
