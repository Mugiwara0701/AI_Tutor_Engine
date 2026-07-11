"""
change_detection/engine.py — Phase E3: Change Detection Engine
generation.

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C, Phase D, Phase E0, Phase E1 (Build Metadata), and Phase E2
(Build Dependency Graph) are all frozen -- this module does not
redesign compiler/, knowledge_graph/, validation/, build_metadata/, or
dependency_graph/. It ONLY adds one more read-only pass that COMPARES
this chapter's current build (already-computed Phase E1/E2 artifacts)
against a previous build's fingerprint snapshot -- it never generates,
repairs, recomputes, or mutates a single field anywhere in the Compiler
IR, the Knowledge Graph, any earlier report, Build Metadata, the
Dependency Graph, or Chapter JSON, and it never inserts into, updates,
or removes from any Compiler IR, Knowledge Graph, or Dependency Graph
registry.

`detect_changes()` is Phase E3's own single pipeline.py integration
point (mirrors dependency_graph.build.generate_dependency_graph()'s own
"one orchestration call" shape, one phase up): snapshot -> compare ->
traverse -> report, in that order, and nothing else.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Incremental Compilation (E4), not Validation & Finalization (E5), not a
dirty-rebuild executor, not an incremental planner, not a cache, not a
persistence layer, not minimal-rebuild execution, and not build
skipping -- this module detects and reports changes and nothing else;
it never decides what should be rebuilt and never rebuilds anything
itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .compare import compare_snapshots
from .exceptions import InvalidPreviousBuildError
from .report import CHANGE_DETECTION_REPORT_VERSION, ChangeDetectionReport, build_summary
from .snapshot import build_snapshot
from .traversal import compute_affected_artifacts

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase (see e.g.
# dependency_graph/build.py's own DEPENDENCY_GRAPH_VERSION). Bump only
# if the SHAPE this module produces itself changes in a way a consumer
# of `change_detection` should be able to detect.
CHANGE_DETECTION_VERSION = "E3.1"


def _extract_previous_fingerprints(
    previous_build: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validates and unwraps `previous_build` (see module's own
    `detect_changes()` docstring for its expected shape -- exactly
    snapshot.build_snapshot()'s own return shape). Returns
    `{"fingerprints": Optional[Dict[str, str]], "warnings": List[str]}`.

    `previous_build=None` is the normal "no earlier build to compare
    against" case (module docstring; compare.py's own MISSING PREVIOUS
    BUILD note) and produces no warning. A non-`None` value that is not
    a dict, or is a dict missing `artifact_fingerprints`, is malformed
    input a caller passed by mistake -- rather than silently guessing
    at a truncated/renamed shape, this is surfaced as a warning and
    treated as "no previous build" (never raised: Phase E3 is a
    read-only reporting pass, and a malformed previous snapshot should
    degrade to "everything looks added", not abort the whole chapter's
    build)."""
    if previous_build is None:
        return {"fingerprints": None, "warnings": []}
    if not isinstance(previous_build, dict) or "artifact_fingerprints" not in previous_build:
        try:
            raise InvalidPreviousBuildError(
                "expected a dict with an 'artifact_fingerprints' key "
                "(snapshot.build_snapshot()'s own return shape)"
            )
        except InvalidPreviousBuildError as exc:
            return {"fingerprints": None, "warnings": [str(exc)]}
    return {"fingerprints": previous_build.get("artifact_fingerprints") or {}, "warnings": []}


