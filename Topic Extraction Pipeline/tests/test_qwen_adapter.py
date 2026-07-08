"""
tests/test_qwen_adapter.py — exercises QwenAdapter's cleanup/parsing logic
and its ModelAdapter conformance WITHOUT loading the real Qwen2.5-VL-3B
model. `vlm_inference.generate` (the existing, reused inference call) is
monkeypatched so these tests are fast and don't need a GPU; the actual
"does Qwen load and run" check is the separate validation spike (step 3),
not a unit test's job.

Run: python -m pytest tests/test_qwen_adapter.py -v
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from prompt_manager.model_adapter import AdapterResponse
from prompt_manager.adapters.qwen_adapter import (
    QwenAdapter, clean_and_parse_qwen_output, _strip_markdown_fences,
    _extract_json_block, _repair_trailing_commas, _repair_control_characters,
    _repair_truncated_json,
)
from modules import vlm_inference


# ---------------------------------------------------------------------------
# Cleanup helper functions (pure, no model involved)
# ---------------------------------------------------------------------------
def test_strip_markdown_fences_with_json_tag():
    raw = '```json\n{"a": 1}\n```'
    assert _strip_markdown_fences(raw) == '{"a": 1}'


def test_strip_markdown_fences_plain():
    raw = '```\n{"a": 1}\n```'
    assert _strip_markdown_fences(raw) == '{"a": 1}'


def test_strip_markdown_fences_no_fence_is_noop():
    raw = '{"a": 1}'
    assert _strip_markdown_fences(raw) == '{"a": 1}'


def test_extract_json_block_from_prose_wrapper():
    raw = 'Sure, here is the JSON you asked for:\n{"a": 1, "b": [1, 2]}\nHope that helps!'
    assert _extract_json_block(raw) == '{"a": 1, "b": [1, 2]}'


def test_repair_trailing_comma_before_closing_brace():
    raw = '{"a": 1, "b": 2,}'
    assert _repair_trailing_commas(raw) == '{"a": 1, "b": 2}'


def test_repair_trailing_comma_before_closing_bracket():
    raw = '{"a": [1, 2, 3,]}'
    assert _repair_trailing_commas(raw) == '{"a": [1, 2, 3]}'


# ---------------------------------------------------------------------------
# clean_and_parse_qwen_output — full cleanup pipeline
# ---------------------------------------------------------------------------
def test_clean_and_parse_plain_valid_json():
    resp = clean_and_parse_qwen_output('{"chapter_title": {"value": "Intro", "confidence": 0.9, "evidence_basis": "x"}}')
    assert resp.success
    assert resp.parsed_output["chapter_title"]["value"] == "Intro"


def test_clean_and_parse_markdown_fenced_json():
    raw = '```json\n{"a": 1}\n```'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output == {"a": 1}
    assert resp.raw_output == raw  # raw_output preserves the untouched original


def test_clean_and_parse_prose_wrapped_json():
    raw = 'Here you go:\n{"a": 1}\nLet me know if you need more.'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output == {"a": 1}


def test_clean_and_parse_trailing_comma_repaired():
    raw = '{"a": 1, "b": 2,}'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output == {"a": 1, "b": 2}


def test_clean_and_parse_fenced_and_trailing_comma_together():
    raw = '```json\n{"a": 1, "b": [1, 2,],}\n```'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output == {"a": 1, "b": [1, 2]}


# ---------------------------------------------------------------------------
# Stray-glued-closing-brace repair — the real malformation observed in
# production logs: Qwen closes a nested field's string value with a `}`
# glued directly onto the closing quote (no comma), which then makes
# json.loads consume that glued brace PLUS the next real closing brace as
# a complete (but wrong, too-early-terminated) top-level object, reporting
# everything genuinely meant to follow as "Extra data".
# ---------------------------------------------------------------------------
def test_repair_stray_closing_brace_low_level():
    from prompt_manager.adapters.qwen_adapter import _repair_stray_closing_brace
    import json

    raw = ('{"latex": {"value": "a", "confidence": 0.75, "evidence_basis": "b"}'
           '}, "spoken_form": {"value": "c"}}')
    try:
        json.loads(raw)
        assert False, "fixture should not already be valid JSON"
    except json.JSONDecodeError as e:
        fixed = _repair_stray_closing_brace(raw, e)
    assert fixed is not None
    assert json.loads(fixed) == {"latex": {"value": "a", "confidence": 0.75, "evidence_basis": "b"},
                                  "spoken_form": {"value": "c"}}


def test_repair_stray_closing_brace_returns_none_for_other_errors():
    from prompt_manager.adapters.qwen_adapter import _repair_stray_closing_brace
    import json

    try:
        json.loads("not json at all")
    except json.JSONDecodeError as e:
        assert _repair_stray_closing_brace("not json at all", e) is None


def test_clean_and_parse_recovers_from_stray_glued_brace_production_case():
    """The exact shape seen in production logs: a two-field task result
    (e.g. equation_analysis's latex/spoken_form) where the model glued an
    extra `}` onto "evidence_basis"'s closing quote, silently dropping the
    second field ("spoken_form") if left unrepaired."""
    raw = ('{\n'
           '  "latex": {\n'
           '    "value": "\\\\text{Equation}",\n'
           '    "confidence": 0.9,\n'
           '    "evidence_basis": "mathematical expression shown in textbook"}\n'
           '  },\n'
           '  "spoken_form": {\n'
           '    "value": "The equation shown",\n'
           '    "confidence": 0.85,\n'
           '    "evidence_basis": "derived from latex"\n'
           '  }\n'
           '}')
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert set(resp.parsed_output.keys()) == {"latex", "spoken_form"}
    assert resp.parsed_output["spoken_form"]["value"] == "The equation shown"


def test_clean_and_parse_still_fails_cleanly_when_no_repair_applies():
    """A genuinely different 'Extra data' cause (two concatenated JSON
    objects, not the stray-glued-brace shape) should still come back as a
    structured failure, not silently mangled by the new repair misfiring."""
    raw = '{"a": 1}{"b": 2}'
    resp = clean_and_parse_qwen_output(raw)
    assert not resp.success
    assert resp.parsed_output is None


def test_clean_and_parse_empty_output_is_structured_failure_not_exception():
    resp = clean_and_parse_qwen_output("")
    assert not resp.success
    assert resp.parsed_output is None
    assert resp.error_message


def test_clean_and_parse_garbage_output_is_structured_failure_not_exception():
    resp = clean_and_parse_qwen_output("I cannot help with that request.")
    assert not resp.success
    assert resp.parsed_output is None
    assert "invalid JSON" in resp.error_message or resp.error_message


def test_clean_and_parse_never_raises_on_malformed_input():
    """Defensive parsing must come back as a structured failure, never an
    exception, for any garbage input — this is what lets prompt_manager's
    retry logic treat it as an ordinary case."""
    tricky_inputs = ["{{{{", "not json at all", "```json\n```", "{'single': 'quotes'}", None]
    for bad in tricky_inputs:
        resp = clean_and_parse_qwen_output(bad)
        assert isinstance(resp, AdapterResponse)
        assert resp.success in (True, False)  # never raises getting here



# ---------------------------------------------------------------------------
# QwenAdapter — conformance + integration with vlm_inference (monkeypatched)
# ---------------------------------------------------------------------------
def test_qwen_adapter_generate_delegates_to_vlm_inference(monkeypatch):
    captured = {}

    def fake_generate(prompt, images=None, max_new_tokens=None):
        captured["prompt"] = prompt
        captured["images"] = images
        captured["max_new_tokens"] = max_new_tokens
        return "raw model text"

    monkeypatch.setattr(vlm_inference, "generate", fake_generate)
    adapter = QwenAdapter(max_new_tokens=256)
    out = adapter.generate("hello", images=["img1"])
    assert out == "raw model text"
    assert captured["prompt"] == "hello"
    assert captured["images"] == ["img1"]
    assert captured["max_new_tokens"] == 256  # adapter's default, since caller didn't override


def test_qwen_adapter_generate_json_success(monkeypatch):
    monkeypatch.setattr(vlm_inference, "generate",
                         lambda prompt, images=None, max_new_tokens=None: '```json\n{"x": 1}\n```')
    adapter = QwenAdapter()
    resp = adapter.generate_json("prompt", images=[])
    assert resp.success
    assert resp.parsed_output == {"x": 1}


def test_qwen_adapter_generate_json_bad_output_is_structured_failure(monkeypatch):
    monkeypatch.setattr(vlm_inference, "generate",
                         lambda prompt, images=None, max_new_tokens=None: "not json")
    adapter = QwenAdapter()
    resp = adapter.generate_json("prompt", images=[])
    assert not resp.success
    assert resp.parsed_output is None
    assert resp.error_message


def test_qwen_adapter_generate_json_infra_failure_does_not_raise(monkeypatch):
    """A real exception during inference (e.g. simulated OOM) must come back
    as a structured AdapterResponse, not propagate — so one bad call can't
    crash a whole batch run."""
    def boom(prompt, images=None, max_new_tokens=None):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(vlm_inference, "generate", boom)
    adapter = QwenAdapter()
    resp = adapter.generate_json("prompt", images=[])
    assert not resp.success
    assert "CUDA out of memory" in resp.error_message


def test_qwen_adapter_token_counts_is_none():
    adapter = QwenAdapter()
    assert adapter.token_counts() is None


def test_qwen_adapter_id_is_set():
    adapter = QwenAdapter()
    assert adapter.adapter_id == "qwen2.5-vl-3b-instruct"


# ---------------------------------------------------------------------------
# ISSUE 2: JSON Repair Layer additions -- control characters + truncation
# ---------------------------------------------------------------------------
def test_repair_control_characters_escapes_literal_newline_in_string():
    raw = '{"semantic_meaning": "line one\nline two"}'
    repaired = _repair_control_characters(raw)
    assert json.loads(repaired) == {"semantic_meaning": "line one\nline two"}


def test_repair_control_characters_leaves_pretty_print_whitespace_alone():
    raw = '{\n  "a": 1\n}'
    assert _repair_control_characters(raw) == raw


def test_clean_and_parse_repairs_invalid_control_character():
    raw = '{"semantic_meaning": "first part\nsecond part", "confidence": 0.8}'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output["confidence"] == 0.8


def test_repair_truncated_json_closes_unterminated_string_and_object():
    raw = '{"latex": "F = ma", "semantic_meaning": "Newton'
    repaired = _repair_truncated_json(raw)
    assert repaired is not None
    parsed = json.loads(repaired)
    assert parsed["latex"] == "F = ma"
    assert parsed["semantic_meaning"] == "Newton"


def test_repair_truncated_json_returns_none_when_not_truncated():
    raw = '{"a": 1}'
    assert _repair_truncated_json(raw) is None


def test_clean_and_parse_repairs_truncated_json():
    raw = '{"latex": "E = mc^2", "variables": ["E: energy", "m: mass"'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output["latex"] == "E = mc^2"
    assert resp.parsed_output["variables"] == ["E: energy", "m: mass"]


def test_clean_and_parse_still_fails_cleanly_on_unrepairable_garbage():
    raw = "this is not JSON at all, just prose."
    resp = clean_and_parse_qwen_output(raw)
    assert not resp.success
    assert resp.raw_output == raw


# ---------------------------------------------------------------------------
# PART 1: production-grade repair layer (modules/json_repair.py), wired in
# as an additional last-resort stage. These exercise malformation classes
# the pre-existing Qwen-specific repairs above don't attempt.
# ---------------------------------------------------------------------------
def test_clean_and_parse_repairs_broken_frac_latex_and_missing_brace():
    raw = r'{"latex": {"value": "$\frac{a}{b", "confidence": 0.9, "evidence_basis": "x"}}'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert "frac" in resp.parsed_output["latex"]["value"]


def test_clean_and_parse_does_not_corrupt_frac_as_form_feed():
    """\\frac's leading backslash-f must never be silently consumed as a
    JSON form-feed escape -- that would 'succeed' while corrupting the
    LaTeX content instead of failing loudly."""
    raw = r'{"latex": "$\frac{x}{y}$", "confidence": 0.5, "evidence_basis": "b"}'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert "\x0c" not in resp.parsed_output["latex"]
    assert "frac" in resp.parsed_output["latex"]


def test_clean_and_parse_repairs_single_quoted_object():
    raw = "{'chapter_title': {'value': 'Intro', 'confidence': 0.9, 'evidence_basis': 'x'}}"
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output["chapter_title"]["value"] == "Intro"


def test_clean_and_parse_repairs_missing_colon():
    raw = '{"a" 1, "b" "two"}'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output == {"a": 1, "b": "two"}


def test_clean_and_parse_repairs_unbalanced_braces():
    raw = '{"a": 1, "b": {"c": 2}'
    resp = clean_and_parse_qwen_output(raw)
    assert resp.success
    assert resp.parsed_output == {"a": 1, "b": {"c": 2}}


def test_clean_and_parse_ambiguous_concatenated_objects_still_fails():
    """Regression guard: the new, broader repair stage must NOT start
    guessing between two genuinely different, independently-valid JSON
    objects concatenated together -- that ambiguity must still be reported
    as a failure, exactly as before this change."""
    raw = '{"a": 1}{"b": 2}'
    resp = clean_and_parse_qwen_output(raw)
    assert not resp.success
    assert resp.parsed_output is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
