"""
modules/ocr_cleanup.py — Phase 1 Stabilization Sprint (final refinement):
a dedicated, generic OCR content-cleanup stage.

WHY THIS IS A SEPARATE MODULE (not folded into pdf_parser.clean_extracted_text):
pdf_parser.clean_extracted_text() is deliberately minimal by design (NFC +
invisible-character stripping only — see its own docstring) because it runs
on BORN-DIGITAL text-layer extraction, which is rendering-perfect and never
has ligature/merged-word/spacing artifacts to begin with. The problems this
module addresses (broken ligatures, merged/split words, duplicate
whitespace, OCR punctuation noise) are specifically artifacts of the
tesseract OCR path (modules/ocr_engine.py), which rasterizes a page image
and reconstructs text from recognized glyphs — a fundamentally lossier
process. Keeping this as its own stage means the already-audited, minimal
born-digital cleanup path is untouched, and this new stage is wired in only
where OCR artifacts actually originate (ocr_engine._tesseract_ocr_page).

DESIGN CONSTRAINTS (per the sprint's own instructions):
  - Language-independent: every check here is script/case/Unicode-category
    driven, never a hardcoded word, language name, or per-book rule. Checks
    that rely on Latin case (e.g. the merged-word heuristic) simply don't
    fire on scripts without case (Devanagari, Tamil, ...) — that is a
    structural consequence of what's detectable, not a language-specific
    branch in the code.
  - Never transliterates, never romanizes, never drops a script's own
    characters — every fix here either (a) decomposes a KNOWN, unambiguous
    OCR/typesetting ligature codepoint into the exact letters it represents,
    (b) normalizes whitespace, or (c) adjusts spacing around punctuation.
    None of these change which characters/language are present.
  - Idempotent: clean_ocr_text(clean_ocr_text(x)) == clean_ocr_text(x) for
    any input (see tests/test_ocr_cleanup.py).
  - Never raises: any unexpected input degrades to the original string.

WHAT THIS DELIBERATELY DOES NOT ATTEMPT:
  - Period-boundary merged sentences (e.g. "end.Next sentence" with a
    dropped space after a full stop) are NOT split. Unlike the comma/
    semicolon/colon spacing handled in normalize_ocr_punctuation, '.' is
    deliberately excluded everywhere in this module: a period is
    immediately followed by an uppercase letter in both the broken case
    ("end.Next") AND in extremely common, entirely correct abbreviation
    patterns ("U.S.A", "Mr.Sharma" as printed, numbered sub-clauses,
    ...). Inserting a space generically on that shape would silently
    corrupt the latter far more often than it fixes the former. This is
    a known, documented limitation, not an oversight.
  - "Split word" repair (a single word incorrectly broken into two tokens
    by a spurious OCR space, e.g. "Ind ia") is NOT attempted. Detecting
    this generically requires a dictionary/language model per script —
    anything short of that either does nothing or risks merging two
    genuinely separate words, which is a worse failure mode (silent
    content corruption) than leaving the artifact for a human/Phase-2 pass
    to see. This is a known, documented limitation, not an oversight.
  - Line-wrap de-hyphenation (rejoining a word split across a line break
    with a trailing "-") is NOT attempted for the same reason: distinguishing
    a genuine hyphenated compound from a wrap-induced hyphen is ambiguous
    without the original line-break position, which is not available at
    this layer (lines are already flattened to single strings upstream).
  - OCR character-substitution correction (e.g. "l" vs "1" vs "I", "0" vs
    "O", rn" vs "m") is NOT attempted: these are context/language dependent
    judgment calls that risk corrupting genuinely correct content far more
    often than they fix genuine errors.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# 1. Broken ligatures
# ---------------------------------------------------------------------------
# The Unicode "Alphabetic Presentation Forms" block (U+FB00-U+FB06) exists
# purely as a typesetting convenience for a handful of Latin letter pairs
# that print with a joined glyph (fi, fl, ...). OCR engines occasionally
# recognize the joined glyph and emit the single ligature codepoint instead
# of the two letters it represents, which then silently fails to
# string-match "fi"/"fl" downstream. Unlike a blanket NFKC pass (which the
# extraction layer deliberately avoids -- see pdf_parser.py's own docstring
# -- because it can fold compatibility variants in ways that alter OTHER
# scripts' own presentation), decomposing exactly these six codepoints is
# safe and unambiguous: they only ever occur in Latin-script text, and each
# one has exactly one possible expansion, with no interaction with any
# other script's characters.
_LIGATURE_MAP = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",   # long s + t
    "\ufb06": "st",
}
_LIGATURE_TABLE = str.maketrans(_LIGATURE_MAP)


def fix_broken_ligatures(text: str) -> str:
    """Decomposes known Latin ligature presentation-form codepoints into
    the plain letters they represent. Script-independent: text containing
    no such codepoints (any Indic script, or already-decomposed Latin
    text) passes through completely unchanged."""
    if not text:
        return text
    return text.translate(_LIGATURE_TABLE)


# ---------------------------------------------------------------------------
# 2. Duplicate / irregular whitespace
# ---------------------------------------------------------------------------
def collapse_duplicate_whitespace(text: str) -> str:
    """Collapses any run of whitespace (regular spaces, tabs, and any
    Unicode space-separator character, category Zs -- e.g. a stray
    non-breaking space OCR sometimes emits) into a single ASCII space, and
    trims the result. Never touches a newline by itself -- a lone newline
    is left alone (it may be structurally meaningful to a caller that
    hasn't flattened it yet); only runs that include at least one
    space/tab/Zs character are collapsed. Category-driven, not a fixed
    whitespace character list, so it is inherently script-independent."""
    if not text:
        return text

    def _is_horizontal_space(ch: str) -> bool:
        return ch in (" ", "\t") or unicodedata.category(ch) == "Zs"

    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if _is_horizontal_space(ch):
            j = i + 1
            saw_run = False
            while j < n and (_is_horizontal_space(text[j]) or text[j] in ("\n", "\r")):
                if text[j] != "\n" and text[j] != "\r":
                    saw_run = True
                j += 1
            # A run of pure horizontal whitespace (no newline mixed in)
            # collapses to a single space. A run that includes a newline
            # is left untouched -- that's a line break, not OCR noise.
            if "\n" in text[i:j] or "\r" in text[i:j]:
                out.append(text[i:j])
            else:
                out.append(" ")
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out).strip()


# ---------------------------------------------------------------------------
# 3. OCR punctuation spacing/noise
# ---------------------------------------------------------------------------
# Space directly before a closing punctuation mark ("word ." / "word ,").
# Deliberately excludes '.' -- collapsing "3 . 14" would also collapse it
# to "3.14" (arguably correct) but the same rule applied to sentence-final
# periods followed by more spacing/quotes is far more error-prone to get
# right generically than the unambiguous cases below, so '.' is left to
# the existing lookup-key layer (compiler/normalization.py) rather than
# risked here against display text.
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([,;:!?\)\]\}])")

# Duplicated punctuation runs that are unambiguous OCR noise (never a
# deliberate stylistic choice in NCERT body text) -- collapse to one.
# '.', '!', '?' are deliberately excluded: "..." is a legitimate ellipsis,
# and "?!"/"!!" can be intentional emphasis in dialogue/exercises, so
# collapsing those risks altering authored meaning rather than fixing noise.
_DUPLICATED_PUNCT_RE = re.compile(r"([,;:])\1+")

# A colon/semicolon/comma with no following space before the next letter
# or digit (any script) — a common OCR spacing drop. '.', '!', '?' are
# excluded here for the same decimal/abbreviation-ambiguity reason as above.
_MISSING_SPACE_AFTER_PUNCT_RE = re.compile(r"([,;:])(?=[^\s\d,;:.!?)\]}])")


def normalize_ocr_punctuation(text: str) -> str:
    """Generic, script-independent punctuation-spacing cleanup: removes a
    stray space before a closing punctuation mark, collapses duplicated
    comma/semicolon/colon runs, and inserts a missing space after one of
    those marks when it's immediately followed by a letter/other
    character with no separator. Periods/exclamation/question marks are
    deliberately left untouched (see comments above) -- this function
    only ever touches punctuation-adjacent WHITESPACE, never removes or
    reorders any letter of any script."""
    if not text:
        return text
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _DUPLICATED_PUNCT_RE.sub(r"\1", text)
    text = _MISSING_SPACE_AFTER_PUNCT_RE.sub(r"\1 ", text)
    return text


# ---------------------------------------------------------------------------
# 4. Merged words at a case-transition boundary
# ---------------------------------------------------------------------------
def split_merged_words_at_case_boundary(text: str) -> str:
    """Inserts a missing space where a lowercase letter or digit is
    immediately followed by an uppercase letter with no separator at all
    (e.g. "photosynthesisRequires" -> "photosynthesis Requires") -- a
    common OCR failure mode where a genuine word-boundary space is
    dropped, most often right after a lowercase word runs into a
    Capitalized word (frequently the start of the next sentence after a
    missed/mis-OCR'd period).

    Case-driven, not language-driven: Python's str.islower()/.isupper()
    already respect Unicode case properties for every script that HAS
    case (Latin, Greek, Cyrillic, ...). Scripts without a case distinction
    (Devanagari, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi,
    Bengali, ...) simply never trigger this check on their own text --
    that is a structural consequence of what a case-transition heuristic
    can detect, not a hardcoded per-language branch."""
    if not text:
        return text
    out = []
    prev = ""
    for ch in text:
        if prev and ch.isupper() and (prev.islower() or prev.isdigit()) \
                and not (prev in "([{\"'") :
            out.append(" ")
        out.append(ch)
        prev = ch
    return "".join(out)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def clean_ocr_text(text: str) -> str:
    """The single public entry point: applies every OCR content-cleanup
    stage above, in a fixed, deterministic order, to raw text produced by
    the tesseract OCR path (modules/ocr_engine.py). Language-independent,
    idempotent, and never raises -- degrades to the original string on any
    unexpected input, exactly like pdf_parser.clean_extracted_text().

    Order matters: ligature decomposition and whitespace collapse run
    first (they can only ever reduce ambiguity for the later stages),
    punctuation spacing next, and the case-boundary word-split heuristic
    last (so it sees already-clean spacing and doesn't double up with the
    punctuation-spacing stage on the same gap).
    """
    if not text:
        return text
    try:
        cleaned = fix_broken_ligatures(text)
        cleaned = collapse_duplicate_whitespace(cleaned)
        cleaned = normalize_ocr_punctuation(cleaned)
        cleaned = split_merged_words_at_case_boundary(cleaned)
        # Punctuation-spacing / word-split can each introduce a new space;
        # one more whitespace collapse pass keeps the result stable, i.e.
        # idempotent, after a single call.
        cleaned = collapse_duplicate_whitespace(cleaned)
        return cleaned
    except Exception:
        return text