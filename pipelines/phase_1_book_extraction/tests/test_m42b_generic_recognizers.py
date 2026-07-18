"""
tests/test_m42b_generic_recognizers.py — M4.2B unit tests for
modules/heading_recognizers/generic_recognizers.py (the first,
generic/language-independent recognizer family, built on the M4.2A
framework).

Coverage:
  - each of the six recognizers: successful recognition, malformed/
    rejected inputs, confidence scoring, diagnostics
  - registry integration: all six are registered (via default_factory
    / default_registry) under distinct names, enabled by default
  - pipeline execution: running the shared default_registry through a
    RecognitionPipeline against representative lines
  - conflict resolution across recognizers on ambiguous input (e.g.
    "I" is both a valid Roman numeral and a bare letter)
  - deterministic behaviour across repeated runs
  - edge cases / failure scenarios (empty text, whitespace-only text,
    oversized text)

Per the M4.2B spec, this suite does NOT exercise any language-specific
(Hindi/Sanskrit/Devanagari) pattern — none is implemented in this
milestone.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.heading_recognizers import default_factory, default_registry
from modules.heading_recognizers.base import RecognitionContext
from modules.heading_recognizers.config import default_config
from modules.heading_recognizers.enums import HeadingClassification
from modules.heading_recognizers.factory import RecognizerFactory
from modules.heading_recognizers.generic_recognizers import (
    AlphabeticHeadingRecognizer,
    ChapterNumberRecognizer,
    ChapterTitleRecognizer,
    HierarchicalHeadingRecognizer,
    NumberedHeadingRecognizer,
    RomanNumeralHeadingRecognizer,
)
from modules.heading_recognizers.pipeline import RecognitionPipeline
from modules.heading_recognizers.registry import RecognizerRegistry


def _ctx(text: str, **kwargs) -> RecognitionContext:
    return RecognitionContext(text=text, page=1, line_index=0, **kwargs)


def _fresh_registry() -> RecognizerRegistry:
    """An isolated registry containing only the M4.2B generic family,
    built through a fresh RecognizerFactory — mirrors how a caller
    other than the process-wide default would assemble one, and keeps
    these tests independent of any config a different test module
    might apply to `default_registry`."""
    factory = RecognizerFactory()
    for cls in (
        NumberedHeadingRecognizer,
        HierarchicalHeadingRecognizer,
        RomanNumeralHeadingRecognizer,
        AlphabeticHeadingRecognizer,
        ChapterNumberRecognizer,
        ChapterTitleRecognizer,
    ):
        factory.register_class(cls.name, cls)
    return factory.build_registry()


# ===========================================================================
# 1. NumberedHeadingRecognizer
# ===========================================================================

class TestNumberedHeadingRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = NumberedHeadingRecognizer()

    def test_matches_bare_numbers(self):
        for text in ("1", "2", "10", "25", "999"):
            with self.subTest(text=text):
                result = self.r.recognize(_ctx(text))
                self.assertIsNotNone(result)
                self.assertEqual(result.classification, HeadingClassification.NUMBERED)
                self.assertEqual(result.number, text)

    def test_matches_with_trailing_marker(self):
        result = self.r.recognize(_ctx("3)"))
        self.assertIsNotNone(result)
        self.assertEqual(result.number, "3")

    def test_rejects_leading_zero(self):
        self.assertIsNone(self.r.recognize(_ctx("01")))

    def test_rejects_hierarchical_numbering(self):
        self.assertIsNone(self.r.recognize(_ctx("1.1")))

    def test_rejects_non_numeric(self):
        for text in ("", "abc", "1a", "one", "I"):
            with self.subTest(text=text):
                self.assertIsNone(self.r.recognize(_ctx(text)))

    def test_rejects_too_many_digits(self):
        self.assertIsNone(self.r.recognize(_ctx("1000")))

    def test_confidence_within_bounds(self):
        result = self.r.recognize(_ctx("5"))
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_zero_gets_low_confidence(self):
        result = self.r.recognize(_ctx("0"))
        self.assertIsNotNone(result)
        self.assertLess(result.confidence, 0.5)

    def test_deterministic(self):
        first = self.r.recognize(_ctx("12"))
        second = self.r.recognize(_ctx("12"))
        self.assertEqual(first, second)

    def test_recognizer_name_and_classification_declared(self):
        self.assertEqual(self.r.name, "numbered_heading")
        self.assertEqual(self.r.classification, HeadingClassification.NUMBERED)


# ===========================================================================
# 2. HierarchicalHeadingRecognizer
# ===========================================================================

class TestHierarchicalHeadingRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = HierarchicalHeadingRecognizer()

    def test_matches_two_segment(self):
        result = self.r.recognize(_ctx("1.1"))
        self.assertIsNotNone(result)
        self.assertEqual(result.classification, HeadingClassification.HIERARCHICAL)
        self.assertEqual(result.level, 2)

    def test_matches_arbitrary_depth(self):
        for text, expected_level in (("2.3", 2), ("4.5.2", 3), ("7.3.4.1", 4)):
            with self.subTest(text=text):
                result = self.r.recognize(_ctx(text))
                self.assertIsNotNone(result)
                self.assertEqual(result.level, expected_level)

    def test_rejects_single_segment(self):
        self.assertIsNone(self.r.recognize(_ctx("1")))

    def test_rejects_empty_segments(self):
        for text in ("1..2", "1.", ".1", "1..2."):
            with self.subTest(text=text):
                self.assertIsNone(self.r.recognize(_ctx(text)))

    def test_trailing_punctuation_is_stripped_before_parsing(self):
        # Trailing "." is normalized away first (mirrors
        # NumberedHeadingRecognizer accepting "1."), so "1.2." is a
        # valid two-segment match, not a malformed one.
        result = self.r.recognize(_ctx("1.2."))
        self.assertIsNotNone(result)
        self.assertEqual(result.number, "1.2")

    def test_rejects_non_numeric_segments(self):
        for text in ("1.a", "IV.2", "a.b"):
            with self.subTest(text=text):
                self.assertIsNone(self.r.recognize(_ctx(text)))

    def test_rejects_empty_text(self):
        self.assertIsNone(self.r.recognize(_ctx("")))

    def test_deterministic(self):
        first = self.r.recognize(_ctx("4.5.2"))
        second = self.r.recognize(_ctx("4.5.2"))
        self.assertEqual(first, second)


# ===========================================================================
# 3. RomanNumeralHeadingRecognizer
# ===========================================================================

class TestRomanNumeralHeadingRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = RomanNumeralHeadingRecognizer()

    def test_matches_valid_numerals(self):
        for text in ("I", "II", "III", "IV", "VI", "IX", "XIV", "XX"):
            with self.subTest(text=text):
                result = self.r.recognize(_ctx(text))
                self.assertIsNotNone(result)
                self.assertEqual(result.classification, HeadingClassification.ROMAN_NUMERAL)

    def test_reuses_utils_for_integer_value(self):
        result = self.r.recognize(_ctx("XIV"))
        self.assertEqual(result.metadata["integer_value"], 14)

    def test_rejects_invalid_numerals(self):
        for text in ("IIII", "VX", "ABC", "IL"):
            with self.subTest(text=text):
                self.assertIsNone(self.r.recognize(_ctx(text)))

    def test_case_insensitive_match(self):
        result = self.r.recognize(_ctx("xiv"))
        self.assertIsNotNone(result)
        self.assertEqual(result.number, "XIV")

    def test_single_letter_lower_confidence_than_multi(self):
        single = self.r.recognize(_ctx("I"))
        multi = self.r.recognize(_ctx("XIV"))
        self.assertLess(single.confidence, multi.confidence)

    def test_trailing_marker_matches(self):
        result = self.r.recognize(_ctx("IV."))
        self.assertIsNotNone(result)
        self.assertEqual(result.number, "IV")

    def test_rejects_empty(self):
        self.assertIsNone(self.r.recognize(_ctx("")))


# ===========================================================================
# 4. AlphabeticHeadingRecognizer
# ===========================================================================

class TestAlphabeticHeadingRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = AlphabeticHeadingRecognizer()

    def test_matches_bare_letters(self):
        for text in ("A", "B", "C", "D"):
            with self.subTest(text=text):
                result = self.r.recognize(_ctx(text))
                self.assertIsNotNone(result)
                self.assertEqual(result.classification, HeadingClassification.ALPHABETIC)
                self.assertEqual(result.number, text)

    def test_matches_marker_forms(self):
        for text, expected_letter in (("a)", "A"), ("(b)", "B"), ("C.", "C")):
            with self.subTest(text=text):
                result = self.r.recognize(_ctx(text))
                self.assertIsNotNone(result)
                self.assertEqual(result.number, expected_letter)

    def test_marker_form_has_higher_confidence_than_bare(self):
        bare = self.r.recognize(_ctx("A"))
        marker = self.r.recognize(_ctx("a)"))
        self.assertLess(bare.confidence, marker.confidence)

    def test_rejects_ordinary_text(self):
        for text in ("As", "I am", "AB", "hello", ""):
            with self.subTest(text=text):
                self.assertIsNone(self.r.recognize(_ctx(text)))

    def test_rejects_numeric_marker(self):
        self.assertIsNone(self.r.recognize(_ctx("1)")))


# ===========================================================================
# 5. ChapterNumberRecognizer
# ===========================================================================

class TestChapterNumberRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = ChapterNumberRecognizer()

    def test_matches_arabic_forms(self):
        for text in ("Chapter 1", "Unit 3", "Lesson 5"):
            with self.subTest(text=text):
                result = self.r.recognize(_ctx(text))
                self.assertIsNotNone(result)
                self.assertEqual(result.classification, HeadingClassification.CHAPTER_NUMBER)

    def test_matches_roman_form(self):
        result = self.r.recognize(_ctx("Chapter IV"))
        self.assertIsNotNone(result)
        self.assertEqual(result.metadata["integer_value"], 4)

    def test_case_insensitive_keyword(self):
        result = self.r.recognize(_ctx("chapter 2"))
        self.assertIsNotNone(result)

    def test_rejects_keyword_without_numeral(self):
        self.assertIsNone(self.r.recognize(_ctx("Chapter")))

    def test_rejects_unknown_keyword(self):
        self.assertIsNone(self.r.recognize(_ctx("Module 1")))

    def test_configurable_keywords_via_settings(self):
        from modules.heading_recognizers.config import RecognizerSettings

        settings = RecognizerSettings(name="chapter_number", extra={"keywords": ["module"]})
        r = ChapterNumberRecognizer(settings=settings)
        self.assertIsNotNone(r.recognize(_ctx("Module 1")))
        self.assertIsNone(r.recognize(_ctx("Chapter 1")))

    def test_title_reflects_keyword_and_numeral(self):
        result = self.r.recognize(_ctx("Chapter 7"))
        self.assertEqual(result.title, "Chapter 7")


# ===========================================================================
# 6. ChapterTitleRecognizer
# ===========================================================================

class TestChapterTitleRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = ChapterTitleRecognizer()

    def test_matches_structural_titles(self):
        for text in ("Motion", "Electricity", "The Living World", "Our Environment"):
            with self.subTest(text=text):
                result = self.r.recognize(_ctx(text))
                self.assertIsNotNone(result)
                self.assertEqual(result.classification, HeadingClassification.CHAPTER_TITLE)
                self.assertEqual(result.title, text)

    def test_rejects_sentence_punctuation(self):
        self.assertIsNone(self.r.recognize(_ctx("This is a sentence.")))

    def test_rejects_leading_digit(self):
        self.assertIsNone(self.r.recognize(_ctx("1 Introduction")))

    def test_rejects_too_many_words(self):
        self.assertIsNone(self.r.recognize(_ctx("This Is Way Too Many Title Case Words Here")))

    def test_rejects_lowercase_running_text(self):
        self.assertIsNone(self.r.recognize(_ctx("photosynthesis in green plants")))

    def test_preceding_chapter_heading_boosts_confidence(self):
        without = self.r.recognize(_ctx("Motion"))
        with_hint = self.r.recognize(_ctx("Motion", preceding_heading_level=1))
        self.assertGreaterEqual(with_hint.confidence, without.confidence)


# ===========================================================================
# 7. Registry / factory integration
# ===========================================================================

class TestRegistryIntegration(unittest.TestCase):
    def test_all_six_registered_on_default_registry(self):
        expected = {
            "numbered_heading", "hierarchical_heading", "roman_numeral_heading",
            "alphabetic_heading", "chapter_number", "chapter_title",
        }
        self.assertTrue(expected.issubset(set(default_registry.registered_names())))

    def test_all_six_enabled_by_default(self):
        for name in (
            "numbered_heading", "hierarchical_heading", "roman_numeral_heading",
            "alphabetic_heading", "chapter_number", "chapter_title",
        ):
            with self.subTest(name=name):
                self.assertTrue(default_registry.is_enabled(name))

    def test_default_factory_knows_all_six(self):
        names = set(default_factory.registered_names())
        self.assertIn("numbered_heading", names)
        self.assertIn("chapter_title", names)

    def test_fresh_registry_round_trip(self):
        registry = _fresh_registry()
        self.assertEqual(len(registry), 6)
        for recognizer in registry.all_recognizers():
            self.assertIn(recognizer.name, registry.registered_names())


# ===========================================================================
# 8. Pipeline execution against the generic family
# ===========================================================================

class TestPipelineExecution(unittest.TestCase):
    def setUp(self):
        self.registry = _fresh_registry()
        self.pipeline = RecognitionPipeline(self.registry)

    def test_representative_lines_each_win(self):
        cases = {
            "1": "numbered_heading",
            "1.1": "hierarchical_heading",
            "IV": "roman_numeral_heading",
            "a)": "alphabetic_heading",
            "Chapter 1": "chapter_number",
            "Motion": "chapter_title",
        }
        for text, expected_winner in cases.items():
            with self.subTest(text=text):
                result = self.pipeline.run(_ctx(text))
                self.assertIsNotNone(result.winner, f"expected a winner for {text!r}")
                self.assertEqual(result.winner.recognizer_name, expected_winner)

    def test_no_recognizer_matches_ordinary_prose(self):
        result = self.pipeline.run(_ctx("This is an ordinary paragraph of body text."))
        self.assertIsNone(result.winner)

    def test_chapter_number_outranks_bare_roman_on_conflicting_priority(self):
        # "Chapter IV" only matches ChapterNumberRecognizer (the keyword
        # is part of the token RomanNumeralHeadingRecognizer would need
        # to match alone), so this exercises normal single-match
        # resolution rather than an actual multi-recognizer conflict.
        result = self.pipeline.run(_ctx("Chapter IV"))
        self.assertEqual(result.winner.recognizer_name, "chapter_number")

    def test_ambiguous_single_letter_i_resolved_deterministically(self):
        # "I" is structurally valid for both RomanNumeralHeadingRecognizer
        # and AlphabeticHeadingRecognizer — a genuine conflict the
        # pipeline's configured strategy (default: HIGHEST_CONFIDENCE)
        # must resolve the same way every time.
        first = self.pipeline.run(_ctx("I"))
        second = self.pipeline.run(_ctx("I"))
        self.assertEqual(len(first.matches), 2)
        self.assertEqual(first.winner.recognizer_name, second.winner.recognizer_name)
        # Roman numeral is registered at a higher-priority default and
        # is not lower-confidence than the alphabetic reading here.
        self.assertEqual(first.winner.recognizer_name, "roman_numeral_heading")

    def test_deterministic_across_repeated_runs(self):
        texts = ["1", "1.1", "IV", "a)", "Chapter 1", "Motion", "not a heading at all"]
        first_run = [self.pipeline.run(_ctx(t)).winner for t in texts]
        second_run = [self.pipeline.run(_ctx(t)).winner for t in texts]
        first_names = [w.recognizer_name if w else None for w in first_run]
        second_names = [w.recognizer_name if w else None for w in second_run]
        self.assertEqual(first_names, second_names)

    def test_all_existing_m4_2a_conflict_strategies_still_work_with_real_recognizers(self):
        from modules.heading_recognizers.enums import ConflictResolutionStrategy

        for strategy in ConflictResolutionStrategy:
            cfg = default_config(conflict_resolution=strategy)
            pipeline = RecognitionPipeline(self.registry, config=cfg)
            result = pipeline.run(_ctx("I"))  # ambiguous: roman + alphabetic
            self.assertGreaterEqual(len(result.winners), 1)


# ===========================================================================
# 9. Edge cases / failure scenarios
# ===========================================================================

class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.registry = _fresh_registry()
        self.pipeline = RecognitionPipeline(self.registry)

    def test_empty_text_matches_nothing(self):
        result = self.pipeline.run(_ctx(""))
        self.assertIsNone(result.winner)

    def test_whitespace_only_text_matches_nothing(self):
        result = self.pipeline.run(_ctx("   \t  "))
        self.assertIsNone(result.winner)

    def test_very_long_text_matches_nothing_and_is_handled_safely(self):
        result = self.pipeline.run(_ctx("word " * 200))
        self.assertIsNone(result.winner)
        # None of the recognizers should have raised.
        from modules.heading_recognizers.enums import RecognitionOutcome
        self.assertEqual(len(result.attempts_by_outcome(RecognitionOutcome.FAILED)), 0)

    def test_no_recognizer_raises_on_any_sample(self):
        from modules.heading_recognizers.enums import RecognitionOutcome

        samples = ["", "   ", "1", "1.1", "I", "A", "Chapter 1", "Motion",
                   "!!!", "###", "1.2.3.4.5.6.7.8", "a" * 500, "()", "-.-"]
        for text in samples:
            with self.subTest(text=text):
                result = self.pipeline.run(_ctx(text))
                self.assertEqual(len(result.attempts_by_outcome(RecognitionOutcome.FAILED)), 0)


if __name__ == "__main__":
    unittest.main()
