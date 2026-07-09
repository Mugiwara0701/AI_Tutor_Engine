"""
tests/test_migration.py — unit tests for storage/migration.py (first-run
local json_out/ -> OneDrive migration).

Uses an in-memory FakeStorage that implements the small slice of
OneDriveStorage's public API migration.py actually calls (root_folder,
resolve_path, exists, upload_file, download_file, upload_json,
download_json) -- no real MSAL/Graph/network involved.
"""
import os
import json as json_module

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage import migration
from storage.exceptions import NotFoundError, MigrationError


class FakeStorage:
    """In-memory stand-in for storage.OneDriveStorage."""

    def __init__(self, root_folder="AI_TUTOR"):
        self.root_folder = root_folder
        self._files = {}  # path -> bytes

    def resolve_path(self, board, klass, subject, book=None):
        parts = [self.root_folder, board, f"Class_{klass}", subject]
        if book:
            parts.append(book)
        return "/".join(parts)

    def exists(self, path):
        return path.strip("/") in self._files

    def upload_file(self, data, path=None, **kw):
        self._files[path.strip("/")] = data
        return path

    def download_file(self, path=None, **kw):
        p = path.strip("/")
        if p not in self._files:
            raise NotFoundError(p)
        return self._files[p]

    def upload_json(self, obj, path=None, indent=2, **kw):
        payload = json_module.dumps(obj, indent=indent).encode("utf-8")
        return self.upload_file(payload, path=path)

    def download_json(self, path=None, **kw):
        return json_module.loads(self.download_file(path=path).decode("utf-8"))


def _write_local_json(root, klass_dir, subject, book, filename, content):
    d = os.path.join(root, klass_dir, subject, book)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, filename)
    with open(path, "w", encoding="utf-8") as f:
        json_module.dump(content, f)
    return path


# ---------------------------------------------------------------------------
# discover_local_files()
# ---------------------------------------------------------------------------

def test_discover_local_files_walks_class_subject_book_layout(tmp_path):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "_book_manifest.json", {"b": 2})
    _write_local_json(root, "Class_12", "Economics", "Macroeconomics", "01_introduction.json", {"c": 3})

    files = migration.discover_local_files(root)

    assert len(files) == 3
    by_name = {f.filename: f for f in files}
    assert by_name["01_solutions.json"].klass == "12"
    assert by_name["01_solutions.json"].subject == "Chemistry"
    assert by_name["01_solutions.json"].book == "Chemistry"


def test_discover_local_files_missing_root_returns_empty(tmp_path):
    assert migration.discover_local_files(str(tmp_path / "does_not_exist")) == []


def test_discover_local_files_skips_non_class_dirs_and_non_json(tmp_path):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    # A stray non-Class_ top-level dir and a stray non-.json file should be
    # skipped, not crash the whole walk.
    os.makedirs(os.path.join(root, "NotAClassDir", "X", "Y"), exist_ok=True)
    with open(os.path.join(root, "Class_12", "Chemistry", "Chemistry", "notes.txt"), "w") as f:
        f.write("not json")

    files = migration.discover_local_files(root)

    assert len(files) == 1
    assert files[0].filename == "01_solutions.json"


# ---------------------------------------------------------------------------
# migrate_local_data_to_onedrive() / ensure_migration_complete()
# ---------------------------------------------------------------------------

def test_migrate_uploads_and_verifies_every_file(tmp_path):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    _write_local_json(root, "Class_12", "Economics", "Macro", "01_intro.json", {"b": 2})
    storage = FakeStorage()

    stats = migration.migrate_local_data_to_onedrive(storage, root, board="CBSE")

    assert stats == {"found": 2, "migrated": 2, "already_present": 0}
    assert storage.exists("AI_TUTOR/CBSE/Class_12/Chemistry/Chemistry/json_out/01_solutions.json")
    assert storage.exists("AI_TUTOR/CBSE/Class_12/Economics/Macro/json_out/01_intro.json")


def test_migrate_is_idempotent_skips_already_present_identical_files(tmp_path):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    storage = FakeStorage()

    first = migration.migrate_local_data_to_onedrive(storage, root, board="CBSE")
    second = migration.migrate_local_data_to_onedrive(storage, root, board="CBSE")

    assert first == {"found": 1, "migrated": 1, "already_present": 0}
    assert second == {"found": 1, "migrated": 0, "already_present": 1}


def test_migrate_raises_migration_error_when_verification_mismatches(tmp_path, monkeypatch):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    storage = FakeStorage()

    # Simulate a corrupt/incomplete upload: upload_file "succeeds" but the
    # bytes it stores don't match what was requested.
    def _bad_upload(data, path=None, **kw):
        storage._files[path.strip("/")] = b"corrupted"
        return path

    monkeypatch.setattr(storage, "upload_file", _bad_upload)

    with pytest.raises(MigrationError):
        migration.migrate_local_data_to_onedrive(storage, root, board="CBSE")


def test_ensure_migration_complete_writes_marker_only_after_full_success(tmp_path):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    storage = FakeStorage()

    assert migration.is_migration_complete(storage, board="CBSE") is False

    migration.ensure_migration_complete(storage, local_root=root, board="CBSE")

    assert migration.is_migration_complete(storage, board="CBSE") is True
    marker = storage.download_json(path="AI_TUTOR/CBSE/_migration_state.json")
    assert marker["completed"] is True
    assert marker["found"] == 1
    assert marker["migrated"] == 1


def test_ensure_migration_complete_no_marker_written_on_failure(tmp_path, monkeypatch):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    storage = FakeStorage()

    def _bad_upload(data, path=None, **kw):
        storage._files[path.strip("/")] = b"corrupted"
        return path

    monkeypatch.setattr(storage, "upload_file", _bad_upload)

    with pytest.raises(MigrationError):
        migration.ensure_migration_complete(storage, local_root=root, board="CBSE")

    assert migration.is_migration_complete(storage, board="CBSE") is False


def test_ensure_migration_complete_is_a_noop_second_time(tmp_path):
    root = str(tmp_path / "json_out")
    _write_local_json(root, "Class_12", "Chemistry", "Chemistry", "01_solutions.json", {"a": 1})
    storage = FakeStorage()

    migration.ensure_migration_complete(storage, local_root=root, board="CBSE")
    # Delete the local file entirely -- if ensure_migration_complete()
    # tried to re-migrate, discover_local_files() would just find nothing
    # (harmless), but the point of this test is that it shouldn't even
    # try: is_migration_complete() should short-circuit it.
    calls = []
    original = migration.migrate_local_data_to_onedrive

    def _spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    import storage.migration as mod
    mod.migrate_local_data_to_onedrive = _spy
    try:
        migration.ensure_migration_complete(storage, local_root=root, board="CBSE")
    finally:
        mod.migrate_local_data_to_onedrive = original

    assert calls == []
