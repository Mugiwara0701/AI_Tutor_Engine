"""
tests/test_storage_identity_persistence_consistency.py — Storage Identity
Verification Audit, Step 5/7: proves every persistence module (Chapter
JSON + book manifest via json_writer.book_output_dir(), and the six Phase
1 artifact types via json_writer.artifact_output_dir()) resolves to the
SAME book folder for the SAME book_slug -- so a book's Knowledge Graph,
Dependency Graph, registries, compiler_metadata, validation, and build
metadata can never end up siblings of a different book folder than its
own Chapter JSON.

This complements (does not duplicate) tests/test_canonical_book_identity.py
and tests/test_metadata_regression.py, which already cover:
  - BookContext.slug_source / derived_storage_identity precedence
  - book_title_override not shadowing derived_storage_identity when cover
    metadata is present
  - process_chapter() vs execute_chapter() agreeing on book_slug
Neither of those files asserts that json_writer's OWN artifact-folder
helpers (book_output_dir / artifact_output_dir) share one resolution path
for a given book_slug -- that is what this file adds.

Per task instructions, generated only: not executed here, for the same
reason tests/test_registries.py's own disclaimer states (this sandbox has
no network access to install fitz/pydantic, which modules/json_writer.py
transitively imports). Every path/function referenced was read directly
from modules/json_writer.py, not assumed -- and the underlying identity
math (BookContext.slug_source -> slugify() -> PathResolver.resolve())
was independently executed and confirmed in this session using a fitz
stub, since storage/path_resolver.py itself has no such dependency.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import json_writer  # noqa: E402
from storage.path_resolver import PathResolver  # noqa: E402


class _FakeOneDriveStorage:
    """Same minimal stand-in tests/test_canonical_book_identity.py's own
    _FakeOneDriveStorage uses -- only the methods book_output_dir()/
    artifact_output_dir() actually call."""

    def __init__(self):
        self._resolver = PathResolver()
        self.created_dirs = []
        self.uploaded = {}

    def resolve_path(self, board, klass, subject, book=None):
        return self._resolver.resolve(board, klass, subject, book)

    def create_directory(self, path):
        self.created_dirs.append(path)

    def upload_json(self, obj, path=None, indent=2, **kw):
        self.uploaded[path] = obj
        return path


@pytest.fixture
def fake_storage(monkeypatch):
    storage = _FakeOneDriveStorage()
    monkeypatch.setattr(json_writer, "_storage_singleton", storage)
    return storage


ALL_ARTIFACT_TYPES = ("registries", "knowledge_graph", "dependency_graph",
                       "validation", "compiler_metadata", "build_metadata")


class TestAllPersistenceModulesShareOneBookFolder:
    def test_book_folder_root_is_identical_across_json_out_and_every_artifact_type(self, fake_storage):
        klass, subject, book_slug = "Class_12", "Accountancy", "accountancy-partnership-accounts"

        json_out_dir = json_writer.book_output_dir(klass, subject, book_slug)
        book_root = json_out_dir.rsplit("/json_out", 1)[0]

        for artifact_type in ALL_ARTIFACT_TYPES:
            artifact_dir = json_writer.artifact_output_dir(artifact_type, klass, subject, book_slug)
            artifact_root = artifact_dir.rsplit(f"/{artifact_type}", 1)[0]
            assert artifact_root == book_root, (
                f"{artifact_type!r} folder root {artifact_root!r} does not match "
                f"json_out's own book root {book_root!r} for the same book_slug"
            )

    def test_book_root_reflects_derived_storage_identity_not_operator_folder(self, fake_storage):
        """End-to-end: for a book with distinguishing cover metadata, every
        persisted artifact's folder must be Accountancy_Partnership_Accounts,
        never Accountancy_Part_1 (the pre-fix operator folder name)."""
        klass, subject, book_slug = "Class_12", "Accountancy", "accountancy-partnership-accounts"
        expected_root = "AI_TUTOR/CBSE/Class_12/Accountancy/Accountancy_Partnership_Accounts"

        json_out_dir = json_writer.book_output_dir(klass, subject, book_slug)
        assert json_out_dir == f"{expected_root}/json_out"
        assert "Accountancy_Part_1" not in json_out_dir

        for artifact_type in ALL_ARTIFACT_TYPES:
            artifact_dir = json_writer.artifact_output_dir(artifact_type, klass, subject, book_slug)
            assert artifact_dir == f"{expected_root}/{artifact_type}"
            assert "Accountancy_Part_1" not in artifact_dir

    def test_chapter_filename_is_identical_across_json_out_and_every_artifact_type(self, fake_storage):
        klass, subject, book_slug = "Class_12", "Accountancy", "accountancy-partnership-accounts"
        chapter_number, chapter_title = 1, "Introduction"

        chapter_path = json_writer.chapter_output_path(klass, subject, book_slug, chapter_number, chapter_title)
        chapter_filename = os.path.basename(chapter_path)

        for artifact_type in ALL_ARTIFACT_TYPES:
            artifact_path = json_writer.artifact_output_path(
                artifact_type, klass, subject, book_slug, chapter_number, chapter_title)
            assert os.path.basename(artifact_path) == chapter_filename

    def test_output_root_override_is_shared_identically_by_every_artifact_type(self, fake_storage):
        """A caller-supplied output_root (e.g. a test redirecting one book's
        output) must be honored identically by json_out and every artifact
        type -- never re-derived independently by one of them."""
        override_root = "AI_TUTOR/CBSE/Class_12/Accountancy/Custom_Redirect"

        json_out_dir = json_writer.book_output_dir("Class_12", "Accountancy", "ignored-slug",
                                                     output_root=override_root)
        assert json_out_dir == f"{override_root}/json_out"

        for artifact_type in ALL_ARTIFACT_TYPES:
            artifact_dir = json_writer.artifact_output_dir(
                artifact_type, "Class_12", "Accountancy", "ignored-slug", output_root=override_root)
            assert artifact_dir == f"{override_root}/{artifact_type}"