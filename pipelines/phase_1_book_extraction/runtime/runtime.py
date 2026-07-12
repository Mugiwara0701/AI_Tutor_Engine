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
            from cache import state as cache_state
            cache_state.reset_current_cache_state()
        except Exception:
            logger.exception(
                "cache: failed to reset current-cache state at the start "
                "of this run; continuing (this run's own CacheEntry/"
                "CacheValidationReport will still overwrite it once "
                "recorded)."
            )

        try:
            from compiler_release import state as release_state
            release_state.reset_current_release_manifest_state()
        except Exception:
            logger.exception(
                "compiler_release: failed to reset current-release-"
                "manifest state at the start of this run; continuing "
                "(this run's own CompilerReleaseManifest will still "
                "overwrite it once recorded)."
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
            self._record_cache()
            self._record_release()
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
        self._record_cache()
        self._record_release()
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

    def _record_cache(self) -> None:
        """Phase F4.1 integration point: persists this run's own
        fingerprint snapshot (read verbatim off the Build Phase F2 just
        recorded) so a LATER run can finally read what THIS run's own
        last-processed-chapter fingerprints were, and generates a
        read-only CacheValidationReport comparing the previous cached
        build's fingerprints against this run's own, alongside Phase
        F3's own already-made Execution Plan. Called immediately after
        _record_execution() above, on both the failure path (mirroring
        _record_build()'s/_record_execution()'s own "a FAILED run still
        gets a record" contract -- there is nothing to cache/validate
        without a manifested Build, so this is a no-op in that case,
        not an error) and the success/cancelled path.

        Never raises: any failure here is logged and swallowed, same
        "a broken observer must never abort the run" principle
        _record_build()/_record_execution() already apply -- Phase
        F4.1's own bookkeeping can never turn a successful (or
        already-recorded) run into a second, different failure for
        run()'s caller.

        Read-only over everything it doesn't itself produce: never
        mutates the Build, Build Manifest, ExecutionPlan, or
        ExecutionReport it reads; never re-decides reuse/rebuild for
        any chapter; never affects book_orchestrator.run()'s own
        already-completed extraction for this run."""
        try:
            from artifact_manager import state as build_state
            from build_executor import state as execution_state
            from cache import state as cache_state
            from cache.snapshot_store import build_cache_entry, persist_fingerprint_snapshot
            from cache.reuse import select_previous_snapshot
            from cache.validation import validate_execution_against_cache
            from modules import json_writer

            current_build = build_state.get_current_build()
            if current_build is None or not current_build.build_manifest:
                # Phase F2's own bookkeeping never completed this run
                # (e.g. _record_build() itself already failed and
                # logged) -- nothing to cache or validate against.
                # Not an error: same "nothing yet is a normal state"
                # treatment every other Phase F integration point
                # already applies.
                logger.info(
                    "cache: no manifested Build available for this run; "
                    "skipping fingerprint snapshot persistence/validation."
                )
                return

            storage = json_writer.get_storage()

            # The previous run's own cached entry, strictly before this
            # run's own build_id -- read BEFORE this run's own entry is
            # persisted below, so a run is never compared against
            # itself. Phase F4.2's own select_previous_snapshot() (see
            # cache/reuse.py) is used here rather than F4.1's own
            # snapshot_store.load_previous_cache_entry(): both return
            # None under the same "nothing yet" conditions, but F4.2's
            # version additionally falls back to an older, still-usable
            # snapshot when the single most recent one is unreadable or
            # structurally invalid, rather than giving up immediately.
            previous_entry = select_previous_snapshot(
                storage, before_build_id=current_build.build_id
            )
            previous_snapshot = (
                previous_entry.get("fingerprint_snapshot") if previous_entry else None
            )
            previous_build_id = previous_entry.get("build_id") if previous_entry else None

            cache_entry = build_cache_entry(current_build)
            persist_fingerprint_snapshot(storage, cache_entry)
            cache_state.set_current_cache_entry(cache_entry)

            current_execution_report = execution_state.get_current_execution_report() or {}
            execution_plan = {
                "summary": current_execution_report.get("execution_statistics") or {},
            }
            report = validate_execution_against_cache(
                execution_plan,
                cache_entry.get("fingerprint_snapshot") or {},
                previous_snapshot,
                build_id=current_build.build_id,
                previous_build_id=previous_build_id,
            )
            cache_state.set_current_cache_validation_report(report)
        except Exception:
            logger.exception(
                "cache: failed to persist/validate this run's fingerprint "
                "snapshot; run()'s own result/status is unaffected."
            )

    def _record_release(self) -> None:
        """Phase F5 integration point: aggregates this run's own
        already-recorded RuntimeStatus (Phase F1), Build/Build Manifest
        (Phase F2), Execution Report (Phase F3), and CacheEntry/
        CacheValidationReport (Phase F4) into one final
        CompilerReleaseManifest, persists it, and records it via
        compiler_release.state.set_current_release_manifest(). Called
        immediately after _record_cache() above, on both the failure
        path (mirroring _record_build()'s/_record_execution()'s/
        _record_cache()'s own "a FAILED run still gets a record"
        contract -- there is nothing to finalize without a manifested
        Build, so this is a no-op in that case, not an error) and the
        success/cancelled path.

        Never raises: any failure here is logged and swallowed, same
        "a broken observer must never abort the run" principle
        _record_build()/_record_execution()/_record_cache() already
        apply -- Phase F5's own bookkeeping can never turn a successful
        (or already-recorded) run into a second, different failure for
        run()'s caller.

        Read-only over everything it doesn't itself produce: never
        mutates the Build, Build Manifest, Execution Report, CacheEntry,
        or CacheValidationReport it reads; never re-decides anything any
        earlier phase already decided; never affects
        book_orchestrator.run()'s own already-completed extraction for
        this run."""
        try:
            from artifact_manager import state as build_state
            from build_executor import state as execution_state
            from cache import state as cache_state
            from compiler_release import state as release_state
            from compiler_release.finalize import finalize_release
            from compiler_release.persistence import persist_release_manifest
            from modules import json_writer

            current_build = build_state.get_current_build()
            if current_build is None or not current_build.build_manifest:
                # Phase F2's own bookkeeping never completed this run
                # (e.g. _record_build() itself already failed and
                # logged) -- nothing to finalize a release for. Not an
                # error: same "nothing yet is a normal state" treatment
                # every other Phase F integration point already
                # applies.
                logger.info(
                    "compiler_release: no manifested Build available for "
                    "this run; skipping release manifest generation."
                )
                return

            chapters_failed = int(
                (runtime_state.get_current_progress() or {}).get(
                    "chapters_failed"
                ) or 0
            )

            manifest = finalize_release(
                runtime_state.get_current_status(),
                current_build,
                execution_state.get_current_execution_report(),
                cache_state.get_current_cache_entry(),
                cache_state.get_current_cache_validation_report(),
                chapters_failed=chapters_failed,
            )

            storage = json_writer.get_storage()
            persist_release_manifest(storage, manifest)

            release_state.set_current_release_manifest(manifest)
        except Exception:
            logger.exception(
                "compiler_release: failed to generate/persist this run's "
                "CompilerReleaseManifest; run()'s own result/status is "
                "unaffected."
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

        (Cache bookkeeping is intentionally not included here -- see
        cache_status(), a separate read-only method just below, for
        why.)

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

    def cache_status(self) -> Dict[str, Any]:
        """Phase F4.2: a read-only summary of the current/most-recent
        run's own cache bookkeeping, sourced entirely from cache/
        state.py's own already-populated slots (set by _record_cache()
        above) -- no new I/O, no storage access.

        Deliberately NOT folded into status() (see that method's own
        docstring, whose documented return shape this must not
        silently expand): status()'s own "same fake orchestrator
        behavior -> same status()" determinism contract (see
        tests/test_f1_compiler_runtime.py's own
        test_two_runtimes_given_identical_inputs_reach_identical_status,
        Phase F1, frozen) cannot hold for fields that are inherently
        run-unique (`build_id`) or cross-run-history-dependent
        (`comparison_basis`/`overall_status`, which legitimately differ
        between a first-ever run with no cached baseline and a later
        run that now has one, even given byte-for-byte identical
        orchestrator behavior). Exposing that information via its own
        method preserves status()'s existing, tested contract exactly
        while still giving a caller everywhere this data already
        existed to reach it.

        Mirrors status()'s own "read-only snapshot" contract otherwise:
        calling this never mutates anything and is safe at any time,
        including mid-run.

        Returns:
            {
                "has_cache_entry": bool,
                "build_id": str or None,
                "previous_build_id": str or None,
                "comparison_basis": str or None,
                "overall_status": str or None,  # NO_BASELINE/CONSISTENT/DIVERGENT
            }

        Every field is None (except the two bools, which are False)
        when no run has completed yet in this process, or when Phase
        F4.1's/F4.2's own bookkeeping itself failed and was swallowed
        (see _record_cache()'s own "never raises" contract) -- same
        "nothing yet is a normal state" convention this class already
        applies everywhere else."""
        from cache import state as cache_state

        cache_entry = cache_state.get_current_cache_entry()
        validation_report = cache_state.get_current_cache_validation_report()
        return {
            "has_cache_entry": cache_entry is not None,
            "build_id": cache_entry.get("build_id") if cache_entry else None,
            "previous_build_id": (
                validation_report.get("previous_build_id") if validation_report else None
            ),
            "comparison_basis": (
                validation_report.get("comparison_basis") if validation_report else None
            ),
            "overall_status": (
                validation_report.get("overall_status") if validation_report else None
            ),
        }

    # -- Phase F4.2: cache reuse introspection ---------------------------

    def cache_history(self) -> List[Dict[str, Any]]:
        """Every persisted build's own CacheEntry, oldest first -- a
        thin pass-through to cache.index.cache_history() over this
        runtime's own already-authenticated storage instance (reused
        via modules.json_writer.get_storage(), never a second
        OneDriveStorage()). Read-only; safe to call at any time,
        including before any run() has ever completed (returns an empty
        list, same "nothing yet" convention cache.index.cache_history()
        itself already documents)."""
        from cache.index import cache_history as _cache_history
        from modules import json_writer

        return _cache_history(json_writer.get_storage())

    def previous_cache_entry(self) -> Optional[Dict[str, Any]]:
        """The most recent persisted CacheEntry a NEXT run() would
        consume as its own previous snapshot -- Phase F4.2's own
        cache.reuse.select_previous_snapshot(), exposed here as a
        read-only runtime-level convenience so a caller can inspect
        what a future run will compare against without needing to
        import the cache package directly. Returns None if no usable
        previous snapshot exists yet (first run ever, or every
        persisted record is unreadable/invalid)."""
        from cache.reuse import select_previous_snapshot
        from modules import json_writer

        return select_previous_snapshot(json_writer.get_storage())

    def cache_optimization_report(self) -> Dict[str, Any]:
        """Phase F4.2's own cross-run CacheOptimizationReport (see
        cache/optimization_report.py) -- how many persisted builds have
        a usable fingerprint snapshot and how often consecutive builds'
        own fingerprints actually changed, across this project's entire
        persisted build history. Read-only; safe to call at any time."""
        from cache.reuse import analyze_cache_reuse
        from modules import json_writer

        return analyze_cache_reuse(json_writer.get_storage())

    # -- Phase F5: release introspection ---------------------------------

    def release_manifest(self) -> Optional[Dict[str, Any]]:
        """The current/most-recent run's own CompilerReleaseManifest, or
        None if no run has completed yet in this process (or Phase F5's
        own bookkeeping failed and was swallowed -- see _record_release()'s
        own "never raises" contract). Read-only; sourced entirely from
        compiler_release/state.py's own already-populated slot (set by
        _record_release() above) -- no new I/O, no storage access."""
        from compiler_release import state as release_state

        return release_state.get_current_release_manifest()

    def release_history(self) -> List[Dict[str, Any]]:
        """Every persisted CompilerReleaseManifest, oldest first -- a
        thin pass-through to compiler_release.discovery.release_history()
        over this runtime's own already-authenticated storage instance
        (reused via modules.json_writer.get_storage(), never a second
        OneDriveStorage()). Read-only; safe to call at any time,
        including before any run() has ever completed (returns an empty
        list, same "nothing yet" convention
        compiler_release.discovery.release_history() itself already
        documents)."""
        from compiler_release.discovery import release_history as _release_history
        from modules import json_writer

        return _release_history(json_writer.get_storage())

    def release_optimization_context(self) -> Dict[str, Any]:
        """Thin pass-through to cache.reuse.analyze_cache_reuse() (Phase
        F4.2, unchanged) -- included here only as a convenience so a
        caller building a human-facing release dashboard doesn't need to
        import cache/ directly. Computes nothing Phase F4 doesn't already
        compute, and is kept explicitly separate from release_manifest()'s
        own required Final Release Status verdict: this cross-run
        analysis reflects the whole project's persisted build history,
        never this run alone, so it must never feed into
        determine_final_release_status() (see compiler_release/
        finalize.py's own module docstring)."""
        from cache.reuse import analyze_cache_reuse
        from modules import json_writer

        return analyze_cache_reuse(json_writer.get_storage())

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