def detect_changes(
    *,
    namespace: str,
    # Phase E2 (Build Dependency Graph), already in scope.
    dependency_graph: Optional[Dict[str, Any]],
    # Phase E1 (Build Metadata), already in scope.
    build_metadata: Optional[Dict[str, Any]],
    # Phase D3 (Release Readiness), already in scope -- needed
    # separately from `build_metadata` because BuildMetadata itself
    # only carries `release_status` (a string), not the full
    # ReleaseReadinessReport dict Phase E2's own "release_readiness"
    # DependencyNode represents -- see snapshot.py.
    release_readiness_report: Optional[Dict[str, Any]],
    # Previous build's own snapshot, in the exact shape
    # snapshot.build_snapshot() returns -- see module docstring.
    # `None` (the default, and the only value pipeline.py currently has
    # to pass, since this codebase has no persistence layer yet --
    # explicitly out of Phase E3's own scope) means "no previous build
    # to compare against."
    previous_build: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase E3's single pipeline.py integration point. Must run AFTER
    dependency_graph.build.generate_dependency_graph() (so there is a
    current DependencyGraph to snapshot and traverse) and is inserted
    immediately after Phase E2, before Chapter JSON is assembled -- see
    pipeline.py's own comment at the call site.

    Read-only over every argument, and performs no new analysis beyond
    what compare.py/traversal.py/snapshot.py themselves already do --
    see module docstring's opening SCOPE paragraph.

    `previous_build`, if supplied, must be shaped exactly like this
    same function's own returned `current_build_snapshot` (i.e.
    snapshot.build_snapshot()'s own output) -- a dict with an
    `artifact_fingerprints` map. Anything else is treated as "no
    previous build" and surfaced as a warning on the returned report
    (see `_extract_previous_fingerprints()` above), never raised.

    Returns:
        {
            "change_detection_report": <dict>,   # ready for
                                                   # change_detection.state.set_current_change_detection_report()
            "current_build_snapshot": <dict>,     # this run's own
                                                   # snapshot -- pass
                                                   # this back in as a
                                                   # future run's
                                                   # `previous_build`
        }
    """
    warnings: list = []
    errors: list = []

    if dependency_graph is None:
        warnings.append(
            "no current DependencyGraph available (Phase E2 produced nothing this "
            "chapter) -- artifact-level comparison and dependency traversal are "
            "limited to whatever the configuration/build-metadata fingerprints alone "
            "can describe."
        )
    if build_metadata is None:
        warnings.append(
            "no current BuildMetadata available (Phase E1 produced nothing this "
            "chapter) -- compiler/knowledge-graph/configuration fingerprint "
            "comparison is skipped for this build."
        )
    if release_readiness_report is None:
        warnings.append(
            "no current ReleaseReadinessReport available -- the 'release_readiness' "
            "artifact is skipped from this build's snapshot."
        )

    current_snapshot = build_snapshot(
        namespace=namespace,
        dependency_graph=dependency_graph,
        build_metadata=build_metadata,
        release_readiness_report=release_readiness_report,
    )
    current_fingerprints = current_snapshot["artifact_fingerprints"]

    previous_extraction = _extract_previous_fingerprints(previous_build)
    previous_fingerprints = previous_extraction["fingerprints"]
    warnings.extend(previous_extraction["warnings"])
    # True only when `previous_build` was both non-None AND successfully
    # parsed into a fingerprints map (possibly empty) by
    # `_extract_previous_fingerprints()` above -- `None` input and
    # malformed input both leave `previous_fingerprints` as None and
    # are equally "no previous build" from a reporting standpoint (see
    # that helper's own docstring).
    has_previous_build = previous_fingerprints is not None

    comparison = compare_snapshots(previous_fingerprints, current_fingerprints)

    changed_node_ids = comparison["added"] + comparison["modified"]
    affected_artifacts = compute_affected_artifacts(dependency_graph, changed_node_ids)
    affected_set = set(affected_artifacts)
    unchanged_artifacts = sorted(
        key for key in comparison["unchanged_candidates"] if key not in affected_set
    )

    summary = build_summary(
        added_artifacts=comparison["added"],
        removed_artifacts=comparison["removed"],
        modified_artifacts=comparison["modified"],
        affected_artifacts=affected_artifacts,
        unchanged_artifacts=unchanged_artifacts,
    )

    report = ChangeDetectionReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        change_detection_report_version=CHANGE_DETECTION_REPORT_VERSION,
        namespace=namespace,
        has_previous_build=has_previous_build,
        added_artifacts=comparison["added"],
        removed_artifacts=comparison["removed"],
        modified_artifacts=comparison["modified"],
        affected_artifacts=affected_artifacts,
        unchanged_artifacts=unchanged_artifacts,
        summary=summary,
        warnings=warnings,
        errors=errors,
    )

    return {
        "change_detection_report": report.to_dict(),
        "current_build_snapshot": current_snapshot,
    }