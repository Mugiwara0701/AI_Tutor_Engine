"""
tests/test_m42d_hindi_sanskrit_recognizers.py — M4.2D unit tests for
modules/heading_recognizers/hindi_sanskrit_recognizers.py (the
Hindi/Sanskrit language-specific recognizer family, built on the
M4.2A framework and reusing M4.2A/B's utils/config/pipeline).

Coverage:
  - HindiHeadingRecognizer: each keyword, with Arabic numerals,
    Devanagari numerals, no numeral, whitespace variations,
    duplicated/missing punctuation
  - SanskritHeadingRecognizer: each keyword, numbered and bare
  - Devanagari numeral utils: is_devanagari_numeral / devanagari_to_arabic /
    normalize_numeral round-trips and rejections
  - OCR-robustness-style normalization: extra spaces, duplicated
    punctuation, missing punctuation, mixed digit systems across the
    corpus (not within one token)
  - registry/factory integration: both recognizers registered on
    default_registry, enabled by default, resolvable via the pipeline
  - regression: M4.2A/B/C recognizers and tests are unaffected —
    English recognizers still behave exactly as before, and Devanagari
    text does not spuriously trigger any generic recognizer
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
from modules.heading_recognizers.hindi_sanskrit_recognizers import (
    HindiHeadingRecognizer,
    SanskritHeadingRecognizer,
)
from modules.heading_recognizers.pipeline import RecognitionPipeline
from modules.heading_recognizers.registry import RecognizerRegistry
from modules.heading_recognizers.utils import (
    devanagari_to_arabic,
    is_devanagari_numeral,
    normalize_numeral,
)


def _ctx(text: str, **kwargs) -> RecognitionContext:
    return RecognitionContext(text=text, page=1, line_index=0, **kwargs)


def _fresh_registry() -> RecognizerRegistry:
    """Isolated registry with the full generic (M4.2B) + Hindi/Sanskrit
    (M4.2D) family, built through a fresh factory — independent of any
    config a different test module applies to `default_registry`."""
    factory = RecognizerFactory()
    for cls in (
        NumberedHeadingRecognizer,
        HierarchicalHeadingRecognizer,
        RomanNumeralHeadingRecognizer,
        AlphabeticHeadingRecognizer,
        ChapterNumberRecognizer,
        ChapterTitleRecognizer,
        HindiHeadingRecognizer,
        SanskritHeadingRecognizer,
    ):
        factory.register_class(cls.name, cls)
    return factory.build_registry()


# ===========================================================================
# 1. Devanagari numeral utils
# ===========================================================================

class TestDevanagariNumeralUtils(unittest.TestCase):
    def test_is_devanagari_numeral_true_cases(self):
        for token in ("०", "१", "५", "१२", "१२३४"):
            self.assertTrue(is_devanagari_numeral(token), token)

    def test_is_devanagari_numeral_false_cases(self):
        for token in ("", " ", "5", "1२", "अध्याय", "१."):
            self.assertFalse(is_devanagari_numeral(token), token)

    def test_devanagari_to_arabic_round_trip(self):
        self.assertEqual(devanagari_to_arabic("५"), "5")
        self.assertEqual(devanagari_to_arabic("१०"), "10")
        self.assertEqual(devanagari_to_arabic("०"), "0")

    def test_devanagari_to_arabic_rejects_non_numeral(self):
        self.assertIsNone(devanagari_to_arabic("5"))
        self.assertIsNone(devanagari_to_arabic("अध्याय"))
        self.assertIsNone(devanagari_to_arabic(""))

    def test_normalize_numeral_accepts_either_system(self):
        self.assertEqual(normalize_numeral("5"), "5")
        self.assertEqual(normalize_numeral("५"), "5")
        self.assertEqual(normalize_numeral("१२"), "12")

    def test_normalize_numeral_rejects_non_numeric(self):
        self.assertIsNone(normalize_numeral("अध्याय"))
        self.assertIsNone(normalize_numeral(""))


# ===========================================================================
# 2. HindiHeadingRecognizer
# ===========================================================================

class TestHindiHeadingRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = HindiHeadingRecognizer()

    def test_recognizer_name_and_classification_declared(self):
        self.assertEqual(self.r.name, "hindi_heading")
        self.assertIsNotNone(self.r.classification)

    def test_chapter_keyword_with_arabic_numeral(self):
        result = self.r.recognize(_ctx("अध्याय 1"))
        self.assertIsNotNone(result)
        self.assertEqual(result.classification, HeadingClassification.CHAPTER_NUMBER)
        self.assertEqual(result.level, 1)
        self.assertEqual(result.number, "1")

    def test_chapter_keyword_with_devanagari_numeral(self):
        result = self.r.recognize(_ctx("अध्याय १"))
        self.assertIsNotNone(result)
        self.assertEqual(result.level, 1)
        self.assertEqual(result.number, "1")

    def test_lesson_keyword_both_numeral_systems_agree(self):
        arabic = self.r.recognize(_ctx("पाठ 5"))
        devanagari = self.r.recognize(_ctx("पाठ ५"))
        self.assertEqual(arabic.number, devanagari.number)
        self.assertEqual(arabic.level, devanagari.level)

    def test_multi_digit_devanagari_numeral(self):
        result = self.r.recognize(_ctx("अध्याय १२"))
        self.assertEqual(result.number, "12")

    def test_bare_keyword_no_numeral_still_matches(self):
        for text in ("गतिविधि", "उदाहरण", "सारांश", "निष्कर्ष", "टिप्पणी", "परिचय"):
            result = self.r.recognize(_ctx(text))
            self.assertIsNotNone(result, text)
            self.assertEqual(result.classification, HeadingClassification.SECTION_KEYWORD, text)
            self.assertIsNone(result.number, text)
            self.assertEqual(result.level, 2, text)

    def test_prashnavali_not_shadowed_by_prashna_prefix(self):
        # प्रश्न is a prefix of प्रश्नावली — both must resolve to their
        # own correct keyword, not one shadowing the other.
        only_prashna = self.r.recognize(_ctx("प्रश्न"))
        prashnavali = self.r.recognize(_ctx("प्रश्नावली"))
        self.assertEqual(only_prashna.title, "प्रश्न")
        self.assertEqual(prashnavali.title, "प्रश्नावली")

    def test_prashna_with_numeral(self):
        result = self.r.recognize(_ctx("प्रश्न १०"))
        self.assertEqual(result.number, "10")
        self.assertEqual(result.title, "प्रश्न १०")

    def test_extra_whitespace_between_keyword_and_numeral(self):
        result = self.r.recognize(_ctx("अध्याय    १"))
        self.assertIsNotNone(result)
        self.assertEqual(result.number, "1")

    def test_duplicated_punctuation_normalized(self):
        result = self.r.recognize(_ctx("अध्याय.. १"))
        self.assertIsNotNone(result)
        self.assertEqual(result.number, "1")

    def test_missing_punctuation_still_matches(self):
        result = self.r.recognize(_ctx("पाठ ५"))
        self.assertIsNotNone(result)

    def test_trailing_danda_stripped(self):
        result = self.r.recognize(_ctx("सारांश।"))
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "सारांश")

    def test_rejects_unrelated_text(self):
        self.assertIsNone(self.r.recognize(_ctx("यह एक साधारण वाक्य है जो शीर्षक नहीं है")))

    def test_rejects_empty_text(self):
        self.assertIsNone(self.r.recognize(_ctx("")))

    def test_confidence_within_bounds(self):
        for text in ("अध्याय १", "सारांश"):
            result = self.r.recognize(_ctx(text))
            self.assertGreaterEqual(result.confidence, 0.0)
            self.assertLessEqual(result.confidence, 1.0)

    def test_deterministic(self):
        results = {self.r.recognize(_ctx("अध्याय १")).number for _ in range(5)}
        self.assertEqual(results, {"1"})

    def test_supports_prefilters_non_keyword_text(self):
        self.assertFalse(self.r.supports(_ctx("यह एक वाक्य है")))
        self.assertTrue(self.r.supports(_ctx("अध्याय १")))


# ===========================================================================
# 3. SanskritHeadingRecognizer
# ===========================================================================

class TestSanskritHeadingRecognizer(unittest.TestCase):
    def setUp(self):
        self.r = SanskritHeadingRecognizer()

    def test_recognizer_name_and_classification_declared(self):
        self.assertEqual(self.r.name, "sanskrit_heading")
        self.assertIsNotNone(self.r.classification)

    def test_chapter_keyword_visarga_form(self):
        result = self.r.recognize(_ctx("अध्यायः"))
        self.assertIsNotNone(result)
        self.assertEqual(result.level, 1)
        self.assertEqual(result.classification, HeadingClassification.SECTION_KEYWORD)

    def test_chapter_keyword_with_numeral(self):
        result = self.r.recognize(_ctx("अध्यायः ३"))
        self.assertEqual(result.number, "3")
        self.assertEqual(result.level, 1)
        self.assertEqual(result.classification, HeadingClassification.CHAPTER_NUMBER)

    def test_lesson_keyword(self):
        result = self.r.recognize(_ctx("पाठः 2"))
        self.assertEqual(result.number, "2")
        self.assertEqual(result.level, 1)

    def test_section_level_keywords(self):
        for text in ("अभ्यासः", "उदाहरणम्", "प्रश्नाः", "गतिविधिः", "सारांशः"):
            result = self.r.recognize(_ctx(text))
            self.assertIsNotNone(result, text)
            self.assertEqual(result.level, 2, text)

    def test_visarga_not_stripped_as_punctuation(self):
        # अध्यायः ends in the Devanagari letter visarga (ः), not ASCII
        # ':' — normalization must never strip it as trailing
        # punctuation, or the keyword itself would be mangled.
        result = self.r.recognize(_ctx("अध्यायः"))
        self.assertEqual(result.title, "अध्यायः")

    def test_rejects_unrelated_text(self):
        self.assertIsNone(self.r.recognize(_ctx("इदं वाक्यं शीर्षकं नास्ति")))

    def test_deterministic(self):
        results = {self.r.recognize(_ctx("पाठः २")).number for _ in range(5)}
        self.assertEqual(results, {"2"})


# ===========================================================================
# 4. Registry / factory integration
# ===========================================================================

class TestRegistryIntegration(unittest.TestCase):
    def test_both_registered_on_default_registry(self):
        self.assertIn("hindi_heading", default_registry)
        self.assertIn("sanskrit_heading", default_registry)

    def test_both_enabled_by_default(self):
        self.assertTrue(default_registry.is_enabled("hindi_heading"))
        self.assertTrue(default_registry.is_enabled("sanskrit_heading"))

    def test_default_factory_knows_both(self):
        names = default_factory.registered_names()
        self.assertIn("hindi_heading", names)
        self.assertIn("sanskrit_heading", names)

    def test_fresh_registry_round_trip(self):
        registry = _fresh_registry()
        self.assertIn("hindi_heading", registry)
        self.assertIn("sanskrit_heading", registry)


# ===========================================================================
# 5. Pipeline execution
# ===========================================================================

class TestPipelineExecution(unittest.TestCase):
    def setUp(self):
        self.pipeline = RecognitionPipeline(_fresh_registry())

    def test_hindi_and_sanskrit_lines_each_win(self):
        cases = {
            "अध्याय १": "hindi_heading",
            "पाठ 5": "hindi_heading",
            "सारांश": "hindi_heading",
            "अध्यायः": "sanskrit_heading",
            "उदाहरणम्": "sanskrit_heading",
        }
        for text, expected_recognizer in cases.items():
            result = self.pipeline.run(_ctx(text))
            self.assertIsNotNone(result.winner, text)
            self.assertEqual(result.winner.recognizer_name, expected_recognizer, text)

    def test_deterministic_across_repeated_runs(self):
        first = self.pipeline.run(_ctx("अध्याय १")).winner
        for _ in range(5):
            again = self.pipeline.run(_ctx("अध्याय १")).winner
            self.assertEqual(first.recognizer_name, again.recognizer_name)
            self.assertEqual(first.number, again.number)

    def test_devanagari_text_does_not_trigger_generic_recognizers(self):
        result = self.pipeline.run(_ctx("अध्याय १"))
        matched_names = {m.recognizer_name for m in result.matches}
        self.assertEqual(matched_names, {"hindi_heading"})


# ===========================================================================
# 6. Regression: M4.2A/B behavior unchanged
# ===========================================================================

class TestRegressionExistingRecognizersUnaffected(unittest.TestCase):
    def setUp(self):
        self.pipeline = RecognitionPipeline(_fresh_registry())

    def test_english_chapter_number_still_works(self):
        result = self.pipeline.run(_ctx("Chapter 1"))
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.recognizer_name, "chapter_number")

    def test_bare_arabic_number_still_works(self):
        result = self.pipeline.run(_ctx("12"))
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.recognizer_name, "numbered_heading")

    def test_roman_numeral_still_works(self):
        result = self.pipeline.run(_ctx("IV"))
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.recognizer_name, "roman_numeral_heading")

    def test_hierarchical_number_still_works(self):
        result = self.pipeline.run(_ctx("1.2.3"))
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.recognizer_name, "hierarchical_heading")

    def test_chapter_title_still_works(self):
        result = self.pipeline.run(_ctx("The Living World"))
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.recognizer_name, "chapter_title")

    def test_generic_recognizers_do_not_match_devanagari_text(self):
        for text in ("अध्याय १", "सारांश", "अध्यायः"):
            for recognizer_cls in (
                NumberedHeadingRecognizer(),
                HierarchicalHeadingRecognizer(),
                RomanNumeralHeadingRecognizer(),
                AlphabeticHeadingRecognizer(),
                ChapterNumberRecognizer(),
                ChapterTitleRecognizer(),
            ):
                self.assertIsNone(recognizer_cls.recognize(_ctx(text)), (recognizer_cls.name, text))


if __name__ == "__main__":
    unittest.main()