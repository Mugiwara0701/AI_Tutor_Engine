"""
pdf_parser.py — deterministic PDF structure extraction.

This is the existing font-based heading/TOC/chapter-detection logic
(previously one flat script) lifted into its own module, unchanged in
approach, plus additions needed for the new pipeline:

  - page_batches(): splits a chapter's pages into 4-8 page batches for the
    VLM stage (semantic_processor.py), so the model never sees the whole
    chapter at once.
  - Heading/topic records now carry page ranges + bbox + reading order,
    which the old script tracked only loosely (line index only) — the new
    schema needs real page_start/page_end/bbox per topic for `pages`,
    `topic_tree`, and per-figure/table page lookups to line up.

Everything here is Python + PyMuPDF only. No model calls happen in this
module — per the task spec, headings/numbering/chapter-splitting/page
detection must stay deterministic.
"""
import re
import os
import glob
import hashlib
import difflib
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF

from config import MIN_PAGE_BATCH_SIZE, MAX_PAGE_BATCH_SIZE, DEFAULT_PAGE_BATCH_SIZE, DEFAULT_LANGUAGE
from modules import language_detector

logger = logging.getLogger("ncert_pipeline.pdf_parser")

# A bare chapter number (a big decorative "1", "12", "IV" ... often set in a
# much larger font than the real chapter title right next to it) must never
# be picked as the chapter_title -- it wins detect_chapter_title's
# "largest font on page 0/1" heuristic whenever the numeral graphic is drawn
# bigger than the title text itself. This was silently producing
# chapter_title == "1" (see detect_chapter_title below).
_PURE_NUMERAL_RE = re.compile(r"^[ivxlcdm\d]{1,4}\.?$", re.I)

# Title must start with a letter -- but NOT specifically a Latin letter.
# `[^\d\s]` (any non-digit, non-whitespace character) matches Devanagari
# (Hindi/Sanskrit) and any other script just as well as it matches ASCII,
# so heading detection isn't silently English-only. This was previously
# `[A-Za-z]`, which meant Hindi/Sanskrit numbered headings never matched at
# all and fell through to the much weaker unnumbered-heading heuristic.
NUM_RE = re.compile(r"^(?P<num>\d+(\.\d+)*)\.?\s+(?P<title>[^\d\s].{1,90})$")
DENYLIST_PREFIX = re.compile(r"^\s*(fig\.?|figure|table|box|activity|exercise|source\s*:|chart)\b", re.I)

ROMAN_MAP = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
             "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
ROMAN_PAGE_RE = re.compile(r"^[ivxlcdm]{1,6}$", re.I)
INLINE_PAGE_RE = re.compile(r"^(?P<body>.+?)\s+(?P<page>\d{1,4}|[ivxlcdm]{1,6})$", re.I)
# A TOC top-level chapter entry is a number followed by a title -- optionally
# preceded by a single section-label word. Which word a given book uses for
# that label ("Unit", "Chapter", "Lesson", "Lecture", "Module", ...) is a
# per-book/per-language choice, not something this parser should ever need
# to enumerate (same principle as modules/language_detector.py: no term
# gets special-cased in *logic*). `(?P<label>[^\d\s]+\s+)?` matches any
# single label word there generically and simply discards it; only the
# number and title that follow are ever used. `[^\d\s]` rather than `\w` for
# the same reason NUM_RE uses it above: `\w` doesn't cover combining marks
# (e.g. Devanagari matras), so a label word in a non-Latin script would
# otherwise fail to match as one token. Without this, a book that numbers
# its top-level divisions as "Unit 1 Solutions" instead of "1. Solutions"
# fails to match at all, gets misfiled into front_back_matter, and
# book["chapters"] ends up empty for the whole book.
TOC_ENTRY_RE = re.compile(r"^(?:[^\d\s]+\s+)?(?P<num>\d+(\.\d+)*)\.?\s+(?P<title>.+)$")

KNOWN_SUBJECTS = [
    "mathematics", "math", "physics", "chemistry", "biology", "science",
    "english", "hindi", "sanskrit", "history", "geography", "civics", "economics",
    "political science", "sociology", "psychology", "accountancy",
    "business studies", "computer science", "computer-science",
]


# --------------------------------------------------------------------------
# Line-level data model
# --------------------------------------------------------------------------
@dataclass
class Line:
    text: str
    size: float
    max_size: float
    bold: bool
    font: str
    page: int
    y: float
    page_height: float
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class Heading:
    numbering: Optional[str]
    level: int
    title: str
    line_idx: int
    confidence: float
    signals: Dict[str, Any]
    page: int = 0
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


def is_bold(font_name: str) -> bool:
    return bool(re.search(r"demi|bold|black|heavy", font_name, re.I))


