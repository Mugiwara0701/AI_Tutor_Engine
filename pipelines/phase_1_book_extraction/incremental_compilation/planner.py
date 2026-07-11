"""
incremental_compilation/planner.py — Phase E4: Minimal Rebuild
Planner.

SCOPE: `plan_rebuild()` is a pure function of Phase E3's own
ChangeDetectionReport and Phase E2's own DependencyGraph -- no I/O, no
registry access, no re-derivation of anything either phase already
computed. It:

  1. Reads dirty / affected / clean / removed classification straight
     off Phase E3's own report (compare.py's/traversal.py's own
     results, already computed -- see REUSE, DON'T RECOMPUTE below).
  2. Unions dirty + affected into the rebuild set.
  3. Calls incremental_compilation.traversal.compute_rebuild_order()
     for a dependency-safe rebuild order over that set (Phase E4's own
     new graph question -- see that module).
  4. Attaches a human-readable reason to every rebuild and every clean
     artifact.

REUSE, DON'T RECOMPUTE (task's own explicit requirement, "Reuse the
Change Detection Report. Never modify it. Never rerun Change
Detection."): this module never calls change_detection.compare.
compare_snapshots() or change_detection.traversal.
compute_affected_artifacts() itself -- `added_artifacts`/
`removed_artifacts`/`modified_artifacts`/`affected_artifacts`/
`unchanged_artifacts` are read directly off the `change_detection_report`
argument, exactly as Phase E3 already computed them. Phase E4's own,
new computation is limited to (a) the dirty union affected set (a
single `set.union()`, not a re-comparison) and (b) rebuild ORDER +
per-artifact REASON text, neither of which Phase E3 ever produces.

READ-ONLY: every argument is read, never mutated; nothing here inserts
into, updates, or removes from any registry, DependencyGraph, or
ChangeDetectionReport.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .exceptions import InvalidChangeDetectionReportError
from .traversal import compute_rebuild_order

_REQUIRED_REPORT_KEYS = (
    "added_artifacts",
    "removed_artifacts",
    "modified_artifacts",
    "affected_artifacts",
    "unchanged_artifacts",
    "has_previous_build",
)


def _extract_change_detection_lists(
    change_detection_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validates and unwraps `change_detection_report` (expected shape:
    exactly change_detection.report.ChangeDetectionReport.to_dict()'s
    own output). Returns a dict of the five classification lists plus
    `has_previous_build`, plus a `warnings` list.

    `change_detection_report=None` is the normal "Phase E3 produced
    nothing this chapter" case (mirrors change_detection.engine.
    detect_changes()'s own `dependency_graph is None`/`build_metadata
    is None` handling one phase down) and produces a warning (Phase E4
    genuinely has nothing to plan without it), never an error. A
    non-`None` value missing one of the fields this module reads is
    malformed input a caller passed by mistake -- rather than silently
    guessing at a truncated/renamed shape, this is surfaced as a
    warning and treated as "nothing to plan" (never raised: Phase E4 is
    a read-only planning pass, and a malformed report should degrade to
    an empty plan, not abort the whole chapter's build)."""
    empty = {key: ([] if key != "has_previous_build" else False) for key in _REQUIRED_REPORT_KEYS}
    if change_detection_report is None:
        return {
            **empty,
            "warnings": [
                "no current ChangeDetectionReport available (Phase E3 produced "
                "nothing this chapter) -- rebuild/clean classification is skipped "
                "entirely for this build."
            ],
        }
    if not isinstance(change_detection_report, dict) or not all(
        key in change_detection_report for key in _REQUIRED_REPORT_KEYS
    ):
        try:
            raise InvalidChangeDetectionReportError(
                "expected a dict shaped like "
                "change_detection.report.ChangeDetectionReport.to_dict()'s "
                "own output (missing one or more of "
                f"{_REQUIRED_REPORT_KEYS!r})"
            )
        except InvalidChangeDetectionReportError as exc:
            return {**empty, "warnings": [str(exc)]}
    return {
        "added_artifacts": change_detection_report.get("added_artifacts") or [],
        "removed_artifacts": change_detection_report.get("removed_artifacts") or [],
        "modified_artifacts": change_detection_report.get("modified_artifacts") or [],
        "affected_artifacts": change_detection_report.get("affected_artifacts") or [],
        "unchanged_artifacts": change_detection_report.get("unchanged_artifacts") or [],
        "has_previous_build": bool(change_detection_report.get("has_previous_build")),
        "warnings": [],
    }


def _direct_rebuilding_dependencies(
    dependency_graph: Optional[Dict[str, Any]], node_id: str, rebuild_set
) -> List[str]:
    """For one `node_id` in the rebuild set, returns the sorted list of
    its own DIRECT dependencies (edges where `source_node_id ==
    node_id`) that are themselves in `rebuild_set` -- used to phrase an
    "affected" artifact's own rebuild reason concretely (module
    docstring: this is a single edge-hop lookup, not a second
    multi-hop traversal duplicating change_detection.traversal.
    compute_affected_artifacts()'s own reverse-BFS -- that BFS already
    determined SET membership in Phase E3; this function only adds a
    one-hop explanation on top of a membership Phase E4 already
    trusts)."""
    edges = (dependency_graph or {}).get("edges") or []
    direct = {
        edge.get("target_node_id")
        for edge in edges
        if edge.get("source_node_id") == node_id
        and edge.get("target_node_id") in rebuild_set
    }
    return sorted(d for d in direct if d is not None)


