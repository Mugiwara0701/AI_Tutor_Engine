"""Unit tests for the Milestone 2.2 DST Builder (`document_structure_tree.builder`)."""
import pytest

from document_structure_tree import (
    CanonicalObjectId,
    ChapterId,
    ContentRef,
    DSTBuildError,
    EntryType,
    HeadingNode,
    HeadingSource,
    Level,
    NodeId,
    ObjectType,
    ROOT_CONTENT_KEY,
    build_tree,
    compute_node_id,
)

CHAPTER = ChapterId("chap-07")


# --------------------------------------------------------------------------
# Single-node tree (root only)
# --------------------------------------------------------------------------

def test_root_only_tree():
    built = build_tree(CHAPTER, headings=[])
    assert built.tree == (built.root,)
    assert built.root.level == Level(0)
    assert built.root.parent_id is None
    assert built.root.sequence == ()
    assert built.root.node_id == compute_node_id(CHAPTER, Level(0), None)


def test_root_only_tree_is_deterministic_across_builds():
    a = build_tree(CHAPTER, headings=[])
    b = build_tree(CHAPTER, headings=[])
    assert a.root.node_id == b.root.node_id
    assert a.tree == b.tree


# --------------------------------------------------------------------------
# Multi-level tree: root -> numbered child -> unnumbered grandchild
# --------------------------------------------------------------------------

def _multilevel_headings():
    return [
        HeadingSource(id="ch4", parent_id=None, number="4", title="Motion", reading_order=0),
        HeadingSource(id="ch4-sub", parent_id="ch4", number=None, title="Distance", reading_order=1),
    ]


def test_multilevel_tree_node_ids_match_identity_function():
    built = build_tree(CHAPTER, headings=_multilevel_headings())

    root_id = compute_node_id(CHAPTER, Level(0), None)
    child_id = compute_node_id(CHAPTER, Level(1), root_id, number="4")
    grandchild_id = compute_node_id(CHAPTER, Level(2), child_id, unnumbered_ordinal=0)

    assert built.root.node_id == root_id
    child = built.nodes_by_id[child_id]
    grandchild = built.nodes_by_id[grandchild_id]

    assert child.parent_id == root_id
    assert child.level == Level(1)
    assert child.number == "4"
    assert child.title == "Motion"

    assert grandchild.parent_id == child_id
    assert grandchild.level == Level(2)
    assert grandchild.number is None
    assert grandchild.title == "Distance"


def test_multilevel_tree_hierarchy_established_via_parent_id():
    built = build_tree(CHAPTER, headings=_multilevel_headings())
    assert built.root.children == tuple(
        n.node_id for n in built.tree if n.parent_id == built.root.node_id
    )
    # exactly one level=0 node
    assert sum(1 for n in built.tree if n.level.is_root()) == 1
    # every non-root node has parent_id set and resolvable in the index
    for n in built.tree:
        if not n.level.is_root():
            assert n.parent_id is not None
            assert n.parent_id in built.nodes_by_id


# --------------------------------------------------------------------------
# Sibling ordering / unnumbered-ordinal disambiguation
# --------------------------------------------------------------------------

def test_unnumbered_siblings_get_distinct_node_ids_by_ordinal():
    headings = [
        HeadingSource(id="a", parent_id=None, number=None, reading_order=0),
        HeadingSource(id="b", parent_id=None, number=None, reading_order=1),
    ]
    built = build_tree(CHAPTER, headings)
    root_children = built.root.children
    assert len(root_children) == 2
    assert len(set(root_children)) == 2  # distinct node_ids
    a_node = built.nodes_by_id[root_children[0]]
    b_node = built.nodes_by_id[root_children[1]]
    assert a_node.title is None and b_node.title is None
    assert a_node.node_id != b_node.node_id


def test_numbered_sibling_identity_independent_of_ordinal_position():
    """A numbered heading's node_id depends only on its number, not on
    where it falls among its siblings (architecture §14, Tier 1)."""
    headings_a = [
        HeadingSource(id="x", parent_id=None, number="9.9", reading_order=0),
        HeadingSource(id="y", parent_id=None, number=None, reading_order=1),
    ]
    headings_b = [
        HeadingSource(id="y", parent_id=None, number=None, reading_order=0),
        HeadingSource(id="x", parent_id=None, number="9.9", reading_order=1),
    ]
    built_a = build_tree(CHAPTER, headings_a)
    built_b = build_tree(CHAPTER, headings_b)

    x_id_expected = compute_node_id(CHAPTER, Level(1), built_a.root.node_id, number="9.9")
    assert x_id_expected in built_a.nodes_by_id
    assert x_id_expected in built_b.nodes_by_id


def test_siblings_sorted_by_reading_order_regardless_of_input_order():
    headings = [
        HeadingSource(id="second", parent_id=None, number=None, reading_order=1),
        HeadingSource(id="first", parent_id=None, number=None, reading_order=0),
    ]
    built = build_tree(CHAPTER, headings)
    # root.children preserves reading_order (0 then 1) regardless of the
    # order HeadingSource objects were passed in.
    expected_first = compute_node_id(CHAPTER, Level(1), built.root.node_id, unnumbered_ordinal=0)
    expected_second = compute_node_id(CHAPTER, Level(1), built.root.node_id, unnumbered_ordinal=1)
    assert built.root.children == (expected_first, expected_second)


# --------------------------------------------------------------------------
# `children` / `content` derived views + sequence interleaving
# --------------------------------------------------------------------------

