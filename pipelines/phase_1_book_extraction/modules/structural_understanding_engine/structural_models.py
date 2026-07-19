"""
modules/structural_understanding_engine/structural_models.py — M5.2C:
`StructuralObject` (the input) and `StructuralAnalysisResult` (the
output) of `engine.StructuralUnderstandingEngine.analyze()`.

Design note, mirroring `educational_object_framework.models`' own
"result model, not an evolving payload" choice: `StructuralObject` is
never mutated by the engine — analysis produces a separate, immutable
`StructuralAnalysisResult` report about it, the same
report-not-replacement shape `ProcessingResult` (M5.1) already
establishes for `ProcessingContext.current_object`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)
from modules.structural_understanding_engine.enums import AnalysisOutcome
from modules.structural_understanding_engine.exceptions import StructuralAnalysisError


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    return dict(value) if value else {}


@dataclass(frozen=True)
class StructuralObject:
    """The generic, opaque-content object `StructuralUnderstandingEngine
    .analyze()` examines the structure of.

    Attributes:
        object_key: Free-form identifier for the concrete educational
            object instance this describes (e.g. a Stage D block id)
            — purely informational, never a routing key, same
            convention `ProcessingContext.book_id` (M5.1) establishes.
        object_type_key: The `EducationalObjectType.key` (M5.2A) this
            instance claims to be — used by
            `StructuralUnderstandingEngine` only to look up taxonomy
            compatibility; never assumed to exist without checking.
        pattern_key: Optional explicit `StructuralPattern.pattern_key`
            (see `patterns.py`) this object should be matched against.
            When `None`, the engine falls back to whatever
            `StructuralHints.pattern_key` a resolved contribution
            supplies, and finally to `object_type_key` itself (many
            taxonomy keys already coincide with a pattern key, e.g.
            "worked_example").
        components: Maps a structural component role (or a subject
            profile's own alias for one, see `StructuralHints
            .component_aliases`) to whatever content the caller
            already extracted for it. Opaque `Any` — this framework
            never inspects a component's *content*, only whether the
            role is present at all.
        metadata: Free-form, engine-agnostic context, opaque to this
            framework.
    """

    object_key: str
    object_type_key: str
    pattern_key: Optional[str] = None
    components: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.object_key, str) or not self.object_key:
            raise StructuralAnalysisError("StructuralObject.object_key must be a non-empty string.")
        if not isinstance(self.object_type_key, str) or not self.object_type_key:
            raise StructuralAnalysisError("StructuralObject.object_type_key must be a non-empty string.")
        if self.pattern_key is not None and (not isinstance(self.pattern_key, str) or not self.pattern_key):
            raise StructuralAnalysisError("StructuralObject.pattern_key must be a non-empty string or None.")
        object.__setattr__(self, "components", _frozen_mapping(self.components))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def with_components(self, **changes: Any) -> "StructuralObject":
        """Returns a new `StructuralObject` with `components` merged
        (added or overwritten); every other field is copied
        unchanged."""
        merged = dict(self.components)
        merged.update(changes)
        from dataclasses import replace
        return replace(self, components=merged)


@dataclass(frozen=True)
class StructuralAnalysisResult:
    """What `StructuralUnderstandingEngine.analyze()` returns: an
    immutable report about one `StructuralObject`, never a mutation of
    it.

    Attributes:
        object_key: Echoes `StructuralObject.object_key` this result
            concerns.
        pattern_key: Which `StructuralPattern` was actually matched
            against, or `None` if none could be resolved
            (`outcome == UNRECOGNIZED_PATTERN`).
        outcome: The coarse `AnalysisOutcome` this result represents.
        present_roles: Which of the matched pattern's component roles
            were found in `StructuralObject.components` (after
            resolving any `StructuralHints.component_aliases`).
        missing_roles: Which required roles (pattern-required, plus
            any `ValidationHints.required_roles` addition) were not
            found.
        validation: An M5.1 `ValidationResult` — reused directly per
            the M5.2C spec's "reuse the M5.1 validation framework
            wherever appropriate" — carrying one diagnostic per
            missing required role.
    """

    object_key: str
    pattern_key: Optional[str]
    outcome: AnalysisOutcome
    present_roles: Tuple[str, ...] = field(default_factory=tuple)
    missing_roles: Tuple[str, ...] = field(default_factory=tuple)
    validation: ValidationResult = field(default_factory=lambda: SUCCESS)

    def __post_init__(self) -> None:
        if not isinstance(self.object_key, str) or not self.object_key:
            raise StructuralAnalysisError("StructuralAnalysisResult.object_key must be a non-empty string.")
        if not isinstance(self.outcome, AnalysisOutcome):
            raise StructuralAnalysisError(
                f"StructuralAnalysisResult.outcome must be an AnalysisOutcome, got {type(self.outcome).__name__}."
            )
        object.__setattr__(self, "present_roles", tuple(self.present_roles))
        object.__setattr__(self, "missing_roles", tuple(self.missing_roles))

    @property
    def is_complete(self) -> bool:
        return self.outcome == AnalysisOutcome.COMPLETE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_key": self.object_key,
            "pattern_key": self.pattern_key,
            "outcome": self.outcome.value,
            "present_roles": list(self.present_roles),
            "missing_roles": list(self.missing_roles),
            "diagnostics": [
                {"severity": d.severity.value, "code": d.code, "message": d.message}
                for d in self.validation.diagnostics
            ],
        }


__all__ = [
    "StructuralObject",
    "StructuralAnalysisResult",
]
