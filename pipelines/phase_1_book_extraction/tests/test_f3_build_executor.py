"""
tests/test_f3_build_executor.py — Phase F3: Build Executor tests.

Three layers, mirroring test_f2_artifact_manager.py's own split one
phase down:

  * UNIT tests for build_executor.plan/report/state in isolation.
  * GATE tests for build_executor.executor.execute_chapter() -- the
    actual pre-execution reuse gate -- using a fake `process_chapter_fn`
    and a monkeypatched `modules.pdf_parser.parse_chapter_pdf`, so the
    reuse/rebuild decision itself is exercised without any real PDF/
    OCR/VLM work.
  * INTEGRATION tests exercising the REAL, modified
    pipeline.process_all_pdfs() chapter loop end to end (proving Phase
    F3 is actually wired in there, not just unit-testable in
    isolation), and CompilerRuntime.run() end to end (proving Phase F3
    is actually wired into _record_execution()).
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import json_writer, pdf_parser  # noqa: E402
from storage.exceptions import NotFoundError  # noqa: E402

from build_executor import state as execution_state  # noqa: E402
from build_executor.exceptions import ExecutionPlanError, ExecutionReportError  # noqa: E402
from build_executor.executor import (  # noqa: E402
    aggregate_run_execution_report,
    execute_chapter,
)
from build_executor.plan import (  # noqa: E402
    aggregate_execution_plan,
    generate_execution_plan,
)
from build_executor.report import generate_execution_report  # noqa: E402

from incremental_compilation import state as incremental_compilation_state  # noqa: E402

from artifact_manager import state as build_state  # noqa: E402
from runtime import state as runtime_state  # noqa: E402
from runtime.runtime import CompilerRuntime  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class FakeStorage:
    """Same in-memory OneDriveStorage stand-in test_f2_artifact_manager.py
    already uses, extended with the two calls modules.json_writer.
    book_output_dir() also makes (create_directory/resolve_path) so the
    REAL pipeline.process_all_pdfs()/json_writer.chapter_output_path()
    can run end to end against it."""

    def __init__(self):
        self.files = {}
        self.dirs_created = set()

    def upload_json(self, obj, path=None, indent=2):
        self.files[path] = obj
        return path

    def download_json(self, path=None):
        if path not in self.files:
            raise NotFoundError(path)
        return self.files[path]

    def exists(self, path=None):
        return path in self.files

    def create_directory(self, path=None):
        self.dirs_created.add(path)

    def resolve_path(self, board, klass, subject, book_slug):
        return f"{board}/{klass}/{subject}/{book_slug}"

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
    """build_executor's own current-execution-report state is
    module-level and run-scoped, same idiom as artifact_manager's own
    current-build state -- reset before/after every test."""
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()
    execution_state.reset_current_execution_report()
    yield
    runtime_state.reset_runtime_state()
    build_state.reset_current_build()
    execution_state.reset_current_execution_report()


@pytest.fixture
def fake_storage(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(json_writer, "_storage_singleton", storage)
    return storage


def _structure(chapter_number, chapter_title, klass="Class_10", subject="Science", book_title="Book One"):
    return pdf_parser.ChapterStructure(
        filename=f"{chapter_number:02d}_ch.pdf",
        subject=subject,
        klass=klass,
        chapter_title=chapter_title,
        chapter_number=chapter_number,
        toc_matched=True,
        num_pages=1,
        lines=[],
        body_size=10.0,
        repeated=set(),
        topics=[],
        page_word_counts={},
        page_sizes={},
        language="en",
    )


class _BookCtx:
    def __init__(self, book_title="Book One"):
        self.book_title = book_title


# ---------------------------------------------------------------------------
# 1. ExecutionPlan
# ---------------------------------------------------------------------------

def test_generate_execution_plan_partitions_reuse_and_rebuild():
    decisions = [
        {"chapter_key": "a.json", "decision": "reuse", "reason": "already exists"},
        {"chapter_key": "b.json", "decision": "rebuild", "reason": "new chapter"},
    ]
    plan = generate_execution_plan(decisions, namespace="Book One")
    assert plan["execution_order"] == ["a.json", "b.json"]
    assert plan["reused_artifacts"] == ["a.json"]
    assert plan["rebuilt_artifacts"] == ["b.json"]
    assert plan["execution_reasons"]["a.json"] == "already exists"
    assert plan["summary"]["reused_count"] == 1
    assert plan["summary"]["rebuilt_count"] == 1
    assert plan["summary"]["total_considered"] == 2
    assert plan["summary"]["requires_execution"] is True
    assert plan["summary"]["is_full_reuse"] is False


def test_generate_execution_plan_is_deterministic():
    decisions = [
        {"chapter_key": "a.json", "decision": "reuse", "reason": "x"},
        {"chapter_key": "b.json", "decision": "rebuild", "reason": "y"},
    ]
    p1 = generate_execution_plan(decisions, namespace="Book One", generated_at="2026-01-01T00:00:00+00:00")
    p2 = generate_execution_plan(decisions, namespace="Book One", generated_at="2026-01-01T00:00:00+00:00")
    assert p1 == p2


def test_generate_execution_plan_rejects_malformed_decision():
    with pytest.raises(ExecutionPlanError):
        generate_execution_plan([{"chapter_key": "a.json", "decision": "maybe"}], namespace="Book One")
    with pytest.raises(ExecutionPlanError):
        generate_execution_plan([{"decision": "reuse"}], namespace="Book One")


def test_generate_execution_plan_never_mutates_input():
    decisions = [{"chapter_key": "a.json", "decision": "reuse", "reason": "x"}]
    original = [dict(d) for d in decisions]
    generate_execution_plan(decisions, namespace="Book One")
    assert decisions == original


def test_aggregate_execution_plan_concatenates_book_plans_in_order():
    book_a = generate_execution_plan(
        [{"chapter_key": "a1.json", "decision": "reuse", "reason": "r"}], namespace="Book A"
    )
    book_b = generate_execution_plan(
        [{"chapter_key": "b1.json", "decision": "rebuild", "reason": "r"}], namespace="Book B"
    )
    run_plan = aggregate_execution_plan([book_a, book_b])
    assert run_plan["execution_order"] == ["a1.json", "b1.json"]
    assert run_plan["reused_artifacts"] == ["a1.json"]
    assert run_plan["rebuilt_artifacts"] == ["b1.json"]
    assert run_plan["namespace"] == "<run>"


def test_aggregate_execution_plan_empty_is_full_reuse_false_and_no_errors():
    run_plan = aggregate_execution_plan([])
    assert run_plan["execution_order"] == []
    assert run_plan["summary"]["requires_execution"] is False
    assert run_plan["errors"] == []


# ---------------------------------------------------------------------------
# 2. ExecutionReport
# ---------------------------------------------------------------------------

def test_generate_execution_report_surfaces_plan_fields_verbatim():
    plan = generate_execution_plan(
        [
            {"chapter_key": "a.json", "decision": "reuse", "reason": "already exists"},
            {"chapter_key": "b.json", "decision": "rebuild", "reason": "new"},
        ],
        namespace="<run>",
    )
    report = generate_execution_report(plan, execution_duration_seconds=12.5)
    assert report["executed_artifacts"] == ["b.json"]
    assert report["reused_artifacts"] == ["a.json"]
    assert report["skipped_artifacts"] == []
    assert report["execution_order"] == ["a.json", "b.json"]
    assert report["execution_duration_seconds"] == 12.5
    assert report["execution_statistics"] == plan["summary"]
    assert report["errors"] == plan["errors"]


def test_generate_execution_report_requires_execution_order():
    with pytest.raises(ExecutionReportError):
        generate_execution_report({}, execution_duration_seconds=1.0)
    with pytest.raises(ExecutionReportError):
        generate_execution_report(None, execution_duration_seconds=1.0)


def test_generate_execution_report_duration_is_optional():
    plan = generate_execution_plan([], namespace="<run>")
    report = generate_execution_report(plan)
    assert report["execution_duration_seconds"] is None


# ---------------------------------------------------------------------------
# 3. execute_chapter() -- the actual pre-execution reuse gate
# ---------------------------------------------------------------------------

def test_execute_chapter_reuse_never_calls_process_chapter_fn(fake_storage, monkeypatch):
    structure = _structure(1, "Motion")
    monkeypatch.setattr(pdf_parser, "parse_chapter_pdf", lambda *a, **k: structure)

    # Pre-populate storage so is_already_extracted() reports True.
    out_path = json_writer.chapter_output_path(
        structure.klass, structure.subject, "book-one", structure.chapter_number,
        structure.chapter_title, output_root="books/book-one",
    )
    fake_storage.files[out_path] = {"already": "there"}

    calls = []

    def fake_process_chapter(*a, **k):
        calls.append((a, k))
        return "should-not-happen"

    decision = execute_chapter(
        pdf_path="irrelevant.pdf", book_ctx=_BookCtx("Book One"), chapter_order_fallback=1,
        use_vlm=False, page_batch_size=6, force=False, output_root="books/book-one",
        process_chapter_fn=fake_process_chapter,
    )

    assert decision["decision"] == "reuse"
    assert decision["output_path"] is None
    assert decision["chapter_key"] == out_path
    assert "already exists" in decision["reason"]
    assert calls == []  # the actual regression: process_chapter_fn was never invoked


def test_execute_chapter_rebuild_calls_process_chapter_fn_once(fake_storage, monkeypatch):
    structure = _structure(2, "Force and Laws")
    monkeypatch.setattr(pdf_parser, "parse_chapter_pdf", lambda *a, **k: structure)

    calls = []

    def fake_process_chapter(pdf_path, book_ctx, chapter_order_fallback, **kwargs):
        calls.append((pdf_path, chapter_order_fallback, kwargs))
        return "json_out/Class_10/Science/book-one/02_force-and-laws.json"

    decision = execute_chapter(
        pdf_path="ch02.pdf", book_ctx=_BookCtx("Book One"), chapter_order_fallback=2,
        use_vlm=True, page_batch_size=6, force=False, output_root="books/book-one",
        process_chapter_fn=fake_process_chapter,
    )

    assert decision["decision"] == "rebuild"
    assert decision["output_path"] == "json_out/Class_10/Science/book-one/02_force-and-laws.json"
    assert len(calls) == 1
    assert calls[0][0] == "ch02.pdf"
    assert calls[0][1] == 2
    assert calls[0][2]["use_vlm"] is True


def test_execute_chapter_force_true_rebuilds_even_if_already_extracted(fake_storage, monkeypatch):
    structure = _structure(3, "Gravitation")
    monkeypatch.setattr(pdf_parser, "parse_chapter_pdf", lambda *a, **k: structure)
    out_path = json_writer.chapter_output_path(
        structure.klass, structure.subject, "book-one", structure.chapter_number,
        structure.chapter_title, output_root="books/book-one",
    )
    fake_storage.files[out_path] = {"already": "there"}

    calls = []

    def fake_process_chapter(*a, **k):
        calls.append(1)
        return out_path

    decision = execute_chapter(
        pdf_path="ch03.pdf", book_ctx=_BookCtx("Book One"), chapter_order_fallback=3,
        use_vlm=False, page_batch_size=6, force=True, output_root="books/book-one",
        process_chapter_fn=fake_process_chapter,
    )
    assert decision["decision"] == "rebuild"
    assert len(calls) == 1


def test_execute_chapter_propagates_process_chapter_fn_exceptions(fake_storage, monkeypatch):
    """A chapter that genuinely fails to extract must still surface as a
    real failure to pipeline.process_all_pdfs()'s own per-chapter
    try/except -- execute_chapter() must never swallow it or silently
    reclassify it as 'reused'."""
    structure = _structure(4, "Work and Energy")
    monkeypatch.setattr(pdf_parser, "parse_chapter_pdf", lambda *a, **k: structure)

    def failing_process_chapter(*a, **k):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        execute_chapter(
            pdf_path="ch04.pdf", book_ctx=_BookCtx("Book One"), chapter_order_fallback=4,
            use_vlm=False, page_batch_size=6, force=False, output_root="books/book-one",
            process_chapter_fn=failing_process_chapter,
        )


# ---------------------------------------------------------------------------
# 4. aggregate_run_execution_report() -- run-level aggregation
# ---------------------------------------------------------------------------

def test_aggregate_run_execution_report_from_all_stats():
    book_a_plan = generate_execution_plan(
        [{"chapter_key": "a1.json", "decision": "reuse", "reason": "r"}], namespace="Book A"
    )
    book_b_plan = generate_execution_plan(
        [{"chapter_key": "b1.json", "decision": "rebuild", "reason": "r"}], namespace="Book B"
    )
    all_stats = [
        {"book_title": "Book A", "execution_plan": book_a_plan},
        {"book_title": "Book B", "execution_plan": book_b_plan},
    ]
    result = aggregate_run_execution_report(all_stats, execution_duration_seconds=5.0)
    assert set(result.keys()) == {"execution_plan", "execution_report"}
    assert result["execution_plan"]["execution_order"] == ["a1.json", "b1.json"]
    assert result["execution_report"]["execution_duration_seconds"] == 5.0
    assert result["execution_report"]["reused_artifacts"] == ["a1.json"]
    assert result["execution_report"]["executed_artifacts"] == ["b1.json"]


def test_aggregate_run_execution_report_tolerates_missing_execution_plan_key():
    """A book stats dict predating this integration (or a test double
    built against the pre-F3 shape) must not break aggregation."""
    all_stats = [{"book_title": "Legacy Book", "found": 1, "written": 1, "failed": 0}]
    result = aggregate_run_execution_report(all_stats)
    assert result["execution_plan"]["execution_order"] == []
    assert result["execution_report"]["errors"] == []


# ---------------------------------------------------------------------------
# 5. State lifecycle
# ---------------------------------------------------------------------------

def test_current_execution_report_state_lifecycle():
    assert execution_state.has_current_execution_report() is False
    assert execution_state.get_current_execution_report() is None

    report = generate_execution_report(generate_execution_plan([], namespace="<run>"))
    execution_state.set_current_execution_report(report)
    assert execution_state.has_current_execution_report() is True
    assert execution_state.get_current_execution_report() == report

    execution_state.reset_current_execution_report()
    assert execution_state.has_current_execution_report() is False
    assert execution_state.get_current_execution_report() is None


# ---------------------------------------------------------------------------
# 6. CompilerRuntime integration (runtime.py's _record_execution())
# ---------------------------------------------------------------------------

class _FakeBookOrchestrator:
    def __init__(self, books=None, raise_exc=None):
        self._books = books if books is not None else [
            {
                "found": 2, "written": 1, "failed": 0, "book_title": "Book One",
                "book_name": "Book One",
                "written_paths": ["json_out/Class_10/Science/book-one/02_ch.json"],
                "book_manifest_path": "json_out/Class_10/Science/book-one/_book_manifest.json",
                "execution_plan": generate_execution_plan(
                    [
                        {"chapter_key": "json_out/.../01_ch.json", "decision": "reuse", "reason": "already exists"},
                        {"chapter_key": "json_out/.../02_ch.json", "decision": "rebuild", "reason": "new"},
                    ],
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


def test_run_records_an_execution_report(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()

    assert execution_state.has_current_execution_report() is True
    report = execution_state.get_current_execution_report()
    assert report["reused_artifacts"] == ["json_out/.../01_ch.json"]
    assert report["executed_artifacts"] == ["json_out/.../02_ch.json"]
    # F2 and F3 must always agree on this run's own duration (see
    # runtime.py's _record_execution() docstring).
    build = build_state.get_current_build()
    assert report["execution_duration_seconds"] == build.execution_summary["duration_seconds"]


def test_run_records_an_execution_report_even_on_failure(monkeypatch, fake_storage):
    fake = _FakeBookOrchestrator(raise_exc=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    with pytest.raises(RuntimeError):
        rt.run()

    # Mirrors _record_build()'s own "a FAILED run still gets a record"
    # contract -- an empty run still gets a (empty) Execution Report.
    assert execution_state.has_current_execution_report() is True
    report = execution_state.get_current_execution_report()
    assert report["execution_order"] == []


def test_new_run_resets_previous_execution_report(fake_book_orchestrator, fake_storage):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()
    first_report = execution_state.get_current_execution_report()
    assert first_report is not None

    rt2 = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt2.run()
    second_report = execution_state.get_current_execution_report()
    # A fresh run still recorded a fresh (equal-shape, re-generated)
    # report -- state was reset then re-populated, never left stale.
    assert second_report is not None


def test_build_executor_failure_never_masks_a_successful_run(fake_book_orchestrator, fake_storage, monkeypatch):
    import build_executor.executor as build_executor_executor

    def _boom(*a, **k):
        raise RuntimeError("build_executor exploded")

    monkeypatch.setattr(build_executor_executor, "aggregate_run_execution_report", _boom)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()  # must not raise despite build_executor blowing up

    assert isinstance(result, list) and len(result) == 1
    # Phase F3's own bookkeeping failed silently -- state was reset at
    # the top of the run and never repopulated.
    assert execution_state.has_current_execution_report() is False


def test_run_return_shape_unchanged_by_phase_f3(fake_book_orchestrator, fake_storage):
    """Backward compatibility: run()'s own return value is exactly what
    the fake book_orchestrator returned, untouched by Phase F3."""
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    result = rt.run()
    assert result[0]["book_title"] == "Book One"
    assert result[0]["written"] == 1


# ---------------------------------------------------------------------------
# 7. Read-only guarantees
# ---------------------------------------------------------------------------

def test_execute_chapter_never_writes_via_storage_when_reusing(fake_storage, monkeypatch):
    """A 'reuse' decision must perform zero storage writes -- only the
    pre-existing existence check (a read) is performed."""
    structure = _structure(5, "Sound")
    monkeypatch.setattr(pdf_parser, "parse_chapter_pdf", lambda *a, **k: structure)
    out_path = json_writer.chapter_output_path(
        structure.klass, structure.subject, "book-one", structure.chapter_number,
        structure.chapter_title, output_root="books/book-one",
    )
    fake_storage.files[out_path] = {"already": "there"}
    files_before = dict(fake_storage.files)

    execute_chapter(
        pdf_path="ch05.pdf", book_ctx=_BookCtx("Book One"), chapter_order_fallback=5,
        use_vlm=False, page_batch_size=6, force=False, output_root="books/book-one",
        process_chapter_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")),
    )
    assert fake_storage.files == files_before


# ---------------------------------------------------------------------------
# 8. Real pipeline.process_all_pdfs() chapter-loop integration
# ---------------------------------------------------------------------------

def test_pipeline_process_all_pdfs_skips_reused_chapter_without_calling_process_chapter(
    tmp_path, fake_storage, monkeypatch
):
    """End-to-end regression through the REAL, modified
    pipeline.process_all_pdfs(): a chapter whose output JSON already
    exists must never reach pipeline.process_chapter() this run."""
    import pipeline

    pdf_dir = tmp_path / "book"
    pdf_dir.mkdir()
    ch1 = pdf_dir / "01_ch.pdf"
    ch2 = pdf_dir / "02_ch.pdf"
    ch1.write_bytes(b"%PDF-1.4 fake\n")
    ch2.write_bytes(b"%PDF-1.4 fake\n")

    structures = {
        str(ch1): _structure(1, "Chapter One"),
        str(ch2): _structure(2, "Chapter Two"),
    }
    monkeypatch.setattr(pipeline.pdf_parser, "parse_chapter_pdf",
                         lambda pdf_path, book_ctx, chapter_order_fallback, **k: structures[pdf_path])
    monkeypatch.setattr(pipeline.pdf_parser, "find_prelims_pdf", lambda paths: None)
    monkeypatch.setattr(pipeline.pdf_parser, "load_book_context", lambda prelims_path: pdf_parser.BookContext(
        book_title="Book One", subject="Science", klass="Class_10",
    ))

    # Pre-populate storage so chapter 1 looks already-extracted; chapter
    # 2 is genuinely new.
    out1 = json_writer.chapter_output_path(
        "Class_10", "Science", "book-one", 1, "Chapter One", output_root="books/book-one"
    )
    fake_storage.files[out1] = {"already": "there"}

    calls = []

    def fake_process_chapter(pdf_path, book_ctx, chapter_order_fallback, **kwargs):
        calls.append(pdf_path)
        return json_writer.chapter_output_path(
            "Class_10", "Science", "book-one", 2, "Chapter Two", output_root="books/book-one"
        )

    monkeypatch.setattr(pipeline, "process_chapter", fake_process_chapter)

    stats = pipeline.process_all_pdfs(
        use_vlm=False, page_batch_size=6, force=False,
        pdf_folder=str(pdf_dir), output_root="books/book-one",
        book_title_override="Book One",
    )

    # The actual regression: process_chapter was called for chapter 2
    # only -- chapter 1 was reused and never reached it.
    assert calls == [str(ch1) if False else str(ch2)] or calls == [str(ch2)]
    assert stats["found"] == 2
    assert stats["written"] == 1
    assert stats["reused_paths"] == [out1]
    assert stats["execution_plan"]["reused_artifacts"] == [out1]
    assert stats["execution_plan"]["summary"]["rebuilt_count"] == 1


def test_pipeline_process_all_pdfs_return_shape_backward_compatible(tmp_path, fake_storage, monkeypatch):
    """Every pre-Phase-F3 key (found/written/failed/book_title/
    written_paths/book_manifest_path) must still be present and
    correct -- Phase F3 only adds keys, never removes or renames any."""
    import pipeline

    pdf_dir = tmp_path / "book"
    pdf_dir.mkdir()
    ch1 = pdf_dir / "01_ch.pdf"
    ch1.write_bytes(b"%PDF-1.4 fake\n")

    structure = _structure(1, "Chapter One")
    monkeypatch.setattr(pipeline.pdf_parser, "parse_chapter_pdf",
                         lambda *a, **k: structure)
    monkeypatch.setattr(pipeline.pdf_parser, "find_prelims_pdf", lambda paths: None)
    monkeypatch.setattr(pipeline.pdf_parser, "load_book_context", lambda prelims_path: pdf_parser.BookContext(
        book_title="Book One", subject="Science", klass="Class_10",
    ))

    expected_path = json_writer.chapter_output_path(
        "Class_10", "Science", "book-one", 1, "Chapter One", output_root="books/book-one"
    )
    monkeypatch.setattr(pipeline, "process_chapter", lambda *a, **k: expected_path)

    stats = pipeline.process_all_pdfs(
        use_vlm=False, page_batch_size=6, force=False,
        pdf_folder=str(pdf_dir), output_root="books/book-one",
        book_title_override="Book One",
    )

    assert stats["found"] == 1
    assert stats["written"] == 1
    assert stats["failed"] == 0
    assert stats["book_title"] == "Book One"
    assert stats["written_paths"] == [expected_path]
    assert "execution_plan" in stats  # additive, doesn't break anything reading only the above


# ---------------------------------------------------------------------------
# 9. dependency_rebuild_order propagation (audit refinement: Phase E4's
#    already-computed rebuild_order, read via
#    incremental_compilation.state.get_current_incremental_compilation_plan(),
#    now flows through generate_execution_plan() ->
#    aggregate_execution_plan() -> generate_execution_report(), instead of
#    being silently dropped. No new computation anywhere below -- every
#    assertion is about propagation of an already-supplied value.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_incremental_compilation_state():
    """incremental_compilation's own module-level "current chapter's
    plan" slot is not touched by this file's existing _reset_state
    fixture (it belongs to Phase E4, not build_executor) -- reset it
    around every test in this file too, so a real chapter's plan set by
    one test can never leak into the next."""
    incremental_compilation_state.reset_incremental_compilation_state()
    yield
    incremental_compilation_state.reset_incremental_compilation_state()


def test_generate_execution_plan_passes_through_dependency_rebuild_order():
    decisions = [{"chapter_key": "a.json", "decision": "rebuild", "reason": "new"}]
    plan = generate_execution_plan(
        decisions, namespace="Book One",
        dependency_rebuild_order=["a.json", "b.json"],
    )
    assert plan["dependency_rebuild_order"] == ["a.json", "b.json"]


def test_generate_execution_plan_dependency_rebuild_order_defaults_empty():
    """Empty rebuild order behaves correctly: omitting the argument (the
    normal case for a book where every chapter was reused, so Phase E4
    never ran) must not raise and must produce an empty list, not None
    or a missing key."""
    plan = generate_execution_plan([], namespace="Book One")
    assert plan["dependency_rebuild_order"] == []


def test_aggregate_execution_plan_preserves_dependency_rebuild_order_across_books():
    """Multiple books aggregate correctly: each book's own
    dependency_rebuild_order is concatenated into the run-level plan, in
    book-processing order -- the same convention execution_order/
    reused_artifacts/rebuilt_artifacts already use one section up."""
    book_a = generate_execution_plan(
        [{"chapter_key": "a1.json", "decision": "rebuild", "reason": "r"}],
        namespace="Book A", dependency_rebuild_order=["a1.json"],
    )
    book_b = generate_execution_plan(
        [{"chapter_key": "b1.json", "decision": "rebuild", "reason": "r"}],
        namespace="Book B", dependency_rebuild_order=["b1.json", "b2.json"],
    )
    run_plan = aggregate_execution_plan([book_a, book_b])
    assert run_plan["dependency_rebuild_order"] == ["a1.json", "b1.json", "b2.json"]


def test_aggregate_execution_plan_dependency_rebuild_order_empty_when_no_book_has_one():
    """Reuse-only runs remain valid: a book plan with no
    dependency_rebuild_order (every chapter reused this run, so Phase E4
    never ran for this book) aggregates to an empty list at the run
    level, never None and never a KeyError."""
    book_a = generate_execution_plan(
        [{"chapter_key": "a1.json", "decision": "reuse", "reason": "already exists"}],
        namespace="Book A",
    )
    run_plan = aggregate_execution_plan([book_a])
    assert run_plan["dependency_rebuild_order"] == []
    assert run_plan["reused_artifacts"] == ["a1.json"]  # unrelated fields unaffected


def test_aggregate_execution_plan_explicit_argument_overrides_book_plans():
    """An explicit dependency_rebuild_order passed directly to
    aggregate_execution_plan() (mirroring generate_execution_plan()'s
    own "explicit argument wins" contract) takes precedence over
    whatever individual book plans carried."""
    book_a = generate_execution_plan(
        [{"chapter_key": "a1.json", "decision": "rebuild", "reason": "r"}],
        namespace="Book A", dependency_rebuild_order=["a1.json"],
    )
    run_plan = aggregate_execution_plan(
        [book_a], dependency_rebuild_order=["explicit.json"]
    )
    assert run_plan["dependency_rebuild_order"] == ["explicit.json"]


def test_generate_execution_report_surfaces_dependency_rebuild_order():
    plan = generate_execution_plan(
        [{"chapter_key": "a.json", "decision": "rebuild", "reason": "new"}],
        namespace="<run>", dependency_rebuild_order=["a.json"],
    )
    report = generate_execution_report(plan)
    assert report["dependency_rebuild_order"] == ["a.json"]


def test_generate_execution_report_dependency_rebuild_order_defaults_empty():
    plan = generate_execution_plan([], namespace="<run>")
    report = generate_execution_report(plan)
    assert report["dependency_rebuild_order"] == []


def test_pipeline_process_all_pdfs_propagates_e4_rebuild_order_for_rebuilt_chapter(
    tmp_path, fake_storage, monkeypatch
):
    """End-to-end regression through the REAL pipeline.process_all_pdfs():
    when a chapter is rebuilt, Phase E4's own rebuild_order (set on
    incremental_compilation.state by that chapter's own real
    process_chapter() call -- simulated here by the fake
    process_chapter standing in for the full Stage A-E5.2 pipeline, the
    same substitution every other pipeline-integration test in this
    file already makes) must reach this book's own ExecutionPlan
    unchanged -- no recomputation, just propagation of the existing
    value."""
    import pipeline

    pdf_dir = tmp_path / "book"
    pdf_dir.mkdir()
    ch1 = pdf_dir / "01_ch.pdf"
    ch1.write_bytes(b"%PDF-1.4 fake\n")

    structure = _structure(1, "Chapter One")
    monkeypatch.setattr(pipeline.pdf_parser, "parse_chapter_pdf", lambda *a, **k: structure)
    monkeypatch.setattr(pipeline.pdf_parser, "find_prelims_pdf", lambda paths: None)
    monkeypatch.setattr(pipeline.pdf_parser, "load_book_context", lambda prelims_path: pdf_parser.BookContext(
        book_title="Book One", subject="Science", klass="Class_10",
    ))

    expected_path = json_writer.chapter_output_path(
        "Class_10", "Science", "book-one", 1, "Chapter One", output_root="books/book-one"
    )

    def fake_process_chapter(pdf_path, book_ctx, chapter_order_fallback, **kwargs):
        # Stands in for the real process_chapter(), which would itself
        # call incremental_compilation.engine.plan_incremental_compilation()
        # and record its result via
        # incremental_compilation.state.set_current_incremental_compilation_plan()
        # -- reproduced here exactly, with a fixed rebuild_order, so this
        # test exercises F3's own propagation without re-running E4.
        incremental_compilation_state.set_current_incremental_compilation_plan(
            {"rebuild_order": ["node:a", "node:b"]}
        )
        return expected_path

    monkeypatch.setattr(pipeline, "process_chapter", fake_process_chapter)

    stats = pipeline.process_all_pdfs(
        use_vlm=False, page_batch_size=6, force=False,
        pdf_folder=str(pdf_dir), output_root="books/book-one",
        book_title_override="Book One",
    )

    assert stats["execution_plan"]["dependency_rebuild_order"] == ["node:a", "node:b"]


def test_pipeline_process_all_pdfs_reuse_only_run_has_empty_dependency_rebuild_order(
    tmp_path, fake_storage, monkeypatch
):
    """Reuse-only runs remain valid: when every chapter this run is
    reused, process_chapter() (and therefore Phase E4) never runs at
    all, so incremental_compilation.state's slot is never set -- this
    book's own ExecutionPlan must carry an empty dependency_rebuild_order
    rather than stale data from an earlier run/book, and process_chapter
    must never be called."""
    import pipeline

    pdf_dir = tmp_path / "book"
    pdf_dir.mkdir()
    ch1 = pdf_dir / "01_ch.pdf"
    ch1.write_bytes(b"%PDF-1.4 fake\n")

    structure = _structure(1, "Chapter One")
    monkeypatch.setattr(pipeline.pdf_parser, "parse_chapter_pdf", lambda *a, **k: structure)
    monkeypatch.setattr(pipeline.pdf_parser, "find_prelims_pdf", lambda paths: None)
    monkeypatch.setattr(pipeline.pdf_parser, "load_book_context", lambda prelims_path: pdf_parser.BookContext(
        book_title="Book One", subject="Science", klass="Class_10",
    ))

    out1 = json_writer.chapter_output_path(
        "Class_10", "Science", "book-one", 1, "Chapter One", output_root="books/book-one"
    )
    fake_storage.files[out1] = {"already": "there"}

    def fake_process_chapter(*a, **k):
        raise AssertionError("must not be called for a reused chapter")

    monkeypatch.setattr(pipeline, "process_chapter", fake_process_chapter)

    stats = pipeline.process_all_pdfs(
        use_vlm=False, page_batch_size=6, force=False,
        pdf_folder=str(pdf_dir), output_root="books/book-one",
        book_title_override="Book One",
    )

    assert stats["execution_plan"]["reused_artifacts"] == [out1]
    assert stats["execution_plan"]["dependency_rebuild_order"] == []


def test_run_records_dependency_rebuild_order_aggregated_across_books(fake_storage, monkeypatch):
    """CompilerRuntime.run() end to end: the final, persisted
    ExecutionReport (the only artifact any caller can retrieve via
    build_executor.state.get_current_execution_report() after a run)
    must carry the run-level dependency_rebuild_order, aggregated from
    each book's own stats["execution_plan"] -- proving the value
    survives all the way from a book's plan through run-level
    aggregation into the final report, not just at the plan layer."""
    books = [
        {
            "found": 1, "written": 1, "failed": 0, "book_title": "Book One",
            "book_name": "Book One",
            "written_paths": ["json_out/.../01_ch.json"],
            "book_manifest_path": None,
            "execution_plan": generate_execution_plan(
                [{"chapter_key": "json_out/.../01_ch.json", "decision": "rebuild", "reason": "new"}],
                namespace="Book One", dependency_rebuild_order=["book-one:ch01"],
            ),
        },
        {
            "found": 1, "written": 0, "failed": 0, "book_title": "Book Two",
            "book_name": "Book Two",
            "written_paths": [],
            "book_manifest_path": None,
            "execution_plan": generate_execution_plan(
                [{"chapter_key": "json_out/.../01_ch.json", "decision": "reuse", "reason": "already exists"}],
                namespace="Book Two",
            ),
        },
    ]
    fake = _FakeBookOrchestrator(books=books)
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False)
    rt.run()

    report = execution_state.get_current_execution_report()
    # Book Two never populated dependency_rebuild_order (reuse-only),
    # so only Book One's value survives into the run-level report.
    assert report["dependency_rebuild_order"] == ["book-one:ch01"]