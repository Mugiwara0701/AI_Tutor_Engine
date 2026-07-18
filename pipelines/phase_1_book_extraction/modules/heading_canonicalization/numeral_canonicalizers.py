"""
modules/heading_canonicalization/numeral_canonicalizers.py — M4.3B:
Number System Canonicalization.

Adds four cooperating `HeadingCanonicalizer` implementations to the
M4.3A framework — nothing in `base.py`, `config.py`, `registry.py`, or
`pipeline.py` is changed, exactly as that framework's "extension
without modification" contract promises:

    NumberingSystemDetector       — detection only (requirement #4):
                                    decides ROMAN / ARABIC / DEVANAGARI
                                    / NONE / UNKNOWN from the character
                                    shape of `original_numbering`,
                                    before anything is converted.
    RomanNumeralCanonicalizer     — requirement #1
    ArabicNumeralCanonicalizer    — requirement #2
    DevanagariNumeralCanonicalizer — requirement #3

Two-phase design: detection is a separate, earlier step
(`NumberingSystemDetector`, lower `default_priority`) from conversion
(the three numeral-specific canonicalizers, which only act once
`heading.numbering_system` already names their own system). This
keeps "what kind of numbering is this" and "convert this numbering to
an integer, or explain why not" as two distinct, independently
testable concerns, while still being three-plus-one ordinary
`HeadingCanonicalizer` steps cooperating through the same
`CanonicalizationPipeline` every other canonicalizer uses — no
bypass, no standalone conversion path outside the framework.

Malformed input never raises out of `canonicalize()`: every failure
path returns an updated `CanonicalHeading` carrying a human-readable
diagnostic (`CanonicalHeading.with_diagnostic()`, the same bookkeeping
mechanism M4.3A already defined) rather than leaving
`canonical_number`/`numbering_system` silently unset or letting an
exception propagate. The pipeline itself (`safe_canonicalize()`,
unchanged) remains the backstop for a genuine bug in this code, not a
substitute for handling expected malformed input here.
"""
from __future__ import annotations

from typing import Optional

from modules.heading_canonicalization.base import CanonicalizationContext, HeadingCanonicalizer
from modules.heading_canonicalization.enums import NumberingSystem
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.numeral_utils import (
    devanagari_to_int,
    is_arabic_numeral,
    is_devanagari_char,
    roman_to_int,
)


class NumberingSystemDetector(HeadingCanonicalizer):
    """Determines which numbering system `heading.original_numbering`
    was written in, purely from its character shape — no conversion,
    no validation of well-formedness beyond "which alphabet/digit set
    is this". Runs before the three numeral-specific canonicalizers
    (lower `default_priority`) so each of them can simply check
    `heading.numbering_system` instead of re-deriving it itself.

    Detection outcomes:
        NONE    — `original_numbering` is missing or blank (a heading
                  legitimately has no numbering marker at all).
        DEVANAGARI — contains at least one character in the Devanagari
                  Unicode block, regardless of whether every character
                  turns out to be a valid digit (that finer check is
                  `DevanagariNumeralCanonicalizer`'s job).
        ARABIC  — every character is an ASCII digit.
        ROMAN   — every character is one of I/V/X/L/C/D/M
                  (case-insensitive), regardless of whether the
                  sequence is a well-formed numeral (that finer check
                  is `RomanNumeralCanonicalizer`'s job).
        UNKNOWN (unchanged) — anything else, e.g. a mix of digits and
                  letters, or characters outside all three supported
                  systems ("mixed numeral systems" / "unsupported
                  numbering formats" from the M4.3B spec). A
                  diagnostic is recorded and `numbering_system` is
                  left at its `UNKNOWN` default so downstream stages
                  can tell "detection ran and found nothing usable"
                  apart from "detection hasn't run yet" — the pipeline
                  never crashes on this input.
    """

    name = "numbering_system_detector"
    default_priority = 10

    def supports(self, heading: CanonicalHeading, context: CanonicalizationContext) -> bool:
        return heading.numbering_system == NumberingSystem.UNKNOWN

    def canonicalize(
        self, heading: CanonicalHeading, context: CanonicalizationContext
    ) -> Optional[CanonicalHeading]:
        raw = heading.original_numbering
        if raw is None or not raw.strip():
            return heading.with_updates(numbering_system=NumberingSystem.NONE)

        candidate = raw.strip()

        if any(is_devanagari_char(ch) for ch in candidate):
            return heading.with_updates(numbering_system=NumberingSystem.DEVANAGARI)

        if is_arabic_numeral(candidate):
            return heading.with_updates(numbering_system=NumberingSystem.ARABIC)

        if all(ch.upper() in "IVXLCDM" for ch in candidate):
            return heading.with_updates(numbering_system=NumberingSystem.ROMAN)

        return heading.with_diagnostic(
            f"numbering_system_detector: unsupported or mixed numbering format: {raw!r}"
        )


