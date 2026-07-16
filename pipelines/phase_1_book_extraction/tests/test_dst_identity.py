"""
tests/test_dst_identity.py — Milestone 1 unit tests for
document_structure_tree.identity.compute_node_id (architecture §14,
schema §4).

Covers: determinism (I1's precondition), Tier 1 stability's precondition
(title/span/sequence cannot be threaded in -- enforced by the function
signature itself, not just by behavior), the documented Tier 2
unnumbered-sibling-ordinal-shift limitation, and cross-chapter scope
isolation (I3's precondition). Also covers the structural-shape guards
(root vs. non-root disambiguator rules).
"""
from __future__ import annotations

import inspect

import pytest

from document_structure_tree.exceptions import DSTIdentityError
from document_structure_tree.identity import IDENTITY_SCHEME_VERSION, compute_node_id
from document_structure_tree.primitives import ChapterId, IdentitySchemeVersion, Level, NodeId


# --------------------------------------------------------------------------
# Determinism (I1's precondition)
# --------------------------------------------------------------------------

def test_determinism_same_inputs_same_output():
    chapter_id = ChapterId("chap-07")
    root = compute_node_id(chapter_id, Level(0), None)
    for _ in range(5):
        assert compute_node_id(chapter_id, Level(0), None) == root

    child_a = compute_node_id(chapter_id, Level(1), root, number="4.1")
    child_b = compute_node_id(chapter_id, Level(1), root, number="4.1")
    assert child_a == child_b


def test_determinism_across_independently_derived_parent_ids():
    # The parent's own node_id must itself be reproducible for the
    # child's id to be reproducible -- exercised explicitly rather than
    # assumed.
    chapter_id = ChapterId("chap-07")
    root_1 = compute_node_id(chapter_id, Level(0), None)
    root_2 = compute_node_id(chapter_id, Level(0), None)
    assert root_1 == root_2

    child_1 = compute_node_id(chapter_id, Level(1), root_1, number="1")
    child_2 = compute_node_id(chapter_id, Level(1), root_2, number="1")
    assert child_1 == child_2


# --------------------------------------------------------------------------
# Tier 1 stability precondition: title/span/sequence structurally
# cannot be passed at all.
# --------------------------------------------------------------------------

def test_signature_excludes_structural_state_fields():
    # This is the "structurally hard, not just theoretically checkable"
    # property the roadmap's M1 risk notes call for: assert directly
    # against the function's signature that no parameter named title,
    # span, or sequence exists to be threaded through, rather than only
    # testing that varying those fields elsewhere has no effect (there
    # is nowhere else for them to be varied).
    params = set(inspect.signature(compute_node_id).parameters)
    assert "title" not in params
    assert "span" not in params
    assert "sequence" not in params


def test_node_id_unchanged_when_only_non_identity_facts_would_differ():
    # Two "builds" of the same numbered heading that would differ in
    # title/span/sequence upstream still produce the same node_id here,
    # because those facts are never inputs to this function in the
    # first place.
    chapter_id = ChapterId("chap-07")
    root = compute_node_id(chapter_id, Level(0), None)
    build_1 = compute_node_id(chapter_id, Level(1), root, number="4.1")
    build_2 = compute_node_id(chapter_id, Level(1), root, number="4.1")
    assert build_1 == build_2


# --------------------------------------------------------------------------
# Tier 2 documented limitation: inserting an earlier unnumbered sibling
# shifts every later unnumbered sibling's ordinal, and therefore its
# node_id (architecture §14).
# --------------------------------------------------------------------------

def test_tier_2_unnumbered_sibling_ordinal_shift_is_reproduced():
    chapter_id = ChapterId("chap-07")
    root = compute_node_id(chapter_id, Level(0), None)

    # "Before": two unnumbered siblings at ordinals 0 and 1.
    before_second_sibling_id = compute_node_id(chapter_id, Level(1), root, unnumbered_ordinal=1)

    # "After": an earlier unnumbered heading is discovered, so the
    # heading that used to be ordinal 1 is now ordinal 2. Its node_id
    # changes -- this is the documented, accepted Tier 2 limitation,
    # anchored here as a regression test rather than treated as a bug.
    after_same_heading_id = compute_node_id(chapter_id, Level(1), root, unnumbered_ordinal=2)

    assert before_second_sibling_id != after_same_heading_id


def test_tier_1_numbered_sibling_unaffected_by_unrelated_unnumbered_insertions():
    # A numbered heading's node_id depends only on its own number, not
    # on how many unnumbered siblings precede it -- the whole point of
    # Tier 1 stability.
    chapter_id = ChapterId("chap-07")
    root = compute_node_id(chapter_id, Level(0), None)
    numbered_before = compute_node_id(chapter_id, Level(1), root, number="4.2")
    numbered_after = compute_node_id(chapter_id, Level(1), root, number="4.2")
    assert numbered_before == numbered_after


