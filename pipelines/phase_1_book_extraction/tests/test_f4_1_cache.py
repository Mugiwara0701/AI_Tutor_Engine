"""
tests/test_f4_1_cache.py — Phase F4.1: Cache Persistence & Validation
tests.

Same layered split test_f2_artifact_manager.py/test_f3_build_executor.py
already use, one package over:

  * UNIT tests for cache.snapshot_store/index/validation/report/state
    in isolation, using a FakeStorage (no real OneDrive/Graph call --
    storage/exceptions.NotFoundError is raised/handled exactly like the
    real OneDriveStorage would).
  * INTEGRATION tests exercising CompilerRuntime.run()/resume() end to
    end, with book_orchestrator faked (mirroring test_f2/test_f3's own
    _FakeBookOrchestrator) and modules.json_writer's storage singleton
    swapped for the same FakeStorage, proving Phase F4.1 is actually
    wired into CompilerRuntime._execute() (via _record_cache()) without
    changing run()/resume()'s own return shape, and without changing
    Phase F2's/F3's own recorded state.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from artifact_manager import state as build_state  # noqa: E402
from artifact_manager.build import create_build  # noqa: E402
from artifact_manager.manifest import generate_build_manifest, attach_artifact_locations  # noqa: E402
from build_executor import state as execution_state  # noqa: E402
from build_executor.plan import generate_execution_plan  # noqa: E402
from cache import state as cache_state  # noqa: E402
from cache.exceptions import CacheReadError, CacheValidationError, CacheWriteError  # noqa: E402
from cache.index import cache_history, list_cache_entries  # noqa: E402
from cache.report import (  # noqa: E402
    STATUS_CONSISTENT,
    STATUS_DIVERGENT,
    STATUS_NO_BASELINE,
)
from cache.snapshot_store import (  # noqa: E402
    build_cache_entry,
    cache_root,
    load_fingerprint_snapshot,
    load_previous_cache_entry,
    load_previous_fingerprint_snapshot,
    persist_fingerprint_snapshot,
    snapshot_exists,
    snapshot_record_path,
)
from cache.validation import validate_execution_against_cache  # noqa: E402
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
    cache/artifact_manager/build_executor actually call:
    upload_json/download_json/exists/list_directory. No Graph/MSAL/
    network involved."""

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
    """Every Phase F module-level state slot this suite touches is
    run-scoped -- reset before/after every test, same idiom test_f2/
    test_f3's own _reset_state fixture already uses."""
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()
    execution_state.reset_current_execution_report()
    cache_state.reset_current_cache_state()
    yield
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()
    execution_state.reset_current_execution_report()
    cache_state.reset_current_cache_state()


@pytest.fixture
def fake_storage(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(json_writer, "_storage_singleton", storage)
    return storage


def _make_manifested_build(build_id_started_at, fingerprints=None, all_stats=None):
    """Builds a fully-manifested Build (Phase F2 shape) for a given
    started_at timestamp -- build ids sort chronologically by
    construction, so distinct started_at values give us distinct,
    orderable build_ids for cross-build ordering tests."""
    context = ExecutionContext(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=None)
    build = create_build(
        context=context, status=RuntimeStatus.COMPLETED,
        all_stats=all_stats if all_stats is not None else [
            {"found": 1, "written": 1, "failed": 0, "book_name": "A"},
        ],
        error=None,
        started_at=build_id_started_at,
        finished_at=build_id_started_at,
    )
    manifest = generate_build_manifest(build)
    manifest = attach_artifact_locations(manifest, chapter_json_paths=[], book_manifest_paths=[])
    if fingerprints is not None:
        manifest = dict(manifest)
        manifest["fingerprints"] = dict(fingerprints)
    return build.with_manifest(manifest)


# ---------------------------------------------------------------------------
# 1. snapshot persistence
# ---------------------------------------------------------------------------

def test_build_cache_entry_reads_manifest_fingerprints_verbatim():
    build = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "abc", "graph_fingerprint": "def", "configuration_fingerprint": "ghi"},
    )
    entry = build_cache_entry(build)
    assert entry["build_id"] == build.build_id
    assert entry["fingerprint_snapshot"] == {
        "compiler_fingerprint": "abc", "graph_fingerprint": "def", "configuration_fingerprint": "ghi",
    }
    assert entry["cache_entry_version"] == "F4.1"
    assert entry["build_status"] == manifest_status(build)


