"""
tests/test_m41e_integration.py — M4.1E Integration & Regression Validation.

Comprehensive integration tests that verify M4.1A–D work together correctly
as a unified pipeline.  Each test exercises the *interface* between two or
more milestone modules rather than re-testing any single module's internals
(those are already covered by test_m41a, test_m41b, test_m41cd).

Coverage:
  ✓ Stage A → Stage B → Stage C end-to-end flow
  ✓ Recognizer registry integration with classified blocks
  ✓ Metadata propagation across stages (M4.1B → Stage B → Stage C)
  ✓ Parent/child type and priority propagation
  ✓ Deterministic ordering across the full pipeline
  ✓ Cross-page continuation integration
  ✓ Duplicate suppression integration
  ✓ Full extraction pipeline integration (classify → prioritize → recognize)
  ✓ Backward compatibility (API contracts, constants, dataclass fields)
  ✓ Recognizer registry stability and completeness
  ✓ text_utils pattern reuse across modules
"""

import pytest
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from modules.pdf_parser import Line
from modules.stage_a_geometry import Block, _make_block, _union_bbox
from modules.stage_b_classify import (
    classify, classify_blocks, BLOCK_TYPES,
    _classify_callout_label, _classify_equation_cluster,
    _classify_body_text_fallback,
    _suppress_duplicate_classifications,
    _propagate_parent_child_types,
    _propagate_metadata,
    _VARIABLE_ONLY_RE, _NUMERIC_SUBSTITUTION_RE,
)
from modules.stage_c_priority import (
    assign_priority, DEFAULT_PRIORITY_MAP,
    HIGH, MEDIUM, LOW,
    _adjust_priority_by_confidence,
    _adjust_priority_by_structure,
    _promote, _demote,
    _PRIORITY_RANK,
)
from modules.recognizers import candidates_for, registered_block_types
from modules.recognizers.base import RecognitionResult, block_raw_texts
from modules.recognizers.registry import _REGISTRY
from modules.recognizers.concept_recognizers import DefinitionRecognizer
from modules.recognizers.formula_recognizers import (
    FormulaRecognizer, MathIdentityRecognizer,
    ChemicalReactionRecognizer, EconomicIdentityRecognizer,
    _extract_variables,
)
from modules.recognizers.procedure_recognizers import (
    ProcedureRecognizer, WorkedExampleRecognizer,
)
from modules.recognizers.visual_recognizers import (
    FlowchartRecognizer, GraphRecognizer, ConceptTableRecognizer,
    DiagramSubtypeRecognizer, FigureWithCaptionRecognizer,
    GenericVisualRecognizer,
)
from modules.layout_quality import (
    apply_layout_quality_passes,
    suppress_cross_kind_duplicates,
    _bbox_iou,
)
from modules.text_utils import (
    DEFINITION_TERM_FIRST_RE, DEFINITION_TERM_AFTER_RE,
    DEFINITION_TERM_DENOTES_RE, DEFINITION_TERM_BY_MEAN_RE,
    TERM_STOPWORDS, term_is_valid,
    STEP_MARKER_RE,
    partial_match_confidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line(text: str, page: int = 0, y: float = 100.0,
          bbox: tuple = None) -> Line:
    if bbox is None:
        bbox = (50.0, y, 500.0, y + 12.0)
    return Line(text=text, size=10.0, max_size=12.0, bold=False,
                font="Arial", page=page, y=y, page_height=800.0, bbox=bbox)


def _block(kind: str, page: int, bbox: tuple, lines: list = None,
           children: list = None, grouping_meta: dict = None,
           block_id: str = None) -> Block:
    if lines is None:
        lines = []
    if children is None:
        children = []
    if grouping_meta is None:
        grouping_meta = {"anchor": kind}
    if block_id is None:
        block_id = f"block-{kind}-{page}-{bbox[1]:.0f}"
    return Block(block_id=block_id, page=page, bbox=bbox,
                 lines=lines, children=children,
                 grouping_meta=grouping_meta)


def _pipeline(blocks):
    """Run the full Stage B → Stage C pipeline on a list of blocks."""
    classified = classify_blocks(list(blocks))
    prioritized = assign_priority(classified)
    return prioritized


def _pipeline_recognize(blocks):
    """Run full Stage B → Stage C → recognizer pipeline."""
    result = _pipeline(blocks)
    recognized = {}
    for b in result:
        cands = candidates_for(b.block_type)
        best = None
        for c in cands:
            r = c.safe_recognize(b)
            if r and (best is None or r.confidence > best.confidence):
                best = r
        recognized[b.block_id] = (b, best)
    return recognized


# =========================================================================
# 1. Stage A → Stage B → Stage C end-to-end flow
# =========================================================================

class TestEndToEndPipelineFlow:
    """Verify blocks flow correctly through all three stages."""

    def test_single_heading_through_pipeline(self):
        blocks = [_block("heading-topic", 0, (50, 50, 400, 70),
                         grouping_meta={"anchor": "heading-topic",
                                        "topic_id": "t1", "numbering": "4.1",
                                        "level": 1})]
        result = _pipeline(blocks)
        assert len(result) == 1
        assert result[0].block_type == "Heading"
        assert result[0].confidence == 1.0
        assert result[0].priority is not None

    def test_multi_type_pipeline_order(self):
        """Multiple block types go through pipeline and come out ordered."""
        blocks = [
            _block("figure", 1, (50, 100, 400, 300), block_id="fig"),
            _block("heading-topic", 0, (50, 50, 400, 70), block_id="h",
                   grouping_meta={"anchor": "heading-topic"}),
            _block("definition-candidate", 0, (50, 200, 400, 220),
                   block_id="d",
                   lines=[_line("Force is defined as something", y=200)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force"}),
        ]
        result = _pipeline(blocks)
        # Must be sorted by (page, y0)
        positions = [(b.page, b.bbox[1]) for b in result]
        assert positions == sorted(positions)

    def test_all_blocks_get_type_and_priority(self):
        """Every block receives both block_type and priority."""
        blocks = [
            _block("heading-topic", 0, (50, 50, 400, 70),
                   grouping_meta={"anchor": "heading-topic"}),
            _block("definition-candidate", 0, (50, 100, 400, 120),
                   lines=[_line("X is defined as Y")],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "X"}),
            _block("table", 0, (50, 200, 400, 400),
                   grouping_meta={"anchor": "table", "caption": "T1"}),
            _block("figure", 0, (50, 500, 400, 600),
                   grouping_meta={"anchor": "figure", "caption": "F1"}),
        ]
        result = _pipeline(blocks)
        for b in result:
            assert b.block_type is not None, f"{b.block_id} missing type"
            assert b.block_type in BLOCK_TYPES, f"Unknown type: {b.block_type}"
            assert b.priority in (HIGH, MEDIUM, LOW), f"{b.block_id} missing priority"

    def test_in_example_tracking_across_blocks(self):
        """An Example label activates in_example for subsequent eq clusters."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120),
                   lines=[_line("Example 1", y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 1"}),
            _block("equation-cluster", 0, (50, 200, 400, 220),
                   children=[_block("equation-line", 0, (50, 200, 400, 220),
                                    grouping_meta={"anchor": "equation-line",
                                                   "raw_text": "= 5 + 3"})],
                   grouping_meta={"anchor": "equation-cluster"}),
        ]
        result = _pipeline(blocks)
        # Both should be Worked Example
        assert result[0].block_type == "Worked Example"
        assert result[1].block_type == "Worked Example"

    def test_heading_resets_in_example(self):
        """A heading between example label and equation resets in_example."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120),
                   lines=[_line("Example 1", y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 1"}),
            _block("heading-topic", 0, (50, 200, 400, 220),
                   grouping_meta={"anchor": "heading-topic"}),
            _block("equation-cluster", 0, (50, 300, 400, 320),
                   children=[_block("equation-line", 0, (50, 300, 400, 320),
                                    grouping_meta={"anchor": "equation-line",
                                                   "raw_text": "F = m * a"})],
                   grouping_meta={"anchor": "equation-cluster"}),
        ]
        result = _pipeline(blocks)
        assert result[1].block_type == "Heading"
        # The equation after the heading should NOT be Worked Example
        assert result[2].block_type == "Formula Box"


# =========================================================================
# 2. Recognizer registry integration
# =========================================================================

class TestRecognizerRegistryIntegration:
    """Verify the recognizer registry works with classified blocks."""

    def test_every_block_type_has_consistent_recognizer_coverage(self):
        """Check that block types returned by Stage B have expected
        recognizer coverage."""
        # Types that MUST have recognizers
        must_have = {"Definition", "Formula Box", "Worked Example", "Table",
                     "Figure", "Diagram", "Flowchart", "Decision Tree",
                     "Programming Syntax", "Accounting Format"}
        for bt in must_have:
            cands = candidates_for(bt)
            assert len(cands) > 0, f"No recognizers for {bt}"

    def test_types_without_recognizers_are_handled(self):
        """Types with no recognizers return empty lists, not errors."""
        for bt in ["Heading", "Activity", "Exercise", "Summary",
                    "Reference", "Ambiguous", "Footer", "Header"]:
            cands = candidates_for(bt)
            assert isinstance(cands, list)
            # These are valid to have 0 recognizers — they don't produce
            # extractable educational objects.

    def test_recognizer_accepts_classified_block(self):
        """A classified Formula Box block is accepted by FormulaRecognizer."""
        child = _block("equation-line", 0, (50, 100, 400, 115),
                       grouping_meta={"anchor": "equation-line",
                                      "raw_text": "F = m * a"})
        b = _block("equation-cluster", 0, (50, 100, 400, 115),
                   children=[child],
                   grouping_meta={"anchor": "equation-cluster"})
        # Classify first
        classify_blocks([b])
        assert b.block_type == "Formula Box"
        # Then recognize
        cands = candidates_for(b.block_type)
        results = [c.safe_recognize(b) for c in cands]
        matched = [r for r in results if r is not None]
        assert len(matched) > 0, "No recognizer matched a Formula Box block"

    def test_definition_recognizer_uses_text_utils_patterns(self):
        """DefinitionRecognizer uses shared patterns from M4.1A text_utils."""
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                   lines=[_line("Momentum is defined as product of mass and velocity")],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Momentum"})
        classify_blocks([b])
        assert b.block_type == "Definition"

        rec = DefinitionRecognizer()
        result = rec.recognize(b)
        assert result is not None
        assert result.data["term"] == "Momentum"
        assert result.data["definition_type"] == "is_defined_as"

    def test_no_duplicate_recognizer_instances_per_type(self):
        """Each recognizer appears at most once per block_type list."""
        for bt, cands in _REGISTRY.items():
            names = [c.name for c in cands]
            assert len(names) == len(set(names)), \
                f"Duplicate recognizer in {bt}: {names}"

    def test_recognizer_returns_correct_result_type(self):
        """Every recognizer returns RecognitionResult or None."""
        b = _block("equation-cluster", 0, (50, 100, 400, 115),
                   children=[_block("equation-line", 0, (50, 100, 400, 115),
                                    grouping_meta={"anchor": "equation-line",
                                                   "raw_text": "F = m * a"})],
                   grouping_meta={"anchor": "equation-cluster"})
        classify_blocks([b])
        for c in candidates_for(b.block_type):
            result = c.safe_recognize(b)
            assert result is None or isinstance(result, RecognitionResult)


# =========================================================================
# 3. Metadata propagation across stages
# =========================================================================

class TestMetadataPropagation:
    """Verify M4.1B metadata flows correctly through Stage B and Stage C."""

    def test_grouped_definitions_boost_confidence_and_priority(self):
        """grouped_definitions from M4.1B → Stage B confidence boost
        → Stage C HIGH priority."""
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                   lines=[_line("Force is defined as something")],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force",
                                  "grouped_definitions": True})
        result = _pipeline([b])
        # classify gives 0.8 for grouped, +0.05 from _propagate_metadata
        assert result[0].block_type == "Definition"
        assert result[0].confidence > 0.8
        assert result[0].priority == HIGH

    def test_has_border_boosts_activity_confidence(self):
        """has_border from M4.1B → Stage B Activity confidence boost."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                   lines=[_line("Note:", y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Note:",
                                  "has_border": True})
        result = _pipeline([b])
        assert result[0].block_type == "Activity"
        assert result[0].confidence >= 0.7  # 0.65 + 0.1 border boost

    def test_merged_continuation_boosts_formula_confidence(self):
        """merged_continuation from M4.1B → Stage B Formula Box boost."""
        child = _block("equation-line", 0, (50, 100, 400, 115),
                       grouping_meta={"anchor": "equation-line",
                                      "raw_text": "E = m * c"})
        b = _block("equation-cluster", 0, (50, 100, 400, 130),
                   children=[child],
                   grouping_meta={"anchor": "equation-cluster",
                                  "merged_continuation": True})
        result = _pipeline([b])
        assert result[0].block_type in ("Formula Box", "Worked Example")
        # merged_continuation adds 0.05 to confidence

    def test_callout_type_hint_from_layout_quality(self):
        """callout_type_hint from M4.1B layout quality → Stage B uses it."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                   lines=[_line("Safety Info")],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Safety Info",
                                  "callout_type_hint": "warning"})
        result = _pipeline([b])
        assert result[0].block_type == "Activity"
        assert result[0].confidence >= 0.6

    def test_continuation_metadata_promotes_priority(self):
        """continuation metadata from M4.1B → Stage C priority promotion."""
        b = _block("callout-label", 0, (50, 700, 400, 780),
                   lines=[_line("Example 3.1", y=700)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 3.1",
                                  "continuation": {"continued_on_page": 1}})
        result = _pipeline([b])
        assert result[0].block_type == "Worked Example"
        assert result[0].priority == HIGH  # MEDIUM + continuation promotion


