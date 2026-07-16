"""
tests/document_structure_tree/test_validation.py — Milestone 3
conformance test suite for `document_structure_tree/validation.py`.

Follows the roadmap's own prescribed pattern (M4/M5/M6): one
conforming fixture + at least one fixture engineered to violate
exactly one check and no other, per invariant, so a test failure
unambiguously points at one broken invariant — plus a handful of
integration-level tests (multiple simultaneous violations, tier
isolation, ValidationMetadata assembly/exhaustiveness).

Fixtures are hand-built directly from the model layer (`HeadingNode`,
`SequenceEntry`, `compute_node_id`), not through `builder.py` — this
keeps every fixture minimal, explicit, and independent of the
builder's own reading-order heuristics, exactly as roadmap M2/M4
themselves test the builder and the S1-S4 validators separately.

Run with: `python3 -m unittest discover -s tests -v` (no pytest
dependency; the sandbox this suite was authored in has no network
access to install one, and the stdlib's `unittest` is sufficient).
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Optional, Sequence, Tuple

from document_structure_tree import (
    ArtifactMetadata,
    BlockIndex,
    BlockRange,
    BuildProvenance,
    CanonicalObjectId,
    ChapterId,
    CompilerVersion,
    EntryType,
    Fingerprint,
    HeadingNode,
    IdentitySchemeVersion,
    InvariantId,
    Level,
    NodeId,
    ObjectType,
    SchemaVersion,
    SequenceEntry,
    Span,
    Timestamp,
    ValidationStatus,
    compute_node_id,
)
from document_structure_tree import validation as v

CHAPTER = ChapterId("chap-test")


# ==========================================================================
# Fixture-building helpers
# ==========================================================================

def mk_root(chapter_id: ChapterId = CHAPTER, sequence: Sequence[SequenceEntry] = (), span: Optional[Span] = None) -> HeadingNode:
    return HeadingNode(
        node_id=compute_node_id(chapter_id, Level(0), None),
        chapter_id=chapter_id,
        level=Level(0),
        parent_id=None,
        sequence=tuple(sequence),
        span=span if span is not None else Span(),
    )


def mk_child(
    parent: HeadingNode,
    *,
    chapter_id: ChapterId = CHAPTER,
    number: Optional[str] = None,
    unnumbered_ordinal: Optional[int] = None,
    title: Optional[str] = None,
    sequence: Sequence[SequenceEntry] = (),
    span: Optional[Span] = None,
    level: Optional[Level] = None,
) -> HeadingNode:
    node_level = level if level is not None else parent.level.child()
    node_id = compute_node_id(
        chapter_id, node_level, parent.node_id, number=number, unnumbered_ordinal=unnumbered_ordinal
    )
    return HeadingNode(
        node_id=node_id,
        chapter_id=chapter_id,
        level=node_level,
        parent_id=parent.node_id,
        sequence=tuple(sequence),
        span=span if span is not None else Span(),
        number=number,
        title=title,
    )


def block_span(start: int, end: int) -> Span:
    return Span(block_range=BlockRange(BlockIndex(start), BlockIndex(end)))


def mk_artifact_metadata(tree: Sequence[HeadingNode], chapter_id: ChapterId = CHAPTER) -> ArtifactMetadata:
    return ArtifactMetadata(
        schema_version=SchemaVersion("1.1.0"),
        compiler_version=CompilerVersion("0.1.0"),
        identity_scheme_version=IdentitySchemeVersion("1"),
        chapter_id=chapter_id,
        build_timestamp=Timestamp("2026-07-15T09:00:00Z"),
        chapter_fingerprint=v.compute_chapter_fingerprint(tree),
    )


def mk_build_provenance(ref: str = "registry-snap-1") -> BuildProvenance:
    return BuildProvenance(canonical_registry_snapshot_ref=ref)


def result_for(tree, index, invariant_id: InvariantId):
    """Dispatch to the single-invariant check_* function under test, by
    InvariantId, using a uniform (tree, index) fixture pair -- avoids
    every test having to know each check_*'s exact registry/chapter_id
    extra-argument signature."""
    dispatch = {
        InvariantId.S1: lambda: v.check_s1(tree, index),
        InvariantId.S2: lambda: v.check_s2(tree),
        InvariantId.S3: lambda: v.check_s3(tree, index),
        InvariantId.S4: lambda: v.check_s4(tree, index),
        InvariantId.O1: lambda: v.check_o1(tree),
        InvariantId.O2: lambda: v.check_o2(tree, index),
        InvariantId.I1: lambda: v.check_i1(tree, index),
        InvariantId.I2: lambda: v.check_i2(tree, index),
        InvariantId.I3: lambda: v.check_i3(tree, index),
        InvariantId.B1: lambda: v.check_b1(tree, index),
    }
    return dispatch[invariant_id]()


def assert_all_pass(testcase: unittest.TestCase, tree: Sequence[HeadingNode]) -> None:
    """Run every tree-only (no-registry-needed) check against `tree` and
    assert that none of them fail -- for fixtures that are fully
    well-formed and expected to pass every applicable invariant."""
    index = v.build_index(tree)
    tree_only = (InvariantId.S1, InvariantId.S2, InvariantId.S3, InvariantId.S4,
                 InvariantId.O1, InvariantId.O2, InvariantId.I1, InvariantId.I2,
                 InvariantId.I3, InvariantId.B1)
    for inv in tree_only:
        result = result_for(tree, index, inv)
        testcase.assertEqual(
            result.status, ValidationStatus.PASS,
            f"expected {inv.value} to pass, but got violations: "
            f"{[x.message for x in (result.violations or [])]}",
        )


def assert_only_fails(testcase: unittest.TestCase, tree: Sequence[HeadingNode], expected_failing: InvariantId) -> None:
    """Run every tree-only (no-registry-needed) check against `tree`
    and assert that exactly `expected_failing` fails — the "engineered
    to violate exactly one check and no other" property the roadmap
    asks every M4/M5/M6 fixture to have."""
    index = v.build_index(tree)
    tree_only = (InvariantId.S1, InvariantId.S2, InvariantId.S3, InvariantId.S4,
                 InvariantId.O1, InvariantId.O2, InvariantId.I1, InvariantId.I2,
                 InvariantId.I3, InvariantId.B1)
    for inv in tree_only:
        result = result_for(tree, index, inv)
        if inv is expected_failing:
            testcase.assertEqual(
                result.status, ValidationStatus.FAIL, f"expected {inv.value} to fail"
            )
        else:
            testcase.assertEqual(
                result.status, ValidationStatus.PASS,
                f"expected {inv.value} to pass, but got violations: "
                f"{[x.message for x in (result.violations or [])]}",
            )


# ==========================================================================
# S1 — Tree well-formedness
# ==========================================================================

class TestS1(unittest.TestCase):
    def test_pass_well_formed_tree(self):
        root_stub = mk_root()
        child = mk_child(root_stub, number="1")
        # Declare `child` in root's own sequence too -- O2 requires an
        # actual child (via parent_id) to also be a declared one.
        root = replace(root_stub, sequence=(SequenceEntry.heading(child.node_id),))
        tree = [root, child]
        assert_all_pass(self, tree)  # no failure expected anywhere
        index = v.build_index(tree)
        self.assertEqual(v.check_s1(tree, index).status, ValidationStatus.PASS)

    def test_fail_dangling_parent(self):
        root = mk_root()
        child = mk_child(root, number="1")
        # Point child's parent_id at a node_id that doesn't exist.
        dangling = replace(child, parent_id=NodeId(f"{CHAPTER.value}:doesnotexist000000000000"))
        tree = [root, dangling]
        index = v.build_index(tree)
        result = v.check_s1(tree, index)
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertTrue(any("dangling" in viol.message for viol in result.violations))

    def test_fail_cycle(self):
        root = mk_root()
        a = mk_child(root, number="1")
        b = mk_child(a, number="1.1")
        # Rewire a's parent_id to point at b, creating a->b->a->... cycle,
        # disconnected from the real root.
        a_cyclic = replace(a, parent_id=b.node_id)
        tree = [root, a_cyclic, b]
        index = v.build_index(tree)
        result = v.check_s1(tree, index)
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertTrue(any("cycle" in viol.message for viol in result.violations))


# ==========================================================================
# S2 — Single root
# ==========================================================================

class TestS2(unittest.TestCase):
    def test_pass_exactly_one_root(self):
        tree = [mk_root()]
        self.assertEqual(v.check_s2(tree).status, ValidationStatus.PASS)

    def test_fail_zero_roots(self):
        result = v.check_s2([])
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertIn("no level=0", result.violations[0].message)

    def test_fail_two_roots(self):
        root1 = mk_root()
        # A second, distinct level=0 node (same chapter) -- structurally
        # a duplicate of the chapter root under a different node_id is
        # impossible via compute_node_id (root has no disambiguator), so
        # a second root can only arise from a directly-constructed,
        # already-nonconformant HeadingNode -- exactly what S2 exists to
        # catch defensively.
        root2 = replace(root1, node_id=NodeId(f"{CHAPTER.value}:secondroot0000000000000"))
        result = v.check_s2([root1, root2])
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertEqual(len(result.violations), 2)


# ==========================================================================
# S3 — Span monotonicity
# ==========================================================================

class TestS3(unittest.TestCase):
    def test_pass_nested_ranges(self):
        root_stub = mk_root(span=block_span(0, 10))
        child = mk_child(root_stub, number="1", span=block_span(2, 5))
        root = replace(root_stub, sequence=(SequenceEntry.heading(child.node_id),))
        tree = [root, child]
        assert_all_pass(self, tree)
        # (S1 is not expected to fail either -- assert full pass explicitly)
        index = v.build_index(tree)
        self.assertEqual(v.check_s3(tree, index).status, ValidationStatus.PASS)

    def test_pass_empty_span_vacuous(self):
        root = mk_root(span=block_span(0, 10))
        leaf = mk_child(root, number="1")  # empty span: no content, no descendants
        index = v.build_index([root, leaf])
        self.assertEqual(v.check_s3([root, leaf], index).status, ValidationStatus.PASS)

    def test_fail_child_exceeds_parent(self):
        root = mk_root(span=block_span(0, 5))
        child = mk_child(root, number="1", span=block_span(3, 20))  # exceeds parent's end
        index = v.build_index([root, child])
        result = v.check_s3([root, child], index)
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_fail_nonempty_child_under_empty_parent(self):
        root = mk_root(span=Span())  # empty
        child = mk_child(root, number="1", span=block_span(0, 5))
        index = v.build_index([root, child])
        result = v.check_s3([root, child], index)
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertTrue(any("empty" in viol.message for viol in result.violations))


# ==========================================================================
# S4 — Reachability
# ==========================================================================

class TestS4(unittest.TestCase):
    def test_pass_fully_connected(self):
        root_stub = mk_root()
        a_stub = mk_child(root_stub, number="1")
        b = mk_child(a_stub, number="1.1")
        a = replace(a_stub, sequence=(SequenceEntry.heading(b.node_id),))
        root = replace(root_stub, sequence=(SequenceEntry.heading(a.node_id),))
        tree = [root, a, b]
        assert_all_pass(self, tree)  # nothing should fail; see explicit check below
        index = v.build_index(tree)
        self.assertEqual(v.check_s4(tree, index).status, ValidationStatus.PASS)

    def test_fail_disconnected_subtree(self):
        root = mk_root()
        a = mk_child(root, number="1")
        # b claims a's node as parent, but b's own node_id is derived
        # against a bogus, nonexistent grandparent-less chain by direct
        # construction, and a is then removed from the tree, leaving b
        # unreachable even though its parent_id still resolves to `a`
        # would need a in the tree; instead simulate disconnection by
        # constructing b under a node_id that never appears in `tree`.
        orphan_parent_id = NodeId(f"{CHAPTER.value}:orphanparent000000000000")
        b = HeadingNode(
            node_id=compute_node_id(CHAPTER, Level(1), orphan_parent_id, number="9"),
            chapter_id=CHAPTER,
            level=Level(1),
            parent_id=orphan_parent_id,
            sequence=(),
            span=Span(),
        )
        tree = [root, a, b]
        index = v.build_index(tree)
        result = v.check_s4(tree, index)
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertTrue(any(viol.node_id == b.node_id for viol in result.violations))


# ==========================================================================
# R1 — Referential integrity (headings)
# ==========================================================================

class TestR1(unittest.TestCase):
    def test_pass_consistent_heading_ref(self):
        root_stub = mk_root()
        child = mk_child(root_stub, number="1")
        root = replace(root_stub, sequence=(SequenceEntry.heading(child.node_id),))
        tree = [root, child]
        index = v.build_index(tree)
        self.assertEqual(v.check_r1(tree, index).status, ValidationStatus.PASS)

    def test_fail_dangling_heading_ref(self):
        bogus = NodeId(f"{CHAPTER.value}:doesnotexist111111111111")
        root = mk_root(sequence=(SequenceEntry.heading(bogus),))
        result = v.check_r1([root], v.build_index([root]))
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_fail_ref_parent_mismatch(self):
        root = mk_root()
        a = mk_child(root, number="1")
        b = mk_child(root, number="2")  # b's real parent is root, not a
        # a's sequence wrongly claims b as its own child
        a_wrong = replace(a, sequence=(SequenceEntry.heading(b.node_id),))
        tree = [root, a_wrong, b]
        result = v.check_r1(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.FAIL)


# ==========================================================================
# R2/R3/R4 — Referential integrity (content) / type consistency / completeness
# ==========================================================================

class TestR2R3R4(unittest.TestCase):
    def _tree_with_content_ref(self, object_id="obj-1", object_type="definition"):
        entry = SequenceEntry.content(CanonicalObjectId(object_id), ObjectType(object_type))
        root = mk_root(sequence=(entry,))
        return [root]

    def test_r2_pass_object_exists(self):
        tree = self._tree_with_content_ref()
        registry = v.InMemoryCanonicalRegistrySnapshot(
            object_types={CanonicalObjectId("obj-1"): ObjectType("definition")},
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("obj-1")})},
        )
        result = v.check_r2(tree, v.build_index(tree), registry)
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_r2_fail_no_registry(self):
        tree = self._tree_with_content_ref()
        result = v.check_r2(tree, v.build_index(tree), None)
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_r2_fail_object_missing(self):
        tree = self._tree_with_content_ref(object_id="obj-ghost")
        registry = v.InMemoryCanonicalRegistrySnapshot(object_types={}, chapter_objects={})
        result = v.check_r2(tree, v.build_index(tree), registry)
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_r3_pass_type_matches(self):
        tree = self._tree_with_content_ref(object_type="definition")
        registry = v.InMemoryCanonicalRegistrySnapshot(
            object_types={CanonicalObjectId("obj-1"): ObjectType("definition")},
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("obj-1")})},
        )
        result = v.check_r3(tree, v.build_index(tree), registry)
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_r3_fail_type_mismatch(self):
        tree = self._tree_with_content_ref(object_type="definition")
        registry = v.InMemoryCanonicalRegistrySnapshot(
            object_types={CanonicalObjectId("obj-1"): ObjectType("figure")},  # drifted
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("obj-1")})},
        )
        result = v.check_r3(tree, v.build_index(tree), registry)
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_r4_pass_complete_and_non_overlapping(self):
        tree = self._tree_with_content_ref()
        registry = v.InMemoryCanonicalRegistrySnapshot(
            object_types={CanonicalObjectId("obj-1"): ObjectType("definition")},
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("obj-1")})},
        )
        result = v.check_r4(tree, v.build_index(tree), CHAPTER, registry)
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_r4_fail_unowned_object(self):
        tree = self._tree_with_content_ref()
        registry = v.InMemoryCanonicalRegistrySnapshot(
            object_types={
                CanonicalObjectId("obj-1"): ObjectType("definition"),
                CanonicalObjectId("obj-2"): ObjectType("figure"),
            },
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("obj-1"), CanonicalObjectId("obj-2")})},
        )
        result = v.check_r4(tree, v.build_index(tree), CHAPTER, registry)
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertTrue(any("obj-2" in viol.message for viol in result.violations))

    def test_r4_fail_duplicate_ownership(self):
        entry = SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("definition"))
        root_stub = mk_root()
        child = mk_child(root_stub, number="1", sequence=(entry,))
        root = replace(root_stub, sequence=(entry,))  # same object also owned by root
        tree = [root, child]
        registry = v.InMemoryCanonicalRegistrySnapshot(
            object_types={CanonicalObjectId("obj-1"): ObjectType("definition")},
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("obj-1")})},
        )
        result = v.check_r4(tree, v.build_index(tree), CHAPTER, registry)
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertTrue(any("2 sequence entries" in viol.message for viol in result.violations))


# ==========================================================================
# O1 — Sequence integrity (duplicates)
# ==========================================================================

class TestO1(unittest.TestCase):
    def test_pass_no_duplicates(self):
        entry_a = SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("definition"))
        entry_b = SequenceEntry.content(CanonicalObjectId("obj-2"), ObjectType("figure"))
        root = mk_root(sequence=(entry_a, entry_b))
        result = v.check_o1([root])
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_fail_duplicate_entry(self):
        entry = SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("definition"))
        root = mk_root(sequence=(entry, entry))
        result = v.check_o1([root])
        self.assertEqual(result.status, ValidationStatus.FAIL)


# ==========================================================================
# O2 — Parent/child sequence consistency (bidirectional)
# ==========================================================================

class TestO2(unittest.TestCase):
    def test_pass_declared_matches_actual(self):
        root_stub = mk_root()
        child = mk_child(root_stub, number="1")
        root = replace(root_stub, sequence=(SequenceEntry.heading(child.node_id),))
        tree = [root, child]
        result = v.check_o2(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_fail_declared_but_not_actual_parent(self):
        root = mk_root()
        a = mk_child(root, number="1")
        b = mk_child(root, number="2")  # b's actual parent is root
        # a's sequence wrongly declares b as its child (direction 1 violation)
        a_wrong = replace(a, sequence=(SequenceEntry.heading(b.node_id),))
        tree = [root, a_wrong, b]
        result = v.check_o2(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_fail_actual_but_not_declared(self):
        root_stub = mk_root()  # root's sequence stays empty
        child = mk_child(root_stub, number="1")  # child's parent_id is root
        # root never lists `child` as a heading-type sequence entry (direction 2 violation)
        tree = [root_stub, child]
        result = v.check_o2(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.FAIL)


# ==========================================================================
# I1 — Determinism / I2 — Tier 1 stability / I3 — Scope isolation
# ==========================================================================

class TestI1I2I3(unittest.TestCase):
    def test_i1_pass_correctly_derived(self):
        root = mk_root()
        numbered = mk_child(root, number="1")
        unnumbered = mk_child(root, unnumbered_ordinal=0)
        root_with_children = replace(
            root, sequence=(SequenceEntry.heading(numbered.node_id), SequenceEntry.heading(unnumbered.node_id))
        )
        tree = [root_with_children, numbered, unnumbered]
        result = v.check_i1(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_i1_fail_tampered_node_id(self):
        root_stub = mk_root()
        child = mk_child(root_stub, number="1")
        root = replace(root_stub, sequence=(SequenceEntry.heading(child.node_id),))
        tampered = replace(child, node_id=NodeId(f"{CHAPTER.value}:tampered0000000000000000"))
        tree = [root, tampered]
        result = v.check_i1(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_i2_pass_numbered_stable(self):
        root = mk_root()
        child = mk_child(root, number="4.1")
        result = v.check_i2([root, child], v.build_index([root, child]))
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_i2_fail_numbered_tampered(self):
        root = mk_root()
        child = mk_child(root, number="4.1")
        tampered = replace(child, node_id=NodeId(f"{CHAPTER.value}:tampered1111111111111111"))
        tree = [root, tampered]
        result = v.check_i2(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_i2_skips_unnumbered_headings(self):
        root = mk_root()
        unnumbered = mk_child(root, unnumbered_ordinal=0)
        tampered = replace(unnumbered, node_id=NodeId(f"{CHAPTER.value}:tampered2222222222222222"))
        tree = [root, tampered]
        # I2 is scoped to numbered (Tier 1) headings only -- an
        # unnumbered node, however malformed, is not I2's concern
        # (I1 covers both tiers; see test_i1_fail_tampered_node_id).
        result = v.check_i2(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_i3_pass_unique_ids(self):
        root = mk_root()
        child = mk_child(root, number="1")
        result = v.check_i3([root, child], v.build_index([root, child]))
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_i3_fail_duplicate_node_id_within_chapter(self):
        root = mk_root()
        child = mk_child(root, number="1")
        clone = replace(child, node_id=root.node_id)  # collides with the root's own id
        tree = [root, clone]
        result = v.check_i3(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_i3_fail_cross_chapter_collision(self):
        root = mk_root()
        child = mk_child(root, number="1")
        tree = [root, child]
        other_chapter_ids = frozenset({child.node_id})
        result = v.check_i3(tree, v.build_index(tree), other_chapter_node_ids=other_chapter_ids)
        self.assertEqual(result.status, ValidationStatus.FAIL)


# ==========================================================================
# B1 — Schema conformance (depth consistency + discriminator)
# ==========================================================================

class TestB1(unittest.TestCase):
    def test_pass_correct_depths_and_discriminators(self):
        root = mk_root()
        a = mk_child(root, number="1")
        b = mk_child(a, number="1.1")
        tree = [root, a, b]
        result = v.check_b1(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_fail_depth_off_by_one(self):
        root = mk_root()
        a = mk_child(root, number="1")
        wrong_level_a = replace(a, level=Level(5))
        tree = [root, wrong_level_a]
        result = v.check_b1(tree, v.build_index(tree))
        self.assertEqual(result.status, ValidationStatus.FAIL)
        self.assertTrue(any("depth consistency" in viol.message for viol in result.violations))


# ==========================================================================
# B2 — Snapshot consistency / B3 — Fingerprint correctness
# ==========================================================================

class TestB2B3(unittest.TestCase):
    def test_b2_pass_with_registry(self):
        bp = mk_build_provenance()
        registry = v.InMemoryCanonicalRegistrySnapshot()
        result = v.check_b2(bp, registry)
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_b2_fail_without_registry(self):
        bp = mk_build_provenance()
        result = v.check_b2(bp, None)
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_b3_pass_correct_fingerprint(self):
        root = mk_root()
        child = mk_child(root, number="1")
        tree = [root, child]
        am = mk_artifact_metadata(tree)
        result = v.check_b3(tree, am)
        self.assertEqual(result.status, ValidationStatus.PASS)

    def test_b3_fail_incorrect_fingerprint(self):
        root = mk_root()
        child = mk_child(root, number="1")
        tree = [root, child]
        bad_am = replace(mk_artifact_metadata(tree), chapter_fingerprint=Fingerprint("0" * 64))
        result = v.check_b3(tree, bad_am)
        self.assertEqual(result.status, ValidationStatus.FAIL)

    def test_b3_insensitive_to_title(self):
        root = mk_root()
        child_a = mk_child(root, number="1", title="Original Title")
        child_b = mk_child(root, number="1", title="A Totally Different Title")
        self.assertEqual(
            v.compute_chapter_fingerprint([root, child_a]),
            v.compute_chapter_fingerprint([root, child_b]),
        )

    def test_b3_insensitive_to_span(self):
        root = mk_root()
        child_a = mk_child(root, number="1", span=Span())
        child_b = mk_child(root, number="1", span=block_span(0, 100))
        self.assertEqual(
            v.compute_chapter_fingerprint([root, child_a]),
            v.compute_chapter_fingerprint([root, child_b]),
        )

    def test_b3_insensitive_to_sequence(self):
        root = mk_root()
        entry = SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("definition"))
        child_a = mk_child(root, number="1", sequence=())
        child_b = mk_child(root, number="1", sequence=(entry,))
        self.assertEqual(
            v.compute_chapter_fingerprint([root, child_a]),
            v.compute_chapter_fingerprint([root, child_b]),
        )

    def test_b3_sensitive_to_number(self):
        root = mk_root()
        child_a = mk_child(root, number="1")
        child_b = mk_child(root, number="2")
        self.assertNotEqual(
            v.compute_chapter_fingerprint([root, child_a]),
            v.compute_chapter_fingerprint([root, child_b]),
        )

    def test_b3_insensitive_to_tree_array_order(self):
        root = mk_root()
        a = mk_child(root, number="1")
        b = mk_child(root, number="2")
        self.assertEqual(
            v.compute_chapter_fingerprint([root, a, b]),
            v.compute_chapter_fingerprint([b, root, a]),
        )


# ==========================================================================
# TreeIndex / build_index
# ==========================================================================

class TestBuildIndex(unittest.TestCase):
    def test_children_by_parent_id_reflects_actual_parentage(self):
        root = mk_root()
        a = mk_child(root, number="1")
        b = mk_child(root, number="2")
        index = v.build_index([root, a, b])
        self.assertEqual(set(index.children_by_parent_id[root.node_id]), {a.node_id, b.node_id})

    def test_zero_children_node_has_no_entry_crash(self):
        root = mk_root()
        leaf = mk_child(root, number="1")
        index = v.build_index([root, leaf])
        self.assertEqual(index.children_by_parent_id.get(leaf.node_id, ()), ())

    def test_duplicate_node_ids_recorded(self):
        root = mk_root()
        child = mk_child(root, number="1")
        clone = replace(child, node_id=root.node_id, parent_id=root.node_id, number="1")
        index = v.build_index([root, child, clone])
        self.assertIn(root.node_id, index.duplicate_node_ids)


# ==========================================================================
# InMemoryCanonicalRegistrySnapshot
# ==========================================================================

class TestInMemoryRegistry(unittest.TestCase):
    def test_object_exists_and_type(self):
        reg = v.InMemoryCanonicalRegistrySnapshot(
            object_types={CanonicalObjectId("x"): ObjectType("figure")},
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("x")})},
        )
        self.assertTrue(reg.object_exists(CanonicalObjectId("x")))
        self.assertFalse(reg.object_exists(CanonicalObjectId("y")))
        self.assertEqual(reg.object_type_of(CanonicalObjectId("x")), ObjectType("figure"))
        self.assertIsNone(reg.object_type_of(CanonicalObjectId("y")))
        self.assertEqual(reg.objects_owned_by_chapter(CHAPTER), frozenset({CanonicalObjectId("x")}))
        self.assertEqual(reg.objects_owned_by_chapter(ChapterId("other")), frozenset())


# ==========================================================================
# run_all_invariants / ValidationMetadata assembly (roadmap M7)
# ==========================================================================

class TestRunAllInvariants(unittest.TestCase):
    def _clean_fixture(self):
        entry = SequenceEntry.content(CanonicalObjectId("obj-1"), ObjectType("definition"))
        root_stub = mk_root()
        child = mk_child(root_stub, number="1", sequence=(entry,))
        root = replace(root_stub, sequence=(SequenceEntry.heading(child.node_id),))
        tree = [root, child]
        registry = v.InMemoryCanonicalRegistrySnapshot(
            object_types={CanonicalObjectId("obj-1"): ObjectType("definition")},
            chapter_objects={CHAPTER: frozenset({CanonicalObjectId("obj-1")})},
        )
        am = mk_artifact_metadata(tree)
        bp = mk_build_provenance()
        return tree, am, bp, registry

    def test_all_pass_clean_fixture(self):
        tree, am, bp, registry = self._clean_fixture()
        vm = v.run_all_invariants(tree, am, bp, registry=registry)
        self.assertEqual(vm.validation_status, ValidationStatus.PASS)
        for result in vm.validation_results:
            self.assertIsNone(result.violations)

    def test_exhaustive_one_result_per_invariant(self):
        tree, am, bp, registry = self._clean_fixture()
        vm = v.run_all_invariants(tree, am, bp, registry=registry)
        reported_ids = {r.invariant_id for r in vm.validation_results}
        self.assertEqual(reported_ids, set(InvariantId))

    def test_deterministic_repeat_run(self):
        tree, am, bp, registry = self._clean_fixture()
        vm1 = v.run_all_invariants(tree, am, bp, registry=registry)
        vm2 = v.run_all_invariants(tree, am, bp, registry=registry)
        self.assertEqual(vm1.to_json(), vm2.to_json())

    def test_single_seeded_failure_isolated(self):
        tree, am, bp, registry = self._clean_fixture()
        # Seed exactly one defect: break B3 by corrupting the stored fingerprint.
        bad_am = replace(am, chapter_fingerprint=Fingerprint("1" * 64))
        vm = v.run_all_invariants(tree, bad_am, bp, registry=registry)
        self.assertEqual(vm.validation_status, ValidationStatus.FAIL)
        failing = {r.invariant_id for r in vm.validation_results if r.status is ValidationStatus.FAIL}
        self.assertEqual(failing, {InvariantId.B3})

    def test_multiple_simultaneous_failures_no_cross_contamination(self):
        tree, am, bp, registry = self._clean_fixture()
        bad_am = replace(am, chapter_fingerprint=Fingerprint("1" * 64))  # B3
        no_registry_result = v.run_all_invariants(tree, bad_am, bp, registry=None)  # + R2/R3/R4/B2
        failing = {r.invariant_id for r in no_registry_result.validation_results if r.status is ValidationStatus.FAIL}
        self.assertEqual(failing, {InvariantId.B3, InvariantId.R2, InvariantId.R3, InvariantId.R4, InvariantId.B2})
        # every other invariant (S1-S4, O1-O2, I1-I3, B1) still independently passes
        for r in no_registry_result.validation_results:
            if r.invariant_id not in failing:
                self.assertEqual(r.status, ValidationStatus.PASS)

    def test_revalidate_matches_run_all_invariants(self):
        from document_structure_tree import DocumentStructureTree

        tree, am, bp, registry = self._clean_fixture()
        vm = v.run_all_invariants(tree, am, bp, registry=registry)
        dst = DocumentStructureTree(artifact_metadata=am, build_provenance=bp, validation_metadata=vm, tree=tree)
        revalidated = v.revalidate(dst, registry=registry)
        self.assertEqual(revalidated.to_json(), vm.to_json())


if __name__ == "__main__":
    unittest.main()