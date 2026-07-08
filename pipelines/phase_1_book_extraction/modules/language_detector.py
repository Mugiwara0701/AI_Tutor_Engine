"""
language_detector.py — deterministic, extensible language identification
for NCERT PDFs, plus a script-usability check used to catch legacy/garbled
font encodings (the "t;'kadj izlkn" instead of real Hindi Unicode symptom).

Why this module exists
-----------------------
Older NCERT Hindi/Sanskrit PDFs are frequently typeset with legacy,
non-Unicode "Hindi typing" fonts (Kruti Dev, DevLys, Chanakya, Walkman,
Agra, Shivaji, ...). These fonts draw Devanagari *glyphs* but map them onto
ordinary Latin/ASCII code points in the font's cmap. PyMuPDF's text
extraction reads the underlying code points, not the rendered glyphs, so
the "text" it returns for a page that visually shows perfectly normal Hindi
is a string of meaningless Latin-looking characters — which is exactly
what ended up in chapter titles/headings. This is NOT an OCR problem and
NOT a Unicode-normalization bug; it is a "the text layer is lying about
what script it contains" problem, and the only reliable way to catch it is
to check whether the *expected* script for the book's language actually
shows up in the extracted text.

Design notes (per the language-robustness milestone)
------------------------------------------------------
  - No language gets special-cased in *logic*: every language is just a row
    in LANGUAGE_NAMES / SCRIPT_RANGES / OCR_LANG_CODES / LANGUAGE_NAME_HINTS.
    Adding a new NCERT language (e.g. Urdu, Bengali) means adding a table
    row, not an if/elif branch anywhere in this file or its callers.
  - Detection is layered, cheapest/most-reliable signal first:
      1) an explicit override (e.g. config.DEFAULT_LANGUAGE)
      2) deterministic metadata already available on the PDF/book
         (filename, book title, subject, PDF document metadata) matched
         against known language names/native spellings
      3) known legacy Hindi/Sanskrit-typing font names (Kruti Dev, DevLys,
         Chanakya, Walkman, ...) found anywhere in the PDF's embedded font
         table -- the fallback for books where every page's text layer is
         mismapped, so neither metadata nor script-ratio analysis has any
         genuine Devanagari (or Devanagari-named) text left to go on
      4) script-ratio analysis of whatever Unicode text the PDF's text
         layer actually contains
      5) "en" as the last-resort default
  - is_text_usable_for_language() is what lets the OCR layer detect the
    legacy-font symptom described above: a page whose extracted text is
    long enough to normally be trusted (min_text_layer_chars) but doesn't
    contain the script the book is supposed to be in gets flagged as
    unusable, so the caller can fall back to OCR instead of writing
    garbled headings into the Chapter JSON.
"""
import re
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Per-language tables — the only place language identity lives. Extending
# to a new language means adding one row to each table below, nothing else.
# --------------------------------------------------------------------------
LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "sa": "Sanskrit",
}

# Unicode code-point block(s) each language's script is expected to use.
# Hindi and Sanskrit share the Devanagari block — telling them apart is not
# a script-detection problem, it's a metadata problem (see
# LANGUAGE_NAME_HINTS below), so they intentionally map to the same range.
SCRIPT_RANGES: Dict[str, List[Tuple[int, int]]] = {
    "en": [(0x0041, 0x005A), (0x0061, 0x007A)],
    "hi": [(0x0900, 0x097F)],
    "sa": [(0x0900, 0x097F)],
}

# Tesseract traineddata language codes for OCR fallback.
OCR_LANG_CODES: Dict[str, str] = {
    "en": "eng",
    "hi": "hin",
    "sa": "san",
}

# Words that, if found in a filename / book title / subject / PDF metadata
# string, deterministically identify the language. Matched case-insensitively
# as a substring. This is metadata matching, not script analysis, so native
# spellings are listed alongside the English name.
LANGUAGE_NAME_HINTS: Dict[str, List[str]] = {
    "hi": ["hindi", "हिन्दी", "हिंदी"],
    "sa": ["sanskrit", "संस्कृत"],
    "en": ["english"],
}

# Legacy ("Hindi typing") font families whose PDFs draw real Devanagari
# glyphs but map them onto ordinary Latin/ASCII code points in the font's
# own cmap (see the module docstring's "t;'kadj izlkn" example). For a book
# entirely set in one of these fonts, EVERY page's text layer is Latin-
# looking gibberish -- not just a page or two -- so there may be no genuine
# Unicode Devanagari character anywhere in the whole PDF for script-ratio
# analysis to find, and no real Hindi/Sanskrit word for metadata matching
# to find either (book title, chapter titles, filenames are all mangled by
# the same font). The font name itself, however, is plain ASCII text set
# by the typesetting software and is never mangled, making it the one
# reliable book-agnostic signal left in this situation. Matched
# case-insensitively as a substring against each embedded font's PostScript
# name. Extending to a newly-encountered legacy font family means adding one
# entry here, nothing else.
LEGACY_DEVANAGARI_FONT_MARKERS: List[str] = [
    "kruti", "devlys", "chanakya", "walkman", "agra", "shivaji",
    "shusha", "ajanta", "amarujala", "dev tt", "devanagari",
]

DEFAULT_LANGUAGE = "en"

_WORD_CHAR_RE = re.compile(r"\w", re.UNICODE)


