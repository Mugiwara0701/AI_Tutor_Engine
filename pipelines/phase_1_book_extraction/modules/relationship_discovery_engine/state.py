"""
modules/relationship_discovery_engine/state.py — M5.2E: chapter-scoped
SemanticGraph state.

Follows the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() convention every other phase in this codebase uses.
Chapter-scoped: reset_*_state() is called before each chapter.

pipeline.py reads this via get_current_semantic_graph() after
RelationshipDiscoveryEngine.build_graph() completes, then passes the
SemanticGraph to modules/master_knowledge_compiler/engine.compile_graph().
"""
from __future__ import annotations

from typing import Optional

_current_semantic_graph: Optional[object] = None


def set_current_semantic_graph(graph: object) -> None:
    """Set the chapter-scoped SemanticGraph."""
    global _current_semantic_graph
    _current_semantic_graph = graph


def get_current_semantic_graph() -> Optional[object]:
    """Return the chapter-scoped SemanticGraph, or None."""
    return _current_semantic_graph


def has_current_semantic_graph() -> bool:
    """Return True iff a SemanticGraph has been set this chapter."""
    return _current_semantic_graph is not None


def reset_semantic_graph_state() -> None:
    """Clear the chapter-scoped SemanticGraph slot.

    Called by pipeline.py before each new chapter so that a previous
    chapter\'s SemanticGraph is never read as the current chapter\'s.
    """
    global _current_semantic_graph
    _current_semantic_graph = None
