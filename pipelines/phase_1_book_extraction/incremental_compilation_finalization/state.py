"""
incremental_compilation_finalization/state.py — Phase E5.2:
Incremental Compilation Finalization module-level state.

Follows the exact single-slot-per-artifact idiom incremental_
compilation_validation/state.py already establishes one package down
(that module's own docstring, itself mirroring incremental_
compilation/state.py's own "One slot, not one per sub-list ... a
single slot is the right granularity here" precedent), plus a third
slot (`_CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS`) alongside the
two report slots -- mirroring validation.release_state's own
`_CURRENT_RELEASE_READINESS_REPORT` / `_CURRENT_RELEASE_STATUS` pair
and compiler.state's own build-summary/final-status pair, one/two
layers up: the verdict gets its own slot, separate from either full
report, so a later in-process consumer can check "is this chapter's
incremental compilation READY" without re-reading and re-parsing a
whole report dict.

set_current_incremental_compilation_readiness_report() /
set_current_incremental_compilation_build_summary() /
set_current_incremental_compilation_final_status() are called once per
chapter by pipeline.py right after incremental_compilation_
finalization.finalize.finalize_incremental_compilation() finishes,
read by any later in-process consumer via the matching get_current_*()
functions, and cleared by reset_incremental_compilation_finalization_
state() before the next chapter's work starts so one chapter's
reports/status never remain "current" while the next chapter is being
processed.

Not thread-safe / not concurrency-safe by design, same as every other
"current chapter" state module in this codebase (this pipeline
processes one chapter at a time, in one process).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's IncrementalCompilationReadinessReport /
# IncrementalCompilationBuildSummary dicts / its own final status, set
# once per chapter by pipeline.py after finalize_incremental_
# compilation() finishes and cleared by reset_incremental_compilation_
# finalization_state() before the next chapter's work starts.
# --------------------------------------------------------------------------
_CURRENT_INCREMENTAL_COMPILATION_READINESS_REPORT: Optional[Dict[str, Any]] = None
_CURRENT_INCREMENTAL_COMPILATION_BUILD_SUMMARY: Optional[Dict[str, Any]] = None
_CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS: Optional[str] = None


def set_current_incremental_compilation_readiness_report(report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    incremental_compilation_finalization.finalize.
    finalize_incremental_compilation() finishes assembling this
    chapter's IncrementalCompilationReadinessReport -- makes it part of
    this process's current-compilation state, reachable by any later
    in-process consumer via get_current_incremental_compilation_
    readiness_report(), without ever writing it into a compiler/graph
    registry or into Chapter JSON."""
    global _CURRENT_INCREMENTAL_COMPILATION_READINESS_REPORT
    _CURRENT_INCREMENTAL_COMPILATION_READINESS_REPORT = report


def get_current_incremental_compilation_readiness_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently
    set_current_incremental_compilation_readiness_report()'d dict, or
    None if none has been set yet in this process (or it has since
    been cleared by reset_incremental_compilation_finalization_
    state()). Deliberately returns None rather than raising: "no
    chapter's IncrementalCompilationReadinessReport has been generated
    yet in this process" is a normal, expected state, not an error
    condition."""
    return _CURRENT_INCREMENTAL_COMPILATION_READINESS_REPORT


def has_current_incremental_compilation_readiness_report() -> bool:
    """True once set_current_incremental_compilation_readiness_report()
    has been called and before the next reset_incremental_compilation_
    finalization_state() call -- a non-raising way to check
    availability before calling get_current_incremental_compilation_
    readiness_report()."""
    return _CURRENT_INCREMENTAL_COMPILATION_READINESS_REPORT is not None


def set_current_incremental_compilation_build_summary(summary: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, alongside
    set_current_incremental_compilation_readiness_report() -- mirrors
    compiler.state.set_current_compiler_build_summary()'s own "each
    finalization artifact gets its own slot" precedent, one layer
    down."""
    global _CURRENT_INCREMENTAL_COMPILATION_BUILD_SUMMARY
    _CURRENT_INCREMENTAL_COMPILATION_BUILD_SUMMARY = summary


def get_current_incremental_compilation_build_summary() -> Optional[Dict[str, Any]]:
    """Returns the most recently
    set_current_incremental_compilation_build_summary()'d dict, or
    None if none has been set yet in this process (or it has since
    been cleared by reset_incremental_compilation_finalization_
    state())."""
    return _CURRENT_INCREMENTAL_COMPILATION_BUILD_SUMMARY


def has_current_incremental_compilation_build_summary() -> bool:
    """True once set_current_incremental_compilation_build_summary()
    has been called and before the next reset_incremental_compilation_
    finalization_state() call."""
    return _CURRENT_INCREMENTAL_COMPILATION_BUILD_SUMMARY is not None


def set_current_incremental_compilation_final_status(status: str) -> None:
    """Called once per chapter by pipeline.py, alongside the two
    set_current_incremental_compilation_*() calls above -- mirrors
    validation.release_state.set_current_release_status()'s /
    compiler.state.set_current_final_compiler_status()'s own "verdict
    gets its own slot, separate from either full report" precedent."""
    global _CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS
    _CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS = status


def get_current_incremental_compilation_final_status() -> Optional[str]:
    """Returns the most recently
    set_current_incremental_compilation_final_status()'d value, or
    None if none has been set yet in this process (or it has since
    been cleared by reset_incremental_compilation_finalization_
    state())."""
    return _CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS


def has_current_incremental_compilation_final_status() -> bool:
    """True once set_current_incremental_compilation_final_status() has
    been called and before the next reset_incremental_compilation_
    finalization_state() call."""
    return _CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS is not None


def reset_incremental_compilation_finalization_state() -> None:
    """Clears the current chapter's IncrementalCompilationReadinessReport,
    IncrementalCompilationBuildSummary, and final status. Call once per
    chapter, alongside every other *_state.reset_*_state() call, before
    that chapter's own incremental-compilation-finalization run happens
    -- never let one chapter's reports/status remain "current" while
    the next chapter is being processed."""
    global _CURRENT_INCREMENTAL_COMPILATION_READINESS_REPORT
    global _CURRENT_INCREMENTAL_COMPILATION_BUILD_SUMMARY
    global _CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS
    _CURRENT_INCREMENTAL_COMPILATION_READINESS_REPORT = None
    _CURRENT_INCREMENTAL_COMPILATION_BUILD_SUMMARY = None
    _CURRENT_INCREMENTAL_COMPILATION_FINAL_STATUS = None