def script_ratio(text: str, lang: str) -> float:
    """Fraction of alphabetic characters in `text` that fall inside
    `lang`'s expected Unicode script range(s). Returns 0.0 if `lang` is
    unknown or there are no alphabetic characters to judge (avoids a
    divide-by-zero on empty/whitespace/digit-only/punctuation-only text)."""
    ranges = SCRIPT_RANGES.get(lang)
    if not ranges or not text:
        return 0.0
    alpha_count = 0
    in_range_count = 0
    for ch in text:
        if not ch.isalpha():
            continue
        alpha_count += 1
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in ranges):
            in_range_count += 1
    return (in_range_count / alpha_count) if alpha_count else 0.0


def detect_language_from_text(text: str, candidates: Optional[List[str]] = None) -> Optional[str]:
    """Picks whichever candidate language's script best matches `text`, or
    None if no candidate clears a minimal-confidence bar. This only
    identifies a *script* — for Devanagari that means "hi" and "sa" are
    indistinguishable from text alone; callers needing to break that tie
    should prefer detect_language_from_metadata() first."""
    candidates = candidates or list(SCRIPT_RANGES)
    best_lang, best_ratio = None, 0.0
    for lang in candidates:
        ratio = script_ratio(text, lang)
        if ratio > best_ratio:
            best_lang, best_ratio = lang, ratio
    return best_lang if best_ratio >= 0.3 else None


def detect_language_from_metadata(*sources: Optional[str]) -> Optional[str]:
    """Checks filename / book title / subject / PDF-metadata strings for a
    known language name (English or a native spelling). Returns the first
    match found, or None if nothing matched."""
    haystacks = [s.lower() for s in sources if s]
    if not haystacks:
        return None
    for lang, hints in LANGUAGE_NAME_HINTS.items():
        for hint in hints:
            hint_l = hint.lower()
            if any(hint_l in h for h in haystacks):
                return lang
    return None


def detect_legacy_devanagari_font(font_names: Optional[List[str]]) -> Optional[str]:
    """Returns "hi" if any embedded font name matches a known legacy
    Hindi/Sanskrit-typing font family (see LEGACY_DEVANAGARI_FONT_MARKERS),
    else None. Hindi is the safer of the two Devanagari-using NCERT
    languages to guess absent any other signal -- same reasoning as the
    script-only tie-break at the bottom of detect_language(). Callers with
    a Sanskrit-specific metadata hint (LANGUAGE_NAME_HINTS) will already
    have resolved to "sa" via detect_language_from_metadata() before this
    ever runs, since that check has priority."""
    if not font_names:
        return None
    for name in font_names:
        if not name:
            continue
        lowered = name.lower()
        if any(marker in lowered for marker in LEGACY_DEVANAGARI_FONT_MARKERS):
            return "hi"
    return None


def detect_language(filename: str = "", book_title: str = "", subject: str = "",
                     sample_text: str = "", pdf_metadata: Optional[Dict[str, str]] = None,
                     override: Optional[str] = None,
                     font_names: Optional[List[str]] = None) -> str:
    """Best available language code for a chapter/book, per the priority
    order documented at the top of this module. Never raises — always
    returns a valid key of LANGUAGE_NAMES (falling back to "en")."""
    if override:
        return override

    meta_values = [v for v in (pdf_metadata or {}).values() if v]
    from_meta = detect_language_from_metadata(filename, book_title, subject, *meta_values)
    if from_meta:
        return from_meta

    # Legacy-font check comes before script analysis: for a book entirely
    # set in a legacy Hindi-typing font, script_ratio() will find ~0%
    # Devanagari everywhere (every character is mismapped) and ~100% "en"
    # everywhere (it all looks like clean Latin letters) -- script analysis
    # alone would confidently conclude "en" and be completely wrong. The
    # font name is the one thing in that scenario that isn't mangled.
    from_legacy_font = detect_legacy_devanagari_font(font_names)
    if from_legacy_font:
        return from_legacy_font

    # Without a metadata hint, script analysis can only tell us "this looks
    # like Devanagari" or "this looks like Latin" — Hindi is by far the more
    # common NCERT language of the two Devanagari options, so it is the
    # safer guess when metadata gave us nothing. Callers should treat a
    # script-only "hi" result as lower-confidence than a metadata-backed one
    # (e.g. log it) rather than silently trusting it the same way.
    from_script = detect_language_from_text(sample_text, candidates=["hi", "en"])
    if from_script:
        return from_script

    return DEFAULT_LANGUAGE


def language_name(lang_code: str) -> str:
    return LANGUAGE_NAMES.get(lang_code, LANGUAGE_NAMES[DEFAULT_LANGUAGE])


def ocr_lang_code(lang_code: str) -> str:
    return OCR_LANG_CODES.get(lang_code, OCR_LANG_CODES[DEFAULT_LANGUAGE])


def is_text_usable_for_language(text: str, lang: str, min_alpha_chars: int = 15,
                                 min_ratio: float = 0.3) -> bool:
    """True if `text`'s script plausibly matches `lang` — i.e. it is safe
    to trust this page's deterministic text layer for headings/semantics
    rather than treating it as garbled.

    This is what catches the legacy-font symptom: a page whose PyMuPDF text
    layer is non-empty and long enough to normally pass the "usable text
    layer" bar (ocr_engine.min_text_layer_chars) but is actually the wrong
    script entirely (Devanagari glyphs mapped onto Latin code points by an
    old Hindi typesetting font, extracted as ASCII gibberish).

    If there aren't even `min_alpha_chars` alphabetic characters to judge
    (e.g. a mostly-numeric or mostly-punctuation line), this can't be
    called reliably, so we don't — return True (benefit of the doubt)
    rather than force every short line through OCR."""
    alpha_chars = sum(1 for ch in text if ch.isalpha())
    if alpha_chars < min_alpha_chars:
        return True
    return script_ratio(text, lang) >= min_ratio