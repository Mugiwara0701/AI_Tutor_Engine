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
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF

# Optional: used ONLY to recover a human-readable book_title (in the
# language actually printed in the book, e.g. Devanagari) when the title
# line's own font is a legacy non-Unicode Hindi/Sanskrit-typing font (see
# language_detector.detect_legacy_devanagari_font) -- the PDF's text LAYER
# is mismapped in that case, but the rendered GLYPHS are correct, so OCR'ing
# a render of just that line recovers the real text where the deterministic
# text layer cannot. This is the one narrow, explicitly-scoped exception to
# this module otherwise being deterministic/model-call-free (see module
# docstring): it never runs unless a legacy font was already detected, is
# wrapped so its absence degrades gracefully (falls back to the existing
# "untitled-book" sentinel, unchanged from before this existed), and is
# never used for chapter/heading/body text -- only this one metadata field.
try:
    import pytesseract
    from PIL import Image
    import io as _io
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


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
# A decorative "drop cap" -- the chapter's real opening letter set alone in
# an oversized/illuminated font as its own text run, physically separate
# from the rest of the title's normal-size text (e.g. a large "Y" sitting
# beside "our Environment"). Root cause of the "Chapter 'Y'" placeholder-
# title regression: on a title page where the drop cap is the single
# largest font size present, the "biggest font wins" heuristic below picked
# the lone letter itself as the chapter_title, never even attempting the
# real title text at a smaller size right next to it. 1-2 bare letters is
# never a genuine standalone NCERT chapter title, so it's excluded here the
# same way bare chapter-number graphics already are.
_DROP_CAP_RE = re.compile(r"^[A-Za-z]{1,2}\.?$")

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
# Separator between the leading number and the title text: a literal period
# ("1. Title") is the common case, but NCERT Hindi/Sanskrit prelims routinely
# number entries with a hyphen ("1- Title"), colon, or close-paren instead
# ("1) Title"). `[.\-:)]?` accepts any of those (or none, for "1 Title") so
# entries aren't missed just because the book's numbering punctuation isn't
# a period.
TOC_ENTRY_RE = re.compile(r"^(?:[^\d\s]+\s+)?(?P<num>\d+(\.\d+)*)[.\-:)]?\s+(?P<title>.+)$")

KNOWN_SUBJECTS = [
    "mathematics", "math", "physics", "chemistry", "biology", "science",
    "english", "hindi", "sanskrit", "history", "geography", "civics", "economics",
    "political science", "sociology", "psychology", "accountancy",
    "business studies", "computer science", "computer-science",
]

# Hindi/Sanskrit NCERT prelims mark the class as "कक्षा <N>" rather than the
# English word "Class" that parse_book_title_and_class()'s regexes were
# originally written for -- so a book whose cover text is genuinely all in
# Devanagari (no bilingual "Class XI" line anywhere) always fell through to
# klass="unknown", even when the class marking was perfectly readable
# Unicode text. This table-driven addition follows the same
# no-special-casing-in-logic principle as language_detector.py: each
# supported class is just a table row, not an if/elif branch.
DEVANAGARI_DIGIT_MAP = {"०": 0, "१": 1, "२": 2, "३": 3, "४": 4,
                         "५": 5, "६": 6, "७": 7, "८": 8, "९": 9}

# NCERT only spans classes 1-12, so a small, explicit table of the ordinal
# words actually used on prelims pages (Hindi-style "दसवीं" and Sanskrit-
# style "दशम"/"दशमः" both appear across different NCERT titles) is safe and
# exhaustive -- unlike English ordinals, Devanagari ordinals don't reduce to
# a single regex-computable pattern, so this has to be a literal lookup.
HINDI_SANSKRIT_CLASS_ORDINALS = {
    1: ["पहली", "प्रथम", "प्रथमः"],
    2: ["दूसरी", "द्वितीय", "द्वितीयः"],
    3: ["तीसरी", "तृतीय", "तृतीयः"],
    4: ["चौथी", "चतुर्थ", "चतुर्थः"],
    5: ["पांचवीं", "पाँचवीं", "पंचम", "पञ्चम", "पञ्चमः"],
    6: ["छठी", "छठवीं", "षष्ठ", "षष्ठः"],
    7: ["सातवीं", "सप्तम", "सप्तमः"],
    8: ["आठवीं", "अष्टम", "अष्टमः"],
    9: ["नौवीं", "नवमी", "नवम", "नवमः"],
    10: ["दसवीं", "दशम", "दशमः"],
    11: ["ग्यारहवीं", "एकादश", "एकादशः"],
    12: ["बारहवीं", "द्वादश", "द्वादशः"],
}
_DEVANAGARI_CLASS_ORDINAL_TO_NUM = {
    word: num for num, words in HINDI_SANSKRIT_CLASS_ORDINALS.items() for word in words
}

# A trailing \b doesn't work here: Python's re only treats Unicode General
# Category L*/Nd/Pc as \w, so a Devanagari word ending in a vowel-sign/
# anusvara/visarga (Mc/Mn categories -- e.g. "ग्यारहवीं" ends in अं, ANUSVARA,
# Mn) has no \w-to-non-\w transition at its own end, and \b silently never
# matches there at all. Used everywhere below instead of \b: matches
# end-of-string or the next character NOT being a "continues the word"
# character (letter/digit/combining mark), so it can't falsely allow a
# longer Devanagari word to match as if it were a shorter table entry
# either.
_DEV_WORD_END = r"(?=[^\w\u0900-\u097F]|$)"

# "कक्षा" followed (optionally through a hyphen/colon/dash separator) by
# Devanagari digits, Arabic digits, or a Roman numeral -- e.g. "कक्षा ९",
# "कक्षा - 11", "कक्षा (XI)".
_DEVANAGARI_CLASS_DIGIT_RE = re.compile(
    r"कक्षा\s*[-:–—(]?\s*([०-९]{1,2}|\d{1,2}|[IVXLCDM]+)" + _DEV_WORD_END, re.I)
# "कक्षा" followed by an ordinal word (e.g. "कक्षा ग्यारहवीं", "कक्षा दशमः") --
# matched separately since the words themselves (not a numeric pattern) are
# what identify the class here. Longest-first so "दशम" doesn't shadow-match
# a prefix of some longer, unlisted ordinal form.
_DEVANAGARI_CLASS_ORDINAL_RE = re.compile(
    r"कक्षा\s*[-:–—(]?\s*(" +
    "|".join(re.escape(w) for w in sorted(_DEVANAGARI_CLASS_ORDINAL_TO_NUM, key=len, reverse=True)) +
    r")" + _DEV_WORD_END)

# NCERT Sanskrit-medium textbooks don't use "कक्षा" (Hindi) at all -- their
# own cover pages instead compound a Sanskrit ordinal STEM directly onto
# "वर्ग" ("class/group") with a case ending, as one word, e.g.
# "द्वादशवर्गाय संस्कृतस्य पाठ्यपुस्तकम्" ("Sanskrit Textbook For The Twelfth
# Class") for Class 12 -- confirmed against a real cover page. These are
# compounding-form stems (no visarga/case-ending of their own, since the
# case ending belongs to "वर्ग", not the stem), a different (shorter) set
# of spellings than HINDI_SANSKRIT_CLASS_ORDINALS' own declined/independent
# forms above, so this is kept as its own small table rather than reusing
# that one.
_SANSKRIT_VARGA_STEM_TO_NUM = {
    "प्रथम": 1, "द्वितीय": 2, "तृतीय": 3, "चतुर्थ": 4,
    "पञ्चम": 5, "पंचम": 5, "षष्ठ": 6, "सप्तम": 7, "अष्टम": 8,
    "नवम": 9, "दशम": 10, "एकादश": 11, "द्वादश": 12,
}
# No separator/whitespace between the stem and "वर्ग" -- it's a genuine
# compound word, not two separate tokens -- and no _DEV_WORD_END check
# after "वर्ग" either, since a case ending (-आय, -स्य, -ः, ...) always
# follows directly and is part of the same word.
_SANSKRIT_VARGA_CLASS_RE = re.compile(
    "(" + "|".join(re.escape(s) for s in sorted(_SANSKRIT_VARGA_STEM_TO_NUM, key=len, reverse=True)) + ")वर्ग")


# Matches "Class <roman numeral>" or "Class <1-2 digit number>" in English
# prelims/OCR text. Used both over the real text layer (parse_book_title_and_
# _class) and over whole-page OCR text (_ocr_recover_class) -- the latter has
# no guarantee that the "class" match found is anywhere near the actual class
# marking, since a whole prelims page can also contain prices, ISBN
# fragments, office phone numbers, or OCR noise that happens to sit near the
# literal word "class". NCERT only spans classes 1-12 (same invariant as
# HINDI_SANSKRIT_CLASS_ORDINALS above), so any match resolving outside that
# range is never a genuine class marking and must be skipped rather than
# accepted -- e.g. a real bug this guarded against: a Class 12 Hindi book's
# whole-page OCR text contained an unrelated two-digit number near the word
# "class" and was previously accepted verbatim as klass="72".
_ENGLISH_CLASS_RE = re.compile(r"class\s+([IVXLCDM]+|\d{1,2})\b", re.I)


def _english_class_match(text: str) -> Optional[str]:
    """Returns the class number as a string for the first "class <numeral>"
    match in `text` that resolves to a plausible NCERT class (1-12),
    skipping over any earlier match whose number falls outside that range
    instead of accepting it. Roman-numeral matches (I-XII) are always in
    range by construction (ROMAN_MAP only defines up to XII); this mainly
    guards the bare-digit branch, which has no such built-in ceiling."""
    for m in _ENGLISH_CLASS_RE.finditer(text):
        grp = m.group(1).upper()
        if grp in ROMAN_MAP:
            num = ROMAN_MAP[grp]
        elif grp.isdigit():
            num = int(grp)
        else:
            continue
        if 1 <= num <= 12:
            return str(num)
    return None


# --------------------------------------------------------------------------
# Out-of-range "near miss" detection
#
# The 1-12 bound above correctly stops a bogus two-digit number (a price, an
# ISBN fragment, ...) from being accepted as a class. But when the ONLY
# "class"/"कक्षा" + digit match on a whole-page OCR pass IS out of range,
# that's usually not unrelated noise -- it's the real marking, misread.
# Tesseract's classic '1'/'7' digit confusion at low render resolution is
# exactly this shape: a genuine "12" comes back as "72", which the bound
# correctly refuses to accept, but simply giving up leaves klass="unknown"
# for a book that IS legibly marked. These two helpers only ever answer
# "does it look like a genuine marking sat here and got misread?" -- they
# never resolve or return a class value themselves, so they can't change
# what _match_devanagari_class()/_english_class_match() ever accept as a
# real class. _ocr_recover_class() uses them purely to decide whether a
# retry at higher render resolution is worth attempting on the SAME page
# before moving on, rather than to assign klass.
def _devanagari_digit_near_miss(text: str) -> bool:
    m = _DEVANAGARI_CLASS_DIGIT_RE.search(text)
    if not m:
        return False
    grp = m.group(1)
    if grp.upper() in ROMAN_MAP:
        return False  # roman numerals here are always in range already
    if all(ch in DEVANAGARI_DIGIT_MAP for ch in grp):
        candidate = "".join(str(DEVANAGARI_DIGIT_MAP[ch]) for ch in grp)
    else:
        candidate = grp
    return candidate.isdigit() and not (1 <= int(candidate) <= 12)


def _english_class_near_miss(text: str) -> bool:
    for m in _ENGLISH_CLASS_RE.finditer(text):
        grp = m.group(1).upper()
        if grp in ROMAN_MAP:
            continue  # always in range already
        if grp.isdigit() and not (1 <= int(grp) <= 12):
            return True
    return False


