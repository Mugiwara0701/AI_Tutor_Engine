"""Unit tests for `SequenceEntry` (schema §2.7) and the Typed Canonical
Reference shape it carries (schema §2.8)."""
import pytest

from document_structure_tree import (
    CanonicalObjectId,
    DSTSerializationError,
    DSTValueError,
    EntryType,
    NodeId,
    ObjectType,
    SequenceEntry,
    round_trip,
)


# --------------------------------------------------------------------------
# Valid construction + round-trip
# --------------------------------------------------------------------------

def test_heading_entry_valid_construction():
    entry = SequenceEntry(entry_type=EntryType.HEADING, ref=NodeId("chap-07:abc123"))
    assert entry.entry_type is EntryType.HEADING
    assert entry.ref == NodeId("chap-07:abc123")
    assert entry.object_type is None


def test_content_entry_valid_construction():
    entry = SequenceEntry(
        entry_type=EntryType.CONTENT, ref=CanonicalObjectId("obj-441"), object_type=ObjectType("figure")
    )
    assert entry.entry_type is EntryType.CONTENT
    assert entry.ref == CanonicalObjectId("obj-441")
    assert entry.object_type == ObjectType("figure")


def test_heading_ergonomic_constructor():
    entry = SequenceEntry.heading(NodeId("chap-07:xyz"))
    assert entry == SequenceEntry(entry_type=EntryType.HEADING, ref=NodeId("chap-07:xyz"))


def test_content_ergonomic_constructor():
    entry = SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("definition"))
    assert entry == SequenceEntry(
        entry_type=EntryType.CONTENT, ref=CanonicalObjectId("obj-1"), object_type=ObjectType("definition")
    )


def test_heading_entry_json_omits_object_type():
    entry = SequenceEntry.heading(NodeId("chap-07:abc"))
    assert entry.to_json() == {"entry_type": "heading", "ref": "chap-07:abc"}


def test_content_entry_json_includes_object_type():
    entry = SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("example"))
    assert entry.to_json() == {"entry_type": "content", "ref": "obj-1", "object_type": "example"}


@pytest.mark.parametrize(
    "entry",
    [
        SequenceEntry.heading(NodeId("chap-07:abc")),
        SequenceEntry.content(CanonicalObjectId("obj-9"), ObjectType("paragraph_group")),
    ],
)
def test_round_trip(entry):
    encoded_once, decoded, encoded_twice = round_trip(entry)
    assert encoded_once == encoded_twice
    assert decoded == entry


# --------------------------------------------------------------------------
# Local shape validation (schema §6 -- B1 discriminator check)
# --------------------------------------------------------------------------

def test_heading_entry_rejects_object_type():
    with pytest.raises(DSTValueError):
        SequenceEntry(entry_type=EntryType.HEADING, ref=NodeId("chap-07:abc"), object_type=ObjectType("figure"))


def test_content_entry_requires_object_type():
    with pytest.raises(DSTValueError):
        SequenceEntry(entry_type=EntryType.CONTENT, ref=CanonicalObjectId("obj-1"))


def test_heading_entry_rejects_canonical_object_id_ref():
    with pytest.raises(DSTValueError):
        SequenceEntry(entry_type=EntryType.HEADING, ref=CanonicalObjectId("obj-1"))


def test_content_entry_rejects_node_id_ref():
    with pytest.raises(DSTValueError):
        SequenceEntry(
            entry_type=EntryType.CONTENT, ref=NodeId("chap-07:abc"), object_type=ObjectType("figure")
        )


# --------------------------------------------------------------------------
# Deserialization shape errors
# --------------------------------------------------------------------------

def test_from_json_missing_entry_type():
    with pytest.raises(DSTSerializationError):
        SequenceEntry.from_json({"ref": "obj-1", "object_type": "figure"})


def test_from_json_missing_ref():
    with pytest.raises(DSTSerializationError):
        SequenceEntry.from_json({"entry_type": "heading"})


def test_from_json_heading_with_object_type_present_is_rejected():
    with pytest.raises(DSTSerializationError):
        SequenceEntry.from_json({"entry_type": "heading", "ref": "chap-07:abc", "object_type": "figure"})


def test_from_json_content_missing_object_type_is_rejected():
    with pytest.raises(DSTSerializationError):
        SequenceEntry.from_json({"entry_type": "content", "ref": "obj-1"})


def test_from_json_unrecognized_entry_type():
    with pytest.raises(DSTSerializationError):
        SequenceEntry.from_json({"entry_type": "aside", "ref": "obj-1"})


def test_no_order_index_field_exists():
    """schema §2.7/§18.3/§18.5: position in the list *is* the order --
    no `order_index`-equivalent field may ever exist on this type."""
    entry = SequenceEntry.heading(NodeId("chap-07:abc"))
    field_names = {f.name for f in entry.__dataclass_fields__.values()}
    assert field_names == {"entry_type", "ref", "object_type"}
