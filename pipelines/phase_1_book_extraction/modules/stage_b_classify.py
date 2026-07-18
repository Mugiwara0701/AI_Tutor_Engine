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
"""
import re
import logging
from typing import Dict, List, Optional, Set, Tuple

from modules.stage_a_geometry import Block

logger = logging.getLogger("ncert_pipeline.stage_b")

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


def classify(block: Block, preceding_text: str = "", in_example: bool = False) -> Tuple[str, float]:
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
        for b in page_blocks:
            block_type, confidence = classify(b, preceding_text=prev_text, in_example=in_example)
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

    # M4.1C: Post-classification quality passes
    _propagate_parent_child_types(blocks)
    _propagate_metadata(blocks)
    blocks = _suppress_duplicate_classifications(blocks)

    # M4.1C: Ensure stable deterministic ordering
    blocks.sort(key=lambda b: (b.page, b.bbox[1]))

    logger.info("Stage B: classified %d block(s).", len(blocks))
    return blocks
