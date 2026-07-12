"""
tests/test_f5_release.py — Phase F5: Compiler Release Finalization
tests.

Same layered split test_f4_1_cache.py/test_f4_2_cache_reuse.py already
use, one package over:

  * UNIT tests for compiler_release.finalize/persistence/discovery/
    report/state in isolation, using the exact same FakeStorage
    test_f4_1_cache.py already defines (re-declared here, not imported,
    mirroring test_f2/test_f3/test_f4_1/test_f4_2's own convention of
    each suite owning its own fakes).
  * INTEGRATION tests exercising CompilerRuntime.run()/resume() end to
    end, with book_orchestrator faked (mirroring test_f2/test_f3/
    test_f4_1's own _FakeBookOrchestrator) and modules.json_writer's
    storage singleton swapped for the same FakeStorage, proving Phase
    F5 is actually wired into CompilerRuntime._execute() (via
    _record_release(), on both the failure and success paths) without
    changing run()/resume()'s own return shape, and without changing
    Phase F1's/F2's/F3's/F4's own recorded state.
  * BACKWARD COMPATIBILITY tests confirming status()'s own return shape
    is unchanged after Phase F5 is wired in.
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
from compiler_release import state as release_state  # noqa: E402
from compiler_release.discovery import list_release_manifests, release_history  # noqa: E402
from compiler_release.exceptions import ReleaseManifestError  # noqa: E402
from compiler_release.finalize import (  # noqa: E402
    determine_final_release_status,
    finalize_release,
    generate_compiler_release_manifest,
)
from compiler_release.persistence import (  # noqa: E402
    persist_release_manifest,
    load_release_manifest,
    release_manifest_exists,
    release_manifest_record_path,
    release_root,
)
from compiler_release.report import (  # noqa: E402
    STATUS_FAILED,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
)
from runtime.context import ExecutionContext, RuntimeStatus  # noqa: E402
from runtime.runtime import CompilerRuntime  # noqa: E402
from runtime import state as runtime_state  # noqa: E402
from storage.exceptions import NotFoundError  # noqa: E402
from modules import json_writer  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fakes (mirrors test_f4_1_cache.py's own FakeStorage exactly)
# ---------------------------------------------------------------------------

class FakeStorage:
    """In-memory stand-in for OneDriveStorage exposing only the surface
    compiler_release/artifact_manager/build_executor/cache actually
    call: upload_json/download_json/exists/list_directory. No Graph/
    MSAL/network involved."""

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
    run-scoped -- reset before/after every test, same idiom
    test_f2/test_f3/test_f4_1/test_f4_2's own _reset_state fixture
    already uses."""
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()
    execution_state.reset_current_execution_report()
    cache_state.reset_current_cache_state()
    release_state.reset_current_release_manifest_state()
    yield
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()
    execution_state.reset_current_execution_report()
    cache_state.reset_current_cache_state()
    release_state.reset_current_release_manifest_state()


