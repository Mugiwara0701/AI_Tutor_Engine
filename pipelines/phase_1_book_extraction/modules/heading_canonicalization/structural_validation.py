"""
modules/heading_canonicalization/structural_validation.py — M4.3D:
Structural Validation.

Adds one cooperating `HeadingCanonicalizer` — `StructuralValidator` —
to the M4.3A framework, exactly the way M4.3B added the numeral
canonicalizer family: nothing in `base.py`, `config.py`, `registry.py`,
`pipeline.py`, or `validation.py` is changed. `validation.py`'s own
docstring anticipated this module precisely: "a future structural-
validator canonicalizer (implementing `base.HeadingCanonicalizer`) is
what will actually populate a `ValidationResult`" — this is that
canonicalizer.

Scope (per the M4.3D spec): validate the *relationships between*
already-canonicalized headings. This module recognizes nothing,
canonicalizes nothing, and never rewrites a heading's numbering,
type, or title — it only reads `CanonicalHeading` fields other
canonicalizers already populated (`canonical_number`,
`numbering_system`, `canonical_type`, `level`) plus the
`CanonicalizationContext` a caller supplies, and produces diagnostics.

Three rule groups, each independent and each individually
best-effort (a failure/ambiguity in one never blocks the others):

  1. Number sequence validation — duplicate / decreasing / skipped
     numbering versus the immediately preceding heading, using the
     `CanonicalizationContext.preceding_canonical_number` /
     `preceding_numbering_system` fields `base.py` already reserved
     for exactly this ("lets a future canonicalizer (e.g. a sequence
     validator) reason about numbering continuity without
     re-deriving it itself").

  2. Hierarchy validation — orphan headings and invalid level jumps,
     using `CanonicalHeading.level` (from M4.2 recognition) and one
     additional piece of caller-supplied context: the preceding
     heading's own level. Because `CanonicalizationContext`'s field
     set is frozen (M4.3A/B/C API freeze), this is threaded through
     the existing, explicitly-opaque `context.metadata` mapping
     (`context.metadata["preceding_heading_level"]`) rather than by
     adding a new dataclass field — no framework file changes.

  3. Canonical consistency validation — internal agreement between
     a single heading's own `canonical_number`, `numbering_system`,
     `canonical_type`, and `level` (no sequence/context needed).

Every rule degrades to a diagnostic, never an exception: malformed or
absent data (a `canonical_number` that isn't an integer string, a
missing `level`, no preceding context at all) simply narrows which
rules can run, exactly like `numeral_canonicalizers.py`'s own
"malformed input never raises" contract.
"""
from __future__ import annotations

from typing import List, Optional

from modules.heading_canonicalization.base import CanonicalizationContext, HeadingCanonicalizer
from modules.heading_canonicalization.enums import (
    CanonicalHeadingType,
    NumberingSystem,
    ValidationSeverity,
    ValidationStatus,
)
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

#: Context.metadata key a caller (e.g. modules/stage_b_classify.py)
#: populates with the immediately preceding heading's own `level`
#: (int, 1-based), or omits/leaves None when there is no preceding
#: heading (start of document/chapter) or its level is unknown. Kept
#: as a plain, documented metadata key rather than a new
#: `CanonicalizationContext` field, per that dataclass's frozen API.
PRECEDING_LEVEL_METADATA_KEY = "preceding_heading_level"

#: The expected recognized `level` for each `CanonicalHeadingType`,
#: used only for the (currently rare, forward-compatible) consistency
#: check between `canonical_type` and `level` -- see
#: `_check_canonical_consistency`. `KEYWORD_SECTION`/`UNSPECIFIED`
#: intentionally have no fixed expected level (a keyword section like
#: "Summary" can legitimately sit at any depth).
_EXPECTED_LEVEL_BY_TYPE = {
    CanonicalHeadingType.CHAPTER: 1,
    CanonicalHeadingType.SECTION: 2,
    CanonicalHeadingType.SUBSECTION: 3,
    CanonicalHeadingType.SUBSUBSECTION: 4,
}

#: Numbering systems `_check_number_sequence` knows how to order
#: (i.e. that were converted to a plain non-negative integer string
#: by `numeral_canonicalizers.py`). `HIERARCHICAL`/`ALPHABETIC` are
#: defined in `enums.py` for a future canonicalizer but nothing in
#: M4.3B produces them yet, and `NONE`/`UNKNOWN` carry no orderable
#: number at all -- sequence validation simply does not apply.
_ORDERABLE_NUMBERING_SYSTEMS = frozenset({
    NumberingSystem.ARABIC, NumberingSystem.ROMAN, NumberingSystem.DEVANAGARI,
})