def _match_devanagari_class(text: str) -> Optional[str]:
    """Returns the class number as a string if `text` contains a "कक्षा ..."
    or Sanskrit "<ordinal>वर्ग..." class marking, else None. Tries the
    "कक्षा"-digit form first (cheapest, unambiguous when present), then the
    "कक्षा"-ordinal-word table, then the Sanskrit वर्ग-compound form."""
    m = _DEVANAGARI_CLASS_DIGIT_RE.search(text)
    if m:
        grp = m.group(1)
        if all(ch in DEVANAGARI_DIGIT_MAP for ch in grp):
            # Devanagari digits are positional, same as Arabic ("११" = 1,1
            # -> "11"), so converting digit-by-digit and concatenating the
            # resulting characters (not summing them) is correct here.
            candidate = "".join(str(DEVANAGARI_DIGIT_MAP[ch]) for ch in grp)
        elif grp.upper() in ROMAN_MAP:
            candidate = str(ROMAN_MAP[grp.upper()])
        else:
            candidate = grp  # already plain Arabic digits
        # Same 1-12 sanity bound as _english_class_match: NCERT only spans
        # classes 1-12, so a "कक्षा"-digit match resolving outside that
        # range is OCR/regex noise, not a real class marking -- fall
        # through to the ordinal-word/वर्ग-compound checks below instead of
        # returning it.
        if candidate.isdigit() and 1 <= int(candidate) <= 12:
            return candidate
    m = _DEVANAGARI_CLASS_ORDINAL_RE.search(text)
    if m:
        return str(_DEVANAGARI_CLASS_ORDINAL_TO_NUM[m.group(1)])
    m = _SANSKRIT_VARGA_CLASS_RE.search(text)
    if m:
        return str(_SANSKRIT_VARGA_STEM_TO_NUM[m.group(1)])
    return None


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


# --------------------------------------------------------------------------
# Unicode Normalization Layer (Stabilization Sprint)
# --------------------------------------------------------------------------
# Deliberately a SEPARATE, minimal constant from compiler/normalization.py's
# own _INVISIBLE_CHARS_TABLE rather than an import from it: compiler/ is a
# later phase built ON TOP OF this module's output (extraction is the
# earlier/lower layer), so this module must never depend upward on
# compiler/. compiler/normalization.py's own layer additionally does
# NFKC + casefold + smart-quote/dash-to-ASCII translation to build an
# internal, non-display *lookup key* -- explicitly NOT what belongs at
# raw-extraction time, where the goal is the opposite: preserve the
# printed text exactly (script, punctuation, and all) while only removing
# characters that carry no visible/semantic content of their own and
# canonicalizing equivalent Unicode representations of the SAME text.
#
# NFC (not NFKC): NFC only canonically composes/decomposes to one
# consistent representation of the *same* character (e.g. a precomposed
# vs. combining-mark-decomposed form of the same accented letter always
# normalize to the same codepoints) -- it never maps a "compatibility"
# variant onto a different, cosimplified base character the way NFKC can
# (e.g. NFKC would fold certain ligatures/fullwidth forms in ways that
# alter a script's own presentation; NFC does not). This is the safe
# choice for raw, language-preserving extracted text.
_INVISIBLE_TEXT_CHARS = (
    "\u00ad"   # SOFT HYPHEN
    "\u200b"   # ZERO WIDTH SPACE
    "\u200e"   # LEFT-TO-RIGHT MARK
    "\u200f"   # RIGHT-TO-LEFT MARK
    "\u2060"   # WORD JOINER
    "\ufeff"   # ZERO WIDTH NO-BREAK SPACE / BOM
)
_INVISIBLE_TEXT_TABLE = {ord(c): None for c in _INVISIBLE_TEXT_CHARS}
# NOTE: zero-width joiner/non-joiner (U+200C/U+200D) are deliberately NOT
# in this table (unlike compiler/normalization.py's lookup-key layer,
# which strips them for matching purposes) -- in several Indic scripts
# (e.g. Bengali, Devanagari conjunct control) they are meaningful,
# rendering-affecting characters, not incidental artifacts, at the raw
# display-text layer. Removing them here would be exactly the kind of
# language-altering change this sprint prohibits.


def clean_extracted_text(text: str) -> str:
    """Deterministic, language-preserving Unicode cleanup applied to every
    line of raw extracted text (see extract_lines() below), independent
    of script/language: NFC normalization (canonicalizes equivalent
    Unicode representations of the SAME text -- never alters which
    characters/language are present) + stripping a small set of
    genuinely invisible/zero-content characters an OCR pass or a PDF's
    text layer can leave behind (BOM, soft hyphen, zero-width space,
    directional marks, word joiner). Never transliterates, never
    romanizes, never touches a single visible character of any script.
    Safe on already-clean text (idempotent) and never raises -- degrades
    to the original string on any unexpected input.
    """
    if not text:
        return text
    try:
        cleaned = unicodedata.normalize("NFC", text)
        cleaned = cleaned.translate(_INVISIBLE_TEXT_TABLE)
        return cleaned
    except Exception:
        return text


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
                text = clean_extracted_text(text)
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

    # A genuine wrapped heading (one heading's text split across two physical
    # PDF lines) continues at -- or very near -- the same left margin as the
    # line above it; that's what makes it recognizable as a *continuation*
    # rather than unrelated text. Without any x-position check here, this
    # heuristic can't tell a real wrap apart from two fragments that simply
    # happen to be bold/large and vertically close -- e.g. a multi-column
    # TOC table, where a row's label ("Chapter One"), title, and page number
    # sit in three widely separated x-columns, and the NEXT row's label
    # starts back at the left margin again. That shape was being merged into
    # one Line spanning two-plus entire TOC rows (row N's page number fused
    # to row N+1's label, etc.), silently corrupting the table before TOC
    # detection ever saw it. Real same-column wraps keep x0 essentially
    # fixed; jumping ~hundreds of points to a different column and back is
    # never a legitimate continuation, so it's excluded here.
    _MAX_WRAP_X0_DRIFT = 20.0

    def x0_continues(a: Line, b: Line) -> bool:
        return abs(a.bbox[0] - b.bbox[0]) <= _MAX_WRAP_X0_DRIFT

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
               and x0_continues(cur, lines[j])
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


# T3 -- chapter title / front-matter boundary detection.
#
# The chapter's front matter (title, subtitle, opening illustration credit,
# epigraph, ...) ends and real body content begins at the first line that
# reads like an actual paragraph sentence: body-sized, and long/punctuated
# like prose rather than a heading or caption. That point is the real
# boundary a title search should respect -- not a fixed page count, which
# either cuts off a title that happens to start past page 1 (an opening
# illustration on its own page, an epigraph on the next) or, just as
# often, lets an in-body callout/subtopic heading (e.g. a highlighted
# "Sorting" box partway into the chapter) compete with the real title
# just because it also happens to fall within an arbitrary page cutoff.
_MIN_BODY_PROSE_LEN = 40


def _looks_like_body_prose(line: "Line", body_size: float) -> bool:
    text = line.text.strip()
    return (
        len(text) >= _MIN_BODY_PROSE_LEN
        and text[-1] in ".!?"
        and line.size <= body_size * 1.15
    )


# Bounds how many pages the boundary search itself will look through before
# giving up (not a title-location cutoff -- see above). A chapter's
# decorative opening region realistically never runs longer than this;
# bounding the search keeps a chapter with unusually short/atypical
# sentences (so no line is ever recognized as body prose) from having its
# entire page range treated as "still front matter."
_MAX_TITLE_SEARCH_PAGES = 6


def _front_matter_boundary(lines: List["Line"], body_size: float, repeated: set) -> Tuple[int, float]:
    for l in lines:
        if l.page > _MAX_TITLE_SEARCH_PAGES:
            break
        if l.text in repeated:
            continue
        if _looks_like_body_prose(l, body_size):
            return l.page, l.y
    return _MAX_TITLE_SEARCH_PAGES, float("inf")


def detect_chapter_title(lines: List[Line], body_size: float, repeated: set) -> Tuple[str, Optional[Line]]:
    """Returns (title_text, title_line). title_line (not just its text) is
    kept so the caller can check the FONT that specific line was set in --
    same reasoning as parse_book_title_and_class's own title_line: a
    chapter opening page can be set in a legacy non-Unicode Hindi/Sanskrit
    font (see language_detector.detect_legacy_devanagari_font), in which
    case title_text is glyph-code noise and the caller needs the Line's
    bbox/page/font to attempt OCR recovery, not just the raw text."""
    boundary_page, boundary_y = _front_matter_boundary(lines, body_size, repeated)
    candidates = [l for l in lines
                  if l.text not in repeated
                  and (l.page < boundary_page or (l.page == boundary_page and l.y < boundary_y))
                  and l.size > body_size * 1.3
                  and not re.fullmatch(r"chapter\s*\d+", l.text.strip(), re.I)
                  # Exclude bare chapter-number graphics ("1", "12", "IV", ...).
                  # These are frequently typeset in a much larger font than the
                  # real title next to them, so without this guard the
                  # "biggest font wins" heuristic below picks the numeral
                  # itself as the chapter_title instead of the actual title.
                  and not _PURE_NUMERAL_RE.match(l.text.strip())
                  # Exclude a lone decorative drop-cap letter (see
                  # _DROP_CAP_RE's docstring) -- same reasoning as the
                  # numeral guard above, for the same "biggest font wins"
                  # heuristic, one line down.
                  and not _DROP_CAP_RE.match(l.text.strip())]
    if not candidates:
        return "untitled-chapter", None
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
    return pick_from[0].text.strip(), pick_from[0]


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
    """Deterministic, script-preserving slug.

    Stabilization Sprint fix: the previous implementation
    (`re.sub(r"[^a-z0-9]+", "-", raw)`) kept ONLY ASCII a-z/0-9 -- any
    part written in a non-Latin script (Devanagari, Tamil, ...) had every
    character stripped, collapsing to "" and falling back to the literal
    string "untitled" for every such title. Since make_id()/make_urn()
    and every book/chapter folder-name call site are layered on this
    function, that silently produced (a) folder/file names that lost the
    book's actual language entirely, and (b) hash collisions: two
    DIFFERENT non-Latin titles both slugified to the same leftover ASCII
    fragments (or nothing at all) and therefore hashed to the same id.

    Fix: normalize to NFC (canonical composition -- keeps a script's
    precomposed forms stable without altering the language), then keep
    every Unicode LETTER, MARK, and NUMBER character (categories L*, M*,
    N*) -- letters covers any script, MARKS is essential for Indic
    scripts, where a combining vowel sign / virama (category Mn/Mc, e.g.
    the sign making "कि" out of "क" + "ि", or the virama forming a
    conjunct like "ज्ञ") is not itself alphanumeric but must never be
    treated as a separator, or the word visually fragments into
    disconnected consonants. Every other character (whitespace,
    punctuation, OS-reserved path characters / \\ : * ? " < > |, ...) is
    collapsed to a single '-'. Never romanizes, transliterates, or drops
    a script's own characters. Falls back to "untitled" only when a part
    is genuinely empty after normalization -- the same "no content at
    all" case the old code handled.
    """
    raw = "_".join(str(p).strip() for p in parts if p and str(p).strip())
    if not raw:
        return "untitled"
    raw = unicodedata.normalize("NFC", raw).lower()

    out: List[str] = []
    prev_was_sep = True  # avoid a leading '-'
    for ch in raw:
        if unicodedata.category(ch)[0] in ("L", "M", "N"):
            out.append(ch)
            prev_was_sep = False
        elif not prev_was_sep:
            out.append("-")
            prev_was_sep = True

    slug = "".join(out).rstrip("-")
    return slug or "untitled"


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


