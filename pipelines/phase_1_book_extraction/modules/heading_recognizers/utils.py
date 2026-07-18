"""
modules/heading_recognizers/utils.py — M4.2A: generic, reusable
helpers future concrete recognizers (M4.2B/C and later) will need.

Framework only: nothing here decides "is this text a heading" — that
judgment belongs entirely to a concrete recognizer. These are plain,
side-effect-free functions any recognizer may import, kept here
rather than duplicated per-recognizer, mirroring
modules/text_utils.py's own role for the Stage D recognizer family
(e.g. its `partial_match_confidence`, which `combine_confidence`
below is deliberately modeled on for a consistent confidence-scoring
convention across both recognizer frameworks).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# ===========================================================================
# Roman numeral parsing
# ===========================================================================

_ROMAN_VALUES = (
    ("M", 1000), ("CM", 900), ("D", 500), ("CD", 400),
    ("C", 100), ("XC", 90), ("L", 50), ("XL", 40),
    ("X", 10), ("IX", 9), ("V", 5), ("IV", 4), ("I", 1),
)

# Strict validating pattern (no repeated-subtractive-pair, no more than
# 3 repeats of I/X/C/M, etc.) — matches well-formed Roman numerals 1-3999.
ROMAN_NUMERAL_RE = re.compile(
    r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)


def is_roman_numeral(token: str) -> bool:
    """True if `token` (case-insensitive) is a well-formed Roman
    numeral in [1, 3999]. Empty string is never a valid numeral."""
    token = (token or "").strip()
    if not token:
        return False
    return bool(ROMAN_NUMERAL_RE.match(token))


def roman_to_int(token: str) -> Optional[int]:
    """Parses a Roman numeral to its integer value, or returns None
    for anything that isn't a well-formed numeral (never raises —
    recognizers are expected to treat a malformed candidate as "not a
    match", not as an error)."""
    token = (token or "").strip().upper()
    if not is_roman_numeral(token):
        return None
    total = 0
    i = 0
    for symbol, value in _ROMAN_VALUES:
        while token[i:i + len(symbol)] == symbol:
            total += value
            i += len(symbol)
    return total if i == len(token) else None


def int_to_roman(value: int) -> Optional[str]:
    """Inverse of `roman_to_int`. Returns None for values outside
    [1, 3999], the range a Roman numeral can represent unambiguously
    with the standard subtractive notation."""
    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= 3999):
        return None
    remaining = value
    parts: List[str] = []
    for symbol, symbol_value in _ROMAN_VALUES:
        count, remaining = divmod(remaining, symbol_value)
        parts.append(symbol * count)
    return "".join(parts)


# ===========================================================================
# Hierarchical numbering parsing (e.g. "1.2.3", "IV.a", "2-1")
# ===========================================================================

# Accepts dot- or dash-separated numeric/alphabetic/roman segments.
# Deliberately permissive at the tokenizing level; a recognizer decides
# which resulting shapes it actually treats as a match.
_HIERARCHICAL_SEP_RE = re.compile(r"[.\-]")


def parse_hierarchical_number(token: str) -> Optional[Tuple[str, ...]]:
    """Splits a dotted/dashed numbering token (e.g. "1.2.3", "2-1-a")
    into its ordered segments as a tuple of strings (e.g.
    ("1", "2", "3")). Returns None for an empty token, a token with an
    empty segment (e.g. "1..2", trailing "1."), or a token containing
    no separator at all (single-segment numbering isn't "hierarchical"
    — callers wanting that should just use the token directly)."""
    token = (token or "").strip()
    if not token:
        return None
    segments = _HIERARCHICAL_SEP_RE.split(token)
    if len(segments) < 2 or any(not seg for seg in segments):
        return None
    return tuple(segments)


def hierarchical_depth(token: str) -> Optional[int]:
    """Number of segments in a hierarchical numbering token (e.g. 3
    for "1.2.3"), or None if `token` doesn't parse as hierarchical."""
    segments = parse_hierarchical_number(token)
    return len(segments) if segments is not None else None


def compare_hierarchical(a: str, b: str) -> Optional[int]:
    """Compares two hierarchical numbering tokens segment-by-segment,
    numerically where a segment is all-digits and lexicographically
    (case-insensitive) otherwise. Returns -1/0/1 like `cmp`, or None
    if either token fails to parse. Shorter-but-equal-prefix sorts
    first (e.g. "1.2" < "1.2.1"), matching normal outline ordering."""
    seg_a = parse_hierarchical_number(a)
    seg_b = parse_hierarchical_number(b)
    if seg_a is None or seg_b is None:
        return None
    for part_a, part_b in zip(seg_a, seg_b):
        if part_a == part_b:
            continue
        if part_a.isdigit() and part_b.isdigit():
            return -1 if int(part_a) < int(part_b) else 1
        return -1 if part_a.lower() < part_b.lower() else 1
    if len(seg_a) == len(seg_b):
        return 0
    return -1 if len(seg_a) < len(seg_b) else 1


# ===========================================================================
# Devanagari numeral parsing (M4.2D: Hindi/Sanskrit heading support)
# ===========================================================================

