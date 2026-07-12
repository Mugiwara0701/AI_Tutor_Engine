"""
runtime/runtime.py — Phase F1: CompilerRuntime, the single execution
entry point F0 §11 mandates.

    CompilerRuntime
        run()
        resume()
        cancel()
        status()
        shutdown()

WHAT THIS CLASS IS: a thin lifecycle wrapper around the orchestration
that already exists in this codebase -- book_orchestrator.run(), which
already does "discover books -> for each book -> pipeline.process_all_pdfs()
-> pipeline.process_chapter() -> every compiler/knowledge_graph/
validation/build_metadata/dependency_graph/change_detection/
incremental_* phase in sequence" (see book_orchestrator.py's own module
docstring). Phase F1 does NOT re-implement any of that sequencing --
CompilerRuntime.run() makes exactly one call into book_orchestrator.run()
and lets it do everything it already does. What Phase F1 adds on top:

  * a real lifecycle (RuntimeStatus: IDLE -> RUNNING -> COMPLETED /
    CANCELLED / FAILED, plus SHUT_DOWN), backed by runtime/state.py
  * status() introspection at any time, including mid-run from another
    thread
  * cooperative cancel() (see the "COOPERATIVE CANCELLATION" section
    below for exactly what this can and cannot interrupt)
  * resume(), which reuses pipeline.py's own existing
    is_already_extracted()/force=False chapter-skip logic -- Phase F1
    introduces no new resume mechanism of its own, per F0 §13's "Phase F
    MUST NOT ... redesign previous phases"
  * error propagation: any exception book_orchestrator.run() lets
    through (e.g. a storage-migration failure -- see book_orchestrator.
    _ensure_storage_ready()'s own docstring on why that one is never
    caught internally) is recorded into runtime/state.py (status ->
    FAILED, last_error set) AND re-raised, unchanged, to run()'s caller.
    CompilerRuntime never swallows an error silently -- status() lets a
    caller *observe* the failure without requiring them to have wrapped
    run() in their own try/except, but the exception itself still
    propagates exactly as it would have if book_orchestrator.run() had
    been called directly.

WHAT THIS CLASS DELIBERATELY DOES NOT DO (F0 §4 / this task's own "PHASE
F1 DOES NOT OWN" section):
  * no Input Manifest, no persistence, no artifact loading/saving (F2)
  * no build gating / "should this even run" decision (F3)
  * no caching (F4)
  * no Compiler Build packaging (F5)
  * no PDF parsing, OCR, Stage A-E extraction, compiler/knowledge-graph/
    validation/dependency-graph/change-detection/incremental-* logic of
    its own -- all of that remains exactly where it already lived,
    inside pipeline.py and the phase packages it calls

COOPERATIVE CANCELLATION -- READ BEFORE RELYING ON cancel(): Python
functions here run synchronously, single-threaded, and
book_orchestrator.run()/pipeline.process_all_pdfs() are ordinary blocking
calls with no preemption. cancel() sets a flag this instance's run()
passed down as `cancel_check` to book_orchestrator.run() (which checks it
once before each book) and pipeline.process_all_pdfs() (which checks it
once before each chapter within the book currently running) -- see both
functions' own cancel_check docstrings. That means: cancel() can only be
observed *between* one chapter finishing and the next starting, or
between one book finishing and the next starting. It CANNOT interrupt a
single chapter already in the middle of process_chapter() (OCR/VLM/
compiler/knowledge-graph/... work already underway for that one chapter
always runs to completion). If a caller wants cancel() to actually take
effect while run() is executing, run() must be called from a different
thread than the one that calls cancel() -- calling both from the same,
single thread means cancel() can never run until run() has already
returned, which is too late to matter.

Not thread-safe beyond that one cancel()-from-another-thread pattern --
same explicit design note as every module this mirrors (compiler/
state.py, knowledge_graph/state.py, ...): one CompilerRuntime instance
manages one build at a time.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from config import DEFAULT_PAGE_BATCH_SIZE

from . import state as runtime_state
from .context import ExecutionContext, RuntimeStatus
from .exceptions import (
    RuntimeAlreadyRunningError,
    RuntimeNotRunningError,
    RuntimeShutDownError,
)

logger = logging.getLogger("ncert_pipeline.runtime")


class CompilerRuntime:
    """F0 §11's single execution entry point. See module docstring for
    the full contract; this docstring covers construction only.

    Every keyword argument here is exactly one book_orchestrator.run()/
    pipeline.process_all_pdfs() already accepts -- Phase F1 introduces no
    new configuration surface, it only captures these into an
    ExecutionContext (runtime/context.py) once per run() so status() can
    report what a build executed with.
    """

    def __init__(self, use_vlm: bool = True, page_batch_size: int = DEFAULT_PAGE_BATCH_SIZE,
                 force: bool = False, pdf_input_folder: Optional[str] = None,
                 progress_callback: Optional[Callable[[dict], None]] = None) -> None:
        self._use_vlm = use_vlm
        self._page_batch_size = page_batch_size
        self._force = force
        self._pdf_input_folder = pdf_input_folder
        self._progress_callback = progress_callback
        self._cancel_requested = False
        self._is_shut_down = False

    # -- internal helpers -----------------------------------------------

    def _check_cancel(self) -> bool:
        """The `cancel_check` callable passed down into
        book_orchestrator.run()/pipeline.process_all_pdfs() -- see module
        docstring's COOPERATIVE CANCELLATION section."""
        return self._cancel_requested

    def _execute(self, context: ExecutionContext) -> List[Dict[str, Any]]:
        """Shared body of run() and resume(): reset runtime state for
        this new build, delegate entirely to book_orchestrator.run() (the
        one and only orchestration call site -- see module docstring),
        and translate the outcome into runtime/state.py + this
        instance's own bookkeeping. Both run() and resume() differ only
        in what ExecutionContext they build before calling this.

        Phase F2 (artifact_manager/) integration: immediately after
        book_orchestrator.run() returns (success, cancellation, OR
        failure -- a FAILED run still gets a Build so build history/
        discovery can show it failed), this builds a Build object, that
        Build's own Build Manifest, persists both via the exact same
        already-authenticated storage instance book_orchestrator.run()'s
        own startup gate constructed (reused through modules.json_writer.
        get_storage(), never a second OneDriveStorage()), and records it
        via artifact_manager.state.set_current_build(). This does NOT
        change what run()/resume() themselves return -- they still
        return `all_stats` unchanged (F0 §13's "preserve public APIs" /
        this task's own backward-compatibility requirement) -- the Build
        is reached via artifact_manager.state.get_current_build()
        instead. A failure inside Phase F2's own bookkeeping (a
        persistence error, say) is logged and swallowed, never allowed to
        mask the run's own real outcome -- same "a broken observer must
        never abort the run" principle _on_book_progress() already
        applies to progress_callback."""
        import book_orchestrator  # local import: same reason pipeline.py/
        # book_orchestrator.py already use local imports for each other --
        # avoids a circular import at module load time (book_orchestrator
        # imports pipeline; runtime must not force an import-order
        # dependency on either at package-load time).

        runtime_state.reset_runtime_state()
        runtime_state.set_current_context(context)
        runtime_state.set_current_status(RuntimeStatus.RUNNING)
        self._cancel_requested = False
        started_at = datetime.now(timezone.utc)

        try:
            from artifact_manager import state as build_state
            build_state.reset_current_build()
        except Exception:
            logger.exception(
                "artifact_manager: failed to reset current-build state at "
                "the start of this run; continuing (this run's own Build "
                "will still overwrite it once recorded)."
            )

        try:
            from build_executor import state as execution_state
            execution_state.reset_current_execution_report()
        except Exception:
            logger.exception(
                "build_executor: failed to reset current-execution-report "
                "state at the start of this run; continuing (this run's "
                "own Execution Report will still overwrite it once "
                "recorded)."
            )

        try:
            all_stats = book_orchestrator.run(
                use_vlm=context.use_vlm,
                page_batch_size=context.page_batch_size,
                force=context.force,
                pdf_input_folder=context.pdf_input_folder,
                cancel_check=self._check_cancel,
                progress_callback=self._on_book_progress,
            )
        except Exception as exc:
            runtime_state.set_current_error(str(exc))
            runtime_state.set_current_status(RuntimeStatus.FAILED)
            self._record_build(context, RuntimeStatus.FAILED, [], str(exc), started_at)
            self._record_execution([])
            raise

        books_completed = len(all_stats)
        chapters_written = sum(s.get("written", 0) for s in all_stats)
        chapters_failed = sum(s.get("failed", 0) for s in all_stats)
        runtime_state.set_current_progress(
            books_completed=books_completed,
            chapters_written=chapters_written,
            chapters_failed=chapters_failed,
        )

        if self._cancel_requested:
            runtime_state.set_current_status(RuntimeStatus.CANCELLED)
        else:
            runtime_state.set_current_status(RuntimeStatus.COMPLETED)
        self._record_build(context, runtime_state.get_current_status(), all_stats, None, started_at)
        self._record_execution(all_stats)
        return all_stats

    def _record_build(
        self,
        context: ExecutionContext,
        status: str,
        all_stats: List[Dict[str, Any]],
        error: Optional[str],
        started_at: datetime,
    ) -> None:
        """Phase F2 integration point: builds, manifests, and persists
        this run's Build -- see _execute()'s own docstring above for the
        full contract. Never raises: any failure here is logged and
        swallowed so Phase F2's own bookkeeping can never turn a
        successful (or already-failed, already-recorded) run into a
        second, different failure for run()'s caller."""
        try:
            from artifact_manager import state as build_state
            from artifact_manager.build import create_build
            from artifact_manager.manifest import generate_build_manifest, attach_artifact_locations
            from artifact_manager.persistence import (
                build_record_path,
                manifest_record_path,
                persist_build,
            )
            from modules import json_writer

            build = create_build(
                context=context, status=status, all_stats=all_stats,
                error=error, started_at=started_at,
            )
            manifest = generate_build_manifest(build)

            chapter_json_paths: List[str] = []
            book_manifest_paths: List[str] = []
            for book_stats in all_stats:
                chapter_json_paths.extend(book_stats.get("written_paths") or [])
                if book_stats.get("book_manifest_path"):
                    book_manifest_paths.append(book_stats["book_manifest_path"])

            # build_record_path()/manifest_record_path() are pure
            # functions of build.build_id (see persistence.py) -- they
            # can be computed up front, before persistence itself runs,
            # so the manifest attached to `build` and the manifest
            # actually written to storage below are the exact same
            # dict, byte for byte. (Previously these paths were only
            # known from persist_build()'s own return value, which
            # required attaching + persisting once, then attaching a
            # *second*, never-persisted copy with the real paths --
            # leaving the on-disk manifest permanently missing its own
            # location. See F2 audit finding F2-H1.)
            manifest = attach_artifact_locations(
                manifest, chapter_json_paths=chapter_json_paths, book_manifest_paths=book_manifest_paths,
                build_record_path=build_record_path(build.build_id),
                manifest_record_path=manifest_record_path(build.build_id),
            )
            build = build.with_manifest(manifest)

            storage = json_writer.get_storage()
            persist_build(storage, build.to_dict(), manifest)

            build_state.set_current_build(build)
        except Exception:
            logger.exception(
                "artifact_manager: failed to build/manifest/persist this "
                "run's Build; run()'s own result/status is unaffected."
            )

    def _record_execution(
        self,
        all_stats: List[Dict[str, Any]],
    ) -> None:
        """Phase F3 integration point: aggregates every book's own
        ExecutionPlan (each book's stats dict's additive
        `"execution_plan"` key -- see pipeline.process_all_pdfs()'s own
        integration of build_executor.executor.execute_chapter()) into
        one run-level ExecutionPlan + ExecutionReport and records it via
        build_executor.state.set_current_execution_report(). Called
        immediately after _record_build() above, on both the failure
        path (with an empty `all_stats`, mirroring _record_build()'s own
        "a FAILED run still gets a record" contract) and the success/
        cancelled path.

        Never raises: any failure here is logged and swallowed, same
        "a broken observer must never abort the run" principle
        _record_build() itself already applies -- Phase F3's own
        bookkeeping can never turn a successful (or already-recorded)
        run into a second, different failure for run()'s caller."""
        try:
            from artifact_manager import state as build_state
            from build_executor import state as execution_state
            from build_executor.executor import aggregate_run_execution_report

            # This run's own duration, read verbatim off the Build Phase
            # F2 just recorded (create_build()'s own execution_summary)
            # -- never independently re-timed here, so Phase F3's own
            # reported duration always agrees with Phase F2's (see
            # report.py's own module docstring). Falls back to None if
            # Phase F2's own bookkeeping failed this run (see
            # _record_build()'s own "never raises" contract) -- an
            # Execution Report with an unknown duration is still valid
            # (ExecutionReport.execution_duration_seconds is Optional).
            current_build = build_state.get_current_build()
            duration_seconds = None
            if current_build is not None:
                duration_seconds = (current_build.execution_summary or {}).get(
                    "duration_seconds"
                )

            result = aggregate_run_execution_report(
                all_stats, execution_duration_seconds=duration_seconds
            )
            execution_state.set_current_execution_report(result["execution_report"])
        except Exception:
            logger.exception(
                "build_executor: failed to aggregate/record this run's "
                "Execution Report; run()'s own result/status is unaffected."
            )

    def _on_book_progress(self, book_stats: dict) -> None:
        """Forwarded as book_orchestrator.run()'s own progress_callback:
        updates runtime/state.py's progress snapshot after each book
        finishes, then relays the same stats dict to this instance's own
        caller-supplied progress_callback, if any -- see F0 §3's
        "progress reporting" responsibility."""
        runtime_state.set_current_progress(current_book=book_stats.get("book_name"))
        if self._progress_callback is not None:
            try:
                self._progress_callback(book_stats)
            except Exception:
                logger.exception(
                    "CompilerRuntime's progress_callback raised for book '%s'; "
                    "ignoring (a broken progress observer must never abort the run).",
                    book_stats.get("book_name"),
                )

    # -- lifecycle API (F0 §11) ------------------------------------------

    def run(self) -> List[Dict[str, Any]]:
        """Starts a fresh build using this instance's own constructor
        arguments. Raises RuntimeShutDownError if shutdown() has already
        been called, or RuntimeAlreadyRunningError if this instance is
        already RUNNING. See module docstring for the full error-
        propagation and cancellation contract."""
        if self._is_shut_down:
            raise RuntimeShutDownError()
        status = runtime_state.get_current_status()
        if status == RuntimeStatus.RUNNING:
            raise RuntimeAlreadyRunningError(status)

        context = ExecutionContext(
            use_vlm=self._use_vlm, page_batch_size=self._page_batch_size,
            force=self._force, pdf_input_folder=self._pdf_input_folder,
        )
        return self._execute(context)

    def resume(self) -> List[Dict[str, Any]]:
        """Resumes an interrupted or previously-completed build.

        Phase F1 introduces no new resume mechanism -- this reuses
        exactly the resumability pipeline.py already has: json_writer.
        is_already_extracted() causes process_chapter() to skip any
        chapter whose output JSON already exists, whenever force=False.
        resume() is therefore implemented as "run the same orchestration
        again with force forced to False" (regardless of what `force`
        this instance was constructed with), so a build that was
        CANCELLED or FAILED partway through -- or one that already
        COMPLETED -- picks up only the chapters not yet written, exactly
        as re-running `python pipeline.py` without --force already does
        today.

        Raises RuntimeShutDownError if shutdown() has already been
        called, RuntimeAlreadyRunningError if this instance is already
        RUNNING, or RuntimeNotRunningError if run() has never been
        called on this instance (status is still IDLE -- nothing to
        resume).
        """
        if self._is_shut_down:
            raise RuntimeShutDownError()
        status = runtime_state.get_current_status()
        if status == RuntimeStatus.RUNNING:
            raise RuntimeAlreadyRunningError(status)
        if status == RuntimeStatus.IDLE:
            raise RuntimeNotRunningError(status)

        context = ExecutionContext(
            use_vlm=self._use_vlm, page_batch_size=self._page_batch_size,
            force=False, pdf_input_folder=self._pdf_input_folder,
        )
        return self._execute(context)

    def cancel(self) -> bool:
        """Requests cooperative cancellation of an in-progress run() --
        see module docstring's COOPERATIVE CANCELLATION section for
        exactly when this is and isn't observed. Idempotent and
        non-raising when nothing is running: returns False and does
        nothing if status is not currently RUNNING (there is nothing to
        cancel -- this mirrors this codebase's own has_current_*()/
        get_current_*() convention of "an inapplicable call is a normal
        state, not an error" wherever raising isn't essential). Returns
        True once a running build has been signaled.

        Raises RuntimeShutDownError if shutdown() has already been
        called (a shut-down instance has nothing to cancel and will
        never run again).
        """
        if self._is_shut_down:
            raise RuntimeShutDownError()
        if runtime_state.get_current_status() != RuntimeStatus.RUNNING:
            return False
        self._cancel_requested = True
        runtime_state.set_current_status(RuntimeStatus.CANCEL_REQUESTED)
        return True

    def status(self) -> Dict[str, Any]:
        """Returns a read-only snapshot dict describing this instance's
        current/most-recent build:

            {
                "status": one of RuntimeStatus's constants,
                "context": {"use_vlm": ..., "page_batch_size": ...,
                             "force": ..., "pdf_input_folder": ...} or None,
                "progress": {"books_total": ..., "books_completed": ...,
                              "chapters_written": ..., "chapters_failed": ...,
                              "current_book": ...},
                "error": str or None,
            }

        Safe to call at any time, including while another thread is
        inside run() -- it only reads runtime/state.py's slots, it never
        mutates anything (F0 §13's "preserve read-only behaviour" -- the
        one place in Phase F1 that requirement most directly applies)."""
        context = runtime_state.get_current_context()
        return {
            "status": runtime_state.get_current_status(),
            "context": (
                {
                    "use_vlm": context.use_vlm,
                    "page_batch_size": context.page_batch_size,
                    "force": context.force,
                    "pdf_input_folder": context.pdf_input_folder,
                }
                if context is not None else None
            ),
            "progress": runtime_state.get_current_progress(),
            "error": runtime_state.get_current_error(),
        }

    def shutdown(self) -> None:
        """Permanently retires this CompilerRuntime instance: clears
        runtime/state.py back to its defaults (status IDLE internally,
        then immediately overridden to SHUT_DOWN so status() reports
        SHUT_DOWN rather than a misleading IDLE) and marks run()/
        resume()/cancel() to raise RuntimeShutDownError from now on.
        Idempotent -- calling shutdown() more than once is a no-op.

        Best-effort only if called while RUNNING (see module docstring's
        COOPERATIVE CANCELLATION section): this also requests
        cancellation, exactly like cancel(), but -- same caveat as
        cancel() -- that can only take effect at the next chapter/book
        boundary, and only if run() is executing on a different thread
        than the one calling shutdown(). shutdown() does not block
        waiting for an in-progress run() to actually stop."""
        if self._is_shut_down:
            return
        if runtime_state.get_current_status() == RuntimeStatus.RUNNING:
            self._cancel_requested = True
        runtime_state.reset_runtime_state()
        runtime_state.set_current_status(RuntimeStatus.SHUT_DOWN)
        self._is_shut_down = True