"""
tests/test_m41cd_stage_bc_recognizers.py — Comprehensive tests for M4.1C
(Stage B + Stage C improvements) and M4.1D (Recognizer improvements).

Covers:
  Stage B:
    - Improved callout classification (Warning, Note, Box, Tip, Important)
    - Exercise / Summary / Reference detection in callouts
    - Body-text definition fallback
    - Grouped definition confidence boost
    - in_example tracking
    - Duplicate classification suppression
    - Parent/child block_type propagation
    - Metadata propagation from M4.1B
    - Deterministic ordering

  Stage C:
    - Confidence-based priority adjustment
    - Structural priority signals (continuation, grouped definitions)
    - Child priority propagation
    - Priority override support

  Recognizers:
    - DefinitionRecognizer (extended patterns, multi-line, continuation)
    - FormulaRecognizer (multiline, variables, continuation)
    - MathIdentityRecognizer (trig/log, variables)
    - ChemicalReactionRecognizer
    - EconomicIdentityRecognizer
    - ProcedureRecognizer (step markers, solution/given, cross-page)
    - WorkedExampleRecognizer (new)
    - FlowchartRecognizer, GraphRecognizer, CircuitDiagramRecognizer
    - ConceptTableRecognizer (prose false-positive suppression)
    - DiagramSubtypeRecognizer (new)
    - FigureWithCaptionRecognizer (new)
    - GenericVisualRecognizer
    - Duplicate suppression
    - Deterministic ordering
"""

import pytest
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from modules.pdf_parser import Line
from modules.stage_a_geometry import Block
from modules.stage_b_classify import (
    classify, classify_blocks,
    _classify_callout_label, _classify_equation_cluster,
    _classify_table_like, _classify_diagram_like,
    _classify_body_text_fallback,
    _suppress_duplicate_classifications,
    _propagate_parent_child_types,
    _propagate_metadata,
    BLOCK_TYPES,
)
from modules.stage_c_priority import (
    assign_priority, DEFAULT_PRIORITY_MAP,
    HIGH, MEDIUM, LOW,
    _promote, _demote,
    _adjust_priority_by_confidence,
    _adjust_priority_by_structure,
)
from modules.recognizers.concept_recognizers import DefinitionRecognizer
from modules.recognizers.formula_recognizers import (
    FormulaRecognizer, MathIdentityRecognizer, ChemicalReactionRecognizer,
    EconomicIdentityRecognizer, _extract_variables,
)
from modules.recognizers.procedure_recognizers import (
    ProcedureRecognizer, AlgorithmRecognizer, JournalProcedureRecognizer,
    WorkedExampleRecognizer,
)
from modules.recognizers.visual_recognizers import (
    FlowchartRecognizer, GraphRecognizer, CircuitDiagramRecognizer,
    ConceptTableRecognizer, DiagramSubtypeRecognizer,
    FigureWithCaptionRecognizer, GenericVisualRecognizer,
)
from modules.recognizers import candidates_for, registered_block_types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line(text, page=0, y=100.0, bbox=None):
    if bbox is None:
        bbox = (50.0, y, 500.0, y + 12.0)
    return Line(text=text, size=10.0, max_size=12.0, bold=False,
                font="Arial", page=page, y=y, page_height=800.0, bbox=bbox)


def _block(kind, page, bbox, lines=None, children=None,
           grouping_meta=None, block_id=None):
    if lines is None:
        lines = []
    if children is None:
        children = []
    if grouping_meta is None:
        grouping_meta = {"anchor": kind}
    if block_id is None:
        block_id = f"block-{kind}-{page}-{bbox[1]:.0f}"
    return Block(
        block_id=block_id, page=page, bbox=bbox,
        lines=lines, children=children,
        grouping_meta=grouping_meta,
    )


# =========================================================================
# STAGE B TESTS (M4.1C)
# =========================================================================

