"""
validation/determinism_state.py — Phase D2: current chapter's
Determinism Report, held as module-level state.

Same established idiom validation/state.py (Phase D1's own state
module) already uses, one artifact over -- see that module's own
docstring for the full ownership/lifecycle rationale, which applies
here unchanged with "System Integrity Report" replaced by "Determinism
Report" throughout:

  1. pipeline.py calls reset_determinism_state() immediately before this
     chapter's own validation.determinism.validate_determinism() call,
     right after Phase D1's own validate_system_integrity() call
     finishes -- clearing whatever the *previous* chapter left behind
     before this chapter's report is computed and set.
  2. pipeline.py calls validation.determinism.validate_determinism()
     once Phase D1 is complete, and calls
     set_current_determinism_report() on the resulting dict -- the only
     place anything is written into this module's state.
  3. From that point until the next reset_determinism_state() call,
     get_current_determinism_report() returns that exact report dict to
     any caller in this process.

Not thread-safe / not concurrency-safe by design, same as validation.
state's own equivalent module-level state.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's Determinism Report, set once per chapter by
# pipeline.py and cleared by reset_determinism_state() below. Exact same
# idiom as validation.state.py's own _CURRENT_SYSTEM_INTEGRITY_REPORT.
# --------------------------------------------------------------------------
_CURRENT_DETERMINISM_REPORT: Optional[Dict[str, Any]] = None


def set_current_determinism_report(report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    validation.determinism.validate_determinism() finishes -- makes the
    report reachable by any later in-process consumer via
    get_current_determinism_report(), without ever writing it into any
    compiler registry, any knowledge graph registry, or Chapter JSON."""
    global _CURRENT_DETERMINISM_REPORT
    _CURRENT_DETERMINISM_REPORT = report


def get_current_determinism_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_determinism_report()'d
    dict, or None if none has been set yet in this process (or it has
    since been cleared by reset_determinism_state()). Deliberately
    returns None rather than raising, for the same reason validation.
    state.get_current_system_integrity_report() does."""
    return _CURRENT_DETERMINISM_REPORT


def has_current_determinism_report() -> bool:
    """True once set_current_determinism_report() has been called and
    before the next reset_determinism_state() call."""
    return _CURRENT_DETERMINISM_REPORT is not None


def reset_determinism_state() -> None:
    """Clears the current Determinism Report -- called by pipeline.py
    before this chapter's Phase D2 step, so a failed or skipped chapter
    never leaves a stale report from the previous chapter visible as
    "current". Same reset idiom as validation.state.
    reset_system_integrity_state()."""
    global _CURRENT_DETERMINISM_REPORT
    _CURRENT_DETERMINISM_REPORT = None
