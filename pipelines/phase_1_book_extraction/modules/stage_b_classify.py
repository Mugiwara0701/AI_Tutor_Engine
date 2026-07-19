"""
stage_b_classify.py — Stage B: Educational Block Classification.

Responsibility (and ONLY this responsibility): WHAT is the block?

Input:  Hierarchical Blocks (stage_a_geometry.Block)
Output: block_type, confidence — attached in place on each Block.

No VLM allowed. Pure deterministic classification. Ambiguous blocks remain
Ambiguous (never force a guess just to avoid the label).

Implemented behind `classify(block)` per the frozen spec, so a future ML
classifier can replace the heuristics below without any caller
(stage_c_priority, stage_d_extraction, pipeline.py) changing.

M4.1C improvements:
  - Improved callout-label classification (Warning, Note, Box sub-types)
  - Better Exercise/Summary detection
  - Reduced Ambiguous classifications via deterministic fallback cues
  - Stable deterministic classification ordering
  - Duplicate classification suppression
  - Improved parent/child block-type propagation
  - Enhanced metadata propagation from Stage A quality passes

M4.2C: heading-topic blocks are additionally run through the shared
modules/heading_recognizers RecognitionPipeline; a winning match is
recorded as `grouping_meta["heading_recognition"]` (recognizer name,
classification, confidence, level, number, diagnostics). Purely additive
-- `block_type`/`confidence` for heading-topic blocks are unchanged from
M4.1. Configurable via config.ENABLE_HEADING_RECOGNITION.

M4.3C: immediately after a successful M4.2 recognition, that same
heading is run through the shared modules/heading_canonicalization
CanonicalizationPipeline (M4.3A framework + M4.3B number-system
canonicalizers); the result is recorded as a second, new
`grouping_meta["heading_canonicalization"]` key (canonical type, canonical
number, numbering system, validation status, diagnostics) alongside --
never replacing -- the M4.2C `heading_recognition` metadata. Also purely
additive; also never touches `block_type`/`confidence`. Configurable via
config.ENABLE_HEADING_CANONICALIZATION. A canonicalization failure is
isolated exactly like a recognition failure: recognition metadata (and
`block_type`/`confidence`) remain intact, and the failure is only ever
logged/diagnosed, never propagated.
"""
import re
import logging
from typing import Dict, List, Optional, Set, Tuple

import config
from modules.stage_a_geometry import Block
from modules.heading_recognizers import RecognitionPipeline, default_registry
from modules.heading_recognizers.base import RecognitionContext, RecognitionResult
from modules.heading_recognizers.exceptions import HeadingRecognitionError
from modules.heading_canonicalization import CanonicalHeading, CanonicalizationPipeline
from modules.heading_canonicalization import default_registry as canonicalization_default_registry
from modules.heading_canonicalization.base import CanonicalizationContext
from modules.heading_canonicalization.exceptions import HeadingCanonicalizationError
from modules.heading_canonicalization.structural_validation import PRECEDING_LEVEL_METADATA_KEY

logger = logging.getLogger("ncert_pipeline.stage_b")

# M4.2C: integration point for modules/heading_recognizers (M4.2A framework
# + M4.2B generic recognizers) into the production heading detection flow.
# One RecognitionPipeline built once, over the framework's own shared
# default_registry/default_config, and reused for every heading-topic block
# classified in this process -- avoids rebuilding the registry/recognizer
# set per block (performance) while still leaving the framework's own
# registry/config as the single source of truth for which recognizers run
# and how they're prioritized/thresholded (configuration requirement: this
# file introduces no new hard-coded thresholds of its own).
_HEADING_RECOGNITION_PIPELINE = RecognitionPipeline(default_registry)

