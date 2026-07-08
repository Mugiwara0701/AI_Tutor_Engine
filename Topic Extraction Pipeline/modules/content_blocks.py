"""
content_blocks.py — deterministic (Python-only) detection of the
spec's small callout categories: activities, boxes, notes, warnings,
examples, and definition terms. These are pattern/keyword matches against
the same Line objects pdf_parser already extracted.

SUPERSEDED IN THE LIVE PIPELINE by modules/stage_a_geometry.py (geometric
grouping of label + body lines into hierarchical Blocks) and
modules/stage_b_classify.py (WHAT a block is, behind classify()) — pipeline.py
no longer calls the detect_*() functions below. This module is kept for:
  (a) standalone/unit-test use of the original flat detectors, and
  (b) its label regexes, which stage_a_geometry._LABEL_ANCHOR_RE mirrors as
      the geometric "where does a callout start" anchor.
The reason for the split: the old design let one regex match BOTH decide
"a block starts here" (Stage A's job) AND "this block is an Activity"
(Stage B's job) in the same step, which is exactly the "detects equations
first and educational meaning later" pattern the frozen architecture
review flagged as fundamentally wrong -- geometry (WHERE) and
classification (WHAT) must be separate stages even when, as here, they
happen to reuse the same keyword list for now.
"""
import re
from typing import List, Dict, Any

from modules.pdf_parser import Line, make_id

ACTIVITY_LABEL_RE = re.compile(r"^\s*(activity|think|observe|try|discuss|experiment)\b[\s:.\-]*", re.I)
BOX_LABEL_RE = re.compile(r"^\s*(did you know|important|note|remember|case study|box)\b[\s:.\-]*", re.I)
WARNING_LABEL_RE = re.compile(r"^\s*(warning|caution|remember|important)\b[\s:.\-]*", re.I)
EXAMPLE_LABEL_RE = re.compile(r"^\s*(example|illustration|solved example)\b[\s:.\-]*\d*", re.I)

# Two distinct sentence shapes for "X is a defined term" in NCERT prose:
#   (a) term-first:  "Bonds are defined as ..."      -> capture before the connector
#   (b) term-after:  "... which is called Bonds."    -> capture after the connector
# These are intentionally two separate patterns (not one re.I-merged pattern)
# because merging them under re.I let [A-Z] match lowercase letters too,
# which silently disabled the "must look like a real term" guard and let
# random mid-sentence clauses (e.g. "sector in an economy which") get
# captured as if they were the defined term.
DEFINITION_TERM_FIRST_RE = re.compile(
    r"^(?P<term>[A-Z][A-Za-z][A-Za-z \-]{1,38})\s+(?:is|are)\s+defined as\b")
DEFINITION_TERM_AFTER_RE = re.compile(
    r"\b(?:is|are)\s+(?:called|known as|referred to as)\s+"
    r"(?:the\s+|an?\s+)?(?P<term>[A-Za-z][A-Za-z \-]{1,38}?)(?=[.,;:]|\s+and\b|$)", re.I)

# A definition sentence that wraps across a line break leaves the real term
# on the *next* line and only a leftover article/pronoun on this one (e.g.
# "...is known as the" with "classical tradition" starting the next line).
# The optional article-prefix in DEFINITION_TERM_AFTER_RE can backtrack to
# capture that leftover word as if it were the term — reject it explicitly.
_TERM_STOPWORDS = {"the", "a", "an", "this", "that", "these", "those", "it", "its", "which", "who"}


def _label_from_match(text: str, regex: re.Pattern) -> str:
    m = regex.match(text)
    return m.group(1).title() if m else ""


def _collect_body_after(lines: List[Line], start_idx: int, repeated: set, max_lines: int = 12) -> str:
    """Grabs the next few non-heading lines after a callout label as its
    body, stopping early at the next label-like line to avoid bleeding into
    the following block."""
    out = []
    start_page = lines[start_idx].page
    for i in range(start_idx + 1, min(start_idx + 1 + max_lines, len(lines))):
        l = lines[i]
        if l.page != start_page:
            break  # don't bleed a callout's body into the next page's content
        if l.text in repeated:
            continue
        if (ACTIVITY_LABEL_RE.match(l.text) or BOX_LABEL_RE.match(l.text)
                or WARNING_LABEL_RE.match(l.text) or EXAMPLE_LABEL_RE.match(l.text)):
            break
        out.append(l.text)
        if len(" ".join(out)) > 500:
            break
    return " ".join(out)


