"""
incremental_compilation/state.py — Phase E4: Incremental Compilation
module-level state.

Follows the exact single-slot idiom change_detection/state.py already
establishes one phase down (that module's own docstring: "a single
'current chapter's ChangeDetectionReport' slot ... following the exact
module-level-slot idiom already established by compiler/state.py,
knowledge_graph/state.py, and validation/state.py"). One slot, not one
per sub-list (dirty/clean/affected/...): nothing downstream of Phase E4
ever needs less than the whole assembled IncrementalCompilationPlan, so
a single slot is the right granularity here -- same reasoning
change_detection/state.py's own docstring already gives one phase
down.

set_current_incremental_compilation_plan() is called once per chapter
by pipeline.py right after
incremental_compilation.engine.plan_incremental_compilation() finishes,
read by any later in-process consumer via
get_current_incremental_compilation_plan(), and cleared by
reset_incremental_compilation_state() before the next chapter's work
starts so one chapter's IncrementalCompilationPlan never remains
"current" while the next chapter is being processed.

Not thread-safe / not concurrency-safe by design, same as every other
"current chapter" state module in this codebase (this pipeline
processes one chapter at a time, in one process).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's IncrementalCompilationPlan dict, set once per
# chapter by pipeline.py after plan_incremental_compilation() finishes
# and cleared by reset_incremental_compilation_state() before the next
# chapter's work starts.
# --------------------------------------------------------------------------
_CURRENT_INCREMENTAL_COMPILATION_PLAN: Optional[Dict[str, Any]] = None


def set_current_incremental_compilation_plan(plan: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    incremental_compilation.engine.plan_incremental_compilation()
    finishes assembling this chapter's IncrementalCompilationPlan --
    makes it part of this process's current-compilation state,
    reachable by any later in-process consumer via
    get_current_incremental_compilation_plan(), without ever writing it
    into a compiler/graph registry or into Chapter JSON."""
    global _CURRENT_INCREMENTAL_COMPILATION_PLAN
    _CURRENT_INCREMENTAL_COMPILATION_PLAN = plan


def get_current_incremental_compilation_plan() -> Optional[Dict[str, Any]]:
    """Returns the most recently
    set_current_incremental_compilation_plan()'d dict, or None if none
    has been set yet in this process (or it has since been cleared by
    reset_incremental_compilation_state()). Deliberately returns None
    rather than raising: "no chapter's IncrementalCompilationPlan has
    been generated yet in this process" is a normal, expected state,
    not an error condition."""
    return _CURRENT_INCREMENTAL_COMPILATION_PLAN


def has_current_incremental_compilation_plan() -> bool:
    """True once set_current_incremental_compilation_plan() has been
    called and before the next reset_incremental_compilation_state()
    call -- a non-raising way to check availability before calling
    get_current_incremental_compilation_plan()."""
    return _CURRENT_INCREMENTAL_COMPILATION_PLAN is not None


def reset_incremental_compilation_state() -> None:
    """Clears the current chapter's IncrementalCompilationPlan. Call
    once per chapter, alongside every other *_state.reset_*_state()
    call, before that chapter's own incremental-compilation planning
    happens -- never let one chapter's IncrementalCompilationPlan
    remain "current" while the next chapter is being processed."""
    global _CURRENT_INCREMENTAL_COMPILATION_PLAN
    _CURRENT_INCREMENTAL_COMPILATION_PLAN = None