def test_sequence_interleaves_content_and_child_headings_by_page():
    headings = [
        HeadingSource(id="parent", parent_id=None, number="1", reading_order=0),
        HeadingSource(id="child", parent_id="parent", number=None, reading_order=1, page=12),
    ]
    content = {
        "parent": [
            ContentRef("obj-late", "definition", page=13),
            ContentRef("obj-early", "figure", page=10),
        ],
    }
    built = build_tree(CHAPTER, headings, content)
    parent_id = compute_node_id(CHAPTER, Level(1), built.root.node_id, number="1")
    parent_node = built.nodes_by_id[parent_id]

    refs_in_order = [
        (e.entry_type, str(e.ref)) for e in parent_node.sequence
    ]
    assert refs_in_order == [
        (EntryType.CONTENT, "obj-early"),   # page 10
        (EntryType.HEADING, str(parent_node.children[0])),  # page 12
        (EntryType.CONTENT, "obj-late"),    # page 13
    ]


def test_entries_missing_page_sort_last_and_keep_relative_order():
    content = {
        None: [
            ContentRef("no-page-1", "note"),
            ContentRef("no-page-2", "warning"),
            ContentRef("has-page", "figure", page=1),
        ],
    }
    built = build_tree(CHAPTER, headings=[], content_by_heading=content)
    refs = [str(e.ref) for e in built.root.sequence]
    assert refs == ["has-page", "no-page-1", "no-page-2"]


def test_content_preceding_first_heading_is_owned_by_root():
    content = {ROOT_CONTENT_KEY: [ContentRef("front-matter-1", "paragraph_group", page=1)]}
    built = build_tree(CHAPTER, headings=[], content_by_heading=content)
    assert len(built.root.sequence) == 1
    entry = built.root.sequence[0]
    assert entry.entry_type is EntryType.CONTENT
    assert entry.ref == CanonicalObjectId("front-matter-1")
    assert entry.object_type == ObjectType("paragraph_group")


def test_heading_node_derived_views_agree_with_sequence_built():
    headings = [
        HeadingSource(id="a", parent_id=None, number="1", reading_order=0, page=5),
        HeadingSource(id="b", parent_id=None, number="2", reading_order=1, page=6),
    ]
    content = {None: [ContentRef("obj-1", "definition", page=1)]}
    built = build_tree(CHAPTER, headings, content)
    assert len(built.root.content) == 1
    assert built.root.content[0].ref == CanonicalObjectId("obj-1")
    assert len(built.root.children) == 2


# --------------------------------------------------------------------------
# node_id -> node and parent_id -> children indices
# --------------------------------------------------------------------------

def test_node_index_covers_every_node_exactly_once():
    built = build_tree(CHAPTER, headings=_multilevel_headings())
    assert set(built.nodes_by_id.keys()) == {n.node_id for n in built.tree}
    assert len(built.nodes_by_id) == len(built.tree)


def test_children_index_reflects_hierarchy_including_zero_children_node():
    built = build_tree(CHAPTER, headings=_multilevel_headings())
    grandchild = [n for n in built.tree if n.title == "Distance"][0]
    assert built.children_by_parent_id[grandchild.node_id] == ()
    parent = [n for n in built.tree if n.title == "Motion"][0]
    assert built.children_by_parent_id[parent.node_id] == (grandchild.node_id,)


# --------------------------------------------------------------------------
# Every constructed node is a real HeadingNode (schema §2.6-valid)
# --------------------------------------------------------------------------

def test_every_built_node_is_a_valid_heading_node_instance():
    built = build_tree(CHAPTER, headings=_multilevel_headings())
    for n in built.tree:
        assert isinstance(n, HeadingNode)
        assert n.chapter_id == CHAPTER


# --------------------------------------------------------------------------
# Construction-precondition errors (DSTBuildError)
# --------------------------------------------------------------------------

def test_duplicate_heading_id_raises():
    with pytest.raises(DSTBuildError):
        build_tree(
            CHAPTER,
            headings=[
                HeadingSource(id="dup", parent_id=None, number="1", reading_order=0),
                HeadingSource(id="dup", parent_id=None, number="2", reading_order=1),
            ],
        )


def test_dangling_parent_reference_raises():
    with pytest.raises(DSTBuildError):
        build_tree(CHAPTER, headings=[HeadingSource(id="a", parent_id="nonexistent")])


def test_parent_cycle_raises():
    with pytest.raises(DSTBuildError):
        build_tree(
            CHAPTER,
            headings=[
                HeadingSource(id="a", parent_id="b", reading_order=0),
                HeadingSource(id="b", parent_id="a", reading_order=1),
            ],
        )


def test_self_parent_cycle_raises():
    with pytest.raises(DSTBuildError):
        build_tree(CHAPTER, headings=[HeadingSource(id="a", parent_id="a")])


# --------------------------------------------------------------------------
# Dangling *content* references are NOT a builder error (R2 is deferred
# to the validation engine, roadmap M5 -- see builder.py docstring).
# --------------------------------------------------------------------------

def test_content_ref_is_carried_through_even_if_unresolvable_elsewhere():
    content = {None: [ContentRef("does-not-exist-anywhere", "definition")]}
    built = build_tree(CHAPTER, headings=[], content_by_heading=content)
    assert built.root.sequence[0].ref == CanonicalObjectId("does-not-exist-anywhere")


# --------------------------------------------------------------------------
# No `order_index`-like field anywhere -- order is positional only
# (schema §2.7, §18.3, §18.5; mirrors heading_node's own risk note).
# --------------------------------------------------------------------------

def test_sequence_entries_carry_no_order_index_field():
    built = build_tree(
        CHAPTER,
        headings=[HeadingSource(id="a", parent_id=None, number="1", reading_order=0)],
        content_by_heading={None: [ContentRef("obj-1", "definition")]},
    )
    entry = built.root.sequence[0]
    assert not hasattr(entry, "order_index")
    assert "order_index" not in entry.to_json()