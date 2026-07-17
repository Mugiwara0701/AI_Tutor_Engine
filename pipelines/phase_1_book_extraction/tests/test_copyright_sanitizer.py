"""
tests/test_copyright_sanitizer.py — tests for Milestone 3.2's
modules/copyright_sanitizer.py (Copyright-Safe Serialization).

Fixtures here are plain dicts built to match the shape pipeline.py's own
equation/educational-object construction actually produces (same "no
pipeline.py execution needed" pattern tests/test_structural_validator.py
already established) -- never an actual pipeline.py run.
"""
from __future__ import annotations

import copy

import config
from modules import copyright_sanitizer as cs


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------
def equation(**overrides):
    base = {
        "id": "eq-1",
        "urn": "urn:ncert:eq-1",
        "object_type": "equation",
        "page": 4,
        "bbox": {"x0": 0, "y0": 0, "x1": 1, "y1": 1, "page": 4},
        "latex": "E = mc^2",
        "spoken_form": "E equals m c squared",
        "variables": ["E", "m", "c"],
        "semantic_meaning": "Mass-energy equivalence.",
        "confidence": 0.9,
        "raw_text": "Einstein showed that E = mc^2 relates mass and energy directly.",
        "block_type": "Formula Box",
        "educational_intent": "introduces_reusable_knowledge",
        "vlm_analysis_skipped": False,
    }
    base.update(overrides)
    return base


def deterministic_procedure_object(**overrides):
    base = {
        "id": "obj-1",
        "block_id": "block-1",
        "block_type": "Worked Example",
        "priority": "high",
        "educational_object_type": "formula_or_procedure",
        "source": "deterministic",
        "confidence": 0.75,
        "reusable_procedure": "Step 1: Identify the known values | Step 2: Apply the formula",
        "procedure_steps": ["Step 1: Identify the known values", "Step 2: Apply the formula"],
        "discarded_substitutions_count": 2,
    }
    base.update(overrides)
    return base


def vlm_fallback_procedure_object(**overrides):
    base = {
        "id": "obj-2",
        "block_id": "block-2",
        "block_type": "Formula Box",
        "priority": "high",
        "educational_object_type": "formula_or_procedure",
        "source": "vlm_fallback",
        "confidence": 0.5,
        "reusable_formula": "v = u + at",
        "reusable_procedure": "Velocity equals initial velocity plus acceleration times time.",
    }
    base.update(overrides)
    return base


def deterministic_syntax_object(**overrides):
    base = {
        "id": "obj-3",
        "block_id": "block-3",
        "block_type": "Programming Syntax",
        "priority": "medium",
        "educational_object_type": "programming_syntax",
        "source": "deterministic",
        "confidence": 0.8,
        "reusable_syntax": "def add(a, b):\n    return a + b\n",
    }
    base.update(overrides)
    return base


def deterministic_accounting_rule_object(**overrides):
    base = {
        "id": "obj-5",
        "block_id": "block-5",
        "block_type": "Golden Rule Box",
        "priority": "high",
        "educational_object_type": "accounting_format",
        "source": "deterministic",
        "confidence": 0.85,
        "format_type": "accounting_rule",
        "rules": [
            "Debit the receiver, Credit the giver",
            "Debit what comes in, Credit what goes out",
        ],
    }
    base.update(overrides)
    return base


def content_block(**overrides):
    base = {
        "id": "activity-1",
        "urn": "urn:ncert:activity-1",
        "object_type": "activity",
        "activity_type": "class_activity",
        "page": 12,
        "semantic_description": "Students form groups and measure the length of the classroom using a metre "
                                 "scale, recording each group's reading on the board before discussing sources "
                                 "of error.",
        "educational_purpose": "",
    }
    base.update(overrides)
    return base


