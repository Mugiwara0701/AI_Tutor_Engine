"""tests/test_dst_registry_snapshot.py — Milestone 5: Compiler
Integration, `document_structure_tree.registry_snapshot.
CompilerRegistrySnapshot` -- the `CanonicalRegistrySnapshot` adapter
over this codebase's real `compiler.RegistryManager`.

These tests exercise the adapter against the REAL compiler registry
infrastructure (`compiler.registries.create_registry_manager()` /
`populate_registries()`), not a hand-rolled stand-in -- the whole point
of this module is that it is the seam between Milestone 3's Protocol
and this codebase's actual canonical registries, so the test double
that matters here is the real `RegistryManager`, not a fake of it.
"""
from __future__ import annotations

import unittest

from compiler.registries import create_registry_manager, populate_registries
from document_structure_tree import CanonicalObjectId, ChapterId, ObjectType
from document_structure_tree.registry_snapshot import (
    EXCLUDED_REGISTRY_NAMES,
    CompilerRegistrySnapshot,
)

CHAPTER_ID = ChapterId("chap-07")


def _populated_manager():
    manager = create_registry_manager()
    populate_registries(
        manager,
        topics=[{"id": "t-1", "object_type": "topic"}],
        concepts=[{"id": "c-1", "object_type": "concept", "name": "Inertia"}],
        glossary=[{"id": "g-1", "object_type": "glossary_entry"}],
        definitions=[{"id": "obj-441", "object_type": "definition"}],
        figures=[
            {"id": "obj-442", "object_type": "figure"},
            # Chart/Graph/Map/Timeline subclass Figure (schemas/chapter_
            # schema.py) and may physically live in the figures registry
            # while carrying their own true object_type -- see
            # registry_snapshot.py's own module docstring.
            {"id": "obj-443", "object_type": "chart"},
        ],
        equations=[{"id": "obj-444", "object_type": "equation"}],
    )
    return manager


class CompilerRegistrySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = _populated_manager()
        self.snapshot = CompilerRegistrySnapshot(registry_manager=self.manager, chapter_id=CHAPTER_ID)

    # -- object_exists ----------------------------------------------------

    def test_object_exists_true_for_a_content_object(self) -> None:
        self.assertTrue(self.snapshot.object_exists(CanonicalObjectId("obj-441")))

    def test_object_exists_true_for_a_figure_subtype_object(self) -> None:
        self.assertTrue(self.snapshot.object_exists(CanonicalObjectId("obj-443")))

    def test_object_exists_false_for_an_unknown_id(self) -> None:
        self.assertFalse(self.snapshot.object_exists(CanonicalObjectId("does-not-exist")))

    def test_object_exists_false_for_a_topic_id(self) -> None:
        """Topics are structural headings, not `content`-type sequence
        references -- see module docstring's "WHICH REGISTRIES COUNT AS
        'CONTENT'" section. A topic id must never resolve as a content
        object, or R2 would be checking the wrong universe."""
        self.assertFalse(self.snapshot.object_exists(CanonicalObjectId("t-1")))

    def test_object_exists_false_for_a_concept_id(self) -> None:
        self.assertFalse(self.snapshot.object_exists(CanonicalObjectId("c-1")))

    def test_object_exists_false_for_a_glossary_id(self) -> None:
        self.assertFalse(self.snapshot.object_exists(CanonicalObjectId("g-1")))

    # -- object_type_of -----------------------------------------------------

    def test_object_type_of_returns_the_items_own_object_type(self) -> None:
        self.assertEqual(
            self.snapshot.object_type_of(CanonicalObjectId("obj-441")),
            ObjectType("definition"),
        )

    def test_object_type_of_reads_the_items_own_field_not_the_registry_name(self) -> None:
        """`obj-443` physically lives in the `figures` registry but its
        own `object_type` is `"chart"` -- the adapter must trust the
        item's own field, never infer a type from which registry
        container the item happens to be inserted into."""
        self.assertEqual(
            self.snapshot.object_type_of(CanonicalObjectId("obj-443")),
            ObjectType("chart"),
        )

    def test_object_type_of_none_for_an_unknown_id(self) -> None:
        self.assertIsNone(self.snapshot.object_type_of(CanonicalObjectId("does-not-exist")))

    # -- objects_owned_by_chapter --------------------------------------------

    def test_objects_owned_by_chapter_excludes_topics_concepts_glossary(self) -> None:
        owned = self.snapshot.objects_owned_by_chapter(CHAPTER_ID)
        owned_values = {obj.value for obj in owned}
        self.assertNotIn("t-1", owned_values)
        self.assertNotIn("c-1", owned_values)
        self.assertNotIn("g-1", owned_values)

    def test_objects_owned_by_chapter_includes_every_content_object(self) -> None:
        owned = {obj.value for obj in self.snapshot.objects_owned_by_chapter(CHAPTER_ID)}
        self.assertEqual(owned, {"obj-441", "obj-442", "obj-443", "obj-444"})

    def test_objects_owned_by_chapter_empty_for_a_different_chapter_id(self) -> None:
        """A snapshot built for one chapter must never attribute its
        registries to a different chapter_id -- see class docstring
        ("intentionally empty ... constructed for")."""
        other = ChapterId("chap-08")
        self.assertEqual(self.snapshot.objects_owned_by_chapter(other), frozenset())

    def test_empty_manager_yields_empty_ownership(self) -> None:
        empty_manager = create_registry_manager()
        snapshot = CompilerRegistrySnapshot(registry_manager=empty_manager, chapter_id=CHAPTER_ID)
        self.assertEqual(snapshot.objects_owned_by_chapter(CHAPTER_ID), frozenset())

    def test_excluded_registry_names_matches_documented_set(self) -> None:
        self.assertEqual(EXCLUDED_REGISTRY_NAMES, frozenset({"topics", "concepts", "glossary"}))


if __name__ == "__main__":
    unittest.main()