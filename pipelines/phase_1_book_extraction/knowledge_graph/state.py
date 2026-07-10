"""
knowledge_graph/state.py — Phase C0: Knowledge Graph State lifecycle.

Reuses the exact "current compilation state" module-level-slot idiom
compiler/state.py already established for Compiler IR (that module's own
docstring: "the same established idiom... a module-level slot, set once
per chapter, read by any later phase that needs it, and reset before the
next chapter starts"). Applied here, unmodified in shape, to the seven
Knowledge Graph artifacts knowledge_graph/schema.py declares
(KnowledgeGraph, KnowledgeGraphManifest, KnowledgeGraphStatistics,
KnowledgeGraphValidationReport, KnowledgeGraphReadinessReport,
KnowledgeGraphBuildSummary, and the final graph status string) -- see
schema.py's own `KnowledgeGraphState` dataclass for the documented shape
these seven slots collectively form.

OWNERSHIP / LIFECYCLE: identical contract to compiler/state.py's own,
one layer up:

  1. A future C1+ pipeline step calls reset_knowledge_graph_state() at
     the start of Knowledge Graph construction for a chapter, so a
     failed or skipped graph build never leaves a stale graph from the
     previous chapter visible as "current".
  2. That pipeline builds a fresh KnowledgeGraph (via a future
     knowledge_graph.build module -- does not exist yet, see
     docs/knowledge_graph_architecture.md's Pipeline section) and calls
     set_current_knowledge_graph() once it is complete.
  3. Every get_current_*() function below returns that exact instance
     (not a copy) to any later, in-process consumer, until the next
     reset.

Phase C0 itself NEVER calls any set_current_*() function in this module
-- every slot stays at its default (None) for the lifetime of Phase C0.
This module is purely the lifecycle plumbing a future C-phase will use,
exactly as compiler/state.py was purely plumbing at Phase B0/B1 before
any later phase actually called its setters with real data.

Not thread-safe / not concurrency-safe by design, same as
compiler/state.py's own explicit design note.
"""
from __future__ import annotations

from typing import Optional

from .schema import (
    KnowledgeGraph,
    KnowledgeGraphManifest,
    KnowledgeGraphStatistics,
    KnowledgeGraphValidationReport,
    KnowledgeGraphReadinessReport,
    KnowledgeGraphBuildSummary,
)

# --------------------------------------------------------------------------
# Current chapter's Knowledge Graph artifacts. Each slot mirrors one
# compiler/state.py slot, one for one -- see that module's own
# PHASE B5.1/B5.2/B5.3 ADDITION docstring sections for the precedent
# this directly follows.
# --------------------------------------------------------------------------
_CURRENT_KNOWLEDGE_GRAPH: Optional[KnowledgeGraph] = None
_CURRENT_KNOWLEDGE_GRAPH_MANIFEST: Optional[KnowledgeGraphManifest] = None
_CURRENT_KNOWLEDGE_GRAPH_STATISTICS: Optional[KnowledgeGraphStatistics] = None
_CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT: Optional[KnowledgeGraphValidationReport] = None
_CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT: Optional[KnowledgeGraphReadinessReport] = None
_CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY: Optional[KnowledgeGraphBuildSummary] = None
_CURRENT_FINAL_GRAPH_STATUS: Optional[str] = None


# -- KnowledgeGraph ---------------------------------------------------------

def set_current_knowledge_graph(graph: KnowledgeGraph) -> None:
    global _CURRENT_KNOWLEDGE_GRAPH
    _CURRENT_KNOWLEDGE_GRAPH = graph


def get_current_knowledge_graph() -> Optional[KnowledgeGraph]:
    return _CURRENT_KNOWLEDGE_GRAPH


def has_current_knowledge_graph() -> bool:
    return _CURRENT_KNOWLEDGE_GRAPH is not None


# -- KnowledgeGraphManifest ---------------------------------------------------

