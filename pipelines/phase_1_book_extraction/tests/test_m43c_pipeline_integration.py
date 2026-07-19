"""
tests/test_m43c_pipeline_integration.py — M4.3C integration tests:
modules/heading_canonicalization (the M4.3A framework + M4.3B
number-system canonicalizers) wired into the production heading
extraction flow, immediately downstream of M4.2C's own
modules/heading_recognizers integration
(modules/stage_b_classify.classify / classify_blocks).

This milestone is integration only (no new canonicalizer, no
framework redesign) — these tests exercise the WIRING: that a
successfully recognized heading (M4.2's own `heading_recognition`
metadata already attached by M4.2C) is additionally run through the
shared CanonicalizationPipeline, that its output lands as a second,
new `heading_canonicalization` grouping_meta key, that a
canonicalizer failure can never take Stage B down (and never disturbs
the already-attached `heading_recognition` metadata), that this is
fully configuration-driven (config.ENABLE_HEADING_CANONICALIZATION),
and that none of this changes Stage B's pre-existing
"Heading"/1.0 contract or M4.2C's own `heading_recognition` contract.

Coverage:
  - successful recognition -> canonicalization flow (Roman / Arabic /
    Devanagari headings all resolve to canonical_number "3")
  - canonical metadata propagation via classify() and classify_blocks()
  - registry/pipeline reuse (module-level singleton, no rebuilding)
  - canonicalizer failures are isolated (recognition metadata and
    block_type/confidence remain intact; diagnostics/logging only)
  - backward compatibility (existing recognition metadata, existing
    APIs, existing block_type/confidence behaviour all unchanged)
  - configuration-driven behaviour
    (config.ENABLE_HEADING_CANONICALIZATION toggle)
  - deterministic execution across repeated runs
  - regression: this file never modifies the frozen M4.2/M4.3A/M4.3B
    framework files it imports from
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

from modules.heading_canonicalization.base import CanonicalizationContext, HeadingCanonicalizer
from modules.heading_canonicalization.enums import NumberingSystem
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.numeral_canonicalizers import (
    ArabicNumeralCanonicalizer,
    DevanagariNumeralCanonicalizer,
    NumberingSystemDetector,
    RomanNumeralCanonicalizer,
)
from modules.heading_canonicalization.pipeline import CanonicalizationPipeline
from modules.heading_canonicalization.registry import CanonicalizerRegistry


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


def _default_canonicalization_registry() -> CanonicalizerRegistry:
    """A fresh registry wired up exactly like the package's own
    default_registry (see modules/heading_canonicalization/__init__.py),
    for tests that need an isolated instance rather than the process-wide
    singleton."""
    registry = CanonicalizerRegistry()
    registry.register(NumberingSystemDetector())
    registry.register(RomanNumeralCanonicalizer())
    registry.register(ArabicNumeralCanonicalizer())
    registry.register(DevanagariNumeralCanonicalizer())
    return registry


class _SwapCanonicalizationPipeline:
    """Context manager that temporarily swaps Stage B's module-level
    `_HEADING_CANONICALIZATION_PIPELINE` for an isolated one, so a test
    can inject a broken/limited canonicalizer set without mutating the
    framework's shared default_registry any other test or module might
    depend on. Restores the original pipeline on exit regardless of
    outcome -- mirrors test_m42c_pipeline_integration.py's own
    `_SwapPipeline` exactly, applied one stage downstream."""

    def __init__(self, pipeline: CanonicalizationPipeline):
        self._new = pipeline
        self._old = None

    def __enter__(self):
        self._old = stage_b_classify._HEADING_CANONICALIZATION_PIPELINE
        stage_b_classify._HEADING_CANONICALIZATION_PIPELINE = self._new
        return self._new

    def __exit__(self, exc_type, exc_val, tb):
        stage_b_classify._HEADING_CANONICALIZATION_PIPELINE = self._old
        return False


class _ExplodingCanonicalizer(HeadingCanonicalizer):
    """Test double: always raises. Used to prove a canonicalizer
    failure can never abort Stage B (M4.3C error-isolation
    requirement)."""

    name = "exploding_canonicalizer"
    default_priority = 1  # runs first

    def canonicalize(self, heading: CanonicalHeading, context: CanonicalizationContext):
        raise RuntimeError("boom: simulated canonicalizer bug")


def _registry_with(*canonicalizers) -> CanonicalizerRegistry:
    reg = CanonicalizerRegistry()
    for c in canonicalizers:
        reg.register(c)
    return reg


# ---------------------------------------------------------------------------
# 1. Successful recognition -> canonicalization flow
# ---------------------------------------------------------------------------

class TestSuccessfulIntegration(unittest.TestCase):
    def test_arabic_numbered_heading_gets_canonical_metadata(self):
        b = _heading_block(numbering="3", title=None, level=1)
        block_type, confidence = classify(b)
        self.assertEqual(block_type, "Heading")
        self.assertEqual(confidence, 1.0)
        self.assertIn("heading_recognition", b.grouping_meta)  # M4.2C unaffected
        canon = b.grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["canonical_number"], "3")
        self.assertEqual(canon["numbering_system"], "arabic")

    def test_roman_numeral_heading_gets_canonical_metadata(self):
        b = _heading_block(numbering="III", title=None, level=1)
        classify(b)
        canon = b.grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["canonical_number"], "3")
        self.assertEqual(canon["numbering_system"], "roman")

    def test_hindi_chapter_heading_with_devanagari_numeral_gets_canonical_metadata(self):
        # HindiHeadingRecognizer (M4.2D) already converts its own matched
        # Devanagari numeral into an ASCII-digit RecognitionResult.number
        # (e.g. "३" -> "3") as part of its own, pre-existing, frozen M4.2
        # behaviour -- so end-to-end, what reaches M4.3B here is already
        # an Arabic-shaped numbering token, and NumberingSystemDetector
        # correctly reports "arabic". Direct Devanagari-digit-to-int
        # conversion (the "३" -> 3 case M4.3B itself is responsible for)
        # is covered directly in
        # test_m43b_number_system_canonicalization.py; this test only
        # confirms the full production chain does not crash and still
        # produces canonical metadata for a Hindi-recognized heading.
        b = _heading_block(numbering=None, title="अध्याय ३", level=1)
        classify(b)
        self.assertEqual(b.grouping_meta["heading_recognition"]["recognizer_name"], "hindi_heading")
        canon = b.grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["canonical_number"], "3")
        self.assertEqual(canon["numbering_system"], "arabic")

    def test_hierarchical_numbering_has_no_canonical_number_but_no_crash(self):
        # "1.1" is recognized (hierarchical) by M4.2 but isn't a bare
        # Roman/Arabic/Devanagari numeral M4.3B knows how to convert --
        # canonicalization metadata is still attached (validation_status/
        # numbering_system/diagnostics), just without a canonical_number.
        b = _heading_block(numbering="1.1", title=None, level=2)
        classify(b)
        self.assertIn("heading_recognition", b.grouping_meta)
        canon = b.grouping_meta["heading_canonicalization"]
        self.assertIsNone(canon["canonical_number"])
        self.assertEqual(canon["numbering_system"], "unknown")

    def test_classify_blocks_end_to_end_propagates_canonical_metadata(self):
        blocks = [
            _heading_block(numbering="I", title=None, level=1,
                            topic_id="t1", block_id="b1", y=50.0),
            _heading_block(numbering="3", title=None, level=1,
                            topic_id="t2", block_id="b2", y=150.0),
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        self.assertEqual(by_id["b1"].grouping_meta["heading_canonicalization"]["canonical_number"], "1")
        self.assertEqual(by_id["b1"].grouping_meta["heading_canonicalization"]["numbering_system"], "roman")
        self.assertEqual(by_id["b2"].grouping_meta["heading_canonicalization"]["canonical_number"], "3")
        self.assertEqual(by_id["b2"].grouping_meta["heading_canonicalization"]["numbering_system"], "arabic")


# ---------------------------------------------------------------------------
# 2. Registry / pipeline reuse
# ---------------------------------------------------------------------------

class TestRegistryReuse(unittest.TestCase):
    def test_module_level_pipeline_is_a_singleton(self):
        # No per-call rebuilding -- the same CanonicalizationPipeline
        # instance backs every classify() call (M4.3C performance
        # requirement: avoid rebuilding the registry/pipeline per
        # heading).
        pipeline_before = stage_b_classify._HEADING_CANONICALIZATION_PIPELINE
        _heading_block(numbering="3")
        classify(_heading_block(numbering="3", block_id="b-reuse"))
        self.assertIs(stage_b_classify._HEADING_CANONICALIZATION_PIPELINE, pipeline_before)

    def test_pipeline_uses_the_frameworks_own_default_registry(self):
        from modules.heading_canonicalization import default_registry as canonical_default_registry
        self.assertIs(
            stage_b_classify._HEADING_CANONICALIZATION_PIPELINE.registry,
            canonical_default_registry,
        )


# ---------------------------------------------------------------------------
# 3. Canonicalizer failures must not terminate the pipeline
# ---------------------------------------------------------------------------

class TestCanonicalizerFailureHandling(unittest.TestCase):
    def test_exploding_canonicalizer_does_not_crash_classify(self):
        broken_registry = _registry_with(_ExplodingCanonicalizer())
        with _SwapCanonicalizationPipeline(CanonicalizationPipeline(broken_registry)):
            b = _heading_block(numbering="3", title=None, level=1)
            block_type, confidence = classify(b)  # must not raise
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        # Recognition metadata (M4.2C) is completely unaffected by a
        # downstream canonicalizer bug.
        self.assertIn("heading_recognition", b.grouping_meta)
        # The only registered canonicalizer failed outright — no
        # numbering_system was ever detected, so no canonical_number
        # either, but this is still recorded via ordinary (empty-ish)
        # canonicalization metadata, not a crash.
        canon = b.grouping_meta["heading_canonicalization"]
        self.assertIsNone(canon["canonical_number"])

    def test_remaining_headings_still_canonicalized_after_a_failure(self):
        # A failing canonicalizer on one heading must not prevent a
        # LATER heading in the same classify_blocks() run from being
        # canonicalized normally.
        broken_registry = _registry_with(
            _ExplodingCanonicalizer(), NumberingSystemDetector(), ArabicNumeralCanonicalizer(),
        )
        with _SwapCanonicalizationPipeline(CanonicalizationPipeline(broken_registry)):
            blocks = [
                _heading_block(numbering="3", title=None, level=1,
                                block_id="b1", y=50.0),
                _heading_block(numbering="7", title=None, level=1,
                                block_id="b2", y=150.0),
            ]
            result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        self.assertEqual(by_id["b1"].grouping_meta["heading_canonicalization"]["canonical_number"], "3")
        self.assertEqual(by_id["b2"].grouping_meta["heading_canonicalization"]["canonical_number"], "7")

    def test_recognition_metadata_survives_even_when_canonicalization_disabled(self):
        original = config.ENABLE_HEADING_CANONICALIZATION
        config.ENABLE_HEADING_CANONICALIZATION = False
        try:
            b = _heading_block(numbering="3", title=None, level=1)
            classify(b)
        finally:
            config.ENABLE_HEADING_CANONICALIZATION = original
        self.assertIn("heading_recognition", b.grouping_meta)
        self.assertNotIn("heading_canonicalization", b.grouping_meta)


# ---------------------------------------------------------------------------
# 4. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility(unittest.TestCase):
    def test_existing_recognition_metadata_shape_is_unchanged(self):
        b = _heading_block(numbering="1.1", title="Motion", level=2)
        classify(b)
        meta = b.grouping_meta["heading_recognition"]
        # Exactly the same keys M4.2C's own tests assert on.
        self.assertEqual(
            set(meta.keys()),
            {"recognizer_name", "classification", "confidence", "level", "number", "diagnostics"},
        )

    def test_legacy_heading_block_without_title_or_numbering_unaffected(self):
        b = Block(block_id="b1", page=0, bbox=(50, 100, 400, 120), lines=[],
                   children=[], grouping_meta={"anchor": "heading-topic"})
        block_type, confidence = classify(b)
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        self.assertNotIn("heading_recognition", b.grouping_meta)
        self.assertNotIn("heading_canonicalization", b.grouping_meta)

    def test_non_heading_anchors_are_never_sent_to_the_framework(self):
        b = Block(block_id="b1", page=0, bbox=(0, 0, 10, 10), lines=[],
                   children=[], grouping_meta={"anchor": "table"})
        block_type, confidence = classify(b)
        self.assertNotIn("heading_canonicalization", b.grouping_meta)
        self.assertEqual(block_type, "Table")

    def test_no_recognition_match_means_no_canonicalization_attempt(self):
        # Nothing for M4.2 to recognize -> M4.3 is never invoked at all
        # (canonicalization only ever runs on a winning RecognitionResult).
        b = _heading_block(
            numbering=None,
            title="this is definitely not a title-cased heading at all really",
        )
        classify(b)
        self.assertNotIn("heading_recognition", b.grouping_meta)
        self.assertNotIn("heading_canonicalization", b.grouping_meta)

    def test_disabling_recognition_also_skips_canonicalization(self):
        original = config.ENABLE_HEADING_RECOGNITION
        config.ENABLE_HEADING_RECOGNITION = False
        try:
            b = _heading_block(numbering="3", title=None, level=1)
            block_type, confidence = classify(b)
        finally:
            config.ENABLE_HEADING_RECOGNITION = original
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        self.assertNotIn("heading_recognition", b.grouping_meta)
        self.assertNotIn("heading_canonicalization", b.grouping_meta)


# ---------------------------------------------------------------------------
# 5. Configuration-driven behaviour
# ---------------------------------------------------------------------------

class TestConfigurationDrivenBehaviour(unittest.TestCase):
    def test_feature_toggle_enabled_by_default(self):
        self.assertTrue(config.ENABLE_HEADING_CANONICALIZATION)

    def test_feature_toggle_off_skips_canonicalization_entirely(self):
        original = config.ENABLE_HEADING_CANONICALIZATION
        config.ENABLE_HEADING_CANONICALIZATION = False
        try:
            b = _heading_block(numbering="3", title=None, level=1)
            classify(b)
            self.assertIn("heading_recognition", b.grouping_meta)
            self.assertNotIn("heading_canonicalization", b.grouping_meta)
        finally:
            config.ENABLE_HEADING_CANONICALIZATION = original

    def test_custom_registry_settings_change_outcome(self):
        # Disabling the Roman canonicalizer via per-canonicalizer
        # settings (the framework's own configuration approach, not a
        # second one this integration invents) leaves numbering_system
        # detected but canonical_number unset for a Roman heading.
        from modules.heading_canonicalization.config import (
            CanonicalizerSettings,
            default_config,
        )
        cfg = default_config().with_canonicalizer_settings(
            CanonicalizerSettings(name="roman_numeral_canonicalizer", enabled=False)
        )
        registry = CanonicalizerRegistry(config=cfg)
        registry.register(NumberingSystemDetector())
        registry.register(RomanNumeralCanonicalizer())
        with _SwapCanonicalizationPipeline(CanonicalizationPipeline(registry)):
            b = _heading_block(numbering="III", title=None, level=1)
            classify(b)
        canon = b.grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["numbering_system"], "roman")
        self.assertIsNone(canon["canonical_number"])


# ---------------------------------------------------------------------------
# 6. Deterministic execution
# ---------------------------------------------------------------------------

class TestDeterministicExecution(unittest.TestCase):
    def test_repeated_classify_calls_produce_identical_canonical_metadata(self):
        results = []
        for _ in range(5):
            b = _heading_block(numbering="III", title=None, level=1)
            classify(b)
            results.append(b.grouping_meta["heading_canonicalization"])
        first = results[0]
        for r in results[1:]:
            self.assertEqual(r, first)

    def test_repeated_classify_blocks_runs_produce_identical_output(self):
        def build():
            return [
                _heading_block(numbering="I", title=None, level=1,
                                block_id="b1", y=50.0),
                _heading_block(numbering="3", title=None, level=1,
                                block_id="b2", y=150.0),
                _heading_block(numbering="३", title=None, level=1,
                                block_id="b3", y=250.0),
            ]
        run_1 = classify_blocks(build())
        run_2 = classify_blocks(build())
        for b1, b2 in zip(run_1, run_2):
            self.assertEqual(
                b1.grouping_meta.get("heading_canonicalization"),
                b2.grouping_meta.get("heading_canonicalization"),
            )


if __name__ == "__main__":
    unittest.main()