def _parse_canonical_number(value: Optional[str]) -> Optional[int]:
    """Best-effort int parse of a `canonical_number` string. Returns
    `None` -- never raises -- for `None`/blank/non-integer input, so a
    surprising/malformed value (e.g. left over from a future
    canonicalizer this module doesn't know about) simply disables the
    checks that need an ordered value, rather than crashing
    validation."""
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return int(candidate)
    except ValueError:
        return None


def _check_number_sequence(
    heading: CanonicalHeading, context: CanonicalizationContext
) -> List[ValidationDiagnostic]:
    """Rule group 1: duplicate / decreasing / skipped numbering, and a
    mid-sequence numbering-system switch, versus the immediately
    preceding heading -- using only what `context` already carries
    (`preceding_canonical_number`, `preceding_numbering_system`).
    Silently produces no diagnostics when there is nothing to compare
    (no preceding value, current heading unnumbered, either value
    non-orderable/unparsable) -- absence of a prior heading is a
    normal state (start of document), not a validation failure."""
    diagnostics: List[ValidationDiagnostic] = []

    if context.preceding_canonical_number is None:
        return diagnostics
    if heading.numbering_system not in _ORDERABLE_NUMBERING_SYSTEMS:
        return diagnostics

    current_value = _parse_canonical_number(heading.canonical_number)
    preceding_value = _parse_canonical_number(context.preceding_canonical_number)
    if current_value is None or preceding_value is None:
        return diagnostics

    if (
        context.preceding_numbering_system is not None
        and context.preceding_numbering_system != heading.numbering_system.value
    ):
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.WARNING,
            code="numbering_system_switch",
            message=(
                f"numbering system changed from {context.preceding_numbering_system!r} "
                f"to {heading.numbering_system.value!r} mid-sequence "
                f"(preceding_number={context.preceding_canonical_number!r}, "
                f"current_number={heading.canonical_number!r})."
            ),
            canonicalizer_name="structural_validator",
        ))

    if current_value == preceding_value:
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.ERROR,
            code="duplicate_number",
            message=(
                f"duplicate numbering: canonical_number {heading.canonical_number!r} "
                f"repeats the immediately preceding heading's number."
            ),
            canonicalizer_name="structural_validator",
        ))
    elif current_value < preceding_value:
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.ERROR,
            code="decreasing_number",
            message=(
                f"decreasing numbering: canonical_number {heading.canonical_number!r} "
                f"is less than the preceding heading's {context.preceding_canonical_number!r}."
            ),
            canonicalizer_name="structural_validator",
        ))
    elif current_value - preceding_value > 1:
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.WARNING,
            code="skipped_number",
            message=(
                f"skipped numbering: jumped from {context.preceding_canonical_number!r} "
                f"to {heading.canonical_number!r} (gap of {current_value - preceding_value})."
            ),
            canonicalizer_name="structural_validator",
        ))

    return diagnostics


def _check_hierarchy(
    heading: CanonicalHeading, context: CanonicalizationContext
) -> List[ValidationDiagnostic]:
    """Rule group 2: orphan headings and invalid hierarchy jumps, using
    `heading.level` (M4.2's recognized depth) and the preceding
    heading's own level, threaded through
    `context.metadata[PRECEDING_LEVEL_METADATA_KEY]`. A heading whose
    own `level` is unknown can't be checked at all (no diagnostic --
    an absent input, not an invalid one). Descending to a shallower or
    equal level (dedenting, e.g. a subsection ending and a new
    chapter starting) is always valid and never flagged; only jumping
    MORE than one level deeper at once (e.g. a chapter directly
    followed by a subsection, with no intervening section) is
    structurally impossible and flagged."""
    diagnostics: List[ValidationDiagnostic] = []

    if heading.level is None:
        return diagnostics

    preceding_level = context.metadata.get(PRECEDING_LEVEL_METADATA_KEY)
    if preceding_level is None:
        if heading.level > 1:
            diagnostics.append(ValidationDiagnostic(
                severity=ValidationSeverity.WARNING,
                code="orphan_heading",
                message=(
                    f"heading recognized at level {heading.level} with no preceding "
                    f"heading at a shallower level in this context -- possibly an "
                    f"orphan child heading, or simply the first heading seen."
                ),
                canonicalizer_name="structural_validator",
            ))
        return diagnostics

    if not isinstance(preceding_level, int):
        # Malformed caller-supplied context -- never let this crash validation.
        return diagnostics

    if heading.level > preceding_level + 1:
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.ERROR,
            code="hierarchy_level_jump",
            message=(
                f"invalid hierarchy jump: level {preceding_level} directly followed by "
                f"level {heading.level}, skipping {heading.level - preceding_level - 1} "
                f"intervening level(s)."
            ),
            canonicalizer_name="structural_validator",
        ))

    return diagnostics


