"""
runtime/state.py — Phase F1: Compiler Runtime module-level state.

Reuses the exact "current state" module-level-slot idiom compiler/state.py
established and every later phase's own state.py (knowledge_graph/,
build_metadata/, dependency_graph/, change_detection/,
incremental_compilation/, incremental_compilation_validation/,
incremental_compilation_finalization/, validation/) has mirrored since --
see compiler/state.py's own module docstring for the idiom's original
rationale. Applied here, unmodified in shape, to the handful of facts
CompilerRuntime needs to answer status() with: current lifecycle status,
the ExecutionContext the current/most-recent run() executed with,
progress counters, and the last error (if any).

ONE IMPORTANT DIFFERENCE FROM EVERY EARLIER PHASE'S state.py: those are
all *chapter-scoped* ("current chapter's RegistryManager", reset before
each new chapter -- see compiler/state.py's OWNERSHIP/LIFECYCLE section).
Runtime state is *run-scoped* instead: it describes the CompilerRuntime's
own current build (which spans every book/chapter pipeline.py processes
in one run() call), not any single chapter within it. reset_runtime_state()
is therefore called once per run() (by CompilerRuntime.run(), right
before orchestration starts), not once per chapter -- F0 §12's "State
remains chapter-scoped" rule governs the artifacts Phase F *consumes*
(Compiler IR, Knowledge Graph, ...), not Phase F1's own runtime-lifecycle
bookkeeping, which by definition has no meaning at chapter granularity.

Not thread-safe / not concurrency-safe by design, same explicit note as
every module this mirrors -- one CompilerRuntime instance, and this
module's slots, describe one build at a time in one process.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .context import ExecutionContext, RuntimeStatus

# --------------------------------------------------------------------------
# Current run's lifecycle status. Set by CompilerRuntime at every lifecycle
# transition (run() -> RUNNING, cancel() -> CANCEL_REQUESTED, a completed
# run -> COMPLETED/CANCELLED/FAILED, shutdown() -> SHUT_DOWN). Defaults to
# IDLE, mirroring get_current_*() elsewhere in this codebase returning None
# for "nothing has happened yet" -- IDLE is that same "normal, expected
# state, not an error condition" for a status string instead of an Optional.
# --------------------------------------------------------------------------
_CURRENT_STATUS: str = RuntimeStatus.IDLE

# --------------------------------------------------------------------------
# The ExecutionContext the current/most-recently-started run() executed
# with, set once per run() call and left in place after that run finishes
# (COMPLETED/CANCELLED/FAILED) so status() can still report what the last
# build ran with -- cleared only by reset_runtime_state() at the start of
# the *next* run(), same "survives until explicitly reset, not until the
# next read" contract every get_current_*() elsewhere in this codebase
# already has.
# --------------------------------------------------------------------------
_CURRENT_CONTEXT: Optional[ExecutionContext] = None

# --------------------------------------------------------------------------
# Progress counters for the current/most-recent run, updated as
# book_orchestrator.run()/pipeline.process_all_pdfs() report back (books
# processed so far, chapters written, chapters failed, and -- once known
# -- the totals). A plain dict, not a dataclass, mirroring build_metadata/
# state.py's and dependency_graph/state.py's own "one slot holding a dict,
# not one slot per field" precedent (nothing outside this module needs
# less than the whole progress snapshot).
# --------------------------------------------------------------------------
_CURRENT_PROGRESS: Dict[str, Any] = {
    "books_total": 0,
    "books_completed": 0,
    "chapters_written": 0,
    "chapters_failed": 0,
    "current_book": None,
}

# --------------------------------------------------------------------------
# The most recent run's error, if status is FAILED -- str(exc), not the
# exception object itself (this module holds plain, easily-inspectable
# data, same convention as every dict/str slot elsewhere in this
# codebase's state.py modules; the actual exception still propagates out
# of CompilerRuntime.run() unchanged, see runtime/exceptions.py's module
# docstring).
# --------------------------------------------------------------------------
_CURRENT_ERROR: Optional[str] = None


def set_current_status(status: str) -> None:
    """Called by CompilerRuntime at every lifecycle transition."""
    global _CURRENT_STATUS
    _CURRENT_STATUS = status


def get_current_status() -> str:
    """Returns the current lifecycle status string. Never None -- IDLE is
    the default before any run() has ever started, mirroring this
    module's own docstring note on why status uses IDLE rather than
    Optional[str]."""
    return _CURRENT_STATUS


def set_current_context(context: ExecutionContext) -> None:
    """Called once by CompilerRuntime.run()/resume(), right before
    orchestration starts, so status() can report what the current build
    is executing with."""
    global _CURRENT_CONTEXT
    _CURRENT_CONTEXT = context


def get_current_context() -> Optional[ExecutionContext]:
    """Returns the ExecutionContext the current/most-recent run executed
    with, or None if no run() has ever been called on this process's
    runtime state. Deliberately returns None rather than raising, for the
    same reason every other get_current_*() in this codebase does."""
    return _CURRENT_CONTEXT


def has_current_context() -> bool:
    """True once set_current_context() has been called and before the
    next reset_runtime_state() call."""
    return _CURRENT_CONTEXT is not None


def set_current_progress(**updates: Any) -> None:
    """Merges `updates` into the current progress dict in place (e.g.
    set_current_progress(chapters_written=3)) -- called by
    CompilerRuntime as book_orchestrator.run()/pipeline.process_all_pdfs()
    report results back, so status() always reflects the latest known
    counts without CompilerRuntime having to re-derive them."""
    _CURRENT_PROGRESS.update(updates)


def get_current_progress() -> Dict[str, Any]:
    """Returns a shallow copy of the current progress dict -- a copy,
    unlike every other get_current_*() in this codebase, specifically so
    a caller mutating the returned dict can never corrupt this module's
    own bookkeeping (progress is read-and-displayed data, not a shared
    mutable artifact later phases build on top of, unlike e.g.
    RegistryManager)."""
    return dict(_CURRENT_PROGRESS)


def set_current_error(error: Optional[str]) -> None:
    """Called by CompilerRuntime.run() when orchestration raises, right
    before status is set to FAILED and the exception is re-raised (see
    runtime/runtime.py's CompilerRuntime.run() docstring for the full
    error-propagation contract)."""
    global _CURRENT_ERROR
    _CURRENT_ERROR = error


def get_current_error() -> Optional[str]:
    """Returns the most recent run's error message, or None if the
    current/most-recent run did not fail."""
    return _CURRENT_ERROR


def has_current_error() -> bool:
    """True once set_current_error() has been called with a non-None
    value and before the next reset_runtime_state() call."""
    return _CURRENT_ERROR is not None


def reset_runtime_state() -> None:
    """Clears every runtime state slot back to its IDLE/empty default.
    Called once per run() (by CompilerRuntime.run(), before orchestration
    starts -- see module docstring's "run-scoped, not chapter-scoped"
    note) and once by shutdown() (after which set_current_status()
    immediately sets SHUT_DOWN back, so shutdown remains observable via
    status() even though every other slot has been cleared). Safe to
    call even if nothing was ever set (idempotent), same as every other
    reset_*_state() in this codebase."""
    global _CURRENT_STATUS, _CURRENT_CONTEXT, _CURRENT_ERROR
    _CURRENT_STATUS = RuntimeStatus.IDLE
    _CURRENT_CONTEXT = None
    _CURRENT_ERROR = None
    _CURRENT_PROGRESS.update(
        books_total=0, books_completed=0, chapters_written=0,
        chapters_failed=0, current_book=None,
    )