# M4.3C: integration point for modules/heading_canonicalization (M4.3A
# framework + M4.3B number-system canonicalizers) into the production
# heading extraction flow, one stage downstream of
# _HEADING_RECOGNITION_PIPELINE above. Built once over the framework's own
# shared canonicalization_default_registry/default_config, and reused for
# every recognized heading in this process, for exactly the same reasons
# _HEADING_RECOGNITION_PIPELINE is a module-level singleton: avoid
# rebuilding the registry/canonicalizer set per heading (performance), and
# leave the framework's own registry/config as the single source of truth
# for which canonicalizers run (this file introduces no new hard-coded
# canonicalization logic or a second registry of its own).
_HEADING_CANONICALIZATION_PIPELINE = CanonicalizationPipeline(canonicalization_default_registry)

# M4.3D: whether the shared canonicalization registry's "structural_validator"
# canonicalizer (modules.heading_canonicalization.structural_validation.
# StructuralValidator) is enabled, checked once at import time -- exactly
# like every other module-level singleton above, and using the registry's
# own existing enable()/disable() lifecycle API (config.py requirement #6:
# "do not introduce a new configuration mechanism"). Disabling this only
# stops that one canonicalizer from running -- NumberingSystemDetector and
# the numeral canonicalizers (M4.3B) are unaffected either way, since
# structural validation runs strictly after them in the same pipeline.
if not config.ENABLE_STRUCTURAL_VALIDATION:
    canonicalization_default_registry.disable("structural_validator")

# Possible block types, verbatim from the frozen architecture spec.
BLOCK_TYPES = [
    "Heading", "Definition", "Law", "Formula Box", "Worked Example", "Exercise",
    "Activity", "Summary", "Table", "Figure", "Diagram", "Flowchart",
    "Programming Syntax", "Accounting Format", "Reference", "Footer", "Header",
    "Decision Tree", "Ambiguous",
]

_EXAMPLE_LABEL_RE = re.compile(r"^\s*(example|illustration|solved example)\b", re.I)
_ACTIVITY_LABEL_RE = re.compile(r"^\s*(activity|think|observe|try|discuss|experiment)\b", re.I)
_BOX_LABEL_RE = re.compile(r"^\s*(did you know|important|case study|box)\b", re.I)
_NOTE_LABEL_RE = re.compile(r"^\s*(note|n\.b\.|nb|remember)\b", re.I)
_WARNING_LABEL_RE = re.compile(r"^\s*(warning|caution|danger|attention)\b", re.I)
_EXERCISE_HINT_RE = re.compile(r"^\s*(exercise|questions?|homework|problems?|practice)\b", re.I)
_LAW_HINT_RE = re.compile(r"\b(law of|principle of|theorem|postulate|axiom)\b", re.I)
_SUMMARY_HINT_RE = re.compile(r"^\s*(summary|conclusion|key points?|recap|things to remember|in a nutshell)\b", re.I)
_REFERENCE_HINT_RE = re.compile(r"^\s*(references?|bibliography|further reading|suggested reading)\b", re.I)
_FLOWCHART_HINT_RE = re.compile(r"\b(flow\s*chart|flowchart)\b", re.I)
_DECISION_TREE_HINT_RE = re.compile(r"\b(decision tree)\b", re.I)
_PROGRAMMING_HINT_RE = re.compile(r"\b(def |print\(|import |for\s+\w+\s+in\s+|#include|void\s+main)\b")
_ACCOUNTING_HINT_RE = re.compile(r"\b(dr\.?|cr\.?|ledger|journal entry|balance sheet|trial balance)\b", re.I)

# M4.1C: Extended callout patterns for Warning/Note/Tip/Important/Remember
_TIP_LABEL_RE = re.compile(r"^\s*(tip|hint|clue)\b", re.I)
_IMPORTANT_LABEL_RE = re.compile(r"^\s*(important)\b", re.I)

# M4.1C: Definition fallback cues in body text
_DEFINITION_BODY_RE = re.compile(
    r"\b(is defined as|are defined as|is called|is known as|is referred to as|denotes)\b", re.I
)

# A block with >=2 equation-line children whose first line pattern looks
# like a plain generalized formula (letters only, no bare-numeric RHS) and
# is immediately preceded (in the source text) by an "Example"/"Illustration"
# label is a Worked Example; otherwise a bare equation cluster with no such
# preceding label is a standalone Formula Box.
_VARIABLE_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s+\-*/^().]*=[A-Za-z\s+\-*/^().]+$")
_NUMERIC_SUBSTITUTION_RE = re.compile(r"^[A-Za-z]?\s*=?\s*[\d.\s+\-*/^().\u00d7xX\u00f7]+$")


