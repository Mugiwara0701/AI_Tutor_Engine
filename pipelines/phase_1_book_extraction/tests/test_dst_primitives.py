"""
tests/test_dst_primitives.py — Milestone 1 unit tests for
document_structure_tree.primitives (schema §2.1's supporting/reusable
value types).

Covers, per type: round-trip (encode -> decode -> re-encode), negative/
constraint-violation cases, and the schema's own documented boundary
conventions (half-open BlockRange, inclusive-inclusive PageRange, the
Span empty-span case and its one asymmetric constraint).
"""
from __future__ import annotations

import pytest

from document_structure_tree.exceptions import DSTSerializationError, DSTValueError
from document_structure_tree.primitives import (
    BlockIndex,
    BlockRange,
    CanonicalObjectId,
    ChapterId,
    CompilerVersion,
    Fingerprint,
    IdentitySchemeVersion,
    Level,
    NodeId,
    ObjectType,
    PageLocator,
    PageRange,
    SchemaVersion,
    Span,
    Timestamp,
)
from document_structure_tree.serialization import round_trip


# --------------------------------------------------------------------------
# Opaque string identifiers: ChapterId, NodeId, CanonicalObjectId, ObjectType
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cls",
    [ChapterId, NodeId, CanonicalObjectId, ObjectType, PageLocator],
)
def test_opaque_string_types_round_trip(cls):
    instance = cls("some-value-123")
    encoded_once, decoded, encoded_twice = round_trip(instance)
    assert encoded_once == "some-value-123"
    assert encoded_twice == encoded_once
    assert decoded == instance


@pytest.mark.parametrize(
    "cls",
    [ChapterId, NodeId, CanonicalObjectId, ObjectType, PageLocator],
)
def test_opaque_string_types_reject_empty_string(cls):
    with pytest.raises(DSTValueError):
        cls("")


@pytest.mark.parametrize(
    "cls",
    [ChapterId, NodeId, CanonicalObjectId, ObjectType, PageLocator],
)
def test_opaque_string_types_reject_non_string(cls):
    with pytest.raises(DSTValueError):
        cls(123)


def test_chapter_id_str_and_equality():
    a = ChapterId("chap-07")
    b = ChapterId("chap-07")
    c = ChapterId("chap-08")
    assert a == b
    assert a != c
    assert str(a) == "chap-07"


# --------------------------------------------------------------------------
# Level
# --------------------------------------------------------------------------

def test_level_zero_is_root():
    assert Level(0).is_root() is True
    assert Level(1).is_root() is False


def test_level_child_is_plus_one():
    assert Level(0).child() == Level(1)
    assert Level(4).child() == Level(5)


def test_level_maximal_depth_value_accepted():
    deep = Level(10_000)
    assert deep.value == 10_000
    assert int(deep) == 10_000


def test_level_rejects_negative():
    with pytest.raises(DSTValueError):
        Level(-1)


def test_level_rejects_bool():
    # bool is an int subclass in Python; explicitly rejected so a
    # caller's typo (True/False) isn't silently treated as 1/0.
    with pytest.raises(DSTValueError):
        Level(True)


def test_level_round_trip():
    encoded_once, decoded, encoded_twice = round_trip(Level(3))
    assert encoded_once == 3
    assert encoded_twice == 3
    assert decoded == Level(3)


# --------------------------------------------------------------------------
# SchemaVersion / CompilerVersion
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [SchemaVersion, CompilerVersion])
def test_version_types_round_trip(cls):
    encoded_once, decoded, encoded_twice = round_trip(cls("1.1.0"))
    assert encoded_once == "1.1.0"
    assert encoded_twice == "1.1.0"
    assert decoded == cls("1.1.0")


@pytest.mark.parametrize("cls", [SchemaVersion, CompilerVersion])
@pytest.mark.parametrize(
    "bad_value",
    ["1.1", "1.1.0.0", "v1.1.0", "1.1.0-beta", "", "not-a-version"],
)
def test_version_types_reject_non_semver(cls, bad_value):
    with pytest.raises(DSTValueError):
        cls(bad_value)


def test_schema_version_major_property():
    assert SchemaVersion("2.4.7").major == 2
    assert SchemaVersion("0.9.9").major == 0


# --------------------------------------------------------------------------
# IdentitySchemeVersion
# --------------------------------------------------------------------------

def test_identity_scheme_version_accepts_string():
    v = IdentitySchemeVersion("1")
    assert v.value == "1"
    assert v.to_json() == "1"


def test_identity_scheme_version_accepts_int_and_normalizes_to_string():
    v = IdentitySchemeVersion(1)
    assert v.value == "1"
    assert isinstance(v.to_json(), str)


def test_identity_scheme_version_rejects_empty():
    with pytest.raises(DSTValueError):
        IdentitySchemeVersion("")


# --------------------------------------------------------------------------
# Timestamp
# --------------------------------------------------------------------------

def test_timestamp_round_trip():
    encoded_once, decoded, encoded_twice = round_trip(Timestamp("2026-07-15T09:00:00Z"))
    assert encoded_once == "2026-07-15T09:00:00Z"
    assert encoded_twice == encoded_once
    assert decoded == Timestamp("2026-07-15T09:00:00Z")


@pytest.mark.parametrize(
    "bad_value",
    [
        "2026-07-15",                 # no time component
        "2026-07-15T09:00:00",        # missing Z
        "2026-07-15 09:00:00Z",       # wrong separator
        "not-a-timestamp",
        "2026-02-30T00:00:00Z",       # not a real calendar date
    ],
)
def test_timestamp_rejects_malformed(bad_value):
    with pytest.raises(DSTValueError):
        Timestamp(bad_value)