def detect_activities(lines: List[Line], repeated: set, chapter_title: str) -> List[Dict[str, Any]]:
    results = []
    for idx, l in enumerate(lines):
        if l.text in repeated:
            continue
        label = _label_from_match(l.text, ACTIVITY_LABEL_RE)
        if not label:
            continue
        body = _collect_body_after(lines, idx, repeated)
        results.append({
            "id": make_id(chapter_title, "activity", label, str(idx)),
            "activity_type": label,
            "title": l.text.strip()[:100],
            "page": l.page,
            "bbox": {"x0": l.bbox[0], "y0": l.bbox[1], "x1": l.bbox[2], "y1": l.bbox[3], "page": l.page},
            "_body_for_semantic": body,  # consumed by pipeline, stripped before writing
        })
    return results


def detect_boxes(lines: List[Line], repeated: set, chapter_title: str) -> List[Dict[str, Any]]:
    results = []
    for idx, l in enumerate(lines):
        if l.text in repeated:
            continue
        label = _label_from_match(l.text, BOX_LABEL_RE)
        if not label:
            continue
        body = _collect_body_after(lines, idx, repeated)
        results.append({
            "id": make_id(chapter_title, "box", label, str(idx)),
            "box_type": label,
            "title": l.text.strip()[:100],
            "page": l.page,
            "bbox": {"x0": l.bbox[0], "y0": l.bbox[1], "x1": l.bbox[2], "y1": l.bbox[3], "page": l.page},
            "_body_for_semantic": body,
        })
    return results


def detect_warnings(lines: List[Line], repeated: set, chapter_title: str) -> List[Dict[str, Any]]:
    results = []
    for idx, l in enumerate(lines):
        if l.text in repeated:
            continue
        label = _label_from_match(l.text, WARNING_LABEL_RE)
        if not label:
            continue
        body = _collect_body_after(lines, idx, repeated)
        results.append({
            "id": make_id(chapter_title, "warning", label, str(idx)),
            "warning_type": label,
            "page": l.page,
            "bbox": {"x0": l.bbox[0], "y0": l.bbox[1], "x1": l.bbox[2], "y1": l.bbox[3], "page": l.page},
            "_body_for_semantic": body,
        })
    return results


def detect_notes(lines: List[Line], repeated: set, chapter_title: str) -> List[Dict[str, Any]]:
    """'Note' is shared with BOX_LABEL_RE; kept as its own list per schema
    (`notes` is a distinct top-level section from `boxes`) — matches lines
    whose label is specifically Note/Remember and treats them as standalone
    highlighted notes rather than boxed callouts when they're short (a
    heuristic since NCERT renders both similarly)."""
    results = []
    for idx, l in enumerate(lines):
        if l.text in repeated:
            continue
        if not re.match(r"^\s*(note|remember)\b[\s:.\-]*", l.text, re.I):
            continue
        body = _collect_body_after(lines, idx, repeated, max_lines=4)
        results.append({
            "id": make_id(chapter_title, "note", str(idx)),
            "page": l.page,
            "bbox": {"x0": l.bbox[0], "y0": l.bbox[1], "x1": l.bbox[2], "y1": l.bbox[3], "page": l.page},
            "_body_for_semantic": body,
        })
    return results


def detect_examples(lines: List[Line], repeated: set, chapter_title: str) -> List[Dict[str, Any]]:
    results = []
    for idx, l in enumerate(lines):
        if l.text in repeated:
            continue
        label = _label_from_match(l.text, EXAMPLE_LABEL_RE)
        if not label:
            continue
        body = _collect_body_after(lines, idx, repeated)
        results.append({
            "id": make_id(chapter_title, "example", str(idx)),
            "title": l.text.strip()[:100],
            "page": l.page,
            "bbox": {"x0": l.bbox[0], "y0": l.bbox[1], "x1": l.bbox[2], "y1": l.bbox[3], "page": l.page},
            "example_type": "worked_example",
            "_body_for_semantic": body,
        })
    return results


def detect_definition_terms(lines: List[Line], repeated: set, topic_lookup) -> List[Dict[str, Any]]:
    """Pattern-based term spotting, handling both 'Term is defined as ...'
    and '... is called Term' sentence shapes. Stores ONLY the term +
    location, never the definition text itself, per the copyright requirement."""
    results = []
    for l in lines:
        if l.text in repeated:
            continue
        m = DEFINITION_TERM_FIRST_RE.match(l.text)
        term = m.group("term").strip() if m else None
        if not term:
            m = DEFINITION_TERM_AFTER_RE.search(l.text)
            term = m.group("term").strip() if m else None
        if not term:
            continue
        if term.lower() in _TERM_STOPWORDS:
            continue
        if len(term.split()) > 6:
            continue
        topic_id = topic_lookup(l.page)
        results.append({"term": term, "page": l.page, "topic": topic_id,
                         "bbox": {"x0": l.bbox[0], "y0": l.bbox[1], "x1": l.bbox[2], "y1": l.bbox[3], "page": l.page}})
    return results