def _classify_equation_cluster(block: Block, preceding_text: str) -> Tuple[str, float]:
    n_lines = len(block.children) or 1
    if _EXAMPLE_LABEL_RE.search(preceding_text or ""):
        return "Worked Example", 0.9 if n_lines >= 2 else 0.6
    if n_lines == 1:
        text = (block.children[0].grouping_meta or {}).get("raw_text", "")
        stripped = text.strip()
        if _VARIABLE_ONLY_RE.match(stripped):
            return "Formula Box", 0.7
        if _NUMERIC_SUBSTITUTION_RE.match(stripped):
            return "Worked Example", 0.5
        return "Formula Box", 0.5
    has_numeric = any(_NUMERIC_SUBSTITUTION_RE.match(
        (c.grouping_meta or {}).get("raw_text", "").strip()) for c in block.children)
    if has_numeric:
        return "Worked Example", 0.65
    return "Formula Box", 0.55


def _classify_callout_label(block: Block) -> Tuple[str, float]:
    """M4.1C improved: better Warning/Note/Box sub-type classification.
    Uses callout_type_hint from M4.1B layout quality passes when available,
    and extended regex patterns for better coverage."""
    label = (block.grouping_meta or {}).get("label_line", "")
    meta = block.grouping_meta or {}

    # M4.1C: Use callout_type_hint from layout quality passes (M4.1B)
    type_hint = meta.get("callout_type_hint", "")

    if _EXAMPLE_LABEL_RE.match(label):
        return "Worked Example", 0.85
    if _ACTIVITY_LABEL_RE.match(label):
        return "Activity", 0.85

    # M4.1C: Improved Warning classification
    if _WARNING_LABEL_RE.match(label) or type_hint == "warning":
        if _LAW_HINT_RE.search(label):
            return "Law", 0.6
        return "Activity", 0.7

    # M4.1C: Improved Note classification
    if _NOTE_LABEL_RE.match(label) or type_hint == "note":
        return "Activity", 0.65

    # M4.1C: Tip / Hint / Clue
    if _TIP_LABEL_RE.match(label):
        return "Activity", 0.7

    # M4.1C: "Important"
    if _IMPORTANT_LABEL_RE.match(label):
        return "Activity", 0.7

    if _BOX_LABEL_RE.match(label) or type_hint == "box":
        return "Activity", 0.65

    # M4.1C: Exercise detection in callout labels
    if _EXERCISE_HINT_RE.match(label):
        return "Exercise", 0.7

    # M4.1C: Summary detection in callout labels
    if _SUMMARY_HINT_RE.match(label):
        return "Summary", 0.7

    # M4.1C: Reference detection in callout labels
    if _REFERENCE_HINT_RE.match(label):
        return "Reference", 0.7

    # M4.1C: Law detection in body text of unmatched callouts
    body_text = " ".join(l.text for l in block.lines)
    if _LAW_HINT_RE.search(body_text):
        return "Law", 0.55

    return "Ambiguous", 0.0


def _classify_table_like(block: Block) -> Tuple[str, float]:
    caption = (block.grouping_meta or {}).get("caption", "") or ""
    body_text = " ".join(l.text for l in block.lines)
    combined = f"{caption} {body_text}"
    if _PROGRAMMING_HINT_RE.search(body_text):
        return "Programming Syntax", 0.6
    if _ACCOUNTING_HINT_RE.search(combined):
        return "Accounting Format", 0.6
    return "Table", 0.7


def _classify_diagram_like(block: Block) -> Tuple[str, float]:
    caption = (block.grouping_meta or {}).get("caption", "") or ""
    if _FLOWCHART_HINT_RE.search(caption):
        return "Flowchart", 0.65
    if _DECISION_TREE_HINT_RE.search(caption):
        return "Decision Tree", 0.65
    return "Diagram", 0.6


