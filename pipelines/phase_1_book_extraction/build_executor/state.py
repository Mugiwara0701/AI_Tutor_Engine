"""
build_executor/state.py — Phase F3: module-level "current execution
report" state.

Reuses the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() idiom every other phase's own state.py in this
codebase already uses (see artifact_manager/state.py's own module
docstring for the same idiom applied one phase down).

RUN-SCOPED, LIKE artifact_manager/state.py AND runtime/state.py -- NOT
CHAPTER-SCOPED: an Execution Report describes one whole CompilerRuntime
run()/resume() call (every book/chapter it touched), so this state is
set once per run/resume (by CompilerRuntime._execute(), immediately
after Phase F2's own Build has been recorded), not once per chapter.

Not thread-safe / not concurrency-safe by design, same explicit note as
every module this mirrors.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

_CURRENT_EXECUTION_REPORT: Optional[Dict[str, Any]] = None


def set_current_execution_report(execution_report: Dict[str, Any]) -> None:
    """Called once by CompilerRuntime._execute() (runtime/runtime.py),
    immediately after this run's Execution Report has been assembled
    (see build_executor.executor.aggregate_run_execution_report())."""
    global _CURRENT_EXECUTION_REPORT
    _CURRENT_EXECUTION_REPORT = execution_report


def get_current_execution_report() -> Optional[Dict[str, Any]]:
    """Returns the current/most-recently-produced Execution Report, or
    None if no run()/resume() has ever completed in this process (or
    Phase F3's own bookkeeping failed this run -- see executor.py's
    "never raises" integration contract). Deliberately returns None
    rather than raising, for the same reason every other
    get_current_*() in this codebase does."""
    return _CURRENT_EXECUTION_REPORT


def has_current_execution_report() -> bool:
    """True once set_current_execution_report() has been called and
    before the next reset_current_execution_report() call."""
    return _CURRENT_EXECUTION_REPORT is not None


def reset_current_execution_report() -> None:
    """Clears this state back to its empty default. Safe to call even
    if nothing was ever set (idempotent), same as every other
    reset_*_state() in this codebase."""
    global _CURRENT_EXECUTION_REPORT
    _CURRENT_EXECUTION_REPORT = None