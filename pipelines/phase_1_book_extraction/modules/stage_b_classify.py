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
"""
import re
import logging
from typing import List, Tuple

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
_NOTE_LABEL_RE = re.compile(r"^\s*(note|remember)\b", re.I)
_WARNING_LABEL_RE = re.compile(r"^\s*(warning|caution)\b", re.I)
_EXERCISE_HINT_RE = re.compile(r"^\s*(exercise|questions?|homework)\b", re.I)
_LAW_HINT_RE = re.compile(r"\b(law of|principle of|theorem|postulate)\b", re.I)
_SUMMARY_HINT_RE = re.compile(r"^\s*(summary|conclusion|key points?|recap)\b", re.I)
_REFERENCE_HINT_RE = re.compile(r"^\s*(references?|bibliography|further reading)\b", re.I)
_FLOWCHART_HINT_RE = re.compile(r"\b(flow\s*chart|flowchart)\b", re.I)
_DECISION_TREE_HINT_RE = re.compile(r"\b(decision tree)\b", re.I)
_PROGRAMMING_HINT_RE = re.compile(r"\b(def |print\(|import |for\s+\w+\s+in\s+|#include|void\s+main)\b")
_ACCOUNTING_HINT_RE = re.compile(r"\b(dr\.?|cr\.?|ledger|journal entry|balance sheet|trial balance)\b", re.I)

# A block with >=2 equation-line children whose first line pattern looks
# like a plain generalized formula (letters only, no bare-numeric RHS) and
# is immediately preceded (in the source text) by an "Example"/"Illustration"
# label is a Worked Example; otherwise a bare equation cluster with no such
# preceding label is a standalone Formula Box.
_VARIABLE_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s+\-*/^().]*=[A-Za-z\s+\-*/^().]+$")
_NUMERIC_SUBSTITUTION_RE = re.compile(r"^[A-Za-z]?\s*=?\s*[\d.\s+\-*/^().×xX÷]+$")


def _classify_equation_cluster(block: Block, preceding_text: str) -> Tuple[str, float]:
    n_lines = len(block.children) or 1
    if _EXAMPLE_LABEL_RE.search(preceding_text or ""):
        return "Worked Example", 0.9 if n_lines >= 2 else 0.6
    # A single, purely variable-form equation with no numeric substitution
    # following it reads as a standalone reusable formula.
    if n_lines == 1:
        text = (block.children[0].grouping_meta or {}).get("raw_text", "")
        stripped = text.strip()
        if _VARIABLE_ONLY_RE.match(stripped):
            return "Formula Box", 0.7
        if _NUMERIC_SUBSTITUTION_RE.match(stripped):
            # A line like "Moles of C2H6O2 = 20 g / 62 g mol-1 = 0.322 mol"
            # is an arithmetic step with real numbers plugged in, not a
            # reusable formula -- this is true regardless of whether an
            # "Example" label happens to be the immediately preceding
            # block. Stage A sometimes splits a worked example's
            # derivation into several separate single-line equation
            # clusters (each with its own vertical gap), which used to
            # make every one of those steps after the first fall through
            # to the unconditional "Formula Box" default below even
            # though _NUMERIC_SUBSTITUTION_RE exists specifically to
            # catch this shape (it was already used in the multi-line
            # branch further down, just never reached from here).
            return "Worked Example", 0.5
        return "Formula Box", 0.5
    # Multiple lines with no preceding "Example" label but a mix of
    # variable-form + numeric-substitution lines is still most likely a
    # worked example (many NCERT worked examples don't repeat the word
    # "Example" right before every one, e.g. mid-derivation examples).
    has_numeric = any(_NUMERIC_SUBSTITUTION_RE.match(
        (c.grouping_meta or {}).get("raw_text", "").strip()) for c in block.children)
    if has_numeric:
        return "Worked Example", 0.65
    return "Formula Box", 0.55


def _classify_callout_label(block: Block) -> Tuple[str, float]:
    label = (block.grouping_meta or {}).get("label_line", "")
    if _EXAMPLE_LABEL_RE.match(label):
        return "Worked Example", 0.85
    if _ACTIVITY_LABEL_RE.match(label):
        return "Activity", 0.85
    if _WARNING_LABEL_RE.match(label):
        return "Law" if _LAW_HINT_RE.search(label) else "Activity", 0.4  # ambiguous overlap, low confidence
    if _NOTE_LABEL_RE.match(label):
        return "Summary", 0.5
    if _BOX_LABEL_RE.match(label):
        return "Activity", 0.55
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


def classify(block: Block, preceding_text: str = "", in_example: bool = False) -> Tuple[str, float]:
    """Pure deterministic classification. `preceding_text` is the raw text
    of the line(s) immediately before this block in reading order (only
    used by the equation-cluster path, as a weak fallback signal when
    `in_example` is False). `in_example` is the caller's structural
    tracking of whether this block falls within an already-open "Example
    .../Solution" callout span (see classify_blocks) -- a far more
    reliable signal than checking this one line's own text or only the
    single immediately-preceding block, since a worked example's
    derivation is routinely split by Stage A into several separate
    equation-cluster blocks, most of which are numeric-substitution
    steps (e.g. "Moles of C2H6O2 = 20 g / 62 g mol-1 = 0.322 mol") that
    don't themselves happen to sit right after the "Example" label."""
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
        # pdf_parser's font-size/numbering heading detector already made
        # this call deterministically and reliably; Stage B just adopts it.
        return "Heading", 1.0
    if anchor == "definition-candidate":
        return "Definition", 0.75
    if anchor == "table":
        return _classify_table_like(block)
    if anchor in ("figure", "diagram"):
        if anchor == "diagram":
            return _classify_diagram_like(block)
        return "Figure", 0.7

    body_text = " ".join(l.text for l in block.lines)
    if _SUMMARY_HINT_RE.search(body_text):
        return "Summary", 0.6
    if _REFERENCE_HINT_RE.search(body_text):
        return "Reference", 0.6
    if _LAW_HINT_RE.search(body_text):
        return "Law", 0.55

    return "Ambiguous", 0.0


