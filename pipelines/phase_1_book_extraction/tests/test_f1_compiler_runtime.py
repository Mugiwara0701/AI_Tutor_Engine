"""
tests/test_f1_compiler_runtime.py — Phase F1: CompilerRuntime lifecycle
tests.

Two layers, same split test_book_orchestrator.py / test_book_orchestrator_
storage_gate.py already use one level down:

  * UNIT tests (most of this file) monkeypatch book_orchestrator itself
    (sys.modules["book_orchestrator"]) with a fake exposing only `run()`,
    so CompilerRuntime's own lifecycle/state/error-propagation logic is
    exercised in isolation from real PDF discovery, storage, and
    pipeline.process_all_pdfs().
  * INTEGRATION tests (bottom of this file) use the REAL, unmodified
    book_orchestrator.run() -> pipeline.process_all_pdfs() call chain,
    stubbing only the storage startup gate and pipeline module exactly
    the way tests/test_book_orchestrator_storage_gate.py already does,
    to prove CompilerRuntime's new cancel_check/progress_callback
    plumbing actually flows through the real, unmodified signatures
    end-to-end.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime import state as runtime_state  # noqa: E402
from runtime.context import RuntimeStatus  # noqa: E402
from runtime.exceptions import (  # noqa: E402
    RuntimeAlreadyRunningError,
    RuntimeNotRunningError,
    RuntimeShutDownError,
)
from runtime.runtime import CompilerRuntime  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    """Runtime state is run-scoped module-level state (see runtime/
    state.py's own module docstring) -- reset before and after every
    test, same idiom every other phase's own state-reset fixture in this
    test suite already uses (e.g. test_e5_2_incremental_compilation_
    finalization.py's _reset_incremental_compilation_finalization_state)."""
    runtime_state.reset_runtime_state()
    yield
    runtime_state.reset_runtime_state()


def _touch_pdf(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4 fake\n")


# ---------------------------------------------------------------------------
# Fake book_orchestrator -- unit-level isolation
# ---------------------------------------------------------------------------

class _FakeBookOrchestrator:
    """Stand-in for the real book_orchestrator module. Records every
    call CompilerRuntime makes into it and can be scripted to raise, to
    invoke cancel_check itself (simulating a cancellation being honored
    mid-run), or to invoke progress_callback per "book"."""

    def __init__(self, books=None, raise_exc=None, honor_cancel_after=None):
        self.calls = []
        self._books = books if books is not None else [
            {"found": 2, "written": 2, "failed": 0, "book_title": "Book One", "book_name": "Book One"},
        ]
        self._raise_exc = raise_exc
        self._honor_cancel_after = honor_cancel_after  # int index or None

    def run(self, use_vlm, page_batch_size, force, pdf_input_folder=None,
            cancel_check=None, progress_callback=None):
        self.calls.append(dict(
            use_vlm=use_vlm, page_batch_size=page_batch_size, force=force,
            pdf_input_folder=pdf_input_folder,
            cancel_check_provided=cancel_check is not None,
            progress_callback_provided=progress_callback is not None,
        ))
        if self._raise_exc is not None:
            raise self._raise_exc

        results = []
        for i, book_stats in enumerate(self._books):
            if cancel_check is not None and cancel_check():
                break
            if self._honor_cancel_after is not None and i == self._honor_cancel_after and cancel_check is not None:
                # Simulate: this book's own run just requested cancellation
                # (e.g. runtime.cancel() was called by another thread while
                # this book was processing) -- honored at the NEXT book
                # boundary in a real run, but for this fake we just stop
                # right here after reporting this book's stats.
                results.append(dict(book_stats))
                if progress_callback is not None:
                    progress_callback(book_stats)
                break
            results.append(dict(book_stats))
            if progress_callback is not None:
                progress_callback(book_stats)
        return results


@pytest.fixture
def fake_book_orchestrator(monkeypatch):
    fake = _FakeBookOrchestrator()
    monkeypatch.setitem(sys.modules, "book_orchestrator", fake)
    return fake


# ---------------------------------------------------------------------------
# 1. Runtime lifecycle / status()
# ---------------------------------------------------------------------------

def test_initial_status_is_idle():
    rt = CompilerRuntime(use_vlm=False)
    snap = rt.status()
    assert snap["status"] == RuntimeStatus.IDLE
    assert snap["context"] is None
    assert snap["error"] is None
    assert snap["progress"]["chapters_written"] == 0


def test_run_transitions_to_completed_on_success(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=True, pdf_input_folder="/pdf_in")
    result = rt.run()

    assert result == fake_book_orchestrator._books
    snap = rt.status()
    assert snap["status"] == RuntimeStatus.COMPLETED
    assert snap["context"] == {
        "use_vlm": False, "page_batch_size": 6, "force": True, "pdf_input_folder": "/pdf_in",
    }
    assert snap["progress"]["chapters_written"] == 2
    assert snap["progress"]["chapters_failed"] == 0
    assert snap["progress"]["books_completed"] == 1
    assert snap["error"] is None


def test_run_passes_execution_context_and_hooks_to_book_orchestrator(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=True, page_batch_size=4, force=False, pdf_input_folder="/x")
    rt.run()

    call = fake_book_orchestrator.calls[0]
    assert call["use_vlm"] is True
    assert call["page_batch_size"] == 4
    assert call["force"] is False
    assert call["pdf_input_folder"] == "/x"
    # Phase F1's cancellation/progress-reporting hooks must actually be
    # wired into the single orchestration call site.
    assert call["cancel_check_provided"] is True
    assert call["progress_callback_provided"] is True


# ---------------------------------------------------------------------------
# 2. Runtime state (F0 §12-mirroring slots) reflected via status()
# ---------------------------------------------------------------------------

def test_progress_reports_current_book_as_each_book_completes(fake_book_orchestrator):
    fake_book_orchestrator._books = [
        {"found": 1, "written": 1, "failed": 0, "book_title": "A", "book_name": "A"},
        {"found": 1, "written": 0, "failed": 1, "book_title": "B", "book_name": "B"},
    ]
    seen_books = []

    def observer(stats):
        seen_books.append(stats["book_name"])

    rt = CompilerRuntime(use_vlm=False, progress_callback=observer)
    rt.run()

    assert seen_books == ["A", "B"]
    snap = rt.status()
    assert snap["progress"]["current_book"] == "B"
    assert snap["progress"]["chapters_written"] == 1
    assert snap["progress"]["chapters_failed"] == 1


def test_broken_progress_callback_does_not_abort_the_run(fake_book_orchestrator):
    def bad_observer(stats):
        raise ValueError("observer is broken")

    rt = CompilerRuntime(use_vlm=False, progress_callback=bad_observer)
    result = rt.run()  # must not raise

    assert result == fake_book_orchestrator._books
    assert rt.status()["status"] == RuntimeStatus.COMPLETED


# ---------------------------------------------------------------------------
# 3. run() re-entrancy guard
# ---------------------------------------------------------------------------

def test_run_raises_if_already_running(monkeypatch):
    """Simulates a re-entrant run() call (e.g. a caller invoking run()
    again from a progress_callback) by having the fake orchestrator call
    back into rt.run() itself."""
    rt = CompilerRuntime(use_vlm=False)

    class _ReentrantFake:
        def run(self, **kwargs):
            with pytest.raises(RuntimeAlreadyRunningError):
                rt.run()
            return [{"found": 0, "written": 0, "failed": 0, "book_title": "x"}]

    monkeypatch.setitem(sys.modules, "book_orchestrator", _ReentrantFake())
    rt.run()  # outer call succeeds; inner call above already asserted it raises
    assert rt.status()["status"] == RuntimeStatus.COMPLETED


# ---------------------------------------------------------------------------
# 4. resume()
# ---------------------------------------------------------------------------

def test_resume_before_any_run_raises_not_running(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False)
    with pytest.raises(RuntimeNotRunningError):
        rt.resume()


def test_resume_forces_force_false_regardless_of_constructor_force(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False, force=True)
    rt.run()
    assert fake_book_orchestrator.calls[0]["force"] is True

    rt.resume()
    # resume() must reuse pipeline.py's own existing is_already_extracted()/
    # force=False skip logic -- Phase F1 introduces no new resume
    # mechanism of its own.
    assert fake_book_orchestrator.calls[1]["force"] is False


def test_resume_works_after_a_completed_run(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False)
    rt.run()
    assert rt.status()["status"] == RuntimeStatus.COMPLETED
    rt.resume()
    assert rt.status()["status"] == RuntimeStatus.COMPLETED
    assert len(fake_book_orchestrator.calls) == 2


# ---------------------------------------------------------------------------
# 5. cancel()
# ---------------------------------------------------------------------------

def test_cancel_when_not_running_is_a_noop(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False)
    assert rt.cancel() is False
    assert rt.status()["status"] == RuntimeStatus.IDLE


def test_cancel_honored_between_books_marks_run_cancelled(fake_book_orchestrator):
    fake_book_orchestrator._books = [
        {"found": 1, "written": 1, "failed": 0, "book_title": "A", "book_name": "A"},
        {"found": 1, "written": 1, "failed": 0, "book_title": "B", "book_name": "B"},
        {"found": 1, "written": 1, "failed": 0, "book_title": "C", "book_name": "C"},
    ]
    rt = CompilerRuntime(use_vlm=False)

    # Cancel as soon as the first book's progress is reported -- this
    # exercises the real cooperative-cancellation path: the SAME
    # cancel_check callable CompilerRuntime handed to book_orchestrator.run()
    # is what the fake orchestrator consults before book 2.
    def observer(stats):
        if stats["book_name"] == "A":
            rt.cancel()

    rt._progress_callback = observer
    result = rt.run()

    assert [b["book_name"] for b in result] == ["A"]
    assert rt.status()["status"] == RuntimeStatus.CANCELLED


# ---------------------------------------------------------------------------
# 6. Error propagation
# ---------------------------------------------------------------------------

def test_run_error_propagates_and_is_recorded_in_status(monkeypatch):
    class _FailingFake:
        def run(self, **kwargs):
            raise RuntimeError("simulated catastrophic failure")

    monkeypatch.setitem(sys.modules, "book_orchestrator", _FailingFake())
    rt = CompilerRuntime(use_vlm=False)

    with pytest.raises(RuntimeError, match="simulated catastrophic failure"):
        rt.run()

    snap = rt.status()
    assert snap["status"] == RuntimeStatus.FAILED
    assert snap["error"] == "simulated catastrophic failure"


def test_failed_run_can_be_resumed(monkeypatch):
    calls = {"n": 0}

    class _FlakyFake:
        def run(self, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")
            return [{"found": 1, "written": 1, "failed": 0, "book_title": "ok"}]

    monkeypatch.setitem(sys.modules, "book_orchestrator", _FlakyFake())
    rt = CompilerRuntime(use_vlm=False)

    with pytest.raises(RuntimeError):
        rt.run()
    assert rt.status()["status"] == RuntimeStatus.FAILED

    result = rt.resume()
    assert result[0]["book_title"] == "ok"
    assert rt.status()["status"] == RuntimeStatus.COMPLETED


# ---------------------------------------------------------------------------
# 7. shutdown()
# ---------------------------------------------------------------------------

def test_shutdown_blocks_run_resume_and_cancel(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False)
    rt.run()
    rt.shutdown()

    assert rt.status()["status"] == RuntimeStatus.SHUT_DOWN
    with pytest.raises(RuntimeShutDownError):
        rt.run()
    with pytest.raises(RuntimeShutDownError):
        rt.resume()
    with pytest.raises(RuntimeShutDownError):
        rt.cancel()


def test_shutdown_is_idempotent(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False)
    rt.shutdown()
    rt.shutdown()  # must not raise
    assert rt.status()["status"] == RuntimeStatus.SHUT_DOWN


def test_shutdown_clears_progress_but_keeps_shut_down_status(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False)
    rt.run()
    assert rt.status()["progress"]["chapters_written"] == 2

    rt.shutdown()
    snap = rt.status()
    assert snap["status"] == RuntimeStatus.SHUT_DOWN
    assert snap["progress"]["chapters_written"] == 0
    assert snap["context"] is None


# ---------------------------------------------------------------------------
# 8. Read-only status() / determinism
# ---------------------------------------------------------------------------

def test_status_snapshot_mutation_does_not_affect_internal_state(fake_book_orchestrator):
    rt = CompilerRuntime(use_vlm=False)
    rt.run()

    snap = rt.status()
    snap["progress"]["chapters_written"] = 99999
    snap["status"] = "TAMPERED"

    fresh = rt.status()
    assert fresh["progress"]["chapters_written"] == 2
    assert fresh["status"] == RuntimeStatus.COMPLETED


def test_two_runtimes_given_identical_inputs_reach_identical_status(monkeypatch):
    """Determinism: same fake orchestrator behavior -> same aggregated
    status(), independent of instance."""
    def make_fake():
        return _FakeBookOrchestrator(books=[
            {"found": 3, "written": 3, "failed": 0, "book_title": "X", "book_name": "X"},
        ])

    monkeypatch.setitem(sys.modules, "book_orchestrator", make_fake())
    rt1 = CompilerRuntime(use_vlm=False, page_batch_size=6)
    rt1.run()
    snap1 = rt1.status()

    monkeypatch.setitem(sys.modules, "book_orchestrator", make_fake())
    rt2 = CompilerRuntime(use_vlm=False, page_batch_size=6)
    rt2.run()
    snap2 = rt2.status()

    assert snap1 == snap2


# ---------------------------------------------------------------------------
# 9. Integration -- real book_orchestrator.run(), only storage/pipeline stubbed
# ---------------------------------------------------------------------------

@pytest.fixture
def _stub_storage_startup_gate(monkeypatch):
    import book_orchestrator
    monkeypatch.setattr(book_orchestrator, "_ensure_storage_ready", lambda: None)
    monkeypatch.setattr(book_orchestrator.json_writer, "set_storage", lambda storage: None)


class _FakePipelineModule:
    """Exact same shape as tests/test_book_orchestrator.py's own
    _FakePipeline, extended to accept Phase F1's new, additive
    cancel_check keyword -- proving the real (unmodified in substance)
    book_orchestrator.run()/process_book() correctly forward it only
    when CompilerRuntime supplies one."""
    def __init__(self):
        self.calls = []

    def process_all_pdfs(self, use_vlm, page_batch_size, force, pdf_folder=None,
                          output_root=None, book_title_override=None, cancel_check=None,
                          **_additive_kwargs):
        self.calls.append(dict(pdf_folder=pdf_folder, book_title_override=book_title_override,
                                cancel_check_provided=cancel_check is not None))
        return {"found": 1, "written": 1, "failed": 0, "book_title": book_title_override or "untitled"}


def test_integration_runtime_drives_real_book_orchestrator(tmp_path, _stub_storage_startup_gate, monkeypatch):
    pdf_in = tmp_path / "pdf_in"
    _touch_pdf(str(pdf_in / "Class_11_Economics" / "lhat101.pdf"))

    fake_pipeline = _FakePipelineModule()
    monkeypatch.setitem(sys.modules, "pipeline", fake_pipeline)

    rt = CompilerRuntime(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=str(pdf_in))
    result = rt.run()

    assert len(result) == 1
    assert result[0]["book_title"] == "Class_11_Economics"
    assert fake_pipeline.calls[0]["cancel_check_provided"] is True  # F1's hook really reaches pipeline.py
    assert rt.status()["status"] == RuntimeStatus.COMPLETED
    assert rt.status()["progress"]["chapters_written"] == 1


def test_integration_no_books_found_completes_cleanly(tmp_path, _stub_storage_startup_gate, monkeypatch):
    empty_pdf_in = tmp_path / "pdf_in"
    empty_pdf_in.mkdir()

    fake_pipeline = _FakePipelineModule()
    monkeypatch.setitem(sys.modules, "pipeline", fake_pipeline)

    rt = CompilerRuntime(use_vlm=False, pdf_input_folder=str(empty_pdf_in))
    result = rt.run()

    assert result == []
    assert rt.status()["status"] == RuntimeStatus.COMPLETED
    assert fake_pipeline.calls == []


# ---------------------------------------------------------------------------
# 10. Backward compatibility of the additive pipeline.py/book_orchestrator.py
#     changes (the fixed-signature fakes below deliberately do NOT declare
#     cancel_check/progress_callback, exactly like the ones already in
#     tests/test_book_orchestrator.py and tests/test_book_orchestrator_
#     storage_gate.py -- if the additive parameters were not truly
#     optional/conditional, calling through them would raise TypeError).
# ---------------------------------------------------------------------------

def test_book_orchestrator_process_book_still_works_without_cancel_check(monkeypatch):
    import book_orchestrator

    class _OldStylePipeline:
        def process_all_pdfs(self, use_vlm, page_batch_size, force, pdf_folder=None,
                              output_root=None, book_title_override=None):
            return {"found": 1, "written": 1, "failed": 0, "book_title": book_title_override}

    monkeypatch.setitem(sys.modules, "pipeline", _OldStylePipeline())
    book = book_orchestrator.Book(name="Legacy_Book", pdf_folder="/pdf_in/Legacy_Book", output_root=None)

    # No cancel_check passed -- must behave exactly as it did before Phase F1.
    stats = book_orchestrator.process_book(book, use_vlm=False, page_batch_size=6, force=False)
    assert stats["written"] == 1