def visual_region(**overrides):
    base = {
        "id": "figure-1",
        "urn": "urn:ncert:figure-1",
        "object_type": "figure",
        "page": 7,
        "title": "",
        "caption": "Fig 3.2 A simple pendulum",
        "figure_type": "figure",
        "confidence": 0.5,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# sanitize_equations
# --------------------------------------------------------------------------
class TestSanitizeEquations:
    def test_raw_text_removed_and_replaced_with_hint(self):
        report = cs.sanitize_equations([equation()])
        clean = report.sanitized[0]
        assert "raw_text" not in clean
        assert clean["has_raw_text_hint"] is True

    def test_raw_text_captured_in_debug_entry(self):
        eq = equation()
        report = cs.sanitize_equations([eq])
        assert len(report.debug_entries) == 1
        entry = report.debug_entries[0]
        assert entry["record_type"] == "equation"
        assert entry["record_key"] == "eq-1"
        assert entry["raw_text"] == eq["raw_text"]

    def test_no_raw_text_means_no_debug_entry_and_false_hint(self):
        eq = equation(raw_text="")
        report = cs.sanitize_equations([eq])
        assert report.debug_entries == []
        assert report.sanitized[0]["has_raw_text_hint"] is False

    def test_vlm_raw_output_and_errors_moved_to_debug(self):
        eq = equation(vlm_raw_output="{bad json", vlm_validation_errors=["missing field: latex"])
        report = cs.sanitize_equations([eq])
        clean = report.sanitized[0]
        assert "vlm_raw_output" not in clean
        assert "vlm_validation_errors" not in clean
        entry = report.debug_entries[0]
        assert entry["vlm_raw_output"] == "{bad json"
        assert entry["vlm_validation_errors"] == ["missing field: latex"]

    def test_safe_fields_pass_through_unchanged(self):
        eq = equation()
        report = cs.sanitize_equations([eq])
        clean = report.sanitized[0]
        for safe_field in ("id", "page", "latex", "spoken_form", "variables",
                            "semantic_meaning", "confidence", "block_type",
                            "educational_intent"):
            assert clean[safe_field] == eq[safe_field]

    def test_does_not_mutate_input(self):
        eq = equation()
        original = copy.deepcopy(eq)
        cs.sanitize_equations([eq])
        assert eq == original

    def test_empty_list(self):
        report = cs.sanitize_equations([])
        assert report.sanitized == []
        assert report.debug_entries == []

    def test_falls_back_to_index_key_when_no_id(self):
        eq = equation()
        eq.pop("id")
        report = cs.sanitize_equations([eq])
        assert report.debug_entries[0]["record_key"] == "_index_0"


# --------------------------------------------------------------------------
# sanitize_educational_objects — reusable_procedure / procedure_steps
# --------------------------------------------------------------------------
class TestSanitizeProcedureObjects:
    def test_deterministic_procedure_stripped_to_structural_metadata(self):
        report = cs.sanitize_educational_objects([deterministic_procedure_object()])
        clean = report.sanitized[0]
        assert "reusable_procedure" not in clean
        assert "procedure_steps" not in clean
        assert clean["procedure_step_count"] == 2
        assert clean["procedure_step_marker_types"] == ["step_n", "step_n"]

    def test_deterministic_procedure_debug_entry_carries_original_text(self):
        obj = deterministic_procedure_object()
        report = cs.sanitize_educational_objects([obj])
        entry = report.debug_entries[0]
        assert entry["record_type"] == "educational_object"
        assert entry["reusable_procedure"] == obj["reusable_procedure"]
        assert entry["procedure_steps"] == obj["procedure_steps"]

    def test_vlm_fallback_procedure_is_left_untouched(self):
        obj = vlm_fallback_procedure_object()
        report = cs.sanitize_educational_objects([obj])
        clean = report.sanitized[0]
        # VLM-fallback content already went through paraphrase + word-cap
        # (see semantic_processor._enforce_word_cap) -- this module must
        # not touch it.
        assert clean["reusable_procedure"] == obj["reusable_procedure"]
        assert report.debug_entries == []

    def test_numbered_and_prose_marker_shapes(self):
        obj = deterministic_procedure_object(
            reusable_procedure="1) Do X | First, do Y | Then do Z | Finally, do W",
            procedure_steps=["1) Do X", "First, do Y", "Then do Z", "Finally, do W"],
        )
        report = cs.sanitize_educational_objects([obj])
        assert report.sanitized[0]["procedure_step_marker_types"] == [
            "numbered", "first", "then", "finally",
        ]

    def test_journal_procedure_type_marker(self):
        obj = deterministic_procedure_object(
            reusable_procedure="Debit the receiver, credit the giver",
            procedure_steps=["Debit the receiver, credit the giver"],
            procedure_type="journal_entry_rule",
        )
        report = cs.sanitize_educational_objects([obj])
        clean = report.sanitized[0]
        assert clean["procedure_step_marker_types"] == ["journal_keyword"]
        # procedure_type itself is already structural/SAFE -- untouched.
        assert clean["procedure_type"] == "journal_entry_rule"

    def test_discarded_substitutions_count_untouched(self):
        obj = deterministic_procedure_object()
        report = cs.sanitize_educational_objects([obj])
        assert report.sanitized[0]["discarded_substitutions_count"] == 2

    def test_object_with_no_procedure_fields_is_untouched(self):
        obj = {
            "id": "obj-4", "educational_object_type": "concept", "source": "deterministic",
            "term": "Photosynthesis",
        }
        report = cs.sanitize_educational_objects([obj])
        assert report.sanitized[0] == obj
        assert report.debug_entries == []

    def test_does_not_mutate_input(self):
        obj = deterministic_procedure_object()
        original = copy.deepcopy(obj)
        cs.sanitize_educational_objects([obj])
        assert obj == original


# --------------------------------------------------------------------------
# sanitize_educational_objects — reusable_syntax
# --------------------------------------------------------------------------
class TestSanitizeSyntaxObjects:
    def test_deterministic_syntax_stripped_to_structural_metadata_by_default(self):
        assert config.PRESERVE_CODE_SNIPPETS_VERBATIM is False
        obj = deterministic_syntax_object()
        report = cs.sanitize_educational_objects([obj])
        clean = report.sanitized[0]
        assert "reusable_syntax" not in clean
        assert clean["code_line_count"] == 2
        assert clean["has_code_content"] is True

    def test_deterministic_syntax_debug_entry_carries_original_code(self):
        obj = deterministic_syntax_object()
        report = cs.sanitize_educational_objects([obj])
        assert report.debug_entries[0]["reusable_syntax"] == obj["reusable_syntax"]

    def test_preserve_flag_keeps_code_verbatim(self, monkeypatch):
        monkeypatch.setattr(config, "PRESERVE_CODE_SNIPPETS_VERBATIM", True)
        obj = deterministic_syntax_object()
        report = cs.sanitize_educational_objects([obj])
        clean = report.sanitized[0]
        assert clean["reusable_syntax"] == obj["reusable_syntax"]
        assert report.debug_entries == []

    def test_pseudocode_kind_field_untouched(self):
        obj = deterministic_syntax_object(syntax_kind="pseudocode")
        report = cs.sanitize_educational_objects([obj])
        assert report.sanitized[0]["syntax_kind"] == "pseudocode"

    def test_empty_code_text(self):
        obj = deterministic_syntax_object(reusable_syntax="")
        report = cs.sanitize_educational_objects([obj])
        clean = report.sanitized[0]
        assert clean["code_line_count"] == 0
        assert clean["has_code_content"] is False
        assert report.debug_entries == []


# --------------------------------------------------------------------------
# sanitize_educational_objects — rules (accounting_format/accounting_rule)
# --------------------------------------------------------------------------
class TestSanitizeAccountingRuleObjects:
    def test_deterministic_rules_stripped_to_structural_metadata(self):
        report = cs.sanitize_educational_objects([deterministic_accounting_rule_object()])
        clean = report.sanitized[0]
        assert "rules" not in clean
        assert clean["matched_rule_count"] == 2
        assert clean["matched_rule_types"] == ["debit_receiver", "debit_comes_in"]

    def test_debug_entry_carries_original_rule_lines(self):
        obj = deterministic_accounting_rule_object()
        report = cs.sanitize_educational_objects([obj])
        entry = report.debug_entries[0]
        assert entry["record_type"] == "educational_object"
        assert entry["rules"] == obj["rules"]

    def test_all_six_rule_categories_classified(self):
        obj = deterministic_accounting_rule_object(rules=[
            "Debit the receiver",
            "Credit the giver",
            "Debit what comes in",
            "Credit what goes out",
            "Debit all expenses and losses",
            "Credit all incomes and gains",
            "Some unrelated line that happens to be in the list",
        ])
        report = cs.sanitize_educational_objects([obj])
        assert report.sanitized[0]["matched_rule_types"] == [
            "debit_receiver", "credit_giver", "debit_comes_in", "credit_goes_out",
            "debit_expenses_losses", "credit_incomes_gains", "other",
        ]

    def test_non_accounting_rule_format_type_untouched(self):
        obj = deterministic_accounting_rule_object(format_type="journal_entry", rules=None)
        obj.pop("rules")
        obj["columns"] = ["date", "particulars", "debit", "credit"]
        report = cs.sanitize_educational_objects([obj])
        assert report.sanitized[0] == obj
        assert report.debug_entries == []

    def test_does_not_mutate_input(self):
        obj = deterministic_accounting_rule_object()
        original = copy.deepcopy(obj)
        cs.sanitize_educational_objects([obj])
        assert obj == original


# --------------------------------------------------------------------------
# sanitize_content_blocks
# --------------------------------------------------------------------------
class TestSanitizeContentBlocks:
    def test_raw_description_removed_and_replaced_with_empty_string(self):
        report = cs.sanitize_content_blocks([content_block()], record_type="activity")
        clean = report.sanitized[0]
        assert clean["semantic_description"] == ""
        assert clean["has_semantic_description_hint"] is True

    def test_debug_entry_carries_original_description(self):
        block = content_block()
        report = cs.sanitize_content_blocks([block], record_type="activity")
        entry = report.debug_entries[0]
        assert entry["record_type"] == "activity"
        assert entry["record_key"] == "activity-1"
        assert entry["semantic_description"] == block["semantic_description"]

    def test_empty_description_means_no_debug_entry_and_false_hint(self):
        block = content_block(semantic_description="")
        report = cs.sanitize_content_blocks([block], record_type="note")
        assert report.debug_entries == []
        assert report.sanitized[0]["has_semantic_description_hint"] is False

    def test_other_fields_untouched(self):
        block = content_block()
        report = cs.sanitize_content_blocks([block], record_type="activity")
        clean = report.sanitized[0]
        assert clean["id"] == block["id"]
        assert clean["activity_type"] == block["activity_type"]
        assert clean["page"] == block["page"]

    def test_does_not_mutate_input(self):
        block = content_block()
        original = copy.deepcopy(block)
        cs.sanitize_content_blocks([block], record_type="activity")
        assert block == original

    def test_empty_list(self):
        report = cs.sanitize_content_blocks([], record_type="box")
        assert report.sanitized == []
        assert report.debug_entries == []


# --------------------------------------------------------------------------
# sanitize_visual_captions
# --------------------------------------------------------------------------
class TestSanitizeVisualCaptions:
    def test_short_caption_passes_through_unchanged(self):
        region = visual_region()
        report = cs.sanitize_visual_captions([region], record_type="figure")
        clean = report.sanitized[0]
        assert clean["caption"] == region["caption"]
        assert report.debug_entries == []

    def test_overlong_caption_truncated_and_captured_in_debug(self):
        long_caption = " ".join(f"word{i}" for i in range(40))
        region = visual_region(caption=long_caption)
        report = cs.sanitize_visual_captions([region], record_type="figure")
        clean = report.sanitized[0]
        assert clean["caption"] != long_caption
        assert len(clean["caption"].split()) <= config.MAX_CAPTION_WORDS
        entry = report.debug_entries[0]
        assert entry["record_type"] == "figure"
        assert entry["caption"] == long_caption

    def test_overlong_title_truncated_independently_of_caption(self):
        long_title = " ".join(f"t{i}" for i in range(30))
        region = visual_region(title=long_title)
        report = cs.sanitize_visual_captions([region], record_type="table")
        clean = report.sanitized[0]
        assert len(clean["title"].split()) <= config.MAX_CAPTION_WORDS
        assert clean["caption"] == region["caption"]  # unaffected
        assert report.debug_entries[0]["title"] == long_title

    def test_empty_caption_and_title_untouched(self):
        region = visual_region(caption="", title="")
        report = cs.sanitize_visual_captions([region], record_type="diagram")
        clean = report.sanitized[0]
        assert clean["caption"] == "" and clean["title"] == ""
        assert report.debug_entries == []

    def test_does_not_mutate_input(self):
        long_caption = " ".join(f"word{i}" for i in range(40))
        region = visual_region(caption=long_caption)
        original = copy.deepcopy(region)
        cs.sanitize_visual_captions([region], record_type="figure")
        assert region == original

    def test_empty_list(self):
        report = cs.sanitize_visual_captions([], record_type="table")
        assert report.sanitized == []
        assert report.debug_entries == []


# --------------------------------------------------------------------------
# sanitize_chapter_records (convenience entry point)
# --------------------------------------------------------------------------
class TestSanitizeChapterRecords:
    def test_combines_both_lists_debug_entries(self):
        eqs, objs, debug_entries = cs.sanitize_chapter_records(
            [equation()],
            [deterministic_procedure_object(), deterministic_syntax_object()],
        )
        assert len(eqs) == 1
        assert len(objs) == 2
        assert len(debug_entries) == 3
        record_types = sorted(e["record_type"] for e in debug_entries)
        assert record_types == ["educational_object", "educational_object", "equation"]

    def test_empty_inputs(self):
        eqs, objs, debug_entries = cs.sanitize_chapter_records([], [])
        assert eqs == [] and objs == [] and debug_entries == []

    def test_fields_removed_count_tracked_per_report(self):
        report = cs.sanitize_equations([equation(), equation(id="eq-2", raw_text="")])
        # eq-1 loses raw_text (1); eq-2 loses nothing.
        assert report.fields_removed_count == 1
