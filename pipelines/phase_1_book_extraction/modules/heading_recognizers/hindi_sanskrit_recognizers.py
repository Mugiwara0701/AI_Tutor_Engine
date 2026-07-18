"""
modules/heading_recognizers/hindi_sanskrit_recognizers.py — M4.2D:
Hindi and Sanskrit language-specific heading recognizers.

Extends the M4.2A framework + M4.2B generic-recognizer family
(generic_recognizers.py) with a Devanagari-script keyword family,
exactly mirroring generic_recognizers.py's own conventions:

  * subclasses `HeadingRecognizer` (base.py) and implements only
    `recognize()` (+ `supports()` as a cheap pre-filter);
  * registered with the framework via TWO
    `factory.register_class(name, RecognizerClass)` calls in
    `modules/heading_recognizers/__init__.py` — nothing in base.py,
    config.py, registry.py, pipeline.py, or factory.py needed to
    change to add these;
  * pure, deterministic, and cheap — no OCR, no PDF parsing, no
    layout analysis, no ML/LLM inference, no translation or semantic
    understanding (all explicitly out of scope per the M4.2D spec:
    this module only classifies a `RecognitionContext`'s already-
    extracted `text`);
  * reuses modules/heading_recognizers/utils.py rather than
    reimplementing numeral parsing or confidence combination — in
    particular the M4.2D-added `normalize_numeral` /
    `devanagari_to_arabic` / `is_devanagari_numeral` helpers, which
    let a keyword's numbering marker be written in either the Arabic
    (0-9) or Devanagari (०-९) digit system and be resolved to the
    same canonical `RecognitionResult.number`.

Both recognizers share one private base class (`_DevanagariKeywordHeadingRecognizer`,
below) purely to avoid duplicating the keyword+numeral matching logic
between the Hindi and Sanskrit families — this mirrors
ChapterNumberRecognizer's own single-keyword-list-driven-by-a-pattern
approach in generic_recognizers.py, just parameterized twice instead
of once. The shared base is intentionally private (not registered,
not exported) — only the two concrete, named subclasses are framework
recognizers.

Scope notes (per the M4.2D spec's "Out of Scope" section):
  * No OCR correction is performed — only lightweight, deterministic
    normalization (whitespace collapsing, duplicate-punctuation
    collapsing, trailing-punctuation stripping) via `_normalize_line`
    below, mirroring generic_recognizers.py's own `_clean()` helper.
  * "Chapter ५" / "Unit ५" (an English chapter keyword combined with a
    Devanagari numeral) is intentionally NOT handled here — that
    combination belongs to ChapterNumberRecognizer's own keyword
    family (generic_recognizers.py), and extending that recognizer's
    numeral parsing is outside this milestone's "Hindi & Sanskrit
    recognizers only" scope. This module handles a Devanagari keyword
    combined with either digit system (e.g. "अध्याय ५" / "अध्याय 5"),
    which covers every pattern the M4.2D spec's own test list
    enumerates.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Sequence

from modules.heading_recognizers.base import HeadingRecognizer, RecognitionContext, RecognitionResult
from modules.heading_recognizers.config import RecognizerSettings
from modules.heading_recognizers.enums import HeadingClassification
from modules.heading_recognizers.utils import (
    clamp_confidence,
    combine_confidence,
    normalize_heading_whitespace,
    normalize_numeral,
)

# A heading candidate is a short line by construction — same rationale
# and same ceiling as generic_recognizers.py's _MAX_CANDIDATE_LENGTH.
_MAX_CANDIDATE_LENGTH = 120

# Devanagari danda / double-danda (U+0964 / U+0965) — the
# Devanagari-script sentence-ending punctuation marks, functionally
# equivalent to ASCII "." for this recognizer's purposes. Distinct
# from the visarga (ः, U+0903), which is a letter that is part of a
# Sanskrit word itself (e.g. "अध्यायः") and must never be stripped.
_DANDA = "\u0964\u0965"

# Collapses a run of 2+ identical punctuation characters (ASCII or
# Devanagari danda) down to one, e.g. "अध्याय.. १" -> "अध्याय. १",
# "पाठ:: ५" -> "पाठ: ५" — the OCR-robustness requirement's "duplicated
# punctuation" case.
_DUPLICATE_PUNCT_RE = re.compile(rf"([.:,\-–—{_DANDA}])\1+")

# Trailing whitespace/punctuation (ASCII or Devanagari danda) left
# after a heading's core text — stripped entirely, mirroring
# utils.strip_trailing_punctuation's own trailing-cleanup role, just
# extended to also recognize Devanagari punctuation.
_TRAILING_PUNCT_RE = re.compile(rf"[\s.:,\-–—{_DANDA}]+$")


def _normalize_line(text: str) -> str:
    """Shared normalization for every recognizer in this module:
    collapse whitespace, collapse duplicated punctuation, then strip
    trailing punctuation — the "lightweight deterministic
    normalization" the M4.2D spec calls for (explicitly NOT OCR
    correction: no spelling/character repair of any kind)."""
    text = normalize_heading_whitespace(text)
    text = _DUPLICATE_PUNCT_RE.sub(r"\1", text)
    return _TRAILING_PUNCT_RE.sub("", text)


class _DevanagariKeywordHeadingRecognizer(HeadingRecognizer):
    """Private shared base for a Devanagari-script keyword family:
    matches one of `keywords`, optionally followed by a numbering
    marker in either the Arabic or Devanagari digit system. Not
    itself registered with the framework — `name` and `classification`
    remain the framework-required abstract placeholders until a
    concrete subclass sets them, exactly like `HeadingRecognizer`
    itself documents subclasses must.

    A keyword with no following numeral is still a match (e.g. bare
    "सारांश") — this family's headings are frequently un-numbered
    (summaries, exercises, activities), unlike
    ChapterNumberRecognizer's generic family, which requires a
    numeral. Whether a keyword conventionally carries a number
    (`chapter_level_keywords`, e.g. अध्याय/पाठ -> heading level 1) or
    not (heading level 2) is supplied per-subclass rather than
    inferred, since that is a closed, small, language-specific fact
    the calling subclass already knows.
    """

    def __init__(
        self,
        keywords: Sequence[str],
        chapter_level_keywords: Sequence[str],
        settings: Optional[RecognizerSettings] = None,
    ) -> None:
        self._settings = settings
        # Longest-first so a keyword that is a prefix of another
        # (e.g. Hindi "प्रश्न" is a prefix of "प्रश्नावली") does not
        # shadow the longer alternative — re's alternation already
        # backtracks correctly here since the overall pattern is
        # fully anchored (^...$), but ordering longest-first keeps the
        # common case matching without backtracking.
        self._keywords = tuple(sorted(set(keywords), key=len, reverse=True))
        self._chapter_level_keywords = frozenset(chapter_level_keywords)
        keyword_pattern = "|".join(re.escape(k) for k in self._keywords)
        self._pattern = re.compile(
            rf"^(?P<keyword>{keyword_pattern})\s*[-:.]?\s*(?P<numeral>[0-9\u0966-\u096F]+)?$"
        )

    def supports(self, context: RecognitionContext) -> bool:
        text = _normalize_line(context.text)
        return bool(text) and len(text) <= _MAX_CANDIDATE_LENGTH and any(
            text.startswith(k) for k in self._keywords
        )

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        text = _normalize_line(context.text)
        match = self._pattern.match(text)
        if not match:
            return None
        keyword = match.group("keyword")
        numeral_raw = match.group("numeral")
        level = 1 if keyword in self._chapter_level_keywords else 2

        if numeral_raw:
            number = normalize_numeral(numeral_raw)
            if number is None:
                # Matched digits but couldn't resolve to a canonical
                # numeral (shouldn't happen given the pattern's own
                # character class, but recognize() must never raise
                # on a plain "doesn't resolve" case — treat as no
                # match rather than guessing).
                return None
            confidence = combine_confidence(0.95)
            return RecognitionResult(
                recognizer_name=self.name,
                classification=HeadingClassification.CHAPTER_NUMBER,
                confidence=clamp_confidence(confidence),
                level=level,
                number=number,
                title=f"{keyword} {numeral_raw}",
                metadata={"keyword": keyword, "numeral_script": "devanagari" if not numeral_raw.isascii() else "arabic"},
                diagnostics=(f"matched keyword {keyword!r} with numeral {numeral_raw!r} (-> {number})",),
            )

        # Bare keyword, no numbering marker — a real, common pattern
        # for this family (सारांश/निष्कर्ष/टिप्पणी and similar rarely
        # carry a number), so this is a full match, just at a somewhat
        # lower confidence than the numbered case since a bare
        # keyword alone is a weaker structural signal.
        confidence = combine_confidence(0.85)
        return RecognitionResult(
            recognizer_name=self.name,
            classification=HeadingClassification.SECTION_KEYWORD,
            confidence=clamp_confidence(confidence),
            level=level,
            number=None,
            title=keyword,
            metadata={"keyword": keyword},
            diagnostics=(f"matched bare keyword {keyword!r} (no numbering marker)",),
        )


# ===========================================================================
# Hindi keyword family
# ===========================================================================

# अध्याय ("chapter") and पाठ ("lesson") conventionally carry a number
# and head a top-level structural unit -> heading level 1. Every other
# keyword here is a section/exercise-level label within a
# chapter/lesson -> heading level 2.
_HINDI_KEYWORDS: Sequence[str] = (
    "अध्याय", "पाठ", "परिचय", "अभ्यास", "गतिविधि", "उदाहरण",
    "प्रश्नावली", "प्रश्न", "परियोजना", "सारांश", "निष्कर्ष", "टिप्पणी",
)
_HINDI_CHAPTER_LEVEL_KEYWORDS: Sequence[str] = ("अध्याय", "पाठ")


class HindiHeadingRecognizer(_DevanagariKeywordHeadingRecognizer):
    """Recognizes common Hindi textbook heading keywords (अध्याय, पाठ,
    परिचय, अभ्यास, गतिविधि, उदाहरण, प्रश्न, प्रश्नावली, परियोजना,
    सारांश, निष्कर्ष, टिप्पणी), each optionally followed by a
    numbering marker in either the Arabic or Devanagari digit system
    (e.g. "अध्याय १", "अध्याय 1", "पाठ ५", "पाठ 5"), or standing alone
    (e.g. "सारांश")."""

    name = "hindi_heading"
    classification = HeadingClassification.CHAPTER_NUMBER
    default_priority = 15  # alongside ChapterNumberRecognizer's generic-keyword family

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        super().__init__(_HINDI_KEYWORDS, _HINDI_CHAPTER_LEVEL_KEYWORDS, settings=settings)


# ===========================================================================
# Sanskrit keyword family
# ===========================================================================

# अध्यायः / पाठः are the Sanskrit (visarga-suffixed) equivalents of the
# Hindi chapter/lesson keywords above -> heading level 1; the rest are
# section/exercise-level -> heading level 2.
_SANSKRIT_KEYWORDS: Sequence[str] = (
    "अध्यायः", "पाठः", "अभ्यासः", "उदाहरणम्", "प्रश्नाः", "गतिविधिः", "सारांशः",
)
_SANSKRIT_CHAPTER_LEVEL_KEYWORDS: Sequence[str] = ("अध्यायः", "पाठः")


class SanskritHeadingRecognizer(_DevanagariKeywordHeadingRecognizer):
    """Recognizes common Sanskrit textbook heading keywords (अध्यायः,
    पाठः, अभ्यासः, उदाहरणम्, प्रश्नाः, गतिविधिः, सारांशः), each
    optionally followed by a numbering marker in either the Arabic or
    Devanagari digit system, or standing alone."""

    name = "sanskrit_heading"
    classification = HeadingClassification.CHAPTER_NUMBER
    default_priority = 16  # immediately after Hindi: same tier, deterministic tie-break by registration order

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        super().__init__(_SANSKRIT_KEYWORDS, _SANSKRIT_CHAPTER_LEVEL_KEYWORDS, settings=settings)


__all__ = [
    "HindiHeadingRecognizer",
    "SanskritHeadingRecognizer",
]