def classify_blocks(blocks: List[Block]) -> List[Block]:
    """Classifies every block in place (mutates + returns the same list for
    convenient chaining).

    Tracks an `in_example` flag per page, in reading order: it turns on at
    an "Example"/"Illustration" callout-label block and turns back off at
    the next Heading or any differently-labeled callout (Activity, Note,
    Warning, Box, Exercise, ...) -- an ordinary "Solution" label block
    matches none of Stage B's callout regexes and comes back Ambiguous, so
    it does NOT close the span, which is exactly what's wanted: the
    "Solution" section is where a worked example's numeric-substitution
    steps actually live. Every equation-cluster block seen while this flag
    is on is classified Worked Example outright (see `classify`), which
    is far more robust than pattern-matching each line's own text --
    Stage A commonly splits one worked example's derivation into many
    separate single-line equation clusters, and no single-line regex can
    reliably tell "20 g / 62 g mol-1 = 0.322 mol" (a substitution step)
    apart from "K = KH x" (an actual formula) once unit words and labels
    are in the mix. `preceding_text` remains the fallback signal for
    equation clusters that appear with no open Example span at all (e.g.
    a standalone Formula Box out in ordinary body text)."""
    by_page = {}
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
                    # A different, explicitly-recognized callout (Activity,
                    # Note, Warning, Box, Exercise, ...) closes out whatever
                    # Example span was open. An ordinary "Solution" label
                    # doesn't match any of these regexes and comes back
                    # Ambiguous, so it deliberately does NOT close the span.
                    in_example = False
            elif anchor == "heading-topic":
                in_example = False
    logger.info("Stage B: classified %d block(s).", len(blocks))
    return blocks