class TestStageBCalloutClassification:
    """M4.1C: Improved callout-label classification."""

    def test_example_label(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Example 3.1"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Worked Example"
        assert conf >= 0.8

    def test_activity_label(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Activity 2.1"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.8

    def test_warning_label_classified_as_activity(self):
        """M4.1C: Warning labels get Activity with improved confidence."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Warning:"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_caution_label(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Caution:"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_note_label_classified_as_activity(self):
        """M4.1C: Note labels get Activity instead of Summary."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Note:"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_remember_label(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Remember"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_tip_label(self):
        """M4.1C: Tip/Hint labels → Activity."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Tip:"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_important_label(self):
        """M4.1C: 'Important' → Activity."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Important"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_box_label(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Did You Know"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_callout_type_hint_warning(self):
        """M4.1C: Uses callout_type_hint from M4.1B."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Safety Info",
                                   "callout_type_hint": "warning"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"
        assert conf >= 0.6

    def test_callout_type_hint_note(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Side Note",
                                   "callout_type_hint": "note"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Activity"

    def test_exercise_in_callout(self):
        """M4.1C: Exercise detection in callout labels."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Exercise 5.1"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Exercise"

    def test_summary_in_callout(self):
        """M4.1C: Summary detection in callout labels."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Summary"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Summary"

    def test_reference_in_callout(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "References"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Reference"

    def test_law_in_callout_body(self):
        """M4.1C: Law detection in body text of unmatched callouts."""
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    lines=[_line("The law of conservation of energy states")],
                    grouping_meta={"anchor": "callout-label", "label_line": "Concept"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Law"

    def test_unrecognized_callout_is_ambiguous(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "label_line": "Random Text"})
        bt, conf = _classify_callout_label(b)
        assert bt == "Ambiguous"


class TestStageBClassify:
    """Tests for the main classify() function."""

    def test_heading(self):
        b = _block("heading-topic", 0, (50, 100, 400, 120),
                    grouping_meta={"anchor": "heading-topic"})
        bt, conf = classify(b)
        assert bt == "Heading"
        assert conf == 1.0

    def test_definition_candidate(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    grouping_meta={"anchor": "definition-candidate", "candidate_term": "Force"})
        bt, conf = classify(b)
        assert bt == "Definition"
        assert conf == 0.75

    def test_grouped_definition_higher_confidence(self):
        """M4.1C: Grouped definitions from M4.1B get higher confidence."""
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    grouping_meta={"anchor": "definition-candidate",
                                   "candidate_term": "Force",
                                   "grouped_definitions": True})
        bt, conf = classify(b)
        assert bt == "Definition"
        assert conf == 0.8

    def test_table_anchor(self):
        b = _block("table", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "table"})
        bt, conf = classify(b)
        assert bt == "Table"

    def test_figure_anchor(self):
        b = _block("figure", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "figure"})
        bt, conf = classify(b)
        assert bt == "Figure"

    def test_diagram_anchor(self):
        b = _block("diagram", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "diagram"})
        bt, conf = classify(b)
        assert bt == "Diagram"

    def test_equation_cluster_in_example(self):
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    grouping_meta={"anchor": "equation-cluster"},
                    children=[_block("equation-line", 0, (50, 100, 400, 120))])
        bt, conf = classify(b, in_example=True)
        assert bt == "Worked Example"

    def test_body_text_summary_fallback(self):
        """M4.1C: Body text fallback detects Summary."""
        b = _block("", 0, (50, 100, 400, 200),
                    lines=[_line("Summary of the chapter")],
                    grouping_meta={"anchor": ""})
        bt, conf = _classify_body_text_fallback(b)
        assert bt == "Summary"

    def test_body_text_definition_fallback(self):
        """M4.1C: Body text fallback detects Definition cues."""
        b = _block("", 0, (50, 100, 400, 200),
                    lines=[_line("Acceleration is defined as the rate of change of velocity")],
                    grouping_meta={"anchor": ""})
        bt, conf = _classify_body_text_fallback(b)
        assert bt == "Definition"

    def test_body_text_law_fallback(self):
        b = _block("", 0, (50, 100, 400, 200),
                    lines=[_line("This is the law of conservation of mass")],
                    grouping_meta={"anchor": ""})
        bt, conf = _classify_body_text_fallback(b)
        assert bt == "Law"

    def test_body_text_empty_is_ambiguous(self):
        b = _block("", 0, (50, 100, 400, 200),
                    lines=[], grouping_meta={"anchor": ""})
        bt, conf = _classify_body_text_fallback(b)
        assert bt == "Ambiguous"


class TestStageBClassifyBlocks:
    """Tests for classify_blocks() pipeline."""

    def test_deterministic_ordering(self):
        """M4.1C: Output is deterministically sorted."""
        blocks = [
            _block("figure", 1, (10, 300, 100, 400), block_id="b1"),
            _block("heading-topic", 0, (10, 50, 100, 70), block_id="b2",
                   grouping_meta={"anchor": "heading-topic"}),
            _block("table", 0, (10, 200, 100, 300), block_id="b3",
                   grouping_meta={"anchor": "table"}),
        ]
        result = classify_blocks(blocks)
        pages = [(b.page, b.bbox[1]) for b in result]
        assert pages == sorted(pages)

    def test_in_example_tracking(self):
        """Example label sets in_example flag for subsequent eq clusters."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120),
                   lines=[_line("Example 1")],
                   grouping_meta={"anchor": "callout-label", "label_line": "Example 1"}),
            _block("equation-cluster", 0, (50, 200, 400, 220),
                   grouping_meta={"anchor": "equation-cluster"},
                   children=[_block("equation-line", 0, (50, 200, 400, 220),
                                    grouping_meta={"anchor": "equation-line", "raw_text": "= 5 + 3"})]),
        ]
        result = classify_blocks(blocks)
        assert result[0].block_type == "Worked Example"
        assert result[1].block_type == "Worked Example"

    def test_heading_resets_in_example(self):
        """A heading after an example label resets the in_example flag."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120),
                   lines=[_line("Example 1")],
                   grouping_meta={"anchor": "callout-label", "label_line": "Example 1"}),
            _block("heading-topic", 0, (50, 200, 400, 220),
                   grouping_meta={"anchor": "heading-topic"}),
            _block("equation-cluster", 0, (50, 300, 400, 320),
                   grouping_meta={"anchor": "equation-cluster"},
                   children=[_block("equation-line", 0, (50, 300, 400, 320),
                                    grouping_meta={"anchor": "equation-line", "raw_text": "F = ma"})]),
        ]
        result = classify_blocks(blocks)
        assert result[1].block_type == "Heading"
        # After heading, in_example is False
        assert result[2].block_type != "Worked Example" or result[2].confidence < 0.85


class TestStageBDuplicateSuppression:
    """M4.1C: Duplicate classification suppression."""

    def test_duplicate_labels_suppressed(self):
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120),
                   block_id="b1",
                   grouping_meta={"anchor": "callout-label", "label_line": "Activity 1"}),
            _block("callout-label", 0, (50, 130, 400, 150),
                   block_id="b2",
                   grouping_meta={"anchor": "callout-label", "label_line": "Activity 1"}),
        ]
        for b in blocks:
            b.block_type = "Activity"
            b.confidence = 0.85 if b.block_id == "b1" else 0.6
        result = _suppress_duplicate_classifications(blocks)
        assert len(result) == 1
        assert result[0].block_id == "b1"

    def test_different_labels_not_suppressed(self):
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120),
                   block_id="b1",
                   grouping_meta={"anchor": "callout-label", "label_line": "Activity 1"}),
            _block("callout-label", 0, (50, 300, 400, 320),
                   block_id="b2",
                   grouping_meta={"anchor": "callout-label", "label_line": "Activity 2"}),
        ]
        for b in blocks:
            b.block_type = "Activity"
            b.confidence = 0.85
        result = _suppress_duplicate_classifications(blocks)
        assert len(result) == 2

    def test_ambiguous_not_suppressed(self):
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 120),
                   block_id="b1",
                   grouping_meta={"anchor": "callout-label", "label_line": "Foo"}),
            _block("callout-label", 0, (50, 130, 400, 150),
                   block_id="b2",
                   grouping_meta={"anchor": "callout-label", "label_line": "Foo"}),
        ]
        for b in blocks:
            b.block_type = "Ambiguous"
            b.confidence = 0.0
        result = _suppress_duplicate_classifications(blocks)
        assert len(result) == 2


class TestStageBParentChildPropagation:
    """M4.1C: Parent/child block_type propagation."""

    def test_ambiguous_child_inherits_parent(self):
        child = _block("equation-line", 0, (50, 110, 400, 120), block_id="c1")
        child.block_type = "Ambiguous"
        child.confidence = 0.0
        parent = _block("equation-cluster", 0, (50, 100, 400, 130),
                        children=[child], block_id="p1")
        parent.block_type = "Worked Example"
        parent.confidence = 0.85
        _propagate_parent_child_types([parent])
        assert child.block_type == "Worked Example"

    def test_heading_child_not_overridden(self):
        child = _block("heading-topic", 0, (50, 110, 400, 120), block_id="c1")
        child.block_type = "Heading"
        child.confidence = 1.0
        parent = _block("callout-label", 0, (50, 100, 400, 200),
                        children=[child], block_id="p1")
        parent.block_type = "Activity"
        parent.confidence = 0.85
        _propagate_parent_child_types([parent])
        assert child.block_type == "Heading"

    def test_ambiguous_parent_no_propagation(self):
        child = _block("equation-line", 0, (50, 110, 400, 120), block_id="c1")
        child.block_type = "Formula Box"
        child.confidence = 0.7
        parent = _block("callout-label", 0, (50, 100, 400, 200),
                        children=[child], block_id="p1")
        parent.block_type = "Ambiguous"
        parent.confidence = 0.0
        _propagate_parent_child_types([parent])
        assert child.block_type == "Formula Box"


class TestStageBMetadataPropagation:
    """M4.1C: Metadata propagation from M4.1B."""

    def test_border_boosts_activity_confidence(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label", "has_border": True})
        b.block_type = "Activity"
        b.confidence = 0.65
        _propagate_metadata([b])
        assert b.confidence >= 0.7

    def test_grouped_definitions_boost(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    grouping_meta={"anchor": "definition-candidate",
                                   "grouped_definitions": True})
        b.block_type = "Definition"
        b.confidence = 0.75
        _propagate_metadata([b])
        assert b.confidence >= 0.8

    def test_merged_continuation_boost(self):
        b = _block("equation-cluster", 0, (50, 100, 400, 150),
                    grouping_meta={"anchor": "equation-cluster",
                                   "merged_continuation": True})
        b.block_type = "Formula Box"
        b.confidence = 0.55
        _propagate_metadata([b])
        assert b.confidence >= 0.6


# =========================================================================
# STAGE C TESTS (M4.1C)
# =========================================================================

class TestStageCPriorityHelpers:
    """M4.1C: Priority helper functions."""

    def test_promote(self):
        assert _promote(LOW) == MEDIUM
        assert _promote(MEDIUM) == HIGH
        assert _promote(HIGH) == HIGH

    def test_demote(self):
        assert _demote(HIGH) == MEDIUM
        assert _demote(MEDIUM) == LOW
        assert _demote(LOW) == LOW


class TestStageCConfidenceAdjustment:
    """M4.1C: Confidence-based priority adjustment."""

    def test_high_confidence_promotes_medium(self):
        b = _block("callout-label", 0, (50, 100, 400, 200))
        b.block_type = "Activity"
        b.confidence = 0.9
        result = _adjust_priority_by_confidence(b, MEDIUM)
        assert result == HIGH

    def test_low_confidence_demotes_high(self):
        b = _block("callout-label", 0, (50, 100, 400, 200))
        b.block_type = "Activity"
        b.confidence = 0.2
        result = _adjust_priority_by_confidence(b, HIGH)
        assert result == MEDIUM

    def test_normal_confidence_unchanged(self):
        b = _block("callout-label", 0, (50, 100, 400, 200))
        b.block_type = "Activity"
        b.confidence = 0.5
        result = _adjust_priority_by_confidence(b, MEDIUM)
        assert result == MEDIUM


class TestStageCStructuralAdjustment:
    """M4.1C: Structural priority adjustment."""

    def test_continuation_promotes(self):
        b = _block("callout-label", 0, (50, 100, 400, 200),
                    grouping_meta={"anchor": "callout-label",
                                   "continuation": {"continued_on_page": 1}})
        result = _adjust_priority_by_structure(b, MEDIUM)
        assert result == HIGH

    def test_grouped_definitions_always_high(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    grouping_meta={"anchor": "definition-candidate",
                                   "grouped_definitions": True})
        result = _adjust_priority_by_structure(b, MEDIUM)
        assert result == HIGH


class TestStageCAssignPriority:
    """Tests for assign_priority()."""

    def test_default_priority_map(self):
        blocks = [
            _block("definition-candidate", 0, (50, 100, 400, 120)),
            _block("equation-cluster", 0, (50, 200, 400, 250)),
            _block("callout-label", 0, (50, 300, 400, 400)),
        ]
        blocks[0].block_type = "Definition"
        blocks[0].confidence = 0.75
        blocks[1].block_type = "Worked Example"
        blocks[1].confidence = 0.65
        blocks[2].block_type = "Exercise"
        blocks[2].confidence = 0.7
        result = assign_priority(blocks)
        assert result[0].priority == HIGH
        assert result[1].priority == MEDIUM
        assert result[2].priority == LOW

    def test_override_priority(self):
        blocks = [_block("callout-label", 0, (50, 100, 400, 200))]
        blocks[0].block_type = "Exercise"
        blocks[0].confidence = 0.7
        result = assign_priority(blocks, overrides={"Exercise": MEDIUM})
        assert result[0].priority == MEDIUM

    def test_child_priority_capped_by_parent(self):
        """M4.1C: Child priority never exceeds parent priority."""
        child = _block("equation-line", 0, (50, 110, 400, 120), block_id="c1")
        child.block_type = "Definition"  # Would be HIGH
        child.confidence = 0.75
        parent = _block("equation-cluster", 0, (50, 100, 400, 130),
                        children=[child], block_id="p1")
        parent.block_type = "Worked Example"  # MEDIUM
        parent.confidence = 0.65
        assign_priority([parent])
        assert child.priority == MEDIUM  # Capped by parent's MEDIUM


# =========================================================================
# RECOGNIZER TESTS (M4.1D)
# =========================================================================

class TestDefinitionRecognizer:
    """M4.1D: DefinitionRecognizer improvements."""

    def test_basic_definition_with_term(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    lines=[_line("Force is defined as mass times acceleration")],
                    grouping_meta={"anchor": "definition-candidate",
                                   "candidate_term": "Force"})
        r = DefinitionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["term"] == "Force"
        assert result.confidence >= 0.75

    def test_is_defined_as_pattern(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    lines=[_line("Momentum is defined as the product of mass and velocity")],
                    grouping_meta={"anchor": "definition-candidate",
                                   "candidate_term": "Momentum"})
        r = DefinitionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["definition_type"] == "is_defined_as"
        assert result.confidence >= 0.85

    def test_is_called_pattern(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    lines=[_line("This quantity is called acceleration")],
                    grouping_meta={"anchor": "definition-candidate",
                                   "candidate_term": "Acceleration"})
        r = DefinitionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.confidence >= 0.75

    def test_grouped_definitions_boost(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    lines=[_line("Force is defined as something")],
                    grouping_meta={"anchor": "definition-candidate",
                                   "candidate_term": "Force",
                                   "grouped_definitions": True})
        r = DefinitionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.confidence >= 0.85

    def test_additional_terms_propagated(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    lines=[_line("Force is defined as something")],
                    grouping_meta={"anchor": "definition-candidate",
                                   "candidate_term": "Force",
                                   "additional_terms": ["Mass", "Weight"]})
        r = DefinitionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert "additional_terms" in result.data
        assert "Mass" in result.data["additional_terms"]

    def test_invalid_term_low_confidence(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    lines=[_line("The is defined as something")],
                    grouping_meta={"anchor": "definition-candidate",
                                   "candidate_term": "The"})
        r = DefinitionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.confidence <= 0.3

    def test_no_term_returns_none(self):
        b = _block("definition-candidate", 0, (50, 100, 400, 120),
                    lines=[_line("Some random text without a definition")],
                    grouping_meta={"anchor": "definition-candidate"})
        r = DefinitionRecognizer()
        result = r.recognize(b)
        assert result is None


class TestFormulaRecognizer:
    """M4.1D: FormulaRecognizer improvements."""

    def test_basic_formula(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line", "raw_text": "F = m * a"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = FormulaRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["reusable_formula"] == "F = m * a"

    def test_variable_extraction(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line", "raw_text": "F = m * a"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = FormulaRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert "variables" in result.data
        assert "F" in result.data["variables"]
        assert "m" in result.data["variables"]
        assert "a" in result.data["variables"]

    def test_multiline_equation_flag(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line", "raw_text": "E = m * c"})
        b = _block("equation-cluster", 0, (50, 100, 400, 150),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster",
                                   "merged_continuation": True})
        r = FormulaRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data.get("multiline_equation") is True

    def test_no_formula_returns_none(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line", "raw_text": "The force is"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = FormulaRecognizer()
        result = r.recognize(b)
        assert result is None


class TestMathIdentityRecognizer:
    def test_trig_identity(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line",
                                       "raw_text": "sin(x) + cos(x) = 1"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = MathIdentityRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["identity_type"] == "trigonometric_or_logarithmic"

    def test_non_trig_returns_none(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line", "raw_text": "F = m * a"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = MathIdentityRecognizer()
        result = r.recognize(b)
        assert result is None


class TestChemicalReactionRecognizer:
    def test_chemical_equation(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line",
                                       "raw_text": "NaCl + AgNO3 → AgCl + NaNO3"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = ChemicalReactionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["reaction_type"] == "chemical_equation"

    def test_non_chemical_returns_none(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line", "raw_text": "F = m * a"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = ChemicalReactionRecognizer()
        result = r.recognize(b)
        assert result is None


class TestEconomicIdentityRecognizer:
    def test_gdp_identity(self):
        child = _block("equation-line", 0, (50, 100, 400, 120),
                        grouping_meta={"anchor": "equation-line",
                                       "raw_text": "GDP = C + I + G + X - M"})
        b = _block("equation-cluster", 0, (50, 100, 400, 120),
                    children=[child],
                    grouping_meta={"anchor": "equation-cluster"})
        r = EconomicIdentityRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["identity_type"] == "economic"


class TestProcedureRecognizer:
    """M4.1D: ProcedureRecognizer improvements."""

    def test_step_numbered_procedure(self):
        b = _block("callout-label", 0, (50, 100, 400, 250),
                    lines=[_line("Step 1: Heat the solution"),
                           _line("Step 2: Add the reagent"),
                           _line("= 20 ml")],
                    grouping_meta={"anchor": "callout-label"})
        r = ProcedureRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert len(result.data["procedure_steps"]) >= 2

    def test_solution_marker(self):
        """M4.1D: Solution markers are recognized."""
        b = _block("callout-label", 0, (50, 100, 400, 250),
                    lines=[_line("Solution:"),
                           _line("First, calculate the force"),
                           _line("Then, find the acceleration")],
                    grouping_meta={"anchor": "callout-label"})
        r = ProcedureRecognizer()
        result = r.recognize(b)
        assert result is not None

    def test_cross_page_continuation(self):
        """M4.1D: Cross-page continuation awareness."""
        b = _block("callout-label", 0, (50, 100, 400, 250),
                    lines=[_line("Step 1: Heat the solution"),
                           _line("Step 2: Add the reagent")],
                    grouping_meta={"anchor": "callout-label",
                                   "continuation": {"continued_on_page": 1}})
        r = ProcedureRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data.get("cross_page") is True

    def test_no_steps_returns_none(self):
        b = _block("callout-label", 0, (50, 100, 400, 250),
                    lines=[_line("The force is applied to the object")],
                    grouping_meta={"anchor": "callout-label"})
        r = ProcedureRecognizer()
        result = r.recognize(b)
        assert result is None


class TestWorkedExampleRecognizer:
    """M4.1D: New WorkedExampleRecognizer."""

    def test_solution_and_given(self):
        b = _block("callout-label", 0, (50, 100, 400, 300),
                    lines=[_line("Given: F = 20 N, m = 5 kg"),
                           _line("Find: acceleration"),
                           _line("Solution: a = F/m = 20/5 = 4 m/s²")],
                    grouping_meta={"anchor": "callout-label"})
        r = WorkedExampleRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["has_solution"] is True
        assert result.data["has_given"] is True
        assert result.confidence >= 0.7

    def test_solution_only(self):
        b = _block("callout-label", 0, (50, 100, 400, 300),
                    lines=[_line("Solution: Calculate the area"),
                           _line("Area = length × width")],
                    grouping_meta={"anchor": "callout-label"})
        r = WorkedExampleRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["has_solution"] is True

    def test_no_solution_no_given(self):
        b = _block("callout-label", 0, (50, 100, 400, 300),
                    lines=[_line("The force is applied to the object")],
                    grouping_meta={"anchor": "callout-label"})
        r = WorkedExampleRecognizer()
        result = r.recognize(b)
        assert result is None


class TestAlgorithmRecognizer:
    def test_algorithm_detected(self):
        b = _block("callout-label", 0, (50, 100, 400, 300),
                    lines=[_line("Input: n"),
                           _line("If n > 0 then print n"),
                           _line("Output: result")],
                    grouping_meta={"anchor": "callout-label"})
        r = AlgorithmRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["procedure_type"] == "algorithm"

    def test_no_algorithm_keywords(self):
        b = _block("callout-label", 0, (50, 100, 400, 300),
                    lines=[_line("The force acts on the body")],
                    grouping_meta={"anchor": "callout-label"})
        r = AlgorithmRecognizer()
        result = r.recognize(b)
        assert result is None


class TestVisualRecognizers:
    """M4.1D: Visual recognizer improvements."""

    def test_flowchart_from_caption(self):
        b = _block("diagram", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "diagram",
                                   "caption": "Flowchart of the process"})
        r = FlowchartRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["visual_subtype"] == "flowchart"

    def test_flowchart_from_body(self):
        """M4.1D: Flowchart detected from body text, not just caption."""
        b = _block("diagram", 0, (50, 100, 400, 300),
                    lines=[_line("Start the flowchart process")],
                    grouping_meta={"anchor": "diagram", "caption": ""})
        r = FlowchartRecognizer()
        result = r.recognize(b)
        assert result is not None

    def test_graph_recognizer(self):
        b = _block("figure", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "figure",
                                   "caption": "Graph of velocity vs time"})
        r = GraphRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["visual_subtype"] == "graph"

    def test_circuit_diagram(self):
        b = _block("diagram", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "diagram",
                                   "caption": "Circuit with resistor and battery"})
        r = CircuitDiagramRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["visual_subtype"] == "circuit_diagram"

    def test_concept_table(self):
        b = _block("table", 0, (50, 100, 400, 300),
                    lines=[_line("Comparison of metals and non-metals")],
                    grouping_meta={"anchor": "table",
                                   "caption": "Difference between metals and non-metals"})
        r = ConceptTableRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["visual_subtype"] == "concept_table"

    def test_concept_table_prose_false_positive(self):
        """M4.1D: Prose false-positive suppression."""
        b = _block("table", 0, (50, 100, 400, 300),
                    lines=[
                        _line("This is a sentence. Another follows here."),
                        _line("More text here. Capital starts again."),
                        _line("Yet more prose. And more too."),
                        _line("Final line. Done now."),
                    ],
                    grouping_meta={"anchor": "table",
                                   "caption": "Comparison of things"})
        r = ConceptTableRecognizer()
        result = r.recognize(b)
        assert result is None  # Suppressed as prose


class TestDiagramSubtypeRecognizer:
    """M4.1D: New DiagramSubtypeRecognizer."""

    def test_lifecycle_diagram(self):
        b = _block("diagram", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "diagram",
                                   "caption": "Life cycle of a butterfly"})
        r = DiagramSubtypeRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["visual_subtype"] == "lifecycle_diagram"

    def test_map(self):
        b = _block("diagram", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "diagram",
                                   "caption": "Map of India showing rainfall"})
        r = DiagramSubtypeRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["visual_subtype"] == "map"

    def test_anatomy(self):
        b = _block("diagram", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "diagram",
                                   "caption": "Cross-section of the human heart"})
        r = DiagramSubtypeRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["visual_subtype"] == "anatomical_diagram"

    def test_no_subtype(self):
        b = _block("diagram", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "diagram", "caption": "A generic image"})
        r = DiagramSubtypeRecognizer()
        result = r.recognize(b)
        assert result is None


class TestFigureWithCaptionRecognizer:
    """M4.1D: FigureWithCaptionRecognizer."""

    def test_formal_figure_caption(self):
        b = _block("figure", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "figure",
                                   "caption": "Figure 3.2: The solar system"})
        r = FigureWithCaptionRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.data["has_formal_caption"] is True
        assert result.confidence >= 0.75

    def test_fig_abbreviation(self):
        b = _block("figure", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "figure",
                                   "caption": "Fig. 5: Cell structure"})
        r = FigureWithCaptionRecognizer()
        result = r.recognize(b)
        assert result is not None

    def test_no_formal_caption(self):
        b = _block("figure", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "figure", "caption": "A nice picture"})
        r = FigureWithCaptionRecognizer()
        result = r.recognize(b)
        assert result is None  # No formal caption


class TestGenericVisualRecognizer:
    """GenericVisualRecognizer always matches."""

    def test_always_matches(self):
        b = _block("figure", 0, (50, 100, 400, 300),
                    grouping_meta={"anchor": "figure", "caption": ""})
        r = GenericVisualRecognizer()
        result = r.recognize(b)
        assert result is not None
        assert result.confidence == 0.5


class TestVariableExtraction:
    """M4.1D: Variable extraction utility."""

    def test_single_letter_variables(self):
        vars = _extract_variables("F = m * a")
        assert "F" in vars
        assert "m" in vars
        assert "a" in vars

    def test_stopwords_excluded(self):
        vars = _extract_variables("sin(x) + cos(x) = 1")
        assert "x" in vars
        assert "sin" not in vars
        assert "cos" not in vars

    def test_empty_string(self):
        vars = _extract_variables("")
        assert vars == []


# =========================================================================
# REGISTRY TESTS
# =========================================================================

class TestRegistry:
    """Tests for the recognizer registry."""

    def test_formula_box_candidates(self):
        cands = candidates_for("Formula Box")
        names = [c.name for c in cands]
        assert "formula" in names
        assert "math_identity" in names
        assert "chemical_reaction" in names

    def test_worked_example_candidates(self):
        cands = candidates_for("Worked Example")
        names = [c.name for c in cands]
        assert "procedure" in names
        assert "worked_example" in names  # M4.1D new

    def test_definition_candidates(self):
        cands = candidates_for("Definition")
        names = [c.name for c in cands]
        assert "definition" in names

    def test_diagram_candidates(self):
        cands = candidates_for("Diagram")
        names = [c.name for c in cands]
        assert "diagram_subtype" in names  # M4.1D new
        assert "generic_visual" in names

    def test_figure_candidates(self):
        cands = candidates_for("Figure")
        names = [c.name for c in cands]
        assert "figure_with_caption" in names  # M4.1D new
        assert "generic_visual" in names

    def test_unknown_type_empty(self):
        cands = candidates_for("NonexistentType")
        assert cands == []


# =========================================================================
# BACKWARD COMPATIBILITY TESTS
# =========================================================================

class TestBackwardCompatibility:
    """Ensure M4.1A/M4.1B contracts are preserved."""

    def test_block_types_list_unchanged(self):
        """The BLOCK_TYPES list must contain all frozen types."""
        required = {
            "Heading", "Definition", "Law", "Formula Box", "Worked Example",
            "Exercise", "Activity", "Summary", "Table", "Figure", "Diagram",
            "Flowchart", "Programming Syntax", "Accounting Format", "Reference",
            "Footer", "Header", "Decision Tree", "Ambiguous",
        }
        assert required.issubset(set(BLOCK_TYPES))

    def test_default_priority_map_complete(self):
        """Every block type in BLOCK_TYPES has a priority mapping."""
        for bt in BLOCK_TYPES:
            assert bt in DEFAULT_PRIORITY_MAP, f"Missing: {bt}"

    def test_classify_returns_tuple(self):
        """classify() always returns (str, float)."""
        b = _block("heading-topic", 0, (50, 100, 400, 120),
                    grouping_meta={"anchor": "heading-topic"})
        result = classify(b)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], float)

    def test_classify_blocks_returns_list(self):
        """classify_blocks() returns a list of Block objects."""
        blocks = [
            _block("heading-topic", 0, (50, 100, 400, 120),
                   grouping_meta={"anchor": "heading-topic"}),
        ]
        result = classify_blocks(blocks)
        assert isinstance(result, list)
        assert all(isinstance(b, Block) for b in result)

    def test_assign_priority_returns_list(self):
        blocks = [_block("heading-topic", 0, (50, 100, 400, 120))]
        blocks[0].block_type = "Heading"
        blocks[0].confidence = 1.0
        result = assign_priority(blocks)
        assert isinstance(result, list)
        assert all(isinstance(b, Block) for b in result)

    def test_registered_block_types(self):
        """Registered block types include the expected set."""
        rbt = set(registered_block_types())
        assert "Formula Box" in rbt
        assert "Worked Example" in rbt
        assert "Definition" in rbt
        assert "Table" in rbt
        assert "Figure" in rbt
        assert "Diagram" in rbt

    def test_variable_only_re_importable(self):
        """_VARIABLE_ONLY_RE is still importable from stage_b_classify."""
        from modules.stage_b_classify import _VARIABLE_ONLY_RE
        assert _VARIABLE_ONLY_RE.match("F = m * a")

    def test_numeric_substitution_re_importable(self):
        """_NUMERIC_SUBSTITUTION_RE is still importable."""
        from modules.stage_b_classify import _NUMERIC_SUBSTITUTION_RE
        assert _NUMERIC_SUBSTITUTION_RE.match("= 3.14")


# =========================================================================
# DETERMINISTIC ORDERING TESTS
# =========================================================================

class TestDeterministicOrdering:
    """Ensure all outputs are deterministically ordered."""

    def test_classify_blocks_sorted(self):
        blocks = [
            _block("figure", 1, (10, 300, 100, 400), block_id="b1"),
            _block("heading-topic", 0, (10, 50, 100, 70), block_id="b2",
                   grouping_meta={"anchor": "heading-topic"}),
        ]
        result = classify_blocks(blocks)
        pages = [(b.page, b.bbox[1]) for b in result]
        assert pages == sorted(pages)

    def test_classify_blocks_stable(self):
        """Same input produces same output order."""
        blocks = [
            _block("figure", 0, (10, 300, 100, 400), block_id="a"),
            _block("table", 0, (10, 50, 100, 150), block_id="b",
                   grouping_meta={"anchor": "table"}),
        ]
        r1 = classify_blocks(list(blocks))
        r2 = classify_blocks(list(blocks))
        assert [b.block_id for b in r1] == [b.block_id for b in r2]
