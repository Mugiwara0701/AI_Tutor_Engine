"""
tests/test_m42e_validation_hardening.py — M4.2E: validation,
edge-case hardening, determinism, confidence-sanity, performance-smoke,
and frozen-public-API-surface tests for the whole heading recognition
subsystem (modules/heading_recognizers), exercised end-to-end through
the shared `default_registry` + `RecognitionPipeline`.

This is a quality-assurance suite, not a feature suite: no new
recognizer is exercised that M4.2B/M4.2D didn't already introduce.

Coverage:
  - Functional validation across every language/numeral-system
    combination the catalog supports (English, Hindi, Sanskrit,
    Arabic numerals, Devanagari numerals, Roman numerals,
    hierarchical numbering).
  - Edge cases: empty/whitespace-only text, malformed numbering,
    missing titles, duplicate numbering (same context recognized
    twice), OCR spacing/punctuation variations, mixed-language text,
    mixed numeral systems (both across a corpus and within one
    token), unexpected symbols, non-string `RecognitionContext.text`
    — all verified to fail gracefully (no crash, no exception
    escaping `RecognitionPipeline.run()`).
  - Determinism: identical input -> identical recognizer selection,
    confidence, metadata, and conflict resolution, across repeated
    runs and across independently-constructed pipelines.
  - Confidence sanity: obvious headings score higher than ambiguous
    ones; every produced confidence is within [0, 1].
  - Regression guard for the two M4.2E hardening fixes themselves
    (Devanagari-digit leakage into `hierarchical_heading`; unguarded
    `supports()` exceptions aborting a whole pipeline run).
  - A light performance smoke test (generous bound, not a benchmark).
  - A frozen-public-API pinning test: every M4.2E "frozen interface"
    name is still present and importable from its documented module.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.heading_recognizers import default_factory, default_registry
from modules.heading_recognizers.base import RecognitionContext
from modules.heading_recognizers.enums import HeadingClassification, RecognitionOutcome
from modules.heading_recognizers.pipeline import RecognitionPipeline


def _ctx(text, **kwargs) -> RecognitionContext:
    return RecognitionContext(text=text, page=1, line_index=0, **kwargs)


# ===========================================================================
# 1. Functional validation across languages / numeral systems
# ===========================================================================

class TestFunctionalValidation(unittest.TestCase):
    def setUp(self):
        self.pipeline = RecognitionPipeline(default_registry)

    def _winner(self, text):
        return self.pipeline.run(_ctx(text)).winner

    def test_english_headings(self):
        cases = {
            "Chapter 1": "chapter_number",
            "Unit 3": "chapter_number",
            "12": "numbered_heading",
            "IV": "roman_numeral_heading",
            "a)": "alphabetic_heading",
            "The Living World": "chapter_title",
        }
        for text, expected in cases.items():
            winner = self._winner(text)
            self.assertIsNotNone(winner, text)
            self.assertEqual(winner.recognizer_name, expected, text)

    def test_hindi_headings(self):
        for text in ("अध्याय १", "अध्याय 1", "पाठ ५", "पाठ 5", "गतिविधि", "उदाहरण", "सारांश", "प्रश्नावली"):
            winner = self._winner(text)
            self.assertIsNotNone(winner, text)
            self.assertEqual(winner.recognizer_name, "hindi_heading", text)

    def test_sanskrit_headings(self):
        for text in ("अध्यायः", "पाठः", "अभ्यासः", "उदाहरणम्", "प्रश्नाः"):
            winner = self._winner(text)
            self.assertIsNotNone(winner, text)
            self.assertEqual(winner.recognizer_name, "sanskrit_heading", text)

    def test_arabic_and_devanagari_numerals_resolve_identically(self):
        arabic = self._winner("अध्याय 7")
        devanagari = self._winner("अध्याय ७")
        self.assertEqual(arabic.number, "7")
        self.assertEqual(devanagari.number, "7")

    def test_roman_numerals(self):
        for text in ("I", "IV", "IX", "XIV", "XX"):
            winner = self._winner(text)
            self.assertIsNotNone(winner, text)
            self.assertEqual(winner.classification, HeadingClassification.ROMAN_NUMERAL)

    def test_hierarchical_numbering(self):
        for text in ("1.1", "2.3", "4.5.2", "7.3.4.1"):
            winner = self._winner(text)
            self.assertIsNotNone(winner, text)
            self.assertEqual(winner.classification, HeadingClassification.HIERARCHICAL)

    def test_chapter_section_subsection_levels(self):
        chapter = self._winner("Chapter 1")
        section = self._winner("1.1")
        self.assertEqual(chapter.level, 1)
        self.assertGreaterEqual(section.level, 2)


# ===========================================================================
# 2. Edge case validation
# ===========================================================================

class TestEdgeCaseValidation(unittest.TestCase):
    def setUp(self):
        self.pipeline = RecognitionPipeline(default_registry)

    def _runs_without_crashing(self, text):
        result = self.pipeline.run(_ctx(text))
        return result

    def test_empty_and_whitespace_only_headings(self):
        for text in ("", " ", "   ", "\t", "\n", "\t\n  "):
            result = self._runs_without_crashing(text)
            self.assertIsNone(result.winner, repr(text))

    def test_malformed_numbering(self):
        for text in ("1..2", "1.", ".1", "1-", "--1", "1..", "अध्याय.."):
            # Must not raise; a winner (or none) is both acceptable,
            # the only hard requirement is graceful handling.
            self._runs_without_crashing(text)

    def test_missing_titles_bare_numbering_only(self):
        for text in ("1", "IV", "a)", "अध्याय १"):
            result = self._runs_without_crashing(text)
            if result.winner is not None:
                # title may legitimately be None (e.g. bare numeral) —
                # just must not raise while being absent.
                _ = result.winner.title

    def test_duplicate_numbering_same_context_twice(self):
        # Recognizing the identical heading twice (e.g. a repeated
        # chapter marker on a reprinted page) must be independently
        # stable, not order- or state-dependent.
        first = self.pipeline.run(_ctx("Chapter 1")).winner
        second = self.pipeline.run(_ctx("Chapter 1")).winner
        self.assertEqual(first.number, second.number)
        self.assertEqual(first.confidence, second.confidence)

    def test_ocr_spacing_variations(self):
        for text in ("Chapter    1", "  Chapter 1  ", "अध्याय     १"):
            result = self._runs_without_crashing(text)
            self.assertIsNotNone(result.winner, text)

    def test_punctuation_variations(self):
        for text in ("Chapter 1.", "Chapter: 1", "अध्याय.. १", "पाठ::  ५", "सारांश।"):
            self._runs_without_crashing(text)

    def test_mixed_language_headings_do_not_crash(self):
        for text in ("Chapter अध्याय 1", "अध्याय Chapter 1", "अध्याय Summary"):
            result = self._runs_without_crashing(text)
            # No hard assertion on a winner either way — only that the
            # framework never raises on genuinely ambiguous mixed input.
            self.assertIsInstance(result.matches, tuple)

    def test_mixed_numeral_systems_within_one_token_rejected_not_crashed(self):
        for text in ("अध्याय 5१", "अध्याय ५5", "Chapter 1५"):
            result = self._runs_without_crashing(text)
            # A numeral mixing both digit systems in one token is not a
            # well-formed numeral in either system - no recognizer
            # should claim it, but nothing may crash either.
            self.assertIsNone(result.winner, text)

    def test_unexpected_symbols(self):
        for text in ("###", "!!!", "@@@", "()", "🎉🎉🎉", "अध्याय\u200b१", "\x00\x01"):
            self._runs_without_crashing(text)

    def test_non_string_text_fails_gracefully(self):
        # RecognitionContext.text is typed `str`, but the dataclass
        # itself does not enforce it at construction time; a caller
        # bug upstream (e.g. a None/int slipping through) must degrade
        # to "no winner", never an uncaught exception escaping run().
        for bad_text in (123, 1.5, ["a"], True, None):
            try:
                ctx = _ctx(bad_text)
            except Exception as exc:  # RecognitionContext construction itself
                self.fail(f"RecognitionContext construction raised for {bad_text!r}: {exc}")
            try:
                result = self.pipeline.run(ctx)
            except Exception as exc:
                self.fail(f"pipeline.run() raised for text={bad_text!r}: {exc}")
            self.assertIsNone(result.winner)

    def test_very_long_input_does_not_crash(self):
        self._runs_without_crashing("१" * 2000)
        self._runs_without_crashing("अध्याय" * 200)
        self._runs_without_crashing("A" * 5000)


# ===========================================================================
# 3. Deterministic behaviour
# ===========================================================================

class TestDeterministicBehaviour(unittest.TestCase):
    def test_identical_input_identical_output_repeated_runs(self):
        pipeline = RecognitionPipeline(default_registry)
        texts = ["Chapter 1", "1.1", "IV", "अध्याय १", "अध्यायः ३", "The Living World"]
        for text in texts:
            baseline = pipeline.run(_ctx(text))
            for _ in range(10):
                again = pipeline.run(_ctx(text))
                self.assertEqual(
                    [(m.recognizer_name, m.classification, m.confidence, m.level, m.number, m.title, m.metadata)
                     for m in baseline.matches],
                    [(m.recognizer_name, m.classification, m.confidence, m.level, m.number, m.title, m.metadata)
                     for m in again.matches],
                    text,
                )
                self.assertEqual(
                    [w.recognizer_name for w in baseline.winners],
                    [w.recognizer_name for w in again.winners],
                    text,
                )

    def test_independent_pipelines_agree(self):
        pipeline_a = RecognitionPipeline(default_registry)
        pipeline_b = RecognitionPipeline(default_registry)
        for text in ("Chapter 1", "अध्याय १", "सारांश"):
            winner_a = pipeline_a.run(_ctx(text)).winner
            winner_b = pipeline_b.run(_ctx(text)).winner
            self.assertEqual(winner_a.recognizer_name, winner_b.recognizer_name, text)
            self.assertEqual(winner_a.confidence, winner_b.confidence, text)

    def test_attempt_ordering_is_stable(self):
        pipeline = RecognitionPipeline(default_registry)
        first = [a.recognizer_name for a in pipeline.run(_ctx("Chapter 1")).attempts]
        second = [a.recognizer_name for a in pipeline.run(_ctx("Chapter 1")).attempts]
        self.assertEqual(first, second)


# ===========================================================================
# 4. Confidence sanity
# ===========================================================================

class TestConfidenceSanity(unittest.TestCase):
    def setUp(self):
        self.pipeline = RecognitionPipeline(default_registry)

    def test_all_confidences_within_bounds(self):
        texts = ["Chapter 1", "1.1", "IV", "I", "a)", "अध्याय १", "सारांश", "The Living World"]
        for text in texts:
            result = self.pipeline.run(_ctx(text))
            for match in result.matches:
                self.assertGreaterEqual(match.confidence, 0.0, text)
                self.assertLessEqual(match.confidence, 1.0, text)

    def test_obvious_heading_outscores_ambiguous_one(self):
        # "Chapter 1" is an unambiguous structural match; a bare "I"
        # is intrinsically ambiguous (Roman numeral vs. stray letter)
        # -- the framework's own generic_recognizers.py documents this
        # exact ordering rationale.
        obvious = self.pipeline.run(_ctx("Chapter 1")).winner
        ambiguous = self.pipeline.run(_ctx("I")).winner
        self.assertGreater(obvious.confidence, ambiguous.confidence)

    def test_numbered_keyword_outscores_bare_keyword(self):
        numbered = self.pipeline.run(_ctx("अध्याय १")).winner
        bare = self.pipeline.run(_ctx("सारांश")).winner
        self.assertGreaterEqual(numbered.confidence, bare.confidence)


# ===========================================================================
# 5. Regression guards for the M4.2E hardening fixes themselves
# ===========================================================================

class TestHardeningFixRegressions(unittest.TestCase):
    def setUp(self):
        self.pipeline = RecognitionPipeline(default_registry)

    def test_devanagari_digits_do_not_leak_into_generic_hierarchical(self):
        # Regression guard for the M4.2E fix: hierarchical_heading is
        # documented ASCII-only; a purely-Devanagari hierarchical-
        # shaped token must not match it.
        for text in ("१.१", "१.२.३", "५.५.५.५"):
            result = self.pipeline.run(_ctx(text))
            matched_names = {m.recognizer_name for m in result.matches}
            self.assertNotIn("hierarchical_heading", matched_names, text)

    def test_ascii_hierarchical_numbering_still_works(self):
        result = self.pipeline.run(_ctx("1.2.3"))
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.recognizer_name, "hierarchical_heading")
        self.assertEqual(result.winner.number, "1.2.3")

    def test_supports_exception_recorded_as_failed_not_propagated(self):
        # Regression guard for the M4.2E fix: a supports()-raising
        # context must produce a FAILED AttemptRecord for the affected
        # recognizer(s), not an exception out of run().
        result = self.pipeline.run(_ctx(123))
        self.assertIsNone(result.winner)
        failed = result.attempts_by_outcome(RecognitionOutcome.FAILED)
        self.assertGreater(len(failed), 0)
        for attempt in failed:
            self.assertIsNotNone(attempt.failure)


# ===========================================================================
# 6. Performance smoke test
# ===========================================================================

class TestPerformanceSmoke(unittest.TestCase):
    def test_repeated_pipeline_execution_is_fast(self):
        pipeline = RecognitionPipeline(default_registry)
        texts = ["Chapter 1", "1.2.3", "IV", "a)", "अध्याय १", "सारांश", "The Living World", "random prose"] * 250
        start = time.perf_counter()
        for text in texts:
            pipeline.run(_ctx(text))
        elapsed = time.perf_counter() - start
        # Generous bound (not a benchmark): catches an accidental O(n^2)
        # or per-call re-registration regression, not micro-variance.
        self.assertLess(elapsed, 5.0, f"{len(texts)} pipeline runs took {elapsed:.3f}s")

    def test_registry_is_not_rebuilt_per_pipeline_construction(self):
        # RecognitionPipeline() must be cheap to construct repeatedly
        # against the shared default_registry (no recognizer
        # re-instantiation) -- the production integration
        # (stage_b_classify.py) relies on building exactly one and
        # reusing it, but nothing should break if a caller builds more.
        start = time.perf_counter()
        for _ in range(1000):
            RecognitionPipeline(default_registry)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0, f"1000 constructions took {elapsed:.3f}s")


# ===========================================================================
# 7. Frozen public API surface
# ===========================================================================

class TestFrozenPublicAPI(unittest.TestCase):
    def test_package_all_contains_every_frozen_name(self):
        import modules.heading_recognizers as pkg
        frozen_names = {
            "HeadingRecognizer", "RecognitionContext", "RecognitionResult",
            "FailureResult", "ConfidenceInfo",
            "HeadingRecognitionConfig", "RecognizerSettings", "default_config",
            "RecognizerRegistry", "default_registry", "register", "unregister",
            "get", "enabled_recognizers", "all_recognizers",
            "RecognizerFactory", "default_factory",
            "RecognitionPipeline", "PipelineResult", "AttemptRecord",
            "HeadingClassification", "ConflictResolutionStrategy",
            "RecognizerState", "RecognitionOutcome",
            "HeadingRecognitionError", "RecognizerRegistrationError",
            "RecognizerConfigurationError", "RecognizerLookupError",
            "RecognizerExecutionError", "RecognitionPipelineError",
            "NumberedHeadingRecognizer", "HierarchicalHeadingRecognizer",
            "RomanNumeralHeadingRecognizer", "AlphabeticHeadingRecognizer",
            "ChapterNumberRecognizer", "ChapterTitleRecognizer",
            "HindiHeadingRecognizer", "SanskritHeadingRecognizer",
        }
        missing = frozen_names - set(pkg.__all__)
        self.assertEqual(missing, set(), f"Frozen names missing from __all__: {missing}")
        for name in frozen_names:
            self.assertTrue(hasattr(pkg, name), f"{name} not importable from modules.heading_recognizers")

    def test_recognition_result_required_fields_unchanged(self):
        from modules.heading_recognizers.base import RecognitionResult
        result = RecognitionResult(
            recognizer_name="probe", classification=HeadingClassification.UNCLASSIFIED, confidence=0.5,
        )
        for field_name in ("recognizer_name", "classification", "confidence", "level", "number", "title", "metadata", "diagnostics"):
            self.assertTrue(hasattr(result, field_name), field_name)

    def test_heading_classification_existing_members_unchanged(self):
        expected = {
            "numbered", "hierarchical", "roman_numeral", "alphabetic",
            "chapter_number", "chapter_title", "unclassified", "section_keyword",
        }
        actual = {member.value for member in HeadingClassification}
        self.assertEqual(actual, expected)

    def test_all_catalog_recognizers_registered_and_enabled(self):
        expected_names = {
            "numbered_heading", "hierarchical_heading", "roman_numeral_heading",
            "alphabetic_heading", "chapter_number", "chapter_title",
            "hindi_heading", "sanskrit_heading",
        }
        registered = set(default_registry.registered_names())
        self.assertEqual(expected_names, registered)
        for name in expected_names:
            self.assertTrue(default_registry.is_enabled(name), name)


if __name__ == "__main__":
    unittest.main()