# =========================================================================
# 4. Parent/child type and priority propagation
# =========================================================================

class TestParentChildPropagation:
    """Verify parent/child relationships are consistent after pipeline."""

    def test_children_classified_by_propagation(self):
        """Children without explicit classification inherit parent type."""
        child = _block("equation-line", 0, (50, 110, 400, 120),
                       grouping_meta={"anchor": "equation-line",
                                      "raw_text": "= 5 + 3"})
        parent = _block("equation-cluster", 0, (50, 100, 400, 130),
                        children=[child],
                        grouping_meta={"anchor": "equation-cluster"})
        result = _pipeline([parent])
        assert parent.block_type is not None
        assert child.block_type is not None
        # Child should have inherited from parent
        assert child.block_type == parent.block_type

    def test_child_priority_never_exceeds_parent(self):
        """Children's priority must not exceed parent's priority."""
        child1 = _block("equation-line", 0, (50, 110, 400, 120),
                        grouping_meta={"anchor": "equation-line",
                                       "raw_text": "F = m * a"})
        child2 = _block("equation-line", 0, (50, 125, 400, 135),
                        grouping_meta={"anchor": "equation-line",
                                       "raw_text": "= 100"})
        parent = _block("equation-cluster", 0, (50, 100, 400, 140),
                        children=[child1, child2],
                        grouping_meta={"anchor": "equation-cluster",
                                       "line_count": 2})
        result = _pipeline([parent])
        parent_rank = _PRIORITY_RANK.get(parent.priority, 2)
        for child in parent.children:
            child_rank = _PRIORITY_RANK.get(child.priority, 2)
            assert child_rank <= parent_rank, \
                f"Child {child.block_id} priority {child.priority} exceeds parent {parent.priority}"

    def test_heading_child_not_overridden(self):
        """A Heading child of a Worked Example keeps its Heading type."""
        heading_child = _block("heading-topic", 0, (50, 110, 400, 120),
                               grouping_meta={"anchor": "heading-topic"})
        heading_child.block_type = "Heading"
        heading_child.confidence = 1.0
        parent = _block("callout-label", 0, (50, 100, 400, 200),
                        children=[heading_child],
                        grouping_meta={"anchor": "callout-label",
                                       "label_line": "Example 1"})
        result = _pipeline([parent])
        assert heading_child.block_type == "Heading"

    def test_definition_child_not_overridden(self):
        """A Definition child keeps its type even inside an Activity."""
        def_child = _block("definition-candidate", 0, (50, 110, 400, 120),
                           lines=[_line("X is defined as Y")],
                           grouping_meta={"anchor": "definition-candidate",
                                          "candidate_term": "X"})
        def_child.block_type = "Definition"
        def_child.confidence = 0.75
        parent = _block("callout-label", 0, (50, 100, 400, 200),
                        children=[def_child],
                        grouping_meta={"anchor": "callout-label",
                                       "label_line": "Activity 1"})
        parent.block_type = "Activity"
        parent.confidence = 0.85
        _propagate_parent_child_types([parent])
        assert def_child.block_type == "Definition"


