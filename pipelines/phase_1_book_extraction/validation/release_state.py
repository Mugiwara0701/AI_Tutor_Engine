"""
validation/release_state.py — Phase D3: current chapter's Release
Readiness Report & Release Status, held as module-level state.

Same established idiom validation/state.py (Phase D1's own state
module) and validation/determinism_state.py (Phase D2's own state
module) already use, one artifact over -- see either module's own
docstring for the full ownership/lifecycle rationale, which applies
here unchanged with "System Integrity Report"/"Determinism Report"
replaced by "Release Readiness Report" throughout, plus one extra slot
(`_CURRENT_RELEASE_STATUS`) mirroring compiler.state's own
`_CURRENT_FINAL_COMPILER_STATUS` / knowledge_graph.state's own
`_CURRENT_FINAL_GRAPH_STATUS` precedent, one layer up:

  1. pipeline.py calls reset_release_state() immediately before this
     chapter's own validation.release.finalize_release() call, right
     after Phase D2's own validate_determinism() call finishes --
     clearing whatever the *previous* chapter left behind before this
     chapter's report/status are computed and set.
  2. pipeline.py calls validation.release.finalize_release() once Phase
     D2 is complete, and calls set_current_release_readiness_report()/
     set_current_release_status() on the resulting dict's two halves --
     the only place anything is written into this module's state.
  3. From that point until the next reset_release_state() call,
     get_current_release_readiness_report()/get_current_release_status()
     return those exact values to any caller in this process.

Not thread-safe / not concurrency-safe by design, same as validation.
state's and validation.determinism_state's own equivalent module-level
state.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's Release Readiness Report / Release Status, set once
# per chapter by pipeline.py and cleared by reset_release_state() below.
# Exact same idiom as validation.determinism_state.py's own
# _CURRENT_DETERMINISM_REPORT, plus a second slot mirroring compiler.
# state.py's own _CURRENT_FINAL_COMPILER_STATUS one layer up.
# --------------------------------------------------------------------------
_CURRENT_RELEASE_READINESS_REPORT: Optional[Dict[str, Any]] = None
_CURRENT_RELEASE_STATUS: Optional[str] = None


def set_current_release_readiness_report(report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    validation.release.finalize_release() finishes -- makes the report
    reachable by any later in-process consumer via
    get_current_release_readiness_report(), without ever writing it into
    any compiler registry, any knowledge graph registry, or Chapter
    JSON."""
    global _CURRENT_RELEASE_READINESS_REPORT
    _CURRENT_RELEASE_READINESS_REPORT = report


def get_current_release_readiness_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_release_readiness_report()'d
    dict, or None if none has been set yet in this process (or it has
    since been cleared by reset_release_state()). Deliberately returns
    None rather than raising, for the same reason validation.
    determinism_state.get_current_determinism_report() does."""
    return _CURRENT_RELEASE_READINESS_REPORT


def has_current_release_readiness_report() -> bool:
    """True once set_current_release_readiness_report() has been called
    and before the next reset_release_state() call."""
    return _CURRENT_RELEASE_READINESS_REPORT is not None


def set_current_release_status(status: str) -> None:
    """Called once per chapter by pipeline.py, alongside
    set_current_release_readiness_report() -- mirrors compiler.state.
    set_current_final_compiler_status()'s/knowledge_graph.state.
    set_current_final_graph_status()'s own "verdict gets its own slot,
    separate from the full report" precedent, one layer up."""
    global _CURRENT_RELEASE_STATUS
    _CURRENT_RELEASE_STATUS = status


def get_current_release_status() -> Optional[str]:
    """Returns the most recently set_current_release_status()'d value,
    or None if none has been set yet in this process (or it has since
    been cleared by reset_release_state())."""
    return _CURRENT_RELEASE_STATUS


def has_current_release_status() -> bool:
    """True once set_current_release_status() has been called and
    before the next reset_release_state() call."""
    return _CURRENT_RELEASE_STATUS is not None


def reset_release_state() -> None:
    """Clears the current Release Readiness Report and Release Status --
    called by pipeline.py before this chapter's Phase D3 step, so a
    failed or skipped chapter never leaves a stale report/status from
    the previous chapter visible as "current". Same reset idiom as
    validation.state.reset_system_integrity_state()/validation.
    determinism_state.reset_determinism_state()."""
    global _CURRENT_RELEASE_READINESS_REPORT, _CURRENT_RELEASE_STATUS
    _CURRENT_RELEASE_READINESS_REPORT = None
    _CURRENT_RELEASE_STATUS = None