def _classify_body_text_fallback(block: Block) -> Tuple[str, float]:
    """M4.1C: Extended body-text fallback for blocks that didn't match
    any anchor-based rule. Reduces Ambiguous classifications."""
    body_text = " ".join(l.text for l in block.lines)
    if not body_text.strip():
        return "Ambiguous", 0.0

    if _SUMMARY_HINT_RE.search(body_text):
        return "Summary", 0.6
    if _REFERENCE_HINT_RE.search(body_text):
        return "Reference", 0.6
    if _LAW_HINT_RE.search(body_text):
        return "Law", 0.55
    if _EXERCISE_HINT_RE.search(body_text):
        return "Exercise", 0.55

    # M4.1C: Definition cues in body text
    if _DEFINITION_BODY_RE.search(body_text):
        return "Definition", 0.45

    return "Ambiguous", 0.0


# ---------------------------------------------------------------------------
# M4.2C: heading recognition framework integration
# ---------------------------------------------------------------------------
#
# Stage A's `_topic_heading_blocks` already wraps each pdf_parser-detected
# TopicRecord as a "heading-topic" Block (see that function's own docstring
# for why headings are detected upstream, not re-derived here) -- so the
# question "is this block a Heading" was already answered deterministically
# and reliably before Stage B ever sees it. What Stage B previously never
# did is ask the *finer-grained* question modules/heading_recognizers (M4.2A
# framework + M4.2B generic recognizers) exists to answer: which heading
# pattern (numbered / hierarchical / roman numeral / alphabetic / chapter
# number / chapter title / ...) does this specific heading's text actually
# match, at what confidence, with what diagnostics. That framework becomes
# the authoritative source for THAT question as of M4.2C; it does not
# override Stage A's own "is this a Heading" determination (block_type and
# confidence for heading-topic blocks are unchanged from M4.1 -- see
# classify() below), only enriches it.


def _heading_recognition_text(meta: Dict) -> str:
    """Picks the candidate text to feed a heading recognizer from a
    heading-topic Block's grouping_meta.

    The M4.2B generic recognizers each expect ONE specific shape of bare
    candidate text -- NumberedHeadingRecognizer/HierarchicalHeadingRecognizer/
    RomanNumeralHeadingRecognizer/AlphabeticHeadingRecognizer all require
    the *entire* text to be nothing but the numbering token itself (e.g.
    "1.1", not "1.1 Motion" -- see their own `recognize()` docstrings),
    while ChapterTitleRecognizer requires the opposite: title-cased prose
    text with no leading digit at all. Concatenating TopicRecord.numbering
    and TopicRecord.title together would make every one of those checks
    fail simultaneously. So: prefer the bare numbering token when
    pdf_parser found one (the common case -- most NCERT headings are
    numbered), falling back to the bare title text only when there is no
    numbering (pdf_parser's own `detect_unnumbered_headings` path), which
    is exactly the input ChapterTitleRecognizer (and, for a title that
    itself starts with a keyword, ChapterNumberRecognizer) is built for.
    """
    # M4.3E hardening fix: grouping_meta is produced by an upstream stage
    # this framework doesn't control, so `numbering`/`title` are only
    # EXPECTED to be `Optional[str]` -- not guaranteed. Calling `.strip()`
    # unconditionally after `or ""` still raised AttributeError for any
    # other truthy non-string value (e.g. a stray int/list from malformed
    # metadata), which would crash this whole call and everything after it
    # in classify_blocks()'s per-page loop -- exactly the "unexpected
    # metadata"/"malformed context" case this framework's own contract
    # ("never raises") already promised to handle. Coercing a non-string
    # value to "" (i.e. treating it as absent) rather than raising keeps
    # that promise; well-formed str/None input is completely unaffected.
    numbering = meta.get("numbering")
    numbering = numbering.strip() if isinstance(numbering, str) else ""
    if numbering:
        return numbering
    title = meta.get("title")
    return title.strip() if isinstance(title, str) else ""