def manifest_status(build):
    return build.build_manifest["build_status"]


def test_build_cache_entry_requires_manifested_build():
    context = ExecutionContext(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=None)
    build = create_build(
        context=context, status=RuntimeStatus.COMPLETED,
        all_stats=[{"found": 1, "written": 1, "failed": 0, "book_name": "A"}],
        error=None, started_at=datetime.now(timezone.utc),
    )
    with pytest.raises(CacheWriteError):
        build_cache_entry(build)  # no manifest attached yet


def test_persist_fingerprint_snapshot_writes_to_expected_path(fake_storage):
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    entry = build_cache_entry(build)
    result = persist_fingerprint_snapshot(fake_storage, entry)
    assert result["snapshot_path"] == snapshot_record_path(build.build_id)
    assert fake_storage.files[snapshot_record_path(build.build_id)] == entry


def test_persist_fingerprint_snapshot_requires_build_id(fake_storage):
    with pytest.raises(CacheWriteError):
        persist_fingerprint_snapshot(fake_storage, {"fingerprint_snapshot": {}})


def test_snapshot_record_path_layout_is_sibling_to_builds_root():
    path = snapshot_record_path("build-20260101T000000000000Z-abc123456789")
    assert path == f"{cache_root()}/build-20260101T000000000000Z-abc123456789/fingerprint_snapshot.json"
    assert cache_root() == "_runtime_cache"


# ---------------------------------------------------------------------------
# 2. snapshot loading
# ---------------------------------------------------------------------------

def test_load_fingerprint_snapshot_round_trip(fake_storage):
    build = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "abc", "graph_fingerprint": None, "configuration_fingerprint": None},
    )
    entry = build_cache_entry(build)
    persist_fingerprint_snapshot(fake_storage, entry)

    loaded = load_fingerprint_snapshot(fake_storage, build.build_id)
    assert loaded == entry


def test_load_fingerprint_snapshot_raises_when_missing(fake_storage):
    with pytest.raises(CacheReadError) as exc_info:
        load_fingerprint_snapshot(fake_storage, "build-does-not-exist")
    assert exc_info.value.build_id == "build-does-not-exist"


def test_snapshot_exists_true_and_false(fake_storage):
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert snapshot_exists(fake_storage, build.build_id) is False
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(build))
    assert snapshot_exists(fake_storage, build.build_id) is True


# ---------------------------------------------------------------------------
# 3. cache index
# ---------------------------------------------------------------------------

def test_list_cache_entries_empty_when_nothing_persisted(fake_storage):
    assert list_cache_entries(fake_storage) == []


def test_list_cache_entries_lists_every_persisted_build_sorted(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(b1))
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(b2))

    entries = list_cache_entries(fake_storage)
    assert set(entries) == {b1.build_id, b2.build_id}
    assert entries == sorted(entries)  # chronological by construction


# ---------------------------------------------------------------------------
# 4. cache history
# ---------------------------------------------------------------------------

def test_cache_history_returns_every_entry_in_order(fake_storage):
    b1 = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "v1", "graph_fingerprint": None, "configuration_fingerprint": None},
    )
    b2 = _make_manifested_build(
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "v2", "graph_fingerprint": None, "configuration_fingerprint": None},
    )
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(b1))
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(b2))

    history = cache_history(fake_storage)
    assert [h["build_id"] for h in history] == [b1.build_id, b2.build_id]
    assert history[0]["fingerprint_snapshot"]["compiler_fingerprint"] == "v1"
    assert history[1]["fingerprint_snapshot"]["compiler_fingerprint"] == "v2"