class RomanNumeralCanonicalizer(HeadingCanonicalizer):
    """Converts a heading whose numbering was detected as `ROMAN`
    into its canonical integer value (requirement #1). Rejects
    malformed Roman numerals (e.g. "IIII", "VX", "IIV") by recording a
    diagnostic and leaving `canonical_number` unset, rather than
    guessing at a value or raising."""

    name = "roman_numeral_canonicalizer"
    default_priority = 20

    def supports(self, heading: CanonicalHeading, context: CanonicalizationContext) -> bool:
        return heading.numbering_system == NumberingSystem.ROMAN and heading.canonical_number is None

    def canonicalize(
        self, heading: CanonicalHeading, context: CanonicalizationContext
    ) -> Optional[CanonicalHeading]:
        value = roman_to_int(heading.original_numbering)
        if value is None:
            return heading.with_diagnostic(
                f"roman_numeral_canonicalizer: malformed roman numeral: {heading.original_numbering!r}"
            )
        return heading.with_updates(canonical_number=str(value))


class ArabicNumeralCanonicalizer(HeadingCanonicalizer):
    """Converts a heading whose numbering was detected as `ARABIC`
    into its canonical integer value (requirement #2). Since
    `NumberingSystemDetector` only assigns `ARABIC` to a string that
    is already all ASCII digits, conversion here cannot fail — this
    canonicalizer never records a diagnostic, only a value."""

    name = "arabic_numeral_canonicalizer"
    default_priority = 20

    def supports(self, heading: CanonicalHeading, context: CanonicalizationContext) -> bool:
        return heading.numbering_system == NumberingSystem.ARABIC and heading.canonical_number is None

    def canonicalize(
        self, heading: CanonicalHeading, context: CanonicalizationContext
    ) -> Optional[CanonicalHeading]:
        candidate = (heading.original_numbering or "").strip()
        if not candidate:
            # Structurally shouldn't happen (detector only assigns
            # ARABIC to a non-empty all-digit string), but never raise
            # on a surprise here — leave canonical_number unset.
            return heading.with_diagnostic(
                "arabic_numeral_canonicalizer: expected an all-digit numbering but found none"
            )
        return heading.with_updates(canonical_number=str(int(candidate)))


class DevanagariNumeralCanonicalizer(HeadingCanonicalizer):
    """Converts a heading whose numbering was detected as
    `DEVANAGARI` into its canonical integer value (requirement #3).
    `NumberingSystemDetector` only requires *one* Devanagari character
    to assign this system, so this canonicalizer still has to check
    every character is actually one of the ten Devanagari digits
    (०-९) — rejecting, with a diagnostic, any other Devanagari
    character (e.g. a Devanagari letter) mixed into the numbering."""

    name = "devanagari_numeral_canonicalizer"
    default_priority = 20

    def supports(self, heading: CanonicalHeading, context: CanonicalizationContext) -> bool:
        return heading.numbering_system == NumberingSystem.DEVANAGARI and heading.canonical_number is None

    def canonicalize(
        self, heading: CanonicalHeading, context: CanonicalizationContext
    ) -> Optional[CanonicalHeading]:
        value = devanagari_to_int(heading.original_numbering)
        if value is None:
            return heading.with_diagnostic(
                "devanagari_numeral_canonicalizer: invalid devanagari numeral: "
                f"{heading.original_numbering!r} contains a non-digit character"
            )
        return heading.with_updates(canonical_number=str(value))


__all__ = [
    "NumberingSystemDetector",
    "RomanNumeralCanonicalizer",
    "ArabicNumeralCanonicalizer",
    "DevanagariNumeralCanonicalizer",
]
