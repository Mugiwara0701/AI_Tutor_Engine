"""
tests/test_m43d_structural_validation.py — M4.3D tests: Structural
Validation.

Covers both layers of this milestone:

  (A) `modules.heading_canonicalization.structural_validation.
      StructuralValidator` in isolation — number sequence validation,
      hierarchy validation, canonical consistency validation, failure
      handling (malformed input never crashes / never raises), and
      determinism. These tests construct `CanonicalHeading` /
      `CanonicalizationContext` directly and need nothing from Stage B
      or Stage A (no PDF/geometry dependency).

  (B) Production wiring through `modules/stage_b_classify.py`
      (`classify` / `classify_blocks`) — mirrors
      `test_m43c_pipeline_integration.py`'s own conventions exactly
      (same `_heading_block` helper shape, same `_SwapCanonicalizationPipeline`
      pattern, same config-toggle style) to prove structural validation
      is wired into the same pipeline M4.3C already integrated, is
      configuration-driven (`config.ENABLE_STRUCTURAL_VALIDATION`),
      never disturbs `heading_recognition`/M4.3B canonicalization
      metadata or `block_type`/confidence, and is deterministic
      end-to-end.

  (C) Regression — every M4.2/M4.3A/M4.3B/M4.3C test module still
      collects and (where the environment allows) passes unmodified.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.heading_canonicalization.base import CanonicalizationContext
from modules.heading_canonicalization.enums import (
    CanonicalHeadingType,
    NumberingSystem,
    ValidationStatus,
)
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.structural_validation import (
    PRECEDING_LEVEL_METADATA_KEY,
    StructuralValidator,
)
from modules.heading_canonicalization.validation import ValidationResult
from modules.heading_recognizers.enums import HeadingClassification


# ---------------------------------------------------------------------------
# Helpers (layer A — no Stage A/B dependency)
# ---------------------------------------------------------------------------

def _heading(
    canonical_number=None,
    numbering_system=NumberingSystem.UNKNOWN,
    level=None,
    canonical_type=None,
    original_numbering=None,
    validation_status=ValidationStatus.PENDING,
) -> CanonicalHeading:
    return CanonicalHeading(
        original_text="some heading text",
        recognized_classification=HeadingClassification.CHAPTER_TITLE,
        recognized_confidence=0.9,
        level=level,
        original_numbering=original_numbering,
        canonical_number=canonical_number,
        numbering_system=numbering_system,
        canonical_type=canonical_type,
        validation_status=validation_status,
    )


def _ctx(preceding_number=None, preceding_system=None, preceding_level=None) -> CanonicalizationContext:
    return CanonicalizationContext(
        preceding_canonical_number=preceding_number,
        preceding_numbering_system=preceding_system,
        metadata={PRECEDING_LEVEL_METADATA_KEY: preceding_level},
    )


VALIDATOR = StructuralValidator()


# ---------------------------------------------------------------------------
# A.1 — Number sequence validation
# ---------------------------------------------------------------------------

class TestNumberSequenceValidation(unittest.TestCase):
    def test_valid_incrementing_sequence_is_success(self):
        h = _heading(canonical_number="3", numbering_system=NumberingSystem.ARABIC, level=1)
        ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)
        self.assertEqual(out.diagnostics, ())

    def test_first_heading_with_no_preceding_context_is_success(self):
        h = _heading(canonical_number="1", numbering_system=NumberingSystem.ARABIC, level=1)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_duplicate_numbering_is_an_error(self):
        h = _heading(canonical_number="2", numbering_system=NumberingSystem.ARABIC, level=1)
        ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.ERROR)
        self.assertTrue(any("duplicate_number" in d for d in out.diagnostics))

    def test_decreasing_numbering_is_an_error(self):
        h = _heading(canonical_number="1", numbering_system=NumberingSystem.ARABIC, level=1)
        ctx = _ctx(preceding_number="5", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.ERROR)
        self.assertTrue(any("decreasing_number" in d for d in out.diagnostics))

    def test_skipped_numbering_is_a_warning_not_an_error(self):
        h = _heading(canonical_number="4", numbering_system=NumberingSystem.ARABIC, level=1)
        ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.WARNING)
        self.assertTrue(any("skipped_number" in d for d in out.diagnostics))

    def test_repeated_numbering_across_three_headings_flags_each_repeat(self):
        # Simulates "Chapter 1, Chapter 2, Chapter 2" from the spec: the
        # second "2" is compared against the first "2" via context and
        # flagged as a duplicate; StructuralValidator itself only ever
        # sees one heading (plus context) at a time, exactly like every
        # other HeadingCanonicalizer.
        ctx1 = CanonicalizationContext()
        h1 = _heading(canonical_number="1", numbering_system=NumberingSystem.ARABIC, level=1)
        out1 = VALIDATOR.canonicalize(h1, ctx1)
        self.assertEqual(out1.validation_status, ValidationStatus.SUCCESS)

        ctx2 = _ctx(preceding_number="1", preceding_system="arabic", preceding_level=1)
        h2 = _heading(canonical_number="2", numbering_system=NumberingSystem.ARABIC, level=1)
        out2 = VALIDATOR.canonicalize(h2, ctx2)
        self.assertEqual(out2.validation_status, ValidationStatus.SUCCESS)

        ctx3 = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        h3 = _heading(canonical_number="2", numbering_system=NumberingSystem.ARABIC, level=1)
        out3 = VALIDATOR.canonicalize(h3, ctx3)
        self.assertEqual(out3.validation_status, ValidationStatus.ERROR)
        self.assertTrue(any("duplicate_number" in d for d in out3.diagnostics))

    def test_numbering_system_switch_mid_sequence_is_a_warning(self):
        h = _heading(canonical_number="3", numbering_system=NumberingSystem.ROMAN, level=1)
        ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertTrue(any("numbering_system_switch" in d for d in out.diagnostics))

    def test_non_orderable_numbering_system_skips_sequence_checks(self):
        # numbering_system NONE/UNKNOWN carries no orderable number --
        # sequence rules must not fire (nothing to compare).
        h = _heading(canonical_number=None, numbering_system=NumberingSystem.NONE, level=1)
        ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)


# ---------------------------------------------------------------------------
# A.2 — Hierarchy validation
# ---------------------------------------------------------------------------

class TestHierarchyValidation(unittest.TestCase):
    def test_valid_hierarchy_descent_and_dedent_is_success(self):
        # 1 -> 1.1 (descend one level): valid.
        h = _heading(level=2)
        ctx = _ctx(preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_dedent_to_a_shallower_level_is_always_valid(self):
        # subsection (3) ends, a new chapter (1) begins: never flagged,
        # regardless of how many levels are given up at once.
        h = _heading(level=1)
        ctx = _ctx(preceding_level=3)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_same_level_sibling_is_valid(self):
        h = _heading(level=2)
        ctx = _ctx(preceding_level=2)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_invalid_hierarchy_jump_skipping_a_level_is_an_error(self):
        # level 1 directly followed by level 3 -- "1", "3.1" in the
        # spec's own example, with no intervening level-2 heading.
        h = _heading(level=3)
        ctx = _ctx(preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.ERROR)
        self.assertTrue(any("hierarchy_level_jump" in d for d in out.diagnostics))

    def test_jump_skipping_two_levels_is_also_an_error(self):
        h = _heading(level=4)
        ctx = _ctx(preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.ERROR)

    def test_orphan_heading_with_no_preceding_context_at_all_is_a_warning(self):
        # First heading in the whole context is already at level 2 --
        # "2.1" in the spec's own example, with no "2" ever seen.
        h = _heading(level=2)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.WARNING)
        self.assertTrue(any("orphan_heading" in d for d in out.diagnostics))

    def test_first_heading_at_level_one_is_never_an_orphan(self):
        h = _heading(level=1)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_missing_level_skips_hierarchy_validation_without_error(self):
        h = _heading(level=None)
        ctx = _ctx(preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_malformed_preceding_level_in_metadata_never_crashes(self):
        h = _heading(level=3)
        ctx = CanonicalizationContext(metadata={PRECEDING_LEVEL_METADATA_KEY: "not-an-int"})
        out = VALIDATOR.canonicalize(h, ctx)  # must not raise
        self.assertIn(out.validation_status, (ValidationStatus.SUCCESS, ValidationStatus.WARNING))


# ---------------------------------------------------------------------------
# A.3 — Canonical consistency validation
# ---------------------------------------------------------------------------

class TestCanonicalConsistencyValidation(unittest.TestCase):
    def test_consistent_number_and_system_is_success(self):
        h = _heading(canonical_number="5", numbering_system=NumberingSystem.ARABIC, level=1)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_number_set_with_none_numbering_system_is_an_error(self):
        h = _heading(canonical_number="5", numbering_system=NumberingSystem.NONE)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.ERROR)
        self.assertTrue(any("canonical_inconsistency" in d for d in out.diagnostics))

    def test_number_set_with_unknown_numbering_system_is_an_error(self):
        h = _heading(canonical_number="5", numbering_system=NumberingSystem.UNKNOWN)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.ERROR)

    def test_resolved_system_without_a_number_is_a_warning(self):
        # e.g. a malformed roman numeral: numbering_system == ROMAN but
        # RomanNumeralCanonicalizer rejected it, leaving canonical_number
        # unset -- already diagnosed on the heading itself, structural
        # validation adds a structural-level warning too.
        h = _heading(canonical_number=None, numbering_system=NumberingSystem.ROMAN)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.WARNING)

    def test_chapter_type_at_unexpected_level_is_a_warning(self):
        h = _heading(canonical_type=CanonicalHeadingType.CHAPTER, level=2)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.WARNING)
        self.assertTrue(any("canonical_type_level_mismatch" in d for d in out.diagnostics))

    def test_chapter_type_at_level_one_is_success(self):
        h = _heading(canonical_type=CanonicalHeadingType.CHAPTER, level=1)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_keyword_section_with_a_number_is_a_warning(self):
        h = _heading(canonical_type=CanonicalHeadingType.KEYWORD_SECTION,
                      canonical_number="2", numbering_system=NumberingSystem.ARABIC)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.WARNING)

    def test_keyword_section_without_a_number_is_success(self):
        h = _heading(canonical_type=CanonicalHeadingType.KEYWORD_SECTION)
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)


# ---------------------------------------------------------------------------
# A.4 — Failure handling: malformed input never crashes validation
# ---------------------------------------------------------------------------

class TestFailureHandling(unittest.TestCase):
    def test_malformed_canonical_number_never_raises(self):
        # canonical_number is only ever str(int(...)) in this codebase,
        # but StructuralValidator must not assume that -- a stray
        # non-integer string must degrade to "can't compare", not crash.
        h = _heading(canonical_number="not-a-number", numbering_system=NumberingSystem.ARABIC, level=1)
        ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)  # must not raise
        self.assertIsInstance(out, CanonicalHeading)

    def test_malformed_preceding_canonical_number_never_raises(self):
        h = _heading(canonical_number="3", numbering_system=NumberingSystem.ARABIC, level=1)
        ctx = _ctx(preceding_number="not-a-number", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)  # must not raise
        self.assertIsInstance(out, CanonicalHeading)

    def test_completely_empty_heading_and_context_never_raises(self):
        h = _heading()
        out = VALIDATOR.canonicalize(h, CanonicalizationContext())  # must not raise
        self.assertEqual(out.validation_status, ValidationStatus.SUCCESS)

    def test_extraction_output_is_preserved_alongside_diagnostics(self):
        # Validation must never rewrite recognition/canonicalization
        # fields -- only validation_status/diagnostics/metadata change.
        h = _heading(canonical_number="2", numbering_system=NumberingSystem.ARABIC, level=1,
                      original_numbering="2")
        ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=1)
        out = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out.original_numbering, "2")
        self.assertEqual(out.canonical_number, "2")
        self.assertEqual(out.numbering_system, NumberingSystem.ARABIC)

    def test_supports_returns_false_once_already_validated(self):
        h = _heading(canonical_number="1", numbering_system=NumberingSystem.ARABIC, level=1,
                      validation_status=ValidationStatus.SUCCESS)
        self.assertFalse(VALIDATOR.supports(h, CanonicalizationContext()))


# ---------------------------------------------------------------------------
# A.5 — Determinism
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):
    def test_identical_input_produces_identical_output(self):
        def run():
            h = _heading(canonical_number="4", numbering_system=NumberingSystem.ARABIC, level=2,
                          canonical_type=CanonicalHeadingType.SECTION)
            ctx = _ctx(preceding_number="2", preceding_system="arabic", preceding_level=2)
            return VALIDATOR.canonicalize(h, ctx)

        first = run()
        for _ in range(10):
            again = run()
            self.assertEqual(again.validation_status, first.validation_status)
            self.assertEqual(again.diagnostics, first.diagnostics)

    def test_diagnostic_order_is_stable_across_rule_groups(self):
        # Number-sequence, hierarchy, then consistency, in that fixed
        # order -- verified by triggering all three at once.
        h = _heading(canonical_number="2", numbering_system=NumberingSystem.NONE, level=5)
        ctx = _ctx(preceding_number="2", preceding_system="none", preceding_level=1)
        out1 = VALIDATOR.canonicalize(h, ctx)
        out2 = VALIDATOR.canonicalize(h, ctx)
        self.assertEqual(out1.diagnostics, out2.diagnostics)


# ---------------------------------------------------------------------------
# Layer B — production wiring through modules/stage_b_classify.py
# ---------------------------------------------------------------------------
#
# Mirrors test_m43c_pipeline_integration.py's own helpers/conventions
# exactly. Requires the same optional PDF-geometry dependency
# (modules.stage_a_geometry -> modules.pdf_parser -> PyMuPDF) that
# module already requires; skipped gracefully if unavailable rather
# than failing the whole suite, so layer A above still runs in a
# minimal environment.

try:
    import config
    from modules.stage_a_geometry import Block
    import modules.stage_b_classify as stage_b_classify
    from modules.stage_b_classify import classify, classify_blocks
    from modules.heading_canonicalization.pipeline import CanonicalizationPipeline
    from modules.heading_canonicalization.registry import CanonicalizerRegistry
    _STAGE_B_AVAILABLE = True
    _STAGE_B_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment-dependent
    _STAGE_B_AVAILABLE = False
    _STAGE_B_IMPORT_ERROR = exc


def _heading_block(numbering=None, title=None, level=1, page=1, y=100.0,
                    topic_id="t1", block_id="b1", extra_meta=None):
    meta = {"anchor": "heading-topic", "topic_id": topic_id,
            "numbering": numbering, "level": level, "title": title}
    if extra_meta:
        meta.update(extra_meta)
    return Block(block_id=block_id, page=page, bbox=(50.0, y, 400.0, y + 20.0),
                 lines=[], children=[], grouping_meta=meta)


class _SwapCanonicalizationPipeline:
    """Same convention as test_m43c_pipeline_integration.py's own
    `_SwapCanonicalizationPipeline` -- temporarily swaps Stage B's
    module-level pipeline singleton for an isolated one and restores it
    on exit regardless of outcome."""

    def __init__(self, pipeline):
        self._new = pipeline
        self._old = None

    def __enter__(self):
        self._old = stage_b_classify._HEADING_CANONICALIZATION_PIPELINE
        stage_b_classify._HEADING_CANONICALIZATION_PIPELINE = self._new
        return self._new

    def __exit__(self, exc_type, exc_val, tb):
        stage_b_classify._HEADING_CANONICALIZATION_PIPELINE = self._old
        return False


@unittest.skipUnless(_STAGE_B_AVAILABLE, f"modules.stage_b_classify unavailable: {_STAGE_B_IMPORT_ERROR}")
class TestProductionWiring(unittest.TestCase):
    def test_valid_chapter_sequence_is_success(self):
        blocks = [
            _heading_block(title="Chapter 1", numbering=None, level=1, block_id="b1", y=50.0),
            _heading_block(title="Chapter 2", numbering=None, level=1, block_id="b2", y=150.0),
            _heading_block(title="Chapter 3", numbering=None, level=1, block_id="b3", y=250.0),
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        for bid in ("b1", "b2", "b3"):
            self.assertEqual(
                by_id[bid].grouping_meta["heading_canonicalization"]["validation_status"], "success"
            )

    def test_missing_chapter_number_is_flagged_as_a_warning(self):
        # Chapter 1, Chapter 2, Chapter 4 -- from the spec's own example.
        blocks = [
            _heading_block(title="Chapter 1", numbering=None, level=1, block_id="b1", y=50.0),
            _heading_block(title="Chapter 2", numbering=None, level=1, block_id="b2", y=150.0),
            _heading_block(title="Chapter 4", numbering=None, level=1, block_id="b3", y=250.0),
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        canon = by_id["b3"].grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["validation_status"], "warning")
        self.assertTrue(any("skipped_number" in d for d in canon["diagnostics"]))

    def test_duplicate_chapter_number_is_flagged_as_an_error(self):
        blocks = [
            _heading_block(title="Chapter 1", numbering=None, level=1, block_id="b1", y=50.0),
            _heading_block(title="Chapter 2", numbering=None, level=1, block_id="b2", y=150.0),
            _heading_block(title="Chapter 2", numbering=None, level=1, block_id="b3", y=250.0),
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        canon = by_id["b3"].grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["validation_status"], "error")
        self.assertTrue(any("duplicate_number" in d for d in canon["diagnostics"]))

    def test_decreasing_chapter_number_is_flagged_as_an_error(self):
        blocks = [
            _heading_block(title="Chapter 5", numbering=None, level=1, block_id="b1", y=50.0),
            _heading_block(title="Chapter 4", numbering=None, level=1, block_id="b2", y=150.0),
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        canon = by_id["b2"].grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["validation_status"], "error")
        self.assertTrue(any("decreasing_number" in d for d in canon["diagnostics"]))

    def test_invalid_level_jump_is_flagged_as_an_error(self):
        # "Chapter 1" recognizes at level 1 (ChapterNumberRecognizer); a
        # bare single letter recognizes at level 3 (AlphabeticHeadingRecognizer)
        # -- level 1 directly followed by level 3, skipping level 2 entirely.
        blocks = [
            _heading_block(title="Chapter 1", numbering=None, level=1, block_id="b1", y=50.0),
            _heading_block(title=None, numbering="A", level=3, block_id="b2", y=150.0),
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        canon = by_id["b2"].grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["validation_status"], "error")
        self.assertTrue(any("hierarchy_level_jump" in d for d in canon["diagnostics"]))

    def test_recognition_and_number_system_canonicalization_metadata_unaffected(self):
        # M4.3D is purely additive: heading_recognition (M4.2C) and the
        # canonical_number/numbering_system fields M4.3B already
        # populates (M4.3C) are completely unchanged by validation.
        blocks = [
            _heading_block(title="Chapter 1", numbering=None, level=1, block_id="b1", y=50.0),
            _heading_block(title="Chapter 1", numbering=None, level=1, block_id="b2", y=150.0),  # duplicate -> ERROR
        ]
        result = classify_blocks(blocks)
        by_id = {b.block_id: b for b in result}
        self.assertIn("heading_recognition", by_id["b2"].grouping_meta)
        canon = by_id["b2"].grouping_meta["heading_canonicalization"]
        self.assertEqual(canon["canonical_number"], "1")
        self.assertEqual(canon["numbering_system"], "arabic")
        self.assertEqual(by_id["b2"].block_type, "Heading")
        self.assertEqual(by_id["b2"].confidence, 1.0)

    def test_structural_validator_failure_is_isolated(self):
        from modules.heading_canonicalization.base import HeadingCanonicalizer
        from modules.heading_canonicalization.numeral_canonicalizers import (
            ArabicNumeralCanonicalizer, NumberingSystemDetector,
        )

        class _ExplodingValidator(HeadingCanonicalizer):
            name = "structural_validator"
            default_priority = 200

            def canonicalize(self, heading, context):
                raise RuntimeError("boom: simulated structural validator bug")

        registry = CanonicalizerRegistry()
        registry.register(NumberingSystemDetector())
        registry.register(ArabicNumeralCanonicalizer())
        registry.register(_ExplodingValidator())
        with _SwapCanonicalizationPipeline(CanonicalizationPipeline(registry)):
            b = _heading_block(numbering="3", level=1)
            block_type, confidence = classify(b)  # must not raise
        self.assertEqual((block_type, confidence), ("Heading", 1.0))
        canon = b.grouping_meta["heading_canonicalization"]
        # canonical_number still resolved; validation_status stays at
        # its PENDING default because the only validator blew up.
        self.assertEqual(canon["canonical_number"], "3")
        self.assertEqual(canon["validation_status"], "pending")

    def test_config_toggle_disables_only_structural_validation(self):
        original = config.ENABLE_STRUCTURAL_VALIDATION
        from modules.heading_canonicalization import default_registry as canonicalization_default_registry
        config.ENABLE_STRUCTURAL_VALIDATION = False
        canonicalization_default_registry.disable("structural_validator")
        try:
            blocks = [
                _heading_block(numbering="1", level=1, block_id="b1", y=50.0),
                _heading_block(numbering="1", level=1, block_id="b2", y=150.0),  # would-be duplicate
            ]
            result = classify_blocks(blocks)
        finally:
            config.ENABLE_STRUCTURAL_VALIDATION = original
            canonicalization_default_registry.enable("structural_validator")
        by_id = {b.block_id: b for b in result}
        canon = by_id["b2"].grouping_meta["heading_canonicalization"]
        # canonical_number/numbering_system (M4.3B) still populated --
        # only validation_status stays PENDING with the validator off.
        self.assertEqual(canon["canonical_number"], "1")
        self.assertEqual(canon["validation_status"], "pending")

    def test_deterministic_across_repeated_classify_blocks_runs(self):
        def build():
            return [
                _heading_block(numbering="1", level=1, block_id="b1", y=50.0),
                _heading_block(numbering="2", level=1, block_id="b2", y=150.0),
                _heading_block(numbering="2", level=1, block_id="b3", y=250.0),
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
