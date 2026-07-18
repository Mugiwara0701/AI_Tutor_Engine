"""
modules/heading_recognizers/base.py — M4.2A: core interfaces,
execution context, and result models for the heading recognition
framework.

Framework only (per the M4.2A spec): this module defines the
`HeadingRecognizer` abstract base class every concrete recognizer
(M4.2B/C and later — NumberedHeadingRecognizer,
HierarchicalHeadingRecognizer, RomanNumeralHeadingRecognizer,
AlphabeticHeadingRecognizer, ChapterNumberRecognizer,
ChapterTitleRecognizer, ...) will implement, plus the immutable
context/result shapes RecognitionPipeline passes between them. It
does not implement any concrete recognition logic itself.

Design mirrors modules/recognizers/base.py's own split (a plain
`Recognizer` base + a `safe_recognize()` wrapper that turns an
exception into "no match" rather than aborting a whole run), adapted
to heading-specific concerns: a heading recognizer classifies one
line/block of source text as a heading candidate (or not), rather
than extracting a whole Educational Object from an already-typed
Stage B block.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from modules.heading_recognizers.enums import HeadingClassification
from modules.heading_recognizers.exceptions import RecognizerExecutionError

logger = logging.getLogger("ncert_pipeline.heading_recognizers")


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Returns a plain, defensively-copied dict for storage on a
    frozen dataclass field — copying (rather than trusting the
    caller's mapping not to mutate later) is what actually makes the
    dataclass's immutability meaningful for mapping-typed fields."""
    return dict(value) if value else {}


@dataclass(frozen=True)
class RecognitionContext:
    """The shared, immutable execution context every recognizer's
    `recognize()` receives. Deliberately holds only what a heading
    recognizer needs to decide "is this text a heading, and if so
    what kind" — it does not carry a full Stage A `Block` or `fitz`
    document, keeping this framework decoupled from the PDF-parsing
    layer (see M4.2A's "out of scope": no PDF parsing, no layout
    detection here). A future integration milestone is responsible
    for constructing a RecognitionContext from whatever upstream
    representation (pdf_parser line, Stage A Block, ...) it is fed.

    Attributes:
        text: The raw candidate line/text being evaluated.
        page: 1-based page number the text was found on, if known.
        line_index: Position of this line within its source block/page,
            if known — used by recognizers/pipeline for tie-breaking
            and by diagnostics, never required for a match.
        preceding_heading_level: The hierarchy level (1 = chapter,
            2 = section, ...) of the most recently recognized heading
            before this context, if any — lets a recognizer reason
            about hierarchy continuity without re-deriving it itself.
        book_id / chapter_id: Optional identifiers for the source
            document, purely informational (never a routing key —
            mirrors modules/recognizers/base.py's own rule that
            subject/book identity is at most a hint, never a trigger).
        metadata: Free-form, recognizer-agnostic extra data (e.g.
            font-size hints ported from an upstream layout pass).
            Recognizers must treat unknown keys as opaque and ignore
            them rather than erroring.
    """

    text: str
    page: Optional[int] = None
    line_index: Optional[int] = None
    preceding_heading_level: Optional[int] = None
    book_id: Optional[str] = None
    chapter_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def with_metadata(self, **changes: Any) -> "RecognitionContext":
        """Returns a new context with `metadata` merged (added or
        overwritten); every other field is copied unchanged. Prefer
        this over constructing a new RecognitionContext by hand when
        only metadata needs to differ, so callers don't have to
        restate every other field."""
        merged = dict(self.metadata)
        merged.update(changes)
        from dataclasses import replace
        return replace(self, metadata=merged)


@dataclass(frozen=True)
class ConfidenceInfo:
    """Immutable breakdown of how a recognizer's raw confidence was
    turned into a pass/fail decision. Kept as a distinct value type
    (rather than flattening onto RecognitionResult) so diagnostics and
    the conflict resolver can reason about "how close was this call"
    without re-deriving it from `passed`/`adjusted_confidence` alone."""

    raw_confidence: float
    adjusted_confidence: float
    threshold: float
    passed: bool

    def __post_init__(self) -> None:
        for name in ("raw_confidence", "adjusted_confidence", "threshold"):
            value = getattr(self, name)
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError(f"ConfidenceInfo.{name} must be within [0.0, 1.0], got {value!r}.")


