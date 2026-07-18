"""
modules/heading_canonicalization/models.py — M4.3A: the canonical
heading model — a stable internal representation a recognized heading
(M4.2 output) is converted into once, then progressively enriched by
canonicalizer steps (M4.3B and later) as it flows through
`CanonicalizationPipeline`.

Design note — why one model with placeholders, not several: M4.3A's
spec explicitly asks for "placeholders" (canonical heading type,
canonical number, numbering system, normalized title, validation
status, diagnostics) rather than a fully-populated shape, because no
M4.3A canonicalizer exists yet to populate them. Modeling this as one
`CanonicalHeading` dataclass — frozen, like every other model in this
project's recognizer/canonicalizer frameworks (see
`heading_recognizers.base.RecognitionResult`) — rather than as a
"recognized heading" + a separate "canonical result" pair keeps
exactly one object flowing through the pipeline: each canonicalizer
receives the current `CanonicalHeading` and returns either `None`
("my transformation doesn't apply here") or a new, updated instance
via `with_updates()` / `dataclasses.replace`. Nothing is ever mutated
in place.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Mapping, Optional, Tuple

from modules.heading_canonicalization.enums import (
    CanonicalHeadingType,
    NumberingSystem,
    ValidationStatus,
)
from modules.heading_canonicalization.exceptions import CanonicalHeadingValidationError
from modules.heading_recognizers.enums import HeadingClassification

if TYPE_CHECKING:  # pragma: no cover - type-checking only, no runtime dependency direction change
    from modules.heading_recognizers.base import RecognitionContext, RecognitionResult


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Defensive-copy helper, identical in spirit to
    `heading_recognizers.base._frozen_mapping` — kept as a private
    duplicate rather than a cross-package import so this package has
    no runtime dependency on `heading_recognizers` internals (only on
    its public `enums`/`base` types used for type hints and the
    `from_recognition()` adapter below)."""
    return dict(value) if value else {}


