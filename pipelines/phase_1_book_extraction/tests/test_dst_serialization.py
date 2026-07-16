"""
tests/test_dst_serialization.py — Milestone 1 unit tests for
document_structure_tree.serialization, the generic scaffolding every
model in this package (and every later milestone's models) is built
from: the OMIT sentinel / json_object omission-vs-null handling, the
shared require_* validators, and the round_trip harness.
"""
from __future__ import annotations

import pytest

from document_structure_tree.exceptions import DSTSerializationError, DSTValueError
from document_structure_tree.serialization import (
    OMIT,
    json_object,
    require_dict,
    require_iso8601_utc,
    require_key,
    require_non_empty_str,
    require_non_negative_int,
    require_semver,
    require_sha256_hex,
    round_trip,
)


# --------------------------------------------------------------------------
# OMIT / json_object
# --------------------------------------------------------------------------

def test_json_object_drops_omitted_fields():
    result = json_object([("a", 1), ("b", OMIT), ("c", "x")])
    assert result == {"a": 1, "c": "x"}
    assert "b" not in result


def test_json_object_preserves_explicit_none():
    # parent_id at the chapter root: present and explicitly null, never
    # omitted (schema §5.3).
    result = json_object([("parent_id", None)])
    assert result == {"parent_id": None}
    assert result["parent_id"] is None


def test_json_object_distinguishes_none_from_omit():
    with_none = json_object([("x", None)])
    with_omit = json_object([("x", OMIT)])
    assert "x" in with_none
    assert "x" not in with_omit


def test_omit_is_a_singleton():
    from document_structure_tree.serialization import Omitted

    assert Omitted() is OMIT
    assert bool(OMIT) is False


# --------------------------------------------------------------------------
# require_non_empty_str
# --------------------------------------------------------------------------

def test_require_non_empty_str_accepts_valid():
    assert require_non_empty_str("abc", "Field") == "abc"


def test_require_non_empty_str_rejects_empty():
    with pytest.raises(DSTValueError):
        require_non_empty_str("", "Field")


def test_require_non_empty_str_rejects_non_string():
    with pytest.raises(DSTValueError):
        require_non_empty_str(123, "Field")


# --------------------------------------------------------------------------
# require_non_negative_int
# --------------------------------------------------------------------------

def test_require_non_negative_int_accepts_zero_and_positive():
    assert require_non_negative_int(0, "Field") == 0
    assert require_non_negative_int(5, "Field") == 5


def test_require_non_negative_int_rejects_negative():
    with pytest.raises(DSTValueError):
        require_non_negative_int(-1, "Field")


def test_require_non_negative_int_rejects_bool():
    with pytest.raises(DSTValueError):
        require_non_negative_int(True, "Field")


def test_require_non_negative_int_rejects_float():
    with pytest.raises(DSTValueError):
        require_non_negative_int(1.5, "Field")


# --------------------------------------------------------------------------
# require_semver
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["1.1.0", "0.0.1", "10.20.30"])
def test_require_semver_accepts_valid(value):
    assert require_semver(value, "Field") == value


@pytest.mark.parametrize("value", ["1.1", "1.1.0.1", "v1.0.0", "1.0.0-beta", ""])
def test_require_semver_rejects_invalid(value):
    with pytest.raises(DSTValueError):
        require_semver(value, "Field")


# --------------------------------------------------------------------------
# require_iso8601_utc
# --------------------------------------------------------------------------

def test_require_iso8601_utc_accepts_schema_example():
    assert require_iso8601_utc("2026-07-15T09:00:00Z", "Field") == "2026-07-15T09:00:00Z"


@pytest.mark.parametrize(
    "value",
    ["2026-07-15", "2026-07-15T09:00:00", "2026/07/15T09:00:00Z", "2026-13-01T00:00:00Z"],
)
def test_require_iso8601_utc_rejects_invalid(value):
    with pytest.raises(DSTValueError):
        require_iso8601_utc(value, "Field")


# --------------------------------------------------------------------------
# require_sha256_hex
# --------------------------------------------------------------------------

def test_require_sha256_hex_accepts_64_char_lowercase_hex():
    digest = "a" * 64
    assert require_sha256_hex(digest, "Field") == digest


def test_require_sha256_hex_rejects_wrong_length():
    with pytest.raises(DSTValueError):
        require_sha256_hex("a" * 63, "Field")


def test_require_sha256_hex_rejects_uppercase():
    with pytest.raises(DSTValueError):
        require_sha256_hex("A" * 64, "Field")


# --------------------------------------------------------------------------
# require_dict / require_key
# --------------------------------------------------------------------------

def test_require_dict_accepts_dict():
    data = {"a": 1}
    assert require_dict(data, "Thing") is data


def test_require_dict_rejects_non_dict():
    with pytest.raises(DSTSerializationError):
        require_dict([1, 2, 3], "Thing")


def test_require_key_returns_value_when_present():
    assert require_key({"a": 1}, "a", "Thing") == 1


def test_require_key_raises_when_missing():
    with pytest.raises(DSTSerializationError):
        require_key({"a": 1}, "b", "Thing")


# --------------------------------------------------------------------------
# round_trip harness (generic, exercised here against a minimal
# hand-built JsonSerializable so this test doesn't depend on
# primitives.py's own test coverage)
# --------------------------------------------------------------------------

class _Wrapped:
    def __init__(self, value):
        self.value = value

    def to_json(self):
        return self.value

    @classmethod
    def from_json(cls, data):
        return cls(data)

    def __eq__(self, other):
        return isinstance(other, _Wrapped) and self.value == other.value


def test_round_trip_harness_returns_three_values():
    encoded_once, decoded, encoded_twice = round_trip(_Wrapped(42))
    assert encoded_once == 42
    assert decoded == _Wrapped(42)
    assert encoded_twice == 42
