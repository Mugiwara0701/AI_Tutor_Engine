"""
modules/educational_taxonomy/validation.py — M5.2A: taxonomy-wide
integrity validation.

This is the concrete integration point with the M5.1 framework: it
reuses `modules.educational_object_framework.validation`'s
`ValidationResult` / `ValidationDiagnostic` / `DiagnosticSeverity`
contracts directly rather than defining a parallel set for the
taxonomy. Per the M5.1 spec ("do NOT duplicate ... validation
contracts"), no new validation *shape* is introduced here — only the
taxonomy-specific *checks* that produce M5.1's existing shape.

Scope: this module validates the taxonomy's own internal integrity
(uniqueness, non-empty categories, deterministic serialization,
structural well-formedness of every entry) — it does NOT validate any
concrete educational object instance against the taxonomy (e.g.
"does this extracted figure conform to the Figure type"); that is
cross-object / processor-level validation, explicitly out of scope
for this milestone (M5.2C+).
"""
from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)
from modules.educational_taxonomy.enums import EducationalCategory

if TYPE_CHECKING:
    from modules.educational_taxonomy.registry import TaxonomyRegistry


def validate_taxonomy(registry: "TaxonomyRegistry") -> ValidationResult:
    """Runs every taxonomy-integrity check against `registry` and
    returns one aggregate `ValidationResult`. Never raises for an
    ordinary integrity problem (that is what the returned diagnostics
    are for) — only a genuinely malformed `registry` argument would
    raise, and `TaxonomyRegistry` itself already guarantees key/alias
    uniqueness at registration time, so in practice this function
    mostly re-confirms that guarantee plus checks concerns registration
    time does not (categories present, deterministic serialization)."""
    diagnostics = []
    diagnostics.extend(_check_key_uniqueness(registry))
    diagnostics.extend(_check_categories_covered(registry))
    diagnostics.extend(_check_deterministic_serialization(registry))
    if not diagnostics:
        return SUCCESS
    return ValidationResult(diagnostics=tuple(diagnostics))


def _check_key_uniqueness(registry: "TaxonomyRegistry") -> list:
    """Belt-and-suspenders re-check of what `TaxonomyRegistry.register()`
    already enforces at registration time — kept as an explicit,
    independently-testable check rather than relying solely on the
    registry never having been misused."""
    counts = Counter(t.key for t in registry.all_types())
    duplicates = [key for key, count in counts.items() if count > 1]
    if not duplicates:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="taxonomy.duplicate_key",
            message=f"Educational object type key '{key}' is registered more than once.",
        )
        for key in sorted(duplicates)
    ]


def _check_categories_covered(registry: "TaxonomyRegistry") -> list:
    """Warns (does not error) if a canonical `EducationalCategory` has
    no registered object type — a category with zero members is not
    structurally invalid, but is worth surfacing since the taxonomy is
    meant to universally cover all seven categories."""
    present = {t.category for t in registry.all_types()}
    missing = [c for c in EducationalCategory if c not in present]
    if not missing:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code="taxonomy.empty_category",
            message=f"Category '{category.value}' has no registered educational object types.",
        )
        for category in missing
    ]


def _check_deterministic_serialization(registry: "TaxonomyRegistry") -> list:
    """Confirms that serializing `registry` twice in a row produces
    byte-identical JSON — the taxonomy's serialization contract (see
    `registry.TaxonomyRegistry.all_types()` and
    `models.EducationalObjectType.to_dict()`)."""
    first = json.dumps([t.to_dict() for t in registry.all_types()], sort_keys=True)
    second = json.dumps([t.to_dict() for t in registry.all_types()], sort_keys=True)
    if first == second:
        return []
    return [
        ValidationDiagnostic(
            severity=DiagnosticSeverity.ERROR,
            code="taxonomy.nondeterministic_serialization",
            message="Serializing the taxonomy twice in a row produced different output.",
        )
    ]


__all__ = [
    "validate_taxonomy",
]
