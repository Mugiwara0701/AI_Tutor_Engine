"""
change_detection/state.py — Phase E3: Change Detection module-level
state.

Follows the exact single-slot idiom dependency_graph/state.py already
establishes one phase down (that module's own docstring: "a single
'current chapter's DependencyGraph' slot ... following the exact
module-level-slot idiom already established by compiler/state.py,
knowledge_graph/state.py, and validation/state.py"). One slot, not one
per sub-list (added/removed/modified/...): nothing downstream of Phase
E3 ever needs less than the whole assembled ChangeDetectionReport, so a
single slot is the right granularity here -- same reasoning
dependency_graph/state.py's own docstring already gives one phase down.

set_current_change_detection_report() is called once per chapter by
pipeline.py right after change_detection.engine.detect_changes()
finishes, read by any later in-process consumer via
get_current_change_detection_report(), and cleared by
reset_change_detection_state() before the next chapter's work starts so
one chapter's ChangeDetectionReport never remains "current" while the
next chapter is being processed.

Not thread-safe / not concurrency-safe by design, same as every other
"current chapter" state module in this codebase (this pipeline
processes one chapter at a time, in one process).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's ChangeDetectionReport dict, set once per chapter by
# pipeline.py after detect_changes() finishes and cleared by
# reset_change_detection_state() before the next chapter's work starts.
# --------------------------------------------------------------------------
_CURRENT_CHANGE_DETECTION_REPORT: Optional[Dict[str, Any]] = None


def set_current_change_detection_report(change_detection_report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    change_detection.engine.detect_changes() finishes assembling this
    chapter's ChangeDetectionReport -- makes it part of this process's
    current-compilation state, reachable by any later in-process
    consumer via get_current_change_detection_report(), without ever
    writing it into a compiler/graph registry or into Chapter JSON."""
    global _CURRENT_CHANGE_DETECTION_REPORT
    _CURRENT_CHANGE_DETECTION_REPORT = change_detection_report


def get_current_change_detection_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently
    set_current_change_detection_report()'d dict, or None if none has
    been set yet in this process (or it has since been cleared by
    reset_change_detection_state()). Deliberately returns None rather
    than raising: "no chapter's ChangeDetectionReport has been
    generated yet in this process" is a normal, expected state, not an
    error condition."""
    return _CURRENT_CHANGE_DETECTION_REPORT


def has_current_change_detection_report() -> bool:
    """True once set_current_change_detection_report() has been called
    and before the next reset_change_detection_state() call -- a
    non-raising way to check availability before calling
    get_current_change_detection_report()."""
    return _CURRENT_CHANGE_DETECTION_REPORT is not None


def reset_change_detection_state() -> None:
    """Clears the current chapter's ChangeDetectionReport. Call once
    per chapter, alongside every other *_state.reset_*_state() call,
    before that chapter's own change detection happens -- never let one
    chapter's ChangeDetectionReport remain "current" while the next
    chapter is being processed."""
    global _CURRENT_CHANGE_DETECTION_REPORT
    _CURRENT_CHANGE_DETECTION_REPORT = None