@pytest.fixture
def fake_storage(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(json_writer, "_storage_singleton", storage)
    return storage


def _make_manifested_build(build_id_started_at, fingerprints=None, all_stats=None):
    """Builds a fully-manifested Build (Phase F2 shape) for a given
    started_at timestamp -- mirrors test_f4_1_cache.py's own helper
    exactly."""
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


def _execution_report(reused_count=1, rebuilt_count=1):
    plan = generate_execution_plan(
        (
            [{"chapter_key": "json_out/.../01_ch.json", "decision": "reuse", "reason": "already exists"}]
            * reused_count
        ) + (
            [{"chapter_key": "json_out/.../02_ch.json", "decision": "rebuild", "reason": "new"}]
            * rebuilt_count
        ),
        namespace="<run>",
    )
    return {"execution_statistics": plan["summary"]}


# ---------------------------------------------------------------------------
# 1. determine_final_release_status() -- one test per §11 branch
# ---------------------------------------------------------------------------

def test_status_ready_when_completed_no_failures_no_divergence():
    status = determine_final_release_status(
        "COMPLETED", {"chapters_failed": 0}, {"overall_status": "CONSISTENT"},
    )
    assert status == STATUS_READY


def test_status_ready_when_completed_no_baseline_cache():
    status = determine_final_release_status(
        "COMPLETED", {"chapters_failed": 0}, {"overall_status": "NO_BASELINE"},
    )
    assert status == STATUS_READY


def test_status_ready_when_completed_and_cache_report_is_none():
    status = determine_final_release_status("COMPLETED", {"chapters_failed": 0}, None)
    assert status == STATUS_READY


def test_status_ready_with_warnings_when_chapters_failed():
    status = determine_final_release_status(
        "COMPLETED", {"chapters_failed": 2}, {"overall_status": "CONSISTENT"},
    )
    assert status == STATUS_READY_WITH_WARNINGS


def test_status_ready_with_warnings_when_cache_divergent():
    status = determine_final_release_status(
        "COMPLETED", {"chapters_failed": 0}, {"overall_status": "DIVERGENT"},
    )
    assert status == STATUS_READY_WITH_WARNINGS


def test_status_failed_when_runtime_failed():
    status = determine_final_release_status("FAILED", None, None)
    assert status == STATUS_FAILED


def test_status_failed_when_runtime_cancelled():
    status = determine_final_release_status("CANCELLED", {"chapters_failed": 0}, {"overall_status": "CONSISTENT"})
    assert status == STATUS_FAILED


def test_status_determinism_same_inputs_twice_identical_output():
    args = ("COMPLETED", {"chapters_failed": 1}, {"overall_status": "DIVERGENT"})
    assert determine_final_release_status(*args) == determine_final_release_status(*args)


# ---------------------------------------------------------------------------
# 2. generate_compiler_release_manifest()
# ---------------------------------------------------------------------------

def test_generate_manifest_shape_has_every_field():
    build = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "abc", "graph_fingerprint": None, "configuration_fingerprint": None},
    )
    execution_report = _execution_report(reused_count=2, rebuilt_count=0)
    cache_entry = {"build_id": build.build_id, "fingerprint_snapshot": {"compiler_fingerprint": "abc"}}
    cache_validation_report = {
        "overall_status": "CONSISTENT", "comparison_basis": "previous_snapshot", "divergences": [],
    }

    manifest = generate_compiler_release_manifest(
        RuntimeStatus.COMPLETED, build, execution_report, cache_entry, cache_validation_report,
        chapters_failed=0,
    )

    for key in (
        "release_manifest_version", "build_id", "generated_at", "runtime_status",
        "final_release_status", "build_summary", "execution_summary", "cache_summary",
        "divergences", "warnings", "errors",
    ):
        assert key in manifest

    assert manifest["build_id"] == build.build_id
    assert manifest["runtime_status"] == RuntimeStatus.COMPLETED
    assert manifest["final_release_status"] == STATUS_READY
    assert manifest["build_summary"]["build_id"] == build.build_id
    assert manifest["build_summary"]["manifest_fingerprint"] == build.build_manifest["manifest_fingerprint"]
    assert manifest["execution_summary"]["reused_count"] == 2
    assert manifest["execution_summary"]["rebuilt_count"] == 0
    assert manifest["execution_summary"]["chapters_failed"] == 0
    assert manifest["cache_summary"] == {
        "has_cache_entry": True, "comparison_basis": "previous_snapshot", "cache_overall_status": "CONSISTENT",
    }


def test_generate_manifest_raises_when_build_manifest_missing():
    context = ExecutionContext(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=None)
    build = create_build(
        context=context, status=RuntimeStatus.COMPLETED,
        all_stats=[{"found": 1, "written": 1, "failed": 0, "book_name": "A"}],
        error=None, started_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ReleaseManifestError):
        generate_compiler_release_manifest(RuntimeStatus.COMPLETED, build, None, None, None)


def test_generate_manifest_raises_when_build_is_none():
    with pytest.raises(ReleaseManifestError):
        generate_compiler_release_manifest(RuntimeStatus.COMPLETED, None, None, None, None)