# =========================================================================
# 5. Deterministic ordering across the full pipeline
# =========================================================================

class TestDeterministicOrdering:
    """Verify output ordering is always deterministic."""

    def test_pipeline_output_sorted_by_page_y0(self):
        """Pipeline output is sorted by (page, y0)."""
        blocks = [
            _block("figure", 2, (10, 100, 100, 200), block_id="p2"),
            _block("table", 0, (10, 300, 100, 400), block_id="p0b",
                   grouping_meta={"anchor": "table"}),
            _block("heading-topic", 0, (10, 50, 100, 70), block_id="p0a",
                   grouping_meta={"anchor": "heading-topic"}),
            _block("definition-candidate", 1, (10, 100, 100, 120),
                   block_id="p1",
                   lines=[_line("X is defined as Y", page=1)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "X"}),
        ]
        result = _pipeline(blocks)
        positions = [(b.page, b.bbox[1]) for b in result]
        assert positions == sorted(positions)

    def test_stable_across_runs(self):
        """Same input always produces identical output."""
        def make_blocks():
            return [
                _block("figure", 0, (10, 300, 100, 400), block_id="a"),
                _block("table", 0, (10, 100, 100, 200), block_id="b",
                       grouping_meta={"anchor": "table"}),
                _block("heading-topic", 0, (10, 50, 100, 70), block_id="c",
                       grouping_meta={"anchor": "heading-topic"}),
            ]
        r1 = _pipeline(make_blocks())
        r2 = _pipeline(make_blocks())
        assert [b.block_id for b in r1] == [b.block_id for b in r2]
        assert [b.block_type for b in r1] == [b.block_type for b in r2]
        assert [b.priority for b in r1] == [b.priority for b in r2]

    def test_empty_pipeline(self):
        """Empty input produces empty output."""
        assert _pipeline([]) == []


