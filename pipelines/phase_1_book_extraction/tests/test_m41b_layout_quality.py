"""
tests/test_m41b_layout_quality.py — Comprehensive tests for M4.1B
layout quality improvements.

Covers all 8 approved improvements:
  1. Cross-kind IoU duplicate suppression
  2. Equation clustering (multiline, aligned, continuation)
  3. Cross-page equation continuation
  4. Contiguous definition grouping
  5. Cross-page worked-example continuation
  6. Warning / Note / Box detection
  7. Table false-positive suppression
  8. Deterministic ordering and general cleanup
"""

import pytest
import sys
from pathlib import Path

# Ensure project root is on path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from modules.pdf_parser import Line, make_id
from modules.layout_detector import VisualRegion
from modules.stage_a_geometry import Block, _make_block, _union_bbox
from modules.layout_quality import (
    suppress_cross_kind_duplicates,
    merge_equation_continuations,
    merge_cross_page_equations,
    group_contiguous_definitions,
    merge_cross_page_worked_examples,
    enhance_callout_detection,
    suppress_table_false_positives,
    remove_duplicate_blocks,
    remove_contained_blocks,
    suppress_cross_kind_visual_duplicates,
    apply_layout_quality_passes,
    is_equation_continuation,
    is_aligned_equation_part,
    detect_border_cues,
    _bbox_iou,
    _bbox_area,
    _bbox_contains,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line(text: str, page: int = 0, y: float = 100.0,
          bbox: tuple = None) -> Line:
    """Create a minimal Line for testing."""
    if bbox is None:
        bbox = (50.0, y, 500.0, y + 12.0)
    return Line(text=text, size=10.0, max_size=12.0, bold=False,
                font="Arial", page=page, y=y, page_height=800.0, bbox=bbox)


def _block(kind: str, page: int, bbox: tuple, lines: list = None,
           children: list = None, grouping_meta: dict = None,
           block_id: str = None) -> Block:
    """Create a minimal Block for testing."""
    if lines is None:
        lines = []
    if children is None:
        children = []
    if grouping_meta is None:
        grouping_meta = {"anchor": kind}
    if block_id is None:
        block_id = f"block-{kind}-{page}-{bbox[1]:.0f}"
    return Block(
        block_id=block_id,
        page=page,
        bbox=bbox,
        lines=lines,
        children=children,
        grouping_meta=grouping_meta,
    )


def _visual_region(kind: str, page: int, bbox: tuple,
                   caption: str = "", extra: dict = None) -> VisualRegion:
    """Create a minimal VisualRegion for testing."""
    return VisualRegion(kind=kind, page=page, bbox=bbox,
                        caption=caption, extra=extra)


# =========================================================================
# 1. Cross-kind IoU duplicate suppression
# =========================================================================

class TestCrossKindIoUSuppression:
    """Tests for suppress_cross_kind_duplicates()."""

    def test_no_overlap_keeps_all(self):
        """Non-overlapping blocks of different kinds are all kept."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100)),
            _block("table", 0, (200, 200, 400, 400)),
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 2

    def test_overlapping_figure_diagram_keeps_higher_priority(self):
        """Figure (priority 70) beats diagram (priority 60)."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100)),
            _block("diagram", 0, (10, 10, 100, 100)),  # exact same bbox
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta["anchor"] == "figure"

    def test_overlapping_equation_figure_keeps_equation(self):
        """Equation-cluster (priority 90) beats figure (priority 70)."""
        blocks = [
            _block("figure", 0, (10, 10, 200, 200)),
            _block("equation-cluster", 0, (15, 15, 195, 195)),  # high IoU
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta["anchor"] == "equation-cluster"

    def test_low_overlap_keeps_both(self):
        """Blocks with IoU below threshold are both kept."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100)),
            _block("diagram", 0, (80, 80, 200, 200)),  # small overlap
        ]
        result = suppress_cross_kind_duplicates(blocks, iou_threshold=0.5)
        assert len(result) == 2

    def test_different_pages_no_suppression(self):
        """Exact same bbox on different pages should not suppress."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100)),
            _block("diagram", 1, (10, 10, 100, 100)),
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 2

    def test_same_priority_keeps_earlier(self):
        """When priorities tie (different kinds, same priority value),
        the block with lower y0 wins deterministically."""
        # Use two blocks whose kinds happen to have the same default
        # priority (both not in _KIND_PRIORITY, so both get _DEFAULT_PRIORITY).
        blocks = [
            _block("unknown-kind-a", 0, (10, 10, 100, 100), block_id="b1",
                   grouping_meta={"anchor": "unknown-kind-a"}),
            _block("unknown-kind-b", 0, (10, 10, 100, 100), block_id="b2",
                   grouping_meta={"anchor": "unknown-kind-b"}),
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 1
        # b1 has lower/equal y0, so it wins the tiebreak
        assert result[0].block_id == "b1"

    def test_heading_beats_everything(self):
        """Heading-topic has highest priority."""
        blocks = [
            _block("heading-topic", 0, (10, 10, 100, 100)),
            _block("equation-cluster", 0, (10, 10, 100, 100)),
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta["anchor"] == "heading-topic"

    def test_empty_and_single_block(self):
        """Edge cases: empty list and single block."""
        assert suppress_cross_kind_duplicates([]) == []
        single = [_block("figure", 0, (10, 10, 100, 100))]
        assert len(suppress_cross_kind_duplicates(single)) == 1

    def test_table_beats_definition(self):
        """Table (priority 80) beats definition-candidate (priority 40)."""
        blocks = [
            _block("table", 0, (10, 10, 200, 200)),
            _block("definition-candidate", 0, (12, 12, 198, 198)),
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta["anchor"] == "table"

    def test_triple_overlap_keeps_highest(self):
        """Three blocks overlapping the same region: keep only the
        highest-priority one."""
        blocks = [
            _block("diagram", 0, (10, 10, 100, 100)),
            _block("figure", 0, (10, 10, 100, 100)),
            _block("equation-cluster", 0, (10, 10, 100, 100)),
        ]
        result = suppress_cross_kind_duplicates(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta["anchor"] == "equation-cluster"


# =========================================================================
# 2. Equation clustering
# =========================================================================

class TestEquationContinuation:
    """Tests for equation continuation detection and merging."""

    def test_operator_start_is_continuation(self):
        assert is_equation_continuation("= 5 + 3")
        assert is_equation_continuation("+ additional term")
        assert is_equation_continuation("- subtracted")

    def test_keyword_continuation(self):
        assert is_equation_continuation("where x = 5")
        assert is_equation_continuation("therefore a = b")
        assert is_equation_continuation("hence the result")
        assert is_equation_continuation("thus we get")
        assert is_equation_continuation("substituting values")
        assert is_equation_continuation("putting the value")

    def test_symbol_continuation(self):
        assert is_equation_continuation("∴ x = 5")
        assert is_equation_continuation("⇒ y = 10")

    def test_normal_text_not_continuation(self):
        assert not is_equation_continuation("The force is")
        assert not is_equation_continuation("Newton's second law")
        assert not is_equation_continuation("")
        assert not is_equation_continuation("   ")

    def test_aligned_equation_markers(self):
        assert is_aligned_equation_part("x &= y + z")
        assert is_aligned_equation_part("continuation ...")
        assert not is_aligned_equation_part("normal text here")

    def test_merge_adjacent_equation_clusters(self):
        """Two adjacent equation clusters with continuation are merged."""
        blocks = [
            _block("equation-cluster", 0, (50, 100, 400, 120),
                   lines=[_line("F = ma", y=100)],
                   children=[_block("equation-line", 0, (50, 100, 400, 120),
                                    lines=[_line("F = ma", y=100)])]),
            _block("equation-cluster", 0, (50, 125, 400, 145),
                   lines=[_line("therefore a = F/m", y=125)],
                   children=[_block("equation-line", 0, (50, 125, 400, 145),
                                    lines=[_line("therefore a = F/m", y=125)])]),
        ]
        result = merge_equation_continuations(blocks)
        assert len(result) == 1
        assert len(result[0].children) == 2

    def test_non_continuation_not_merged(self):
        """Two equation clusters without continuation pattern are NOT merged."""
        blocks = [
            _block("equation-cluster", 0, (50, 100, 400, 120),
                   lines=[_line("F = ma", y=100)],
                   children=[]),
            _block("equation-cluster", 0, (50, 300, 400, 320),
                   lines=[_line("E = mc²", y=300)],
                   children=[]),
        ]
        result = merge_equation_continuations(blocks)
        assert len(result) == 2

    def test_different_page_not_merged(self):
        """Equation clusters on different pages are not merged here."""
        blocks = [
            _block("equation-cluster", 0, (50, 100, 400, 120),
                   lines=[_line("F = ma", page=0, y=100)], children=[]),
            _block("equation-cluster", 1, (50, 100, 400, 120),
                   lines=[_line("= 5 + 3", page=1, y=100)], children=[]),
        ]
        result = merge_equation_continuations(blocks)
        assert len(result) == 2

    def test_non_equation_blocks_unchanged(self):
        """Non-equation blocks pass through unchanged."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100)),
            _block("table", 0, (200, 200, 400, 400)),
        ]
        result = merge_equation_continuations(blocks)
        assert len(result) == 2

    def test_grouped_meta_flag(self):
        """Merged blocks get merged_continuation=True in grouping_meta."""
        blocks = [
            _block("equation-cluster", 0, (50, 100, 400, 120),
                   lines=[_line("F = ma", y=100)],
                   grouping_meta={"anchor": "equation-cluster", "line_count": 1},
                   children=[_block("equation-line", 0, (50, 100, 400, 120))]),
            _block("equation-cluster", 0, (50, 135, 400, 155),
                   lines=[_line("hence a = 5", y=135)],
                   grouping_meta={"anchor": "equation-cluster", "line_count": 1},
                   children=[_block("equation-line", 0, (50, 135, 400, 155))]),
        ]
        result = merge_equation_continuations(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta.get("merged_continuation") is True


# =========================================================================
# 3. Cross-page equation continuation
# =========================================================================

class TestCrossPageEquationContinuation:
    """Tests for merge_cross_page_equations()."""

    def test_continuation_across_pages(self):
        """Equation ending on page 0, continuing with '= ...' on page 1."""
        blocks = [
            _block("equation-cluster", 0, (50, 700, 400, 720),
                   lines=[_line("F = ma", page=0, y=700)], children=[]),
            _block("equation-cluster", 1, (50, 50, 400, 70),
                   lines=[_line("= 20 × 5", page=1, y=50)], children=[]),
        ]
        result = merge_cross_page_equations(blocks)
        assert len(result) == 1
        assert result[0].page == 0
        assert result[0].page_end == 1
        assert "continuation" in result[0].grouping_meta

    def test_no_continuation_pattern_no_merge(self):
        """Equation on page 1 starts fresh (no continuation cue)."""
        blocks = [
            _block("equation-cluster", 0, (50, 700, 400, 720),
                   lines=[_line("F = ma", page=0, y=700)], children=[]),
            _block("equation-cluster", 1, (50, 50, 400, 70),
                   lines=[_line("E = mc²", page=1, y=50)], children=[]),
        ]
        result = merge_cross_page_equations(blocks)
        assert len(result) == 2

    def test_non_adjacent_pages_no_merge(self):
        """Equations on pages 0 and 3 are never merged."""
        blocks = [
            _block("equation-cluster", 0, (50, 700, 400, 720),
                   lines=[_line("F = ma", page=0)], children=[]),
            _block("equation-cluster", 3, (50, 50, 400, 70),
                   lines=[_line("= result", page=3)], children=[]),
        ]
        result = merge_cross_page_equations(blocks)
        assert len(result) == 2

    def test_children_transferred(self):
        """Children of the merged block are re-parented."""
        child = _block("equation-line", 1, (50, 50, 400, 70),
                       block_id="child-1")
        blocks = [
            _block("equation-cluster", 0, (50, 700, 400, 720),
                   lines=[_line("F = ma", page=0)], children=[], block_id="parent"),
            _block("equation-cluster", 1, (50, 50, 400, 70),
                   lines=[_line("= 100", page=1)], children=[child]),
        ]
        result = merge_cross_page_equations(blocks)
        assert len(result) == 1
        assert child.parent == "parent"


# =========================================================================
# 4. Contiguous definition grouping
# =========================================================================

class TestContiguousDefinitionGrouping:
    """Tests for group_contiguous_definitions()."""

    def test_adjacent_definitions_merged(self):
        """Two vertically adjacent definition-candidates are merged."""
        blocks = [
            _block("definition-candidate", 0, (50, 100, 400, 112),
                   lines=[_line("Force is defined as", y=100)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force"}),
            _block("definition-candidate", 0, (50, 115, 400, 127),
                   lines=[_line("Mass is defined as", y=115)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Mass"}),
        ]
        result = group_contiguous_definitions(blocks)
        assert len(result) == 1
        assert len(result[0].lines) == 2
        assert result[0].grouping_meta.get("grouped_definitions") is True

    def test_distant_definitions_not_merged(self):
        """Two definitions with a large gap are NOT merged."""
        blocks = [
            _block("definition-candidate", 0, (50, 100, 400, 112),
                   lines=[_line("Force is defined as", y=100)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force"}),
            _block("definition-candidate", 0, (50, 300, 400, 312),
                   lines=[_line("Mass is defined as", y=300)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Mass"}),
        ]
        result = group_contiguous_definitions(blocks)
        assert len(result) == 2

    def test_different_pages_not_merged(self):
        """Definitions on different pages are NOT merged."""
        blocks = [
            _block("definition-candidate", 0, (50, 100, 400, 112),
                   lines=[_line("Force is defined as", page=0, y=100)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force"}),
            _block("definition-candidate", 1, (50, 100, 400, 112),
                   lines=[_line("Mass is defined as", page=1, y=100)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Mass"}),
        ]
        result = group_contiguous_definitions(blocks)
        assert len(result) == 2

    def test_intervening_non_definition_breaks_group(self):
        """A non-definition block between two definitions prevents merge."""
        blocks = [
            _block("definition-candidate", 0, (50, 100, 400, 112),
                   lines=[_line("Force is defined as", y=100)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force"}),
            _block("figure", 0, (50, 115, 400, 200)),
            _block("definition-candidate", 0, (50, 205, 400, 217),
                   lines=[_line("Mass is defined as", y=205)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Mass"}),
        ]
        result = group_contiguous_definitions(blocks)
        assert len(result) == 3

    def test_additional_terms_tracked(self):
        """When definitions are merged, additional terms are recorded."""
        blocks = [
            _block("definition-candidate", 0, (50, 100, 400, 112),
                   lines=[_line("Force is defined as", y=100)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Force"}),
            _block("definition-candidate", 0, (50, 118, 400, 130),
                   lines=[_line("Mass is defined as", y=118)],
                   grouping_meta={"anchor": "definition-candidate",
                                  "candidate_term": "Mass"}),
        ]
        result = group_contiguous_definitions(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta["candidate_term"] == "Force"
        assert "Mass" in result[0].grouping_meta.get("additional_terms", [])


# =========================================================================
# 5. Cross-page worked-example continuation
# =========================================================================

class TestCrossPageWorkedExamples:
    """Tests for merge_cross_page_worked_examples()."""

    def test_example_continues_to_next_page(self):
        """An 'Example' callout at page bottom continues on next page."""
        blocks = [
            _block("callout-label", 0, (50, 700, 400, 780),
                   lines=[_line("Example 3.1", page=0, y=700),
                          _line("Find the force...", page=0, y=715)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 3.1"}),
            _block("callout-label", 1, (50, 50, 400, 130),
                   lines=[_line("Continuing the solution...", page=1, y=50)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Continuing the solution..."}),
        ]
        result = merge_cross_page_worked_examples(blocks)
        assert len(result) == 1
        assert result[0].page == 0
        assert result[0].page_end == 1

    def test_new_example_not_merged(self):
        """A new 'Example 3.2' on the next page is NOT a continuation."""
        blocks = [
            _block("callout-label", 0, (50, 700, 400, 780),
                   lines=[_line("Example 3.1", page=0, y=700)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 3.1"}),
            _block("callout-label", 1, (50, 50, 400, 130),
                   lines=[_line("Example 3.2", page=1, y=50)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Example 3.2"}),
        ]
        result = merge_cross_page_worked_examples(blocks)
        assert len(result) == 2

    def test_non_example_not_merged(self):
        """A non-example callout (Activity) should NOT trigger merge."""
        blocks = [
            _block("callout-label", 0, (50, 700, 400, 780),
                   lines=[_line("Activity 2.1", page=0, y=700)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Activity 2.1"}),
            _block("callout-label", 1, (50, 50, 400, 130),
                   lines=[_line("Continue doing...", page=1, y=50)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Continue doing..."}),
        ]
        result = merge_cross_page_worked_examples(blocks)
        assert len(result) == 2

    def test_solved_example_continues(self):
        """'Solved Example' variant triggers continuation."""
        blocks = [
            _block("callout-label", 0, (50, 700, 400, 780),
                   lines=[_line("Solved Example 5", page=0, y=700)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Solved Example 5"}),
            _block("callout-label", 1, (50, 50, 400, 130),
                   lines=[_line("Step 2: Calculate...", page=1, y=50)],
                   children=[],
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Step 2: Calculate..."}),
        ]
        result = merge_cross_page_worked_examples(blocks)
        assert len(result) == 1


# =========================================================================
# 6. Warning / Note / Box detection
# =========================================================================

class TestWarningNoteBoxDetection:
    """Tests for enhanced callout detection with layout cues."""

    def test_note_heading_detected(self):
        """A callout with 'Note:' label gets callout_type_hint='note'."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 200),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Note:"}),
        ]
        lines = [_line("Note:", y=100)]
        result = enhance_callout_detection(blocks, lines)
        assert result[0].grouping_meta.get("callout_type_hint") == "note"

    def test_warning_heading_detected(self):
        """A callout with 'Warning!' gets callout_type_hint='warning'."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 200),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Warning!"}),
        ]
        lines = [_line("Warning!", y=100)]
        result = enhance_callout_detection(blocks, lines)
        assert result[0].grouping_meta.get("callout_type_hint") == "warning"

    def test_caution_detected_as_warning(self):
        """'Caution' is classified as warning type."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 200),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Caution:"}),
        ]
        result = enhance_callout_detection(blocks, [])
        assert result[0].grouping_meta.get("callout_type_hint") == "warning"

    def test_important_detected_as_warning(self):
        """'Important' is classified as warning type."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 200),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Important"}),
        ]
        result = enhance_callout_detection(blocks, [])
        assert result[0].grouping_meta.get("callout_type_hint") == "warning"

    def test_box_heading_detected(self):
        """A callout with 'Did You Know' gets callout_type_hint='box'."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 200),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Did You Know"}),
        ]
        result = enhance_callout_detection(blocks, [])
        assert result[0].grouping_meta.get("callout_type_hint") == "box"

    def test_remember_detected_as_box(self):
        """'Remember' is classified as box type."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 200),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Remember"}),
        ]
        result = enhance_callout_detection(blocks, [])
        assert result[0].grouping_meta.get("callout_type_hint") == "box"

    def test_border_cue_detection(self):
        """Unicode box-drawing characters are detected as borders."""
        lines = [
            _line("─" * 20, page=0, y=98.0, bbox=(50, 98, 400, 100)),
            _line("Some note text", page=0, y=110.0),
            _line("─" * 20, page=0, y=130.0, bbox=(50, 130, 400, 132)),
        ]
        borders = detect_border_cues(lines, 0)
        assert len(borders) >= 2

    def test_border_enhances_callout(self):
        """A callout near a border gets has_border=True."""
        blocks = [
            _block("callout-label", 0, (50, 100, 400, 130),
                   grouping_meta={"anchor": "callout-label",
                                  "label_line": "Note:"}),
        ]
        lines = [
            _line("─" * 20, page=0, y=95.0, bbox=(50, 95, 400, 97)),
            _line("Note:", page=0, y=100.0, bbox=(50, 100, 400, 112)),
        ]
        result = enhance_callout_detection(blocks, lines)
        assert result[0].grouping_meta.get("has_border") is True
        assert result[0].grouping_meta.get("visual_grouping") is True

    def test_non_callout_blocks_unchanged(self):
        """Non-callout blocks are not modified."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100)),
        ]
        result = enhance_callout_detection(blocks, [])
        assert "callout_type_hint" not in result[0].grouping_meta

    def test_hyphen_border_detection(self):
        """Lines of hyphens are detected as borders."""
        lines = [_line("-" * 30, page=0, y=100.0)]
        borders = detect_border_cues(lines, 0)
        assert len(borders) == 1

    def test_underscore_border_detection(self):
        """Lines of underscores are detected as borders."""
        lines = [_line("_" * 15, page=0, y=100.0)]
        borders = detect_border_cues(lines, 0)
        assert len(borders) == 1