def set_current_knowledge_graph_manifest(manifest: KnowledgeGraphManifest) -> None:
    global _CURRENT_KNOWLEDGE_GRAPH_MANIFEST
    _CURRENT_KNOWLEDGE_GRAPH_MANIFEST = manifest


def get_current_knowledge_graph_manifest() -> Optional[KnowledgeGraphManifest]:
    return _CURRENT_KNOWLEDGE_GRAPH_MANIFEST


def has_current_knowledge_graph_manifest() -> bool:
    return _CURRENT_KNOWLEDGE_GRAPH_MANIFEST is not None


# -- KnowledgeGraphStatistics -------------------------------------------------

def set_current_knowledge_graph_statistics(statistics: KnowledgeGraphStatistics) -> None:
    global _CURRENT_KNOWLEDGE_GRAPH_STATISTICS
    _CURRENT_KNOWLEDGE_GRAPH_STATISTICS = statistics


def get_current_knowledge_graph_statistics() -> Optional[KnowledgeGraphStatistics]:
    return _CURRENT_KNOWLEDGE_GRAPH_STATISTICS


def has_current_knowledge_graph_statistics() -> bool:
    return _CURRENT_KNOWLEDGE_GRAPH_STATISTICS is not None


# -- KnowledgeGraphValidationReport -------------------------------------------

def set_current_knowledge_graph_validation_report(
    report: KnowledgeGraphValidationReport,
) -> None:
    global _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT
    _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT = report


def get_current_knowledge_graph_validation_report() -> Optional[KnowledgeGraphValidationReport]:
    return _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT


def has_current_knowledge_graph_validation_report() -> bool:
    return _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT is not None


# -- KnowledgeGraphReadinessReport --------------------------------------------

def set_current_knowledge_graph_readiness_report(
    report: KnowledgeGraphReadinessReport,
) -> None:
    global _CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT
    _CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT = report


def get_current_knowledge_graph_readiness_report() -> Optional[KnowledgeGraphReadinessReport]:
    return _CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT


def has_current_knowledge_graph_readiness_report() -> bool:
    return _CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT is not None


# -- KnowledgeGraphBuildSummary ------------------------------------------------

def set_current_knowledge_graph_build_summary(summary: KnowledgeGraphBuildSummary) -> None:
    global _CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY
    _CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY = summary


def get_current_knowledge_graph_build_summary() -> Optional[KnowledgeGraphBuildSummary]:
    return _CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY


def has_current_knowledge_graph_build_summary() -> bool:
    return _CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY is not None


# -- Final Graph Status -------------------------------------------------------

def set_current_final_graph_status(status: str) -> None:
    global _CURRENT_FINAL_GRAPH_STATUS
    _CURRENT_FINAL_GRAPH_STATUS = status


def get_current_final_graph_status() -> Optional[str]:
    return _CURRENT_FINAL_GRAPH_STATUS


def has_current_final_graph_status() -> bool:
    return _CURRENT_FINAL_GRAPH_STATUS is not None


# -- Reset --------------------------------------------------------------------

def reset_knowledge_graph_state() -> None:
    """Clears every Knowledge Graph state slot together -- the one
    function a future C-phase pipeline calls once per chapter, mirroring
    compiler.state.reset_registry_state()'s own role exactly. Safe to
    call even if no slot was ever set (idempotent)."""
    global _CURRENT_KNOWLEDGE_GRAPH
    global _CURRENT_KNOWLEDGE_GRAPH_MANIFEST
    global _CURRENT_KNOWLEDGE_GRAPH_STATISTICS
    global _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT
    global _CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT
    global _CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY
    global _CURRENT_FINAL_GRAPH_STATUS
    _CURRENT_KNOWLEDGE_GRAPH = None
    _CURRENT_KNOWLEDGE_GRAPH_MANIFEST = None
    _CURRENT_KNOWLEDGE_GRAPH_STATISTICS = None
    _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT = None
    _CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT = None
    _CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY = None
    _CURRENT_FINAL_GRAPH_STATUS = None