def test_cache_history_skips_unloadable_entry_without_failing(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(b1))
    # Simulate a partially-written cache record: the folder is listed
    # (list_directory sees the "directory" prefix) but the record
    # itself is corrupt/missing at read time.
    bad_build_id = "build-20260101T999999000000Z-deadbeefdead"
    fake_storage.files[f"{cache_root()}/{bad_build_id}/_marker"] = {}

    history = cache_history(fake_storage)
    assert [h["build_id"] for h in history] == [b1.build_id]


# ---------------------------------------------------------------------------
# 5. cache validation
# ---------------------------------------------------------------------------

def _plan(rebuilt_count, reused_count=0):
    return {"summary": {"rebuilt_count": rebuilt_count, "reused_count": reused_count,
                         "total_considered": rebuilt_count + reused_count,
                         "requires_execution": bool(rebuilt_count),
                         "is_full_reuse": bool(reused_count) and not rebuilt_count}}


def test_validate_no_previous_snapshot_is_no_baseline():
    report = validate_execution_against_cache(
        _plan(rebuilt_count=1), {"compiler_fingerprint": "a"}, None, build_id="build-x",
    )
    assert report["overall_status"] == STATUS_NO_BASELINE
    assert report["comparison_basis"] == "no_previous_snapshot"
    assert report["fingerprints_changed"] is None
    assert report["divergences"] == []


def test_validate_consistent_when_fingerprints_changed_and_chapters_rebuilt():
    report = validate_execution_against_cache(
        _plan(rebuilt_count=2), {"compiler_fingerprint": "b"}, {"compiler_fingerprint": "a"},
        build_id="build-y", previous_build_id="build-x",
    )
    assert report["overall_status"] == STATUS_CONSISTENT
    assert report["fingerprints_changed"] is True
    assert report["divergences"] == []


def test_validate_consistent_when_fingerprints_unchanged_and_nothing_rebuilt():
    same = {"compiler_fingerprint": "a", "graph_fingerprint": "b", "configuration_fingerprint": "c"}
    report = validate_execution_against_cache(
        _plan(rebuilt_count=0, reused_count=3), dict(same), dict(same),
        build_id="build-y", previous_build_id="build-x",
    )
    assert report["overall_status"] == STATUS_CONSISTENT
    assert report["fingerprints_changed"] is False


def test_validate_divergent_when_fingerprints_changed_but_nothing_rebuilt():
    report = validate_execution_against_cache(
        _plan(rebuilt_count=0, reused_count=1), {"compiler_fingerprint": "b"}, {"compiler_fingerprint": "a"},
        build_id="build-y", previous_build_id="build-x",
    )
    assert report["overall_status"] == STATUS_DIVERGENT
    assert report["fingerprints_changed"] is True
    assert len(report["divergences"]) == 1
    assert "reused every chapter" in report["divergences"][0]


def test_validate_divergent_when_fingerprints_unchanged_but_something_rebuilt():
    same = {"compiler_fingerprint": "a"}
    report = validate_execution_against_cache(
        _plan(rebuilt_count=1), dict(same), dict(same), build_id="build-y", previous_build_id="build-x",
    )
    assert report["overall_status"] == STATUS_DIVERGENT
    assert report["fingerprints_changed"] is False
    assert "rebuilt 1 chapter" in report["divergences"][0]


def test_validate_requires_execution_plan_summary():
    with pytest.raises(CacheValidationError):
        validate_execution_against_cache({}, {}, None, build_id="build-y")