# =========================================================================
# 7. Table false-positive suppression
# =========================================================================

class TestTableFalsePositiveSuppression:
    """Tests for suppress_table_false_positives()."""

    def test_genuine_table_kept(self):
        """A real table (multiple rows/cols, sufficient area) is kept."""
        blocks = [
            _block("table", 0, (50, 100, 400, 300),
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 5, "columns": 3}}),
        ]
        result = suppress_table_false_positives(blocks)
        assert len(result) == 1

    def test_single_cell_table_suppressed(self):
        """A 1×1 table is suppressed as a formatting artifact."""
        blocks = [
            _block("table", 0, (50, 100, 400, 300),
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 1, "columns": 1}}),
        ]
        result = suppress_table_false_positives(blocks)
        assert len(result) == 0

    def test_tiny_table_suppressed(self):
        """A very small table is suppressed."""
        blocks = [
            _block("table", 0, (50, 100, 70, 110),  # 20 × 10 = 200 sq pts
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 2, "columns": 2}}),
        ]
        result = suppress_table_false_positives(blocks)
        assert len(result) == 0

    def test_caption_only_table_kept(self):
        """A caption-only stub (rows=0, cols=0) is kept for metadata."""
        blocks = [
            _block("table", 0, (50, 100, 400, 120),
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 0, "columns": 0}}),
        ]
        result = suppress_table_false_positives(blocks)
        assert len(result) == 1

    def test_prose_grid_suppressed(self):
        """A 'table' whose lines are mostly prose sentences is suppressed."""
        blocks = [
            _block("table", 0, (50, 100, 400, 300),
                   lines=[
                       _line("This is a sentence. Another follows.", y=100),
                       _line("More text here. Capital starts.", y=115),
                       _line("Yet more prose. And more too.", y=130),
                       _line("Final line. Done now.", y=145),
                   ],
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 4, "columns": 2}}),
        ]
        result = suppress_table_false_positives(blocks)
        assert len(result) == 0

    def test_non_table_blocks_unaffected(self):
        """Non-table blocks pass through unmodified."""
        blocks = [
            _block("figure", 0, (50, 100, 400, 300)),
            _block("equation-cluster", 0, (50, 400, 400, 500)),
        ]
        result = suppress_table_false_positives(blocks)
        assert len(result) == 2

    def test_large_multi_col_table_kept(self):
        """A large table with many columns is genuine."""
        blocks = [
            _block("table", 0, (50, 100, 500, 400),
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 10, "columns": 5}}),
        ]
        result = suppress_table_false_positives(blocks)
        assert len(result) == 1