def test_timestamp_accepts_fractional_seconds():
    ts = Timestamp("2026-07-15T09:00:00.123Z")
    assert ts.value == "2026-07-15T09:00:00.123Z"


# --------------------------------------------------------------------------
# Fingerprint
# --------------------------------------------------------------------------

def test_fingerprint_of_is_deterministic_sha256_hex():
    fp1 = Fingerprint.of(b"hello world")
    fp2 = Fingerprint.of(b"hello world")
    assert fp1 == fp2
    assert len(fp1.value) == 64
    assert fp1.value == fp1.value.lower()


def test_fingerprint_rejects_non_hex():
    with pytest.raises(DSTValueError):
        Fingerprint("not-a-hex-digest")


def test_fingerprint_rejects_wrong_length():
    with pytest.raises(DSTValueError):
        Fingerprint("abc123")


def test_fingerprint_rejects_uppercase_hex():
    # Schema §2.1 fixes the encoding as *lowercase* hex; uppercase must
    # not be silently normalized.
    upper = Fingerprint.of(b"x").value.upper()
    with pytest.raises(DSTValueError):
        Fingerprint(upper)


# --------------------------------------------------------------------------
# BlockIndex / BlockRange (half-open)
# --------------------------------------------------------------------------

def test_block_index_round_trip():
    encoded_once, decoded, encoded_twice = round_trip(BlockIndex(42))
    assert encoded_once == 42
    assert decoded == BlockIndex(42)
    assert encoded_twice == 42


def test_block_index_rejects_negative():
    with pytest.raises(DSTValueError):
        BlockIndex(-1)


def test_block_range_round_trip():
    br = BlockRange(BlockIndex(3), BlockIndex(40))
    encoded_once, decoded, encoded_twice = round_trip(br)
    assert encoded_once == {"start": 3, "end": 40}
    assert decoded == br
    assert encoded_twice == encoded_once


def test_block_range_rejects_start_greater_than_end():
    with pytest.raises(DSTValueError):
        BlockRange(BlockIndex(10), BlockIndex(5))


def test_block_range_allows_zero_width_range():
    br = BlockRange(BlockIndex(5), BlockIndex(5))
    assert br.is_empty() is True


def test_block_range_adjacent_non_overlapping_under_half_open_semantics():
    # Schema §2.1's own "Bound-convention note" example.
    a = BlockRange(BlockIndex(0), BlockIndex(5))
    b = BlockRange(BlockIndex(5), BlockIndex(10))
    assert a.is_adjacent_to(b) is True
    assert b.is_adjacent_to(a) is True


def test_block_range_contains():
    outer = BlockRange(BlockIndex(0), BlockIndex(88))
    inner = BlockRange(BlockIndex(3), BlockIndex(40))
    disjoint = BlockRange(BlockIndex(90), BlockIndex(100))
    assert outer.contains(inner) is True
    assert outer.contains(outer) is True
    assert outer.contains(disjoint) is False


def test_block_range_from_json_missing_key_raises_serialization_error():
    with pytest.raises(DSTSerializationError):
        BlockRange.from_json({"start": 0})


def test_block_range_from_json_wrong_shape_raises_serialization_error():
    with pytest.raises(DSTSerializationError):
        BlockRange.from_json([0, 5])


# --------------------------------------------------------------------------
# PageLocator / PageRange (inclusive-inclusive)
# --------------------------------------------------------------------------

def test_page_range_round_trip_and_inclusivity_documented():
    pr = PageRange(PageLocator("88"), PageLocator("94"))
    encoded_once, decoded, encoded_twice = round_trip(pr)
    assert encoded_once == {"start": "88", "end": "94"}
    assert decoded == pr
    # Both endpoints are documented as included -- this is a rendering
    # convention (schema §2.9), not something this type computes, so
    # the test only anchors that construction with equal-looking
    # bounds is legal and that both endpoints are preserved exactly.
    assert decoded.start.value == "88"
    assert decoded.end.value == "94"


def test_page_range_supports_non_numeric_locators():
    pr = PageRange(PageLocator("xii"), PageLocator("xv"))
    assert pr.to_json() == {"start": "xii", "end": "xv"}


# --------------------------------------------------------------------------
# Span
# --------------------------------------------------------------------------

def test_span_round_trip_full():
    span = Span(
        block_range=BlockRange(BlockIndex(3), BlockIndex(40)),
        page_range=PageRange(PageLocator("88"), PageLocator("94")),
    )
    encoded_once, decoded, encoded_twice = round_trip(span)
    assert encoded_once == {
        "block_range": {"start": 3, "end": 40},
        "page_range": {"start": "88", "end": "94"},
    }
    assert decoded == span
    assert encoded_twice == encoded_once


def test_span_block_range_only_omits_page_range_key():
    span = Span(block_range=BlockRange(BlockIndex(0), BlockIndex(5)))
    encoded = span.to_json()
    assert "page_range" not in encoded
    assert encoded == {"block_range": {"start": 0, "end": 5}}


def test_span_empty_case_both_fields_absent():
    span = Span()
    assert span.is_empty() is True
    assert span.to_json() == {}
    assert Span.from_json({}) == span


def test_span_page_range_without_block_range_is_rejected():
    with pytest.raises(DSTValueError):
        Span(page_range=PageRange(PageLocator("1"), PageLocator("2")))


def test_span_from_json_round_trips_empty_object():
    encoded_once, decoded, encoded_twice = round_trip(Span())
    assert encoded_once == {}
    assert decoded == Span()
    assert decoded.is_empty() is True
    assert encoded_twice == {}