def test_validate_never_mutates_its_inputs():
    plan = _plan(rebuilt_count=1)
    plan_copy = {"summary": dict(plan["summary"])}
    current = {"compiler_fingerprint": "a"}
    previous = {"compiler_fingerprint": "a"}
    current_copy, previous_copy = dict(current), dict(previous)

    validate_execution_against_cache(plan, current, previous, build_id="build-y", previous_build_id="build-x")

    assert plan == plan_copy
    assert current == current_copy
    assert previous == previous_copy


# ---------------------------------------------------------------------------
# 6. missing previous snapshot
# ---------------------------------------------------------------------------

def test_load_previous_cache_entry_returns_none_when_nothing_persisted(fake_storage):
    assert load_previous_cache_entry(fake_storage) is None
    assert load_previous_fingerprint_snapshot(fake_storage) is None


def test_load_previous_cache_entry_returns_none_before_the_first_build(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(b1))

    result = load_previous_cache_entry(fake_storage, before_build_id=b1.build_id)
    assert result is None


def test_load_previous_cache_entry_finds_the_most_recent_strictly_before(fake_storage):
    b1 = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "v1", "graph_fingerprint": None, "configuration_fingerprint": None},
    )
    b2 = _make_manifested_build(
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "v2", "graph_fingerprint": None, "configuration_fingerprint": None},
    )
    b3 = _make_manifested_build(
        datetime(2026, 1, 3, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "v3", "graph_fingerprint": None, "configuration_fingerprint": None},
    )
    for b in (b1, b2, b3):
        persist_fingerprint_snapshot(fake_storage, build_cache_entry(b))

    result = load_previous_cache_entry(fake_storage, before_build_id=b3.build_id)
    assert result["build_id"] == b2.build_id
    snapshot = load_previous_fingerprint_snapshot(fake_storage, before_build_id=b3.build_id)
    assert snapshot["compiler_fingerprint"] == "v2"


def test_load_previous_cache_entry_unreadable_record_treated_as_none(fake_storage, monkeypatch):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(b1))
    # Corrupt the persisted record so download_json() raises something
    # other than a clean, expected shape -- simulate via monkeypatching
    # load_fingerprint_snapshot to always raise CacheReadError.
    import cache.snapshot_store as snapshot_store_mod
    monkeypatch.setattr(
        snapshot_store_mod, "load_fingerprint_snapshot",
        lambda storage, build_id: (_ for _ in ()).throw(CacheReadError(build_id, "corrupt")),
    )
    assert load_previous_cache_entry(fake_storage) is None


# ---------------------------------------------------------------------------
# 7. deterministic behavior
# ---------------------------------------------------------------------------

def test_build_cache_entry_is_deterministic_for_same_build():
    build = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "a", "graph_fingerprint": "b", "configuration_fingerprint": "c"},
    )
    e1 = build_cache_entry(build)
    e2 = build_cache_entry(build)
    assert e1 == e2


def test_validate_execution_against_cache_is_deterministic():
    plan = _plan(rebuilt_count=1)
    current = {"compiler_fingerprint": "a"}
    previous = {"compiler_fingerprint": "b"}
    r1 = validate_execution_against_cache(
        plan, current, previous, build_id="build-y", previous_build_id="build-x",
        generated_at="2026-01-01T00:00:00+00:00",
    )
    r2 = validate_execution_against_cache(
        plan, current, previous, build_id="build-y", previous_build_id="build-x",
        generated_at="2026-01-01T00:00:00+00:00",
    )
    assert r1 == r2


# ---------------------------------------------------------------------------
# 8. read-only guarantees
# ---------------------------------------------------------------------------

def test_persist_fingerprint_snapshot_never_mutates_cache_entry(fake_storage):
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    entry = build_cache_entry(build)
    entry_copy = dict(entry)
    persist_fingerprint_snapshot(fake_storage, entry)
    assert entry == entry_copy


def test_build_cache_entry_never_mutates_build_manifest():
    build = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "a"},
    )
    manifest_before = dict(build.build_manifest)
    build_cache_entry(build)
    assert build.build_manifest == manifest_before


