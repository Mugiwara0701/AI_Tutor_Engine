"""
validation/state.py — Phase D1: current chapter's System Integrity
Report, held as module-level state.

Same established idiom compiler/state.py and knowledge_graph/state.py
already use (one module-level slot per artifact, set once per chapter by
pipeline.py, read by any later in-process consumer, cleared by
reset_system_integrity_state() before this module's own state is
(re)written) -- applied here to the one Phase D1 artifact
(validation.system_integrity.SystemIntegrityReport, stored as its own
plain dict via .to_dict()). No new architectural style is introduced.

OWNERSHIP / LIFECYCLE:

  1. pipeline.py calls compiler_state.reset_registry_state() and
     kg_state.reset_knowledge_graph_state() before any per-chapter work
     starts. reset_system_integrity_state() is NOT called at that same
     point -- Phase D1 has nothing to reset yet that early, since it
     only ever runs once Phase C is already complete. Instead, pipeline.py
     calls reset_system_integrity_state() immediately before this
     chapter's own validation.system_integrity.validate_system_
     integrity() call, right after Phase C finishes -- clearing whatever
     the *previous* chapter left behind before this chapter's report is
     computed and (see step 2) set.
  2. pipeline.py calls validation.system_integrity.validate_system_
     integrity() once Phase C (Knowledge Graph) is fully complete, and
     calls set_current_system_integrity_report() on the resulting dict
     -- the only place anything is written into this module's state.
  3. From that point until the next reset_system_integrity_state() call
     (i.e. until the following chapter reaches its own Phase D1 step),
     get_current_system_integrity_report() returns that exact report
     dict to any caller in this process.

Not thread-safe / not concurrency-safe by design, same as
compiler/state.py's and knowledge_graph/state.py's own equivalent
module-level state -- this pipeline processes one chapter at a time, in
one process.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's System Integrity Report, set once per chapter by
# pipeline.py after validation.system_integrity.validate_system_
# integrity() finishes and cleared by reset_system_integrity_state()
# below. Exact same idiom as knowledge_graph/state.py's own
# _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT.
# --------------------------------------------------------------------------
_CURRENT_SYSTEM_INTEGRITY_REPORT: Optional[Dict[str, Any]] = None


def set_current_system_integrity_report(report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    validation.system_integrity.validate_system_integrity() finishes --
    makes the report reachable by any later in-process consumer via
    get_current_system_integrity_report(), without ever writing it into
    any compiler registry, any knowledge graph registry, or Chapter
    JSON."""
    global _CURRENT_SYSTEM_INTEGRITY_REPORT
    _CURRENT_SYSTEM_INTEGRITY_REPORT = report


def get_current_system_integrity_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_system_integrity_report()'d
    dict, or None if none has been set yet in this process (or it has
    since been cleared by reset_system_integrity_state()). Deliberately
    returns None rather than raising, for the same reason
    compiler.state.get_current_registry_manager() does."""
    return _CURRENT_SYSTEM_INTEGRITY_REPORT


def has_current_system_integrity_report() -> bool:
    """True once set_current_system_integrity_report() has been called
    and before the next reset_system_integrity_state() call."""
    return _CURRENT_SYSTEM_INTEGRITY_REPORT is not None


def reset_system_integrity_state() -> None:
    """Clears the current System Integrity Report -- called by
    pipeline.py before each new chapter starts processing, so a failed
    or skipped chapter never leaves a stale report from the previous
    chapter visible as \"current\". Same reset idiom as
    compiler.state.reset_registry_state() / knowledge_graph.state.
    reset_knowledge_graph_state()."""
    global _CURRENT_SYSTEM_INTEGRITY_REPORT
    _CURRENT_SYSTEM_INTEGRITY_REPORT = None