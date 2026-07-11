"""
incremental_compilation_validation/state.py — Phase E5.1: Incremental
Compilation Validation module-level state.

Follows the exact single-slot idiom incremental_compilation/state.py
already establishes one phase down (that module's own docstring: "One
slot, not one per sub-list ... a single slot is the right granularity
here"), plus one extra slot (`_CURRENT_INCREMENTAL_COMPILATION_
VALIDATION_STATUS`) mirroring validation.release_state's own
`_CURRENT_RELEASE_STATUS` / compiler.state's own `_CURRENT_FINAL_
COMPILER_STATUS` precedent, one layer up: the verdict gets its own
slot, separate from the full report, so a later in-process consumer can
check "did E5.1 pass" without re-reading and re-parsing the whole
report dict.

set_current_incremental_compilation_validation_report() /
set_current_incremental_compilation_validation_status() are called once
per chapter by pipeline.py right after
incremental_compilation_validation.engine.validate_incremental_compilation()
finishes, read by any later in-process consumer via the matching
get_current_*() functions, and cleared by
reset_incremental_compilation_validation_state() before the next
chapter's work starts so one chapter's report/status never remains
"current" while the next chapter is being processed.

Not thread-safe / not concurrency-safe by design, same as every other
"current chapter" state module in this codebase (this pipeline
processes one chapter at a time, in one process).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's IncrementalCompilationValidationReport dict / its own
# overall_status, set once per chapter by pipeline.py after
# validate_incremental_compilation() finishes and cleared by
# reset_incremental_compilation_validation_state() before the next
# chapter's work starts.
# --------------------------------------------------------------------------
_CURRENT_INCREMENTAL_COMPILATION_VALIDATION_REPORT: Optional[Dict[str, Any]] = None
_CURRENT_INCREMENTAL_COMPILATION_VALIDATION_STATUS: Optional[str] = None


def set_current_incremental_compilation_validation_report(report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    incremental_compilation_validation.engine.
    validate_incremental_compilation() finishes assembling this
    chapter's IncrementalCompilationValidationReport -- makes it part of
    this process's current-compilation state, reachable by any later
    in-process consumer via
    get_current_incremental_compilation_validation_report(), without
    ever writing it into a compiler/graph registry or into Chapter
    JSON."""
    global _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_REPORT
    _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_REPORT = report


def get_current_incremental_compilation_validation_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently
    set_current_incremental_compilation_validation_report()'d dict, or
    None if none has been set yet in this process (or it has since been
    cleared by reset_incremental_compilation_validation_state()).
    Deliberately returns None rather than raising: "no chapter's
    IncrementalCompilationValidationReport has been generated yet in
    this process" is a normal, expected state, not an error
    condition."""
    return _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_REPORT


def has_current_incremental_compilation_validation_report() -> bool:
    """True once
    set_current_incremental_compilation_validation_report() has been
    called and before the next
    reset_incremental_compilation_validation_state() call -- a
    non-raising way to check availability before calling
    get_current_incremental_compilation_validation_report()."""
    return _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_REPORT is not None


def set_current_incremental_compilation_validation_status(status: str) -> None:
    """Called once per chapter by pipeline.py, alongside
    set_current_incremental_compilation_validation_report() -- mirrors
    validation.release_state.set_current_release_status()'s own "verdict
    gets its own slot, separate from the full report" precedent, one
    layer up."""
    global _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_STATUS
    _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_STATUS = status


def get_current_incremental_compilation_validation_status() -> Optional[str]:
    """Returns the most recently
    set_current_incremental_compilation_validation_status()'d value, or
    None if none has been set yet in this process (or it has since been
    cleared by reset_incremental_compilation_validation_state())."""
    return _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_STATUS


def has_current_incremental_compilation_validation_status() -> bool:
    """True once set_current_incremental_compilation_validation_status()
    has been called and before the next
    reset_incremental_compilation_validation_state() call."""
    return _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_STATUS is not None


def reset_incremental_compilation_validation_state() -> None:
    """Clears the current chapter's IncrementalCompilationValidationReport
    and its own overall_status. Call once per chapter, alongside every
    other *_state.reset_*_state() call, before that chapter's own
    incremental-compilation-validation run happens -- never let one
    chapter's report/status remain "current" while the next chapter is
    being processed."""
    global _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_REPORT, _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_STATUS
    _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_REPORT = None
    _CURRENT_INCREMENTAL_COMPILATION_VALIDATION_STATUS = None