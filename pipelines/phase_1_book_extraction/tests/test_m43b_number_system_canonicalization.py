"""
tests/test_m43b_number_system_canonicalization.py — M4.3B unit tests
for deterministic Number System Canonicalization
(modules/heading_canonicalization/numeral_utils.py +
numeral_canonicalizers.py).

Coverage:
  - numeral_utils: roman_to_int (valid, invalid, subtraction rules,
    edge cases), devanagari_to_int (single/multi digit, leading
    zeros, invalid characters), is_arabic_numeral, is_devanagari_char
  - NumberingSystemDetector: correct system detection for Roman /
    Arabic / Devanagari / empty (NONE) / mixed-or-unsupported (UNKNOWN
    + diagnostic)
  - RomanNumeralCanonicalizer / ArabicNumeralCanonicalizer /
    DevanagariNumeralCanonicalizer: conversion, malformed-input
    handling, non-applicability
  - End-to-end via CanonicalizationPipeline + default_registry:
    Chapter III / Chapter 3 / अध्याय ३ all resolve to canonical_number
    "3" with the expected numbering_system; the pipeline never raises
  - Determinism: identical input always produces identical output
  - Regression: all M4.2 and M4.3A tests continue to pass (not
    re-executed here — see test_m42*.py / test_m43a_*.py — but this
    file never modifies or bypasses the frozen framework those tests
    exercise)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.heading_canonicalization.base import CanonicalizationContext
from modules.heading_canonicalization.enums import CanonicalizationOutcome, NumberingSystem
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.numeral_canonicalizers import (
    ArabicNumeralCanonicalizer,
    DevanagariNumeralCanonicalizer,
    NumberingSystemDetector,
    RomanNumeralCanonicalizer,
)
from modules.heading_canonicalization.numeral_utils import (
    devanagari_to_int,
    is_arabic_numeral,
    is_devanagari_char,
    roman_to_int,
)
from modules.heading_canonicalization.pipeline import CanonicalizationPipeline
from modules.heading_canonicalization.registry import CanonicalizerRegistry, default_registry

from modules.heading_recognizers.enums import HeadingClassification


def _make_heading(**overrides) -> CanonicalHeading:
    defaults = dict(
        original_text="Chapter 3",
        recognized_classification=HeadingClassification.CHAPTER_NUMBER,
        recognized_confidence=0.9,
        level=1,
        original_numbering="3",
        original_language="en",
    )
    defaults.update(overrides)
    return CanonicalHeading(**defaults)


# ===========================================================================
# numeral_utils — pure functions
# ===========================================================================

class RomanToIntTests(unittest.TestCase):
    def test_basic_valid_numerals(self):
        cases = {
            "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
            "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
        }
        for numeral, expected in cases.items():
            with self.subTest(numeral=numeral):
                self.assertEqual(roman_to_int(numeral), expected)

    def test_larger_valid_numerals(self):
        cases = {
            "XL": 40, "L": 50, "XC": 90, "C": 100,
            "CD": 400, "D": 500, "CM": 900, "M": 1000,
            "MCMXCIV": 1994, "MMXXIV": 2024, "MMMCMXCIX": 3999,
        }
        for numeral, expected in cases.items():
            with self.subTest(numeral=numeral):
                self.assertEqual(roman_to_int(numeral), expected)

    def test_case_insensitive(self):
        self.assertEqual(roman_to_int("iii"), 3)
        self.assertEqual(roman_to_int("Mcmxciv"), 1994)

    def test_subtraction_rules_enforced(self):
        # IIII (non-canonical repetition) and IIV/VX (invalid
        # subtraction) must be rejected even though they only use
        # valid Roman characters.
        for malformed in ("IIII", "IIV", "VX", "IC", "IM", "VV", "LL", "DD"):
            with self.subTest(numeral=malformed):
                self.assertIsNone(roman_to_int(malformed))

    def test_empty_and_none(self):
        self.assertIsNone(roman_to_int(""))
        self.assertIsNone(roman_to_int(None))
        self.assertIsNone(roman_to_int("   "))

    def test_non_roman_characters_rejected(self):
        self.assertIsNone(roman_to_int("IIIA"))
        self.assertIsNone(roman_to_int("3"))
        self.assertIsNone(roman_to_int("१२"))

    def test_whitespace_is_stripped(self):
        self.assertEqual(roman_to_int("  IX  "), 9)


class DevanagariToIntTests(unittest.TestCase):
    def test_single_digit(self):
        self.assertEqual(devanagari_to_int("३"), 3)
        self.assertEqual(devanagari_to_int("०"), 0)

    def test_multiple_digits(self):
        self.assertEqual(devanagari_to_int("१२"), 12)
        self.assertEqual(devanagari_to_int("१०८"), 108)

    def test_leading_zeros(self):
        self.assertEqual(devanagari_to_int("०१२"), 12)
        self.assertEqual(devanagari_to_int("००३"), 3)

    def test_larger_values(self):
        self.assertEqual(devanagari_to_int("१२३४"), 1234)

    def test_invalid_characters_rejected(self):
        self.assertIsNone(devanagari_to_int("अ"))  # Devanagari letter, not a digit
        self.assertIsNone(devanagari_to_int("३क"))  # mixed digit + letter
        self.assertIsNone(devanagari_to_int("3"))  # ASCII digit, not Devanagari

    def test_empty_and_none(self):
        self.assertIsNone(devanagari_to_int(""))
        self.assertIsNone(devanagari_to_int(None))
        self.assertIsNone(devanagari_to_int("   "))


class DetectionHelperTests(unittest.TestCase):
    def test_is_arabic_numeral(self):
        self.assertTrue(is_arabic_numeral("3"))
        self.assertTrue(is_arabic_numeral("103"))
        self.assertFalse(is_arabic_numeral("3A"))
        self.assertFalse(is_arabic_numeral("३"))
        self.assertFalse(is_arabic_numeral(""))
        self.assertFalse(is_arabic_numeral(None))

    def test_is_devanagari_char(self):
        self.assertTrue(is_devanagari_char("३"))
        self.assertTrue(is_devanagari_char("अ"))
        self.assertFalse(is_devanagari_char("3"))
        self.assertFalse(is_devanagari_char("I"))
        self.assertFalse(is_devanagari_char(""))


# ===========================================================================
# NumberingSystemDetector
# ===========================================================================

class NumberingSystemDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = NumberingSystemDetector()
        self.context = CanonicalizationContext()

    def test_detects_roman(self):
        heading = _make_heading(original_numbering="III")
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.ROMAN)

    def test_detects_arabic(self):
        heading = _make_heading(original_numbering="3")
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.ARABIC)

    def test_detects_devanagari(self):
        heading = _make_heading(original_numbering="३")
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.DEVANAGARI)

    def test_detects_devanagari_even_if_digits_invalid(self):
        # Detection is character-shape-only; validity is the
        # DevanagariNumeralCanonicalizer's job, not the detector's.
        heading = _make_heading(original_numbering="अ")
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.DEVANAGARI)

    def test_empty_numbering_yields_none_system(self):
        heading = _make_heading(original_numbering=None)
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.NONE)

    def test_blank_numbering_yields_none_system(self):
        heading = _make_heading(original_numbering="   ")
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.NONE)

    def test_mixed_numeral_systems_yield_unknown_with_diagnostic(self):
        heading = _make_heading(original_numbering="3iv")
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.UNKNOWN)
        self.assertEqual(len(updated.diagnostics), 1)
        self.assertIn("unsupported or mixed", updated.diagnostics[0])

    def test_unsupported_format_yields_unknown_with_diagnostic(self):
        heading = _make_heading(original_numbering="A")
        updated = self.detector.canonicalize(heading, self.context)
        self.assertEqual(updated.numbering_system, NumberingSystem.UNKNOWN)
        self.assertEqual(len(updated.diagnostics), 1)

    def test_supports_only_when_unknown(self):
        heading = _make_heading(original_numbering="3")
        self.assertTrue(self.detector.supports(heading, self.context))
        already_detected = heading.with_updates(numbering_system=NumberingSystem.ARABIC)
        self.assertFalse(self.detector.supports(already_detected, self.context))


# ===========================================================================
# Concrete numeral canonicalizers
# ===========================================================================

class RomanNumeralCanonicalizerTests(unittest.TestCase):
    def setUp(self):
        self.canonicalizer = RomanNumeralCanonicalizer()
        self.context = CanonicalizationContext()

    def test_supports_requires_roman_system_and_no_existing_number(self):
        heading = _make_heading(
            original_numbering="III", numbering_system=NumberingSystem.ROMAN
        )
        self.assertTrue(self.canonicalizer.supports(heading, self.context))

        wrong_system = _make_heading(
            original_numbering="3", numbering_system=NumberingSystem.ARABIC
        )
        self.assertFalse(self.canonicalizer.supports(wrong_system, self.context))

        already_done = heading.with_updates(canonical_number="3")
        self.assertFalse(self.canonicalizer.supports(already_done, self.context))

    def test_converts_valid_roman_numeral(self):
        heading = _make_heading(
            original_numbering="III", numbering_system=NumberingSystem.ROMAN
        )
        updated = self.canonicalizer.canonicalize(heading, self.context)
        self.assertEqual(updated.canonical_number, "3")

    def test_rejects_malformed_roman_numeral_with_diagnostic(self):
        heading = _make_heading(
            original_numbering="IIII", numbering_system=NumberingSystem.ROMAN
        )
        updated = self.canonicalizer.canonicalize(heading, self.context)
        self.assertIsNone(updated.canonical_number)
        self.assertEqual(len(updated.diagnostics), 1)
        self.assertIn("malformed roman numeral", updated.diagnostics[0])


class ArabicNumeralCanonicalizerTests(unittest.TestCase):
    def setUp(self):
        self.canonicalizer = ArabicNumeralCanonicalizer()
        self.context = CanonicalizationContext()

    def test_converts_arabic_numeral(self):
        for raw, expected in (("1", "1"), ("15", "15"), ("103", "103"), ("1000", "1000")):
            with self.subTest(raw=raw):
                heading = _make_heading(
                    original_numbering=raw, numbering_system=NumberingSystem.ARABIC
                )
                updated = self.canonicalizer.canonicalize(heading, self.context)
                self.assertEqual(updated.canonical_number, expected)

    def test_supports_requires_arabic_system(self):
        heading = _make_heading(
            original_numbering="III", numbering_system=NumberingSystem.ROMAN
        )
        self.assertFalse(self.canonicalizer.supports(heading, self.context))


class DevanagariNumeralCanonicalizerTests(unittest.TestCase):
    def setUp(self):
        self.canonicalizer = DevanagariNumeralCanonicalizer()
        self.context = CanonicalizationContext()

    def test_converts_devanagari_numeral(self):
        for raw, expected in (("३", "3"), ("१२", "12"), ("१०८", "108")):
            with self.subTest(raw=raw):
                heading = _make_heading(
                    original_numbering=raw, numbering_system=NumberingSystem.DEVANAGARI
                )
                updated = self.canonicalizer.canonicalize(heading, self.context)
                self.assertEqual(updated.canonical_number, expected)

    def test_rejects_invalid_devanagari_digit_with_diagnostic(self):
        heading = _make_heading(
            original_numbering="अ", numbering_system=NumberingSystem.DEVANAGARI
        )
        updated = self.canonicalizer.canonicalize(heading, self.context)
        self.assertIsNone(updated.canonical_number)
        self.assertEqual(len(updated.diagnostics), 1)
        self.assertIn("invalid devanagari numeral", updated.diagnostics[0])


# ===========================================================================
# End-to-end pipeline integration (isolated registry — does not touch
# the process-wide default_registry's shared state across test runs)
# ===========================================================================

class PipelineIntegrationTests(unittest.TestCase):
    def _isolated_registry(self) -> CanonicalizerRegistry:
        registry = CanonicalizerRegistry()
        registry.register(NumberingSystemDetector())
        registry.register(RomanNumeralCanonicalizer())
        registry.register(ArabicNumeralCanonicalizer())
        registry.register(DevanagariNumeralCanonicalizer())
        return registry

    def test_chapter_iii_resolves_to_three_roman(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_text="Chapter III", original_numbering="III")
        result = pipeline.run(heading)
        self.assertEqual(result.output_heading.canonical_number, "3")
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.ROMAN)

    def test_chapter_3_resolves_to_three_arabic(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_text="Chapter 3", original_numbering="3")
        result = pipeline.run(heading)
        self.assertEqual(result.output_heading.canonical_number, "3")
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.ARABIC)

    def test_devanagari_heading_resolves_to_three(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_text="अध्याय ३", original_numbering="३")
        result = pipeline.run(heading)
        self.assertEqual(result.output_heading.canonical_number, "3")
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.DEVANAGARI)

    def test_malformed_roman_never_crashes_pipeline(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_numbering="IIII")
        result = pipeline.run(heading)  # must not raise
        self.assertIsNone(result.output_heading.canonical_number)
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.ROMAN)
        self.assertTrue(
            any("malformed roman numeral" in d for d in result.output_heading.diagnostics)
        )

    def test_mixed_numeral_system_never_crashes_pipeline(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_numbering="3iv")
        result = pipeline.run(heading)  # must not raise
        self.assertIsNone(result.output_heading.canonical_number)
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.UNKNOWN)

    def test_empty_numbering_never_crashes_pipeline(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_numbering=None)
        result = pipeline.run(heading)  # must not raise
        self.assertIsNone(result.output_heading.canonical_number)
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.NONE)

    def test_unsupported_format_never_crashes_pipeline(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_numbering="A")
        result = pipeline.run(heading)  # must not raise
        self.assertIsNone(result.output_heading.canonical_number)
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.UNKNOWN)

    def test_determinism_across_repeated_runs(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_text="Chapter III", original_numbering="III")
        results = [pipeline.run(heading) for _ in range(5)]
        first = results[0].output_heading
        for other in results[1:]:
            self.assertEqual(other.output_heading.canonical_number, first.canonical_number)
            self.assertEqual(other.output_heading.numbering_system, first.numbering_system)
            self.assertEqual(other.output_heading.diagnostics, first.diagnostics)

    def test_attempts_recorded_and_none_are_crashes(self):
        pipeline = CanonicalizationPipeline(self._isolated_registry())
        heading = _make_heading(original_text="Chapter 3", original_numbering="3")
        result = pipeline.run(heading)
        outcomes = {a.canonicalizer_name: a.outcome for a in result.attempts}
        self.assertIn("numbering_system_detector", outcomes)
        self.assertIn("arabic_numeral_canonicalizer", outcomes)
        # The detector and arabic canonicalizer must have APPLIED;
        # roman/devanagari canonicalizers must not have matched.
        self.assertEqual(outcomes["numbering_system_detector"], CanonicalizationOutcome.APPLIED)
        self.assertEqual(outcomes["arabic_numeral_canonicalizer"], CanonicalizationOutcome.APPLIED)
        self.assertEqual(outcomes["roman_numeral_canonicalizer"], CanonicalizationOutcome.SKIPPED)
        self.assertEqual(outcomes["devanagari_numeral_canonicalizer"], CanonicalizationOutcome.SKIPPED)


class DefaultRegistryRegistrationTests(unittest.TestCase):
    """Confirms M4.3B's canonicalizers are actually registered into
    the package's process-wide default_registry (the integration
    point specified by requirement #5, Framework Integration)."""

    def test_all_four_canonicalizers_registered_by_default(self):
        names = set(default_registry.registered_names())
        self.assertIn("numbering_system_detector", names)
        self.assertIn("roman_numeral_canonicalizer", names)
        self.assertIn("arabic_numeral_canonicalizer", names)
        self.assertIn("devanagari_numeral_canonicalizer", names)

    def test_default_registry_end_to_end(self):
        pipeline = CanonicalizationPipeline(default_registry)
        heading = _make_heading(original_text="Chapter III", original_numbering="III")
        result = pipeline.run(heading)
        self.assertEqual(result.output_heading.canonical_number, "3")
        self.assertEqual(result.output_heading.numbering_system, NumberingSystem.ROMAN)


if __name__ == "__main__":
    unittest.main()