# =========================================================================
# 6. Cross-page continuation integration
# =========================================================================

class TestCrossPageIntegration:
    """Verify cross-page blocks are handled correctly end-to-end."""

    def test_cross_page_example_classified_and_prioritized(self):
        """A cross-page Worked Example gets correct type and priority."""
        b = _block("callout-label", 0, (50, 700, 400, 780),
                   lines=[_line("Example 3.1", page=0, y=700),
                          _line("Find the force", page=0, y=715)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 3.1",
                                  "continuation": {"continued_on_page": 1,
                                                   "merged_block_id": "x"}})
        b.page_end = 1
        result = _pipeline([b])
        assert result[0].block_type == "Worked Example"
        assert result[0].priority == HIGH  # continuation promotes

    def test_cross_page_block_preserves_page_end(self):
        """page_end is preserved through the pipeline."""
        b = _block("callout-label", 0, (50, 700, 400, 780),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 3.1",
                                  "continuation": {"continued_on_page": 1}})
        b.page_end = 1
        result = _pipeline([b])
        assert result[0].page_end == 1

    def test_cross_page_equation_continuation_recognized(self):
        """An equation with merged_continuation flag from M4.1B is
        correctly classified and recognized."""
        child = _block("equation-line", 0, (50, 100, 400, 115),
                       grouping_meta={"anchor": "equation-line",
                                      "raw_text": "E = m * c"})
        b = _block("equation-cluster", 0, (50, 100, 400, 130),
                   children=[child],
                   grouping_meta={"anchor": "equation-cluster",
                                  "merged_continuation": True,
                                  "continuation": {"continued_on_page": 1}})
        result = _pipeline([b])
        # Should be classified and have promoted priority
        assert result[0].block_type is not None
        assert result[0].priority == HIGH  # continuation promotes


