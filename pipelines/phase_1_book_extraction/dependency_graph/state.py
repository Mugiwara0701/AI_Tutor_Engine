"""
dependency_graph/state.py — Phase E2: Build Dependency Graph
module-level state.

Follows the exact single-slot idiom build_metadata/state.py already
establishes one phase down (that module's own docstring: "a single
'current chapter's BuildMetadata' slot ... following the exact
module-level-slot idiom already established by compiler/state.py,
knowledge_graph/state.py, and validation/state.py"). One slot, not one
per sub-artifact: exactly as with BuildMetadata, nothing downstream of
Phase E2 ever needs less than the whole assembled DependencyGraph, so
a single slot -- not one per node-registry/edge-registry/metadata
block -- is the right granularity here (see build_metadata/state.py's
own docstring for the equivalent reasoning one phase down).

set_current_dependency_graph() is called once per chapter by
pipeline.py right after
dependency_graph.build.generate_dependency_graph() finishes, read by
any later in-process consumer via get_current_dependency_graph(), and
cleared by reset_dependency_graph_state() before the next chapter's
work starts so one chapter's DependencyGraph never remains "current"
while the next chapter is being processed.

Not thread-safe / not concurrency-safe by design, same as every other
"current chapter" state module in this codebase (this pipeline
processes one chapter at a time, in one process).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's DependencyGraph dict, set once per chapter by
# pipeline.py after generate_dependency_graph() finishes and cleared by
# reset_dependency_graph_state() before the next chapter's work starts.
# --------------------------------------------------------------------------
_CURRENT_DEPENDENCY_GRAPH: Optional[Dict[str, Any]] = None


def set_current_dependency_graph(dependency_graph: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    dependency_graph.build.generate_dependency_graph() finishes
    assembling this chapter's DependencyGraph -- makes it part of this
    process's current-compilation state, reachable by any later
    in-process consumer via get_current_dependency_graph(), without
    ever writing it into a compiler/graph registry or into Chapter
    JSON."""
    global _CURRENT_DEPENDENCY_GRAPH
    _CURRENT_DEPENDENCY_GRAPH = dependency_graph


def get_current_dependency_graph() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_dependency_graph()'d dict,
    or None if none has been set yet in this process (or it has since
    been cleared by reset_dependency_graph_state()). Deliberately
    returns None rather than raising: "no chapter's DependencyGraph has
    been generated yet in this process" is a normal, expected state,
    not an error condition."""
    return _CURRENT_DEPENDENCY_GRAPH


def has_current_dependency_graph() -> bool:
    """True once set_current_dependency_graph() has been called and
    before the next reset_dependency_graph_state() call -- a
    non-raising way to check availability before calling
    get_current_dependency_graph()."""
    return _CURRENT_DEPENDENCY_GRAPH is not None


def reset_dependency_graph_state() -> None:
    """Clears the current chapter's DependencyGraph. Call once per
    chapter, alongside every other *_state.reset_*_state() call, before
    that chapter's own dependency_graph generation happens -- never let
    one chapter's DependencyGraph remain "current" while the next
    chapter is being processed."""
    global _CURRENT_DEPENDENCY_GRAPH
    _CURRENT_DEPENDENCY_GRAPH = None