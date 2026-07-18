"""
modules/heading_canonicalization/base.py — M4.3A: core interfaces and
execution context for the heading canonicalization framework.

Mirrors modules/heading_recognizers/base.py's own split exactly, one
layer downstream: a plain `HeadingCanonicalizer` abstract base class
every concrete canonicalizer (M4.3B — RomanNumeralCanonicalizer,
ArabicNumeralCanonicalizer, DevanagariNumeralCanonicalizer, and later
a title normalizer and structural validator) will implement, plus the
context/failure shapes `CanonicalizationPipeline` passes between them.
Framework only — this module implements no concrete canonicalization
logic itself (see the M4.3A spec's "Out of Scope").
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional, Tuple

from modules.heading_canonicalization.exceptions import CanonicalizerExecutionError
from modules.heading_canonicalization.models import CanonicalHeading

logger = logging.getLogger("ncert_pipeline.heading_canonicalization")


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Defensive-copy helper — see `models._frozen_mapping` for why
    this is duplicated per-module rather than shared."""
    return dict(value) if value else {}


@dataclass(frozen=True)
class CanonicalizationContext:
    """The shared, immutable execution context every canonicalizer's
    `canonicalize()` receives alongside the `CanonicalHeading` it
    operates on. Deliberately separate from `CanonicalHeading` itself
    (which IS the evolving payload) — this holds everything a
    canonicalizer might need to know about *where* that heading sits
    that isn't part of the heading's own data, mirroring
    `heading_recognizers.base.RecognitionContext`'s own role one layer
    upstream.

    Attributes:
        book_id / chapter_id: Optional identifiers for the source
            document, purely informational — never a routing key, same
            convention as `RecognitionContext.book_id`/`chapter_id`.
        preceding_canonical_number: The most recently canonicalized
            heading's `canonical_number` at the same or shallower
            level, if any — lets a future canonicalizer (e.g. a
            sequence validator) reason about numbering continuity
            without re-deriving it itself. None until a canonicalizer
            actually populates `canonical_number` on some heading
            (M4.3A leaves this unset in ordinary use).
        preceding_numbering_system: The `NumberingSystem` associated
            with `preceding_canonical_number`, if known — lets a
            canonicalizer detect a numbering-system switch mid-
            document without re-deriving it itself.
        metadata: Free-form, canonicalizer-agnostic extra data.
            Canonicalizers must treat unknown keys as opaque and
            ignore them rather than erroring — same contract as
            `RecognitionContext.metadata`.
    """

    book_id: Optional[str] = None
    chapter_id: Optional[str] = None
    preceding_canonical_number: Optional[str] = None
    preceding_numbering_system: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def with_metadata(self, **changes: Any) -> "CanonicalizationContext":
        """Returns a new context with `metadata` merged (added or
        overwritten); every other field is copied unchanged. Mirrors
        `RecognitionContext.with_metadata()`."""
        merged = dict(self.metadata)
        merged.update(changes)
        return replace(self, metadata=merged)


@dataclass(frozen=True)
class CanonicalizationFailure:
    """What the pipeline records when a canonicalizer raises during
    `canonicalize()` (caught by `safe_canonicalize()`) or is skipped
    for a structural reason. Mirrors
    `heading_recognizers.base.FailureResult` exactly, applied to
    canonicalizers instead of recognizers."""

    canonicalizer_name: str
    reason: str
    exception_type: Optional[str] = None
    diagnostics: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.canonicalizer_name:
            raise ValueError("CanonicalizationFailure.canonicalizer_name must be non-empty.")
        if not self.reason:
            raise ValueError("CanonicalizationFailure.reason must be non-empty.")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


class HeadingCanonicalizer(ABC):
    """Abstract base class every concrete canonicalizer implements.
    Deliberately minimal — mirrors
    `heading_recognizers.base.HeadingRecognizer` one layer downstream:
    the framework (registry, pipeline) only ever depends on this
    interface, never on a concrete subclass, so a new canonicalizer
    (M4.3B and later — a Roman/Arabic/Devanagari numeral
    canonicalizer, a title normalizer, a structural validator) can be
    added without any change here.

    Subclasses MUST set `name` as a class attribute and implement
    `canonicalize()`. `default_priority` and `supports()` have
    sensible defaults and rarely need overriding.
    """

    name: str = "base"
    #: Lower runs first when `CanonicalizationPipeline` orders
    #: canonicalizers by priority — identical convention to
    #: `HeadingRecognizer.default_priority`. A canonicalizer may
    #: instead be reordered per-deployment via
    #: `CanonicalizerSettings.priority` without changing this class
    #: attribute.
    default_priority: int = 100

    @abstractmethod
    def canonicalize(
        self,
        heading: CanonicalHeading,
        context: CanonicalizationContext,
    ) -> Optional[CanonicalHeading]:
        """Pure, deterministic, cheap. Returns a NEW `CanonicalHeading`
        (via `heading.with_updates(...)`) when this canonicalizer
        applies and changes something; returns `None` when this
        canonicalizer's transformation does not apply to `heading` at
        all — the canonicalization analogue of
        `HeadingRecognizer.recognize()` returning `None` for "wrong
        recognizer for this input" rather than "matched with low
        confidence". Must never mutate `heading` in place (it is
        frozen, so this would raise regardless) and must never raise
        for ordinary "doesn't apply" input; raise only for a genuine
        canonicalizer bug (`safe_canonicalize()` below is the caller's
        safety net, not a substitute for handling expected
        non-applicability)."""
        raise NotImplementedError

    def supports(self, heading: CanonicalHeading, context: CanonicalizationContext) -> bool:
        """Cheap pre-filter the pipeline may consult before calling
        `canonicalize()` at all (e.g. a numbering-system canonicalizer
        skipping a heading that already has a `canonical_number`).
        Default: every canonicalizer supports every heading; a
        canonicalizer with narrow applicability should override this
        rather than encode the check as an early-return inside
        `canonicalize()`, so the pipeline can record it as SKIPPED
        rather than a wasted UNCHANGED call. Mirrors
        `HeadingRecognizer.supports()`."""
        return True

    def safe_canonicalize(
        self,
        heading: CanonicalHeading,
        context: CanonicalizationContext,
    ) -> Optional[CanonicalHeading]:
        """Wraps `canonicalize()` so one misbehaving canonicalizer
        can't take a whole `CanonicalizationPipeline` run down — logs
        and raises `CanonicalizerExecutionError`, which
        `CanonicalizationPipeline` catches and records as a
        `CanonicalizationFailure`, exactly mirroring
        `HeadingRecognizer.safe_recognize()`'s own contract."""
        try:
            return self.canonicalize(heading, context)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            logger.exception(
                "Canonicalizer '%s' raised on heading (original_text=%r) — treating as failure.",
                self.name, heading.original_text,
            )
            raise CanonicalizerExecutionError(self.name, str(exc)) from exc


__all__ = [
    "CanonicalizationContext",
    "CanonicalizationFailure",
    "HeadingCanonicalizer",
]
