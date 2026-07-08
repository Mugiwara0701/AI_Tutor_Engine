"""
tests/test_output_contract.py — unit tests for output_contract.py's
generic validation, focused on normalize_single_field_response(): the
repair for a small-model quirk where a single-required-field task
(recover_chapter_title) returns the flat {value, confidence,
evidence_basis} triple directly instead of wrapping it under the
field's name, seen in production logs as
"'chapter_title' is required but missing" on every attempt.

Run: python -m pytest tests/test_output_contract.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from prompt_manager import output_contract as oc
from prompt_manager.output_contract import FieldSpec, OutputContract


SINGLE_FIELD_CONTRACT = OutputContract("single_field_task", [
    FieldSpec("chapter_title", required=True, is_evidence_triple=True),
])

MULTI_FIELD_CONTRACT = OutputContract("multi_field_task", [
    FieldSpec("heading_title", required=True, is_evidence_triple=True),
    FieldSpec("numbering", required=False, is_evidence_triple=True),
])

OPTIONAL_SINGLE_FIELD_CONTRACT = OutputContract("optional_single_field_task", [
    FieldSpec("subtitle", required=False, is_evidence_triple=True),
])

NON_TRIPLE_SINGLE_FIELD_CONTRACT = OutputContract("non_triple_single_field_task", [
    FieldSpec("key_visual_elements", required=True, is_evidence_triple=False, is_list=True),
])

VALID_TRIPLE = {"value": "जयशंकर प्रसाद", "confidence": 0.9, "evidence_basis": "largest text on page 1"}


def test_wraps_collapsed_flat_triple_under_field_name():
    result = oc.normalize_single_field_response(SINGLE_FIELD_CONTRACT, dict(VALID_TRIPLE))
    assert result == {"chapter_title": VALID_TRIPLE}


def test_normalized_result_passes_validation():
    result = oc.normalize_single_field_response(SINGLE_FIELD_CONTRACT, dict(VALID_TRIPLE))
    is_valid, errors = oc.validate(SINGLE_FIELD_CONTRACT, result)
    assert is_valid
    assert errors == []


def test_correctly_wrapped_response_is_left_unchanged():
    wrapped = {"chapter_title": dict(VALID_TRIPLE)}
    result = oc.normalize_single_field_response(SINGLE_FIELD_CONTRACT, wrapped)
    assert result == wrapped


def test_multi_field_contract_is_never_touched():
    flat = dict(VALID_TRIPLE)
    result = oc.normalize_single_field_response(MULTI_FIELD_CONTRACT, flat)
    assert result == flat  # unchanged -- ambiguous which field it would belong to, so don't guess


def test_optional_single_field_is_never_touched():
    # required=False -- a missing field here is a legitimate "the model
    # decided there's nothing to report", not a collapsed-wrapper bug, so
    # this must not attempt to force a wrap.
    flat = dict(VALID_TRIPLE)
    result = oc.normalize_single_field_response(OPTIONAL_SINGLE_FIELD_CONTRACT, flat)
    assert result == flat


def test_non_evidence_triple_single_field_is_never_touched():
    parsed = {"key_visual_elements": ["a", "b"]}
    result = oc.normalize_single_field_response(NON_TRIPLE_SINGLE_FIELD_CONTRACT, parsed)
    assert result == parsed


def test_does_not_wrap_something_that_is_not_actually_a_valid_triple():
    # Missing "evidence_basis" -- not a real collapsed triple, just plain
    # bad output. Must not be force-wrapped into looking valid.
    bad = {"value": "x", "confidence": 0.9}
    result = oc.normalize_single_field_response(SINGLE_FIELD_CONTRACT, bad)
    assert result == bad
    is_valid, errors = oc.validate(SINGLE_FIELD_CONTRACT, result)
    assert not is_valid


def test_unrelated_response_shape_is_left_alone():
    unrelated = {"some_other_key": "some_other_value"}
    result = oc.normalize_single_field_response(SINGLE_FIELD_CONTRACT, unrelated)
    assert result == unrelated


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
