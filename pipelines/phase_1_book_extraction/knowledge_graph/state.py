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

PHASE C4.2 ADDITION (Knowledge Graph Fingerprints & Readiness): two new
slots, `_CURRENT_REGISTRY_FINGERPRINTS` and `_CURRENT_GRAPH_FINGERPRINT`,
are added below -- the same "additive, frozen-phase-safe extension"
pattern compiler/state.py's own PHASE B5.2 ADDITION already establishes
one layer down (that module's set_current_registry_fingerprints()/
set_current_compiler_fingerprint() precedent, reused here unchanged in
shape). `_CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT` already existed as
a Phase C0 placeholder slot (see knowledge_graph/schema.py's
KnowledgeGraphReadinessReport) and is populated for the first time by
Phase C4.2 (knowledge_graph/fingerprints.py) -- no new slot or setter
was needed for it.

Not thread-safe / not concurrency-safe by design, same as
compiler/state.py's own explicit design note.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

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
# -- Phase C4.2 additions (see module docstring's PHASE C4.2 ADDITION) --
_CURRENT_REGISTRY_FINGERPRINTS: Optional[Dict[str, str]] = None
_CURRENT_GRAPH_FINGERPRINT: Optional[str] = None


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


# -- Registry Fingerprints (Phase C4.2) ---------------------------------------

def set_current_registry_fingerprints(fingerprints: Dict[str, str]) -> None:
    """Called once per chapter by pipeline.py, immediately after
    knowledge_graph.fingerprints.generate_graph_fingerprints() finishes
    fingerprinting this chapter's graph registries -- makes the per-
    registry fingerprints part of Knowledge Graph State, readable by
    any later, in-process consumer via get_current_registry_
    fingerprints(), without ever writing them into ChapterJSON. Mirrors
    compiler_state.set_current_registry_fingerprints()'s own shape one
    layer down."""
    global _CURRENT_REGISTRY_FINGERPRINTS
    _CURRENT_REGISTRY_FINGERPRINTS = fingerprints


def get_current_registry_fingerprints() -> Optional[Dict[str, str]]:
    """Returns the most recently set_current_registry_fingerprints()'d
    dict, or None if it has not been set (yet) this chapter."""
    return _CURRENT_REGISTRY_FINGERPRINTS


def has_current_registry_fingerprints() -> bool:
    """True once set_current_registry_fingerprints() has been called
    and not yet reset."""
    return _CURRENT_REGISTRY_FINGERPRINTS is not None


# -- Knowledge Graph Fingerprint (Phase C4.2) ----------------------------------

def set_current_graph_fingerprint(fingerprint: str) -> None:
    """Called once per chapter by pipeline.py, immediately after
    knowledge_graph.fingerprints.generate_graph_fingerprint() derives
    this chapter's single graph fingerprint -- makes it part of
    Knowledge Graph State, without ever writing it into ChapterJSON.
    Mirrors compiler_state.set_current_compiler_fingerprint()'s own
    shape one layer down."""
    global _CURRENT_GRAPH_FINGERPRINT
    _CURRENT_GRAPH_FINGERPRINT = fingerprint


def get_current_graph_fingerprint() -> Optional[str]:
    """Returns the most recently set_current_graph_fingerprint()'d
    value, or None if it has not been set (yet) this chapter."""
    return _CURRENT_GRAPH_FINGERPRINT


def has_current_graph_fingerprint() -> bool:
    """True once set_current_graph_fingerprint() has been called and
    not yet reset."""
    return _CURRENT_GRAPH_FINGERPRINT is not None


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
    global _CURRENT_REGISTRY_FINGERPRINTS
    global _CURRENT_GRAPH_FINGERPRINT
    _CURRENT_KNOWLEDGE_GRAPH = None
    _CURRENT_KNOWLEDGE_GRAPH_MANIFEST = None
    _CURRENT_KNOWLEDGE_GRAPH_STATISTICS = None
    _CURRENT_KNOWLEDGE_GRAPH_VALIDATION_REPORT = None
    _CURRENT_KNOWLEDGE_GRAPH_READINESS_REPORT = None
    _CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY = None
    _CURRENT_FINAL_GRAPH_STATUS = None
    _CURRENT_REGISTRY_FINGERPRINTS = None
    _CURRENT_GRAPH_FINGERPRINT = None