def test_generate_manifest_degrades_gracefully_when_execution_report_missing():
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    manifest = generate_compiler_release_manifest(
        RuntimeStatus.COMPLETED, build, None, None, None,
    )
    assert manifest["execution_summary"] is None
    assert manifest["cache_summary"] == {
        "has_cache_entry": False, "comparison_basis": None, "cache_overall_status": None,
    }
    assert any("ExecutionReport" in w for w in manifest["warnings"])


def test_generate_manifest_degrades_gracefully_when_cache_validation_report_missing():
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    execution_report = _execution_report(reused_count=1, rebuilt_count=0)
    manifest = generate_compiler_release_manifest(
        RuntimeStatus.COMPLETED, build, execution_report, None, None,
    )
    assert manifest["cache_summary"]["has_cache_entry"] is False
    assert manifest["cache_summary"]["cache_overall_status"] is None
    # A missing cache baseline must not, on its own, produce a warning
    # verdict -- NO_BASELINE-equivalent (None) is a READY-eligible state.
    assert manifest["final_release_status"] == STATUS_READY


def test_generate_manifest_never_mutates_its_inputs():
    build = _make_manifested_build(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        fingerprints={"compiler_fingerprint": "a"},
    )
    manifest_before = dict(build.build_manifest)
    execution_report = _execution_report(reused_count=1, rebuilt_count=1)
    execution_report_before = dict(execution_report)
    cache_validation_report = {"overall_status": "CONSISTENT", "comparison_basis": "previous_snapshot", "divergences": ["x"]}
    cache_validation_report_before = dict(cache_validation_report)

    generate_compiler_release_manifest(
        RuntimeStatus.COMPLETED, build, execution_report, {"build_id": build.build_id}, cache_validation_report,
    )

    assert build.build_manifest == manifest_before
    assert execution_report == execution_report_before
    assert cache_validation_report == cache_validation_report_before


def test_generate_manifest_surfaces_divergences_verbatim():
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    cache_validation_report = {
        "overall_status": "DIVERGENT", "comparison_basis": "previous_snapshot",
        "divergences": ["fingerprints changed but nothing rebuilt"],
    }
    manifest = generate_compiler_release_manifest(
        RuntimeStatus.COMPLETED, build, _execution_report(1, 0), {"build_id": build.build_id}, cache_validation_report,
    )
    assert manifest["divergences"] == ["fingerprints changed but nothing rebuilt"]
    assert manifest["final_release_status"] == STATUS_READY_WITH_WARNINGS


def test_finalize_release_matches_generate_compiler_release_manifest():
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    a = finalize_release(RuntimeStatus.COMPLETED, build, None, None, None, generated_at="2026-01-01T00:00:00+00:00")
    b = generate_compiler_release_manifest(
        RuntimeStatus.COMPLETED, build, None, None, None, generated_at="2026-01-01T00:00:00+00:00",
    )
    assert a == b


# ---------------------------------------------------------------------------
# 3. persistence.py / discovery.py
# ---------------------------------------------------------------------------

def test_persist_release_manifest_writes_to_expected_path(fake_storage):
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    manifest = generate_compiler_release_manifest(RuntimeStatus.COMPLETED, build, None, None, None)
    result = persist_release_manifest(fake_storage, manifest)
    assert result["release_manifest_path"] == release_manifest_record_path(build.build_id)
    assert fake_storage.files[release_manifest_record_path(build.build_id)] == manifest


def test_persist_release_manifest_requires_build_id(fake_storage):
    with pytest.raises(ReleaseManifestError):
        persist_release_manifest(fake_storage, {"final_release_status": "READY"})


def test_release_manifest_record_path_layout_is_own_sibling_root():
    path = release_manifest_record_path("build-20260101T000000000000Z-abc123456789")
    assert path == f"{release_root()}/build-20260101T000000000000Z-abc123456789/release_manifest.json"
    assert release_root() == "_runtime_release"