@dataclass(frozen=True)
class RecognitionResult:
    """What a recognizer's `recognize()` returns on a match. Immutable
    by design — once produced, a result flowing through the pipeline's
    conflict resolution cannot be altered by a later recognizer or by
    the pipeline itself; transformations (e.g. `RecognitionPipeline`
    annotating a result with its resolved rank) must construct a new
    instance via `dataclasses.replace`.

    `level` follows the same 1-based convention as
    RecognitionContext.preceding_heading_level (1 = chapter,
    2 = section, ...); a recognizer that cannot determine a level
    (e.g. it only classifies, doesn't rank) leaves it None and the
    pipeline/downstream consumer decides how to handle that.
    """

    recognizer_name: str
    classification: HeadingClassification
    confidence: float
    level: Optional[int] = None
    number: Optional[str] = None
    title: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.recognizer_name:
            raise ValueError("RecognitionResult.recognizer_name must be non-empty.")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"RecognitionResult.confidence must be within [0.0, 1.0], got {self.confidence!r}.")
        if self.level is not None and self.level < 1:
            raise ValueError(f"RecognitionResult.level must be >= 1 when set, got {self.level!r}.")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True)
class FailureResult:
    """What the pipeline records when a recognizer raises during
    `recognize()` (caught by `safe_recognize()`) or is skipped for a
    structural reason. Distinct from "no match" (`recognize()`
    returning `None` cleanly) — a FailureResult always means something
    the recognizer author would want to know about, whereas `None`
    just means "not this recognizer's pattern"."""

    recognizer_name: str
    reason: str
    exception_type: Optional[str] = None
    diagnostics: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.recognizer_name:
            raise ValueError("FailureResult.recognizer_name must be non-empty.")
        if not self.reason:
            raise ValueError("FailureResult.reason must be non-empty.")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


class HeadingRecognizer(ABC):
    """Abstract base class every concrete heading recognizer
    implements. Deliberately minimal: the framework (registry,
    factory, pipeline) only ever depends on this interface, never on
    a concrete subclass — new recognizers can be added (M4.2B/C and
    later) without any change here, satisfying M4.2A's "extension
    without modification" objective.

    Subclasses MUST set `name` and `classification` as class
    attributes (or override the properties below) and implement
    `recognize()`. `priority` and `supports()` have sensible defaults
    and rarely need overriding.
    """

    name: str = "base"
    classification: HeadingClassification = HeadingClassification.UNCLASSIFIED
    #: Lower runs first when RecognitionPipeline orders recognizers by
    #: priority (mirrors the "lower number = higher priority" convention
    #: config.DEFAULT_PRIORITY establishes). A recognizer may instead be
    #: reordered per-deployment via RecognizerSettings.priority without
    #: changing this class attribute.
    default_priority: int = 100

    @abstractmethod
    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        """Pure, deterministic, cheap. Returns `None` when this
        recognizer's pattern does not apply to `context` at all — as
        opposed to applying with low confidence, which is a
        RecognitionResult with a low `confidence` value. That
        distinction is what lets the pipeline and diagnostics tell
        "wrong recognizer for this input" apart from "right
        recognizer, but not confident". Must not raise for
        ordinary "doesn't match" input; raise only for a genuine
        recognizer bug (safe_recognize() below is the caller's safety
        net, not a substitute for handling expected non-matches)."""
        raise NotImplementedError

    def supports(self, context: RecognitionContext) -> bool:
        """Cheap pre-filter the pipeline may consult before calling
        `recognize()` at all (e.g. to skip obviously-irrelevant
        recognizers without paying for a full recognize() call).
        Default: every recognizer supports every context; a
        recognizer with a narrow applicability (e.g. only page 1)
        should override this rather than encode the check as an
        early-return inside `recognize()`, so the pipeline can record
        it as SKIPPED rather than a wasted NO_MATCH call."""
        return True

    def safe_recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        """Wraps `recognize()` so one misbehaving recognizer (a bad
        regex, an unexpected metadata shape) can't take a whole
        RecognitionPipeline run down — logs and raises
        RecognizerExecutionError, which RecognitionPipeline catches
        and records as a FailureResult, exactly mirroring
        modules/recognizers/base.py's own `safe_recognize()` contract
        for the Stage D framework."""
        try:
            return self.recognize(context)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            logger.exception(
                "Recognizer '%s' raised on context (page=%s, line_index=%s) — treating as failure.",
                self.name, context.page, context.line_index,
            )
            raise RecognizerExecutionError(self.name, str(exc)) from exc


__all__ = [
    "RecognitionContext",
    "ConfidenceInfo",
    "RecognitionResult",
    "FailureResult",
    "HeadingRecognizer",
]
