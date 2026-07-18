"""
modules/heading_canonicalization/numeral_utils.py — M4.3B: pure,
deterministic numeral-parsing helpers used by the concrete
canonicalizers in `numeral_canonicalizers.py`.

These are plain functions, not `HeadingCanonicalizer` implementations
— they contain no framework wiring (no registry, no pipeline, no
`CanonicalHeading`) and are only ever called FROM a canonicalizer's
`canonicalize()`, exactly as `README.md`'s own
`RomanNumeralCanonicalizer` example sketches (`value =
roman_to_int(heading.original_numbering)`). Keeping the character-
level parsing logic here — separate from the canonicalizers that call
it — keeps each canonicalizer's `canonicalize()` a short, readable
"detect applicability, call a pure helper, wrap the result" method,
mirroring how `heading_recognizers` keeps its own regex/parsing
helpers in `utils.py` rather than inline in each recognizer.

Every function here is pure: same input always produces the same
output, no exceptions raised for "doesn't apply" or "malformed" input
(both are reported via a `None` return), no I/O, no reliance on
anything beyond the function's own arguments — the foundation M4.3B's
"Deterministic Behaviour" requirement rests on.
"""
from __future__ import annotations

import re
from typing import Optional

#: The exact ten Devanagari digit characters (U+0966-U+096F), in
#: ascending numeric order — the only characters
#: `devanagari_to_int()` accepts. Keyed by character for O(1) lookup.
DEVANAGARI_DIGIT_MAP = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
}

#: Every character a well-formed (or malformed-but-plausibly-Roman)
#: Roman numeral may contain, case-insensitive. Used only for
#: *detection* ("does this look like it was meant to be a Roman
#: numeral") — `roman_to_int()` below is what actually validates
#: well-formedness.
ROMAN_CHARS = frozenset("IVXLCDMivxlcdm")

#: Strict Roman-numeral grammar: at most 4 thousands, then the
#: standard subtractive-or-additive pattern per place value (hundreds,
#: tens, ones). Deliberately rejects non-canonical forms like "IIII",
#: "VX", or "IIV" — anything not matched here is malformed, not just
#: unusually written.
_ROMAN_PATTERN = re.compile(
    r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$"
)

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def is_devanagari_char(ch: str) -> bool:
    """True if `ch` falls within the Devanagari Unicode block
    (U+0900-U+097F) — used by the numbering-system detector to decide
    "this numbering was written in Devanagari script" independent of
    whether every character in it is actually a valid digit (that
    finer-grained check is `devanagari_to_int()`'s job)."""
    return len(ch) == 1 and "\u0900" <= ch <= "\u097f"


def roman_to_int(raw: Optional[str]) -> Optional[int]:
    """Converts a well-formed Roman numeral to its integer value.
    Returns `None` — never raises — for anything malformed: empty
    input, invalid characters, or a character sequence that violates
    Roman numeral subtraction/repetition rules (e.g. "IIII", "VX",
    "IIV", "MMMM" beyond the supported range). Case-insensitive.
    Pure and deterministic: the same string always yields the same
    result."""
    if not raw:
        return None
    candidate = raw.strip().upper()
    if not candidate or not _ROMAN_PATTERN.fullmatch(candidate):
        return None

    total = 0
    previous_value = 0
    for ch in reversed(candidate):
        value = _ROMAN_VALUES[ch]
        if value < previous_value:
            total -= value
        else:
            total += value
            previous_value = value
    return total


def devanagari_to_int(raw: Optional[str]) -> Optional[int]:
    """Converts a string of Devanagari digit characters (०-९) to its
    integer value, tolerating leading zeros (e.g. "०१२" -> 12).
    Returns `None` — never raises — if `raw` is empty or contains any
    character that is not one of the ten Devanagari digits."""
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    try:
        ascii_digits = "".join(DEVANAGARI_DIGIT_MAP[ch] for ch in candidate)
    except KeyError:
        return None
    return int(ascii_digits)


def is_arabic_numeral(raw: Optional[str]) -> bool:
    """True if `raw`, stripped, is one or more ASCII digits and
    nothing else. Used for numbering-system detection; the actual
    conversion for a confirmed Arabic numeral is a plain `int()` call
    (see `ArabicNumeralCanonicalizer`), since any all-ASCII-digit
    string is already a valid integer literal."""
    if not raw:
        return False
    candidate = raw.strip()
    return candidate.isascii() and candidate.isdigit()


__all__ = [
    "DEVANAGARI_DIGIT_MAP",
    "ROMAN_CHARS",
    "is_devanagari_char",
    "roman_to_int",
    "devanagari_to_int",
    "is_arabic_numeral",
]