def test_different_unnumbered_ordinals_never_collide():
    chapter_id = ChapterId("chap-07")
    root = compute_node_id(chapter_id, Level(0), None)
    ids = [compute_node_id(chapter_id, Level(1), root, unnumbered_ordinal=i) for i in range(20)]
    assert len(set(ids)) == len(ids)


def test_numbered_and_unnumbered_disambiguators_never_collide():
    # A numbered heading numbered "2" and an unnumbered heading at
    # ordinal 2 under the same parent must not collide, even though
    # "2" and 2 could naively stringify the same way.
    chapter_id = ChapterId("chap-07")
    root = compute_node_id(chapter_id, Level(0), None)
    numbered = compute_node_id(chapter_id, Level(1), root, number="2")
    unnumbered = compute_node_id(chapter_id, Level(1), root, unnumbered_ordinal=2)
    assert numbered != unnumbered


# --------------------------------------------------------------------------
# Cross-chapter scope isolation (I3's precondition)
# --------------------------------------------------------------------------

def test_cross_chapter_non_collision_same_shape():
    root_a = compute_node_id(ChapterId("chap-07"), Level(0), None)
    root_b = compute_node_id(ChapterId("chap-08"), Level(0), None)
    assert root_a != root_b

    child_a = compute_node_id(ChapterId("chap-07"), Level(1), root_a, number="4.1")
    child_b = compute_node_id(ChapterId("chap-08"), Level(1), root_b, number="4.1")
    assert child_a != child_b


# --------------------------------------------------------------------------
# Structural-shape guards
# --------------------------------------------------------------------------

def test_root_requires_no_parent_and_no_disambiguator():
    root = compute_node_id(ChapterId("chap-07"), Level(0), None)
    assert isinstance(root, NodeId)


def test_root_level_with_parent_id_is_rejected():
    root = compute_node_id(ChapterId("chap-07"), Level(0), None)
    with pytest.raises(DSTIdentityError):
        compute_node_id(ChapterId("chap-07"), Level(0), root)


def test_root_level_with_disambiguator_is_rejected():
    with pytest.raises(DSTIdentityError):
        compute_node_id(ChapterId("chap-07"), Level(0), None, number="1")


def test_non_root_level_without_parent_is_rejected():
    with pytest.raises(DSTIdentityError):
        compute_node_id(ChapterId("chap-07"), Level(1), None, number="1")


def test_non_root_requires_exactly_one_disambiguator_not_both():
    root = compute_node_id(ChapterId("chap-07"), Level(0), None)
    with pytest.raises(DSTIdentityError):
        compute_node_id(ChapterId("chap-07"), Level(1), root, number="1", unnumbered_ordinal=0)


def test_non_root_requires_exactly_one_disambiguator_not_neither():
    root = compute_node_id(ChapterId("chap-07"), Level(0), None)
    with pytest.raises(DSTIdentityError):
        compute_node_id(ChapterId("chap-07"), Level(1), root)


def test_empty_number_string_is_rejected():
    root = compute_node_id(ChapterId("chap-07"), Level(0), None)
    with pytest.raises(DSTIdentityError):
        compute_node_id(ChapterId("chap-07"), Level(1), root, number="")


def test_negative_unnumbered_ordinal_is_rejected():
    root = compute_node_id(ChapterId("chap-07"), Level(0), None)
    with pytest.raises(DSTIdentityError):
        compute_node_id(ChapterId("chap-07"), Level(1), root, unnumbered_ordinal=-1)


# --------------------------------------------------------------------------
# identity_scheme_version
# --------------------------------------------------------------------------

def test_identity_scheme_version_is_exposed_and_typed():
    assert isinstance(IDENTITY_SCHEME_VERSION, IdentitySchemeVersion)
    assert IDENTITY_SCHEME_VERSION.value == "1"


def test_node_id_is_deep_and_multi_level():
    chapter_id = ChapterId("chap-07")
    root = compute_node_id(chapter_id, Level(0), None)
    level_1 = compute_node_id(chapter_id, Level(1), root, number="4")
    level_2 = compute_node_id(chapter_id, Level(2), level_1, number="4.1")
    level_3 = compute_node_id(chapter_id, Level(3), level_2, unnumbered_ordinal=0)
    # All distinct, and reproducible when the same chain is rebuilt.
    ids = [root, level_1, level_2, level_3]
    assert len(set(ids)) == len(ids)

    rebuilt_level_1 = compute_node_id(chapter_id, Level(1), root, number="4")
    rebuilt_level_2 = compute_node_id(chapter_id, Level(2), rebuilt_level_1, number="4.1")
    rebuilt_level_3 = compute_node_id(chapter_id, Level(3), rebuilt_level_2, unnumbered_ordinal=0)
    assert rebuilt_level_1 == level_1
    assert rebuilt_level_2 == level_2
    assert rebuilt_level_3 == level_3