def _display_subject(subject: str) -> str:
    """Canonicalizes a resolved subject into the properly-cased form used
    everywhere metadata is displayed (JSON document.subject, manifests,
    runtime logs) -- e.g. "accountancy" -> "Accountancy", "political
    science" -> "Political Science", "computer-science" -> "Computer
    Science".

    Root cause this fixes: KNOWN_SUBJECTS (just below) and every match
    against it are deliberately all-lowercase -- that's an internal
    matching vocabulary, not display text, and one entry ("computer-
    science") only exists in hyphenated form to match filenames/folder
    names. Both places that resolve a subject via this vocabulary
    (parse_book_title_and_class()'s "textbook in X for class Y" regex,
    whose captured group is also lowercased for the same
    consistent-matching reason, and auto_detect_subject() below) used to
    return that lowercase matching key AS the canonical subject too,
    which is where "Accountancy" first became "accountancy" -- silently,
    at the very origin of the metadata, before any downstream code (or
    the runtime log) ever saw it.

    The "unknown" sentinel is deliberately left untouched: every caller
    across this module and pipeline.py compares against the literal
    lowercase string "unknown" (see e.g. pipeline.py's
    `book_ctx.subject == "unknown"` fallback-chain gate) -- title-casing
    it to "Unknown" would silently break every one of those checks.
    """
    if subject == "unknown":
        return subject
    return subject.replace("-", " ").title()


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
        return _display_subject(found)
    found = _search(first_page_text.lower())
    if found:
        return _display_subject(found)
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


# Phase 1 Final Metadata Architecture Refinement: the generic "Part <N>" /
# "Volume <N>" / "Book <N>" phrasing NCERT prints on the cover of any
# subject that ships in more than one part (Mathematics Part I/II, Themes
# in Indian History Part I/II/III, ...). Deliberately generic -- matches
# the *pattern*, never a specific subject or title -- so it works across
# the whole corpus without hardcoding.
_PART_VOLUME_RE = re.compile(r"^\s*(Part|Volume|Book)\s+([IVXLCDM]+|\d{1,2})\s*$", re.I)
_EDITION_RE = re.compile(r"\b(\d{4})\s+Edition\b|\bEdition\s*[:\-]?\s*(\d{4})\b", re.I)


def parse_cover_metadata(lines: List[Line], body_size: float, repeated: set, book_title: str) -> Dict[str, Optional[str]]:
    """Extracts the secondary, DISTINGUISHING cover-page metadata that can
    sit alongside the main title on the title page -- subtitle, Part/
    Volume/Book number, edition -- the metadata NCERT itself uses to tell
    apart multiple books that share the same main cover title (e.g. two
    "Accountancy" books: one "Partnership Accounts", one "Company
    Accounts and Analysis of Financial Statements").

    Generic by construction: nothing here is keyed off a specific subject,
    title, or NCERT book name -- only font-size/position heuristics
    (mirrors parse_book_title_and_class's own approach) and the generic
    "Part/Volume/Book <numeral>" phrasing. Never touches `book_title`
    itself; every field returned is independently preserved, never
    concatenated together.

    Returns {"subtitle": ..., "part": ..., "volume": ..., "edition": ...},
    each a string or None. A missing prelims/title page (or a book with no
    such distinguishing metadata printed at all -- the common case)
    returns all four as None, which is exactly what callers should expect
    for the vast majority of single-part NCERT books.
    """
    page0 = [l for l in lines if l.page == 0 and l.text not in repeated]

    part = volume = None
    for l in page0:
        m = _PART_VOLUME_RE.match(l.text.strip())
        if m:
            kind, value = m.group(1).capitalize(), m.group(2).upper()
            if kind == "Volume":
                volume = f"Volume {value}"
            else:
                # "Part" and "Book" (as in "Book 1 of 2") both distinguish
                # a book from its siblings the same way; keep them in
                # separate fields only when both happen to be present.
                part = f"{kind} {value}"

    edition = None
    for l in page0:
        m = _EDITION_RE.search(l.text)
        if m:
            year = m.group(1) or m.group(2)
            edition = f"{year} Edition"
            break

    # Subtitle: text on the title page that visually sits in the same
    # "big font, not body text" tier as the title itself, is NOT the
    # title line, and isn't already accounted for as Part/Volume/edition
    # or the "Textbook ... for Class ..." / "Class <N>" phrasing
    # parse_book_title_and_class already treats as class/subject metadata.
    title_lower = book_title.strip().lower()
    title_size = next((l.max_size for l in page0 if l.text.strip().lower() == title_lower), None)
    subtitle_parts = []
    if title_size is not None:
        for l in sorted(page0, key=lambda x: x.y):
            text = l.text.strip()
            if not text or text.lower() == title_lower:
                continue
            if _PART_VOLUME_RE.match(text) or _EDITION_RE.search(text):
                continue
            if re.search(r"class\s+([IVXLCDM]+|\d{1,2})\b", text, re.I):
                continue
            if re.search(r"textbook\s+in\s+.+\s+for\s+class", text, re.I):
                continue
            # Same "clearly bigger than body text" band parse_book_title_and_class
            # uses for the title itself, just capped below the title's own
            # size so the subtitle can never outrank (or duplicate) it.
            if body_size * 1.15 <= l.max_size < title_size:
                subtitle_parts.append(text)

    subtitle = " ".join(subtitle_parts).strip() or None

    return {"subtitle": subtitle, "part": part, "volume": volume, "edition": edition}


def parse_book_title_and_class(lines: List[Line], body_size: float, repeated: set):
    page0 = [l for l in lines if l.page == 0 and l.text not in repeated]
    big = [l for l in page0 if l.max_size >= body_size * 1.5]
    # `title_line` (not just its text) is kept so the caller can check
    # the FONT that specific line was set in -- prelims pages routinely
    # mix a legacy Devanagari font with plain Arial/Latin lines on the
    # very same page, so "any font anywhere in the PDF" is too broad a
    # signal for whether THIS line's text is trustworthy; the title
    # line's own font is the precise one that matters.
    title_line = max(big, key=lambda l: l.max_size) if big else None
    book_title = title_line.text.strip() if title_line else "untitled-book"

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
        english_class = _english_class_match(l.text)
        if english_class:
            klass = english_class
        elif klass == "unknown":
            # Hindi/Sanskrit prelims mark the class as "कक्षा ..." rather
            # than the English word -- see _match_devanagari_class.
            devanagari_class = _match_devanagari_class(l.text)
            if devanagari_class:
                klass = devanagari_class
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
            english_class = _english_class_match(joined_text)
            if english_class:
                klass = english_class
            else:
                devanagari_class = _match_devanagari_class(joined_text)
                if devanagari_class:
                    klass = devanagari_class
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
    return book_title, _display_subject(subject), klass, title_line


def _is_contents_heading(text: str) -> bool:
    """True for a conventional English/keyword-style "Contents" heading
    line ("Contents", "Contents iii", "CONTENTS PAGE", "Table of
    Contents", ...).

    T1 (generic structural TOC detection): this is now used ONLY as one
    optional confidence booster inside find_toc_lines() -- never as the
    thing that gates detection. A book whose TOC heading is "Index",
    "विषय सूची", "अनुक्रमणिका", or has no heading line at all must be
    detected purely from row structure; this function only ever *helps*
    (lets a shorter run of entries qualify) and is never required. Kept
    narrow/English-only deliberately: broadening it with more languages
    would still leave every language not on the list unsupported, which
    is exactly the keyword-list dependency T1 replaces with structural
    signals that work regardless of script.
    """
    t = text.strip().lower()
    return t.startswith("content") or t == "table of contents"


# --------------------------------------------------------------------------
# T1 -- structural TOC-row signals
# --------------------------------------------------------------------------
# A TOC row is recognized by its SHAPE, not its language: "<title text>
# <page number>", usually joined by either a leading item number
# ("1.  Real Numbers  1") or a dotted/spaced leader ("Introduction ... 1").
# Both signals are script-agnostic because they key off ASCII digits/dots,
# which every NCERT layout uses for numbering and page numbers regardless
# of the language the title itself is printed in.
_TRAILING_NUMERIC_TOKEN_RE = re.compile(r"^\d{1,4}$")
_TRAILING_ROMAN_TOKEN_RE = re.compile(r"^[ivxlcdm]{1,6}$", re.I)
# Leading item numbering: an optional single label word (any script --
# same `[^\d\s]+` reasoning as TOC_ENTRY_RE above), then a number, then the
# rest of the row. Digits are the signal; the label/title text is never
# inspected for a specific word.
# Same separator broadening as TOC_ENTRY_RE: NCERT prelims frequently use
# "1- Title" (hyphen) instead of "1. Title" (period) for chapter numbering,
# so the separator class here must accept both (plus colon/close-paren)
# rather than only a literal period.
_LEADING_NUM_RE = re.compile(r"^(?:[^\d\s]+\s+)?(\d+)(?:\.\d+)*[.\-:)]?\s+\S")
# NCERT chapter/section numbering never reaches three digits, but copyright
# pages are full of "<Month> <Year> <Saka/Vikram month> <Year>" edition-history
# lines (e.g. "May 2007 Jyaistha 1929", "September 2021 Bhadrapada 1943") that
# otherwise satisfy the same "label word + number + rest" shape as a genuine
# TOC row like "9. Financial Management". Any 3+ digit leading number is a
# year, not a chapter/section number, so it is excluded here.
_MAX_PLAUSIBLE_TOC_NUMBER = 200
# 3+ literal periods, with or without interleaving spaces -- the printed
# "dotted leader" connecting a title to its page number.
_DOTTED_LEADER_RE = re.compile(r"(?:\.\s*){3,}")


def _trailing_page_token(text: str) -> Optional[str]:
    """The row's final whitespace-delimited token, if (and only if) it is
    plausibly a page number (1-4 digits, or a short roman numeral for
    front-matter pages) AND there is real title text before it (>=3
    characters once trailing punctuation is stripped) -- so a bare
    standalone page number, or a one-word line that happens to end in a
    roman-numeral-shaped word, doesn't count on its own."""
    stripped = text.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return None
    last = tokens[-1]
    if not (_TRAILING_NUMERIC_TOKEN_RE.fullmatch(last) or _TRAILING_ROMAN_TOKEN_RE.fullmatch(last)):
        return None
    body = " ".join(tokens[:-1]).strip(" .")
    if len(body) < 3:
        return None
    return last


def _has_leading_number(text: str) -> bool:
    m = _LEADING_NUM_RE.match(text.strip())
    if not m:
        return False
    return int(m.group(1)) < _MAX_PLAUSIBLE_TOC_NUMBER


def _has_dotted_leader(text: str) -> bool:
    return bool(_DOTTED_LEADER_RE.search(text))


def _is_strong_toc_row(line: "Line") -> bool:
    """A row with BOTH a trailing page-number-shaped token AND (leading
    item numbering OR a dotted leader) -- the two structural shapes a
    genuine TOC entry takes across the corpus. Requiring both, rather
    than a trailing number alone, is what keeps a heading line like
    "Contents iii" (trailing roman numeral, no numbering/leader) or a
    stray "...for Class X" cover line from being mistaken for an entry."""
    return _trailing_page_token(line.text) is not None and (
        _has_leading_number(line.text) or _has_dotted_leader(line.text)
    )


def _is_weak_toc_row(line: "Line") -> bool:
    """Fallback row shape for TOCs that number entries with words instead
    of digits (e.g. Sanskrit ordinals like "prathamah pathah" / "first
    lesson" rather than "1."): a trailing ARABIC-digit page number with
    real title text before it, and nothing else required. Deliberately
    narrower than `_is_strong_toc_row`'s trailing-token check (which also
    accepts a trailing roman numeral) because NCERT prelims consistently
    print front-matter page references (Foreword, Preface, ...) with
    roman-numeral page numbers and chapter entries with Arabic ones --
    restricting to Arabic digits is what keeps this fallback from
    scooping up front-matter lines that have no numbering of their own
    at all. Only ever used as a second pass, after the strict
    leading-number/dotted-leader pass has already come back empty."""
    tok = _trailing_page_token(line.text)
    return tok is not None and _TRAILING_NUMERIC_TOKEN_RE.fullmatch(tok) is not None


def _sequential_trailing_numbers(run: List["Line"]) -> bool:
    """Analogous to `_sequential_leading_numbers` but keyed off each row's
    trailing (Arabic-digit) page number instead of a leading item number --
    the only ordering signal available for a word-numbered TOC. A genuine
    chapter listing's page numbers strictly increase down the page; this
    is what distinguishes such a listing from an arbitrary run of unrelated
    sentences that each happen to end in a number."""
    nums = []
    for l in run:
        tok = _trailing_page_token(l.text)
        if tok and _TRAILING_NUMERIC_TOKEN_RE.fullmatch(tok):
            nums.append(int(tok))
    if len(nums) < 2:
        return False
    return all(b > a for a, b in zip(nums, nums[1:]))