def _recognize_heading(
    block: Block, preceding_heading_level: Optional[int]
) -> Optional[Tuple[RecognitionContext, RecognitionResult]]:
    """Runs the shared M4.2A/B RecognitionPipeline against one heading-topic
    Block. Returns the (RecognitionContext, winning RecognitionResult) pair
    on a match, or None when nothing matched (or the framework is disabled
    via config) -- the context is returned alongside the result (M4.3C)
    purely so a subsequent canonicalization step can reuse the exact same
    RecognitionContext.text that was actually recognized, rather than
    recomputing `_heading_recognition_text(meta)` a second time (M4.3C
    performance requirement: avoid redundant conversions). Never raises --
    RecognitionPipeline.run() already turns an individual recognizer's
    exception into a FailureResult internally (HeadingRecognizer.
    safe_recognize()), and this wraps the run() call itself in the
    framework's own exception hierarchy as a second line of defense, so a
    heading recognition problem can never abort Stage B / the extraction
    pipeline (M4.2C error-handling requirement)."""
    if not config.ENABLE_HEADING_RECOGNITION:
        return None

    meta = block.grouping_meta or {}
    text = _heading_recognition_text(meta)
    if not text:
        return None

    context = RecognitionContext(
        text=text,
        page=block.page,
        preceding_heading_level=preceding_heading_level,
        metadata={"topic_id": meta.get("topic_id"), "numbering": meta.get("numbering"),
                  "stage_a_level": meta.get("level")},
    )
    try:
        result = _HEADING_RECOGNITION_PIPELINE.run(context)
    except HeadingRecognitionError:
        logger.exception(
            "Heading recognition pipeline failed for topic_id=%s on page %s -- "
            "keeping Stage A's Heading classification, no recognition metadata attached.",
            meta.get("topic_id"), block.page,
        )
        return None
    if result.winner is None:
        return None
    return context, result.winner


def _attach_heading_recognition_metadata(block: Block, result: RecognitionResult) -> None:
    """Records the winning recognizer's outcome on the block for downstream
    consumers (e.g. a later phase mapping this onto
    document_structure_tree's HeadingDetectionMethod) without touching any
    existing grouping_meta key -- reuses the framework's own immutable
    RecognitionResult fields rather than inventing a parallel shape."""
    block.grouping_meta["heading_recognition"] = {
        "recognizer_name": result.recognizer_name,
        "classification": result.classification.value,
        "confidence": result.confidence,
        "level": result.level,
        "number": result.number,
        "diagnostics": result.diagnostics,
    }


# ---------------------------------------------------------------------------
# M4.3C: heading canonicalization framework integration
# ---------------------------------------------------------------------------
#
# One stage further downstream of M4.2C's own integration immediately
# above: once a heading-topic Block has a winning M4.2 RecognitionResult,
# M4.3 (M4.3A framework + M4.3B number-system canonicalizers) exists to
# answer the next question -- what is this heading's stable, canonical
# numbering, independent of whether it was written "III", "3", or "३".
# Exactly like M4.2C, this is additive: it never changes block_type,
# confidence, or the `heading_recognition` metadata M4.2C already attaches
# (M4.3C requirement #2, Preserve Existing Behaviour) -- it only attaches a
# second, new `heading_canonicalization` metadata key alongside it.


