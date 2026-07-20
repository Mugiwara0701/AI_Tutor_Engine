"""
modules/master_knowledge_compiler/state.py — M5.3: chapter-scoped
MasterKnowledgePackage state.

Follows the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() convention every other phase in this codebase uses
(compiler/state.py, knowledge_graph/state.py, document_structure_tree/
state.py, dependency_graph/state.py, change_detection/state.py,
incremental_compilation/state.py, build_metadata/state.py, and
validation/state.py all use the same pattern). Chapter-scoped:
reset_*_state() is called before each chapter, so a new chapter's
MasterKnowledgePackage never collides with the previous chapter's.

artifact_manager/build.py reads this via get_current_master_knowledge_package()
/ has_current_master_knowledge_package() in build_reference_snapshot() to
register the last chapter's MasterKnowledgePackage into the run-level Build.
"""
from __future__ import annotations

from typing import Optional

_current_master_knowledge_package: Optional[object] = None


def set_current_master_knowledge_package(package: object) -> None:
    """Set the chapter-scoped MasterKnowledgePackage."""
    global _current_master_knowledge_package
    _current_master_knowledge_package = package


def get_current_master_knowledge_package() -> Optional[object]:
    """Return the chapter-scoped MasterKnowledgePackage, or None."""
    return _current_master_knowledge_package


def has_current_master_knowledge_package() -> bool:
    """Return True iff a MasterKnowledgePackage has been set this chapter."""
    return _current_master_knowledge_package is not None


def reset_master_knowledge_package_state() -> None:
    """Clear the chapter-scoped MasterKnowledgePackage slot.

    Called by pipeline.py before each new chapter so that a previous
    chapter\'s package is never read as the current chapter\'s.
    """
    global _current_master_knowledge_package
    _current_master_knowledge_package = None