def _is_heading_shaped(line: "Line") -> bool:
    """Generic (keyword-independent) shape check for "this line reads
    like a section heading, not body prose, and not a TOC row itself":
    short, and not ending in sentence punctuation. Matches "Contents",
    "Index", "विषय सूची", "अनुक्रमणिका", or any other language's TOC
    heading purely by shape -- no word list involved. A real "Contents"/
    "Index"-style keyword match is folded in as an OR so an actual
    keyword still counts (a confidence booster, per T1's requirement),
    but it is never required to reach True."""
    text = line.text.strip()
    if not text or len(text) > 60:
        return False
    if _is_strong_toc_row(line):
        return False
    if text[-1] in ".,;:?!":
        return False
    return True


def _sequential_leading_numbers(run: List["Line"]) -> bool:
    """True if the leading item numbers across a candidate run form a
    strictly increasing sequence (1, 2, 3, ... -- not necessarily by 1,
    since sub-numbered/skipped entries are fine) -- a structural signal
    that rows belong to one ordered listing, independent of language."""
    nums = []
    for l in run:
        m = re.match(r"^(?:[^\d\s]+\s+)?(\d+)", l.text.strip())
        if m:
            nums.append(int(m.group(1)))
    if len(nums) < 2:
        return False
    return all(b > a for a, b in zip(nums, nums[1:]))


def _page_numbers_aligned(run: List["Line"]) -> bool:
    """True if the rows' right edges (where a right-aligned page-number
    column would sit) fall within a tight band of each other -- the
    "alignment of page numbers" structural signal. Best-effort: on real
    PDFs bbox varies row to row for a genuine TOC page-number column;
    this simply never blocks acceptance when bbox data isn't
    discriminating (e.g. synthetic/degenerate input)."""
    right_edges = [l.bbox[2] for l in run if l.bbox]
    if len(right_edges) < 2:
        return False
    spread = max(right_edges) - min(right_edges)
    widest = max(1.0, max(right_edges))
    return (spread / widest) <= 0.15


_MIN_RUN_WITH_HEADING_ANCHOR = 1
_MIN_RUN_WITH_STRUCTURAL_BONUS = 2
_MIN_RUN_NO_ANCHOR = 3

# T2 -- multi-page TOC continuation.
#
# Real multi-page TOCs are almost never perfectly contiguous rows of entries
# start to finish: the page break between TOC page 1 and TOC page 2 nearly
# always carries a small non-entry artifact -- a repeated running header
# ("Contents", "Contents (Contd.)", a unit divider like "UNIT II"), or a
# stray footer/page-number line for the TOC page itself -- sitting between
# the two blocks of entries. `find_toc_lines`'s run-detection loop only
# ever looks at row SHAPE, so it correctly stops the moment it hits one of
# these, and used to return that first run immediately, which is exactly
# why extraction silently stopped after the first TOC page: chapters
# printed on every subsequent page were simply never looked at.
#
# `_MAX_CONTINUATION_GAP` bounds how many non-entry filler lines are
# allowed between two entry blocks before they're treated as unrelated
# (e.g. the TOC ending and real prose -- a Preface, a Foreword -- starting).
# It is deliberately small and content-blind (no keyword list, no assumed
# page count): a run of entries resuming within a few short/non-prose
# lines of the previous block is accepted as a continuation of the SAME
# TOC regardless of language or layout; a prose line encountered before
# any entry resumes ends the search immediately, so a real Preface/
# Foreword section is never merged in.
_MAX_CONTINUATION_GAP = 6


def _is_gap_filler(line: "Line", is_row=_is_strong_toc_row) -> bool:
    """True for a line that could plausibly sit BETWEEN two TOC entries/
    pages without itself being a TOC entry: a stray page-footer number/
    roman numeral on its own, a wrapped sub-item continuation line with
    no page number of its own (e.g. a "(b) Second Poem" line following
    "1. Poet Name (a) First Poem 12", still part of the same numbered
    entry), or any other short, non-prose (heading-shaped) line such as a
    repeated running header or a unit/section divider. Never a
    requirement of a specific word -- purely shape-based, same principle
    as `_is_heading_shaped`.

    `is_row` is the row-shape predicate currently being used to find TOC
    entries (`_is_strong_toc_row` for the primary pass, `_is_weak_toc_row`
    for the word-numbered fallback pass) -- a line that already qualifies
    as an entry under that predicate is never gap filler, it's the next
    real row.

    A line that itself reads as a NEW "Contents"/"Index"-style heading
    (e.g. a Part-II book's own TOC page also prints a "Contents (Part I)"
    reference block listing the companion volume's chapters, purely for
    the reader's convenience -- those chapters are not in this PDF) is
    deliberately excluded: it signals a second, separate table of
    contents starting, not a gap inside the current one, so it must end
    the continuation search rather than be skipped over."""
    text = line.text.strip()
    if _is_contents_heading(text):
        return False
    if not text:
        return True
    if is_row(line):
        return False
    if re.fullmatch(r"\d{1,4}", text) or re.fullmatch(r"[ivxlcdm]{1,6}", text, re.I):
        return True
    return _is_heading_shaped(line)


def _next_continuation_start(filtered: List["Line"], idx: int, is_row=_is_strong_toc_row) -> Optional[int]:
    """Looks ahead (bounded by `_MAX_CONTINUATION_GAP`) from `idx` for the
    next TOC-entry row (per `is_row`), skipping only gap-filler lines
    along the way. Returns that row's index, or None if a non-filler
    (prose) line is hit first, or the gap budget runs out before any
    entry resumes -- either way, "not a continuation of this TOC"."""
    k = idx
    gap = 0
    while k < len(filtered) and gap <= _MAX_CONTINUATION_GAP:
        if is_row(filtered[k]):
            return k
        if not _is_gap_filler(filtered[k], is_row):
            return None
        k += 1
        gap += 1
    return None


def _cluster_toc_rows(filtered: List["Line"]) -> List["Line"]:
    """Merge same-page Line objects whose y-ranges overlap into a single,
    left-to-right-ordered Line.

    Multi-column TOC layouts ("Chapter 9" | "Financial Management" | "215",
    tab-separated on one printed row) are frequently extracted by PyMuPDF as
    two or three SEPARATE Line objects -- one per text block -- even though
    their bboxes share the same y-range, because the wide horizontal gap
    between columns splits them into different blocks. Every downstream
    row-shape check (`_is_strong_toc_row` and friends) needs the chapter
    number, title, and page number together on one Line to recognize a TOC
    entry, so this reconstructs the visual row before any of that runs.
    Lines that already stand alone on their row pass through unchanged."""
    by_page: Dict[int, List["Line"]] = {}
    for l in filtered:
        by_page.setdefault(l.page, []).append(l)

    out: List["Line"] = []
    for pno in sorted(by_page):
        page_lines = by_page[pno]
        used = [False] * len(page_lines)
        for idx, l in enumerate(page_lines):
            if used[idx]:
                continue
            row = [l]
            used[idx] = True
            y0, y1 = l.bbox[1], l.bbox[3]
            for jdx in range(idx + 1, len(page_lines)):
                if used[jdx]:
                    continue
                cand = page_lines[jdx]
                cy0, cy1 = cand.bbox[1], cand.bbox[3]
                # Center-based comparison rather than a strict overlap ratio:
                # a lone page-number token (e.g. "1") is often reported with
                # a tighter/shorter bbox than the title text it sits beside
                # (font metrics, renderer differences), which can shrink an
                # overlap-ratio check below threshold for that one row even
                # though it's clearly printed on the same line. Comparing
                # vertical centers against a tolerance keyed off the
                # SMALLER line's own height is robust to that height
                # mismatch while still rejecting genuinely different rows.
                a_center, b_center = (y0 + y1) / 2, (cy0 + cy1) / 2
                tol = 0.6 * max(min(y1 - y0, cy1 - cy0), 1.0)
                if abs(a_center - b_center) <= tol:
                    row.append(cand)
                    used[jdx] = True
                    y0, y1 = min(y0, cy0), max(y1, cy1)
            if len(row) == 1:
                out.append(l)
                continue
            row.sort(key=lambda r: r.bbox[0])
            x0 = min(r.bbox[0] for r in row)
            x1 = max(r.bbox[2] for r in row)
            merged_text = "  ".join(r.text.strip() for r in row)
            out.append(Line(text=merged_text, size=l.size, max_size=max(r.max_size for r in row),
                             bold=any(r.bold for r in row), font=l.font, page=pno,
                             y=y0, page_height=l.page_height, bbox=(x0, y0, x1, y1)))
    out.sort(key=lambda r: (r.page, r.bbox[1]))
    return out


def _find_toc_block(filtered: List[Line], is_row, sequential_fn) -> List[Line]:
    """Shared run-finding logic behind `find_toc_lines`'s two passes: the
    strict pass (`is_row=_is_strong_toc_row`, `sequential_fn=
    _sequential_leading_numbers`) and the word-numbered fallback pass
    (`is_row=_is_weak_toc_row`, `sequential_fn=_sequential_trailing_numbers`).
    Identical logic driven off different row-shape/ordering predicates so
    both passes get the same run-qualification and multi-page-continuation
    behaviour for free.

    Building the initial run tolerates a bounded run of non-entry lines
    IN BETWEEN two qualifying rows (via `_next_continuation_start`), not
    just entry rows back-to-back: a multi-line TOC entry (e.g. "1. Poet
    Name (a) First Poem   12" followed by an unpaginated continuation row
    "(b) Second Poem" before the next numbered entry resumes) would
    otherwise end the run the moment the unpaginated continuation line is
    reached, even though the very next line is clearly still part of the
    same table of contents. The gap budget and gap-filler shape check are
    identical to the ones already used for merging entries split across a
    physical page break -- a same-page wrapped sub-item is structurally
    the same situation (a small non-entry gap between two real rows)."""
    n = len(filtered)
    i = 0
    while i < n:
        if not is_row(filtered[i]):
            i += 1
            continue

        j = i
        run: List[Line] = []
        while j < n:
            if not is_row(filtered[j]):
                nxt = _next_continuation_start(filtered, j, is_row)
                if nxt is None:
                    break
                j = nxt
                continue
            if run and run[-1].text == filtered[j].text:
                # Same duplicate-prevention as the continuation-merge loop
                # below: a restated "last row of this page" repeated verbatim
                # as the first row of the next page, with zero filler lines
                # between them (no blank line, header, or footer artifact
                # extracted at that particular page break), lands inside this
                # single contiguous run instead of going through
                # `_next_continuation_start`'s merge path -- so without this
                # check it was never deduplicated.
                j += 1
                continue
            run.append(filtered[j])
            j += 1

        # A generic heading-shaped line (any short, non-prose line) is only
        # ever a confidence booster once there's already a run of 2+ rows to
        # back it up (structural_bonus below). Letting it alone justify a
        # single-row run made ANY short line immediately followed by ANY
        # digit-shaped row look like a complete one-chapter TOC -- which is
        # exactly what front-matter boilerplate looks like ("New Delhi" /
        # signature date, "First Edition" / edition-history line). Only an
        # explicit Contents/Index-style keyword match is a strong enough
        # anchor to justify trusting a single row on its own.
        keyword_anchor = i > 0 and _is_contents_heading(filtered[i - 1].text)
        generic_anchor = i > 0 and _is_heading_shaped(filtered[i - 1])
        structural_bonus = sequential_fn(run) and _page_numbers_aligned(run)

        qualifies = (
            (keyword_anchor and len(run) >= _MIN_RUN_WITH_HEADING_ANCHOR)
            or len(run) >= _MIN_RUN_NO_ANCHOR
            or (structural_bonus and len(run) >= _MIN_RUN_WITH_STRUCTURAL_BONUS)
            or (generic_anchor and structural_bonus and len(run) >= _MIN_RUN_WITH_STRUCTURAL_BONUS)
        )
        if not qualifies:
            i = j
            continue

        merged: List[Line] = list(run)
        cursor = j
        while cursor < n:
            k = _next_continuation_start(filtered, cursor, is_row)
            if k is None:
                break
            k_end = k
            while k_end < n and is_row(filtered[k_end]):
                k_end += 1
            for l in filtered[k:k_end]:
                if merged and merged[-1].text == l.text:
                    continue  # duplicate-prevention at the page-break seam
                merged.append(l)
            cursor = k_end
        return merged

    return []


