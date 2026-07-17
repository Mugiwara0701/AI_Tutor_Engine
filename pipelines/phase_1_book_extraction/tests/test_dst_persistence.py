"""tests/test_dst_persistence.py — Milestone 6: Serialization &
Persistence, `document_structure_tree/persistence.py`.

An audit of the original M6/M7 roadmap found `document_structure_tree`
was never added to `modules.json_writer._ARTIFACT_SUBFOLDERS`, so
`artifact_output_dir("document_structure_tree", ...)` -- and therefore
every call `document_structure_tree/persistence.py` makes to it --
raised `ValueError` before ever reaching storage. That registration gap
is fixed in `modules/json_writer.py`; this file is the persistence
regression coverage the audit asked for: persist -> load -> equality,
using the exact same in-memory `FakeStorage` stand-in for
`storage.OneDriveStorage` that `tests/test_f2_artifact_manager.py`
already uses for every other artifact type (no new test double
introduced).
"""
from __future__ import annotations

import unittest

from document_structure_tree import (
    DocumentStructureTree,
    generate_artifact,
)
from document_structure_tree.artifact import to_canonical_json
from document_structure_tree.persistence import (
    ARTIFACT_TYPE,
    DocumentStructureTreeNotFoundError,
    document_structure_tree_exists,
    document_structure_tree_record_path,
    load_document_structure_tree,
    persist_document_structure_tree,
)
from modules import json_writer
from storage.exceptions import NotFoundError

from .fixtures import (
    BUILD_TIMESTAMP,
    CHAPTER_ID,
    COMPILER_VERSION,
    REGISTRY_REF,
    SCHEMA_VERSION,
    build_small_clean_tree,
    clean_registry,
)


class FakeStorage:
    """In-memory stand-in for OneDriveStorage exposing only the surface
    document_structure_tree/persistence.py actually calls:
    upload_json/download_json/exists. Identical in shape to
    tests/test_f2_artifact_manager.py's own FakeStorage -- kept as a
    separate copy here rather than imported, since that class lives in
    a test module, not a shared fixtures module."""

    def __init__(self):
        self.files = {}

    def upload_json(self, obj, path=None, indent=2):
        self.files[path] = obj
        return path

    def download_json(self, path=None):
        if path not in self.files:
            raise NotFoundError(path)
        return self.files[path]

    def exists(self, path=None):
        return path in self.files

    def resolve_path(self, board, klass, subject, book_slug):
        # Same shape storage.PathResolver produces -- only the book-dir
        # resolution modules.json_writer._resolve_book_dir() needs;
        # persist/load themselves only ever call upload_json/
        # download_json/exists above.
        return f"AI_TUTOR/{board}/{klass}/{subject}/{book_slug}"


def _build_artifact() -> DocumentStructureTree:
    built = build_small_clean_tree()
    registry = clean_registry()
    return generate_artifact(
        tree=built.tree,
        chapter_id=CHAPTER_ID,
        schema_version=SCHEMA_VERSION,
        compiler_version=COMPILER_VERSION,
        canonical_registry_snapshot_ref=REGISTRY_REF,
        build_timestamp=BUILD_TIMESTAMP,
        registry=registry,
    )


def _assert_dst_equal(test: unittest.TestCase, a: DocumentStructureTree, b: DocumentStructureTree) -> None:
    """Compares two DocumentStructureTree instances the way this
    artifact is actually meant to be compared: `tree`'s own array
    order carries no meaning (schema §5.2), but the dataclass's
    generated `__eq__` is order-sensitive, and to_canonical_json()
    deliberately re-sorts `tree` into canonical order (this module's
    persist_document_structure_tree() writes exactly that shape) -- so
    a fresh in-memory artifact and the same artifact reloaded from
    storage can be tuple-unequal on `tree` while representing an
    identical Document Structure Tree. Canonical-JSON equality is the
    right notion of equality here; it's also, incidentally, an
    equality check on every field at once, not just `tree`."""
    test.assertEqual(to_canonical_json(a), to_canonical_json(b))


class PersistDocumentStructureTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = FakeStorage()
        self.artifact = _build_artifact()
        self.route = dict(
            klass="Class_12", subject="Chemistry", book_slug="ncert-chemistry-part-1",
            chapter_number=7, chapter_title="Solutions",
        )
        # document_structure_tree_record_path()/artifact_output_path()
        # resolve their book-dir via modules.json_writer's own storage
        # singleton (independent of the `storage` argument
        # persist/load themselves take for upload_json/download_json/
        # exists) -- hand it the same FakeStorage so no real,
        # network/msal-backed OneDriveStorage ever gets constructed.
        # See modules/json_writer.py's set_storage() docstring: this is
        # exactly the intended way to supply an already-usable client.
        self._previous_storage_singleton = json_writer._storage_singleton
        json_writer.set_storage(self.storage)

    def tearDown(self) -> None:
        json_writer._storage_singleton = self._previous_storage_singleton

    def test_persist_writes_under_the_document_structure_tree_artifact_type(self) -> None:
        # Regression guard for the exact bug the audit found: this call
        # must not raise, and the path it writes to must live under
        # this artifact type's own registered subfolder.
        path = persist_document_structure_tree(
            self.storage, **self.route, document_structure_tree=self.artifact,
        )
        self.assertIn(ARTIFACT_TYPE, path)
        self.assertEqual(
            path, document_structure_tree_record_path(**self.route),
        )
        self.assertIn(path, self.storage.files)

    def test_persist_then_load_round_trips_to_an_equal_artifact(self) -> None:
        persist_document_structure_tree(
            self.storage, **self.route, document_structure_tree=self.artifact,
        )
        loaded = load_document_structure_tree(self.storage, **self.route)
        _assert_dst_equal(self, loaded, self.artifact)

    def test_persist_then_load_round_trips_a_tree_with_a_derived_summary(self) -> None:
        # generate_artifact() populates derived_summary by default (schema
        # §2.2's optional layer); confirms it survives persist -> load
        # rather than only the required artifact_metadata/tree/etc. layers.
        self.assertIsNotNone(self.artifact.derived_summary)
        persist_document_structure_tree(
            self.storage, **self.route, document_structure_tree=self.artifact,
        )
        loaded = load_document_structure_tree(self.storage, **self.route)
        self.assertIsNotNone(loaded.derived_summary)
        _assert_dst_equal(self, loaded, self.artifact)

    def test_exists_is_false_before_persisting_and_true_after(self) -> None:
        self.assertFalse(document_structure_tree_exists(self.storage, **self.route))
        persist_document_structure_tree(
            self.storage, **self.route, document_structure_tree=self.artifact,
        )
        self.assertTrue(document_structure_tree_exists(self.storage, **self.route))

    def test_load_before_persisting_raises_not_found(self) -> None:
        with self.assertRaises(DocumentStructureTreeNotFoundError):
            load_document_structure_tree(self.storage, **self.route)

    def test_persisted_record_is_the_same_shape_to_canonical_json_produces(self) -> None:
        persist_document_structure_tree(
            self.storage, **self.route, document_structure_tree=self.artifact,
        )
        path = document_structure_tree_record_path(**self.route)
        self.assertEqual(self.storage.files[path], to_canonical_json(self.artifact))

    def test_different_chapters_persist_to_different_paths_and_dont_collide(self) -> None:
        other_route = dict(self.route, chapter_number=8, chapter_title="Electrochemistry")
        persist_document_structure_tree(
            self.storage, **self.route, document_structure_tree=self.artifact,
        )
        persist_document_structure_tree(
            self.storage, **other_route, document_structure_tree=self.artifact,
        )
        self.assertNotEqual(
            document_structure_tree_record_path(**self.route),
            document_structure_tree_record_path(**other_route),
        )
        _assert_dst_equal(self, load_document_structure_tree(self.storage, **self.route), self.artifact)
        _assert_dst_equal(self, load_document_structure_tree(self.storage, **other_route), self.artifact)


if __name__ == "__main__":
    unittest.main()