@dataclass(frozen=True)
class CanonicalHeading:
    """Stable internal representation of one heading, from the moment
    it leaves M4.2 heading recognition through however many M4.3
    canonicalization steps are configured to run against it.

    Preserved from recognition (never altered by a canonicalizer —
    these are the historical record of what M4.2 decided):
        original_text: The raw candidate text that was recognized
            (`RecognitionContext.text`).
        recognized_classification: Which heading pattern family
            matched (`RecognitionResult.classification`).
        recognized_confidence: That recognizer's confidence
            (`RecognitionResult.confidence`).
        level: The recognized hierarchy level, 1-based, if the
            recognizer determined one (`RecognitionResult.level`).
        original_numbering: The heading's numbering marker exactly as
            recognized, before any normalization
            (`RecognitionResult.number`).
        original_language: The source language the heading text was
            written in, if known (e.g. "en", "hi", "sa") — purely
            informational, mirrors `RecognitionContext.book_id`'s own
            "hint, never a trigger" convention; no canonicalizer in
            this milestone branches on it.

    Canonicalization placeholders (M4.3A defines the field; a later
    M4.3 milestone is what actually assigns a non-default value):
        canonical_type: This heading's structural role once
            canonicalized (see `CanonicalHeadingType`). None until a
            future canonicalizer assigns one.
        canonical_number: The heading's numbering, normalized into a
            stable internal form. None until a future
            number-system canonicalizer assigns one (M4.3B).
        numbering_system: Which numeral/marker system
            `original_numbering` was written in (see
            `NumberingSystem`). Defaults to `UNKNOWN` — "not yet
            determined" — distinct from `NONE` ("determined to have
            no numbering").
        normalized_title: The heading's title text, normalized. None
            until a future title-normalizer canonicalizer assigns one.
        validation_status: Coarse validation state (see
            `ValidationStatus`). Defaults to `PENDING` — no validator
            has run yet; only a structural-validator canonicalizer
            (out of scope for M4.3A) ever changes this.

    Bookkeeping:
        diagnostics: Free-form, human-readable notes accumulated by
            canonicalizer steps (e.g. "left canonical_number unset:
            no numbering-system canonicalizer registered"). Never
            parsed by the framework itself — purely for humans and
            tests, mirrors `RecognitionResult.diagnostics`.
        metadata: Free-form, canonicalizer-agnostic extra data.
            Canonicalizers must treat unknown keys as opaque and
            ignore them rather than erroring — same contract as
            `RecognitionContext.metadata`.
    """

    original_text: str
    recognized_classification: HeadingClassification
    recognized_confidence: float
    level: Optional[int] = None
    original_numbering: Optional[str] = None
    original_language: Optional[str] = None

    canonical_type: Optional[CanonicalHeadingType] = None
    canonical_number: Optional[str] = None
    numbering_system: NumberingSystem = NumberingSystem.UNKNOWN
    normalized_title: Optional[str] = None
    validation_status: ValidationStatus = ValidationStatus.PENDING

    diagnostics: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.original_text, str) or not self.original_text.strip():
            raise CanonicalHeadingValidationError(
                "CanonicalHeading.original_text must be a non-empty string."
            )
        if not isinstance(self.recognized_classification, HeadingClassification):
            raise CanonicalHeadingValidationError(
                "CanonicalHeading.recognized_classification must be a HeadingClassification, "
                f"got {type(self.recognized_classification).__name__}."
            )
        if not (0.0 <= float(self.recognized_confidence) <= 1.0):
            raise CanonicalHeadingValidationError(
                f"CanonicalHeading.recognized_confidence must be within [0.0, 1.0], "
                f"got {self.recognized_confidence!r}."
            )
        if self.level is not None and self.level < 1:
            raise CanonicalHeadingValidationError(
                f"CanonicalHeading.level must be >= 1 when set, got {self.level!r}."
            )
        if self.canonical_type is not None and not isinstance(self.canonical_type, CanonicalHeadingType):
            raise CanonicalHeadingValidationError(
                "CanonicalHeading.canonical_type must be a CanonicalHeadingType or None, "
                f"got {type(self.canonical_type).__name__}."
            )
        if not isinstance(self.numbering_system, NumberingSystem):
            raise CanonicalHeadingValidationError(
                "CanonicalHeading.numbering_system must be a NumberingSystem, "
                f"got {type(self.numbering_system).__name__}."
            )
        if not isinstance(self.validation_status, ValidationStatus):
            raise CanonicalHeadingValidationError(
                "CanonicalHeading.validation_status must be a ValidationStatus, "
                f"got {type(self.validation_status).__name__}."
            )
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    # -- immutable "update" helpers --------------------------------------------------

    def with_updates(self, **changes: Any) -> "CanonicalHeading":
        """Returns a new `CanonicalHeading` with `changes` applied;
        every other field is copied unchanged. The one mutation
        method every canonicalizer should use instead of constructing
        a new `CanonicalHeading` by hand, so a canonicalizer that only
        cares about (say) `canonical_number` doesn't have to restate
        every other field."""
        return replace(self, **changes)

    def with_diagnostic(self, message: str) -> "CanonicalHeading":
        """Returns a new `CanonicalHeading` with `message` appended to
        `diagnostics`. Convenience wrapper around `with_updates()` for
        the single most common per-step update."""
        return self.with_updates(diagnostics=self.diagnostics + (message,))

    def with_metadata(self, **changes: Any) -> "CanonicalHeading":
        """Returns a new `CanonicalHeading` with `metadata` merged
        (added or overwritten); every other field is copied
        unchanged. Mirrors `RecognitionContext.with_metadata()`."""
        merged = dict(self.metadata)
        merged.update(changes)
        return self.with_updates(metadata=merged)

    @property
    def is_canonicalized(self) -> bool:
        """True once at least the two structural placeholders that
        matter most downstream (`canonical_type`, `numbering_system`
        being resolved away from `UNKNOWN`) have been assigned by some
        canonicalizer. Never true immediately after
        `from_recognition()` — purely a convenience for callers
        (including tests) that want to check "has any canonicalizer
        actually run on this heading" without inspecting every field
        individually."""
        return self.canonical_type is not None and self.numbering_system != NumberingSystem.UNKNOWN

    # -- M4.2 interop --------------------------------------------------

    @classmethod
    def from_recognition(
        cls,
        context: "RecognitionContext",
        result: "RecognitionResult",
        *,
        original_language: Optional[str] = None,
    ) -> "CanonicalHeading":
        """Builds the initial `CanonicalHeading` for one heading,
        directly from the M4.2 framework's own output shapes
        (`RecognitionContext` + the `RecognitionResult` it produced —
        e.g. `PipelineResult.winner` from
        `heading_recognizers.pipeline.RecognitionPipeline.run()`).

        This is the framework's one bridge from "heading recognition
        output" to "canonicalization input" (M4.3A's stated
        responsibility: "receives recognized headings produced by
        M4.2 and prepares them for deterministic normalization in
        later milestones") — deliberately a plain adapter function
        with no side effects and no dependency on Stage B / the
        production pipeline, so it stays usable in isolation (e.g.
        from tests) exactly as easily as from
        `modules/stage_b_classify.py` would use it in a future
        integration milestone (explicitly out of scope for M4.3A).

        Every canonicalization placeholder is left at its default
        (`None` / `UNKNOWN` / `PENDING`) — this adapter performs no
        normalization itself.
        """
        return cls(
            original_text=context.text,
            recognized_classification=result.classification,
            recognized_confidence=result.confidence,
            level=result.level,
            original_numbering=result.number,
            original_language=original_language,
        )


__all__ = [
    "CanonicalHeading",
]