def find_toc_lines(lines: List[Line], repeated: set) -> List[Line]:
    """T1 -- generic structural TOC-page detection, T2 -- multi-page merge.

    Detects a table-of-contents block by row SHAPE (leading item
    numbering, trailing page-number tokens, dotted leaders, sequential
    numbering, page-number alignment) rather than by matching a heading
    keyword. A heading-shaped line immediately above a run of TOC-like
    rows (whether it's a recognized keyword like "Contents"/"Index" or
    an unrecognized one like "विषय सूची"/"अनुक्रमणिका", or any other
    short non-prose line) is treated purely as a confidence booster: its
    presence lets a shorter run of entries qualify, but a run of entries
    that's already long/consistent enough is detected with no heading
    line at all. Conversely, a heading keyword with no matching row
    structure after it is never enough on its own -- see the
    `_is_strong_toc_row`-gated run-search below, which only ever returns
    lines that themselves look like TOC rows.

    Once an initial qualifying run is found, any further block(s) of
    entry rows separated from it only by a small page-break-shaped gap
    (see `_next_continuation_start`) are merged in -- covering a TOC of
    arbitrary length across an arbitrary number of physical pages, in
    printed order, regardless of layout or language. A continuation
    block never has to independently pass the run-length bar the first
    block does (it's extending an already-established TOC, not proving
    one from scratch), so a final page with just one or two remaining
    chapters is still picked up. An entry row that exactly repeats the
    immediately preceding merged row (e.g. a "continued from..." restated
    line) is skipped, preventing a duplicate chapter entry at the seam.

    A second, weaker pass is ALSO always computed alongside the strict one:
    some TOCs (e.g. Sanskrit prelims that number chapters with ordinal
    words -- "prathamah pathah", "first lesson" -- instead of a digit)
    never carry any leading number or dotted leader for `_is_strong_toc_row`
    to key off at all. `_is_weak_toc_row` only requires a trailing
    ARABIC-digit page number, and the run still has to clear the same
    qualification bar (a long-enough run, or a strictly-increasing
    trailing-page-number sequence backing up a heading/short run) via
    `_sequential_trailing_numbers`, so this never fires on arbitrary prose
    that happens to end in a digit.

    Root-cause note (word-numbered-TOC regression): this used to return the
    strict pass's result unconditionally the moment it was non-empty, on
    the assumption that ANY strict match must be the real TOC. That's true
    for the common case, but a book whose main chapter listing is
    word-numbered (so only the weak pass can ever find it) can still have
    a short, unrelated digit-numbered list elsewhere ON THE SAME TOC PAGE
    -- e.g. an appendix sub-list like "1. Metre ... 102 / 2. Figures of
    Speech ... 107 / 3. Recommended Books ... 112" -- that independently
    satisfies `_is_strong_toc_row` and clears the same run-length bar
    entirely on its own. Returning on that match immediately meant the
    weak pass -- the only one that could ever find the book's real,
    word-numbered chapter list -- was never even attempted, and the
    3-entry appendix fragment was reported as "the table of contents"
    instead of the 10+ actual chapters. Both passes are now always run,
    and whichever finds the LONGER contiguous TOC-shaped block wins: a
    book's real chapter listing is virtually always substantially longer
    than an incidental short numbered aside elsewhere on the page, so run
    length is a robust, purely structural tiebreaker that doesn't require
    knowing anything about either list's content or language.
    """
    filtered = [l for l in lines if l.text not in repeated]
    filtered = _cluster_toc_rows(filtered)

    strict = _find_toc_block(filtered, _is_strong_toc_row, _sequential_leading_numbers)
    weak = _find_toc_block(filtered, _is_weak_toc_row, _sequential_trailing_numbers)

    if strict or weak:
        return strict if len(strict) >= len(weak) else weak

    logger.warning(
        "No table-of-contents-shaped block of rows found in the prelims/TOC file -- "
        "proceeding without a table of contents. Chapter numbers/titles for this book "
        "will rely entirely on per-chapter font-size heuristics instead of TOC matching, "
        "which is less reliable."
    )
    return []


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

    # Whether this block's numbering scheme is word-based (Sanskrit ordinals
    # such as "prathamah pathah" instead of "1.") is decided by MAJORITY
    # VOTE across the block, not by whether a digit-numbered entry exists
    # ANYWHERE in it. A single word-numbered chapter listing can legitimately
    # share its TOC page with a short, independently-numbered digit aside --
    # e.g. an appendix sub-list "1. Metre ... 102 / 2. Figures of Speech ...
    # 107 / 3. Recommended Books ... 112" tacked on after the real chapters.
    # Deciding "any digit present -> whole block is digit-numbered" (the
    # previous rule) misfiled every genuine word-numbered chapter as
    # front/back matter the moment such an aside was present, and kept only
    # the 2-3 incidental appendix rows as "chapters". Requiring unmatched
    # entries to be the STRICT MAJORITY is what keeps a real digit-numbered
    # book (where only a stray unmatched line or two should fall through to
    # front_back_matter, unchanged from previous behaviour) from flipping
    # into word-numbered mode just because of a couple of odd rows.
    unmatched_entries = [e for e in entries if not TOC_ENTRY_RE.match(e[0])]
    digit_entries = [e for e in entries if TOC_ENTRY_RE.match(e[0])]
    word_numbered_block = len(unmatched_entries) > len(digit_entries)

    # Within a word-numbered block, a genuine chapter row and an incidental
    # front/back-matter row (an invocation before the chapter list starts,
    # an appendix header after it ends) both satisfy the exact same
    # weak-pass row shape ("<title> <page>"), so find_toc_lines cannot tell
    # them apart by shape alone -- but real chapter rows in these books
    # share a repeated structural pattern: an ordinal word FOLLOWED BY a
    # recurring label word ("<ordinal> पाठः <title>", "<ordinal> Lesson
    # <title>", ...). We detect that recurring second token empirically (no
    # hardcoded word/language) and use it to tell genuine chapters apart
    # from a leading/trailing outlier that merely happens to share the same
    # trailing-page-number row shape. Only LEADING/TRAILING outliers are
    # demoted -- an interior row that breaks the pattern is left as a
    # chapter, since misclassifying a real chapter as front matter is worse
    # than leaving in one odd row.
    conforms = [None] * len(entries)  # False = leading/trailing outlier; None = normal chapter
    if word_numbered_block:
        second_tokens = []
        for combined, _ in entries:
            if TOC_ENTRY_RE.match(combined):
                continue
            toks = combined.split()
            second_tokens.append(toks[1] if len(toks) > 1 else None)
        counts = Counter(t for t in second_tokens if t)
        if counts:
            common_token, common_count = counts.most_common(1)[0]
            if common_count > len(second_tokens) / 2:
                verdicts = []
                for combined, _ in entries:
                    if TOC_ENTRY_RE.match(combined):
                        verdicts.append(None)
                        continue
                    toks = combined.split()
                    tok = toks[1] if len(toks) > 1 else None
                    verdicts.append(tok == common_token)
                lo = 0
                while lo < len(verdicts) and verdicts[lo] is False:
                    lo += 1
                hi = len(verdicts) - 1
                while hi >= 0 and verdicts[hi] is False:
                    hi -= 1
                for i, v in enumerate(verdicts):
                    if v is False and lo <= i <= hi:
                        v = None  # interior outlier: still counts as a chapter
                    conforms[i] = v

    book: Dict[str, Any] = {"chapters": [], "front_back_matter": []}
    cur_chapter, cur_topic = None, None
    for i, (combined, page_raw) in enumerate(entries):
        page = int(page_raw) if page_raw and page_raw.isdigit() else page_raw
        m = TOC_ENTRY_RE.match(combined)
        if not m:
            if word_numbered_block and conforms[i] is not False:
                cur_chapter = {
                    "number": len(book["chapters"]) + 1,
                    "title": re.sub(r"\s+", " ", combined).strip(),
                    "page_start": page,
                    "topics": [],
                }
                book["chapters"].append(cur_chapter)
                cur_topic = None
                continue
            book["front_back_matter"].append({"title": combined, "page_start": page})
            continue
        num, title = m.group("num"), re.sub(r"\s+", " ", m.group("title")).strip()
        depth = num.count(".")
        # A depth-0 digit entry inside a word-numbered chapter block whose
        # number does NOT continue the running chapter count (e.g. an
        # appendix restarting at "1." after 11 word-numbered chapters
        # already exist) is a separately-numbered sub-list riding along on
        # the same TOC page, not a new top-level chapter that should reset
        # the numbering -- attach it under whichever chapter is currently
        # open instead.
        if word_numbered_block and depth == 0 and cur_chapter is not None \
                and int(num.split(".")[0]) != len(book["chapters"]) + 1:
            cur_topic = {"number": num, "title": title, "page_start": page, "subtopics": []}
            cur_chapter["topics"].append(cur_topic)
            continue
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


def match_chapter_by_number(chapter_order: Optional[int], toc: Optional[Dict[str, Any]]):
    """Looks up a chapter in the prelims TOC by its POSITION (1-based)
    among the chapter PDFs in this book -- i.e. toc["chapters"][chapter_order
    - 1] -- rather than by fuzzy-matching detected title text. This is the
    *primary* way to resolve a chapter against the TOC, not a fallback: the
    TOC file already carries the ground-truth, PRINTED-ORDER number->title
    mapping (that's literally what a table of contents is, and T2 already
    guarantees `toc["chapters"]` is in printed order), and NCERT chapter
    PDFs are named/ordered sequentially, so chapter_order is normally a
    completely reliable index into toc["chapters"] -- no text comparison
    needed at all.

    T4 root-cause note: this function used to compare chapter_order against
    each TOC entry's printed `number` field for EQUALITY instead of using it
    as a positional index -- despite this very docstring always describing
    it as "a completely reliable index into toc['chapters']". Value-equality
    and positional-index only coincide for a single-volume book, where the
    chapter's local/filename-derived number and its printed official number
    are the same thing. They diverge for a continued-numbering multi-part
    book: NCERT's own <subject><part><chapter>.pdf filename convention
    restarts the two-digit chapter suffix at "01" for every Part, so
    "Business Studies Part II"'s first chapter file has chapter_order == 1,
    but is officially PRINTED as chapter 9, continuing Part I's 1-8. The old
    equality check looked for a TOC entry whose printed number was 1, never
    found one (Part II's own TOC prints 9, 10, 11, ...), and silently fell
    through -- to fuzzy title matching, and if that also missed (a garbled
    OCR'd title, a low similarity ratio, ...) all the way to reporting the
    local per-part position (1) as if it were the official chapter number.
    Positional indexing fixes this because it never depends on what number
    is printed anywhere: the Nth chapter PDF actually being processed is
    reliably the Nth entry printed in THIS BOOK/PART'S OWN TOC, exactly the
    way a person reads down the contents page -- true whether the printed
    numbers happen to be 1..8, 9..16, or anything else, and it still
    resolves correctly (unchanged) for single-volume books, where position
    and printed number are identical anyway.

    This also matters when detect_chapter_title() got a garbled or empty
    title (e.g. a decorative unit-opener page where the real title is
    rendered as a graphic, not text, and font-size heuristics instead pick
    up a merged fragment like "1 Unit1"): fuzzy title matching has nothing
    usable to compare in that case and will never clear the similarity
    threshold, so it silently leaves the garbage title in place. Matching
    by position instead sidesteps the bad title entirely and pulls the
    correct one straight from the TOC.

    Returns None if `chapter_order` is None/out of range for the TOC, or
    the TOC has no chapters at all -- callers should fall back to
    match_chapter_in_toc() or chapter_order itself (clearly labeled as an
    unconfirmed local position, never as a confirmed official number) in
    that case."""
    if not toc or not toc.get("chapters"):
        return None
    chapters = toc["chapters"]
    if chapter_order is None or chapter_order < 1 or chapter_order > len(chapters):
        return None
    return chapters[chapter_order - 1]


