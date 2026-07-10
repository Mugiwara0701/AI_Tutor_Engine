"""
knowledge_graph/finalize.py — Phase C4.3: Knowledge Graph Finalization
(Knowledge Graph Build Summary & Final Graph Status).

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C0, Phase C1 (node construction), Phase C2 (edge construction),
Phase C3 (validation & integrity), Phase C4.1 (manifest & statistics),
and Phase C4.2 (fingerprints & readiness) are all frozen -- this module
does not redesign knowledge_graph/schema.py, knowledge_graph/state.py's
existing lifecycle, knowledge_graph/validation.py,
knowledge_graph/build.py, or knowledge_graph/fingerprints.py. It ONLY
adds one more read-only Knowledge Graph pass, mirroring
compiler/finalize.py's own Phase B5.3 role exactly one layer up: it
AGGREGATES what Phases C1-C4.2 already computed into one final Graph
Build Summary and one final graph status -- it never generates,
repairs, recomputes, or mutates a single field anywhere in the
Knowledge Graph, and it never inserts into, updates, or removes from
any graph registry.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Graph Queries, Graph Traversal, BFS/DFS/Shortest Path, Graph Search,
Graph Optimization, Graph Caching, a Graph Serialization redesign, a
Runtime API, Incremental Graph Builds, or Database persistence. It
performs no new validation or readiness checking of its own -- see
TASK below.

REUSE, DON'T RECOMPUTE (mirrors every earlier Knowledge Graph pass's
own rule, and compiler/finalize.py's own identical rule one layer
down): every field below is read from artifacts Phases C3/C4.1/C4.2
already produced this chapter -- `validation_report`
(knowledge_graph.validation.validate_knowledge_graph()),
`manifest`/`statistics` (knowledge_graph.build.
generate_knowledge_graph_manifest()/generate_knowledge_graph_
statistics()), and `registry_fingerprints`/`graph_fingerprint`/
`readiness_report` (knowledge_graph.fingerprints.
generate_graph_fingerprints()). Nothing in this module re-scans a
graph registry, re-derives a fingerprint, or re-validates the
Knowledge Graph a second time.

TASK 2 -- Final Graph Status: `determine_final_graph_status(...)`
derives one of READY / READY_WITH_WARNINGS / FAILED from EXACTLY TWO
already-computed artifacts -- `validation_report["overall_status"]`
(Phase C3) and `readiness_report["ready"]`/`readiness_report["warnings"]`
(Phase C4.2) -- and nothing else, mirroring compiler.finalize.
determine_final_compiler_status()'s own decision rule one layer up.
It never re-validates the graph, never re-runs a readiness check, and
never inspects a graph registry directly.

  * FAILED               -- validation did not pass, OR readiness found
                             at least one failed check.
  * READY_WITH_WARNINGS  -- validation passed AND readiness is ready,
                             but validation and/or readiness carries at
                             least one warning.
  * READY                -- validation passed, readiness is ready, and
                             neither report carries any warning.

TASK 1 -- Knowledge Graph Build Summary: `generate_graph_build_summary
(...)` returns one deterministic dict aggregating the manifest,
statistics, fingerprints, and readiness report already produced this
chapter, reusing the existing `knowledge_graph.schema.
KnowledgeGraphBuildSummary` placeholder dataclass (task's own "reuse
whenever possible" requirement -- that dataclass has existed,
unpopulated with real data, since Phase C0; see its own docstring).
Performs no new computation over the graph itself -- every field is a
read, or a small string built from already-computed reads.

TASK 5 -- Knowledge Graph Finalization: `finalize_knowledge_graph(...)`
is the one pipeline.py integration point (mirrors
knowledge_graph.build.generate_knowledge_graph_manifest()'s,
knowledge_graph.fingerprints.generate_graph_fingerprints()'s, and
compiler.finalize.finalize_compiler_build()'s own shape). It must run
AFTER knowledge_graph.fingerprints.generate_graph_fingerprints() (so
there is a readiness report / graph fingerprint to aggregate) -- see
pipeline.py's own integration comment at the call site. It runs Task 2
before Task 1 (the build summary's own `build_status` field carries
the Task 2 verdict) and returns both results together, ready to be
handed to knowledge_graph.state.set_current_knowledge_graph_build_
summary()/set_current_final_graph_status() (both already exist -- see
that module's own PHASE C4.2 ADDITION docstring section and its
`_CURRENT_KNOWLEDGE_GRAPH_BUILD_SUMMARY`/`_CURRENT_FINAL_GRAPH_STATUS`
slots, present since Phase C0 as placeholders for exactly this call).
This pass performs no analysis of its own: it only assembles artifacts
Phases C3-C4.2 already produced.

BACKWARD COMPATIBILITY: every field this module reads (from
`validation_report`, `manifest`, `statistics`, `registry_fingerprints`,
`graph_fingerprint`, `readiness_report`) is only ever read, never
changed. No existing graph registry, node, edge, manifest, statistics,
fingerprint, readiness report, Compiler IR, or Educational JSON output
changes as a result of this module existing. The only new Knowledge
Graph artifacts are the build summary dict and the final status string
-- both stored using knowledge_graph/state.py's own pre-existing
get/set/has functions, which this module does not modify.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .registries import GraphRegistryManager
from .schema import KnowledgeGraphBuildSummary

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of every earlier phase's
# own *_VERSION constant, and of compiler.finalize.FINALIZE_VERSION,
# which versions the Compiler's own build summary shape). Bump only if
# the build-summary/final-status SHAPE this file produces itself
# changes in a way a consumer of `build_summary`/`final_status` should
# be able to detect -- mirrors compiler/finalize.py's own
# FINALIZE_VERSION precedent, one layer up.
GRAPH_FINALIZE_VERSION = "1.0.0"

# The three allowed Final Graph Status values (task's own closed set) --
# reused unchanged from compiler.finalize's own STATUS_* constants'
# naming convention, one layer down.
STATUS_READY = "READY"
STATUS_READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
STATUS_FAILED = "FAILED"


# --------------------------------------------------------------------------
# Task 2: Final Graph Status
# --------------------------------------------------------------------------

def determine_final_graph_status(
    validation_report: Optional[Dict[str, Any]],
    readiness_report: Optional[Dict[str, Any]],
) -> str:
    """Phase C4.3 Task 2. Derived ONLY from `validation_report`
    (Phase C3's own verdict -- read via its `overall_status` key, the
    same key knowledge_graph.fingerprints.generate_graph_readiness_
    report()'s own "graph_validation_passed" check already reads) and
    `readiness_report` (Phase C4.2's own verdict) -- never performs
    additional validation, never re-runs a readiness check, never
    touches a graph registry. See module docstring's TASK 2 section for
    the exact decision rule.

    Missing input (None) is treated the same as a failing verdict for
    that input -- a graph that never validated, or was never assessed
    for readiness, cannot be reported READY or READY_WITH_WARNINGS.
    """
    validation_status = (validation_report or {}).get("overall_status")
    validation_passed = validation_status == "pass"

    ready = bool(readiness_report) and bool(readiness_report.get("ready"))

    if not validation_passed or not ready:
        return STATUS_FAILED

    warning_count = len((validation_report or {}).get("warnings") or []) + len(
        (readiness_report or {}).get("warnings") or []
    )
    if warning_count:
        return STATUS_READY_WITH_WARNINGS
    return STATUS_READY


# --------------------------------------------------------------------------
# Task 1: Knowledge Graph Build Summary
# --------------------------------------------------------------------------

def generate_graph_build_summary(
    graph_registry_manager: GraphRegistryManager,
    validation_report: Optional[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    graph_fingerprint: Optional[str],
    readiness_report: Optional[Dict[str, Any]],
    final_status: str,
) -> Dict[str, Any]:
    """Phase C4.3 Task 1. Aggregates the manifest, statistics,
    fingerprints, and readiness report already produced this chapter --
    never recomputes any of them. `graph_registry_manager` is accepted
    only so `total_node_registries` can fall back to the manager's own
    cheap aggregate accessor (`.names()`) the same way
    generate_graph_build_summary()'s Compiler analogue
    (compiler.finalize.generate_compiler_build_summary()) falls back to
    `manager.names()`/`manager.total_size()` -- never by iterating every
    registry's items itself.

    `final_status` is Task 2's own verdict, computed once by the caller
    (finalize_knowledge_graph() below) and threaded through here so this
    module derives it exactly once -- never a second, independently
    computed judgment.

    Read-only over every argument. Returned as a plain dict
    (summary.to_dict(), where `summary` is a reused
    `knowledge_graph.schema.KnowledgeGraphBuildSummary` instance --
    Task 1's own "reuse the existing placeholder" requirement),
    matching every earlier artifact's own "plain, storable dict"
    convention.
    """
    manifest = manifest or {}
    statistics = statistics or {}
    readiness_report = readiness_report or {}
    validation_report = validation_report or {}

    graph_schema_version = manifest.get(
        "graph_schema_version", KnowledgeGraphBuildSummary().graph_schema_version
    )
    identity_version = manifest.get(
        "identity_version", KnowledgeGraphBuildSummary().identity_version
    )
    # Same carry-forward pattern knowledge_graph/build.py's own
    # `KnowledgeGraphManifest.graph_status` and compiler/finalize.py's
    # own `compiler_status` precedent already document: `graph_status`
    # here is manifest generation's own "did generation complete"
    # verdict, exposed under this artifact's own field name -- never a
    # second, independently-computed judgment, and never confused with
    # `build_status` below (see schema.py's own KnowledgeGraphBuildSummary
    # docstring for why this distinction is deliberate).
    graph_status = manifest.get("graph_status", "unbuilt")

    total_node_registries = len(graph_registry_manager.names())
    total_nodes = manifest.get("node_count", statistics.get("total_nodes", 0))
    total_edges = manifest.get("edge_count", statistics.get("total_edges", 0))

    validation_summary = {
        "status": validation_report.get("overall_status", validation_report.get("status", "unknown")),
        "error_count": len(validation_report.get("errors") or []),
        "warning_count": len(validation_report.get("warnings") or []),
    }
    readiness_summary = dict(
        readiness_report.get("readiness_summary")
        or {
            "total_checks": 0,
            "passed_count": 0,
            "failed_count": 0,
            "warning_count": 0,
        }
    )

    overall_summary = (
        f"Knowledge Graph build {final_status}: {total_node_registries} "
        f"registr{'y' if total_node_registries == 1 else 'ies'}, "
        f"{total_nodes} node{'s' if total_nodes != 1 else ''}, "
        f"{total_edges} edge{'s' if total_edges != 1 else ''}; "
        f"validation={validation_summary['status']} "
        f"({validation_summary['error_count']} error(s), "
        f"{validation_summary['warning_count']} warning(s)); "
        f"readiness={'ready' if readiness_report.get('ready') else 'not ready'} "
        f"({readiness_summary.get('passed_count', 0)}/"
        f"{readiness_summary.get('total_checks', 0)} checks passed)."
    )

    summary = KnowledgeGraphBuildSummary(
        generated_at=datetime.now(timezone.utc).isoformat(),
        graph_schema_version=graph_schema_version,
        identity_version=identity_version,
        graph_status=graph_status,
        build_status=final_status,
        total_node_registries=total_node_registries,
        total_nodes=total_nodes,
        total_edges=total_edges,
        validation_summary=validation_summary,
        readiness_summary=readiness_summary,
        graph_fingerprint=graph_fingerprint,
        overall_summary=overall_summary,
    )
    return summary.to_dict()


# --------------------------------------------------------------------------
# Task 5: Pipeline Integration -- the one pass pipeline.py calls
# --------------------------------------------------------------------------

def finalize_knowledge_graph(
    graph_registry_manager: GraphRegistryManager,
    *,
    validation_report: Optional[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    graph_fingerprint: Optional[str],
    readiness_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase C4.3's single pipeline.py integration point (mirrors
    knowledge_graph.fingerprints.generate_graph_fingerprints()'s and
    compiler.finalize.finalize_compiler_build()'s own shape). Must run
    AFTER knowledge_graph.fingerprints.generate_graph_fingerprints()
    (so `readiness_report`/`graph_fingerprint` are available to
    aggregate) -- see module docstring's TASK 5 section and pipeline.py's
    own comment at the call site.

    Runs Task 2 (final status) before Task 1 (build summary), since the
    build summary's own `build_status` field carries the Task 2 verdict,
    and returns both together as one plain dict, ready to be handed to
    knowledge_graph.state.set_current_knowledge_graph_build_summary()/
    set_current_final_graph_status() (both already exist -- see module
    docstring's TASK 5 section).

    Read-only over every argument, and performs no new analysis of its
    own -- see module docstring's opening SCOPE paragraph. No graph
    mutation, no side effects.
    """
    final_status = determine_final_graph_status(validation_report, readiness_report)
    build_summary = generate_graph_build_summary(
        graph_registry_manager,
        validation_report,
        manifest,
        statistics,
        registry_fingerprints,
        graph_fingerprint,
        readiness_report,
        final_status,
    )
    return {
        "graph_build_summary": build_summary,
        "graph_final_status": final_status,
    }
