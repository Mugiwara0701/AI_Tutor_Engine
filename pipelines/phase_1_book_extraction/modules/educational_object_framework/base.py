"""
modules/educational_object_framework/base.py — M5.1: core interfaces
and execution context for the educational object processing
framework.

Mirrors modules/heading_canonicalization/base.py's own split exactly,
one layer downstream in spirit (though a sibling, not a successor, in
the pipeline sense — see this package's `README.md`): a plain
`EducationalObjectProcessor` abstract base class every concrete
processor (M5.2 — an EquationProcessor, FigureProcessor,
TableProcessor, DiagramProcessor, ExampleProcessor, ActivityProcessor,
DefinitionProcessor, GlossaryProcessor, ...) will implement, plus the
context/failure shapes `ProcessingPipeline` passes between them.
Framework only — this module implements no concrete object-specific
processing logic itself (see the M5.1 spec's "Out of Scope").

`ProcessingContext` is deliberately generic: it carries a
`current_object` field typed `Any`, not any concrete educational
object model. Nothing here imports `schemas.chapter_schema` or any
other object-specific schema — a future processor is free to expect
whatever shape it needs from `current_object` (e.g. a
`schemas.chapter_schema.Equation` Pydantic model, a raw dict, a Stage
D block) without this framework ever needing to change.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional, Tuple

from modules.educational_object_framework.exceptions import ProcessorExecutionError

logger = logging.getLogger("ncert_pipeline.educational_object_framework")


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Defensive-copy helper — see
    `heading_canonicalization.base._frozen_mapping` for why this is
    duplicated per-module rather than shared across packages."""
    return dict(value) if value else {}


@dataclass(frozen=True)
class ProcessingContext:
    """The shared, immutable execution context every processor's
    `process()` receives. Deliberately generic — no field here
    assumes any particular educational object type; a concrete
    processor (M5.2) is what interprets `current_object` /
    `object_type` and decides whether it applies.

    Attributes:
        current_object: The object being processed, in whatever shape
            an upstream stage produced it (a Stage D block, a
            `schemas.chapter_schema.CanonicalObjectBase` subclass
            instance, a raw dict, ...). Opaque to this framework —
            never inspected, never assumed to have any particular
            attribute, by anything in this package.
        object_type: An optional, free-form string hint for what kind
            of educational object `current_object` is (e.g.
            "equation", "figure", "table") — purely informational,
            same "hint, never a trigger" convention
            `RecognitionContext.book_id` establishes; the framework
            itself never branches on it. A concrete processor may use
            it as a cheap `supports()` pre-filter instead of
            inspecting `current_object` itself.
        chapter_metadata: Free-form chapter-level context (e.g.
            chapter number/title, subject, board) a processor may
            want without needing its own lookup. Generic mapping
            rather than a specific schema type, for the same
            decoupling reason as `current_object`.
        surrounding_context: Free-form neighbourhood information (e.g.
            preceding/following objects, page position, layout hints)
            a processor may use to reason about `current_object` in
            relation to what is around it, without this framework
            assuming any particular shape for that neighbourhood.
        book_id / chapter_id: Optional identifiers for the source
            document, purely informational — never a routing key,
            mirrors `RecognitionContext.book_id`/`chapter_id`'s own
            convention.
        metadata: Free-form, processor-agnostic processing metadata
            (e.g. run id, timing hints ported from an upstream stage).
            Processors must treat unknown keys as opaque and ignore
            them rather than erroring — same contract as
            `RecognitionContext.metadata`.
        diagnostics: Free-form, human-readable notes accumulated
            before or between processor runs (e.g. by whatever
            upstream stage constructs a `ProcessingContext`). Never
            parsed by the framework itself — purely for humans and
            tests.
    """

    current_object: Any = None
    object_type: Optional[str] = None
    chapter_metadata: Mapping[str, Any] = field(default_factory=dict)
    surrounding_context: Mapping[str, Any] = field(default_factory=dict)
    book_id: Optional[str] = None
    chapter_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "chapter_metadata", _frozen_mapping(self.chapter_metadata))
        object.__setattr__(self, "surrounding_context", _frozen_mapping(self.surrounding_context))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def with_metadata(self, **changes: Any) -> "ProcessingContext":
        """Returns a new context with `metadata` merged (added or
        overwritten); every other field is copied unchanged. Mirrors
        `RecognitionContext.with_metadata()` /
        `CanonicalizationContext.with_metadata()`."""
        merged = dict(self.metadata)
        merged.update(changes)
        return replace(self, metadata=merged)

    def with_diagnostic(self, message: str) -> "ProcessingContext":
        """Returns a new context with `message` appended to
        `diagnostics`; every other field is copied unchanged."""
        return replace(self, diagnostics=self.diagnostics + (message,))

    def with_current_object(self, current_object: Any, object_type: Optional[str] = None) -> "ProcessingContext":
        """Returns a new context pointed at a different
        `current_object` (and, optionally, `object_type`); every
        other field — chapter metadata, surrounding context,
        identifiers, processing metadata, diagnostics — is copied
        unchanged. The convenience an upstream stage uses to walk a
        chapter's objects one at a time through the same
        `ProcessingPipeline` without rebuilding the rest of the
        context each time."""
        if object_type is not None:
            return replace(self, current_object=current_object, object_type=object_type)
        return replace(self, current_object=current_object)


