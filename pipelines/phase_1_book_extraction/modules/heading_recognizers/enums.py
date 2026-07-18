"""
modules/heading_recognizers/enums.py — M4.2A: shared closed/open
vocabularies for the heading recognition framework.

Mirrors document_structure_tree/enums.py's own convention in this
project: str-backed Enums, JSON-serializable via `.value`, directly
comparable against the equivalent string. Unlike
document_structure_tree.enums.HeadingDetectionMethod (which records,
on an already-built DST node, WHICH broad technique produced it —
layout_analysis / typography / toc_matching / vlm_inference /
heuristic_merging), the enums here are internal to the recognition
framework itself: they describe HOW a candidate line/block was
classified by a specific recognizer, and how the pipeline should
behave while getting there. Nothing in this module talks to the DST
package directly — a future integration milestone maps
HeadingClassification values onto a HeadingDetectionMethod when a
recognized heading is handed off to document_structure_tree.builder.
"""
from __future__ import annotations

from enum import Enum


class HeadingClassification(str, Enum):
    """The kind of heading pattern a recognizer matched. Deliberately
    NOT a closed set — this is a compiler-internal vocabulary, exactly
    like HeadingDetectionMethod's own "..." in the frozen schema.
    M4.2A defines only the framework-level placeholder; concrete
    recognizers (M4.2B/C and later) each own exactly one of the
    "real" members below and are the only place that constructs a
    RecognitionResult carrying it. Adding a new member later (a new
    heading pattern family) is additive and never requires touching
    this framework's core (registry/factory/pipeline)."""

    NUMBERED = "numbered"
    HIERARCHICAL = "hierarchical"
    ROMAN_NUMERAL = "roman_numeral"
    ALPHABETIC = "alphabetic"
    CHAPTER_NUMBER = "chapter_number"
    CHAPTER_TITLE = "chapter_title"
    #: M4.2D: a bare language-specific structural keyword heading with
    #: no attached numbering (e.g. Hindi "सारांश", Sanskrit "सारांशः").
    #: Additive member only — no change to the framework core that
    #: consumes this enum (registry/factory/pipeline), per this class's
    #: own "adding a new member is additive" contract above.
    SECTION_KEYWORD = "section_keyword"
    UNCLASSIFIED = "unclassified"


class ConflictResolutionStrategy(str, Enum):
    """How RecognitionPipeline resolves two-or-more recognizers
    matching the same input. Closed set: the pipeline's conflict
    resolver (pipeline.py) has one code path per member, so adding a
    strategy is a framework change, not a data change."""

    HIGHEST_CONFIDENCE = "highest_confidence"
    PRIORITY_ORDER = "priority_order"
    FIRST_MATCH = "first_match"
    ALL_MATCHES = "all_matches"


class RecognizerState(str, Enum):
    """Lifecycle state a RecognizerRegistry tracks per registered
    recognizer. Distinct from RecognitionOutcome, which describes the
    result of a single recognize() call — this describes the
    recognizer itself, across calls."""

    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"


class RecognitionOutcome(str, Enum):
    """The result shape of one recognizer's attempt against one
    RecognitionContext. MATCHED means recognize() returned a
    RecognitionResult; NO_MATCH means it returned None (pattern
    doesn't apply — not "applies with low confidence", exactly the
    same True-None distinction modules/recognizers/base.py documents
    for the Stage D framework); FAILED means recognize() raised and
    safe_recognize() caught it; SKIPPED means the pipeline never
    called recognize() at all (recognizer disabled, or
    supports(context) returned False)."""

    MATCHED = "matched"
    NO_MATCH = "no_match"
    FAILED = "failed"
    SKIPPED = "skipped"


__all__ = [
    "HeadingClassification",
    "ConflictResolutionStrategy",
    "RecognizerState",
    "RecognitionOutcome",
]