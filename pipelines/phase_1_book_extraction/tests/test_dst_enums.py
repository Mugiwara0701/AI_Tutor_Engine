"""
tests/test_dst_enums.py — Milestone 1 unit tests for
document_structure_tree.enums.

Covers round-trip serialization for every closed enum this milestone
defines, plus the negative case (an unrecognized string is rejected,
not silently coerced).
"""
from __future__ import annotations

import pytest

from document_structure_tree.enums import (
    EntryType,
    HeadingDetectionMethod,
    InvariantId,
    ValidationStatus,
)
from document_structure_tree.exceptions import DSTSerializationError
from document_structure_tree.serialization import round_trip


def test_entry_type_values_and_round_trip():
    assert EntryType.HEADING.to_json() == "heading"
    assert EntryType.CONTENT.to_json() == "content"
    encoded_once, decoded, encoded_twice = round_trip(EntryType.HEADING)
    assert encoded_once == "heading"
    assert decoded is EntryType.HEADING
    assert encoded_twice == "heading"


def test_entry_type_from_json_rejects_unknown_value():
    with pytest.raises(DSTSerializationError):
        EntryType.from_json("footnote")


def test_entry_type_from_json_rejects_non_string():
    with pytest.raises(DSTSerializationError):
        EntryType.from_json(1)


def test_validation_status_values_and_round_trip():
    assert ValidationStatus.PASS.to_json() == "pass"
    assert ValidationStatus.FAIL.to_json() == "fail"
    encoded_once, decoded, encoded_twice = round_trip(ValidationStatus.FAIL)
    assert decoded is ValidationStatus.FAIL
    assert encoded_once == encoded_twice == "fail"


def test_validation_status_rejects_unknown_value():
    with pytest.raises(DSTSerializationError):
        ValidationStatus.from_json("warn")


@pytest.mark.parametrize(
    "member,expected",
    [
        (HeadingDetectionMethod.LAYOUT_ANALYSIS, "layout_analysis"),
        (HeadingDetectionMethod.TYPOGRAPHY, "typography"),
        (HeadingDetectionMethod.TOC_MATCHING, "toc_matching"),
        (HeadingDetectionMethod.VLM_INFERENCE, "vlm_inference"),
        (HeadingDetectionMethod.HEURISTIC_MERGING, "heuristic_merging"),
    ],
)
def test_heading_detection_method_values(member, expected):
    assert member.to_json() == expected
    assert HeadingDetectionMethod.from_json(expected) is member


def test_heading_detection_method_rejects_unknown_value():
    with pytest.raises(DSTSerializationError):
        HeadingDetectionMethod.from_json("psychic_inference")


@pytest.mark.parametrize(
    "code",
    [
        "S1", "S2", "S3", "S4",
        "R1", "R2", "R3", "R4",
        "O1", "O2",
        "I1", "I2", "I3",
        "B1", "B2", "B3",
    ],
)
def test_invariant_id_covers_every_architecture_invariant(code):
    member = InvariantId.from_json(code)
    assert member.value == code
    assert member.to_json() == code


def test_invariant_id_is_exhaustive_and_closed():
    # Architecture §15 defines exactly sixteen invariants; schema §2.1
    # calls InvariantId a closed set.
    assert len(list(InvariantId)) == 16


def test_invariant_id_rejects_unknown_code():
    with pytest.raises(DSTSerializationError):
        InvariantId.from_json("S5")


def test_object_type_is_not_defined_as_a_closed_enum():
    # Schema §2.1 classifies ObjectType as an open string set owned by
    # the canonical registries, not enumerated by this schema -- so it
    # must not appear as a member of this module's closed-enum surface.
    import document_structure_tree.enums as enums_module

    assert not hasattr(enums_module, "ObjectType")
