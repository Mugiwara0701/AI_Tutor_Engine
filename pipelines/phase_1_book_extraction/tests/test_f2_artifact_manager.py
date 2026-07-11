"""
tests/test_f2_artifact_manager.py — Phase F2: Artifact Manager tests.

Same two-layer split test_f1_compiler_runtime.py already uses:

  * UNIT tests for artifact_manager.build/manifest/persistence/discovery/
    state in isolation, using a FakeStorage (no real OneDrive/Graph call
    -- storage/exceptions.NotFoundError is raised/handled exactly like
    the real OneDriveStorage would).
  * INTEGRATION tests exercising CompilerRuntime.run()/resume() end to
    end, with book_orchestrator faked (mirroring test_f1_compiler_
    runtime.py's own _FakeBookOrchestrator) and modules.json_writer's
    storage singleton swapped for the same FakeStorage, proving Phase
    F2 is actually wired into CompilerRuntime._execute() without
    changing run()/resume()'s own return shape.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from artifact_manager import state as build_state  # noqa: E402
from artifact_manager.build import Build, create_build  # noqa: E402
from artifact_manager.exceptions import (  # noqa: E402
    ArtifactError,
    BuildError,
    ManifestError,
    PersistenceError,
)
from artifact_manager.manifest import (  # noqa: E402
    attach_artifact_locations,
    generate_build_manifest,
)
from artifact_manager import persistence, discovery  # noqa: E402
from runtime.context import ExecutionContext, RuntimeStatus  # noqa: E402
from runtime.runtime import CompilerRuntime  # noqa: E402
from runtime import state as runtime_state  # noqa: E402
from storage.exceptions import NotFoundError  # noqa: E402
from modules import json_writer  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class FakeStorage:
    """In-memory stand-in for OneDriveStorage exposing only the surface
    artifact_manager actually calls: upload_json/download_json/exists/
    list_directory. No Graph/MSAL/network involved."""

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

    def list_directory(self, path=None):
        prefix = path.rstrip("/") + "/"
        matched = False
        seen = set()
        out = []
        for p in self.files:
            if p.startswith(prefix):
                matched = True
                top = p[len(prefix):].split("/")[0]
                if top not in seen:
                    seen.add(top)
                    out.append({"name": top, "is_folder": True, "size": 0, "path": prefix + top})
        if not matched:
            raise NotFoundError(path)
        return out


@pytest.fixture(autouse=True)
def _reset_state():
    """Both runtime state and Phase F2's own current-build state are
    module-level and run-scoped -- reset before/after every test, same
    idiom test_f1_compiler_runtime.py's own _reset_runtime_state fixture
    already uses."""
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()
    yield
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()


@pytest.fixture
def fake_storage(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(json_writer, "_storage_singleton", storage)
    return storage


class _FakeBookOrchestrator:
    def __init__(self, books=None, raise_exc=None):
        self._books = books if books is not None else [
            {"found": 2, "written": 2, "failed": 0, "book_title": "Book One", "book_name": "Book One",
             "written_paths": ["json_out/Class_12/Chem/BookOne/01_ch.json",
                                "json_out/Class_12/Chem/BookOne/02_ch.json"],
             "book_manifest_path": "json_out/Class_12/Chem/BookOne/_book_manifest.json"},
        ]
        self._raise_exc = raise_exc

    def run(self, use_vlm, page_batch_size, force, pdf_input_folder=None,
            cancel_check=None, progress_callback=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        for book_stats in self._books:
            if progress_callback is not None:
                progress_callback(book_stats)
        return [dict(b) for b in self._books]


@pytest.fixture
def fake_book_orchestrator(monkeypatch):
    fake = _FakeBookOrchestrator()
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)
    return fake


def _make_build(all_stats=None, status=RuntimeStatus.COMPLETED, error=None) -> Build:
    context = ExecutionContext(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=None)
    return create_build(
        context=context, status=status,
        all_stats=all_stats if all_stats is not None else [
            {"found": 1, "written": 1, "failed": 0, "book_name": "A"},
        ],
        error=error,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# 1. Build object
# ---------------------------------------------------------------------------

def test_create_build_basic_shape():
    build = _make_build()
    assert build.build_id.startswith("build-")
    assert build.build_manifest is None
    assert build.execution_summary["chapters_written"] == 1
    assert build.execution_summary["status"] == RuntimeStatus.COMPLETED
    # References are None here since no compiler/knowledge_graph/etc.
    # chapter-scoped state was ever set in this process.
    assert build.compiler_ir_reference is None
    assert build.knowledge_graph_reference is None


def test_create_build_rejects_non_list_all_stats():
    context = ExecutionContext(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=None)
    with pytest.raises(BuildError):
        create_build(context=context, status=RuntimeStatus.COMPLETED, all_stats={"not": "a list"},
                      error=None, started_at=datetime.now(timezone.utc))


def test_build_is_immutable_with_manifest_returns_new_instance():
    build = _make_build()
    manifest = {"build_id": build.build_id, "fake": True}
    build2 = build.with_manifest(manifest)
    assert build.build_manifest is None       # original untouched
    assert build2.build_manifest == manifest
    assert build2.build_id == build.build_id


def test_build_reference_snapshot_reads_existing_compiler_state():
    """Reuse, don't recompute: if compiler/state.py already has a
    current registry manager set (as it would mid-pipeline.process_
    chapter()), Build reads it verbatim via RegistryManager.serialize()
    -- never a second serialization format."""
    import compiler.state as compiler_state
    from compiler.registry_manager import RegistryManager

    manager = RegistryManager()
    manager.create("concepts")
    compiler_state.set_current_registry_manager(manager)
    try:
        build = _make_build()
        assert build.compiler_ir_reference is not None
        assert build.compiler_ir_reference["source"] == "last_processed_chapter"
        assert "registries" in build.compiler_ir_reference["artifact"]
    finally:
        compiler_state.reset_registry_state()


# ---------------------------------------------------------------------------
# 2. Build Manifest
# ---------------------------------------------------------------------------

def test_generate_build_manifest_is_deterministic():
    build = _make_build()
    m1 = generate_build_manifest(build)
    m2 = generate_build_manifest(build)
    assert m1 == m2
    assert m1["manifest_fingerprint"] == m2["manifest_fingerprint"]
    assert m1["build_id"] == build.build_id
    assert m1["build_status"] == RuntimeStatus.COMPLETED


def test_generate_build_manifest_requires_execution_summary():
    build = _make_build()
    broken = Build(**{**build.to_dict(), "execution_summary": None})
    with pytest.raises(ManifestError):
        generate_build_manifest(broken)


def test_manifest_surfaces_chapter_failures_as_warnings():
    build = _make_build(all_stats=[{"found": 2, "written": 1, "failed": 1, "book_name": "A"}])
    manifest = generate_build_manifest(build)
    assert any("chapter(s) failed" in w for w in manifest["warnings"])


def test_manifest_surfaces_book_level_errors():
    build = _make_build(
        all_stats=[{"found": 0, "written": 0, "failed": 0, "book_name": "Bad Book", "error": "boom"}],
        status=RuntimeStatus.FAILED, error="boom",
    )
    manifest = generate_build_manifest(build)
    assert manifest["build_status"] == RuntimeStatus.FAILED
    assert any("boom" in e for e in manifest["errors"])
    assert any("Bad Book" in e for e in manifest["errors"])


def test_attach_artifact_locations_updates_fingerprint_and_never_mutates_input():
    build = _make_build()
    m1 = generate_build_manifest(build)
    m2 = attach_artifact_locations(m1, chapter_json_paths=["a.json"], book_manifest_paths=["_book_manifest.json"])
    assert m1["artifact_locations"]["chapter_json_paths"] == []   # original untouched
    assert m2["artifact_locations"]["chapter_json_paths"] == ["a.json"]
    assert m2["manifest_fingerprint"] != m1["manifest_fingerprint"]


# ---------------------------------------------------------------------------
# 3. Persistence / discovery
# ---------------------------------------------------------------------------

def test_persist_and_load_build_round_trip(fake_storage):
    build = _make_build()
    manifest = generate_build_manifest(build)
    build = build.with_manifest(manifest)

    paths = persistence.persist_build(fake_storage, build.to_dict(), manifest)
    assert paths["build_record_path"] == persistence.build_record_path(build.build_id)

    loaded = persistence.load_build(fake_storage, build.build_id)
    assert loaded["build_id"] == build.build_id
    loaded_manifest = persistence.load_manifest(fake_storage, build.build_id)
    assert loaded_manifest["build_id"] == build.build_id
    assert persistence.build_exists(fake_storage, build.build_id) is True


def test_load_build_raises_artifact_error_when_missing(fake_storage):
    with pytest.raises(ArtifactError):
        persistence.load_build(fake_storage, "build-does-not-exist")


def test_persist_build_requires_build_id(fake_storage):
    with pytest.raises(PersistenceError):
        persistence.persist_build(fake_storage, {"no": "build_id"}, {})


def test_discovery_lists_builds_and_history(fake_storage):
    assert discovery.list_builds(fake_storage) == []
    assert discovery.build_history(fake_storage) == []

    for _ in range(2):
        build = _make_build()
        manifest = generate_build_manifest(build)
        build = build.with_manifest(manifest)
        persistence.persist_build(fake_storage, build.to_dict(), manifest)

    ids = discovery.list_builds(fake_storage)
    assert len(ids) == 2
    history = discovery.build_history(fake_storage)
    assert len(history) == 2
    assert all("build_status" in h for h in history)


# ---------------------------------------------------------------------------
# 4. artifact_manager.state
# ---------------------------------------------------------------------------

def test_current_build_state_lifecycle():
    assert not build_state.has_current_build()
    assert build_state.get_current_build() is None

    build = _make_build()
    build_state.set_current_build(build)
    assert build_state.has_current_build()
    assert build_state.get_current_build() is build

    build_state.reset_current_build()
    assert not build_state.has_current_build()


# ---------------------------------------------------------------------------
# 5. CompilerRuntime integration (F1 -> F2 wiring)
# ---------------------------------------------------------------------------

def test_run_records_a_build_without_changing_return_shape(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()

    # Public API preserved: run() still returns the raw per-book stats list.
    assert result == fake_book_orchestrator._books
    assert isinstance(result, list)

    assert build_state.has_current_build()
    build = build_state.get_current_build()
    assert build.execution_summary["status"] == RuntimeStatus.COMPLETED
    assert build.execution_summary["chapters_written"] == 2
    assert build.build_manifest is not None

    locations = build.build_manifest["artifact_locations"]
    assert locations["chapter_json_paths"] == [
        "json_out/Class_12/Chem/BookOne/01_ch.json",
        "json_out/Class_12/Chem/BookOne/02_ch.json",
    ]
    assert locations["book_manifest_paths"] == ["json_out/Class_12/Chem/BookOne/_book_manifest.json"]
    assert locations["build_record_path"] is not None

    # Actually persisted via the reused storage instance.
    assert persistence.build_exists(fake_storage, build.build_id)


def test_failed_run_still_records_a_build_and_still_raises(fake_storage, monkeypatch):
    boom = RuntimeError("storage migration failed")
    fake = _FakeBookOrchestrator(raise_exc=boom)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)

    rt = CompilerRuntime(use_vlm=False)
    with pytest.raises(RuntimeError):
        rt.run()

    assert runtime_state.get_current_status() == RuntimeStatus.FAILED
    assert build_state.has_current_build()
    build = build_state.get_current_build()
    assert build.execution_summary["status"] == RuntimeStatus.FAILED
    assert build.execution_summary["error"] == "storage migration failed"
    assert build.execution_summary["books_completed"] == 0


def test_new_run_resets_previous_build(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False)
    rt.run()
    first_build_id = build_state.get_current_build().build_id

    rt2 = CompilerRuntime(use_vlm=False)
    rt2.run()
    second_build_id = build_state.get_current_build().build_id

    assert first_build_id != second_build_id
    # Both remain independently discoverable/persisted.
    assert persistence.build_exists(fake_storage, first_build_id)
    assert persistence.build_exists(fake_storage, second_build_id)


def test_artifact_manager_failure_never_masks_a_successful_run(fake_book_orchestrator, monkeypatch):
    """If Phase F2's own bookkeeping breaks (e.g. persistence raises),
    run() itself must still succeed and return the real stats -- Phase
    F2 must never turn a good run into a failure."""

    def broken_get_storage():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(json_writer, "get_storage", broken_get_storage)

    rt = CompilerRuntime(use_vlm=False)
    result = rt.run()

    assert result == fake_book_orchestrator._books
    assert rt.status()["status"] == RuntimeStatus.COMPLETED
    # Build/manifest were constructed but never persisted / never recorded,
    # since get_storage() itself raised inside _record_build()'s try/except.
    assert not build_state.has_current_build()
