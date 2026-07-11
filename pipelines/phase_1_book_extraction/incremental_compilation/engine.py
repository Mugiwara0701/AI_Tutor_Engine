"""
incremental_compilation/engine.py — Phase E4: Incremental Compilation
Engine.

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C, Phase D, Phase E0, Phase E1 (Build Metadata), Phase E2 (Build
Dependency Graph), and Phase E3 (Change Detection) are all frozen --
this module does not redesign compiler/, knowledge_graph/, validation/,
build_metadata/, dependency_graph/, or change_detection/. It ONLY adds
one more read-only pass that PLANS which of this chapter's build
artifacts require rebuilding, given Phase E3's own ChangeDetectionReport
and Phase E2's own DependencyGraph -- it never generates, repairs,
recomputes, or mutates a single field anywhere in the Compiler IR, the
Knowledge Graph, any earlier report, Build Metadata, the Dependency
Graph, the Change Detection Report, or Chapter JSON, and it never
inserts into, updates, or removes from any Compiler IR, Knowledge
Graph, or Dependency Graph registry.

`plan_incremental_compilation()` is Phase E4's own single pipeline.py
integration point (mirrors change_detection.engine.detect_changes()'s
own "one orchestration call" shape, one phase up): classify -> order ->
reason -> report, in that order, and nothing else.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Phase E5 (Validation & Finalization of the incremental plan itself),
not a compilation executor, not a cache, not a persistence layer, not
distributed execution, not parallel scheduling, and not an actual
rebuild of anything -- this module plans and reports, and nothing
else; it never decides to skip a build step on its own initiative and
never rebuilds anything itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .plan import INCREMENTAL_COMPILATION_PLAN_VERSION, IncrementalCompilationPlan, build_summary
from .planner import plan_rebuild

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase (see e.g.
# change_detection/engine.py's own CHANGE_DETECTION_VERSION). Bump only
# if the SHAPE this module produces itself changes in a way a consumer
# of `incremental_compilation` should be able to detect.
INCREMENTAL_COMPILATION_VERSION = "E4.1"


def plan_incremental_compilation(
    *,
    namespace: str,
    # Phase E3 (Change Detection), already in scope.
    change_detection_report: Optional[Dict[str, Any]],
    # Phase E2 (Build Dependency Graph), already in scope.
    dependency_graph: Optional[Dict[str, Any]],
    # Phase E1 (Build Metadata), already in scope -- read for
    # provenance/context only (see PROVENANCE, NOT COMPUTATION below);
    # no field of it drives any classification or ordering decision
    # this module makes.
    build_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase E4's single pipeline.py integration point. Must run AFTER
    change_detection.engine.detect_changes() (so there is a current
    ChangeDetectionReport to plan from) and is inserted immediately
    after Phase E3, before Chapter JSON is assembled -- see pipeline.py's
    own comment at the call site.

    Read-only over every argument, and performs no new comparison and
    no new affected-artifact derivation beyond what planner.py itself
    already does (a single dirty/affected union plus a rebuild-order
    traversal) -- see module docstring's opening SCOPE paragraph and
    planner.py's own REUSE, DON'T RECOMPUTE section.

    PROVENANCE, NOT COMPUTATION: `build_metadata` is accepted (per the
    task's own "Read: Change Detection Report, Build Dependency Graph,
    Build Metadata" instruction) and its three top-level fingerprints
    are copied into the returned plan's own `build_provenance` field,
    purely as provenance context (module docstring's PROVENANCE NOTE
    below) -- so a consumer of this one plan can tell, without a
    second lookup, which compiler/graph/configuration build it was
    computed against. Nothing about which artifacts are dirty, clean,
    affected, or in what order they rebuild is ever derived from
    `build_metadata` -- that classification is entirely
    change_detection_report's and dependency_graph's own, per
    planner.py.

    Returns:
        {
            "incremental_compilation_plan": <dict>,   # ready for
                # incremental_compilation.state.
                # set_current_incremental_compilation_plan()
        }
    """
    plan_result = plan_rebuild(
        namespace=namespace,
        change_detection_report=change_detection_report,
        dependency_graph=dependency_graph,
    )

    # PROVENANCE NOTE: read-only, best-effort context copied from
    # Phase E1's own already-computed fingerprints -- never re-derived,
    # and absent entirely (rather than fabricated as None-valued keys)
    # when `build_metadata` itself is None, mirroring
    # dependency_graph/build.py's own "reuse, don't fabricate" rule.
    build_provenance: Dict[str, Any] = {}
    if build_metadata is not None:
        compiler_metadata = build_metadata.get("compiler_metadata") or {}
        graph_metadata = build_metadata.get("graph_metadata") or {}
        configuration_metadata = build_metadata.get("configuration_metadata") or {}
        build_provenance = {
            "compiler_fingerprint": compiler_metadata.get("compiler_fingerprint"),
            "graph_fingerprint": graph_metadata.get("graph_fingerprint"),
            "configuration_fingerprint": configuration_metadata.get(
                "configuration_fingerprint"
            ),
        }

    summary = build_summary(
        dirty_artifacts=plan_result["dirty_artifacts"],
        affected_artifacts=plan_result["affected_artifacts"],
        rebuild_artifacts=plan_result["rebuild_artifacts"],
        clean_artifacts=plan_result["clean_artifacts"],
        removed_artifacts=plan_result["removed_artifacts"],
    )

    plan = IncrementalCompilationPlan(
        generated_at=datetime.now(timezone.utc).isoformat(),
        incremental_compilation_plan_version=INCREMENTAL_COMPILATION_PLAN_VERSION,
        namespace=namespace,
        has_previous_build=plan_result["has_previous_build"],
        dirty_artifacts=plan_result["dirty_artifacts"],
        affected_artifacts=plan_result["affected_artifacts"],
        rebuild_artifacts=plan_result["rebuild_artifacts"],
        clean_artifacts=plan_result["clean_artifacts"],
        removed_artifacts=plan_result["removed_artifacts"],
        rebuild_order=plan_result["rebuild_order"],
        rebuild_reasons=plan_result["rebuild_reasons"],
        reuse_reasons=plan_result["reuse_reasons"],
        dependency_traversal_summary=plan_result["dependency_traversal_summary"],
        build_provenance=build_provenance,
        summary=summary,
        warnings=plan_result["warnings"],
        errors=plan_result["errors"],
    )

    return {"incremental_compilation_plan": plan.to_dict()}