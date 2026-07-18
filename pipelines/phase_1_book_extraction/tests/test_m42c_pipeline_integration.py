"""
tests/test_m42c_pipeline_integration.py — M4.2C integration tests:
modules/heading_recognizers (the M4.2A framework + M4.2B generic
recognizer family) wired into the production heading detection flow
(modules/stage_b_classify.classify / classify_blocks).

This milestone is integration only (no new recognizer, no framework
redesign) — these tests exercise the WIRING: that a heading-topic
Block's grouping_meta reaches the shared RecognitionPipeline, that a
winning recognizer's result is attached as metadata, that conflicts
between recognizers are resolved through the framework's own
conflict-resolution mechanism (never a second one), that a recognizer
failure can never take Stage B down, and that none of this changes
Stage B's pre-existing "Heading"/1.0 contract for heading-topic
blocks (M4.1's backward-compatibility guarantee).

Coverage:
  - successful pipeline integration (numbered + unnumbered headings)
  - multiple recognizers matching the same heading / conflict
    resolution (mirrors M4.2B's own "I" roman-vs-alphabetic case)
  - malformed / empty headings
  - recognizer failures do not abort Stage B
  - deterministic execution across repeated runs
  - backward compatibility (legacy heading-topic blocks with no
    title/numbering in grouping_meta; non-heading anchors untouched)
  - configuration-driven behaviour (config.ENABLE_HEADING_RECOGNITION
    toggle; a stricter per-deployment HeadingRecognitionConfig)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import config
from modules.stage_a_geometry import Block
import modules.stage_b_classify as stage_b_classify
from modules.stage_b_classify import classify, classify_blocks
from modules.heading_recognizers.base import (
    HeadingRecognizer,
    RecognitionContext,
    RecognitionResult,
)
from modules.heading_recognizers.config import (
    HeadingRecognitionConfig,
    RecognizerSettings,
    default_config,
)
from modules.heading_recognizers.enums import HeadingClassification
from modules.heading_recognizers.factory import RecognizerFactory
from modules.heading_recognizers.generic_recognizers import (
    ChapterTitleRecognizer,
    HierarchicalHeadingRecognizer,
    NumberedHeadingRecognizer,
)
from modules.heading_recognizers.pipeline import RecognitionPipeline
from modules.heading_recognizers.registry import RecognizerRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _heading_block(numbering=None, title=None, level=1, page=1, y=100.0,
                    topic_id="t1", block_id="b1", extra_meta=None):
    meta = {"anchor": "heading-topic", "topic_id": topic_id,
            "numbering": numbering, "level": level, "title": title}
    if extra_meta:
        meta.update(extra_meta)
    return Block(block_id=block_id, page=page, bbox=(50.0, y, 400.0, y + 20.0),
                 lines=[], children=[], grouping_meta=meta)


class _SwapPipeline:
    """Context manager that temporarily swaps Stage B's module-level
    `_HEADING_RECOGNITION_PIPELINE` for an isolated one (built from a
    fresh RecognizerRegistry/RecognitionPipeline), so a test can inject
    a broken/limited recognizer set without mutating the framework's
    shared `default_registry` any other test or module might depend
    on. Restores the original pipeline on exit regardless of outcome."""

    def __init__(self, pipeline: RecognitionPipeline):
        self._new = pipeline
        self._old = None

    def __enter__(self):
        self._old = stage_b_classify._HEADING_RECOGNITION_PIPELINE
        stage_b_classify._HEADING_RECOGNITION_PIPELINE = self._new
        return self._new

    def __exit__(self, exc_type, exc_val, tb):
        stage_b_classify._HEADING_RECOGNITION_PIPELINE = self._old
        return False


class _ExplodingRecognizer(HeadingRecognizer):
    """Test double: always raises. Used to prove a recognizer failure
    can never abort Stage B (M4.2C error-handling requirement)."""

    name = "exploding_heading"
    classification = HeadingClassification.UNCLASSIFIED
    default_priority = 1  # runs first, so its failure can't be masked by an earlier winner

    def recognize(self, context: RecognitionContext):
        raise RuntimeError("boom: simulated recognizer bug")


def _registry_with(*recognizers, config_obj=None):
    reg = RecognizerRegistry(config=config_obj or default_config())
    for r in recognizers:
        reg.register(r)
    return reg


# ---------------------------------------------------------------------------
# 1. Successful pipeline integration
# ---------------------------------------------------------------------------

class TestSuccessfulIntegration(unittest.TestCase):
    def test_numbered_heading_gets_recognition_metadata(self):
        b = _heading_block(numbering="1.1", title="Motion", level=2)
        block_type, confidence = classify(b)
        self.assertEqual(block_type, "Heading")
        self.assertEqual(confidence, 1.0)
        meta = b.grouping_meta["heading_recognition"]
        self.assertEqual(meta["recognizer_name"], "hierarchical_heading")
        self.assertEqual(meta["classification"], "hierarchical")
        self.assertEqual(meta["number"], "1.1")
        self.assertTrue(0.0 <= meta["confidence"] <= 1.0)
        self.assertTrue(meta["diagnostics"])

    def test_unnumbered_chapter_title_gets_recognition_metadata(self):
        b = _heading_block(numbering=None, title="Motion", level=1)
        block_type, confidence = classify(b)
        self.assertEqual(block_type, "Heading")
        self.assertEqual(confidence, 1.0)
        meta = b.grouping_meta["heading_recognition"]
        self.assertEqual(meta["recognizer_name"], "chapter_title")
        self.assertEqual(meta["classification"], "chapter_title")

    def test_classify_blocks_end_to_end(self):
        blocks = [
            _heading_block(numbering=None, title="Motion", level=1,
                            topic_id="t1", block_id="b1", y=50.0),
            _heading_block(numbering="1.1", title="Uniform Motion", level=2,
                            topic_id="t2", block_id="b2", y=150.0),
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        self.assertEqual(by_id["b1"].block_type, "Heading")
        self.assertEqual(by_id["b2"].block_type, "Heading")
        self.assertIn("heading_recognition", by_id["b1"].grouping_meta)
        self.assertIn("heading_recognition", by_id["b2"].grouping_meta)


# ---------------------------------------------------------------------------
# 2. Multiple recognizers matching / conflict resolution
# ---------------------------------------------------------------------------

class TestConflictResolution(unittest.TestCase):
    def test_ambiguous_roman_vs_alphabetic_resolves_deterministically(self):
        # "I" is a valid bare Roman numeral AND a valid bare single-letter
        # alphabetic marker (mirrors M4.2B's own ambiguity test) — both
        # recognizers match; the framework's own conflict resolver (not a
        # second one built for this integration) must pick exactly one
        # winner, and it must be the higher-confidence Roman match.
        b = _heading_block(numbering="I", title=None, level=1)
        classify(b)
        meta = b.grouping_meta["heading_recognition"]
        self.assertEqual(meta["recognizer_name"], "roman_numeral_heading")

    def test_hierarchical_wins_over_numbered_by_priority(self):
        # "1.1" only structurally matches HierarchicalHeadingRecognizer
        # (NumberedHeadingRecognizer's own regex rejects a "." mid-token),
        # so this exercises the *registry's* priority ordering feeding
        # RecognitionPipeline, not an ambiguous multi-match — hierarchical
        # is registered at priority 10, ahead of numbered's 20.
        b = _heading_block(numbering="1.1", title=None, level=2)
        classify(b)
        meta = b.grouping_meta["heading_recognition"]
        self.assertEqual(meta["recognizer_name"], "hierarchical_heading")


# ---------------------------------------------------------------------------
# 3. Malformed headings
# ---------------------------------------------------------------------------

class TestMalformedHeadings(unittest.TestCase):
    def test_empty_numbering_and_title_no_crash_no_metadata(self):
        b = _heading_block(numbering=None, title=None)
        block_type, confidence = classify(b)
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        self.assertNotIn("heading_recognition", b.grouping_meta)

    def test_whitespace_only_title_no_crash_no_metadata(self):
        b = _heading_block(numbering="   ", title="   ")
        block_type, confidence = classify(b)
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        self.assertNotIn("heading_recognition", b.grouping_meta)

    def test_nonsense_text_no_match_no_metadata(self):
        # Long, non-title-cased, unnumbered gibberish matches none of the
        # six generic recognizers — should degrade to plain "Heading"/1.0
        # exactly like before M4.2C, not raise or downgrade confidence.
        b = _heading_block(numbering=None,
                            title="this is definitely not a title-cased heading at all really")
        block_type, confidence = classify(b)
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        self.assertNotIn("heading_recognition", b.grouping_meta)

    def test_missing_grouping_meta_entirely(self):
        b = Block(block_id="b1", page=1, bbox=(0, 0, 10, 10), lines=[], children=[],
                   grouping_meta={"anchor": "heading-topic"})
        block_type, confidence = classify(b)
        self.assertEqual((block_type, confidence), ("Heading", 1.0))


# ---------------------------------------------------------------------------
# 4. Recognizer failures must not terminate the pipeline
# ---------------------------------------------------------------------------

class TestRecognizerFailureHandling(unittest.TestCase):
    def test_exploding_recognizer_does_not_crash_classify(self):
        broken_registry = _registry_with(_ExplodingRecognizer())
        with _SwapPipeline(RecognitionPipeline(broken_registry)):
            b = _heading_block(numbering="1.1", title="Motion", level=2)
            block_type, confidence = classify(b)  # must not raise
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        # The one registered recognizer failed outright — no winner, so
        # no metadata is attached, but Stage A's own classification is
        # completely unaffected.
        self.assertNotIn("heading_recognition", b.grouping_meta)

    def test_remaining_candidates_still_process_after_a_failure(self):
        # A failing recognizer on ONE block must not prevent a LATER
        # block in the same classify_blocks() run from being recognized
        # normally — proves Stage B keeps processing remaining heading
        # candidates exactly as M4.2C requires.
        broken_registry = _registry_with(
            _ExplodingRecognizer(), ChapterTitleRecognizer(),
        )
        with _SwapPipeline(RecognitionPipeline(broken_registry)):
            blocks = [
                _heading_block(numbering=None, title="Motion", level=1,
                                block_id="b1", y=50.0),
                _heading_block(numbering=None, title="Electricity", level=1,
                                block_id="b2", y=150.0),
            ]
            result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        self.assertEqual(by_id["b1"].block_type, "Heading")
        self.assertEqual(by_id["b2"].block_type, "Heading")
        self.assertEqual(
            by_id["b1"].grouping_meta["heading_recognition"]["recognizer_name"],
            "chapter_title",
        )
        self.assertEqual(
            by_id["b2"].grouping_meta["heading_recognition"]["recognizer_name"],
            "chapter_title",
        )


# ---------------------------------------------------------------------------
# 5. Deterministic execution
# ---------------------------------------------------------------------------

class TestDeterministicExecution(unittest.TestCase):
    def test_repeated_classify_calls_produce_identical_metadata(self):
        results = []
        for _ in range(5):
            b = _heading_block(numbering="1.1", title="Motion", level=2)
            classify(b)
            results.append(b.grouping_meta["heading_recognition"])
        first = results[0]
        for r in results[1:]:
            self.assertEqual(r, first)

    def test_repeated_classify_blocks_runs_produce_identical_output(self):
        def build():
            return [
                _heading_block(numbering=None, title="Motion", level=1,
                                block_id="b1", y=50.0),
                _heading_block(numbering="1.1", title="Uniform Motion", level=2,
                                block_id="b2", y=150.0),
                _heading_block(numbering="I", title=None, level=1,
                                block_id="b3", y=250.0),
            ]
        run_1 = classify_blocks(build())
        run_2 = classify_blocks(build())
        for b1, b2 in zip(run_1, run_2):
            self.assertEqual(b1.block_type, b2.block_type)
            self.assertEqual(b1.confidence, b2.confidence)
            self.assertEqual(
                b1.grouping_meta.get("heading_recognition"),
                b2.grouping_meta.get("heading_recognition"),
            )


# ---------------------------------------------------------------------------
# 6. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility(unittest.TestCase):
    def test_legacy_heading_block_without_title_or_numbering_unaffected(self):
        # The exact grouping_meta shape M4.1's own tests already use for
        # heading-topic blocks (no "title"/"numbering" keys at all) --
        # must classify identically to before M4.2C.
        b = Block(block_id="b1", page=0, bbox=(50, 100, 400, 120), lines=[],
                   children=[], grouping_meta={"anchor": "heading-topic"})
        block_type, confidence = classify(b)
        self.assertEqual((block_type, confidence), ("Heading", 1.0))

    def test_non_heading_anchors_are_never_sent_to_the_framework(self):
        b = Block(block_id="b1", page=0, bbox=(0, 0, 10, 10), lines=[],
                   children=[], grouping_meta={"anchor": "table"})
        block_type, confidence = classify(b)
        self.assertNotIn("heading_recognition", b.grouping_meta)
        self.assertEqual(block_type, "Table")

    def test_disabling_feature_toggle_preserves_heading_classification(self):
        original = config.ENABLE_HEADING_RECOGNITION
        config.ENABLE_HEADING_RECOGNITION = False
        try:
            b = _heading_block(numbering="1.1", title="Motion", level=2)
            block_type, confidence = classify(b)
        finally:
            config.ENABLE_HEADING_RECOGNITION = original
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        self.assertNotIn("heading_recognition", b.grouping_meta)


# ---------------------------------------------------------------------------
# 7. Configuration-driven behaviour
# ---------------------------------------------------------------------------

class TestConfigurationDrivenBehaviour(unittest.TestCase):
    def test_feature_toggle_enabled_by_default(self):
        self.assertTrue(config.ENABLE_HEADING_RECOGNITION)

    def test_feature_toggle_off_skips_recognition_entirely(self):
        original = config.ENABLE_HEADING_RECOGNITION
        config.ENABLE_HEADING_RECOGNITION = False
        try:
            b = _heading_block(numbering=None, title="Motion", level=1)
            classify(b)
            self.assertNotIn("heading_recognition", b.grouping_meta)
        finally:
            config.ENABLE_HEADING_RECOGNITION = original

    def test_stricter_confidence_threshold_changes_outcome(self):
        # A per-deployment HeadingRecognitionConfig with a threshold above
        # ChapterTitleRecognizer's own achievable confidence for a 1-word
        # title turns its match into a below-threshold NO_MATCH — proves
        # Stage B reads recognizer settings from the framework's own
        # configuration object rather than a hard-coded threshold of its
        # own (M4.2C's "no new hard-coded thresholds" requirement).
        strict_config = default_config().with_recognizer_settings(
            RecognizerSettings(name="chapter_title", confidence_threshold=0.99)
        )
        factory = RecognizerFactory(config=strict_config)
        factory.register_class(ChapterTitleRecognizer.name, ChapterTitleRecognizer)
        strict_registry = factory.build_registry(RecognizerRegistry(config=strict_config))

        with _SwapPipeline(RecognitionPipeline(strict_registry)):
            b = _heading_block(numbering=None, title="Motion", level=1)
            classify(b)
        self.assertNotIn("heading_recognition", b.grouping_meta)

    def test_permissive_threshold_allows_the_same_match(self):
        permissive_config = default_config()  # framework default threshold (0.5)
        factory = RecognizerFactory(config=permissive_config)
        factory.register_class(ChapterTitleRecognizer.name, ChapterTitleRecognizer)
        registry = factory.build_registry(RecognizerRegistry(config=permissive_config))

        with _SwapPipeline(RecognitionPipeline(registry)):
            b = _heading_block(numbering=None, title="Motion", level=1)
            classify(b)
        self.assertEqual(
            b.grouping_meta["heading_recognition"]["recognizer_name"], "chapter_title"
        )


# ---------------------------------------------------------------------------
# 8. preceding_heading_level threading through classify_blocks()
# ---------------------------------------------------------------------------

class TestPrecedingHeadingLevelTracking(unittest.TestCase):
    def test_chapter_title_confidence_is_higher_right_after_a_level_1_heading(self):
        # ChapterTitleRecognizer scores a small context bonus when
        # `preceding_heading_level == 1` — classify_blocks() must derive
        # that from the *previous* heading-topic block's own Stage A
        # `level`, in page reading order, and thread it through.
        first = _heading_block(numbering="1", title=None, level=1,
                                block_id="b1", y=50.0)
        second = _heading_block(numbering=None, title="Motion", level=1,
                                 block_id="b2", y=150.0)
        classify_blocks([first, second])
        meta = second.grouping_meta["heading_recognition"]
        self.assertEqual(meta["recognizer_name"], "chapter_title")

        # Same title, but with nothing preceding it on its own page —
        # context_score should be lower (0.9 instead of 1.0 per
        # ChapterTitleRecognizer's own docstring), so confidence differs.
        isolated = _heading_block(numbering=None, title="Motion", level=1,
                                   block_id="b3", y=50.0, page=2)
        classify_blocks([isolated])
        isolated_meta = isolated.grouping_meta["heading_recognition"]
        self.assertLess(isolated_meta["confidence"], meta["confidence"])


if __name__ == "__main__":
    unittest.main()