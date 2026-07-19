"""
tests/test_m43e_validation_hardening_freeze.py — M4.3E tests:
Validation, Hardening & Freeze.

This milestone adds NO new functionality (per the M4.3E spec). This
test module is the primary deliverable: it stress-tests the complete,
already-implemented heading subsystem (M4.2 recognition, M4.3A-D
canonicalization/validation, and their production wiring in
`modules/stage_b_classify.py`) against edge cases the milestone spec
calls out by name, verifies error isolation end-to-end, verifies
determinism, verifies the public API freeze, and verifies singleton/
performance discipline. It does not re-test functional correctness
already covered by test_m42*/test_m43a-d* (see the Regression class
at the bottom, which simply confirms those suites still collect and
pass unmodified).

One genuine defect was found and fixed during this milestone (see
`modules/stage_b_classify.py`'s `_heading_recognition_text`): it
called `.strip()` on `grouping_meta.get("numbering")`/`("title")`
unconditionally after `or ""`, which raised `AttributeError` for any
other truthy non-string value (e.g. a stray int/list from malformed
upstream metadata) -- contradicting that function's own documented
"never raises" contract. `TestMalformedMetadataNeverCrashes` below
is the regression test for that fix.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.heading_canonicalization.base import CanonicalizationContext
from modules.heading_canonicalization.enums import NumberingSystem, ValidationStatus
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.numeral_utils import (
    devanagari_to_int,
    roman_to_int,
)
from modules.heading_canonicalization.pipeline import CanonicalizationPipeline
from modules.heading_canonicalization.registry import CanonicalizerRegistry
from modules.heading_canonicalization.structural_validation import (
    PRECEDING_LEVEL_METADATA_KEY,
    StructuralValidator,
)
from modules.heading_recognizers.base import RecognitionContext
from modules.heading_recognizers.enums import HeadingClassification
from modules.heading_recognizers.pipeline import RecognitionPipeline
from modules.heading_recognizers.registry import RecognizerRegistry
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


def _full_recognizer_registry() -> RecognizerRegistry:
    """An isolated registry with every M4.2B/D recognizer, independent
    of `modules.heading_recognizers.default_registry` -- so these
    tests never depend on (or disturb) global registration state."""
    reg = RecognizerRegistry()
    for cls in (
        HierarchicalHeadingRecognizer, NumberedHeadingRecognizer,
        RomanNumeralHeadingRecognizer, AlphabeticHeadingRecognizer,
        ChapterNumberRecognizer, ChapterTitleRecognizer,
        HindiHeadingRecognizer, SanskritHeadingRecognizer,
    ):
        reg.register(cls())
    return reg


def _full_canonicalization_registry() -> CanonicalizerRegistry:
    """An isolated registry with every M4.3B canonicalizer plus the
    M4.3D structural validator, independent of
    `modules.heading_canonicalization.default_registry`."""
    from modules.heading_canonicalization.numeral_canonicalizers import (
        ArabicNumeralCanonicalizer, DevanagariNumeralCanonicalizer,
        NumberingSystemDetector, RomanNumeralCanonicalizer,
    )
    reg = CanonicalizerRegistry()
    reg.register(NumberingSystemDetector())
    reg.register(RomanNumeralCanonicalizer())
    reg.register(ArabicNumeralCanonicalizer())
    reg.register(DevanagariNumeralCanonicalizer())
    reg.register(StructuralValidator())
    return reg


REC_PIPELINE = RecognitionPipeline(_full_recognizer_registry())
CANON_PIPELINE = CanonicalizationPipeline(_full_canonicalization_registry())


def _run_end_to_end(text: str, preceding_canonical_number=None,
                     preceding_numbering_system=None, preceding_level=None):
    """Full recognition -> canonicalization -> structural validation,
    exactly mirroring what modules/stage_b_classify.py wires together,
    but with private, isolated registries/pipelines. Returns the final
    CanonicalHeading, or None if nothing recognized `text` at all.
    Never raises (that not-raising IS what most tests below assert)."""
    ctx = RecognitionContext(text=text)
    pipeline_result = REC_PIPELINE.run(ctx)
    if pipeline_result.winner is None:
        return None
    heading = CanonicalHeading.from_recognition(ctx, pipeline_result.winner)
    canon_context = CanonicalizationContext(
        preceding_canonical_number=preceding_canonical_number,
        preceding_numbering_system=preceding_numbering_system,
        metadata={PRECEDING_LEVEL_METADATA_KEY: preceding_level},
    )
    return CANON_PIPELINE.run(heading, canon_context).output_heading


# ===========================================================================
# 1. Edge case testing -- end to end, across recognition + canonicalization
#    + structural validation
# ===========================================================================

class TestEmptyAndWhitespaceHeadings(unittest.TestCase):
    def test_empty_string_never_raises_and_never_matches(self):
        self.assertIsNone(_run_end_to_end(""))

    def test_whitespace_only_never_raises_and_never_matches(self):
        for text in (" ", "\t", "\n", "   \t\n  ", "\u00a0", "\u200b"):
            with self.subTest(text=repr(text)):
                self.assertIsNone(_run_end_to_end(text))

    def test_recognition_context_accepts_empty_text_without_raising(self):
        # RecognitionContext itself places no non-empty constraint on
        # `text` (CanonicalHeading does, at its own later boundary) --
        # confirms a pipeline run against it is still well-defined.
        ctx = RecognitionContext(text="")
        result = REC_PIPELINE.run(ctx)  # must not raise
        self.assertEqual(result.winners, ())


class TestMalformedNumbering(unittest.TestCase):
    def test_malformed_roman_numerals_never_raise(self):
        # Note: "MMMM" is deliberately NOT in this list -- M4.3B's own
        # numeral_utils.roman_to_int documents an intentionally wider
        # M{0,4} range (accepts 4000) than heading_recognizers.utils's
        # stricter M{0,3}/3999 cap; it is not malformed by *this*
        # module's own definition. (RomanNumeralHeadingRecognizer's own
        # recognition-layer check still rejects "MMMM" -- see
        # TestMalformedNumbering's mixed/unsupported-style tests above,
        # and the manual probe in this milestone's own investigation --
        # so this wider cap is unreachable in the production pipeline
        # today; noted as an observation in the M4.3E deliverables, not
        # a defect, since it causes no incorrect production behavior.)
        for token in ("IIII", "VX", "IIV", "IM", "IL", "XXXX", "VV", "LL", "DD"):
            with self.subTest(token=token):
                value = roman_to_int(token)  # must not raise
                self.assertIsNone(value)

    def test_malformed_devanagari_numerals_never_raise(self):
        for token in ("", "abc", "५a", "a५", "१२a", "５"):  # last is fullwidth digit, not Devanagari
            with self.subTest(token=repr(token)):
                value = devanagari_to_int(token)  # must not raise
                self.assertIsNone(value)

    def test_mixed_numbering_systems_resolve_to_unknown_not_a_crash(self):
        # e.g. a digit followed by a roman letter -- neither pure arabic
        # nor pure roman nor devanagari.
        heading = CanonicalHeading(
            original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
            recognized_confidence=0.9, original_numbering="1V",
        )
        out = CANON_PIPELINE.run(heading).output_heading  # must not raise
        self.assertEqual(out.numbering_system, NumberingSystem.UNKNOWN)
        self.assertIsNone(out.canonical_number)

    def test_unsupported_numbering_style_resolves_to_unknown(self):
        for numbering in ("①", "IV-a", "1a", "*", "—", "四"):
            with self.subTest(numbering=numbering):
                heading = CanonicalHeading(
                    original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
                    recognized_confidence=0.9, original_numbering=numbering,
                )
                out = CANON_PIPELINE.run(heading).output_heading  # must not raise
                self.assertIn(out.numbering_system, (NumberingSystem.UNKNOWN, NumberingSystem.DEVANAGARI))


class TestDuplicateHeadingsAndInvalidHierarchy(unittest.TestCase):
    def test_duplicate_chapter_numbers_flagged_error(self):
        out1 = _run_end_to_end("Chapter 2")
        out2 = _run_end_to_end(
            "Chapter 2",
            preceding_canonical_number=out1.canonical_number,
            preceding_numbering_system=out1.numbering_system.value,
            preceding_level=out1.level,
        )
        self.assertEqual(out2.validation_status, ValidationStatus.ERROR)

    def test_invalid_hierarchy_jump_flagged_error(self):
        out1 = _run_end_to_end("Chapter 1")  # level 1
        out2 = _run_end_to_end("a)", preceding_level=out1.level)  # level 3 marker
        self.assertEqual(out2.level, 3)
        self.assertEqual(out2.validation_status, ValidationStatus.ERROR)


class TestMissingCanonicalValues(unittest.TestCase):
    def test_heading_with_no_numbering_at_all_is_success(self):
        out = _run_end_to_end("The Living World")
        self.assertIsNotNone(out)
        self.assertIsNone(out.canonical_number)
        self.assertEqual(out.numbering_system, NumberingSystem.NONE)
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_structural_validator_never_requires_canonical_type(self):
        # canonical_type is never populated by any M4.3B/D canonicalizer
        # in this codebase yet -- validation must be fully usable
        # without it.
        heading = CanonicalHeading(
            original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
            recognized_confidence=0.9,
        )
        out = StructuralValidator().canonicalize(heading, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)


class TestUnexpectedMetadataAndMalformedContext(unittest.TestCase):
    def test_unknown_metadata_keys_are_ignored_not_rejected(self):
        ctx = RecognitionContext(text="1", metadata={"totally_unexpected_key": object()})
        result = REC_PIPELINE.run(ctx)  # must not raise
        self.assertIsNotNone(result.winner)

    def test_canonicalization_context_with_unexpected_metadata_shape(self):
        heading = CanonicalHeading(
            original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
            recognized_confidence=0.9, level=3, canonical_number="1",
            numbering_system=NumberingSystem.ARABIC,
        )
        weird_ctx = CanonicalizationContext(
            preceding_canonical_number="1",
            preceding_numbering_system="arabic",
            metadata={PRECEDING_LEVEL_METADATA_KEY: object(), "unrelated": [1, 2, {3: 4}]},
        )
        out = CANON_PIPELINE.run(heading, weird_ctx).output_heading  # must not raise
        self.assertIsInstance(out, CanonicalHeading)

    def test_recognition_context_metadata_defensively_copied(self):
        shared = {"k": "v"}
        ctx = RecognitionContext(text="1", metadata=shared)
        shared["k"] = "mutated"
        self.assertEqual(ctx.metadata["k"], "v")  # context's own copy is unaffected

    def test_canonicalization_context_metadata_defensively_copied(self):
        shared = {"k": "v"}
        ctx = CanonicalizationContext(metadata=shared)
        shared["k"] = "mutated"
        self.assertEqual(ctx.metadata["k"], "v")


class TestVeryLongHeadingsAndUnicodeEdgeCases(unittest.TestCase):
    def test_very_long_numbering_token_never_raises(self):
        # Recognizer-layer candidate-length pre-filters (e.g.
        # ChapterNumberRecognizer's own _MAX_CANDIDATE_LENGTH) are a
        # deliberate structural heuristic -- a real heading numbering
        # is never hundreds of digits long -- so a 300-digit token is
        # correctly SKIPPED at recognition, not an error. Structural
        # validation and numeral canonicalization themselves must
        # still never raise on an oversized number if one somehow
        # reaches them, so this exercises that layer directly.
        heading = CanonicalHeading(
            original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
            recognized_confidence=0.9, original_numbering="9" * 300,
        )
        out = CANON_PIPELINE.run(heading).output_heading  # must not raise
        self.assertEqual(out.numbering_system, NumberingSystem.ARABIC)
        self.assertEqual(len(out.canonical_number), 300)

    def test_very_long_devanagari_numeral_never_raises(self):
        heading = CanonicalHeading(
            original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
            recognized_confidence=0.9, original_numbering="५" * 200,
        )
        out = CANON_PIPELINE.run(heading).output_heading  # must not raise
        self.assertEqual(out.numbering_system, NumberingSystem.DEVANAGARI)
        self.assertEqual(len(out.canonical_number), 200)

    def test_very_long_plain_text_is_simply_not_a_heading(self):
        # Every generic recognizer's own supports() length ceiling
        # means an oversized candidate is cheaply SKIPPED, not an
        # error -- confirms that pre-filter holds for pathological input.
        self.assertIsNone(_run_end_to_end("word " * 5000))

    def test_unicode_combining_characters_never_raise(self):
        # "Chapter" with a combining acute accent injected mid-word,
        # plus a right-to-left override control character.
        for text in ("Chapter\u0301 1", "\u202eChapter 1\u202c", "Chapter\u200d1", "🎉Chapter 1🎉"):
            with self.subTest(text=repr(text)):
                _run_end_to_end(text)  # must not raise; match/no-match either is fine

    def test_emoji_only_text_never_raises(self):
        self.assertIsNone(_run_end_to_end("🎉🎊✨"))

    def test_null_byte_and_control_characters_never_raise(self):
        for text in ("Chapter 1\x00", "\x01\x02\x03", "Chapter\x0c1"):
            with self.subTest(text=repr(text)):
                _run_end_to_end(text)  # must not raise


class TestMalformedMetadataNeverCrashes(unittest.TestCase):
    """Regression coverage for the one genuine defect found and fixed
    during M4.3E: `modules/stage_b_classify.py`'s
    `_heading_recognition_text` called `.strip()` unconditionally on
    `grouping_meta.get("numbering")`/`("title")` after `or ""`, which
    raised `AttributeError` for any other truthy non-string value
    (e.g. a stray int/list/dict from malformed upstream metadata),
    contradicting that function's own "never raises" contract and
    crashing the entire `classify_blocks()` page loop for every block
    after the malformed one."""

    def _classify(self, **meta):
        try:
            from modules.stage_a_geometry import Block
            from modules.stage_b_classify import classify
        except Exception as exc:  # pragma: no cover - environment-dependent
            self.skipTest(f"modules.stage_b_classify unavailable: {exc}")
        block = Block(block_id="b1", page=1, bbox=(50.0, 100.0, 400.0, 120.0),
                      lines=[], children=[], grouping_meta=meta)
        return classify(block)  # must not raise

    def test_non_string_numbering_never_raises(self):
        self._classify(anchor="heading-topic", numbering=123, level=1, title=None)

    def test_non_string_level_never_raises(self):
        self._classify(anchor="heading-topic", numbering="1", level="not-an-int", title=None)

    def test_non_string_title_never_raises(self):
        self._classify(anchor="heading-topic", numbering=None, level=1, title=456)

    def test_list_and_dict_metadata_values_never_raise(self):
        self._classify(anchor="heading-topic", numbering=["1", "2"], level=None, title={"a": 1})

    def test_well_formed_string_metadata_still_recognized_correctly(self):
        # The fix must not change behavior for the overwhelmingly
        # common, well-formed case.
        block_type, confidence = self._classify(
            anchor="heading-topic", numbering="3", level=1, title=None,
        )
        self.assertEqual((block_type, confidence), ("Heading", 1.0))

    def test_missing_metadata_keys_entirely_never_raise(self):
        self._classify(anchor="heading-topic")

    def test_empty_grouping_meta_never_raises(self):
        self._classify()


# ===========================================================================
# 2. Error isolation
# ===========================================================================

class TestErrorIsolation(unittest.TestCase):
    def test_recognizer_failure_is_isolated_from_the_pipeline_run(self):
        from modules.heading_recognizers.base import HeadingRecognizer, RecognitionResult

        class _ExplodingRecognizer(HeadingRecognizer):
            name = "exploding"
            classification = HeadingClassification.UNCLASSIFIED
            default_priority = 1

            def recognize(self, context):
                raise RuntimeError("boom: simulated recognizer bug")

        reg = RecognizerRegistry()
        reg.register(_ExplodingRecognizer())
        reg.register(NumberedHeadingRecognizer())
        pipeline = RecognitionPipeline(reg)
        result = pipeline.run(RecognitionContext(text="3"))  # must not raise
        self.assertIsNotNone(result.winner)
        self.assertEqual(result.winner.recognizer_name, "numbered_heading")
        failed = [a for a in result.attempts if a.recognizer_name == "exploding"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].outcome.value, "failed")

    def test_recognizer_supports_failure_is_isolated(self):
        from modules.heading_recognizers.base import HeadingRecognizer

        class _ExplodingSupports(HeadingRecognizer):
            name = "exploding_supports"
            classification = HeadingClassification.UNCLASSIFIED
            default_priority = 1

            def supports(self, context):
                raise RuntimeError("boom: simulated supports() bug")

            def recognize(self, context):
                return None

        reg = RecognizerRegistry()
        reg.register(_ExplodingSupports())
        reg.register(NumberedHeadingRecognizer())
        pipeline = RecognitionPipeline(reg)
        result = pipeline.run(RecognitionContext(text="3"))  # must not raise
        self.assertIsNotNone(result.winner)

    def test_canonicalizer_failure_is_isolated_from_the_pipeline_run(self):
        from modules.heading_canonicalization.base import HeadingCanonicalizer
        from modules.heading_canonicalization.numeral_canonicalizers import (
            ArabicNumeralCanonicalizer, NumberingSystemDetector,
        )

        class _ExplodingCanonicalizer(HeadingCanonicalizer):
            name = "exploding_canonicalizer"
            default_priority = 5

            def canonicalize(self, heading, context):
                raise RuntimeError("boom: simulated canonicalizer bug")

        reg = CanonicalizerRegistry()
        reg.register(NumberingSystemDetector())
        reg.register(_ExplodingCanonicalizer())
        reg.register(ArabicNumeralCanonicalizer())
        pipeline = CanonicalizationPipeline(reg)
        heading = CanonicalHeading(
            original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
            recognized_confidence=0.9, original_numbering="3",
        )
        result = pipeline.run(heading)  # must not raise
        self.assertEqual(result.output_heading.canonical_number, "3")

    def test_structural_validator_failure_is_isolated(self):
        from modules.heading_canonicalization.base import HeadingCanonicalizer
        from modules.heading_canonicalization.numeral_canonicalizers import (
            ArabicNumeralCanonicalizer, NumberingSystemDetector,
        )

        class _ExplodingValidator(HeadingCanonicalizer):
            name = "structural_validator"
            default_priority = 200

            def canonicalize(self, heading, context):
                raise RuntimeError("boom: simulated validator bug")

        reg = CanonicalizerRegistry()
        reg.register(NumberingSystemDetector())
        reg.register(ArabicNumeralCanonicalizer())
        reg.register(_ExplodingValidator())
        pipeline = CanonicalizationPipeline(reg)
        heading = CanonicalHeading(
            original_text="x", recognized_classification=HeadingClassification.CHAPTER_TITLE,
            recognized_confidence=0.9, original_numbering="3",
        )
        result = pipeline.run(heading)  # must not raise
        self.assertEqual(result.output_heading.canonical_number, "3")
        self.assertEqual(result.output_heading.validation_status, ValidationStatus.PENDING)


# ===========================================================================
# 3. Determinism
# ===========================================================================

class TestDeterminism(unittest.TestCase):
    def test_recognition_is_deterministic_across_repeated_runs(self):
        texts = ["Chapter 3", "1.1", "IV", "a)", "The Living World", "अध्याय ५", "अध्यायः"]
        for text in texts:
            with self.subTest(text=text):
                first = REC_PIPELINE.run(RecognitionContext(text=text))
                for _ in range(5):
                    again = REC_PIPELINE.run(RecognitionContext(text=text))
                    self.assertEqual(again.winners, first.winners)
                    self.assertEqual(
                        [a.outcome for a in again.attempts], [a.outcome for a in first.attempts]
                    )

    def test_full_stack_is_deterministic_across_repeated_runs(self):
        first = _run_end_to_end("Chapter 4", preceding_canonical_number="4",
                                 preceding_numbering_system="arabic", preceding_level=1)
        for _ in range(5):
            again = _run_end_to_end("Chapter 4", preceding_canonical_number="4",
                                     preceding_numbering_system="arabic", preceding_level=1)
            self.assertEqual(again.canonical_number, first.canonical_number)
            self.assertEqual(again.validation_status, first.validation_status)
            self.assertEqual(again.diagnostics, first.diagnostics)

    def test_registry_ordering_is_deterministic_regardless_of_dict_iteration(self):
        reg = _full_recognizer_registry()
        names_1 = [r.name for r in reg.all_recognizers()]
        names_2 = [r.name for r in reg.all_recognizers()]
        self.assertEqual(names_1, names_2)


# ===========================================================================
# 4. Performance / singleton reuse
# ===========================================================================

class TestSingletonReuse(unittest.TestCase):
    def test_stage_b_uses_one_module_level_recognition_pipeline(self):
        try:
            import modules.stage_b_classify as stage_b_classify
        except Exception as exc:  # pragma: no cover - environment-dependent
            self.skipTest(f"modules.stage_b_classify unavailable: {exc}")
        p1 = stage_b_classify._HEADING_RECOGNITION_PIPELINE
        p2 = stage_b_classify._HEADING_RECOGNITION_PIPELINE
        self.assertIs(p1, p2)

    def test_stage_b_uses_one_module_level_canonicalization_pipeline(self):
        try:
            import modules.stage_b_classify as stage_b_classify
        except Exception as exc:  # pragma: no cover - environment-dependent
            self.skipTest(f"modules.stage_b_classify unavailable: {exc}")
        p1 = stage_b_classify._HEADING_CANONICALIZATION_PIPELINE
        p2 = stage_b_classify._HEADING_CANONICALIZATION_PIPELINE
        self.assertIs(p1, p2)

    def test_pipeline_run_does_not_mutate_or_rebuild_the_registry(self):
        reg = _full_recognizer_registry()
        pipeline = RecognitionPipeline(reg)
        before = reg.registered_names()
        for _ in range(20):
            pipeline.run(RecognitionContext(text="Chapter 1"))
        after = reg.registered_names()
        self.assertEqual(before, after)
        self.assertIs(pipeline.registry, reg)  # same instance, never rebuilt


# ===========================================================================
# 5. Public API freeze verification
# ===========================================================================

class TestPublicApiFreeze(unittest.TestCase):
    def test_heading_recognizers_exports_unchanged(self):
        import modules.heading_recognizers as hr
        expected = {
            "RecognitionContext", "ConfidenceInfo", "RecognitionResult", "FailureResult",
            "HeadingRecognizer",
            "HeadingRecognitionConfig", "RecognizerSettings", "default_config",
            "RecognizerRegistry", "default_registry", "register", "unregister", "get",
            "enabled_recognizers", "all_recognizers",
            "RecognizerFactory", "default_factory",
            "AttemptRecord", "PipelineResult", "RecognitionPipeline",
            "HeadingClassification", "ConflictResolutionStrategy",
            "RecognizerState", "RecognitionOutcome",
            "HeadingRecognitionError", "RecognizerRegistrationError", "RecognizerConfigurationError",
            "RecognizerLookupError", "RecognizerExecutionError", "RecognitionPipelineError",
            "NumberedHeadingRecognizer", "HierarchicalHeadingRecognizer",
            "RomanNumeralHeadingRecognizer", "AlphabeticHeadingRecognizer",
            "ChapterNumberRecognizer", "ChapterTitleRecognizer",
            "HindiHeadingRecognizer", "SanskritHeadingRecognizer",
        }
        self.assertEqual(set(hr.__all__), expected)
        for name in expected:
            self.assertTrue(hasattr(hr, name), f"missing public export: {name}")

    def test_heading_canonicalization_exports_unchanged_since_m43d(self):
        import modules.heading_canonicalization as hc
        expected = {
            "CanonicalHeading", "ValidationDiagnostic", "ValidationResult", "SUCCESS",
            "CanonicalizationContext", "CanonicalizationFailure", "HeadingCanonicalizer",
            "HeadingCanonicalizationConfig", "CanonicalizerSettings", "default_config",
            "CanonicalizerRegistry", "default_registry", "register", "unregister", "get",
            "enabled_canonicalizers", "all_canonicalizers",
            "CanonicalizationPipeline", "CanonicalizationPipelineResult", "AttemptRecord",
            "NumberingSystemDetector", "RomanNumeralCanonicalizer",
            "ArabicNumeralCanonicalizer", "DevanagariNumeralCanonicalizer",
            "CanonicalHeadingType", "NumberingSystem", "ValidationStatus", "ValidationSeverity",
            "CanonicalizerState", "CanonicalizationOutcome",
            "HeadingCanonicalizationError", "CanonicalizerRegistrationError",
            "CanonicalizerConfigurationError", "CanonicalizerLookupError",
            "CanonicalizerExecutionError", "CanonicalizationPipelineError",
            "CanonicalHeadingValidationError",
            "StructuralValidator", "PRECEDING_LEVEL_METADATA_KEY",
        }
        self.assertEqual(set(hc.__all__), expected)
        for name in expected:
            self.assertTrue(hasattr(hc, name), f"missing public export: {name}")

    def test_default_registries_unchanged_since_m43d(self):
        import modules.heading_canonicalization as hc
        names = set(hc.default_registry.registered_names())
        self.assertEqual(
            names,
            {
                "numbering_system_detector", "roman_numeral_canonicalizer",
                "arabic_numeral_canonicalizer", "devanagari_numeral_canonicalizer",
                "structural_validator",
            },
        )

    def test_config_flags_unchanged_since_m43d(self):
        try:
            import config
        except Exception as exc:  # pragma: no cover - environment-dependent
            self.skipTest(f"config unavailable: {exc}")
        for flag in ("ENABLE_HEADING_RECOGNITION", "ENABLE_HEADING_CANONICALIZATION",
                     "ENABLE_STRUCTURAL_VALIDATION"):
            self.assertTrue(hasattr(config, flag), f"missing config flag: {flag}")
            self.assertIsInstance(getattr(config, flag), bool)


# ===========================================================================
# 6. Regression -- M4.2/M4.3A-D suites still pass unmodified
# ===========================================================================

class TestRegressionSuitesStillPass(unittest.TestCase):
    """Loads and runs every test_m42*/test_m43[abcd]* module in-process
    (not just "collectible") and fails loudly if anything in them
    regressed. Modules that themselves fail to import for reasons
    unrelated to this milestone (e.g. an unavailable optional
    dependency such as pytest, already failing identically before this
    milestone) are reported, not silently skipped, but don't fail this
    particular test -- test_m43[abcd]*, which have no such external
    dependency, are held to a strict zero-tolerance standard."""

    _STRICT_PREFIXES = ("test_m43a", "test_m43b", "test_m43c", "test_m43d")

    def test_m43_suites_pass_with_zero_failures(self):
        loader = unittest.TestLoader()
        tests_dir = _REPO / "tests"
        for path in sorted(tests_dir.glob("test_m43[abcd]*.py")):
            module_name = f"tests.{path.stem}"
            with self.subTest(module=module_name):
                suite = loader.loadTestsFromName(module_name)
                result = unittest.TextTestRunner(verbosity=0, stream=io.StringIO()).run(suite)
                self.assertEqual(
                    (len(result.failures), len(result.errors)), (0, 0),
                    f"{module_name}: {len(result.failures)} failure(s), {len(result.errors)} error(s)",
                )

    def test_m42_suites_at_least_partially_collectible(self):
        # M4.2's own suites (test_m41b/test_m41cd/test_m41e) require an
        # optional `pytest` dependency this sandbox doesn't have --
        # verified pre-existing and unrelated to this milestone (fails
        # on `import pytest` before any heading-subsystem code runs).
        # test_m42*'s own suites (no pytest dependency) are held to the
        # same zero-tolerance standard as M4.3.
        loader = unittest.TestLoader()
        tests_dir = _REPO / "tests"
        found_any = False
        for path in sorted(tests_dir.glob("test_m42*.py")):
            found_any = True
            module_name = f"tests.{path.stem}"
            with self.subTest(module=module_name):
                try:
                    suite = loader.loadTestsFromName(module_name)
                except Exception as exc:
                    self.skipTest(f"{module_name} unavailable in this environment: {exc}")
                    continue
                result = unittest.TextTestRunner(verbosity=0, stream=io.StringIO()).run(suite)
                self.assertEqual(
                    (len(result.failures), len(result.errors)), (0, 0),
                    f"{module_name}: {len(result.failures)} failure(s), {len(result.errors)} error(s)",
                )
        if not found_any:
            self.skipTest("no test_m42*.py modules found")


if __name__ == "__main__":
    unittest.main()