# =========================================================================
# 8. Deterministic ordering and general cleanup
# =========================================================================

class TestGeneralCleanup:
    """Tests for remove_duplicate_blocks() and remove_contained_blocks()."""

    def test_same_kind_duplicate_removal(self):
        """Two blocks of the same kind with high IoU: keep the richer one."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100), lines=[_line("Cap")],
                   block_id="fig-1"),
            _block("figure", 0, (10, 10, 100, 100), block_id="fig-2",
                   grouping_meta={"anchor": "figure"}),
        ]
        result = remove_duplicate_blocks(blocks)
        assert len(result) == 1
        assert result[0].block_id == "fig-1"  # has more lines

    def test_different_kind_not_deduped(self):
        """Different kinds with same bbox are NOT deduped by this pass."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100), block_id="fig"),
            _block("table", 0, (10, 10, 100, 100), block_id="tab"),
        ]
        result = remove_duplicate_blocks(blocks)
        assert len(result) == 2

    def test_low_overlap_not_deduped(self):
        """Same kind with low IoU are NOT deduped."""
        blocks = [
            _block("figure", 0, (10, 10, 100, 100)),
            _block("figure", 0, (200, 200, 300, 300),
                   grouping_meta={"anchor": "figure"}),
        ]
        result = remove_duplicate_blocks(blocks)
        assert len(result) == 2

    def test_contained_block_removed(self):
        """A block fully inside a higher-priority block is removed."""
        blocks = [
            _block("equation-cluster", 0, (10, 10, 400, 400)),
            _block("definition-candidate", 0, (50, 50, 200, 200)),
        ]
        result = remove_contained_blocks(blocks)
        assert len(result) == 1
        assert result[0].grouping_meta["anchor"] == "equation-cluster"

    def test_child_block_not_removed(self):
        """A block that is already a child of its container is NOT removed."""
        parent = _block("equation-cluster", 0, (10, 10, 400, 400),
                        block_id="parent")
        child = _block("equation-line", 0, (50, 50, 200, 200),
                       block_id="child")
        child.parent = "parent"
        blocks = [parent, child]
        result = remove_contained_blocks(blocks)
        assert len(result) == 2

    def test_lower_priority_container_no_suppression(self):
        """A low-priority container does NOT suppress a high-priority inner."""
        blocks = [
            _block("definition-candidate", 0, (10, 10, 400, 400)),
            _block("equation-cluster", 0, (50, 50, 200, 200)),
        ]
        result = remove_contained_blocks(blocks)
        assert len(result) == 2


