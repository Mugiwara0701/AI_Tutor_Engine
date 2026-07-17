"""Unit tests for `HeadingNode` (schema §2.6)."""
import pytest

from document_structure_tree import (
    BlockIndex,
    BlockRange,
    CanonicalObjectId,
    ChapterId,
    DSTSerializationError,
    DSTValueError,
    HeadingNode,
    Level,
    NodeId,
    ObjectType,
    SequenceEntry,
    Span,
    compute_node_id,
    round_trip,
)

CHAPTER = ChapterId("chap-07")


def _root_id() -> NodeId:
    return compute_node_id(CHAPTER, Level(0), None)


def make_root(**overrides) -> HeadingNode:
    fields = dict(
        node_id=_root_id(),
        chapter_id=CHAPTER,
        level=Level(0),
        parent_id=None,
        sequence=(),
        span=Span(),
    )
    fields.update(overrides)
    return HeadingNode(**fields)


def make_child(root_id: NodeId, **overrides) -> HeadingNode:
    fields = dict(
        node_id=compute_node_id(CHAPTER, Level(1), root_id, number="4.1"),
        chapter_id=CHAPTER,
        level=Level(1),
        parent_id=root_id,
        number="4.1",
        title="Newton's Second Law",
        sequence=(),
        span=Span(),
    )
    fields.update(overrides)
    return HeadingNode(**fields)


# --------------------------------------------------------------------------
# Valid construction
# --------------------------------------------------------------------------

def test_root_node_constructs():
    root = make_root()
    assert root.level.is_root()
    assert root.parent_id is None


def test_non_root_node_constructs():
    root_id = _root_id()
    child = make_child(root_id)
    assert child.parent_id == root_id
    assert child.number == "4.1"
    assert child.title == "Newton's Second Law"


def test_sequence_defaults_are_normalized_to_tuple():
    root = make_root(sequence=[])
    assert root.sequence == ()
    assert isinstance(root.sequence, tuple)


# --------------------------------------------------------------------------
# Local validation: parent_id null iff level == 0 (schema §2.6, local S2)
# --------------------------------------------------------------------------

def test_root_with_parent_id_is_rejected():
    with pytest.raises(DSTValueError):
        make_root(parent_id=NodeId("chap-07:someparent"))


def test_non_root_without_parent_id_is_rejected():
    root_id = _root_id()
    with pytest.raises(DSTValueError):
        make_child(root_id, parent_id=None)


# --------------------------------------------------------------------------
# number / title
# --------------------------------------------------------------------------

def test_empty_number_is_rejected():
    root_id = _root_id()
    with pytest.raises(DSTValueError):
        make_child(root_id, number="")


def test_empty_title_is_rejected():
    root_id = _root_id()
    with pytest.raises(DSTValueError):
        make_child(root_id, title="")


def test_number_and_title_omitted_from_json_when_absent():
    root = make_root()
    encoded = root.to_json()
    assert "number" not in encoded
    assert "title" not in encoded


def test_parent_id_present_and_null_for_root_never_omitted():
    root = make_root()
    encoded = root.to_json()
    assert "parent_id" in encoded
    assert encoded["parent_id"] is None


# --------------------------------------------------------------------------
# Derived views (schema §2.7, "Derived views") over this node's own sequence
# --------------------------------------------------------------------------

def test_children_and_content_derived_views_preserve_order():
    root_id = _root_id()
    child_a_id = compute_node_id(CHAPTER, Level(1), root_id, number="4.1")
    child_b_id = compute_node_id(CHAPTER, Level(1), root_id, number="4.2")
    node = make_root(
        sequence=(
            SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("paragraph_group")),
            SequenceEntry.heading(child_a_id),
            SequenceEntry.content(CanonicalObjectId("obj-2"), ObjectType("definition")),
            SequenceEntry.heading(child_b_id),
        )
    )
    assert node.children == (child_a_id, child_b_id)
    assert [c.ref for c in node.content] == [CanonicalObjectId("obj-1"), CanonicalObjectId("obj-2")]


def test_children_empty_when_no_heading_entries():
    node = make_root(sequence=(SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("figure")),))
    assert node.children == ()


# --------------------------------------------------------------------------
# Serialization round-trips
# --------------------------------------------------------------------------

def test_round_trip_root():
    encoded_once, decoded, encoded_twice = round_trip(make_root())
    assert encoded_once == encoded_twice
    assert decoded == make_root()


def test_round_trip_full_child_with_span_and_sequence():
    root_id = _root_id()
    node = make_child(
        root_id,
        sequence=(SequenceEntry.content(CanonicalObjectId("obj-442"), ObjectType("definition")),),
        span=Span(block_range=BlockRange(BlockIndex(3), BlockIndex(40))),
    )
    encoded_once, decoded, encoded_twice = round_trip(node)
    assert encoded_once == encoded_twice
    assert decoded == node


def test_from_json_missing_parent_id_key():
    data = make_root().to_json()
    del data["parent_id"]
    with pytest.raises(DSTSerializationError):
        HeadingNode.from_json(data)


def test_from_json_non_root_with_null_parent_id_is_rejected():
    root_id = _root_id()
    data = make_child(root_id).to_json()
    data["parent_id"] = None
    with pytest.raises(DSTValueError):
        HeadingNode.from_json(data)


# --------------------------------------------------------------------------
# node_id derivation is external (Milestone 1) -- this type only stores it
# --------------------------------------------------------------------------

def test_node_id_is_stored_verbatim_not_recomputed():
    """HeadingNode never recomputes node_id from its other fields --
    an arbitrary NodeId is accepted as-is (identity derivation is
    identity.compute_node_id's job, called before construction)."""
    node = make_root(node_id=NodeId("chap-07:not-a-real-derivation"))
    assert node.node_id == NodeId("chap-07:not-a-real-derivation")