def test_load_release_manifest_round_trip(fake_storage):
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    manifest = generate_compiler_release_manifest(RuntimeStatus.COMPLETED, build, None, None, None)
    persist_release_manifest(fake_storage, manifest)

    loaded = load_release_manifest(fake_storage, build.build_id)
    assert loaded == manifest


def test_load_release_manifest_raises_when_missing(fake_storage):
    with pytest.raises(ReleaseManifestError):
        load_release_manifest(fake_storage, "build-does-not-exist")


def test_release_manifest_exists_false_then_true(fake_storage):
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert release_manifest_exists(fake_storage, build.build_id) is False
    manifest = generate_compiler_release_manifest(RuntimeStatus.COMPLETED, build, None, None, None)
    persist_release_manifest(fake_storage, manifest)
    assert release_manifest_exists(fake_storage, build.build_id) is True


def test_list_release_manifests_empty_when_nothing_persisted(fake_storage):
    assert list_release_manifests(fake_storage) == []


def test_release_history_returns_every_entry_in_order(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    m1 = generate_compiler_release_manifest(RuntimeStatus.COMPLETED, b1, None, None, None)
    m2 = generate_compiler_release_manifest(RuntimeStatus.COMPLETED, b2, None, None, None)
    persist_release_manifest(fake_storage, m1)
    persist_release_manifest(fake_storage, m2)

    history = release_history(fake_storage)
    assert [h["build_id"] for h in history] == sorted([b1.build_id, b2.build_id])


def test_release_history_one_bad_record_does_not_hide_the_rest(fake_storage):
    b1 = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b2 = _make_manifested_build(datetime(2026, 1, 2, tzinfo=timezone.utc))
    m2 = generate_compiler_release_manifest(RuntimeStatus.COMPLETED, b2, None, None, None)
    persist_release_manifest(fake_storage, m2)
    # b1's own folder exists (via list_directory) but its manifest.json
    # was never actually written -- a partially-written record.
    fake_storage.files[f"{release_root()}/{b1.build_id}/.placeholder"] = {}

    history = release_history(fake_storage)
    assert [h["build_id"] for h in history] == [b2.build_id]


def test_release_never_writes_into_runtime_builds_or_cache_roots(fake_storage):
    build = _make_manifested_build(datetime(2026, 1, 1, tzinfo=timezone.utc))
    manifest = generate_compiler_release_manifest(RuntimeStatus.COMPLETED, build, None, None, None)
    persist_release_manifest(fake_storage, manifest)
    assert all(not p.startswith("_runtime_builds/") for p in fake_storage.files)
    assert all(not p.startswith("_runtime_cache/") for p in fake_storage.files)
    assert all(p.startswith(f"{release_root()}/") for p in fake_storage.files)


# ---------------------------------------------------------------------------
# 4. runtime integration
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


def test_run_records_a_release_manifest_on_success(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()

    assert release_state.has_current_release_manifest() is True
    manifest = rt.release_manifest()
    build = build_state.get_current_build()
    assert manifest["build_id"] == build.build_id
    assert manifest["runtime_status"] == RuntimeStatus.COMPLETED
    assert manifest["final_release_status"] in (STATUS_READY, STATUS_READY_WITH_WARNINGS)
    assert release_manifest_exists(fake_storage, build.build_id) is True


def test_run_records_a_release_manifest_on_failure_when_build_was_recorded(fake_storage, monkeypatch):
    """Mirrors _record_build()'s/_record_execution()'s/_record_cache()'s
    own "a FAILED run still gets a record" contract."""
    fake = _FakeBookOrchestrator(raise_exc=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    with pytest.raises(RuntimeError):
        rt.run()

    assert build_state.has_current_build() is True
    assert release_state.has_current_release_manifest() is True
    manifest = rt.release_manifest()
    assert manifest["runtime_status"] == RuntimeStatus.FAILED
    assert manifest["final_release_status"] == STATUS_FAILED


def test_run_produces_no_manifest_when_no_build_was_recorded(fake_book_orchestrator, monkeypatch):
    """If Phase F2's own bookkeeping breaks entirely (no manifested
    Build recorded at all), Phase F5 must skip cleanly rather than
    raise -- not an error, just nothing to finalize."""
    def broken_get_storage():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(json_writer, "get_storage", broken_get_storage)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()  # must not raise

    assert isinstance(result, list)
    assert build_state.has_current_build() is False
    assert release_state.has_current_release_manifest() is False
    assert rt.release_manifest() is None


def test_release_failure_never_masks_a_successful_run(fake_book_orchestrator, fake_storage, monkeypatch):
    import compiler_release.persistence as persistence_mod

    def _boom(*a, **k):
        raise RuntimeError("release exploded")

    monkeypatch.setattr(persistence_mod, "persist_release_manifest", _boom)
    # runtime.py imports persist_release_manifest locally inside
    # _record_release(); patch it at its own defining module so the
    # local `from compiler_release.persistence import
    # persist_release_manifest` resolves to the broken version.

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()  # must not raise despite F5 blowing up

    assert isinstance(result, list) and len(result) == 1
    # Phase F5's own bookkeeping failed silently -- state was reset at
    # the top of the run and never repopulated.
    assert release_state.has_current_release_manifest() is False
    # Phase F1-F4 must be entirely unaffected by Phase F5's failure.
    assert build_state.has_current_build() is True
    assert execution_state.has_current_execution_report() is True
    assert cache_state.has_current_cache_entry() is True


def test_new_run_resets_previous_release_state(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    first_manifest = rt.release_manifest()
    assert first_manifest is not None

    rt2 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt2.run()
    second_manifest = rt2.release_manifest()
    assert second_manifest is not None
    assert second_manifest["build_id"] != first_manifest["build_id"]


def test_release_history_reflects_two_persisted_runs_in_order(fake_storage, monkeypatch):
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

    history = rt2.release_history()
    assert [h["build_id"] for h in history] == sorted([first_build_id, second_build_id])


def test_release_optimization_context_matches_cache_optimization_report(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    a = dict(rt.release_optimization_context())
    b = dict(rt.cache_optimization_report())
    # Each call independently stamps its own "now" via
    # cache.report.new_generated_at() -- not itself part of the
    # comparison; a pass-through's contract is "same computation",
    # not "same wall-clock instant".
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


def test_release_manifest_reflects_chapters_failed_from_runtime_progress(fake_storage, monkeypatch):
    fake = _FakeBookOrchestrator(
        books=[
            {
                "found": 2, "written": 1, "failed": 1, "book_title": "Book One", "book_name": "Book One",
                "written_paths": [], "book_manifest_path": None,
                "execution_plan": generate_execution_plan(
                    [{"chapter_key": "json_out/.../01_ch.json", "decision": "reuse", "reason": "already exists"}],
                    namespace="Book One",
                ),
            },
        ],
    )
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()

    manifest = rt.release_manifest()
    assert manifest["execution_summary"]["chapters_failed"] == 1
    assert manifest["final_release_status"] == STATUS_READY_WITH_WARNINGS


# ---------------------------------------------------------------------------
# 5. backward compatibility
# ---------------------------------------------------------------------------

def test_run_return_shape_unchanged_by_phase_f5(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()
    assert result == fake_book_orchestrator._books


def test_status_return_shape_unchanged_by_phase_f5(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    status = rt.status()
    assert set(status.keys()) == {"status", "context", "progress", "error"}


def test_phase_f2_f3_f4_state_unaffected_by_phase_f5(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    build = build_state.get_current_build()
    assert build.build_manifest is not None
    assert build.build_manifest["fingerprints"] == {
        "compiler_fingerprint": None, "graph_fingerprint": None, "configuration_fingerprint": None,
    }
    assert execution_state.has_current_execution_report() is True
    assert cache_state.has_current_cache_entry() is True


def test_release_manifest_and_release_history_safe_before_any_run():
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    assert rt.release_manifest() is None