@dataclass(frozen=True)
class ProcessingFailure:
    """What the pipeline records when a processor raises during
    `process()` (caught by `safe_process()`) or is skipped for a
    structural reason. Mirrors
    `heading_canonicalization.base.CanonicalizationFailure` exactly,
    applied to educational object processors instead of
    canonicalizers."""

    processor_name: str
    reason: str
    exception_type: Optional[str] = None
    diagnostics: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.processor_name:
            raise ValueError("ProcessingFailure.processor_name must be non-empty.")
        if not self.reason:
            raise ValueError("ProcessingFailure.reason must be non-empty.")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


class EducationalObjectProcessor(ABC):
    """Abstract base class every concrete educational object processor
    implements. Deliberately minimal — mirrors
    `heading_canonicalization.base.HeadingCanonicalizer` /
    `heading_recognizers.base.HeadingRecognizer`: the framework
    (registry, pipeline) only ever depends on this interface, never on
    a concrete subclass, so a new processor (M5.2 and later — an
    EquationProcessor, FigureProcessor, TableProcessor, ...) can be
    added without any change here.

    Subclasses MUST set `name` as a class attribute and implement
    `process()`. `default_priority` and `supports()` have sensible
    defaults and rarely need overriding.
    """

    name: str = "base"
    #: Lower runs first when `ProcessingPipeline` orders processors by
    #: priority — identical convention to
    #: `HeadingCanonicalizer.default_priority` /
    #: `HeadingRecognizer.default_priority`. A processor may instead
    #: be reordered per-deployment via `ProcessorSettings.priority`
    #: without changing this class attribute.
    default_priority: int = 100

    @abstractmethod
    def process(self, context: ProcessingContext) -> Optional["ProcessingResult"]:
        """Pure, deterministic, cheap (or as cheap as the concrete
        object type allows). Returns a `ProcessingResult` when this
        processor has something to report for `context`; returns
        `None` when it has nothing to contribute despite `supports()`
        having matched — the processing analogue of
        `HeadingRecognizer.recognize()` returning `None`. Must never
        mutate `context` (it is frozen, so this would raise
        regardless) and must never raise for ordinary "nothing to do"
        input; raise only for a genuine processor bug
        (`safe_process()` below is the caller's safety net, not a
        substitute for handling expected non-applicability)."""
        raise NotImplementedError

    def supports(self, context: ProcessingContext) -> bool:
        """Cheap pre-filter the pipeline consults before calling
        `process()` at all (e.g. a processor that only handles
        `context.object_type == "equation"` skipping every other
        object type). Default: every processor supports every
        context; a processor with narrow applicability should
        override this rather than encode the check as an early-return
        inside `process()`, so the pipeline can record it as SKIPPED
        rather than a wasted NO_RESULT call. Mirrors
        `HeadingCanonicalizer.supports()` /
        `HeadingRecognizer.supports()`."""
        return True

    def safe_process(self, context: ProcessingContext) -> Optional["ProcessingResult"]:
        """Wraps `process()` so one misbehaving processor can't take a
        whole `ProcessingPipeline` run down — logs and raises
        `ProcessorExecutionError`, which `ProcessingPipeline` catches
        and records as a `ProcessingFailure`, exactly mirroring
        `HeadingCanonicalizer.safe_canonicalize()` /
        `HeadingRecognizer.safe_recognize()`'s own contract."""
        try:
            return self.process(context)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            logger.exception(
                "Processor '%s' raised on context (object_type=%r) — treating as failure.",
                self.name, context.object_type,
            )
            raise ProcessorExecutionError(self.name, str(exc)) from exc


__all__ = [
    "ProcessingContext",
    "ProcessingFailure",
    "EducationalObjectProcessor",
]