def extract_lines(pdf_path: str) -> List[Line]:
    doc = fitz.open(pdf_path)
    lines: List[Line] = []
    for pno, page in enumerate(doc):
        ph = page.rect.height
        d = page.get_text("dict")
        for block in d["blocks"]:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(s["text"] for s in spans).strip()
                if not text:
                    continue
                sizes = Counter()
                for s in spans:
                    sizes[round(s["size"], 1)] += len(s["text"])
                dom_size = sizes.most_common(1)[0][0]
                max_size = max(sizes)
                dom_font = max(spans, key=lambda s: len(s["text"]))["font"]
                bold = any(is_bold(s["font"]) for s in spans if round(s["size"], 1) == max_size)
                bbox = line.get("bbox", spans[0]["bbox"])
                y = spans[0]["bbox"][1]
                lines.append(Line(text=text, size=dom_size, max_size=max_size, bold=bold,
                                   font=dom_font, page=pno, y=y, page_height=ph, bbox=tuple(bbox)))
    doc.close()
    return lines


def dedupe_decorative_duplicates(lines: List[Line]) -> List[Line]:
    out: List[Line] = []
    for l in lines:
        if out:
            p = out[-1]
            same_pos = p.page == l.page and round(p.size, 1) == round(l.size, 1) and abs(p.y - l.y) < 3
            is_dup = p.text == l.text or p.text.startswith(l.text) or l.text.startswith(p.text)
            if same_pos and is_dup:
                if len(l.text) > len(p.text):
                    out[-1] = l
                continue
        out.append(l)
    return out


def merge_wrapped_lines(lines: List[Line], body_size: float) -> List[Line]:
    def heading_styled(l: Line) -> bool:
        return l.bold or (l.max_size / body_size >= 1.05)

    def similar_tier(a: Line, b: Line) -> bool:
        lo, hi = sorted([a.max_size, b.max_size])
        return hi / lo <= 1.2

    def is_chapter_label(l: Line) -> bool:
        return bool(re.fullmatch(r"chapter\s*\d+\.?", l.text.strip(), re.I))

    merged: List[Line] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        j = i + 1
        while (j < len(lines)
               and lines[j].page == cur.page
               and heading_styled(cur)
               and not is_chapter_label(cur)
               and not cur.text.rstrip().endswith((".", "?", "!", ":"))
               and not NUM_RE.match(lines[j].text)
               and heading_styled(lines[j])
               and similar_tier(cur, lines[j])
               and (lines[j].y - cur.y) < 2.2 * max(cur.max_size, lines[j].max_size)
               and len(cur.text) < 90):
            x0 = min(cur.bbox[0], lines[j].bbox[0])
            y0 = min(cur.bbox[1], lines[j].bbox[1])
            x1 = max(cur.bbox[2], lines[j].bbox[2])
            y1 = max(cur.bbox[3], lines[j].bbox[3])
            cur = Line(text=(cur.text.rstrip() + " " + lines[j].text.strip()).strip(),
                       size=cur.size, max_size=max(cur.max_size, lines[j].max_size),
                       bold=cur.bold or lines[j].bold, font=cur.font,
                       page=cur.page, y=cur.y, page_height=cur.page_height,
                       bbox=(x0, y0, x1, y1))
            j += 1
        merged.append(cur)
        i = j
    return merged


def body_font_size(lines: List[Line]) -> float:
    counter = Counter()
    for l in lines:
        counter[l.size] += len(l.text)
    return counter.most_common(1)[0][0] if counter else 10.5