def match_chapter_by_position(processing_position: Optional[int], toc: Optional[Dict[str, Any]]):
    """Looks up a chapter in the prelims TOC by this chapter's own ordinal
    position in THIS RUN's processing order (1st file handled, 2nd file
    handled, ...) -- i.e. toc["chapters"][processing_position - 1] -- the
    same positional-indexing mechanism match_chapter_by_number() uses, just
    keyed off a different index source.

    This is the fallback match_chapter_by_number() itself calls out for
    (see its own docstring, step 2): reached only when chapter_order (the
    PDF's filename-derived number) did NOT resolve anything -- either there
    was no parseable number at all, or the number parsed doesn't land
    inside this book/part's own toc["chapters"] range. That second case is
    exactly what happens for a book with non-sequential local filenames
    (the two-digit suffix in the chapter PDFs skips a number, is reused, or
    otherwise doesn't line up 1:1 with this TOC's own printed order) --
    chapter_order can be out of range or point at the wrong entry even
    though the file is still being handled in the correct, TOC-matching
    order during this run. processing_position -- this run's own 1, 2,
    3, ... loop counter -- doesn't depend on anything parsed from the
    filename, so it still lines up against this book/part's own TOC
    (in printed order, per T2) the same way a person reads down the
    chapter files in the order they were actually given.

    Returns None under the same conditions as match_chapter_by_number: no
    TOC, no chapters, or the position out of range -- callers should fall
    back to match_chapter_in_toc() (fuzzy title matching) or the raw
    position/order value itself (clearly labeled as an unconfirmed local
    position, never as a confirmed official number) in that case.
    """
    if not toc or not toc.get("chapters"):
        return None
    chapters = toc["chapters"]
    if processing_position is None or processing_position < 1 or processing_position > len(chapters):
        return None
    return chapters[processing_position - 1]


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
    # Set by pipeline.process_all_pdfs() from book_orchestrator's
    # discovered folder name (book_title_override param), when given.
    # This is ONLY the output-directory/identity key -- it keeps sibling
    # books (or sibling "Part N" folders of the same subject) from
    # colliding in json_out/, per book_orchestrator.py's own docstring.
    # It is deliberately kept separate from `book_title` (the OFFICIAL
    # NCERT title, parsed from the prelims/TOC PDF) so that slugifying
    # the folder name for output-path purposes never clobbers the real
    # displayed book title in the extracted JSON. This decoupling fixes
    # the regression where book_title_override overwrote `book_title`
    # directly, silently replacing official titles like "Introductory to
    # Macroeconomics" with whatever the input folder happened to be named
    # (e.g. "Macroeconomics"). `book_title` itself is never touched by the
    # override unless no official title could be parsed at all (still
    # "untitled-book").
    #
    # Phase 1 Final Metadata Architecture Refinement: this field is kept
    # ONLY for backward compatibility with books that already live under
    # a folder-name-derived OneDrive path (see slug_source below) -- the
    # identity model no longer *depends* on an operator having named the
    # input folder distinctly. Long-term identity now comes from the
    # canonical cover metadata fields below.
    book_folder_name: Optional[str] = None

    # --- Canonical cover metadata (Phase 1 Final Metadata Architecture
    # Refinement, STEP 2) -- exactly as printed by NCERT, extracted by
    # parse_cover_metadata() off the SAME prelims/TOC PDF book_title comes
    # from (never inferred from folder names). Each stays independently
    # preserved -- never concatenated into book_title, never abbreviated,
    # never simplified -- and is None whenever NCERT prints no such
    # distinguishing metadata for this book (the common, single-part case).
    cover_subtitle: Optional[str] = None
    part: Optional[str] = None
    volume: Optional[str] = None
    edition: Optional[str] = None

    # Set only when parse_book_title_and_class's chosen title line came from
    # a legacy non-Unicode Hindi/Sanskrit-typing font (see
    # language_detector.detect_legacy_devanagari_font) -- the raw text
    # PyMuPDF extracted for that line, which is Latin-looking glyph-code
    # noise, not real Unicode Devanagari (e.g. "HkkLorh" instead of
    # "भास्वती"). `book_title` itself is reset to "untitled-book" in this
    # case (see load_book_context) so it never silently ships as the
    # displayed title; this field exists purely so the raw text is still
    # visible for logging/audit and as an input a downstream OCR-based
    # title-recovery step (outside this deterministic module) could use.
    book_title_legacy_raw: Optional[str] = None

    # Set whenever parse_book_title_and_class's chosen title LINE is in a
    # legacy non-Unicode font -- i.e. whenever this book hit the "raw text
    # layer is glyph-code noise" wall at all, regardless of whether plain
    # Tesseract OCR of the title crop then happened to succeed or fail.
    # load_book_context() itself never calls the VLM (this module stays
    # deterministic-only by design -- see semantic_processor.py's module
    # docstring), so this is purely location/evidence a caller with a
    # loaded VLM (pipeline.py, after Qwen2.5-VL preload) can use to
    # re-render the cover and call
    # semantic_processor.process_recover_book_cover_metadata() as a
    # second-line fallback. None whenever the legacy-font branch never ran
    # (the common, non-legacy-font case).
    book_title_line_page: Optional[int] = None
    book_title_line_bbox: Optional[tuple] = None
    book_title_ocr_attempt: str = ""

    # Explicit "still needs recovering" flags, set once inside
    # load_book_context() at the moment each deterministic/OCR attempt
    # actually succeeds or fails -- NOT re-derived later from book_title/
    # klass's current value. This matters because book_title gets a
    # last-resort folder-name fallback applied by pipeline.py AFTER
    # load_book_context() returns (see book_title_override in
    # process_all_pdfs()); checking `book_title == "untitled-book"` at
    # that later point would already be masked by that fallback and a VLM
    # recovery pass would never fire. These flags capture the true
    # "was the OFFICIAL cover value actually recovered" signal at its
    # only reliable source -- right here, before anything else touches it.
    book_title_needs_recovery: bool = False
    klass_needs_recovery: bool = False

    @property
    def educational_identity(self) -> str:
        """The identity a student/teacher actually recognizes the book
        by: whichever distinguishing cover metadata NCERT printed
        (subtitle, else Part, else Volume), or the book's own official
        title when NCERT printed no distinguishing metadata at all.
        Purely a function of canonical fields already on this instance --
        never hardcodes a subject or title."""
        return self.cover_subtitle or self.part or self.volume or self.book_title

    @property
    def derived_storage_identity(self) -> str:
        """Deterministic, human-readable storage identity built ONLY from
        canonical cover metadata (STEP 2/3): "<book_title>" whenever
        NCERT prints no distinguishing subtitle/Part/Volume for this book
        (the common case, and identical to the pre-refinement behavior),
        else "<book_title> - <distinguishing metadata>". Each field stays
        independently preserved elsewhere -- this is a STORAGE-ONLY
        composite and must never become the displayed book_title."""
        distinguishing = self.cover_subtitle or self.part or self.volume
        return f"{self.book_title} - {distinguishing}" if distinguishing else self.book_title

    @property
    def slug_source(self) -> str:
        """Authoritative source for this book's output-directory identity
        (book_slug). Precedence:

          1. book_folder_name -- an EXPLICIT operator override, when one
             was supplied (book_orchestrator.py's discovered subfolder
             name). Kept for backward compatibility only: any book
             already living under a folder-name-derived OneDrive path
             keeps producing that exact same path.
          2. derived_storage_identity -- canonical-cover-metadata-derived
             and deterministic; unique whenever NCERT prints
             distinguishing metadata (subtitle/Part/Volume), and
             identical to the official title otherwise. This is now the
             long-term identity source -- no operator folder name is
             required to reach it.
        """
        return self.book_folder_name or self.derived_storage_identity


def book_slug_source(book_ctx: Any) -> str:
    """getattr-safe equivalent of BookContext.slug_source, for callers
    that may receive a duck-typed book_ctx double (e.g. test doubles that
    only set book_title/subject/klass/toc) instead of a real BookContext
    instance -- avoids an AttributeError on the newer book_folder_name /
    canonical-metadata fields for any such caller that predates them."""
    folder_name = getattr(book_ctx, "book_folder_name", None)
    if folder_name:
        return folder_name
    derived = getattr(book_ctx, "derived_storage_identity", None)
    return derived or book_ctx.book_title


def _ocr_recover_title(prelims_path: str, title_line: "Line", lang: str,
                        return_raw: bool = False) -> "Optional[str] | tuple":
    """Best-effort recovery of a legacy-font title LINE's real text via OCR
    of its own rendered glyphs, rather than the (mismapped) text layer.

    return_raw=True changes the return shape to (text_or_none, raw_attempt):
    raw_attempt is the single longest string Tesseract produced across every
    render-variant/language attempt, even if none of them passed the
    script-usability check (empty string if OCR never produced anything at
    all). This exists purely so a caller can hand that low-confidence read
    to a downstream VLM recovery step as a weak hint, rather than the read
    being discarded the moment it fails is_text_usable_for_language() --
    default (return_raw=False) is unchanged for the two existing callers.

    Renders only `title_line`'s own bounding box -- not the whole page --
    at a high upscale factor: a short, large-font title line OCRs far more
    reliably in isolation than as part of a busy cover page full of small
    boilerplate/logo text, which is what the earlier whole-page probe
    against the real PDFs showed noisy results for everywhere except the
    title line itself.

    Tries `lang`'s own Tesseract traineddata first, then falls back to
    Hindi's if that specific pack isn't installed in this environment
    (common for "sa": Sanskrit's "san" pack is a separate, much less
    commonly installed download than "hin"/"eng", but Hindi and Sanskrit
    share the Devanagari glyph set, so Tesseract's Hindi model can still
    read a Sanskrit title's glyphs even though its dictionary is Hindi's --
    same reasoning as language_detector.detect_legacy_devanagari_font()'s
    "Hindi is the safer Devanagari guess absent other signal"). This is
    purely an OCR-engine fallback and never changes the `lang` this
    function was asked to recover text *in* -- only which trained model is
    used to read the glyphs.

    Returns the OCR'd, NFC-normalized text (with any trailing zero-width
    joiner/non-joiner artifacts Tesseract sometimes appends after a
    Devanagari virama-ending conjunct stripped off), or None if OCR isn't
    available in this environment, the render call fails, no installed
    language pack could read the glyphs, or the result doesn't actually
    look like text in `lang`'s script -- any of which means the caller
    should fall back to the existing "untitled-book" sentinel rather than
    risk storing a low-confidence or outright wrong OCR guess as the
    book's official title.
    """
    if not _OCR_AVAILABLE:
        logger.warning("OCR title recovery skipped for %s: pytesseract/Pillow not importable in this environment.",
                        prelims_path)
        return (None, "") if return_raw else None
    if not title_line.bbox or title_line.bbox == (0.0, 0.0, 0.0, 0.0):
        logger.warning(
            "OCR title recovery skipped for %s: title_line has no usable bbox (got %r, page=%s, font=%s) "
            "-- the line-detection step never populated a real bounding box for this line, so there is "
            "nothing to render/crop.",
            prelims_path, title_line.bbox, title_line.page, title_line.font,
        )
        return (None, "") if return_raw else None
    try:
        doc = fitz.open(prelims_path)
        page = doc[title_line.page]
        x0, y0, x1, y1 = title_line.bbox
        # Decorative/calligraphic NCERT title fonts (e.g. "अंतरा"-style
        # covers) routinely have swashes/flourishes that extend beyond the
        # line's own tight glyph bbox -- a pad of 4 can clip those strokes,
        # which costs Tesseract exactly the visual detail it needs to tell
        # similar-looking conjuncts apart. 10 gives more breathing room
        # without pulling in neighboring lines on a normal single-line crop.
        pad = 10
        clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
        pix = page.get_pixmap(matrix=fitz.Matrix(6, 6), clip=clip)
        img = Image.open(_io.BytesIO(pix.tobytes("png")))
        doc.close()
    except Exception:
        logger.warning("Rendering title line to an image failed for %s (bbox=%r); falling back to untitled-book.",
                        prelims_path, title_line.bbox, exc_info=True)
        return (None, "") if return_raw else None

    # Plain render first (proven to already work for every other
    # legacy-font book), then progressively stronger de-watermarking
    # treatments only if plain isn't usable -- see _watermark_variants'
    # docstring for why the ordering matters here.
    img_variants = list(_watermark_variants(img))

    ocr_lang_attempts = [lang]
    if lang != "hi":
        ocr_lang_attempts.append("hi")

    unusable_results = []
    for variant_name, variant_img in img_variants:
        for attempt_lang in ocr_lang_attempts:
            try:
                ocr_text = pytesseract.image_to_string(
                    variant_img, lang=language_detector.ocr_lang_code(attempt_lang), config="--psm 7"
                ).strip()
            except Exception:
                logger.warning(
                    "OCR title recovery with lang=%s (traineddata=%s) failed for %s -- likely missing "
                    "language pack; %s.",
                    attempt_lang, language_detector.ocr_lang_code(attempt_lang), prelims_path,
                    "trying Hindi's pack as a Devanagari-glyph fallback" if attempt_lang == lang and lang != "hi"
                    else "no further fallback available",
                )
                continue
            ocr_text = unicodedata.normalize("NFC", ocr_text)
            # Trailing ZWNJ/ZWJ (U+200C/U+200D) is a known Tesseract artifact on
            # Devanagari virama-ending conjuncts -- invisible, so the title
            # looks correct printed, but the string no longer equals the same
            # word elsewhere (TOC entries, slugify()-derived filenames/IDs),
            # silently breaking downstream matching. A joiner at the very end
            # of a string has nothing left to join to, so stripping it here is
            # never a legitimate mid-word change.
            ocr_text = re.sub(r"[\u200c\u200d]+$", "", ocr_text)
            if ocr_text and language_detector.is_text_usable_for_language(ocr_text, attempt_lang, min_alpha_chars=2):
                return (ocr_text, ocr_text) if return_raw else ocr_text
            unusable_results.append((variant_name, attempt_lang, ocr_text))
    if unusable_results:
        logger.warning(
            "OCR title recovery for %s produced text that didn't pass the script-usability check for "
            "any attempted rendering/language: %r -- this is a real OCR read (not a missing-traineddata case); "
            "check whether the crop/render (bbox=%r) is actually capturing the title glyphs.",
            prelims_path, unusable_results, title_line.bbox,
        )
    if return_raw:
        # Best-effort hint for a downstream VLM step even though nothing here
        # passed the script-usability check: the longest raw string any
        # variant/language attempt produced (empty string if OCR produced
        # nothing at all across every attempt).
        best_raw = max((text for _, _, text in unusable_results), key=len, default="")
        return None, best_raw
    return None