class TestDeterministicOrdering:
    """Tests that the final output is always deterministically ordered."""

    def test_sorted_by_page_then_y(self):
        """Output blocks are sorted by (page, y0)."""
        blocks = [
            _block("figure", 1, (10, 300, 100, 400)),
            _block("table", 0, (10, 50, 100, 150)),
            _block("equation-cluster", 0, (10, 200, 100, 250)),
            _block("diagram", 1, (10, 100, 100, 200)),
        ]
        result = apply_layout_quality_passes(blocks)
        pages = [(b.page, b.bbox[1]) for b in result]
        assert pages == sorted(pages)

    def test_stable_ordering_across_runs(self):
        """Same input always produces the same output order."""
        blocks = [
            _block("figure", 0, (10, 300, 100, 400), block_id="a"),
            _block("table", 0, (10, 50, 100, 150), block_id="b"),
            _block("equation-cluster", 0, (10, 200, 100, 250), block_id="c"),
        ]
        result1 = apply_layout_quality_passes(list(blocks))
        result2 = apply_layout_quality_passes(list(blocks))
        ids1 = [b.block_id for b in result1]
        ids2 = [b.block_id for b in result2]
        assert ids1 == ids2

    def test_empty_input(self):
        """Empty input returns empty output."""
        assert apply_layout_quality_passes([]) == []

    def test_single_block(self):
        """Single block passes through unchanged."""
        blocks = [_block("figure", 0, (10, 10, 100, 100))]
        result = apply_layout_quality_passes(blocks)
        assert len(result) == 1


