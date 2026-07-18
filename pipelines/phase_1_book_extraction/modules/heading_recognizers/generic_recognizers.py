"""
modules/heading_recognizers/generic_recognizers.py — M4.2B: the first
set of concrete heading recognizers.

Implements the "generic" family of heading patterns: patterns that
recur across textbooks regardless of subject or language (arabic
numbering, hierarchical numbering, Roman numerals, single-letter
alphabetic markers, "Chapter N" / "Unit N" / "Lesson N" identifiers,
and bare structural chapter titles). Every recognizer here:

  * subclasses `HeadingRecognizer` (base.py, M4.2A) and implements
    only `recognize()` (+ `supports()` where a cheap pre-filter is
    worthwhile);
  * is registered with the framework via ONE
    `factory.register_class(name, RecognizerClass)` call in
    `modules/heading_recognizers/__init__.py` — nothing in base.py,
    config.py, registry.py, pipeline.py, enums.py, or utils.py needed
    to change to add these;
  * is pure, deterministic, and cheap — no OCR, no PDF parsing, no
    layout analysis, no ML/LLM inference (all out of scope per the
    M4.2B spec: this module only classifies a `RecognitionContext`'s
    already-extracted `text`);
  * is language-independent: only ASCII digits, Roman-numeral
    letters, and Latin alphabetic markers are recognized here.
    Devanagari numerals and any Hindi/Sanskrit-specific pattern are
    explicitly out of scope for M4.2B and are NOT implemented in this
    module (a later milestone's concern);
  * reuses modules/heading_recognizers/utils.py rather than
    reimplementing Roman-numeral parsing, hierarchical-number
    parsing, alphabetic-marker parsing, whitespace/punctuation
    normalization, or confidence combination.

Each recognizer accepts an optional `settings: RecognizerSettings`
constructor argument (mirroring the factory's default builder, which
calls `cls(settings=settings)` first and falls back to a no-arg
constructor) purely so a recognizer that wants deployment-tunable
behaviour (currently only `ChapterNumberRecognizer`'s keyword list)
can read it from `settings.extra`; the settings object is never
required and every recognizer here works out of the box with no
configuration at all, per HeadingRecognitionConfig.settings_for()'s
own zero-config-required contract.
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

from modules.heading_recognizers.base import HeadingRecognizer, RecognitionContext, RecognitionResult
from modules.heading_recognizers.config import RecognizerSettings
from modules.heading_recognizers.enums import HeadingClassification
from modules.heading_recognizers.utils import (
    alphabetic_marker_to_index,
    clamp_confidence,
    combine_confidence,
    hierarchical_depth,
    is_alphabetic_marker,
    is_roman_numeral,
    normalize_heading_whitespace,
    parse_hierarchical_number,
    roman_to_int,
    strip_trailing_punctuation,
)

# A heading candidate is a short line by construction (a chapter/section
# label, not a paragraph) — used by several recognizers below as a cheap
# `supports()` pre-filter so obviously-irrelevant (very long) lines are
# recorded as SKIPPED by the pipeline rather than paying for a full
# recognize() + regex match.
_MAX_CANDIDATE_LENGTH = 120


def _clean(text: str) -> str:
    """Shared first step for every recognizer in this module: collapse
    whitespace and trim, without altering case/punctuation (that's
    each recognizer's own concern)."""
    return normalize_heading_whitespace(text)


# ===========================================================================
# 1. NumberedHeadingRecognizer — "1", "2", "10", "25"
# ===========================================================================

# Bare 1-3 digit number, optionally followed by a single trailing "."
# or ")" marker. Deliberately does NOT match a token containing "." or
# "-" mid-string (e.g. "1.1", "2-1") — those belong to
# HierarchicalHeadingRecognizer, not here. A leading zero (e.g. "01")
# is rejected: textbook chapter/section numbering never zero-pads.
_NUMBERED_RE = re.compile(r"^(0|[1-9]\d{0,2})([.)])?$")


class NumberedHeadingRecognizer(HeadingRecognizer):
    """Recognizes a bare arabic-numeral heading label such as "1",
    "12", "1.", or "3)". Rejects multi-segment numbering (that's
    HierarchicalHeadingRecognizer's job), leading zeros, and anything
    that isn't purely numeric plus at most one trailing marker
    character."""

    name = "numbered_heading"
    classification = HeadingClassification.NUMBERED
    default_priority = 20

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        self._settings = settings

    def supports(self, context: RecognitionContext) -> bool:
        text = _clean(context.text)
        return bool(text) and len(text) <= 6

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        text = _clean(context.text)
        match = _NUMBERED_RE.match(text)
        if not match:
            return None
        digits, marker = match.group(1), match.group(2)
        if digits == "0":
            # "0" alone is almost never a real heading number; still a
            # structural match, but at very low confidence rather than
            # an outright rejection (a malformed-but-plausible OCR
            # artifact might legitimately be "0" for a preface).
            confidence = combine_confidence(0.3)
        else:
            # A trailing "." or ")" marker is a small positive signal
            # (textbooks commonly write "1." for sections); its absence
            # is not penalized since a bare "1" is just as valid.
            confidence = combine_confidence(0.9, 1.0 if marker else 0.95)
        return RecognitionResult(
            recognizer_name=self.name,
            classification=self.classification,
            confidence=clamp_confidence(confidence),
            level=2,
            number=digits,
            title=None,
            diagnostics=(f"matched bare numeric token {digits!r}" + (f" with marker {marker!r}" if marker else ""),),
        )


# ===========================================================================
# 2. HierarchicalHeadingRecognizer — "1.1", "2.3", "4.5.2", "7.3.4.1"
# ===========================================================================

# Every segment must be purely numeric (this recognizer is the
# arabic-hierarchical family only — an alpha/roman segment such as
# "IV.a" is out of scope here and is left unmatched by design).
_HIERARCHICAL_SEGMENT_RE = re.compile(r"^\d{1,3}$")


class HierarchicalHeadingRecognizer(HeadingRecognizer):
    """Recognizes dot-separated numeric hierarchical numbering such as
    "1.1", "2.3", "4.5.2", "7.3.4.1", at arbitrary depth. Rejects a
    single (non-hierarchical) segment, any empty segment (e.g. "1..2",
    trailing "1."), and any non-numeric segment."""

    name = "hierarchical_heading"
    classification = HeadingClassification.HIERARCHICAL
    default_priority = 10  # ahead of NumberedHeadingRecognizer: "1.1" must not fall through to "numbered"

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        self._settings = settings

    def supports(self, context: RecognitionContext) -> bool:
        text = _clean(context.text)
        return bool(text) and "." in text and len(text) <= 20

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        text = strip_trailing_punctuation(_clean(context.text))
        segments = parse_hierarchical_number(text)
        if segments is None:
            return None
        if not all(_HIERARCHICAL_SEGMENT_RE.match(seg) for seg in segments):
            return None
        depth = hierarchical_depth(text)
        if depth is None or depth < 2:
            return None
        # Deeper nesting is intrinsically less ambiguous with other
        # patterns (a 4-segment number is unmistakably hierarchical),
        # so confidence rises slightly with depth, capped at 4 levels'
        # worth of bonus.
        confidence = combine_confidence(0.9, 1.0 + min(depth - 2, 2) * 0.0)
        return RecognitionResult(
            recognizer_name=self.name,
            classification=self.classification,
            confidence=clamp_confidence(confidence),
            level=min(depth, 6),
            number=text,
            title=None,
            diagnostics=(f"parsed {depth} hierarchical segments: {segments!r}",),
        )


# ===========================================================================
# 3. RomanNumeralHeadingRecognizer — "I", "II", "III", "IV", ..., "XX"
# ===========================================================================

class RomanNumeralHeadingRecognizer(HeadingRecognizer):
    """Recognizes a bare Roman-numeral heading label ("I", "IV", "XIV",
    "XX", ...), optionally followed by a single trailing "." or ")"
    marker. Reuses `utils.is_roman_numeral` / `utils.roman_to_int`
    (M4.2A) rather than re-implementing Roman-numeral validation, so
    malformed numerals (e.g. "IIII", "VX") are rejected exactly as
    utils.py already defines "well-formed"."""

    name = "roman_numeral_heading"
    classification = HeadingClassification.ROMAN_NUMERAL
    default_priority = 30

    _TRAILING_MARKER_RE = re.compile(r"^([A-Za-z]+)([.)])?$")

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        self._settings = settings

    def supports(self, context: RecognitionContext) -> bool:
        text = _clean(context.text)
        if not text:
            return False
        bare = len(text) <= 8 and text.isalpha()
        marked = len(text) <= 9 and len(text) >= 2 and text[:-1].isalpha() and text[-1] in ")."
        return bare or marked

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        text = _clean(context.text)
        match = self._TRAILING_MARKER_RE.match(text)
        if not match:
            return None
        token, marker = match.group(1), match.group(2)
        if not is_roman_numeral(token):
            return None
        value = roman_to_int(token)
        if value is None:
            return None
        # A single "I" is maximally ambiguous with a stray capital
        # letter / alphabetic marker; longer, multi-letter numerals
        # (II, IV, XIV, ...) are unambiguously Roman. Confidence
        # reflects that rather than treating every valid numeral alike.
        base = 0.6 if len(token) == 1 else 0.9
        confidence = combine_confidence(base, 1.0 if marker else 0.97)
        return RecognitionResult(
            recognizer_name=self.name,
            classification=self.classification,
            confidence=clamp_confidence(confidence),
            level=2,
            number=token.upper(),
            title=None,
            metadata={"integer_value": value},
            diagnostics=(f"parsed Roman numeral {token.upper()!r} = {value}",),
        )


# ===========================================================================
# 4. AlphabeticHeadingRecognizer — "A", "B", "C", "D"
# ===========================================================================

_BARE_LETTER_RE = re.compile(r"^([A-Za-z])$")


class AlphabeticHeadingRecognizer(HeadingRecognizer):
    """Recognizes a single-letter heading label — either bare ("A",
    "b") or an explicitly-marked ordinal ("a)", "(b)", "C.", reusing
    `utils.is_alphabetic_marker` / `utils.alphabetic_marker_to_index`
    from M4.2A). Deliberately narrow (exactly one letter, optionally
    wrapped in marker punctuation) so ordinary running text is never
    mistaken for a heading: "As" or "I am" cannot match, only a
    single isolated letter can."""

    name = "alphabetic_heading"
    classification = HeadingClassification.ALPHABETIC
    default_priority = 40

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        self._settings = settings

    def supports(self, context: RecognitionContext) -> bool:
        text = _clean(context.text)
        return bool(text) and len(text) <= 4

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        text = _clean(context.text)

        bare = _BARE_LETTER_RE.match(text)
        if bare:
            letter = bare.group(1).upper()
            index = ord(letter) - ord("A") + 1
            return RecognitionResult(
                recognizer_name=self.name,
                classification=self.classification,
                confidence=clamp_confidence(combine_confidence(0.55)),
                level=3,
                number=letter,
                title=None,
                metadata={"index": index},
                diagnostics=(f"matched bare single letter {letter!r}",),
            )

        if is_alphabetic_marker(text):
            index = alphabetic_marker_to_index(text)
            letter = chr(ord("A") + index - 1) if index else None
            return RecognitionResult(
                recognizer_name=self.name,
                classification=self.classification,
                confidence=clamp_confidence(combine_confidence(0.85)),
                level=3,
                number=letter,
                title=None,
                metadata={"index": index} if index else {},
                diagnostics=(f"matched alphabetic marker {text!r}",),
            )

        return None


# ===========================================================================
# 5. ChapterNumberRecognizer — "Chapter 1", "Chapter IV", "Unit 3", "Lesson 5"
# ===========================================================================

_DEFAULT_CHAPTER_KEYWORDS: Sequence[str] = ("chapter", "unit", "lesson")


class ChapterNumberRecognizer(HeadingRecognizer):
    """Recognizes a keyword + numeral chapter/unit/lesson identifier,
    e.g. "Chapter 1", "Chapter IV", "Unit 3", "Lesson 5". The keyword
    list is configurable via `RecognizerSettings.extra["keywords"]`
    (defaulting to `chapter` / `unit` / `lesson`) so a deployment can
    extend it (e.g. add "Module") without a code change, per the
    spec's "use configurable patterns where appropriate"."""

    name = "chapter_number"
    classification = HeadingClassification.CHAPTER_NUMBER
    default_priority = 5  # must win over the bare numeral/roman recognizers on the same line

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        self._settings = settings
        keywords = _DEFAULT_CHAPTER_KEYWORDS
        if settings is not None:
            configured = settings.extra.get("keywords")
            if configured:
                keywords = tuple(configured)
        self._keywords = tuple(k.lower() for k in keywords)
        keyword_pattern = "|".join(re.escape(k) for k in self._keywords)
        self._pattern = re.compile(
            rf"^(?P<keyword>{keyword_pattern})\s*[.:-]?\s*(?P<numeral>[A-Za-z0-9]+)\s*[.:-]?$",
            re.IGNORECASE,
        )

    def supports(self, context: RecognitionContext) -> bool:
        text = _clean(context.text).lower()
        return bool(text) and len(text) <= _MAX_CANDIDATE_LENGTH and any(text.startswith(k) for k in self._keywords)

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        text = _clean(context.text)
        match = self._pattern.match(text)
        if not match:
            return None
        keyword = match.group("keyword")
        numeral = match.group("numeral")

        arabic_value: Optional[int] = int(numeral) if numeral.isdigit() else None
        roman_value = roman_to_int(numeral) if arabic_value is None else None
        if arabic_value is None and roman_value is None:
            # Neither a plain arabic number nor a well-formed Roman
            # numeral followed the keyword — not a chapter identifier
            # this recognizer can confidently resolve.
            return None

        confidence = combine_confidence(0.95)
        metadata = {"keyword": keyword.title()}
        if arabic_value is not None:
            metadata["integer_value"] = arabic_value
        else:
            metadata["integer_value"] = roman_value

        return RecognitionResult(
            recognizer_name=self.name,
            classification=self.classification,
            confidence=clamp_confidence(confidence),
            level=1,
            number=numeral,
            title=f"{keyword.title()} {numeral}",
            metadata=metadata,
            diagnostics=(f"matched keyword {keyword!r} with numeral {numeral!r}",),
        )


# ===========================================================================
# 6. ChapterTitleRecognizer — "Motion", "Electricity", "The Living World"
# ===========================================================================

# Purely structural: how many words, how they're capitalized, whether
# trailing punctuation looks like a sentence rather than a label — no
# subject-specific vocabulary of any kind, per the spec's "structural
# heuristics only" / "do not use subject-specific rules".
_MAX_TITLE_WORDS = 6
_MAX_TITLE_LENGTH = 60
_SENTENCE_END_RE = re.compile(r"[.!?]$")
_LOWERCASE_FUNCTION_WORDS = {
    "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "with", "our",
}


def _looks_title_cased(words: Sequence[str]) -> bool:
    """True if every word is either fully uppercase (acronym-like, e.g.
    "DNA") or starts with an uppercase letter — except common short
    function words, which are allowed to stay lowercase mid-title
    ("The Living World", "Our Environment")."""
    for i, word in enumerate(words):
        core = re.sub(r"[^A-Za-z]", "", word)
        if not core:
            return False
        if i > 0 and core.lower() in _LOWERCASE_FUNCTION_WORDS:
            continue
        if not core[0].isupper():
            return False
    return True


class ChapterTitleRecognizer(HeadingRecognizer):
    """Recognizes a standalone textbook chapter title using structural
    heuristics only: short (<= 6 words / 60 characters), no sentence-
    ending punctuation, no leading digit, and title-cased (allowing
    common function words like "the"/"of"/"our" to stay lowercase).
    Deliberately the lowest-priority, lowest-base-confidence generic
    recognizer — a bare piece of title-cased short text is the
    weakest structural signal of the six, so it should only win a
    conflict when nothing more specific (numbered/hierarchical/roman/
    alphabetic/chapter-number) also matched the same line."""

    name = "chapter_title"
    classification = HeadingClassification.CHAPTER_TITLE
    default_priority = 90

    def __init__(self, settings: Optional[RecognizerSettings] = None) -> None:
        self._settings = settings

    def supports(self, context: RecognitionContext) -> bool:
        text = _clean(context.text)
        return bool(text) and len(text) <= _MAX_TITLE_LENGTH

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        text = _clean(context.text)
        if not text or text[0].isdigit():
            return None
        # A real chapter title is more than a single character — this
        # also keeps single-letter/numeral tokens ("I", "A") as the
        # sole concern of AlphabeticHeadingRecognizer /
        # RomanNumeralHeadingRecognizer rather than a spurious
        # structural "title" match here.
        if len(text) < 3:
            return None
        if _SENTENCE_END_RE.search(text):
            return None

        words = text.split(" ")
        if not (1 <= len(words) <= _MAX_TITLE_WORDS):
            return None
        if not all(re.search(r"[A-Za-z]", w) for w in words):
            return None
        if not _looks_title_cased(words):
            return None

        # Structural confidence: shorter titles (1-3 words) are the
        # strongest signal; longer ones ("The Living World", 3 words)
        # still count but taper off toward the 6-word ceiling.
        length_score = 1.0 if len(words) <= 3 else max(0.6, 1.0 - 0.1 * (len(words) - 3))
        # A preceding chapter-level heading (level 1) immediately
        # before this line is a positive structural hint that this
        # line is the chapter's title, not just capitalized text; its
        # absence (e.g. `preceding_heading_level` simply unknown) is
        # not penalized much, since most contexts won't carry it.
        context_score = 1.0 if context.preceding_heading_level == 1 else 0.9
        confidence = combine_confidence(0.7, length_score, context_score)

        return RecognitionResult(
            recognizer_name=self.name,
            classification=self.classification,
            confidence=clamp_confidence(confidence),
            level=1,
            number=None,
            title=text,
            diagnostics=(
                f"structural match: {len(words)} title-cased word(s), no sentence punctuation",
            ),
        )


__all__ = [
    "NumberedHeadingRecognizer",
    "HierarchicalHeadingRecognizer",
    "RomanNumeralHeadingRecognizer",
    "AlphabeticHeadingRecognizer",
    "ChapterNumberRecognizer",
    "ChapterTitleRecognizer",
]
