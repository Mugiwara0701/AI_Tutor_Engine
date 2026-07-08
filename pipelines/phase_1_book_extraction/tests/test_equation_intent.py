"""
tests/test_equation_intent.py — unit tests for modules/equation_intent.py,
the dynamic educational-intent gate that decides whether an equation should
go through the expensive equation_analysis VLM call (ISSUE 3 / ISSUE 4).

Run: python -m pytest tests/test_equation_intent.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from modules import equation_intent


# ---------------------------------------------------------------------------
# block_type-driven routing (the primary, Stage-B-derived signal)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("block_type", ["Formula Box", "Law", "Definition"])
def test_reusable_block_types_run_vlm(block_type):
    assert equation_intent.introduces_reusable_knowledge(block_type, "") is True


@pytest.mark.parametrize("block_type", [
    "Worked Example", "Exercise", "Activity", "Reference", "Footer", "Header", "Summary",
])
def test_non_reusable_block_types_skip_vlm(block_type):
    assert equation_intent.introduces_reusable_knowledge(block_type, "") is False


# ---------------------------------------------------------------------------
# Fallback text-cue routing (Ambiguous / no matching Stage A/B block at all)
# -- generic instructional-language cues, not any one publisher's labels.
# ---------------------------------------------------------------------------
def test_ambiguous_block_type_falls_back_to_reusable_text_cue():
    text = "The law of conservation of momentum states that ..."
    assert equation_intent.introduces_reusable_knowledge(None, text) is True
    assert equation_intent.introduces_reusable_knowledge("Ambiguous", text) is True


def test_ambiguous_block_type_falls_back_to_non_reusable_text_cue():
    text = "Solve for x: substitute the given values and calculate the result."
    assert equation_intent.introduces_reusable_knowledge(None, text) is False


def test_unknown_with_no_cues_defaults_to_running_vlm():
    """Conservative default: an equation this pipeline genuinely cannot
    classify one way or the other still gets analyzed, so Issue 3's
    cost-cutting never risks silently starving Master JSON of real
    semantics for something that might be a genuine formula (Issue 5/6)."""
    assert equation_intent.introduces_reusable_knowledge(None, "") is True
    assert equation_intent.introduces_reusable_knowledge("SomeNewBlockType", "xyz") is True


def test_skip_reason_is_human_readable_and_non_empty():
    reason = equation_intent.skip_reason("Worked Example", "")
    assert "Worked Example" in reason
    reason2 = equation_intent.skip_reason(None, "calculate the total and substitute the values")
    assert reason2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