def _watermark_variants(img: "Image.Image"):
    """Yields (name, image) pairs: increasingly aggressive treatments of a
    rendered page/crop for the translucent diagonal "© NCERT / Not to be
    republished" watermark that crosses some NCERT prelims covers, weakest
    (the untouched original) first.

    A single fixed brightness threshold applied unconditionally sounds
    like the obvious fix -- solid black print text survives, lighter grey
    watermark strokes don't -- but on some covers it wiped the real text
    too: a small/thin/decorative glyph rendered at this crop size is often
    mostly anti-aliased grey rather than solid black, so a threshold tuned
    to kill the watermark can kill those glyphs right along with it (this
    is exactly what happened to both the title and the class-marking OCR
    on a real book after an earlier version of this fix applied the
    threshold unconditionally -- both came back completely empty instead
    of merely low-confidence).

    So: always try the plain render first (this is the render that already
    worked for every other legacy-font book before any watermark handling
    existed, so it must stay the first attempt, never be replaced by one).
    Only if that fails does a caller move on to progressively stronger
    de-watermarking treatments -- autocontrast (redistributes the
    grey range without discarding any of it, so it can't erase faint
    strokes the way a hard cutoff can) before the hard threshold (which
    stays available as a last resort for covers where the watermark
    is dark/solid enough that nothing gentler removes it).

    Never raises: any treatment that fails to construct is just skipped,
    so the plain original is always yielded at minimum."""
    yield "plain", img
    try:
        from PIL import ImageOps
        yield "autocontrast", ImageOps.autocontrast(img.convert("L"))
    except Exception:
        pass
    try:
        gray = img.convert("L")
        yield "threshold_150", gray.point(lambda p: 255 if p > 150 else 0)
    except Exception:
        pass


def _ocr_recover_class(prelims_path: str, lang: str, max_pages: int = 2) -> Optional[str]:
    """Best-effort recovery of a "कक्षा ..." (or "Class ...") marking when
    the cover page is set in a legacy non-Unicode font, so the raw text
    layer can't be trusted for ANY line on the page (see
    _ocr_recover_title's docstring for why).

    Unlike the title, there's no single line known in advance to hold the
    class marking -- it can sit in a different font-size tier than the
    title, or as part of a line that upstream dedup/merge steps reshape or
    drop before it ever becomes a clean standalone Line object. Guessing
    which extracted Line to crop and OCR is fragile for exactly that
    reason (an earlier version of this function did that, and silently
    found nothing on a real book). Instead, this OCRs each of the first
    `max_pages` prelims pages as a WHOLE image and searches the result for
    a class marking -- slower per page than a single-line crop, but this
    only runs a handful of times per BOOK (not per chapter), and only
    after the regex pass over the raw text layer has already failed.

    Never raises; returns None if OCR isn't available or no scanned page's
    text resolves to a class marking.
    """
    if not _OCR_AVAILABLE:
        return None
    ocr_lang_attempts = [lang]
    if lang != "hi":
        ocr_lang_attempts.append("hi")
    try:
        doc = fitz.open(prelims_path)
    except Exception:
        return None
    try:
        for pno in range(min(max_pages, doc.page_count)):
            try:
                page = doc[pno]
            except Exception:
                continue
            # 3x is enough resolution for most covers, but a class marking
            # set in a small font can render too blurry at 3x for Tesseract
            # to read its digits correctly -- the classic '1'/'7' confusion,
            # which turns a real "12" into "72". That's caught by the 1-12
            # bound in _match_devanagari_class()/_english_class_match() (so
            # it's never wrongly accepted), but simply moving on afterwards
            # left genuinely-marked books at klass="unknown". So: if this
            # page's OCR text has a near-miss (see _devanagari_digit_near_miss
            # / _english_class_near_miss above), it's worth re-OCRing the
            # SAME page at a sharper render before giving up on it -- 6x
            # matches the resolution already used for the single-line title
            # crop elsewhere in this module. If there's no near-miss either,
            # there's nothing on this page suggesting a marking exists at
            # all, so a sharper render of it isn't worth the extra OCR cost.
            for zoom in (3, 6):
                try:
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    base_img = Image.open(_io.BytesIO(pix.tobytes("png")))
                except Exception:
                    break
                saw_near_miss = False
                # Plain render first, then progressively stronger
                # de-watermarking treatments only if plain finds nothing --
                # see _watermark_variants' docstring for why the plain
                # render must never be skipped or replaced outright.
                for variant_name, img in _watermark_variants(base_img):
                    for attempt_lang in ocr_lang_attempts:
                        try:
                            # Default (automatic) page segmentation, not --psm 7's
                            # single-line mode -- this is a whole page, not a crop.
                            ocr_text = pytesseract.image_to_string(
                                img, lang=language_detector.ocr_lang_code(attempt_lang)
                            )
                        except Exception:
                            continue
                        ocr_text = unicodedata.normalize("NFC", ocr_text)
                        devanagari_class = _match_devanagari_class(ocr_text)
                        if devanagari_class:
                            return devanagari_class
                        m_class = _english_class_match(ocr_text)
                        if m_class:
                            return m_class
                        if _devanagari_digit_near_miss(ocr_text) or _english_class_near_miss(ocr_text):
                            saw_near_miss = True
                # NOTE: previously this broke out of the zoom loop here
                # ("nothing hints at a marking on this page; skip the sharper
                # retry") whenever the 3x pass produced no near-miss either.
                # That assumed a missed marking always shows up as an
                # out-of-range digit near-miss, which is only true for a
                # *blurry* miss -- a watermark-occluded "कक्षा" token instead
                # produces NO match and NO near-miss (the word itself doesn't
                # come through at all), so the sharper 6x retry was being
                # skipped on exactly the pages that needed it most. Always
                # running both zoom levels costs at most one extra whole-page
                # OCR pass, and only for books that already needed OCR class
                # recovery in the first place (a small minority of books), so
                # the extra cost is negligible against correctly recovering
                # klass instead of leaving it "unknown".
    finally:
        doc.close()
    return None


def needs_vlm_cover_metadata_recovery(book_ctx: "BookContext") -> bool:
    """True iff load_book_context() hit the legacy-font wall on this book's
    cover AND still needs book_title and/or klass recovered -- there's a
    real page/crop location on file for a caller with the VLM loaded to
    render and retry against.

    Deliberately keyed off book_title_needs_recovery/klass_needs_recovery
    (set once, at the moment each attempt actually succeeded or failed
    inside load_book_context()) rather than re-checking book_title ==
    "untitled-book" here: by the time a caller (pipeline.py) gets around to
    calling this, a last-resort folder-name fallback may already have
    overwritten book_title away from the sentinel, which would make that
    check always False and silently skip real recovery for the common
    case where an operator folder name happens to be supplied for every
    book (see book_title_override in process_all_pdfs())."""
    return book_ctx.book_title_line_page is not None and (
        book_ctx.book_title_needs_recovery or book_ctx.klass_needs_recovery
    )