# =========================================================================
# Cross-kind visual region suppression
# =========================================================================

class TestCrossKindVisualDuplicates:
    """Tests for suppress_cross_kind_visual_duplicates()."""

    def test_overlapping_figure_diagram_regions(self):
        """Overlapping figure and diagram VisualRegions: keep figure."""
        layout = {
            "figures": [_visual_region("figure", 0, (10, 10, 200, 200))],
            "diagrams": [_visual_region("diagram", 0, (10, 10, 200, 200))],
            "tables": [],
            "equations": [],
        }
        result = suppress_cross_kind_visual_duplicates(layout)
        assert len(result["figures"]) == 1
        assert len(result["diagrams"]) == 0

    def test_non_overlapping_regions_kept(self):
        """Non-overlapping regions of different kinds are all kept."""
        layout = {
            "figures": [_visual_region("figure", 0, (10, 10, 100, 100))],
            "diagrams": [_visual_region("diagram", 0, (200, 200, 400, 400))],
            "tables": [],
            "equations": [],
        }
        result = suppress_cross_kind_visual_duplicates(layout)
        assert len(result["figures"]) == 1
        assert len(result["diagrams"]) == 1

    def test_table_beats_figure(self):
        """Table (priority 80) beats figure (priority 70)."""
        layout = {
            "figures": [_visual_region("figure", 0, (10, 10, 200, 200))],
            "tables": [_visual_region("table", 0, (10, 10, 200, 200))],
            "diagrams": [],
            "equations": [],
        }
        result = suppress_cross_kind_visual_duplicates(layout)
        assert len(result["tables"]) == 1
        assert len(result["figures"]) == 0

    def test_empty_layout(self):
        """Empty layout passes through."""
        layout = {"figures": [], "tables": [], "equations": [], "diagrams": []}
        result = suppress_cross_kind_visual_duplicates(layout)
        assert all(len(v) == 0 for v in result.values())

    def test_different_pages_not_suppressed(self):
        """Same bbox on different pages should not suppress."""
        layout = {
            "figures": [_visual_region("figure", 0, (10, 10, 200, 200))],
            "diagrams": [_visual_region("diagram", 1, (10, 10, 200, 200))],
            "tables": [],
            "equations": [],
        }
        result = suppress_cross_kind_visual_duplicates(layout)
        assert len(result["figures"]) == 1
        assert len(result["diagrams"]) == 1