def _canonicalize_heading(
    context: RecognitionContext,
    result: RecognitionResult,
    *,
    preceding_canonical_number: Optional[str] = None,
    preceding_numbering_system: Optional[str] = None,
    preceding_canonical_level: Optional[int] = None,
) -> Optional[CanonicalHeading]:
    """Runs the shared M4.3A/B CanonicalizationPipeline against one winning
    M4.2 RecognitionResult (and the RecognitionContext that produced it),
    via the framework's own from_recognition() adapter
    (modules.heading_canonicalization.models.CanonicalHeading.
    from_recognition). Returns the resulting CanonicalHeading, or None
    when canonicalization is disabled via config, or when
    from_recognition()/the pipeline run cannot proceed at all. Never
    raises -- CanonicalizationPipeline.run() already turns an individual
    canonicalizer's exception into a FAILED AttemptRecord internally
    (HeadingCanonicalizer.safe_canonicalize()), and this wraps the
    from_recognition() + run() calls in the framework's own exception
    hierarchy as a second line of defense, so a canonicalization problem
    can never abort Stage B / the extraction pipeline (M4.3C error-
    isolation requirement) -- the `heading_recognition` metadata
    `_attach_heading_recognition_metadata` already attached is completely
    unaffected either way, since canonicalization only ever runs after
    that metadata has already been attached (see classify() below)."""
    if not config.ENABLE_HEADING_CANONICALIZATION:
        return None

    # M4.3D: pass the immediately preceding heading's own canonicalization
    # state along -- CanonicalizationContext.preceding_canonical_number /
    # preceding_numbering_system are M4.3A framework fields reserved for
    # exactly this ("lets a future canonicalizer ... reason about numbering
    # continuity"); preceding level has no dedicated field (that dataclass's
    # field set is frozen), so it travels in the existing, explicitly opaque
    # `metadata` mapping instead -- see structural_validation.
    # PRECEDING_LEVEL_METADATA_KEY. None of this affects M4.3B's own
    # canonicalizers, which never read these fields.
    canonicalization_context = CanonicalizationContext(
        preceding_canonical_number=preceding_canonical_number,
        preceding_numbering_system=preceding_numbering_system,
        metadata={PRECEDING_LEVEL_METADATA_KEY: preceding_canonical_level},
    )

    try:
        heading = CanonicalHeading.from_recognition(context, result)
        pipeline_result = _HEADING_CANONICALIZATION_PIPELINE.run(heading, canonicalization_context)
    except HeadingCanonicalizationError:
        logger.exception(
            "Heading canonicalization pipeline failed for recognized heading "
            "%r (classification=%s) -- keeping M4.2 recognition metadata, no "
            "canonicalization metadata attached.",
            context.text, result.classification.value,
        )
        return None
    return pipeline_result.output_heading


def _attach_heading_canonicalization_metadata(block: Block, heading: CanonicalHeading) -> None:
    """Records the canonicalization pipeline's output on the block for
    downstream consumers, as a second metadata key alongside (never
    replacing or altering) the `heading_recognition` metadata
    `_attach_heading_recognition_metadata` already attached -- reuses the
    framework's own immutable CanonicalHeading fields rather than
    inventing a parallel shape."""
    block.grouping_meta["heading_canonicalization"] = {
        "canonical_type": heading.canonical_type.value if heading.canonical_type is not None else None,
        "canonical_number": heading.canonical_number,
        "numbering_system": heading.numbering_system.value,
        "validation_status": heading.validation_status.value,
        "diagnostics": heading.diagnostics,
    }


def classify(block: Block, preceding_text: str = "", in_example: bool = False,
             preceding_heading_level: Optional[int] = None,
             preceding_canonical_number: Optional[str] = None,
             preceding_numbering_system: Optional[str] = None,
             preceding_canonical_level: Optional[int] = None) -> Tuple[str, float]:
    """Pure deterministic classification."""
    anchor = (block.grouping_meta or {}).get("anchor", "")

    if anchor == "equation-cluster":
        if in_example:
            return "Worked Example", 0.85
        return _classify_equation_cluster(block, preceding_text)
    if anchor == "callout-label":
        label = (block.grouping_meta or {}).get("label_line", "")
        if _EXERCISE_HINT_RE.match(label):
            return "Exercise", 0.7
        return _classify_callout_label(block)
    if anchor == "heading-topic":
        # M4.2C: run the heading recognition framework for its diagnostic
        # metadata; block_type/confidence stay exactly what M4.1 already
        # returned here (Stage A's TopicRecord detection remains
        # authoritative for "is this a Heading" -- see module docstring
        # above), so this is additive and cannot regress existing callers.
        recognition = _recognize_heading(block, preceding_heading_level)
        if recognition is not None:
            recognition_context, winner = recognition
            _attach_heading_recognition_metadata(block, winner)
            # M4.3C: run the canonicalization framework immediately after a
            # successful recognition, over that same (context, winner) pair
            # -- purely additive, exactly like the recognition step above:
            # block_type/confidence are already decided by this point and
            # are never touched again.
            canonical_heading = _canonicalize_heading(
                recognition_context, winner,
                preceding_canonical_number=preceding_canonical_number,
                preceding_numbering_system=preceding_numbering_system,
                preceding_canonical_level=preceding_canonical_level,
            )
            if canonical_heading is not None:
                _attach_heading_canonicalization_metadata(block, canonical_heading)
        return "Heading", 1.0
    if anchor == "definition-candidate":
        meta = block.grouping_meta or {}
        if meta.get("grouped_definitions"):
            return "Definition", 0.8
        return "Definition", 0.75
    if anchor == "table":
        return _classify_table_like(block)
    if anchor in ("figure", "diagram"):
        if anchor == "diagram":
            return _classify_diagram_like(block)
        return "Figure", 0.7

    # M4.1C: Improved body-text fallback
    return _classify_body_text_fallback(block)