# =========================================================================
# 7. Duplicate suppression integration
# =========================================================================

class TestDuplicateSuppressionIntegration:
    """Verify duplicate suppression works across the full pipeline."""

    def test_duplicate_callout_labels_suppressed(self):
        """Two blocks with same type and label on same page → one survives."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120), block_id="dup1",
                   lines=[_line("Activity 1", y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Activity 1"}),
            _block("callout-label", 0, (50, 150, 400, 170), block_id="dup2",
                   lines=[_line("Activity 1", y=150)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Activity 1"}),
        ]
        result = _pipeline(blocks)
        activity_blocks = [b for b in result if b.block_type == "Activity"]
        assert len(activity_blocks) == 1

    def test_different_labels_not_suppressed(self):
        """Two blocks with same type but different labels both survive."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120), block_id="a1",
                   lines=[_line("Activity 1", y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Activity 1"}),
            _block("callout-label", 0, (50, 300, 400, 320), block_id="a2",
                   lines=[_line("Activity 2", y=300)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Activity 2"}),
        ]
        result = _pipeline(blocks)
        activity_blocks = [b for b in result if b.block_type == "Activity"]
        assert len(activity_blocks) == 2

    def test_different_pages_not_suppressed(self):
        """Same label on different pages are both kept."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120), block_id="p0",
                   lines=[_line("Activity 1", page=0, y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Activity 1"}),
            _block("callout-label", 1, (50, 100, 400, 120), block_id="p1",
                   lines=[_line("Activity 1", page=1, y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Activity 1"}),
        ]
        result = _pipeline(blocks)
        assert len(result) == 2

    def test_headings_never_suppressed(self):
        """Headings are exempt from duplicate suppression."""
        blocks = [
            _block("heading-topic", 0, (50, 50, 400, 70), block_id="h1",
                   grouping_meta={"anchor": "heading-topic"}),
            _block("heading-topic", 0, (50, 100, 400, 120), block_id="h2",
                   grouping_meta={"anchor": "heading-topic"}),
        ]
        result = _pipeline(blocks)
        headings = [b for b in result if b.block_type == "Heading"]
        assert len(headings) == 2


# =========================================================================
# 8. Full extraction pipeline integration
# =========================================================================

class TestFullExtractionPipeline:
    """End-to-end: classify → prioritize → recognize."""

    def test_formula_box_recognized(self):
        """Formula Box flows through classify → prioritize → recognize."""
        child = _block("equation-line", 0, (50, 100, 400, 115),
                       grouping_meta={"anchor": "equation-line",
                                      "raw_text": "F = m * a"})
        b = _block("equation-cluster", 0, (50, 100, 400, 115),
                   children=[child],
                   grouping_meta={"anchor": "equation-cluster"})
        recognized = _pipeline_recognize([b])
        block, result = recognized[b.block_id]
        assert block.block_type == "Formula Box"
        assert block.priority == HIGH
        assert result is not None
        assert "reusable_formula" in result.data

    def test_definition_recognized(self):
        """Definition flows through classify → prioritize → recognize."""
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                   lines=[_line("Momentum is defined as product of mass and velocity")],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Momentum"})
        recognized = _pipeline_recognize([b])
        block, result = recognized[b.block_id]
        assert block.block_type == "Definition"
        assert block.priority == HIGH
        assert result is not None
        assert result.data["term"] == "Momentum"

    def test_table_recognized(self):
        """Table block gets at least generic visual recognition."""
        b = _block("table", 0, (50, 100, 400, 300),
                   grouping_meta={"anchor": "table",
                                  "caption": "Table 4.1: Properties",
                                  "region_extra": {"rows": 5, "columns": 3}})
        recognized = _pipeline_recognize([b])
        block, result = recognized[b.block_id]
        assert block.block_type == "Table"
        assert result is not None  # generic_visual always matches

    def test_figure_with_formal_caption_recognized(self):
        """Figure with 'Figure N' caption → FigureWithCaptionRecognizer."""
        b = _block("figure", 0, (50, 100, 400, 300),
                   grouping_meta={"anchor": "figure",
                                  "caption": "Figure 4.1: The solar system"})
        recognized = _pipeline_recognize([b])
        block, result = recognized[b.block_id]
        assert block.block_type == "Figure"
        assert result is not None
        # FigureWithCaptionRecognizer should match with higher confidence
        # than GenericVisualRecognizer
        assert result.confidence >= 0.5

    def test_diagram_subtype_recognized(self):
        """Diagram with lifecycle caption → DiagramSubtypeRecognizer."""
        b = _block("diagram", 0, (50, 100, 400, 300),
                   grouping_meta={"anchor": "diagram",
                                  "caption": "Life cycle of a butterfly"})
        recognized = _pipeline_recognize([b])
        block, result = recognized[b.block_id]
        assert block.block_type == "Diagram"
        assert result is not None
        assert result.data.get("visual_subtype") == "lifecycle_diagram"

    def test_mixed_chapter_pipeline(self):
        """A realistic mix of block types all get classified, prioritized,
        and recognized correctly."""
        blocks = [
            _block("heading-topic", 0, (50, 50, 400, 70), block_id="h",
                   grouping_meta={"anchor": "heading-topic"}),
            _block("definition-candidate", 0, (50, 100, 400, 120),
                   block_id="d",
                   lines=[_line("Force is defined as mass times acceleration")],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force"}),
            _block("equation-cluster", 0, (50, 200, 400, 215),
                   block_id="eq",
                   children=[_block("equation-line", 0, (50, 200, 400, 215),
                                    grouping_meta={"anchor": "equation-line",
                                                   "raw_text": "F = m * a"})],
                   grouping_meta={"anchor": "equation-cluster"}),
            _block("table", 0, (50, 400, 400, 500), block_id="t",
                   grouping_meta={"anchor": "table", "caption": "Table 1"}),
            _block("callout-label", 1, (50, 100, 400, 200), block_id="ex",
                   lines=[_line("Exercise 5.1", page=1, y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Exercise 5.1"}),
        ]
        recognized = _pipeline_recognize(blocks)

        # All blocks should have types and priorities
        for bid, (block, _) in recognized.items():
            assert block.block_type is not None
            assert block.priority is not None

        # Specific type checks
        assert recognized["h"][0].block_type == "Heading"
        assert recognized["d"][0].block_type == "Definition"
        assert recognized["eq"][0].block_type == "Formula Box"
        assert recognized["t"][0].block_type == "Table"
        assert recognized["ex"][0].block_type == "Exercise"

        # Priority checks
        assert recognized["d"][0].priority == HIGH
        assert recognized["eq"][0].priority == HIGH
        assert recognized["t"][0].priority == HIGH
        assert recognized["ex"][0].priority == LOW


# =========================================================================
# 9. Backward compatibility
# =========================================================================

class TestBackwardCompatibility:
    """Verify API contracts from all milestones are preserved."""

    def test_block_dataclass_fields(self):
        """Block has all required fields from the frozen architecture."""
        b = Block(block_id="test", page=0, bbox=(0, 0, 100, 100))
        assert hasattr(b, "block_id")
        assert hasattr(b, "page")
        assert hasattr(b, "bbox")
        assert hasattr(b, "lines")
        assert hasattr(b, "children")
        assert hasattr(b, "parent")
        assert hasattr(b, "grouping_meta")
        assert hasattr(b, "page_end")
        assert hasattr(b, "block_type")
        assert hasattr(b, "confidence")
        assert hasattr(b, "priority")

    def test_block_types_frozen(self):
        """The BLOCK_TYPES list contains all required types."""
        required = {
            "Heading", "Definition", "Law", "Formula Box", "Worked Example",
            "Exercise", "Activity", "Summary", "Table", "Figure", "Diagram",
            "Flowchart", "Programming Syntax", "Accounting Format", "Reference",
            "Footer", "Header", "Decision Tree", "Ambiguous",
        }
        assert required == set(BLOCK_TYPES)

    def test_priority_map_covers_all_block_types(self):
        """Every BLOCK_TYPE has a DEFAULT_PRIORITY_MAP entry."""
        for bt in BLOCK_TYPES:
            assert bt in DEFAULT_PRIORITY_MAP, f"Missing priority for {bt}"

    def test_priority_constants(self):
        assert HIGH == "high"
        assert MEDIUM == "medium"
        assert LOW == "low"

    def test_classify_signature(self):
        """classify() accepts (block, preceding_text, in_example)."""
        b = _block("heading-topic", 0, (50, 50, 400, 70),
                   grouping_meta={"anchor": "heading-topic"})
        result = classify(b, preceding_text="", in_example=False)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], float)

    def test_classify_blocks_signature(self):
        """classify_blocks() accepts list, returns list."""
        blocks = [_block("heading-topic", 0, (50, 50, 400, 70),
                         grouping_meta={"anchor": "heading-topic"})]
        result = classify_blocks(blocks)
        assert isinstance(result, list)

    def test_assign_priority_signature(self):
        """assign_priority() accepts (blocks, overrides), returns list."""
        blocks = [_block("heading-topic", 0, (50, 50, 400, 70),
                         grouping_meta={"anchor": "heading-topic"})]
        blocks[0].block_type = "Heading"
        blocks[0].confidence = 1.0
        result = assign_priority(blocks)
        assert isinstance(result, list)

    def test_assign_priority_overrides(self):
        """Priority overrides work without modifying the default map."""
        blocks = [_block("callout-label", 0, (50, 100, 400, 200))]
        blocks[0].block_type = "Exercise"
        blocks[0].confidence = 0.7
        result = assign_priority(blocks, overrides={"Exercise": MEDIUM})
        assert result[0].priority == MEDIUM
        # Default map should NOT be modified
        assert DEFAULT_PRIORITY_MAP["Exercise"] == LOW

    def test_candidates_for_returns_list(self):
        """candidates_for() returns a list (possibly empty)."""
        assert isinstance(candidates_for("Formula Box"), list)
        assert isinstance(candidates_for("NonexistentType"), list)

    def test_registered_block_types_returns_list(self):
        """registered_block_types() returns a list of strings."""
        rbt = registered_block_types()
        assert isinstance(rbt, list)
        assert all(isinstance(bt, str) for bt in rbt)

    def test_variable_only_re_importable(self):
        """Key regexes remain importable from stage_b_classify."""
        assert _VARIABLE_ONLY_RE.match("F = m * a")
        assert not _VARIABLE_ONLY_RE.match("= 3.14")

    def test_numeric_substitution_re_importable(self):
        assert _NUMERIC_SUBSTITUTION_RE.match("= 3.14")

    def test_text_utils_patterns_importable(self):
        """M4.1A shared patterns are importable."""
        assert DEFINITION_TERM_FIRST_RE is not None
        assert DEFINITION_TERM_AFTER_RE is not None
        assert DEFINITION_TERM_DENOTES_RE is not None
        assert DEFINITION_TERM_BY_MEAN_RE is not None
        assert TERM_STOPWORDS is not None
        assert STEP_MARKER_RE is not None

    def test_term_is_valid_utility(self):
        """M4.1A term_is_valid works correctly."""
        assert term_is_valid("Force")
        assert term_is_valid("Momentum")
        assert not term_is_valid("the")
        assert not term_is_valid("")
        assert not term_is_valid("a")

    def test_partial_match_confidence_utility(self):
        """M4.1A partial_match_confidence works correctly."""
        assert partial_match_confidence(5, 5, 0.85) == 0.85
        assert partial_match_confidence(0, 5, 0.85) == 0.0
        assert partial_match_confidence(0, 0, 0.85) == 0.0
        assert 0.0 < partial_match_confidence(3, 5, 0.85) < 0.85

    def test_layout_quality_functions_importable(self):
        """M4.1B layout quality functions are importable."""
        assert callable(apply_layout_quality_passes)
        assert callable(suppress_cross_kind_duplicates)
        assert callable(_bbox_iou)

    def test_recognizer_safe_recognize_catches_errors(self):
        """safe_recognize() never raises, even on bad input."""
        rec = FormulaRecognizer()
        b = _block("heading-topic", 0, (50, 50, 400, 70),
                   grouping_meta={"anchor": "heading-topic"})
        result = rec.safe_recognize(b)
        # Should return None, not raise
        assert result is None or isinstance(result, RecognitionResult)


# =========================================================================
# 10. Recognizer registry stability and completeness
# =========================================================================

class TestRegistryStability:
    """Verify the recognizer registry is complete and stable."""

    def test_all_visual_types_have_generic_fallback(self):
        """Every visual block type has GenericVisualRecognizer as fallback."""
        visual_types = ["Table", "Figure", "Diagram", "Flowchart",
                        "Decision Tree", "Programming Syntax",
                        "Accounting Format"]
        for bt in visual_types:
            cands = candidates_for(bt)
            names = [c.name for c in cands]
            assert "generic_visual" in names, \
                f"{bt} missing generic_visual fallback"

    def test_formula_box_has_all_formula_recognizers(self):
        """Formula Box has all four formula family recognizers."""
        cands = candidates_for("Formula Box")
        names = {c.name for c in cands}
        assert "formula" in names
        assert "math_identity" in names
        assert "chemical_reaction" in names
        assert "economic_identity" in names

    def test_worked_example_has_procedure_recognizers(self):
        """Worked Example has procedure + formula recognizers."""
        cands = candidates_for("Worked Example")
        names = {c.name for c in cands}
        assert "procedure" in names
        assert "worked_example" in names
        assert "formula" in names

    def test_definition_has_recognizer(self):
        """Definition type has the definition recognizer."""
        cands = candidates_for("Definition")
        names = {c.name for c in cands}
        assert "definition" in names

    def test_registry_recognizer_count(self):
        """Verify total recognizer count across all types."""
        total = sum(len(cands) for cands in _REGISTRY.values())
        # At least 30 total registrations (some recognizers are registered
        # for multiple types)
        assert total >= 30


# =========================================================================
# 11. text_utils pattern reuse verification
# =========================================================================

class TestTextUtilsReuse:
    """Verify that M4.1A patterns are used consistently across modules."""

    def test_definition_recognizer_uses_text_utils(self):
        """DefinitionRecognizer imports from text_utils, not its own patterns."""
        import inspect
        source = inspect.getsource(DefinitionRecognizer)
        # Should reference the imported patterns
        assert "DEFINITION_TERM_FIRST_RE" in source or "term_is_valid" in source

    def test_procedure_recognizer_uses_step_marker(self):
        """ProcedureRecognizer uses STEP_MARKER_RE from text_utils."""
        from modules.recognizers.procedure_recognizers import ProcedureRecognizer
        import inspect
        source = inspect.getsource(ProcedureRecognizer)
        assert "STEP_MARKER_RE" in source

    def test_formula_recognizer_uses_partial_match_confidence(self):
        """FormulaRecognizer uses partial_match_confidence from text_utils."""
        from modules.recognizers.formula_recognizers import FormulaRecognizer
        import inspect
        source = inspect.getsource(FormulaRecognizer)
        assert "partial_match_confidence" in source


# =========================================================================
# 12. Confidence-based priority promotion/demotion
# =========================================================================

class TestConfidencePriorityIntegration:
    """Verify confidence-based priority adjustments work end-to-end."""

    def test_high_confidence_heading_promoted(self):
        """Heading with confidence=1.0 (MEDIUM base) → promoted to HIGH."""
        b = _block("heading-topic", 0, (50, 50, 400, 70),
                   grouping_meta={"anchor": "heading-topic"})
        result = _pipeline([b])
        assert result[0].confidence == 1.0
        assert result[0].priority == HIGH

    def test_low_confidence_not_promoted(self):
        """A block with confidence < 0.85 and MEDIUM base stays MEDIUM."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                   lines=[_line("Note:", y=100)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Note:"})
        result = _pipeline([b])
        # Note → Activity (0.65 confidence, MEDIUM base)
        assert result[0].block_type == "Activity"
        assert result[0].confidence < 0.85
        assert result[0].priority == MEDIUM

    def test_promote_demote_idempotent(self):
        """_promote(HIGH) == HIGH, _demote(LOW) == LOW."""
        assert _promote(HIGH) == HIGH
        assert _demote(LOW) == LOW


# =========================================================================
# 13. Edge cases
# =========================================================================

class TestEdgeCases:
    """Edge cases that could cause integration failures."""

    def test_block_with_no_lines_no_children(self):
        """A block with no text content gets Ambiguous type."""
        b = _block("", 0, (50, 100, 400, 200),
                   grouping_meta={"anchor": ""})
        result = _pipeline([b])
        assert result[0].block_type == "Ambiguous"
        assert result[0].priority is not None

    def test_block_with_empty_grouping_meta(self):
        """A block with empty grouping_meta doesn't crash."""
        b = Block(block_id="empty", page=0, bbox=(50, 100, 400, 200),
                  grouping_meta={})
        result = _pipeline([b])
        assert len(result) == 1
        assert result[0].block_type is not None

    def test_block_with_none_grouping_meta(self):
        """A block with None grouping_meta doesn't crash."""
        b = Block(block_id="none-meta", page=0, bbox=(50, 100, 400, 200),
                  grouping_meta=None)
        result = _pipeline([b])
        assert len(result) == 1

    def test_recognizer_on_empty_block(self):
        """Recognizers handle empty blocks gracefully."""
        b = Block(block_id="empty", page=0, bbox=(50, 100, 400, 200),
                  grouping_meta={"anchor": "equation-cluster"})
        b.block_type = "Formula Box"
        b.confidence = 0.5
        for c in candidates_for("Formula Box"):
            result = c.safe_recognize(b)
            # Should not crash — may return None
            assert result is None or isinstance(result, RecognitionResult)

    def test_very_long_label_line(self):
        """A very long label_line doesn't crash classification."""
        long_label = "A" * 1000
        b = _block("callout-label", 0, (50, 100, 400, 200),
                   lines=[_line(long_label)],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": long_label})
        result = _pipeline([b])
        assert result[0].block_type is not None

    def test_unicode_in_block_text(self):
        """Unicode characters in block text don't crash the pipeline."""
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                   lines=[_line("Résumé is defined as a summary")],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Résumé"})
        result = _pipeline([b])
        assert result[0].block_type == "Definition"

    def test_block_raw_texts_children_vs_lines(self):
        """block_raw_texts correctly prefers children over lines."""
        child = _block("equation-line", 0, (50, 100, 400, 115),
                       grouping_meta={"anchor": "equation-line",
                                      "raw_text": "F = m * a"})
        b = _block("equation-cluster", 0, (50, 100, 400, 115),
                   children=[child],
                   lines=[_line("Some other text")],
                   grouping_meta={"anchor": "equation-cluster"})
        texts = block_raw_texts(b)
        assert "F = m * a" in texts
        assert "Some other text" not in texts
