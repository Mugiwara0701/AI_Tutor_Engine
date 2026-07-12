"""
tests/test_f4_2_cache_reuse.py — Phase F4.2: Cache Reuse (previous
snapshot discovery/selection/loading/validation, runtime integration,
cross-run cache optimization reporting) tests.

Same layered split test_f4_1_cache.py already uses, one phase over:

  * UNIT tests for cache.reuse in isolation, using the exact same
    FakeStorage test_f4_1_cache.py already defines (re-declared here,
    not imported, mirroring test_f2/test_f3/test_f4_1's own convention
    of each suite owning its own fakes).
  * INTEGRATION tests exercising CompilerRuntime.run() end to end with
    book_orchestrator faked, proving Phase F4.2 is actually wired into
    CompilerRuntime._record_cache() (via cache.reuse.
    select_previous_snapshot()) and exposed through status()/the new
    cache_history()/previous_cache_entry()/cache_optimization_report()
    methods, without changing run()'s own return shape or Phase
    F4.1's own recorded state.
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
from cache.exceptions import CacheSnapshotInvalidError  # noqa: E402
from cache.report import STATUS_CONSISTENT, STATUS_DIVERGENT, STATUS_NO_BASELINE  # noqa: E402
from cache.reuse import (  # noqa: E402
    analyze_cache_reuse,
    discover_previous_snapshot_candidates,
    list_reusable_snapshots,
    select_previous_fingerprint_snapshot,
    select_previous_snapshot,
    validate_cache_entry,
)
from cache.snapshot_store import build_cache_entry, persist_fingerprint_snapshot  # noqa: E402
from runtime.context import ExecutionContext, RuntimeStatus  # noqa: E402
from runtime.runtime import CompilerRuntime  # noqa: E402
from runtime import state as runtime_state  # noqa: E402
from storage.exceptions import NotFoundError  # noqa: E402
from modules import json_writer  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fakes (mirrors test_f4_1_cache.py's own FakeStorage exactly)
# ---------------------------------------------------------------------------

class FakeStorage:
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


def _make_manifested_build(build_id_started_at, fingerprints=None, all_stats=None, status=RuntimeStatus.COMPLETED):
    context = ExecutionContext(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=None)
    build = create_build(
        context=context, status=status,
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


def _persist(storage, build, fingerprints=None):
    if fingerprints is not None:
        entry = build_cache_entry(build)
        entry = dict(entry)
        entry["fingerprint_snapshot"] = dict(fingerprints)
        persist_fingerprint_snapshot(storage, entry)
        return entry
    entry = build_cache_entry(build)
    persist_fingerprint_snapshot(storage, entry)
    return entry


# ---------------------------------------------------------------------------
# 1. validation
# ---------------------------------------------------------------------------

def test_validate_cache_entry_accepts_well_formed_entry():
    entry = {
        "cache_entry_version": "F4.1",
        "build_id": "build-x",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "build_status": "COMPLETED",
        "fingerprint_snapshot": {"compiler_fingerprint": "a"},
    }
    assert validate_cache_entry(entry, "build-x") is entry  # returned unchanged, not copied


def test_validate_cache_entry_rejects_non_dict():
    with pytest.raises(CacheSnapshotInvalidError):
        validate_cache_entry("not-a-dict", "build-x")


def test_validate_cache_entry_rejects_missing_build_id():
    with pytest.raises(CacheSnapshotInvalidError):
        validate_cache_entry({"fingerprint_snapshot": {}}, "build-x")


def test_validate_cache_entry_rejects_build_id_mismatch():
    with pytest.raises(CacheSnapshotInvalidError):
        validate_cache_entry(
            {"build_id": "build-other", "fingerprint_snapshot": {}}, "build-x"
        )


def test_validate_cache_entry_rejects_missing_fingerprint_snapshot():
    with pytest.raises(CacheSnapshotInvalidError):
        validate_cache_entry({"build_id": "build-x"}, "build-x")


def test_validate_cache_entry_rejects_non_dict_fingerprint_snapshot():
    with pytest.raises(CacheSnapshotInvalidError):
        validate_cache_entry(
            {"build_id": "build-x", "fingerprint_snapshot": "oops"}, "build-x"
        )


def test_validate_cache_entry_tolerates_unknown_version(caplog):
    entry = {
        "cache_entry_version": "F9.9-from-the-future",
        "build_id": "build-x",
        "fingerprint_snapshot": {},
    }
    # Must not raise -- forward-compatible reader (see module docstring).
    assert validate_cache_entry(entry, "build-x") is entry


def test_validate_cache_entry_never_mutates_its_input():
    entry = {"build_id": "build-x", "fingerprint_snapshot": {"a": "1"}}
    entry_copy = dict(entry)
    validate_cache_entry(entry, "build-x")
    assert entry == entry_copy


# ---------------------------------------------------------------------------
# 2. discovery
# ---------------------------------------------------------------------------

def test_discover_previous_snapshot_candidates_empty_when_nothing_persisted(fake_storage):
    assert discover_previous_snapshot_candidates(fake_storage) == []


def test_discover_previous_snapshot_candidates_newest_first(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    b3 = _make_manifested_build(datetime(2026, 1, 3, tzinfo=timezone.utc))
    for b in (b1, b2, b3):
        _persist(fake_storage, b)

    candidates = discover_previous_snapshot_candidates(fake_storage)
    assert candidates == [b3.build_id, b2.build_id, b1.build_id]


def test_discover_previous_snapshot_candidates_respects_before_build_id(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    for b in (b1, b2):
        _persist(fake_storage, b)

    candidates = discover_previous_snapshot_candidates(fake_storage, before_build_id=b2.build_id)
    assert candidates == [b1.build_id]


# ---------------------------------------------------------------------------
# 3. selection / loading -- missing snapshot
# ---------------------------------------------------------------------------

def test_select_previous_snapshot_returns_none_when_nothing_persisted(fake_storage):
    assert select_previous_snapshot(fake_storage) is None
    assert select_previous_fingerprint_snapshot(fake_storage) is None


def test_select_previous_snapshot_returns_none_before_the_first_build(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    _persist(fake_storage, b1)
    assert select_previous_snapshot(fake_storage, before_build_id=b1.build_id) is None


# ---------------------------------------------------------------------------
# 4. selection / loading -- multiple previous builds
# ---------------------------------------------------------------------------

def test_select_previous_snapshot_picks_most_recent_strictly_before(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    b3 = _make_manifested_build(datetime(2026, 1, 3, tzinfo=timezone.utc))
    _persist(fake_storage, b1, {"compiler_fingerprint": "v1"})
    _persist(fake_storage, b2, {"compiler_fingerprint": "v2"})
    _persist(fake_storage, b3, {"compiler_fingerprint": "v3"})

    result = select_previous_snapshot(fake_storage, before_build_id=b3.build_id)
    assert result["build_id"] == b2.build_id

    snapshot = select_previous_fingerprint_snapshot(fake_storage, before_build_id=b3.build_id)
    assert snapshot["compiler_fingerprint"] == "v2"


# ---------------------------------------------------------------------------
# 5. selection / loading -- corrupted snapshot (fallback behavior)
# ---------------------------------------------------------------------------

def test_select_previous_snapshot_falls_back_past_unreadable_record(fake_storage):
    """The key F4.2 behavior F4.1's own load_previous_cache_entry()
    does not have: when the single most recent candidate's record is
    unreadable, select_previous_snapshot() keeps walking to an older,
    still-good one instead of giving up."""
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    _persist(fake_storage, b1, {"compiler_fingerprint": "v1"})
    _persist(fake_storage, b2, {"compiler_fingerprint": "v2"})
    # Corrupt b2's own persisted record in place (simulates a partially
    # written / truncated JSON record storage still lists but can't
    # meaningfully serve).
    path = f"_runtime_cache/{b2.build_id}/fingerprint_snapshot.json"
    fake_storage.files[path] = {"build_id": b2.build_id}  # missing fingerprint_snapshot

    result = select_previous_snapshot(fake_storage)
    assert result["build_id"] == b1.build_id
    assert result["fingerprint_snapshot"]["compiler_fingerprint"] == "v1"


def test_select_previous_snapshot_falls_back_past_missing_record(fake_storage, monkeypatch):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    _persist(fake_storage, b1, {"compiler_fingerprint": "v1"})
    _persist(fake_storage, b2, {"compiler_fingerprint": "v2"})

    import cache.reuse as reuse_mod
    real_load = reuse_mod.load_fingerprint_snapshot

    def _flaky(storage, build_id):
        if build_id == b2.build_id:
            from cache.exceptions import CacheReadError
            raise CacheReadError(build_id, "simulated storage read failure")
        return real_load(storage, build_id)

    monkeypatch.setattr(reuse_mod, "load_fingerprint_snapshot", _flaky)

    result = select_previous_snapshot(fake_storage)
    assert result["build_id"] == b1.build_id


def test_select_previous_snapshot_returns_none_when_every_candidate_is_bad(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    _persist(fake_storage, b1)
    path = f"_runtime_cache/{b1.build_id}/fingerprint_snapshot.json"
    fake_storage.files[path] = {"not": "a cache entry"}

    assert select_previous_snapshot(fake_storage) is None


def test_select_previous_snapshot_respects_max_candidates(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    _persist(fake_storage, b1, {"compiler_fingerprint": "v1"})
    path = f"_runtime_cache/{b2.build_id}/fingerprint_snapshot.json"
    fake_storage.files[path] = {"build_id": b2.build_id}  # invalid -- missing fingerprint_snapshot

    # Only one candidate examined (the bad one) -- must not fall back to b1.
    result = select_previous_snapshot(fake_storage, max_candidates=1)
    assert result is None


# ---------------------------------------------------------------------------
# 6. list_reusable_snapshots
# ---------------------------------------------------------------------------

def test_list_reusable_snapshots_excludes_invalid_entries(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    _persist(fake_storage, b1, {"compiler_fingerprint": "v1"})
    path = f"_runtime_cache/{b2.build_id}/fingerprint_snapshot.json"
    fake_storage.files[path] = {"build_id": b2.build_id}  # invalid

    reusable = list_reusable_snapshots(fake_storage)
    assert [e["build_id"] for e in reusable] == [b1.build_id]


# ---------------------------------------------------------------------------
# 7. deterministic behavior
# ---------------------------------------------------------------------------

def test_select_previous_snapshot_is_deterministic(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    _persist(fake_storage, b1, {"compiler_fingerprint": "v1"})
    _persist(fake_storage, b2, {"compiler_fingerprint": "v2"})

    r1 = select_previous_snapshot(fake_storage)
    r2 = select_previous_snapshot(fake_storage)
    assert r1 == r2


def test_analyze_cache_reuse_is_deterministic(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    _persist(fake_storage, b1, {"compiler_fingerprint": "v1"})
    _persist(fake_storage, b2, {"compiler_fingerprint": "v2"})

    r1 = analyze_cache_reuse(fake_storage, generated_at="2026-01-05T00:00:00+00:00")
    r2 = analyze_cache_reuse(fake_storage, generated_at="2026-01-05T00:00:00+00:00")
    assert r1 == r2


# ---------------------------------------------------------------------------
# 8. cache optimization reporting / cross-run reuse analysis
# ---------------------------------------------------------------------------

def test_analyze_cache_reuse_empty_history(fake_storage):
    report = analyze_cache_reuse(fake_storage)
    assert report["total_builds"] == 0
    assert report["readable_snapshots"] == 0
    assert report["comparable_pairs"] == 0
    assert report["fingerprint_churn_rate"] is None
    assert report["longest_unchanged_streak"] == 0
    assert report["most_recent_build_id"] is None


def test_analyze_cache_reuse_counts_unchanged_and_changed_pairs(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    b3 = _make_manifested_build(datetime(2026, 1, 3, tzinfo=timezone.utc))
    same = {"compiler_fingerprint": "a", "graph_fingerprint": "b", "configuration_fingerprint": "c"}
    _persist(fake_storage, b1, same)
    _persist(fake_storage, b2, same)  # unchanged vs b1
    _persist(fake_storage, b3, {"compiler_fingerprint": "z", "graph_fingerprint": "b", "configuration_fingerprint": "c"})  # changed vs b2

    report = analyze_cache_reuse(fake_storage)
    assert report["total_builds"] == 3
    assert report["readable_snapshots"] == 3
    assert report["comparable_pairs"] == 2
    assert report["unchanged_pairs"] == 1
    assert report["changed_pairs"] == 1
    assert report["fingerprint_churn_rate"] == 0.5
    assert report["longest_unchanged_streak"] == 1
    assert report["most_recent_build_id"] == b3.build_id
    assert report["most_recent_status"] == "COMPLETED"


def test_analyze_cache_reuse_longest_streak_spans_multiple_unchanged_pairs(fake_storage):
    same = {"compiler_fingerprint": "a"}
    builds = [
        _make_manifested_build(datetime(2026, 1, d, tzinfo=timezone.utc)) for d in range(1, 5)
    ]
    for b in builds:
        _persist(fake_storage, b, same)

    report = analyze_cache_reuse(fake_storage)
    assert report["comparable_pairs"] == 3
    assert report["unchanged_pairs"] == 3
    assert report["longest_unchanged_streak"] == 3
    assert report["fingerprint_churn_rate"] == 0.0


def test_analyze_cache_reuse_excludes_invalid_snapshot_from_comparable_pairs(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    b3 = _make_manifested_build(datetime(2026, 1, 3, tzinfo=timezone.utc))
    same = {"compiler_fingerprint": "a"}
    _persist(fake_storage, b1, same)
    path = f"_runtime_cache/{b2.build_id}/fingerprint_snapshot.json"
    fake_storage.files[path] = {"build_id": b2.build_id}  # invalid, breaks the chain
    _persist(fake_storage, b3, same)

    report = analyze_cache_reuse(fake_storage)
    assert report["total_builds"] == 3
    assert report["readable_snapshots"] == 2
    assert report["invalid_or_corrupt_snapshots"] == 1
    # b1<->b2 and b2<->b3 are both broken by b2's own invalid record --
    # zero comparable pairs remain even though b1 and b3 share identical
    # fingerprints, because they are not *consecutive*.
    assert report["comparable_pairs"] == 0
    assert len(report["warnings"]) == 1


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


def test_status_exposes_cache_summary_after_a_run(fake_book_orchestrator, fake_storage):
    # cache bookkeeping is exposed via its own cache_status() accessor
    # rather than folded into status() -- see CompilerRuntime.
    # cache_status()'s own docstring for why: status()'s pre-existing,
    # frozen "same behavior -> same status()" determinism contract
    # (tests/test_f1_compiler_runtime.py's own
    # test_two_runtimes_given_identical_inputs_reach_identical_status)
    # cannot hold for fields that are inherently run-unique (build_id)
    # or cross-run-history-dependent (comparison_basis/overall_status).
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()

    status = rt.status()
    assert "cache" not in status

    cache_status = rt.cache_status()
    assert cache_status["has_cache_entry"] is True
    assert cache_status["build_id"] == build_state.get_current_build().build_id
    assert cache_status["overall_status"] == STATUS_NO_BASELINE
    assert cache_status["comparison_basis"] == "no_previous_snapshot"


def test_status_cache_summary_defaults_before_any_run():
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    assert "cache" not in rt.status()
    assert rt.cache_status() == {
        "has_cache_entry": False,
        "build_id": None,
        "previous_build_id": None,
        "comparison_basis": None,
        "overall_status": None,
    }


def test_runtime_cache_history_reflects_persisted_builds(fake_storage, monkeypatch):
    fake1 = _FakeBookOrchestrator(rebuilt_count=1, reused_count=0)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake1)
    rt1 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt1.run()
    first_build_id = build_state.get_current_build().build_id

    fake2 = _FakeBookOrchestrator(rebuilt_count=1, reused_count=0)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake2)
    rt2 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt2.run()
    second_build_id = build_state.get_current_build().build_id

    history = rt2.cache_history()
    assert [h["build_id"] for h in history] == [first_build_id, second_build_id]


def test_runtime_previous_cache_entry_reflects_most_recent_persisted_build(fake_storage, monkeypatch):
    fake1 = _FakeBookOrchestrator(rebuilt_count=1, reused_count=0)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake1)
    rt1 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt1.run()
    first_build_id = build_state.get_current_build().build_id

    # Before a second run, "the previous entry a next run would see" is
    # simply the first run's own entry.
    rt_probe = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    assert rt_probe.previous_cache_entry()["build_id"] == first_build_id


def test_runtime_cache_optimization_report_reflects_history(fake_storage, monkeypatch):
    for _ in range(2):
        fake = _FakeBookOrchestrator(rebuilt_count=1, reused_count=0)
        monkeypatch.setitem(sys.modules, "book_orchestrator", fake)
        rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
        rt.run()

    report = rt.cache_optimization_report()
    assert report["total_builds"] == 2
    assert report["readable_snapshots"] == 2
    assert report["comparable_pairs"] == 1


def test_second_run_still_compares_against_first_runs_snapshot_via_f4_2_selection(fake_storage, monkeypatch):
    """Proves the F4.2 swap inside _record_cache() (select_previous_snapshot()
    instead of F4.1's own load_previous_cache_entry()) preserves F4.1's
    own exact CacheValidationReport behavior for the simple, no-corruption
    case (see test_f4_1_cache.py's own equivalent test)."""
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
    assert report["comparison_basis"] == "previous_snapshot"
    assert report["previous_build_id"] == first_build_id
    assert report["fingerprints_changed"] is False
    assert report["overall_status"] == STATUS_DIVERGENT


def test_third_run_falls_back_past_a_corrupted_second_snapshot(fake_storage, monkeypatch):
    """End-to-end proof of the F4.2 fallback behavior through the real
    runtime integration point: run 1 succeeds, run 2's own persisted
    record gets corrupted afterward, run 3 must still compare against
    run 1's own (still valid) snapshot rather than silently falling
    back to NO_BASELINE."""
    fake1 = _FakeBookOrchestrator(rebuilt_count=0, reused_count=1)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake1)
    rt1 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt1.run()
    first_build_id = build_state.get_current_build().build_id

    fake2 = _FakeBookOrchestrator(rebuilt_count=0, reused_count=1)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake2)
    rt2 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt2.run()
    second_build_id = build_state.get_current_build().build_id

    # Corrupt run 2's own persisted fingerprint snapshot record.
    path = f"_runtime_cache/{second_build_id}/fingerprint_snapshot.json"
    fake_storage.files[path] = {"build_id": second_build_id}  # missing fingerprint_snapshot

    fake3 = _FakeBookOrchestrator(rebuilt_count=0, reused_count=1)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake3)
    rt3 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt3.run()

    report = cache_state.get_current_cache_validation_report()
    assert report["comparison_basis"] == "previous_snapshot"
    assert report["previous_build_id"] == first_build_id


# ---------------------------------------------------------------------------
# 10. backward compatibility
# ---------------------------------------------------------------------------

def test_run_return_shape_unchanged_by_phase_f4_2(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()
    assert result == fake_book_orchestrator._books


def test_status_keys_are_a_superset_of_phase_f1_shape(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    status = rt.status()
    for key in ("status", "context", "progress", "error"):
        assert key in status


def test_phase_f4_1_cache_state_unaffected_by_phase_f4_2(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    assert cache_state.has_current_cache_entry() is True
    assert cache_state.has_current_cache_validation_report() is True
    report = cache_state.get_current_cache_validation_report()
    assert report["overall_status"] == STATUS_NO_BASELINE