def load_book_context(prelims_path: Optional[str]) -> BookContext:
    if not prelims_path:
        return BookContext()
    lines = extract_lines(prelims_path)
    lines = dedupe_decorative_duplicates(lines)
    body_size = body_font_size(lines)
    lines = merge_wrapped_lines(lines, body_size)
    repeated = find_repeated_lines(lines)
    book_title, subject, klass, title_line = parse_book_title_and_class(lines, body_size, repeated)
    logger.info(
        "parse_book_title_and_class() -> book_title=%r subject=%r klass=%r title_line_font=%r",
        book_title, subject, klass, title_line.font if title_line else None,
    )

    # A book set in a legacy (non-Unicode) Hindi/Sanskrit-typing font (see
    # language_detector's module docstring) has a text layer that reads real
    # Devanagari as meaningless Latin-looking glyph-code noise -- PyMuPDF
    # extraction "succeeds" (produces a non-empty string), so book_title
    # never falls into the existing "untitled-book" sentinel on its own; it
    # comes out confidently wrong instead ("HkkLorh" rather than "भास्वती").
    # Checked against the title LINE's own font specifically, not "any font
    # anywhere in the PDF" (prelims pages routinely mix the legacy
    # Devanagari font with plain Arial/Latin lines on the same page, e.g.
    # the NCERT English boilerplate alongside a Sanskrit title).
    #
    # The text LAYER is mismapped, but the rendered GLYPHS are not -- OCR of
    # just that line's own bounding box recovers the real title in its
    # actual printed language (verified against real Chanakya-font NCERT
    # prelims: OCR reads "भास्वती"/"शाश्वती" correctly). Only ever attempted
    # for this one flagged line, never for chapter/heading/body text, and
    # falls back to the pre-existing "untitled-book" sentinel (so
    # slug_source/derived_storage_identity still fall through cleanly to the
    # operator-supplied folder name) if OCR isn't available in this
    # environment or doesn't produce a confident result.
    book_title_legacy_raw = None
    book_title_line_page = None
    book_title_line_bbox = None
    book_title_ocr_attempt = ""
    book_title_needs_recovery = False
    klass_needs_recovery = False
    if title_line and language_detector.detect_legacy_devanagari_font([title_line.font]):
        book_title_legacy_raw = book_title
        # Location is recorded unconditionally the moment we know this is a
        # legacy-font cover -- not only on failure -- since a later VLM
        # class-recovery pass (see klass_needs_recovery below) may still
        # need to re-render this cover even when the title itself was
        # recovered fine via plain OCR just below.
        book_title_line_page = title_line.page
        book_title_line_bbox = tuple(title_line.bbox) if title_line.bbox else None
        # Metadata-only guess at this point (book_title is still the raw,
        # possibly-garbled text layer -- filename/subject are the reliable
        # signals here) rather than hardcoding "hi", so an OCR-recovered
        # title uses the right Tesseract model (san vs hin) instead of
        # always assuming Hindi for every legacy-font book regardless of
        # its actual language.
        early_lang_guess = (
            language_detector.detect_language_from_metadata(
                # Full path, not just the basename -- NCERT filenames
                # themselves are terse internal codes ("lhsk1ps.pdf") that
                # never carry a language hint, but the folder structure an
                # operator organizes books under often does (e.g.
                # ".../Sanskrit/Part 1/lhsk1ps.pdf"), and detect_language_
                # from_metadata() is just a case-insensitive substring
                # search, so this is a strict superset of the basename-only
                # check with nothing lost.
                prelims_path, book_title, subject
            )
            or DEFAULT_LANGUAGE
            # config.DEFAULT_LANGUAGE can itself be None/unset -- this whole
            # branch only runs after detect_legacy_devanagari_font() already
            # confirmed a legacy Devanagari-typing font, so "hi" is always a
            # sane, guaranteed-non-None last resort here (never "en" default
            # devanagari script line simply doesn't happen).
            or "hi"
        )
        ocr_title, ocr_raw_attempt = _ocr_recover_title(prelims_path, title_line, early_lang_guess,
                                                          return_raw=True)
        book_title_ocr_attempt = ocr_raw_attempt or ""
        if ocr_title:
            book_title = ocr_title
            logger.info(
                "Prelims title line is set in a legacy non-Unicode font (%s); "
                "recovered the real title %r via OCR of the rendered line "
                "(raw text layer was %r).",
                title_line.font, book_title, book_title_legacy_raw,
            )
        else:
            book_title = "untitled-book"
            # Flag (not just leave book_title as the sentinel) that the
            # OFFICIAL cover title still needs recovering -- book_title
            # itself may get overwritten by an unrelated last-resort
            # folder-name fallback later in pipeline.py, but this flag is
            # set once, right here, and nothing after this point in
            # load_book_context() (which never sees that fallback -- it
            # runs entirely inside pipeline.py, after this function
            # returns) can accidentally clear it.
            book_title_needs_recovery = True
            logger.warning(
                "Prelims title line is set in a legacy non-Unicode font (%s); "
                "the extracted text %r is glyph-code noise, not real Unicode "
                "text, and plain OCR recovery was unavailable/unconfident "
                "(best raw OCR attempt: %r). Leaving book_title as "
                "'untitled-book' here; page=%s bbox=%r are carried on "
                "BookContext for an optional VLM-based recovery pass.",
                title_line.font, book_title_legacy_raw, book_title_ocr_attempt,
                book_title_line_page, book_title_line_bbox,
            )

    if klass == "unknown" and title_line and language_detector.detect_legacy_devanagari_font([title_line.font]):
        # klass is still unknown after parse_book_title_and_class()'s regex
        # pass -- on a legacy-font cover page (confirmed above, since we're
        # already inside the book_title OCR-recovery branch's condition)
        # the "कक्षा ..." marking, if present, is just as likely to be
        # glyph-code noise in the raw text layer as the title itself was.
        # Uses whichever language OCR actually recovered the title in
        # (falls back to "hi" internally, same reasoning as the title
        # recovery above).
        class_ocr_lang = language_detector.detect_language_from_metadata(
            os.path.basename(prelims_path), book_title, subject
        ) or "hi"
        recovered_klass = _ocr_recover_class(prelims_path, class_ocr_lang)
        if recovered_klass:
            klass = recovered_klass
            logger.info(
                "Prelims class marking recovered via OCR (legacy font %s): klass=%r",
                title_line.font, klass,
            )
        else:
            klass_needs_recovery = True
            logger.warning(
                "Prelims class marking could not be recovered via OCR (legacy font %s) -- "
                "no 'कक्षा ...'/'Class ...' marking was found on the first pages of %s. "
                "klass remains 'unknown' for this book; a VLM-based recovery pass may "
                "still resolve it (see needs_vlm_cover_metadata_recovery()).",
                title_line.font, prelims_path,
            )

    cover_meta = parse_cover_metadata(lines, body_size, repeated, book_title)
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
        sample_text=first_page_text, pdf_metadata=pdf_meta,
        font_names=font_names,
    )
    if language == language_detector.DEFAULT_LANGUAGE:
        # detect_language() fell all the way through its own cascade
        # (metadata / legacy-font / script-ratio) without resolving
        # anything and landed on the detector module's own generic "en"
        # catch-all -- only now is it safe to apply this pipeline's own
        # configured default guess (e.g. "hi", since most NCERT books are
        # Hindi) instead of blindly overriding real detection every time.
        language = DEFAULT_LANGUAGE
    return BookContext(book_title=book_title, subject=subject, klass=klass, toc=toc, language=language,
                        cover_subtitle=cover_meta["subtitle"], part=cover_meta["part"],
                        volume=cover_meta["volume"], edition=cover_meta["edition"],
                        book_title_legacy_raw=book_title_legacy_raw,
                        book_title_line_page=book_title_line_page,
                        book_title_line_bbox=book_title_line_bbox,
                        book_title_ocr_attempt=book_title_ocr_attempt,
                        book_title_needs_recovery=book_title_needs_recovery,
                        klass_needs_recovery=klass_needs_recovery)


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
    # T4 -- the chapter's LOCAL position among the PDFs actually being
    # processed in this book/run (i.e. this run's processing order),
    # deliberately tracked as a field fully independent of chapter_number
    # (the OFFICIAL printed number). Never used as a stand-in for
    # chapter_number and never overwritten by it, or vice versa -- see
    # match_chapter_by_position()'s docstring for the bug this separation
    # fixes (a Part II book's chapter 1-in-this-run being reported as
    # "Official Chapter Number 1" instead of its true printed 9).
    chapter_position: Any = None


def parse_chapter_pdf(pdf_path: str, book_ctx: BookContext, chapter_order_fallback: int,
                       subject: Optional[str] = None, klass: Optional[str] = None,
                       processing_position: Optional[int] = None) -> ChapterStructure:
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
        override=book_ctx.language or DEFAULT_LANGUAGE,
        font_names=font_names,
    )

    chapter_title, chapter_title_line = detect_chapter_title(lines, body_size, repeated)
    # A chapter opening page can be set in the same legacy non-Unicode
    # Hindi/Sanskrit-typing font as a book's cover title (see
    # language_detector's module docstring and load_book_context's own
    # handling of book_title above) -- in that case chapter_title just
    # extracted is glyph-code noise ("izFke% ikB% vuq'kklue~" rather than
    # "प्रथमः पाठः अनुशासनम्"), which then propagates into chapter_number
    # matching, the JSON's chapter_title field, and slugify()-derived
    # filenames/storage paths. Recovered the same way as book_title: OCR
    # of just that line's own rendered glyphs. Falls back to the raw
    # (garbled) text -- not "untitled-chapter" -- when OCR is unavailable
    # or unconfident, since a chapter (unlike the book itself) still needs
    # *some* title string for downstream TOC matching to have a chance,
    # and match_chapter_by_number()/match_chapter_by_position() below don't
    # depend on chapter_title being clean anyway.
    if chapter_title_line and language_detector.detect_legacy_devanagari_font([chapter_title_line.font]):
        chapter_title_legacy_raw = chapter_title
        ocr_title = _ocr_recover_title(pdf_path, chapter_title_line, language)
        if ocr_title:
            chapter_title = ocr_title
            logger.info(
                "Chapter title line is set in a legacy non-Unicode font (%s); "
                "recovered the real title %r via OCR of the rendered line "
                "(raw text layer was %r).",
                chapter_title_line.font, chapter_title, chapter_title_legacy_raw,
            )
        else:
            logger.warning(
                "Chapter title line is set in a legacy non-Unicode font (%s); "
                "the extracted text %r is glyph-code noise, not real Unicode "
                "text, and OCR recovery was unavailable/unconfident, so the "
                "raw (garbled) text is being kept as chapter_title rather "
                "than blocking on a clean title.",
                chapter_title_line.font, chapter_title_legacy_raw,
            )
    # T4 -- official chapter-number resolution, in order of reliability:
    #
    # 1. Value-based lookup: chapter_order_fallback (this PDF's own
    #    local/filename-derived number) matched against each TOC entry's
    #    printed `number`. Correct and preferred whenever the two actually
    #    coincide (single-volume books; also the right choice for a
    #    partial/non-sequential run -- see chapter_number_from_filename()'s
    #    docstring) -- doesn't depend on detect_chapter_title() having
    #    found clean text either (see match_chapter_by_number()'s
    #    docstring for the decorative/graphic-title-page case).
    # 2. Positional lookup: this file's ordinal position in the current
    #    run against the TOC's own printed order. This is what resolves
    #    continued-numbering multi-part books correctly (Part II's local
    #    "chapter 1" file is officially chapter 9) -- see
    #    match_chapter_by_position()'s docstring for the full root-cause
    #    explanation. Only reached when (1) found no match, so it never
    #    overrides a good value-based match.
    # 3. Fuzzy title matching: last resort, when neither structural
    #    signal (printed number or run position) resolved anything.
    toc_match = match_chapter_by_number(chapter_order_fallback, book_ctx.toc)
    if not toc_match:
        toc_match = match_chapter_by_position(processing_position, book_ctx.toc)
    if not toc_match:
        toc_match = match_chapter_in_toc(chapter_title, book_ctx.toc)
    toc_matched = bool(toc_match)
    # chapter_position: this chapter's LOCAL position in this book/run,
    # tracked independently of chapter_number below and never conflated
    # with it -- see ChapterStructure.chapter_position's docstring. This
    # is the value that used to silently become chapter_number itself
    # whenever no TOC match was found; it no longer does.
    chapter_position = processing_position if processing_position is not None else chapter_order_fallback
    if toc_match:
        chapter_number = toc_match["number"]
        toc_title = toc_match["title"]
        # The TOC page can be set in the very same legacy non-Unicode font
        # as the chapter opening page (see the OCR-recovery block above),
        # but parse_toc() collapses every TOC line down to a plain
        # (text, page) string tuple at its very first line -- discarding
        # the source Line's font entirely -- so there is no way to
        # OCR-recover a TOC title the way book_title/chapter_title above
        # are recovered. Blindly trusting toc_match["title"] here would
        # silently clobber a chapter_title that was JUST correctly
        # OCR-recovered from the chapter's own opening page with an
        # equally-garbled TOC-page string. Only accept the TOC's title
        # when it actually looks like real text in the book's language;
        # otherwise keep whatever chapter_title already holds (which is
        # never worse, and is often the OCR-recovered clean title).
        if language_detector.is_text_usable_for_language(toc_title, language):
            chapter_title = toc_title
    else:
        # No TOC signal resolved anything for this chapter (no TOC at
        # all, or none of the three lookups above matched) -- the local
        # position is the only number available, so it's used here same
        # as before T4, but it is NEVER labeled as TOC-confirmed
        # (toc_matched stays False) and chapter_position above still
        # carries the same value under its own, unambiguous name for any
        # caller that needs to tell "official" and "local" apart.
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
        language=language, chapter_position=chapter_position,
    )


def page_batches(num_pages: int, batch_size: int = DEFAULT_PAGE_BATCH_SIZE) -> List[List[int]]:
    """Split a chapter's page range into batches of `batch_size` pages
    (clamped to 4-8) for the VLM stage. Deterministic, no model calls."""
    batch_size = max(MIN_PAGE_BATCH_SIZE, min(MAX_PAGE_BATCH_SIZE, batch_size))
    pages = list(range(num_pages))
    return [pages[i:i + batch_size] for i in range(0, len(pages), batch_size)]