def test_cache_never_writes_into_runtime_builds_root(fake_storage):
    """Phase F4.1 must never write into Phase F2's own _runtime_builds/
    root -- separate, sibling roots only."""
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    persist_fingerprint_snapshot(fake_storage, build_cache_entry(build))
    assert all(not p.startswith("_runtime_builds/") for p in fake_storage.files)
    assert all(p.startswith(f"{cache_root()}/") for p in fake_storage.files)


# ---------------------------------------------------------------------------
# 9. runtime integration
# ---------------------------------------------------------------------------

class _FakeBookOrchestrator:
    def __init__(self, books=None, raise_exc=None, rebuilt_count=1, reused_count=1):
        self._books = books if books is not None else [
            {
                "found": 2, "written": 1, "failed": 0, "book_title": "Book One", "book_name": "Book One",
                "written_paths": ["json_out/Class_10/Science/book-one/02_ch.json"],
                "book_manifest_path": "json_out/Class_10/Science/book-one/_book_manifest.json",
                "execution_plan": generate_execution_plan(
                    (
                        [{"chapter_key": "json_out/.../01_ch.json", "decision": "reuse", "reason": "already exists"}]
                        * reused_count
                    ) + (
                        [{"chapter_key": "json_out/.../02_ch.json", "decision": "rebuild", "reason": "new"}]
                        * rebuilt_count
                    ),
                    namespace="Book One",
                ),
            },
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


def test_run_persists_a_fingerprint_snapshot_and_records_cache_entry(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()

    assert cache_state.has_current_cache_entry() is True
    entry = cache_state.get_current_cache_entry()
    build = build_state.get_current_build()
    assert entry["build_id"] == build.build_id
    assert snapshot_exists(fake_storage, build.build_id) is True


def test_run_records_a_no_baseline_cache_validation_report_on_first_run(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()

    assert cache_state.has_current_cache_validation_report() is True
    report = cache_state.get_current_cache_validation_report()
    assert report["overall_status"] == STATUS_NO_BASELINE
    assert report["comparison_basis"] == "no_previous_snapshot"


def test_second_run_compares_against_first_runs_cached_snapshot(fake_storage, monkeypatch):
    fake1 = _FakeBookOrchestrator(rebuilt_count=1, reused_count=0)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake1)
    rt1 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt1.run()
    first_build_id = build_state.get_current_build().build_id

    fake2 = _FakeBookOrchestrator(rebuilt_count=1, reused_count=0)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake2)
    rt2 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt2.run()

    report = cache_state.get_current_cache_validation_report()
    # Neither fake run ever set compiler/knowledge-graph chapter state,
    # so both builds' own fingerprints are identically empty/None --
    # fingerprints unchanged, but this run's own ExecutionPlan rebuilt
    # a chapter (existence-based reuse signal, not fingerprint-based) --
    # exactly the DIVERGENT case validation.py documents.
    assert report["comparison_basis"] == "previous_snapshot"
    assert report["previous_build_id"] == first_build_id
    assert report["fingerprints_changed"] is False
    assert report["overall_status"] == STATUS_DIVERGENT


def test_run_records_cache_even_on_failure_when_build_was_recorded(fake_storage, monkeypatch):
    """Mirrors _record_build()'s/_record_execution()'s own "a FAILED
    run still gets a record" contract: a FAILED run still gets a Build
    (status FAILED) and a manifest, so Phase F4.1 still has something
    to cache/validate against."""
    fake = _FakeBookOrchestrator(raise_exc=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    with pytest.raises(RuntimeError):
        rt.run()

    assert build_state.has_current_build() is True
    assert cache_state.has_current_cache_entry() is True


def test_cache_failure_never_masks_a_successful_run(fake_book_orchestrator, fake_storage, monkeypatch):
    import cache.snapshot_store as snapshot_store_mod

    def _boom(*a, **k):
        raise RuntimeError("cache exploded")

    monkeypatch.setattr(snapshot_store_mod, "persist_fingerprint_snapshot", _boom)
    # runtime.py imports persist_fingerprint_snapshot locally inside
    # _record_cache(); patch it at its own defining module so that
    # local `from cache.snapshot_store import persist_fingerprint_snapshot`
    # resolves to the broken version.

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()  # must not raise despite cache blowing up

    assert isinstance(result, list) and len(result) == 1
    # Phase F4.1's own bookkeeping failed silently -- state was reset
    # at the top of the run and never repopulated.
    assert cache_state.has_current_cache_entry() is False
    # Phase F2/F3 must be entirely unaffected by Phase F4.1's failure.
    assert build_state.has_current_build() is True
    assert execution_state.has_current_execution_report() is True


def test_new_run_resets_previous_cache_state(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    first_entry = cache_state.get_current_cache_entry()
    assert first_entry is not None

    rt2 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt2.run()
    second_entry = cache_state.get_current_cache_entry()
    assert second_entry is not None
    assert second_entry["build_id"] != first_entry["build_id"]


def test_cache_never_writes_when_build_manifest_bookkeeping_itself_failed(fake_book_orchestrator, monkeypatch):
    """If Phase F2's own bookkeeping breaks entirely (no manifested
    Build recorded at all), Phase F4.1 must skip cleanly rather than
    raise -- there is nothing to cache or validate."""
    def broken_get_storage():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(json_writer, "get_storage", broken_get_storage)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()  # must not raise

    assert isinstance(result, list)
    assert build_state.has_current_build() is False
    assert cache_state.has_current_cache_entry() is False


# ---------------------------------------------------------------------------
# 10. backward compatibility
# ---------------------------------------------------------------------------

def test_run_return_shape_unchanged_by_phase_f4_1(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()
    assert result == fake_book_orchestrator._books


def test_phase_f2_build_manifest_unaffected_by_phase_f4_1(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    build = build_state.get_current_build()
    assert build.build_manifest is not None
    assert build.build_manifest["fingerprints"] == {
        "compiler_fingerprint": None, "graph_fingerprint": None, "configuration_fingerprint": None,
    }


def test_phase_f3_execution_report_unaffected_by_phase_f4_1(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    report = execution_state.get_current_execution_report()
    assert report["executed_artifacts"] == ["json_out/.../02_ch.json"]
    assert report["reused_artifacts"] == ["json_out/.../01_ch.json"]


def test_existing_f2_f3_test_surfaces_still_importable_alongside_cache():
    """A trivial smoke test proving cache/ introduces no import-order
    or naming collision with artifact_manager/build_executor -- both
    packages' own state modules remain independently importable and
    independently resettable."""
    from artifact_manager import state as bs
    from build_executor import state as es
    from cache import state as cs

    bs.reset_current_build()
    es.reset_current_execution_report()
    cs.reset_current_cache_state()

    assert bs.has_current_build() is False
    assert es.has_current_execution_report() is False
    assert cs.has_current_cache_entry() is False
    assert cs.has_current_cache_validation_report() is False


def test_cache_state_lifecycle():
    assert cache_state.has_current_cache_entry() is False
    assert cache_state.get_current_cache_entry() is None
    cache_state.set_current_cache_entry({"build_id": "build-x"})
    assert cache_state.has_current_cache_entry() is True
    assert cache_state.get_current_cache_entry() == {"build_id": "build-x"}

    assert cache_state.has_current_cache_validation_report() is False
    cache_state.set_current_cache_validation_report({"overall_status": STATUS_CONSISTENT})
    assert cache_state.has_current_cache_validation_report() is True
    assert cache_state.get_current_cache_validation_report()["overall_status"] == STATUS_CONSISTENT

    cache_state.reset_current_cache_state()
    assert cache_state.has_current_cache_entry() is False
    assert cache_state.has_current_cache_validation_report() is False