# Devanagari digits ०-९ (U+0966-U+096F), positionally identical to
# ASCII 0-9 — a plain per-character translation table is sufficient;
# no place-value/grouping logic is needed since Devanagari numerals
# use the same base-10 positional notation as Arabic numerals.
_DEVANAGARI_DIGIT_TO_ARABIC = str.maketrans("०१२३४५६७८९", "0123456789")
_DEVANAGARI_DIGITS = frozenset("०१२३४५६७८९")


def is_devanagari_numeral(token: str) -> bool:
    """True if `token` consists entirely of Devanagari digits (० - ९)
    and is non-empty. Mirrors `is_roman_numeral`'s "empty string is
    never valid" convention."""
    token = (token or "").strip()
    return bool(token) and all(ch in _DEVANAGARI_DIGITS for ch in token)


def devanagari_to_arabic(token: str) -> Optional[str]:
    """Translates a Devanagari-digit numeral to its ASCII-digit
    equivalent (e.g. "५" -> "5", "१२" -> "12"). Returns None for
    anything that isn't a well-formed Devanagari numeral — never
    raises, mirroring `roman_to_int`'s "malformed input is not a
    match" convention rather than an error."""
    if not is_devanagari_numeral(token):
        return None
    return token.translate(_DEVANAGARI_DIGIT_TO_ARABIC)


def normalize_numeral(token: str) -> Optional[str]:
    """Accepts either an Arabic-digit or a Devanagari-digit numeral
    and returns its ASCII-digit form, or None if `token` is neither
    (e.g. mixed digit systems in one token, or non-numeric content).
    The single entry point recognizers should use when a heading's
    numbering marker may be written in either system."""
    token = (token or "").strip()
    if not token:
        return None
    if token.isascii() and token.isdigit():
        return token
    return devanagari_to_arabic(token)


# ===========================================================================
# Common heading text utilities
# ===========================================================================

# Matches a single alphabetic ordinal marker such as "a)", "(b)", "C."
ALPHABETIC_MARKER_RE = re.compile(r"^\(?([a-zA-Z])[).]$")


def is_alphabetic_marker(token: str) -> bool:
    """True for a single-letter ordinal marker like "a)", "(b)", "C."."""
    return bool(ALPHABETIC_MARKER_RE.match((token or "").strip()))


def alphabetic_marker_to_index(token: str) -> Optional[int]:
    """1-based index for an alphabetic marker ("a" -> 1, "b" -> 2, ...
    case-insensitive), or None if `token` isn't one."""
    match = ALPHABETIC_MARKER_RE.match((token or "").strip())
    if not match:
        return None
    return ord(match.group(1).lower()) - ord("a") + 1


def strip_trailing_punctuation(text: str) -> str:
    """Removes trailing colons/periods/dashes/whitespace commonly left
    on a heading label after its numbering marker is stripped off
    (e.g. "Introduction :" -> "Introduction"). Never strips leading
    content and never raises on an empty string."""
    return re.sub(r"[\s:.\-–—]+$", "", text or "")


def normalize_heading_whitespace(text: str) -> str:
    """Collapses internal whitespace runs to a single space and trims
    the ends — the minimal, format-preserving normalization every
    recognizer needs before pattern-matching heading text, without
    altering case or punctuation (callers needing that do it
    themselves, since it's pattern-specific)."""
    return re.sub(r"\s+", " ", (text or "").strip())


# ===========================================================================
# Confidence helpers
# ===========================================================================


def clamp_confidence(value: float) -> float:
    """Clamps `value` into [0.0, 1.0]. Never raises — a caller passing
    a NaN-free out-of-range float (e.g. from an intermediate
    computation) gets a valid confidence back rather than a crash."""
    return max(0.0, min(1.0, float(value)))


def combine_confidence(*scores: float, base: float = 1.0) -> float:
    """Combines several independent [0, 1] sub-confidences (e.g. "does
    the numbering match" x "does the font-size hint match" x "is
    position plausible") into one overall confidence, modeled on
    modules/text_utils.partial_match_confidence's own multiplicative
    approach: multiplies `base` by every score in turn and clamps the
    result, so any single weak signal appropriately pulls the overall
    confidence down rather than being averaged away by strong ones."""
    result = base
    for score in scores:
        result *= clamp_confidence(score)
    return clamp_confidence(result)


def meets_threshold(confidence: float, threshold: float) -> bool:
    """True if `confidence >= threshold`, both clamped into [0, 1]
    first so a caller doesn't need to pre-validate either value."""
    return clamp_confidence(confidence) >= clamp_confidence(threshold)


__all__ = [
    "ROMAN_NUMERAL_RE",
    "is_roman_numeral",
    "roman_to_int",
    "int_to_roman",
    "parse_hierarchical_number",
    "hierarchical_depth",
    "compare_hierarchical",
    "is_devanagari_numeral",
    "devanagari_to_arabic",
    "normalize_numeral",
    "ALPHABETIC_MARKER_RE",
    "is_alphabetic_marker",
    "alphabetic_marker_to_index",
    "strip_trailing_punctuation",
    "normalize_heading_whitespace",
    "clamp_confidence",
    "combine_confidence",
    "meets_threshold",
]