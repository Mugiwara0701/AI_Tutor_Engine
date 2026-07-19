"""
modules/educational_object_framework/enums.py — M5.1: shared
closed/open vocabularies for the educational object processing
framework.

Mirrors modules/heading_canonicalization/enums.py's own convention in
this project: str-backed Enums, JSON-serializable via `.value`,
directly comparable against the equivalent string. Nothing in this
module decides HOW an educational object is processed (that is a
concrete processor's job, in M5.2) — these are the shared
vocabularies the framework's models, registry, and pipeline contracts
need to exist at all.

Deliberately absent: any enum naming a specific educational object
kind (equation, figure, table, diagram, example, activity,
definition, glossary, ...). Per the M5.1 spec ("the context should be
generic — do not hard-code any educational object type"), that
vocabulary belongs to M5.2's concrete processors, not to this
framework.
"""
from __future__ import annotations

from enum import Enum


class ProcessorState(str, Enum):
    """Lifecycle state a `ProcessorRegistry` tracks per registered
    processor. Mirrors
    `heading_canonicalization.enums.CanonicalizerState` exactly,
    applied to educational object processors instead of
    canonicalizers."""

    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"


class ProcessingOutcome(str, Enum):
    """The result shape of one processor's attempt against one
    `ProcessingContext` within a pipeline run. Mirrors
    `heading_canonicalization.enums.CanonicalizationOutcome`'s
    four-way split, adapted to the framework's aggregate-rather-than-
    chain execution model (see `pipeline.py`):

    EXECUTED — process() returned a ProcessingResult.
    NO_RESULT — process() returned None (this processor's capability
        check (`supports()`) matched, but it had nothing to
        contribute for this particular context — the processing
        analogue of RecognitionOutcome.NO_MATCH).
    FAILED — process() raised and safe_process() caught it.
    SKIPPED — the pipeline never called process() at all (processor
        disabled, or supports() returned False).
    """

    EXECUTED = "executed"
    NO_RESULT = "no_result"
    FAILED = "failed"
    SKIPPED = "skipped"


class DiagnosticSeverity(str, Enum):
    """Severity of a single free-form diagnostic entry recorded by a
    processor or the pipeline itself. Mirrors
    `heading_canonicalization.enums.ValidationSeverity` exactly —
    kept as a small, closed vocabulary so future validation helpers
    (M5.1 scope: "validation helpers", not validation *rules*) have a
    shared severity type to build on without inventing their own."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


__all__ = [
    "ProcessorState",
    "ProcessingOutcome",
    "DiagnosticSeverity",
]
