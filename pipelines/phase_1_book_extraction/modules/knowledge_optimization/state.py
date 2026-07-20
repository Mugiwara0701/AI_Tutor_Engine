"""
modules/knowledge_optimization/state.py — M5.4: chapter-scoped
OptimizedKnowledgePackage state.

Follows the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() convention every other phase in this codebase uses.
Chapter-scoped: reset_*_state() is called before each chapter.

artifact_manager/build.py reads this via
get_current_optimized_knowledge_package() /
has_current_optimized_knowledge_package() in build_reference_snapshot()
to register the last chapter\'s OptimizedKnowledgePackage into the
run-level Build.
"""
from __future__ import annotations

from typing import Optional

_current_optimized_knowledge_package: Optional[object] = None


def set_current_optimized_knowledge_package(package: object) -> None:
    """Set the chapter-scoped OptimizedKnowledgePackage."""
    global _current_optimized_knowledge_package
    _current_optimized_knowledge_package = package


def get_current_optimized_knowledge_package() -> Optional[object]:
    """Return the chapter-scoped OptimizedKnowledgePackage, or None."""
    return _current_optimized_knowledge_package


def has_current_optimized_knowledge_package() -> bool:
    """Return True iff an OptimizedKnowledgePackage has been set this chapter."""
    return _current_optimized_knowledge_package is not None


def reset_optimized_knowledge_package_state() -> None:
    """Clear the chapter-scoped OptimizedKnowledgePackage slot.

    Called by pipeline.py before each new chapter so that a previous
    chapter\'s package is never read as the current chapter\'s.
    """
    global _current_optimized_knowledge_package
    _current_optimized_knowledge_package = None
