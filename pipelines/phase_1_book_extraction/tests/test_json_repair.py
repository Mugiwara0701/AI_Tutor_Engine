"""
tests/test_json_repair.py — exercises modules/json_repair.py, the generic
production-grade repair pipeline layered on top of (not replacing) the
existing Qwen-specific cleanup in prompt_manager/adapters/qwen_adapter.py.

Run: python -m pytest tests/test_json_repair.py -v
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import json_repair as jr


# ---------------------------------------------------------------------------
# Markdown fences / prose wrapping / multiple objects
# ---------------------------------------------------------------------------
def test_strip_markdown_fences_embedded_mid_string():
    raw = 'Sure! ```json\n{"a": 1}\n``` hope that helps'
    assert jr.strip_markdown_fences(raw) == '{"a": 1}'


def test_extract_json_candidates_finds_object_in_prose():
    raw = 'Here you go: {"a": 1, "b": [1, 2]} thanks!'
    candidates = jr.extract_json_candidates(raw)
    assert '{"a": 1, "b": [1, 2]}' in candidates


def test_pick_best_json_object_prefers_parseable_candidate():
    raw = '{"a": 1} then some prose {broken'
    assert jr.pick_best_json_object(raw) == '{"a": 1}'


def test_remove_duplicated_json_blocks_collapses_verbatim_repeat():
    raw = '{"a": 1, "b": 2}{"a": 1, "b": 2}'
    result = jr.remove_duplicated_json_blocks(raw)
    assert json.loads(result) == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Structural repairs
# ---------------------------------------------------------------------------
def test_balance_braces_and_brackets_closes_unclosed_object():
    raw = '{"a": 1, "b": {"c": 2}'
    fixed = jr.balance_braces_and_brackets(raw)
    assert json.loads(fixed) == {"a": 1, "b": {"c": 2}}


def test_balance_braces_and_brackets_drops_stray_extra_closer():
    raw = '{"a": 1}}'
    fixed = jr.balance_braces_and_brackets(raw)
    assert json.loads(fixed) == {"a": 1}


def test_normalize_smart_quotes():
    raw = "\u201ca\u201d: 1"
    assert jr.normalize_smart_quotes(raw) == '"a": 1'


def test_repair_single_quotes_key_and_value():
    raw = "{'a': 'hello', 'b': 2}"
    fixed = jr.repair_single_quotes(raw)
    assert json.loads(fixed) == {"a": "hello", "b": 2}


def test_repair_missing_colons():
    raw = '{"a" 1, "b" "two"}'
    fixed = jr.repair_missing_colons(raw)
    assert json.loads(fixed) == {"a": 1, "b": "two"}


def test_repair_trailing_commas():
    assert jr.repair_trailing_commas('{"a": 1,}') == '{"a": 1}'


def test_repair_missing_commas_heuristic_between_strings():
    raw = '{"a": "x"\n"b": "y"}'
    fixed = jr.repair_missing_commas_heuristic(raw)
    assert json.loads(fixed) == {"a": "x", "b": "y"}


# ---------------------------------------------------------------------------
# LaTeX / math / chemistry repairs
# ---------------------------------------------------------------------------
def test_repair_latex_backslashes_frac():
    raw = r'{"latex": "$\frac{a}{b}$"}'
    fixed = jr.repair_latex_backslashes(raw)
    assert json.loads(fixed) == {"latex": "$\\frac{a}{b}$"}


def test_repair_malformed_latex_groups_closes_missing_brace():
    raw = r'{"latex": "\frac{a}{b"}'
    fixed = jr.repair_malformed_latex_groups(raw)
    assert "\\frac{a}{b}" in fixed


def test_repair_malformed_latex_groups_sqrt_missing_close():
    raw = r'{"latex": "\sqrt{x"}'
    fixed = jr.repair_malformed_latex_groups(raw)
    assert "\\sqrt{x}" in fixed


def test_normalize_unicode_math_symbols_arrows_and_operators():
    raw = "A --> B, 2 <= 3"
    fixed = jr.normalize_unicode_math_symbols(raw)
    assert "\u2192" in fixed
    assert "\u2264" in fixed


def test_repair_ocr_escape_noise_collapses_over_escaping():
    raw = r"\\\frac{a}{b}"
    fixed = jr.repair_ocr_escape_noise(raw)
    assert fixed == r"\\frac{a}{b}"


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------
def test_repair_truncated_json_closes_open_object_and_string():
    raw = '{"latex": "F = ma", "semantic_meaning": "Newton'
    fixed = jr.repair_truncated_json(raw)
    assert fixed is not None
    parsed = json.loads(fixed)
    assert parsed["semantic_meaning"] == "Newton"


def test_repair_truncated_json_none_when_complete():
    assert jr.repair_truncated_json('{"a": 1}') is None


# ---------------------------------------------------------------------------
# Full orchestration: repair_and_parse
# ---------------------------------------------------------------------------
def test_repair_and_parse_already_valid():
    result = jr.repair_and_parse('{"a": 1}')
    assert result.success
    assert result.parsed == {"a": 1}
    assert result.stages_applied == []


def test_repair_and_parse_markdown_fenced():
    result = jr.repair_and_parse('```json\n{"a": 1}\n```')
    assert result.success
    assert result.parsed == {"a": 1}


def test_repair_and_parse_single_quotes_and_trailing_comma():
    result = jr.repair_and_parse("{'a': 1, 'b': [1, 2,],}")
    assert result.success
    assert result.parsed == {"a": 1, "b": [1, 2]}


def test_repair_and_parse_unbalanced_braces():
    result = jr.repair_and_parse('{"a": 1, "b": {"c": 2}')
    assert result.success
    assert result.parsed == {"a": 1, "b": {"c": 2}}


def test_repair_and_parse_broken_latex_and_missing_brace():
    raw = r'{"latex": "\frac{a}{b", "confidence": 0.9}'
    result = jr.repair_and_parse(raw)
    assert result.success
    assert result.parsed["confidence"] == 0.9
    assert "frac" in result.parsed["latex"]


def test_repair_and_parse_prose_wrapped_and_duplicated():
    raw = 'Here is the answer: {"a": 1} {"a": 1}'
    result = jr.repair_and_parse(raw)
    assert result.success
    assert result.parsed == {"a": 1}


def test_repair_and_parse_missing_colon_and_comma_together():
    raw = '{"a" 1\n"b" "two"}'
    result = jr.repair_and_parse(raw)
    assert result.success
    assert result.parsed == {"a": 1, "b": "two"}


def test_repair_and_parse_empty_input_fails_cleanly():
    result = jr.repair_and_parse("")
    assert not result.success
    assert result.error


def test_repair_and_parse_none_input_fails_cleanly():
    result = jr.repair_and_parse(None)
    assert not result.success


def test_repair_and_parse_never_raises_on_garbage():
    for bad in ["{{{{", "not json at all", "```json\n```", "", None, "{'x': }"]:
        result = jr.repair_and_parse(bad)
        assert result.success in (True, False)


def test_repair_and_parse_mixed_ocr_latex_control_chars():
    raw = ('{"semantic_meaning": "line one\nline two uses $\\vec{v}$",'
           ' "confidence": 0.8}')
    result = jr.repair_and_parse(raw)
    assert result.success
    assert result.parsed["confidence"] == 0.8
