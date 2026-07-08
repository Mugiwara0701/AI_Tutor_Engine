"""
tests/test_prompt_manager.py — exercises prompt_manager's functional core
WITHOUT needing Qwen or a GPU. A FakeAdapter (implements ModelAdapter) is
used so these tests run anywhere and are fast; the real qwen_adapter gets
its own separate validation-spike smoke test in step 3, per the frozen
Milestone 1 order.

Run: python -m pytest tests/test_prompt_manager.py -v
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import json as _json
from prompt_manager.model_adapter import ModelAdapter, AdapterResponse
from prompt_manager.prompt_manager import PromptManager, TaskContext, MissingContextError
from prompt_manager import context_builder, task_registry, output_contract


# ---------------------------------------------------------------------------
# Fake adapter: returns whatever canned response(s) the test configures, in
# order, one per call. Implements generate_json() the same way a real
# adapter would — parse whatever generate() returns — so these tests still
# exercise prompt_manager's retry/validation logic without needing Qwen.
# Adapter-specific cleanup (markdown fences etc.) is NOT this test double's
# job to simulate; that's covered separately in test_qwen_adapter.py.
# ---------------------------------------------------------------------------
class FakeAdapter(ModelAdapter):
    adapter_id = "fake-adapter-for-tests"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate(self, prompt, images=None, max_new_tokens=None):
        self.calls.append({"prompt": prompt, "images": images, "max_new_tokens": max_new_tokens})
        if not self._responses:
            raise RuntimeError("FakeAdapter ran out of canned responses")
        return self._responses.pop(0)

    def generate_json(self, prompt, images=None, max_new_tokens=None):
        raw = self.generate(prompt, images=images, max_new_tokens=max_new_tokens)
        try:
            parsed = _json.loads(raw)
            return AdapterResponse(success=True, raw_output=raw, cleaned_output=raw, parsed_output=parsed)
        except Exception:
            return AdapterResponse(success=False, raw_output=raw, cleaned_output=raw,
                                    parsed_output=None, error_message="FakeAdapter: model output was not valid JSON")


VALID_CONCEPT_RESPONSE = json.dumps({
    "concepts": [
        {"name": "Gross Domestic Product", "aliases": ["GDP"], "importance": "high"},
        {"name": "National Income", "aliases": [], "importance": "medium"},
    ]
})

VALID_FIGURE_RESPONSE = json.dumps({
    "figure_type": {"value": "diagram", "confidence": 0.9, "evidence_basis": "arrows and labeled boxes visible"},
    "semantic_description": {"value": "Shows the circular flow of income between households and firms.",
                              "confidence": 0.85, "evidence_basis": "overall visual layout"},
    "key_visual_elements": [
        {"value": "arrow from household to firm", "confidence": 0.9, "evidence_basis": "visible arrow"},
        {"value": "arrow from firm to household", "confidence": 0.9, "evidence_basis": "visible arrow"},
        {"value": "labeled market box", "confidence": 0.8, "evidence_basis": "labeled rectangle"},
    ],
    "visual_relationships": [
        {"from_element": "household", "to_element": "firm", "relationship_type": "supplies labor to"},
    ],
    "layout": {"value": "circular flow diagram", "confidence": 0.8, "evidence_basis": "circular arrangement of boxes"},
    "educational_purpose": {"value": "Illustrates the flow of goods, services, and money.",
                             "confidence": 0.85, "evidence_basis": "standard textbook diagram type"},
    "concepts": ["circular flow", "income"],
    "related_topics": ["national income accounting"],
    "importance": {"value": "high", "confidence": 0.8, "evidence_basis": "core chapter diagram"},
    "difficulty": {"value": "medium", "confidence": 0.7, "evidence_basis": "requires understanding two-sector flow"},
    "animation_candidate": {"value": True, "confidence": 0.75, "evidence_basis": "flow arrows animate well"},
})

INVALID_FIGURE_RESPONSE_EMPTY_ELEMENTS = json.dumps({
    "figure_type": {"value": "diagram", "confidence": 0.9, "evidence_basis": "x"},
    "semantic_description": {"value": "Some description.", "confidence": 0.8, "evidence_basis": "x"},
    "key_visual_elements": [],  # invalid per addendum #2 — must be non-empty list or explicit null, never []
    "educational_purpose": {"value": "purpose", "confidence": 0.7, "evidence_basis": "x"},
    "importance": {"value": "high", "confidence": 0.8, "evidence_basis": "x"},
    "difficulty": {"value": "medium", "confidence": 0.7, "evidence_basis": "x"},
    "animation_candidate": {"value": False, "confidence": 0.6, "evidence_basis": "x"},
})


# ---------------------------------------------------------------------------
# context_builder
# ---------------------------------------------------------------------------
def test_render_substitutes_all_vars():
    tmpl = "Title: {{ topic_title }}. Body: {{ topic_body_text }}"
    out = context_builder.render(tmpl, {"topic_title": "GDP", "topic_body_text": "Some text."})
    assert out == "Title: GDP. Body: Some text." + context_builder.JSON_SAFETY_SUFFIX


def test_render_raises_on_missing_var():
    tmpl = "Title: {{ topic_title }}."
    with pytest.raises(context_builder.TemplateRenderError):
        context_builder.render(tmpl, {})


def test_render_stringifies_lists_readably():
    tmpl = "Concepts so far: {{ prior_concepts }}"
    out = context_builder.render(tmpl, {"prior_concepts": ["GDP", "inflation"]})
    assert "GDP" in out and "inflation" in out


def test_render_empty_list_renders_as_none_marker():
    tmpl = "{{ prior_concepts }}"
    out = context_builder.render(tmpl, {"prior_concepts": []})
    assert out == "(none)" + context_builder.JSON_SAFETY_SUFFIX


# ---------------------------------------------------------------------------
# task_registry
# ---------------------------------------------------------------------------
def test_all_registered_tasks_have_a_template_and_meta_file():
    for name, spec in task_registry.TASKS.items():
        assert os.path.exists(spec.template_path()), f"missing template for {name}"
        assert os.path.exists(spec.meta_path()), f"missing meta.json for {name}"


def test_all_registered_tasks_have_an_output_contract():
    for name, spec in task_registry.TASKS.items():
        assert spec.output_contract_name in output_contract.CONTRACTS, f"missing contract for {name}"


def test_unknown_task_raises_keyerror():
    with pytest.raises(KeyError):
        task_registry.get_task("not_a_real_task")


def test_templates_reference_all_declared_required_vars():
    """Every required_context_var a task declares should actually appear in
    its own template — otherwise the fail-fast check and the template are
    silently out of sync."""
    for name, spec in task_registry.TASKS.items():
        with open(spec.template_path(), encoding="utf-8") as f:
            text = f.read()
        template_vars = set(context_builder.find_template_vars(text))
        for required in spec.required_context_vars:
            assert required in template_vars, f"{name}: required var '{required}' not used in its template"


# ---------------------------------------------------------------------------
# output_contract
# ---------------------------------------------------------------------------
def test_valid_figure_response_passes_contract():
    contract = output_contract.get_contract("figure_analysis")
    is_valid, errors = output_contract.validate(contract, json.loads(VALID_FIGURE_RESPONSE))
    assert is_valid, errors


def test_empty_key_visual_elements_fails_contract():
    contract = output_contract.get_contract("figure_analysis")
    is_valid, errors = output_contract.validate(contract, json.loads(INVALID_FIGURE_RESPONSE_EMPTY_ELEMENTS))
    assert not is_valid
    assert any("key_visual_elements" in e for e in errors)


def test_null_key_visual_elements_is_allowed_but_missing_is_flagged_if_required_without_value():
    contract = output_contract.get_contract("figure_analysis")
    payload = json.loads(VALID_FIGURE_RESPONSE)
    payload["key_visual_elements"] = None
    is_valid, errors = output_contract.validate(contract, payload)
    # explicit null is the addendum's escape valve for mandatory_non_empty fields
    assert is_valid, errors


def test_evidence_triple_missing_confidence_fails():
    contract = output_contract.get_contract("semantic_metadata")
    payload = {
        "difficulty": {"value": "medium", "evidence_basis": "x"},  # missing confidence
        "importance": {"value": "high", "confidence": 0.9, "evidence_basis": "x"},
        "visual_dependency": {"value": "low", "confidence": 0.8, "evidence_basis": "x"},
    }
    is_valid, errors = output_contract.validate(contract, payload)
    assert not is_valid
    assert any("difficulty" in e for e in errors)


def test_evidence_triple_confidence_out_of_range_fails():
    contract = output_contract.get_contract("semantic_metadata")
    payload = {
        "difficulty": {"value": "medium", "confidence": 1.5, "evidence_basis": "x"},
        "importance": {"value": "high", "confidence": 0.9, "evidence_basis": "x"},
        "visual_dependency": {"value": "low", "confidence": 0.8, "evidence_basis": "x"},
    }
    is_valid, errors = output_contract.validate(contract, payload)
    assert not is_valid


# ---------------------------------------------------------------------------
# PromptManager.run — full orchestration with a fake adapter
# ---------------------------------------------------------------------------
def test_missing_required_context_fails_fast_before_any_model_call():
    adapter = FakeAdapter(responses=["should never be reached"])
    manager = PromptManager(adapter)
    ctx = TaskContext(variables={"topic_title": "GDP"})  # missing topic_body_text
    with pytest.raises(MissingContextError):
        manager.run("concept_extraction", ctx)
    assert adapter.calls == [], "adapter must not be called when context validation fails"


def test_successful_run_on_first_attempt():
    adapter = FakeAdapter(responses=[VALID_CONCEPT_RESPONSE])
    manager = PromptManager(adapter)
    ctx = TaskContext(variables={
        "topic_title": "National Income", "topic_body_text": "Body text here.",
        "chapter_title": "Macroeconomics", "prior_concepts": [],
    })
    result = manager.run("concept_extraction", ctx)
    assert result.success
    assert result.retry_count == 0
    assert len(result.parsed_output["concepts"]) == 2
    assert result.model_adapter_id == "fake-adapter-for-tests"
    assert result.prompt_version == "v1"


def test_retries_once_then_succeeds():
    adapter = FakeAdapter(responses=[INVALID_FIGURE_RESPONSE_EMPTY_ELEMENTS, VALID_FIGURE_RESPONSE])
    manager = PromptManager(adapter)
    ctx = TaskContext(
        variables={"caption": "Fig 3.1 Circular flow", "topic_title": "National Income", "nearby_body_text": ""},
        images=["fake-image-object"],
    )
    result = manager.run("figure_analysis", ctx)
    assert result.success
    assert result.retry_count == 1
    assert len(adapter.calls) == 2


def test_fails_after_exhausting_retry():
    adapter = FakeAdapter(responses=[INVALID_FIGURE_RESPONSE_EMPTY_ELEMENTS, INVALID_FIGURE_RESPONSE_EMPTY_ELEMENTS])
    manager = PromptManager(adapter)
    ctx = TaskContext(
        variables={"caption": "Fig 3.1", "topic_title": "National Income", "nearby_body_text": ""},
        images=["fake-image-object"],
    )
    result = manager.run("figure_analysis", ctx)
    assert not result.success
    assert result.retry_count == 1
    assert result.parsed_output is None
    assert any("key_visual_elements" in e for e in result.validation_errors)


def test_non_json_output_is_treated_as_failure_not_a_crash():
    adapter = FakeAdapter(responses=["I'm not JSON at all, sorry!", "I'm still not JSON!"])
    manager = PromptManager(adapter)
    ctx = TaskContext(variables={"topic_title": "X", "topic_body_text": "Y"})
    result = manager.run("concept_extraction", ctx)
    assert not result.success
    assert result.retry_count == 1


def test_fallback_reason_passed_through_unchanged():
    adapter = FakeAdapter(responses=[VALID_CONCEPT_RESPONSE])
    manager = PromptManager(adapter)
    ctx = TaskContext(variables={"topic_title": "X", "topic_body_text": "Y"})
    result = manager.run("concept_extraction", ctx, fallback_reason="low_confidence")
    assert result.fallback_reason == "low_confidence"


def test_unknown_task_name_raises_keyerror():
    adapter = FakeAdapter(responses=[])
    manager = PromptManager(adapter)
    ctx = TaskContext(variables={})
    with pytest.raises(KeyError):
        manager.run("not_a_real_task", ctx)


def test_text_only_task_does_not_require_images():
    """concept_extraction has expects_images=False — must not blow up or
    require an image even if none is supplied."""
    adapter = FakeAdapter(responses=[VALID_CONCEPT_RESPONSE])
    manager = PromptManager(adapter)
    ctx = TaskContext(variables={"topic_title": "X", "topic_body_text": "Y"})  # no images
    result = manager.run("concept_extraction", ctx)
    assert result.success
    assert adapter.calls[0]["images"] == []


# ---------------------------------------------------------------------------
# Single-field wrapper-collapse repair — the production failure: for a
# task with exactly one required field (recover_chapter_title), Qwen
# sometimes returns the flat {value, confidence, evidence_basis} triple
# directly instead of wrapping it under "chapter_title", failing validation
# with "'chapter_title' is required but missing" on both attempts even
# though the model's actual answer was fine.
# ---------------------------------------------------------------------------
def test_single_field_response_missing_wrapper_key_is_repaired():
    collapsed_response = _json.dumps({
        "value": "जयशंकर प्रसाद", "confidence": 0.9,
        "evidence_basis": "largest text block on page 1",
    })
    adapter = FakeAdapter(responses=[collapsed_response])
    manager = PromptManager(adapter)
    ctx = TaskContext(
        variables={"book_title": "अंतरा", "subject": "Hindi", "candidate_titles": "t;'kadj izlkn",
                   "ocr_text_first_pages": ""},
        images=["fake-image-object"],
    )
    result = manager.run("recover_chapter_title", ctx)
    assert result.success
    assert result.retry_count == 0  # fixed on the FIRST attempt, no retry needed
    assert result.parsed_output["chapter_title"]["value"] == "जयशंकर प्रसाद"


def test_multi_field_task_is_not_affected_by_the_wrapper_repair():
    """recover_heading has two fields -- the collapse-repair must never
    touch it, so a genuinely missing wrapper there still fails validation
    exactly as before (proving the repair is scoped correctly, not just
    "always try to make it pass")."""
    collapsed_response = _json.dumps({
        "value": "some heading", "confidence": 0.8, "evidence_basis": "x",
    })
    adapter = FakeAdapter(responses=[collapsed_response, collapsed_response])
    manager = PromptManager(adapter)
    ctx = TaskContext(
        variables={"chapter_title": "जयशंकर प्रसाद", "expected_level": 1, "nearby_headings": [],
                   "ocr_text_region": ""},
        images=["fake-image-object"],
    )
    result = manager.run("recover_heading", ctx)
    assert not result.success
    assert any("heading_title" in e for e in result.validation_errors)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