# =========================================================================
# Bbox utility tests
# =========================================================================

class TestBboxUtilities:
    """Tests for bbox helper functions."""

    def test_iou_identical(self):
        assert _bbox_iou((0, 0, 100, 100), (0, 0, 100, 100)) == 1.0

    def test_iou_no_overlap(self):
        assert _bbox_iou((0, 0, 50, 50), (100, 100, 200, 200)) == 0.0

    def test_iou_partial(self):
        iou = _bbox_iou((0, 0, 100, 100), (50, 50, 150, 150))
        assert 0.1 < iou < 0.3  # 50×50 / (10000 + 10000 - 2500)

    def test_area(self):
        assert _bbox_area((0, 0, 100, 100)) == 10000.0
        assert _bbox_area((50, 50, 50, 50)) == 0.0

    def test_contains(self):
        assert _bbox_contains((0, 0, 200, 200), (50, 50, 150, 150))
        assert not _bbox_contains((50, 50, 150, 150), (0, 0, 200, 200))

    def test_contains_with_tolerance(self):
        """Slightly outside but within tolerance still counts."""
        assert _bbox_contains((10, 10, 200, 200), (8, 8, 195, 195), tolerance=5.0)


# =========================================================================
# Integration test — full apply_layout_quality_passes pipeline
# =========================================================================