def _check_canonical_consistency(heading: CanonicalHeading) -> List[ValidationDiagnostic]:
    """Rule group 3: internal agreement between one heading's own
    `canonical_number`, `numbering_system`, `canonical_type`, and
    `level` -- no context/sequence needed."""
    diagnostics: List[ValidationDiagnostic] = []

    has_number = heading.canonical_number is not None
    system = heading.numbering_system

    if has_number and system in (NumberingSystem.NONE, NumberingSystem.UNKNOWN):
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.ERROR,
            code="canonical_inconsistency",
            message=(
                f"canonical_number {heading.canonical_number!r} is set but "
                f"numbering_system is {system.value!r} (expected a resolved system)."
            ),
            canonicalizer_name="structural_validator",
        ))

    if not has_number and system in _ORDERABLE_NUMBERING_SYSTEMS:
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.WARNING,
            code="canonical_inconsistency",
            message=(
                f"numbering_system resolved to {system.value!r} but canonical_number "
                f"was never set (the numeral canonicalizer likely rejected malformed "
                f"input -- see this heading's own diagnostics)."
            ),
            canonicalizer_name="structural_validator",
        ))

    if heading.canonical_type is not None and heading.level is not None:
        expected_level = _EXPECTED_LEVEL_BY_TYPE.get(heading.canonical_type)
        if expected_level is not None and heading.level != expected_level:
            diagnostics.append(ValidationDiagnostic(
                severity=ValidationSeverity.WARNING,
                code="canonical_type_level_mismatch",
                message=(
                    f"canonical_type {heading.canonical_type.value!r} usually implies "
                    f"level {expected_level}, but this heading was recognized at "
                    f"level {heading.level}."
                ),
                canonicalizer_name="structural_validator",
            ))

    if heading.canonical_type == CanonicalHeadingType.KEYWORD_SECTION and has_number:
        diagnostics.append(ValidationDiagnostic(
            severity=ValidationSeverity.WARNING,
            code="canonical_type_level_mismatch",
            message=(
                f"canonical_type is 'keyword_section' (e.g. Summary/Exercises) but "
                f"canonical_number {heading.canonical_number!r} is set -- keyword "
                f"sections are not expected to carry a numeric position."
            ),
            canonicalizer_name="structural_validator",
        ))

    return diagnostics


class StructuralValidator(HeadingCanonicalizer):
    """M4.3D: validates the relationships between canonical headings
    (number sequence, hierarchy, canonical consistency) and records
    the outcome as validation diagnostics. Never rewrites a heading's
    recognition or canonicalization fields (`original_*`,
    `canonical_number`, `numbering_system`, `canonical_type`,
    `normalized_title`) -- only ever updates `validation_status`,
    appends to `diagnostics`, and attaches the full structured
    `ValidationResult` under `metadata["structural_validation"]` for
    any downstream consumer that wants more than the coarse status
    (mirrors how `modules/stage_b_classify.py` already attaches
    structured canonicalization output under its own new metadata key
    rather than overloading an existing one).

    Runs last in the pipeline (`default_priority` higher than every
    M4.3B canonicalizer's) so every canonicalizer that might still
    populate `canonical_number`/`numbering_system`/`canonical_type`
    has already had its turn by the time validation rules run."""

    name = "structural_validator"
    default_priority = 200

    def supports(self, heading: CanonicalHeading, context: CanonicalizationContext) -> bool:
        # Runs at most once per heading per pipeline execution -- once
        # validation_status has been set away from PENDING, this
        # heading has already been validated (mirrors
        # NumberingSystemDetector.supports()'s own
        # "already resolved, nothing left to do" convention).
        return heading.validation_status == ValidationStatus.PENDING

    def canonicalize(
        self, heading: CanonicalHeading, context: CanonicalizationContext
    ) -> Optional[CanonicalHeading]:
        diagnostics: List[ValidationDiagnostic] = []
        diagnostics.extend(_check_number_sequence(heading, context))
        diagnostics.extend(_check_hierarchy(heading, context))
        diagnostics.extend(_check_canonical_consistency(heading))

        result = ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS

        updated = heading.with_updates(
            validation_status=result.status,
            diagnostics=heading.diagnostics + tuple(
                f"structural_validator[{d.code}]: {d.message}" for d in result.diagnostics
            ),
        )
        return updated.with_metadata(structural_validation=result)


__all__ = [
    "StructuralValidator",
    "PRECEDING_LEVEL_METADATA_KEY",
]