# ---------------------------------------------------------------------------
# M4.1C: Duplicate classification suppression
# ---------------------------------------------------------------------------

def _suppress_duplicate_classifications(blocks: List[Block]) -> List[Block]:
    """M4.1C: When two blocks on the same page have the same block_type
    AND share the same label_line, keep the one with higher confidence."""
    by_page: Dict[int, List[Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)

    suppressed_ids: Set[str] = set()
    for page, page_blocks in by_page.items():
        seen: Dict[Tuple[str, str], Block] = {}
        for b in sorted(page_blocks, key=lambda x: x.bbox[1]):
            if b.block_type == "Ambiguous" or b.block_type == "Heading":
                continue
            label = (b.grouping_meta or {}).get("label_line", "")
            if not label:
                continue
            key = (b.block_type, label)
            if key in seen:
                existing = seen[key]
                if b.confidence > existing.confidence:
                    suppressed_ids.add(existing.block_id)
                    seen[key] = b
                else:
                    suppressed_ids.add(b.block_id)
            else:
                seen[key] = b

    if suppressed_ids:
        logger.debug("Stage B duplicate suppression: removed %d block(s).", len(suppressed_ids))

    return [b for b in blocks if b.block_id not in suppressed_ids]


# ---------------------------------------------------------------------------
# M4.1C: Parent/child block_type propagation
# ---------------------------------------------------------------------------

def _propagate_parent_child_types(blocks: List[Block]) -> None:
    """M4.1C: Improve parent/child classification consistency."""
    for b in blocks:
        if not b.children:
            continue
        parent_type = b.block_type
        if not parent_type or parent_type == "Ambiguous":
            continue

        for child in b.children:
            child_type = child.block_type or "Ambiguous"

            if child_type in ("Heading", "Definition"):
                continue

            if child_type == "Ambiguous":
                child.block_type = parent_type
                child.confidence = max(child.confidence, b.confidence * 0.8)

            if parent_type in ("Worked Example", "Activity", "Exercise"):
                if child_type not in ("Heading", "Definition", "Figure",
                                      "Table", "Diagram"):
                    child.block_type = parent_type
                    child.confidence = max(child.confidence, b.confidence * 0.9)


# ---------------------------------------------------------------------------
# M4.1C: Metadata propagation from M4.1B
# ---------------------------------------------------------------------------

def _propagate_metadata(blocks: List[Block]) -> None:
    """M4.1C: Enhance classification using metadata from M4.1B quality
    passes."""
    for b in blocks:
        meta = b.grouping_meta or {}

        if meta.get("has_border") and b.block_type == "Activity":
            b.confidence = min(1.0, b.confidence + 0.1)

        if meta.get("grouped_definitions") and b.block_type == "Definition":
            b.confidence = min(1.0, b.confidence + 0.05)

        if meta.get("merged_continuation") and b.block_type in ("Worked Example", "Formula Box"):
            b.confidence = min(1.0, b.confidence + 0.05)


def classify_blocks(blocks: List[Block]) -> List[Block]:
    """Classifies every block in place (mutates + returns the same list).

    M4.1C improvements:
    - Tracks in_example flag per page in reading order
    - Suppresses duplicate classifications
    - Propagates parent/child block types
    - Propagates M4.1B layout quality metadata
    - Ensures stable deterministic ordering"""
    by_page: Dict[int, List[Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page, []).append(b)
    for page_blocks in by_page.values():
        page_blocks.sort(key=lambda b: b.bbox[1])
        prev_text = ""
        in_example = False
        # M4.2C: the most recently classified heading's own Stage A level
        # (grouping_meta["level"], NOT the recognizer's guess -- see
        # _recognize_heading's docstring) -- fed to modules.heading_recognizers
        # as RecognitionContext.preceding_heading_level so recognizers that
        # reason about hierarchy continuity (e.g. ChapterTitleRecognizer) have
        # it, without Stage B trusting an unverified recognizer level for its
        # own bookkeeping.
        preceding_heading_level: Optional[int] = None
        # M4.3D: the most recently canonicalized heading's own
        # canonical_number/numbering_system/level (from the
        # `heading_canonicalization` metadata M4.3C already attaches below),
        # fed to modules.heading_canonicalization as
        # CanonicalizationContext.preceding_canonical_number/
        # preceding_numbering_system and the structural_validation.
        # PRECEDING_LEVEL_METADATA_KEY metadata entry, so StructuralValidator
        # can reason about numbering/hierarchy continuity across headings on
        # the same page -- same "reset per page" scoping
        # `preceding_heading_level` above already uses, for consistency.
        preceding_canonical_number: Optional[str] = None
        preceding_numbering_system: Optional[str] = None
        preceding_canonical_level: Optional[int] = None
        for b in page_blocks:
            block_type, confidence = classify(
                b, preceding_text=prev_text, in_example=in_example,
                preceding_heading_level=preceding_heading_level,
                preceding_canonical_number=preceding_canonical_number,
                preceding_numbering_system=preceding_numbering_system,
                preceding_canonical_level=preceding_canonical_level,
            )
            b.block_type = block_type
            b.confidence = confidence
            prev_text = " ".join(l.text for l in b.lines)[:200]

            anchor = (b.grouping_meta or {}).get("anchor", "")
            if anchor == "callout-label":
                label = (b.grouping_meta or {}).get("label_line", "")
                if _EXAMPLE_LABEL_RE.match(label):
                    in_example = True
                elif block_type != "Ambiguous":
                    in_example = False
            elif anchor == "heading-topic":
                in_example = False
                level = (b.grouping_meta or {}).get("level")
                if isinstance(level, int):
                    preceding_heading_level = level

                canonical_meta = (b.grouping_meta or {}).get("heading_canonicalization")
                if canonical_meta is not None:
                    if canonical_meta.get("canonical_number") is not None:
                        preceding_canonical_number = canonical_meta["canonical_number"]
                        preceding_numbering_system = canonical_meta["numbering_system"]
                    # M4.3D: deliberately the recognizer's OWN level
                    # (heading_recognition["level"], == this same heading's
                    # CanonicalHeading.level) rather than Stage A's
                    # grouping_meta["level"] used for `preceding_heading_level`
                    # above -- StructuralValidator compares
                    # `CanonicalHeading.level` values on both sides of a
                    # transition, so the preceding value fed into that same
                    # comparison must come from that same field, not a
                    # different (Stage A) notion of level.
                    recognized_level = (b.grouping_meta.get("heading_recognition") or {}).get("level")
                    if isinstance(recognized_level, int):
                        preceding_canonical_level = recognized_level

    # M4.1C: Post-classification quality passes
    _propagate_parent_child_types(blocks)
    _propagate_metadata(blocks)
    blocks = _suppress_duplicate_classifications(blocks)

    # M4.1C: Ensure stable deterministic ordering
    blocks.sort(key=lambda b: (b.page, b.bbox[1]))

    logger.info("Stage B: classified %d block(s).", len(blocks))
    return blocks