def find_repeated_lines(lines: List[Line]) -> set:
    per_page_margin_text = Counter()
    pages = set(l.page for l in lines)
    for l in lines:
        near_top = l.y < 0.12 * l.page_height
        near_bottom = l.y > 0.90 * l.page_height
        if near_top or near_bottom:
            per_page_margin_text[l.text] += 1
    return {t for t, c in per_page_margin_text.items() if c >= max(3, len(pages) // 2)}


def detect_chapter_title(lines: List[Line], body_size: float, repeated: set) -> str:
    candidates = [l for l in lines if l.page <= 1 and l.text not in repeated
                  and l.size > body_size * 1.3
                  and not re.fullmatch(r"chapter\s*\d+", l.text.strip(), re.I)
                  # Exclude bare chapter-number graphics ("1", "12", "IV", ...).
                  # These are frequently typeset in a much larger font than the
                  # real title next to them, so without this guard the
                  # "biggest font wins" heuristic below picks the numeral
                  # itself as the chapter_title instead of the actual title.
                  and not _PURE_NUMERAL_RE.match(l.text.strip())]
    if not candidates:
        return "untitled-chapter"
    best_size = max(c.size for c in candidates)
    # The single largest-font line on the title page is *usually* the real
    # chapter title, but not always: a pull-quote, a subject-icon caption, a
    # decorative running strap, or a highlighted box can legitimately be set
    # in an even larger font than the title itself. Picking strictly
    # `c.size == best_size` silently grabs that decorative text instead
    # whenever it happens to be a point or two bigger.
    #
    # Instead, treat every candidate within 15% of the largest size as
    # plausible (a "band"), then break ties by page position (topmost
    # first) and boldness. The real chapter title is reliably the first
    # bold, near-largest text block on the page -- even on the pages where
    # it isn't the single biggest -- because decorative/caption text that
    # out-sizes it is typically further down the page or not bold.
    band = [c for c in candidates if c.size >= best_size * 0.85]
    band.sort(key=lambda c: (c.page, c.y))
    bold_band = [c for c in band if c.bold]
    pick_from = bold_band if bold_band else band
    return pick_from[0].text.strip()


def detect_headings(lines: List[Line], body_size: float, repeated: set) -> List[Heading]:
    headings: List[Heading] = []
    expected_next: Dict[int, tuple] = {}

    for idx, l in enumerate(lines):
        if l.text in repeated:
            continue
        m = NUM_RE.match(l.text)
        if not m:
            continue
        if DENYLIST_PREFIX.search(m.group("title")):
            continue

        num = m.group("num")
        title = m.group("title").strip()
        depth = num.count(".")
        if depth == 0:
            continue
        level = 1 if depth == 1 else 2

        size_ratio = l.max_size / body_size
        signals = {"font_larger": size_ratio >= 1.08, "bold": l.bold, "size_ratio": round(size_ratio, 2)}

        parts = tuple(int(p) for p in num.split("."))
        prev = expected_next.get(depth)
        seq_ok = not (prev is not None and parts <= prev)
        signals["sequence_ok"] = seq_ok

        score = 0.35
        score += 0.25 if signals["font_larger"] else 0
        score += 0.25 if signals["bold"] else 0
        score += 0.15 if seq_ok else -0.3
        score = max(0.0, min(0.98, score))

        if not (signals["font_larger"] or signals["bold"]) or not seq_ok:
            continue

        expected_next[depth] = parts
        headings.append(Heading(numbering=num, level=level, title=title, line_idx=idx,
                                 confidence=round(score, 2), signals=signals,
                                 page=l.page, bbox=l.bbox))
    return headings


def detect_unnumbered_headings(lines: List[Line], body_size: float, repeated: set,
                                already_used_idx: set, chapter_title: str = "") -> List[Heading]:
    headings: List[Heading] = []
    for idx, l in enumerate(lines):
        if idx in already_used_idx or l.text in repeated:
            continue
        if NUM_RE.match(l.text) or DENYLIST_PREFIX.search(l.text):
            continue
        if re.fullmatch(r"chapter\s*\d+", l.text.strip(), re.I):
            continue
        if chapter_title and l.text.strip() == chapter_title.strip():
            continue
        if len(l.text) > 90 or len(l.text) < 3 or l.text.endswith((".", "?", "!", ",")):
            continue
        size_ratio = l.max_size / body_size
        font_larger = size_ratio >= 1.08
        if not (font_larger or l.bold):
            continue
        score = 0.35 + (0.25 if font_larger else 0) + (0.2 if l.bold else 0)
        headings.append(Heading(numbering=None, level=1, title=l.text.strip(), line_idx=idx,
                                 confidence=round(min(score, 0.8), 2),
                                 signals={"font_larger": font_larger, "bold": l.bold,
                                          "size_ratio": round(size_ratio, 2), "numbered": False},
                                 page=l.page, bbox=l.bbox))
    return headings


def build_body_map(lines: List[Line], headings: List[Heading], repeated: set) -> Dict[int, str]:
    heading_positions = sorted(h.line_idx for h in headings)
    heading_positions.append(len(lines))
    body_for = {}
    for h in headings:
        start = h.line_idx + 1
        end = heading_positions[heading_positions.index(h.line_idx) + 1]
        chunk = [lines[i].text for i in range(start, end) if lines[i].text not in repeated]
        body_for[h.line_idx] = " ".join(chunk)
    return body_for


def slugify(*parts: str) -> str:
    raw = "_".join(p.lower().strip() for p in parts if p)
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw or "untitled"


def make_id(*parts: str) -> str:
    """A3 — Stable ID infrastructure. Deterministic by construction: the id
    is purely a function of `parts` (slugify() -> sha1 hex digest,
    truncated), with no random/UUID/timestamp component anywhere in the
    path. Re-running the compiler on unchanged input parts (chapter title,
    object kind, page/position) always reproduces the exact same id --
    that's what makes it safe to use as a stable cross-run reference. If a
    part changes (e.g. a heading gets corrected via script-mismatch
    recovery), the id deliberately changes too, since the identity is tied
    to that content, not to a slot/index that would silently alias two
    different things across runs.
    """
    base = slugify(*parts)
    h = hashlib.sha1(base.encode()).hexdigest()[:6]
    return f"{base[:60]}-{h}"


def make_urn(namespace: str, *parts: str) -> str:
    """A3 — Stable URN infrastructure, layered on top of slugify() rather
    than inventing a second identity mechanism. Produces a hierarchical,
    globally-unique reference:

        urn:ncert-kg:<namespace>:<slug-1>:<slug-2>:...

    `namespace` is typically "<book_slug>:<chapter_slug>" so urns stay
    unique across an entire book/run, not just within one chapter.

    DETERMINISM: built ONLY from slugify()-normalized `parts` -- object
    kind, a content-derived key (name/term/title), and, only where no
    content-derived key exists, a stable positional index -- never a
    random UUID or a timestamp. Two independent compiler runs over
    unchanged source content therefore always produce the identical urn;
    the urn only changes when one of its inputs actually changes (i.e.
    "stable across recompilations unless educational meaning changes",
    per the Phase A roadmap's A3 requirement).

    MULTILINGUAL / MULTI-BOARD NOTE: `namespace`/`parts` are taken as
    already-resolved strings -- this function does not itself special-case
    language or exam board. That means a translated title/heading
    naturally slugifies to a different urn than its English-source
    counterpart for "the same" underlying concept. That divergence is
    intentional and out of scope for Phase A (cross-language/cross-board
    concept alignment is a Phase-2/knowledge-graph concern, not an
    identity-generation one) -- but it is called out explicitly here, per
    the roadmap's instruction to review whether multilingual/multi-board
    support requires URN changes, as the seam a future pass should extend
    (e.g. keying off a language-independent concept fingerprint) rather
    than a hidden assumption someone has to rediscover.
    """
    board_namespace = "ncert-kg"
    slug_parts = [slugify(p) for p in parts if p]
    if not slug_parts:
        return f"urn:{board_namespace}:{namespace}"
    return f"urn:{board_namespace}:{namespace}:" + ":".join(slug_parts)


def auto_detect_subject(filename: str, first_page_text: str) -> str:
    # Longest-first: without this, scanning first_page_text for e.g. "science"
    # (a generic word that shows up incidentally in almost any subject's
    # body text -- "management is both a science and an art", etc.) matches
    # before the book's real, more specific subject ("business studies") is
    # ever checked, because KNOWN_SUBJECTS happens to list the generic
    # single-word subjects first. This was silently mislabeling entire books.
    subjects_by_specificity = sorted(KNOWN_SUBJECTS, key=len, reverse=True)

    def _search(haystack: str) -> Optional[str]:
        for subj in subjects_by_specificity:
            if re.search(r"\b" + re.escape(subj) + r"\b", haystack):
                return "mathematics" if subj == "math" else subj
        return None

    haystack = filename.lower().replace("_", " ").replace("-", " ")
    found = _search(haystack)
    if found:
        return found
    found = _search(first_page_text.lower())
    if found:
        return found
    return "unknown"


def auto_detect_class(filename: str, first_page_text: str) -> str:
    pattern = re.compile(r"(?:class|grade|std\.?)\s*[-_]?\s*(\d{1,2})", re.I)
    for source in (filename.replace("_", " ").replace("-", " "), first_page_text):
        m = pattern.search(source)
        if m:
            return m.group(1)
    return "unknown"


# --------------------------------------------------------------------------
# Prelims / TOC
# --------------------------------------------------------------------------
def is_prelims_filename(filename: str) -> bool:
    stem = os.path.splitext(filename)[0].lower()
    return stem.endswith("ps") or "prelim" in stem


# NCERT chapter PDFs are named <subject-code><part-digit><chapter-2-digits>.pdf
# -- e.g. "lech102.pdf" is Chemistry Part 1, chapter 2; "kemh113.pdf" is Maths
# Part 1, chapter 13. Non-chapter files in the same folder (prelims
# "...ps.pdf", appendices "...a1.pdf", answer keys "...an.pdf", ...) end in
# letters rather than two digits, so they simply don't match.
_CHAPTER_NUM_FILENAME_RE = re.compile(r"(\d{2})$")


def chapter_number_from_filename(filename: str) -> Optional[int]:
    """Extract the real chapter number from an NCERT chapter PDF's filename.

    This must be used instead of a chapter PDF's position in whatever batch
    of files happens to be in the input folder for a given run. A caller
    that instead numbers chapters purely by loop position (1, 2, 3, ... in
    processing order) gets it wrong the moment fewer than all of a book's
    chapters are present in one run -- e.g. dropping in a single newly
    published chapter (say, chapter 5) processes it as position #1, and
    that #1 then gets used to look up chapter 1's title in the TOC
    (match_chapter_by_number), silently overwriting the correct title with
    chapter 1's. Parsing the number out of the filename itself sidesteps
    this because it doesn't depend on which other files are present.

    Returns None (caller should fall back to loop position) if the
    filename doesn't end in two digits -- i.e. it isn't a standard NCERT
    chapter filename at all.
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = _CHAPTER_NUM_FILENAME_RE.search(stem)
    return int(m.group(1)) if m else None


def parse_book_title_and_class(lines: List[Line], body_size: float, repeated: set):
    page0 = [l for l in lines if l.page == 0 and l.text not in repeated]
    big = [l for l in page0 if l.max_size >= body_size * 1.5]
    book_title = max(big, key=lambda l: l.max_size).text.strip() if big else "untitled-book"

    # The "Textbook for Class XII" / "Textbook in X for Class Y" line can sit
    # anywhere in the prelims file -- how many pages precede it (blank leaf,
    # foreword, notes-on-transliteration, etc.) varies book to book, so there
    # is no page count that's safe to hardcode here. These two regexes are
    # specific enough (they require the literal "class <numeral/number>" or
    # "textbook in <subject> for class" phrasing) that searching the *entire*
    # prelims document for them can't accidentally match unrelated text, so
    # there's no need to guess a cutoff at all -- mirrors find_toc_lines(),
    # which likewise never assumes "Contents" lands within N pages.
    scannable = [l for l in lines if l.text not in repeated]

    subject, klass = "unknown", "unknown"
    for l in scannable:
        m_class = re.search(r"class\s+([IVXLCDM]+|\d{1,2})\b", l.text, re.I)
        if m_class:
            grp = m_class.group(1).upper()
            klass = str(ROMAN_MAP[grp]) if grp in ROMAN_MAP else grp
        m_subj = re.search(r"textbook\s+in\s+([A-Za-z ]+?)\s+for\s+class", l.text, re.I)
        if m_subj:
            subject = m_subj.group(1).strip().lower()

    if klass == "unknown" or subject == "unknown":
        # Some layouts split the phrase across two separate text runs (e.g.
        # a roman numeral set in a different size/font than the word
        # "Class"), which come through as distinct Line objects and never
        # match the single-line regexes above. Fall back to the same
        # patterns over the whole document's text joined with spaces, so a
        # match that used to span two adjacent lines can still be found.
        joined_text = " ".join(l.text for l in scannable)
        if klass == "unknown":
            m_class = re.search(r"class\s+([IVXLCDM]+|\d{1,2})\b", joined_text, re.I)
            if m_class:
                grp = m_class.group(1).upper()
                klass = str(ROMAN_MAP[grp]) if grp in ROMAN_MAP else grp
        if subject == "unknown":
            m_subj = re.search(r"textbook\s+in\s+([A-Za-z ]+?)\s+for\s+class", joined_text, re.I)
            if m_subj:
                subject = m_subj.group(1).strip().lower()

    if subject == "unknown":
        # The "textbook in X for class Y" phrasing above only matches some
        # NCERT prelims layouts. Fall back to scanning the book's own big
        # title text (e.g. "Business Studies") against the known-subject
        # list -- still fully deterministic, and far more reliable than
        # leaving it "unknown" and letting each chapter guess independently
        # from its own body text (see auto_detect_subject's docstring: a
        # generic word incidentally used in one chapter's prose, e.g.
        # "management is a science", must never override the real subject).
        # Deliberately narrow to the title page only, never the rest of the
        # document: NCERT prelims files carry a review-committee /
        # contributors list somewhere in the front matter, full of lines
        # like "Department of Psychology, ..." for reviewers whose own
        # field has nothing to do with the book's actual subject. A generic
        # substring search over that text would pick up whichever
        # known-subject word happens to be longest (subjects_by_specificity
        # is sorted longest-first) regardless of relevance -- this already
        # mislabeled a chemistry book "psychology" once from exactly that
        # list. The structured regexes above are specific enough to be
        # safe over the whole document; this last-resort generic keyword
        # match is not, so it stays confined to the cover/title page.
        subjects_by_specificity = sorted(KNOWN_SUBJECTS, key=len, reverse=True)
        page0_text = " ".join(l.text for l in page0).lower()
        for source in (book_title.lower(), page0_text):
            for subj in subjects_by_specificity:
                if re.search(r"\b" + re.escape(subj) + r"\b", source):
                    subject = "mathematics" if subj == "math" else subj
                    break
            if subject != "unknown":
                break
    return book_title, subject, klass


def _is_contents_heading(text: str) -> bool:
    """True for the prelims page's "Contents" heading line.

    Previously required an *exact* match against "contents", which misses
    it whenever the heading line picks up trailing/adjacent tokens during
    line extraction or merge_wrapped_lines() -- e.g. "Contents iii",
    "CONTENTS PAGE", "Contents:" -- causing find_toc_lines() to silently
    return [] (no warning was ever logged), which in turn means the whole
    book falls back to per-chapter, TOC-less detection: no chapter-number
    matching, no toc_matched, and chapter titles left entirely to the
    font-size heuristic in detect_chapter_title().
    """
    t = text.strip().lower()
    return t.startswith("content") or t == "table of contents"


def find_toc_lines(lines: List[Line], repeated: set) -> List[Line]:
    start = next((i for i, l in enumerate(lines) if _is_contents_heading(l.text)), None)
    if start is None:
        logger.warning(
            "No 'Contents' heading found in the prelims/TOC file -- proceeding without a "
            "table of contents. Chapter numbers/titles for this book will rely entirely on "
            "per-chapter font-size heuristics instead of TOC matching, which is less reliable."
        )
        return []
    out = []
    seen_glossary_standalone = False
    for l in lines[start + 1:]:
        if l.text in repeated:
            continue
        out.append(l)
        text_upper = l.text.strip().upper()
        if text_upper == "GLOSSARY":
            seen_glossary_standalone = True
            continue
        if seen_glossary_standalone:
            break
        if text_upper.startswith("GLOSSARY") and text_upper != "GLOSSARY":
            break
    return out


def parse_toc(toc_lines: List[Line]) -> Dict[str, Any]:
    entries = []
    buf = []
    for l in toc_lines:
        text = l.text.strip().lstrip("?").strip()
        if not text:
            continue
        is_pure_page_num = re.fullmatch(r"\d{1,4}", text) or ROMAN_PAGE_RE.fullmatch(text)
        if is_pure_page_num:
            if buf:
                entries.append((" ".join(buf), text))
                buf = []
            continue
        m_inline = INLINE_PAGE_RE.match(text)
        if m_inline:
            body = m_inline.group("body").strip()
            page = m_inline.group("page")
            if buf:
                entries.append((" ".join(buf + [body]), page))
                buf = []
            else:
                entries.append((body, page))
            continue
        buf.append(text)
    if buf:
        entries.append((" ".join(buf), None))

    book: Dict[str, Any] = {"chapters": [], "front_back_matter": []}
    cur_chapter, cur_topic = None, None
    for combined, page_raw in entries:
        page = int(page_raw) if page_raw and page_raw.isdigit() else page_raw
        m = TOC_ENTRY_RE.match(combined)
        if not m:
            book["front_back_matter"].append({"title": combined, "page_start": page})
            continue
        num, title = m.group("num"), re.sub(r"\s+", " ", m.group("title")).strip()
        depth = num.count(".")
        if depth == 0:
            cur_chapter = {"number": int(num), "title": title, "page_start": page, "topics": []}
            book["chapters"].append(cur_chapter)
            cur_topic = None
        elif depth == 1 and cur_chapter is not None:
            cur_topic = {"number": num, "title": title, "page_start": page, "subtopics": []}
            cur_chapter["topics"].append(cur_topic)
        elif cur_topic is not None:
            cur_topic["subtopics"].append({"number": num, "title": title, "page_start": page})
    return book


def match_chapter_in_toc(detected_title: str, toc: Optional[Dict[str, Any]]):
    if not toc or not toc.get("chapters"):
        return None
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
    target = norm(detected_title)
    if not target:
        return None
    best, best_ratio = None, 0.0
    for ch in toc["chapters"]:
        ratio = difflib.SequenceMatcher(None, target, norm(ch["title"])).ratio()
        if ratio > best_ratio:
            best, best_ratio = ch, ratio
    return best if best_ratio >= 0.55 else None


def match_chapter_by_number(chapter_order: int, toc: Optional[Dict[str, Any]]):
    """Looks up a chapter in the prelims TOC by its position (1-based) among
    the chapter PDFs in this book, rather than by fuzzy-matching detected
    title text. This is the *primary* way to resolve a chapter against the
    TOC, not a fallback: the TOC file already carries the ground-truth
    number->title mapping (that's literally what a table of contents is),
    and NCERT chapter PDFs are named/ordered sequentially, so chapter_order
    is normally a completely reliable index into toc["chapters"] -- no text
    comparison needed at all.

    This matters most exactly when detect_chapter_title() got a garbled or
    empty title (e.g. a decorative unit-opener page where the real title is
    rendered as a graphic, not text, and font-size heuristics instead pick
    up a merged fragment like "1 Unit1"): fuzzy title matching has nothing
    usable to compare in that case and will never clear the similarity
    threshold, so it silently leaves the garbage title in place. Matching
    by number instead sidesteps the bad title entirely and pulls the
    correct one straight from the TOC.

    Returns None if the TOC has no entry at that position, or has no
    numbered chapters at all -- callers should fall back to
    match_chapter_in_toc() or chapter_order in that case."""
    if not toc or not toc.get("chapters"):
        return None
    for ch in toc["chapters"]:
        if ch.get("number") == chapter_order:
            return ch
    return None


@dataclass
class BookContext:
    book_title: str = "untitled-book"
    subject: str = "unknown"
    klass: str = "unknown"
    toc: Optional[Dict[str, Any]] = None
    # None means "not determined at book level" (e.g. no prelims file was
    # found) -- callers (parse_chapter_pdf) fall back to per-chapter
    # detection in that case rather than treating None as English.
    language: Optional[str] = None


def load_book_context(prelims_path: Optional[str]) -> BookContext:
    if not prelims_path:
        return BookContext()
    lines = extract_lines(prelims_path)
    lines = dedupe_decorative_duplicates(lines)
    body_size = body_font_size(lines)
    lines = merge_wrapped_lines(lines, body_size)
    repeated = find_repeated_lines(lines)
    book_title, subject, klass = parse_book_title_and_class(lines, body_size, repeated)
    toc_lines = find_toc_lines(lines, repeated)
    toc = parse_toc(toc_lines) if toc_lines else None

    first_page_text = " ".join(l.text for l in lines if l.page == 0)[:2000]
    pdf_meta = {}
    try:
        doc = fitz.open(prelims_path)
        pdf_meta = doc.metadata or {}
        doc.close()
    except Exception:
        pass
    # font_names comes straight off the Line records extract_lines() already
    # built (each line's dominant font, per-span), rather than a second PDF
    # read -- font names are plain ASCII set by the typesetting software, so
    # they survive intact even on a legacy-font (mismapped) book where the
    # text itself doesn't (see language_detector.detect_legacy_devanagari_font).
    font_names = list({l.font for l in lines if l.font})
    language = language_detector.detect_language(
        filename=os.path.basename(prelims_path), book_title=book_title, subject=subject,
        sample_text=first_page_text, pdf_metadata=pdf_meta, override=DEFAULT_LANGUAGE,
        font_names=font_names,
    )
    return BookContext(book_title=book_title, subject=subject, klass=klass, toc=toc, language=language)


def find_prelims_pdf(all_paths: List[str]) -> Optional[str]:
    candidates = [p for p in all_paths if is_prelims_filename(os.path.basename(p))]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        verified = []
        for p in candidates:
            probe_lines = extract_lines(p)
            probe_lines = dedupe_decorative_duplicates(probe_lines)
            probe_repeated = find_repeated_lines(probe_lines)
            if find_toc_lines(probe_lines, probe_repeated):
                verified.append(p)
        return verified[0] if verified else candidates[0]
    return None


# --------------------------------------------------------------------------
# Per-chapter-PDF structural extraction (the object semantic_processor and
# json_writer consume)
# --------------------------------------------------------------------------
@dataclass
class TopicRecord:
    id: str
    title: str
    numbering: Optional[str]
    level: int  # 1 = topic, 2 = sub-topic
    parent: Optional[str]
    page_start: int
    page_end: int
    bbox: Tuple[float, float, float, float]
    reading_order: int
    body_text: str
    confidence: float
    signals: Dict[str, Any]


@dataclass
class ChapterStructure:
    filename: str
    subject: str
    klass: str
    chapter_title: str
    chapter_number: Any
    toc_matched: bool
    num_pages: int
    lines: List[Line]
    body_size: float
    repeated: set
    topics: List[TopicRecord]
    page_word_counts: Dict[int, int]
    page_sizes: Dict[int, Tuple[float, float]]
    language: str = "en"  # ISO code from language_detector; propagates to OCR + prompts + JSON output


def parse_chapter_pdf(pdf_path: str, book_ctx: BookContext, chapter_order_fallback: int,
                       subject: Optional[str] = None, klass: Optional[str] = None) -> ChapterStructure:
    filename = os.path.basename(pdf_path)
    doc = fitz.open(pdf_path)
    num_pages = doc.page_count
    page_sizes = {p: (doc[p].rect.width, doc[p].rect.height) for p in range(num_pages)}
    doc.close()

    lines = extract_lines(pdf_path)
    lines = dedupe_decorative_duplicates(lines)
    body_size = body_font_size(lines)
    lines = merge_wrapped_lines(lines, body_size)
    repeated = find_repeated_lines(lines)
    first_page_text = " ".join(l.text for l in lines if l.page == 0)[:2000]

    page_word_counts: Dict[int, int] = Counter()
    for l in lines:
        if l.text not in repeated:
            page_word_counts[l.page] += len(l.text.split())

    if subject is None:
        subject = book_ctx.subject if book_ctx.subject != "unknown" else auto_detect_subject(filename, first_page_text)
    if klass is None:
        klass = book_ctx.klass if book_ctx.klass != "unknown" else auto_detect_class(filename, first_page_text)

    pdf_meta = {}
    try:
        doc = fitz.open(pdf_path)
        pdf_meta = doc.metadata or {}
        doc.close()
    except Exception:
        pass
    # font_names, same reasoning as load_book_context(): cheap, book-agnostic
    # signal for the legacy-font case, and this chapter's own font_names
    # matter when there was no prelims file at all (book_ctx.language is
    # then None and this call is the only detection that runs).
    font_names = list({l.font for l in lines if l.font})
    # book_ctx.language (set from the prelims/TOC file, when one exists) is
    # authoritative for every chapter in that book -- passed in as an
    # override so a single chapter whose own first page happens to be
    # mostly numbers/figures doesn't get mis-detected independently.
    language = language_detector.detect_language(
        filename=filename, book_title=book_ctx.book_title, subject=subject,
        sample_text=first_page_text, pdf_metadata=pdf_meta,
        override=DEFAULT_LANGUAGE or book_ctx.language,
        font_names=font_names,
    )

    chapter_title = detect_chapter_title(lines, body_size, repeated)
    # Number-based lookup first: chapter_order_fallback (this PDF's position
    # among the book's chapter files) is normally a fully reliable index
    # into the TOC's number->title mapping, and doesn't depend on
    # detect_chapter_title() having found clean text -- see
    # match_chapter_by_number()'s docstring for why this matters on
    # decorative/graphic title pages. Fuzzy title matching only runs as a
    # fallback when the TOC has no entry at that exact position (e.g. a
    # front-matter page miscounted as a chapter).
    toc_match = match_chapter_by_number(chapter_order_fallback, book_ctx.toc)
    if not toc_match:
        toc_match = match_chapter_in_toc(chapter_title, book_ctx.toc)
    toc_matched = bool(toc_match)
    if toc_match:
        chapter_number = toc_match["number"]
        chapter_title = toc_match["title"]
    else:
        chapter_number = chapter_order_fallback

    headings = detect_headings(lines, body_size, repeated)
    if not headings:
        headings = detect_unnumbered_headings(lines, body_size, repeated, set(), chapter_title=chapter_title)

    body_map = build_body_map(lines, headings, repeated)

    # page_end per heading = page of the next heading (or last page of doc)
    topics: List[TopicRecord] = []
    sorted_headings = sorted(headings, key=lambda h: h.line_idx)
    parent_topic_id = None
    for order, h in enumerate(sorted_headings):
        next_page = sorted_headings[order + 1].page if order + 1 < len(sorted_headings) else num_pages - 1
        topic_id = make_id(chapter_title, h.numbering or h.title, str(order))
        if h.level == 1:
            parent_topic_id = topic_id
            parent = None
        else:
            parent = parent_topic_id
        topics.append(TopicRecord(
            id=topic_id, title=h.title, numbering=h.numbering, level=h.level, parent=parent,
            page_start=h.page, page_end=max(h.page, next_page), bbox=h.bbox,
            reading_order=order, body_text=body_map.get(h.line_idx, ""),
            confidence=h.confidence, signals=h.signals,
        ))

    return ChapterStructure(
        filename=filename, subject=subject or "unknown", klass=klass or "unknown",
        chapter_title=chapter_title, chapter_number=chapter_number, toc_matched=toc_matched,
        num_pages=num_pages, lines=lines, body_size=body_size, repeated=repeated,
        topics=topics, page_word_counts=dict(page_word_counts), page_sizes=page_sizes,
        language=language,
    )


def page_batches(num_pages: int, batch_size: int = DEFAULT_PAGE_BATCH_SIZE) -> List[List[int]]:
    """Split a chapter's page range into batches of `batch_size` pages
    (clamped to 4-8) for the VLM stage. Deterministic, no model calls."""
    batch_size = max(MIN_PAGE_BATCH_SIZE, min(MAX_PAGE_BATCH_SIZE, batch_size))
    pages = list(range(num_pages))
    return [pages[i:i + batch_size] for i in range(0, len(pages), batch_size)]