class TestFullPipeline:
    """End-to-end integration tests for apply_layout_quality_passes."""

    def test_mixed_blocks_cleaned(self):
        """A realistic mix of blocks is cleaned deterministically."""
        blocks = [
            # Genuine figure
            _block("figure", 0, (50, 50, 300, 200), block_id="fig1"),
            # Diagram overlapping the figure (should be suppressed)
            _block("diagram", 0, (50, 50, 300, 200), block_id="diag1"),
            # Genuine table
            _block("table", 0, (50, 300, 400, 500), block_id="tab1",
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 5, "columns": 3}}),
            # Fake table (1×1 cell)
            _block("table", 0, (50, 550, 400, 650), block_id="tab2",
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 1, "columns": 1}}),
            # Equation cluster
            _block("equation-cluster", 1, (50, 100, 400, 120),
                   lines=[_line("F = ma", page=1, y=100)],
                   children=[], block_id="eq1"),
        ]
        result = apply_layout_quality_passes(blocks)
        ids = {b.block_id for b in result}
        assert "fig1" in ids        # figure kept
        assert "diag1" not in ids   # diagram suppressed (overlaps figure)
        assert "tab1" in ids        # genuine table kept
        assert "tab2" not in ids    # fake table suppressed
        assert "eq1" in ids         # equation kept

    def test_determinism_guarantee(self):
        """Running the same input twice produces identical output."""
        blocks = [
            _block("figure", 0, (50, 50, 300, 200), block_id="f"),
            _block("diagram", 0, (50, 50, 300, 200), block_id="d"),
            _block("equation-cluster", 0, (50, 300, 400, 400), block_id="e"),
            _block("table", 0, (50, 500, 400, 600), block_id="t",
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 3, "columns": 2}}),
        ]
        r1 = apply_layout_quality_passes(list(blocks))
        r2 = apply_layout_quality_passes(list(blocks))
        assert [b.block_id for b in r1] == [b.block_id for b in r2]
        assert [b.bbox for b in r1] == [b.bbox for b in r2]

    def test_no_blocks_returns_empty(self):
        assert apply_layout_quality_passes([]) == []

    def test_all_passes_applied_in_order(self):
        """Verify all passes run by checking their cumulative effects."""
        # Create a scenario that would be affected by multiple passes:
        # - overlapping figure+diagram (pass 2)
        # - fake 1×1 table (pass 1)
        # - duplicate figures (pass 8)
        blocks = [
            _block("figure", 0, (10, 10, 200, 200), block_id="f1",
                   lines=[_line("Caption 1")]),
            _block("figure", 0, (10, 10, 200, 200), block_id="f2",
                   grouping_meta={"anchor": "figure"}),  # duplicate
            _block("diagram", 0, (10, 10, 200, 200), block_id="d1"),
            _block("table", 0, (10, 300, 30, 310), block_id="t1",
                   grouping_meta={"anchor": "table",
                                  "region_extra": {"rows": 1, "columns": 1}}),
        ]
        result = apply_layout_quality_passes(blocks)
        ids = {b.block_id for b in result}
        # Diagram suppressed by cross-kind IoU (pass 2)
        assert "d1" not in ids
        # Fake table suppressed by pass 1
        assert "t1" not in ids
        # One of the duplicate figures suppressed by pass 8
        assert len([b for b in result if b.grouping_meta.get("anchor") == "figure"]) == 1