def _rebuild_reason(
    node_id: str,
    *,
    added: set,
    modified: set,
    dependency_graph: Optional[Dict[str, Any]],
    rebuild_set,
) -> str:
    """One human-readable reason string per rebuild artifact -- exactly
    one of three shapes, never a fourth invented category:
    "added"/"modified" (Phase E3's own dirty classification, read
    verbatim) or "affected" (Phase E3's own affected classification,
    with a same-run, single-hop dependency lookup added for
    concreteness -- see `_direct_rebuilding_dependencies()` above)."""
    if node_id in added:
        return "added: no previous build had a fingerprint for this artifact"
    if node_id in modified:
        return "modified: fingerprint differs from the previous build"
    causes = _direct_rebuilding_dependencies(dependency_graph, node_id, rebuild_set)
    if causes:
        return (
            "affected: depends on artifact(s) requiring rebuild -- "
            f"{causes!r}"
        )
    return (
        "affected: transitively depends on a changed artifact "
        "(no direct rebuilding dependency in this DependencyGraph -- "
        "see change_detection's own affected_artifacts for the full "
        "transitive chain)"
    )


def plan_rebuild(
    *,
    namespace: str,
    change_detection_report: Optional[Dict[str, Any]],
    dependency_graph: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase E4's Minimal Rebuild Planner. Read-only over both
    arguments; performs no new comparison and no new affected-set
    derivation (module docstring's REUSE, DON'T RECOMPUTE) -- its only
    new computation is the dirty/affected union, the rebuild order
    (traversal.py), and per-artifact reason text.

    Returns a dict with every field
    incremental_compilation.plan.IncrementalCompilationPlan needs
    beyond `namespace`/`generated_at`/version stamping (those are
    engine.py's own job, mirroring change_detection.engine.
    detect_changes()'s own division of labor with report.py one phase
    down)."""
    warnings: List[str] = []
    errors: List[str] = []

    if dependency_graph is None:
        warnings.append(
            "no current DependencyGraph available (Phase E2 produced nothing this "
            "chapter) -- rebuild order falls back to a deterministic, "
            "alphabetically-sorted order with no dependency-safety guarantee."
        )

    extracted = _extract_change_detection_lists(change_detection_report)
    warnings.extend(extracted["warnings"])

    added = set(extracted["added_artifacts"])
    modified = set(extracted["modified_artifacts"])
    affected = extracted["affected_artifacts"]
    removed_artifacts = sorted(set(extracted["removed_artifacts"]))
    clean_artifacts = sorted(set(extracted["unchanged_artifacts"]))
    has_previous_build = extracted["has_previous_build"]

    dirty_artifacts = sorted(added | modified)
    affected_artifacts = sorted(set(affected))
    rebuild_set = set(dirty_artifacts) | set(affected_artifacts)
    rebuild_artifacts = sorted(rebuild_set)

    order_result = compute_rebuild_order(dependency_graph, rebuild_set)
    if order_result["cycle_detected"]:
        errors.append(
            "cycle detected in the rebuild subgraph among: "
            f"{order_result['cycle_node_ids']!r} -- these artifacts were still "
            "included in rebuild_order, in deterministic alphabetical order, "
            "but their relative dependency ordering could not be resolved."
        )

    rebuild_reasons: Dict[str, str] = {
        node_id: _rebuild_reason(
            node_id,
            added=added,
            modified=modified,
            dependency_graph=dependency_graph,
            rebuild_set=rebuild_set,
        )
        for node_id in rebuild_artifacts
    }
    reuse_reasons: Dict[str, str] = {
        node_id: (
            "unchanged: fingerprint identical to the previous build and no "
            "rebuilding dependency"
        )
        for node_id in clean_artifacts
    }

    dependency_traversal_summary = {
        "graph_node_count": len((dependency_graph or {}).get("nodes") or []),
        "graph_edge_count": len((dependency_graph or {}).get("edges") or []),
        "rebuild_subgraph_edge_count": order_result["edges_considered"],
        "cycle_detected": order_result["cycle_detected"],
        "cycle_node_ids": order_result["cycle_node_ids"],
    }

    return {
        "has_previous_build": has_previous_build,
        "dirty_artifacts": dirty_artifacts,
        "affected_artifacts": affected_artifacts,
        "rebuild_artifacts": rebuild_artifacts,
        "clean_artifacts": clean_artifacts,
        "removed_artifacts": removed_artifacts,
        "rebuild_order": order_result["order"],
        "rebuild_reasons": rebuild_reasons,
        "reuse_reasons": reuse_reasons,
        "dependency_traversal_summary": dependency_traversal_summary,
        "warnings": warnings,
        "errors": errors,
    }