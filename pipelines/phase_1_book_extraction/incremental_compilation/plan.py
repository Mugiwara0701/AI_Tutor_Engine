"""
incremental_compilation/plan.py — Phase E4: Incremental Compilation
Plan.

SCOPE: `IncrementalCompilationPlan` is the full Phase E4 artifact --
purely a data holder, matching every earlier phase's own "dataclass +
to_dict(), all actual computation happens in the owning
build.py/engine.py/planner.py" convention (compiler/build.py's
CompilerManifest, dependency_graph/schema.py's DependencyGraph,
change_detection/report.py's ChangeDetectionReport). All construction
happens in planner.py's `plan_rebuild()`, orchestrated by engine.py's
`plan_incremental_compilation()`.

READ-ONLY REPORTING (mirrors change_detection/report.py's own
ChangeDetectionReport precedent exactly, one phase up): this plan
describes what must be rebuilt and why, and what can be reused and why
-- it never rebuilds, executes, caches, or schedules a single one of
them. A `warnings`/`errors` entry is reported, never acted on.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase. Bump only if the PLAN SHAPE this
# module produces itself changes in a way a consumer should be able to
# detect.
INCREMENTAL_COMPILATION_PLAN_VERSION = "E4.1"


@dataclass
class IncrementalCompilationPlan:
    """The full Phase E4 artifact.

    FIELD NOTES:
    - `namespace`: the same `chapter_reference` every earlier Phase
      B-E3 artifact for this chapter already uses -- reused unchanged,
      never a second, independently computed namespace.
    - `has_previous_build`: read straight off Phase E3's own
      ChangeDetectionReport.has_previous_build, unchanged -- Phase E4
      never re-derives this.
    - `dirty_artifacts`: Phase E3's own `added_artifacts` +
      `modified_artifacts`, unioned and sorted -- artifacts that must
      rebuild because THEIR OWN fingerprint changed (or is new).
    - `affected_artifacts`: Phase E3's own `affected_artifacts`,
      reused verbatim -- artifacts that must rebuild because something
      they depend on changed, even though their own fingerprint did
      not move.
    - `rebuild_artifacts`: `dirty_artifacts` union `affected_artifacts`
      -- every artifact this plan says must be rebuilt, sorted. This
      is the plan's own single source of truth for "what needs
      rebuilding"; `rebuild_order` below is the same set, reordered
      for dependency-safe execution, never a second, independently
      determined set.
    - `clean_artifacts`: Phase E3's own `unchanged_artifacts`, reused
      verbatim -- artifacts that need no rebuild at all.
    - `removed_artifacts`: Phase E3's own `removed_artifacts`, reused
      verbatim -- present in a previous build, absent from the current
      DependencyGraph. Surfaced for visibility only: an artifact with
      no current node cannot be "rebuilt" (there is nothing to rebuild
      it INTO), and is therefore never a member of `rebuild_artifacts`
      or `rebuild_order` (mirrors change_detection/traversal.py's own
      "REMOVED ARTIFACTS ARE NOT TRAVERSED" rule, one phase up).
    - `rebuild_order`: `rebuild_artifacts`, reordered into a
      dependency-safe rebuild sequence by
      incremental_compilation.traversal.compute_rebuild_order() over
      Phase E2's own DependencyGraph -- see that module for the
      algorithm and its own determinism/cycle-handling guarantees.
    - `rebuild_reasons`: `{artifact_key: reason string}` for every
      entry in `rebuild_artifacts` -- "added"/"modified" for a dirty
      artifact, or "affected via <direct dependency ids>" for an
      artifact that is only in the rebuild set transitively.
    - `reuse_reasons`: `{artifact_key: reason string}` for every entry
      in `clean_artifacts` -- always "unchanged" text in the current
      implementation (Phase E4 has exactly one reason an artifact is
      reusable: its own fingerprint didn't move and nothing it depends
      on rebuilds), kept as a mapping rather than a constant so a
      future, more granular Phase E4 refinement can add detail per
      artifact without changing this field's shape.
    - `dependency_traversal_summary`: small, denormalized detail about
      the rebuild-order computation itself (edge/cycle counts) --
      never a second source of truth for anything `rebuild_order`/
      `rebuild_artifacts` already carry.
    - `build_provenance`: read-only, best-effort context copied from
      Phase E1's own already-computed BuildMetadata fingerprints
      (compiler/graph/configuration) -- so a consumer of this plan
      alone can tell which build it was computed against, without a
      second lookup. Purely informational: no classification,
      ordering, or reason in this plan is ever derived from it (see
      engine.py's own PROVENANCE, NOT COMPUTATION note). Empty when
      `build_metadata` was not supplied.
    - `summary`: small, denormalized counts of the lists above, for a
      consumer that only wants "how much needs rebuilding" without
      counting lists itself -- never a second source of truth (every
      count is `len()` of one of this same plan's own fields).
    - `warnings` / `errors`: plain strings, mirroring every earlier
      phase's own report convention -- read-only observations, never
      repaired by this plan itself.
    - `incremental_compilation_plan_version`: this module's own
      INCREMENTAL_COMPILATION_PLAN_VERSION, stamped per-instance.
    """

    generated_at: str
    incremental_compilation_plan_version: str
    namespace: str
    has_previous_build: bool
    dirty_artifacts: List[str] = field(default_factory=list)
    affected_artifacts: List[str] = field(default_factory=list)
    rebuild_artifacts: List[str] = field(default_factory=list)
    clean_artifacts: List[str] = field(default_factory=list)
    removed_artifacts: List[str] = field(default_factory=list)
    rebuild_order: List[str] = field(default_factory=list)
    rebuild_reasons: Dict[str, str] = field(default_factory=dict)
    reuse_reasons: Dict[str, str] = field(default_factory=dict)
    dependency_traversal_summary: Dict[str, Any] = field(default_factory=dict)
    build_provenance: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_summary(
    *,
    dirty_artifacts: List[str],
    affected_artifacts: List[str],
    rebuild_artifacts: List[str],
    clean_artifacts: List[str],
    removed_artifacts: List[str],
) -> Dict[str, Any]:
    """Small, denormalized summary block -- every count is a direct
    `len()` of one of IncrementalCompilationPlan's own list fields,
    never independently computed or re-derived. Mirrors
    change_detection.report.build_summary()'s own precedent exactly,
    one phase up."""
    return {
        "dirty_count": len(dirty_artifacts),
        "affected_count": len(affected_artifacts),
        "rebuild_count": len(rebuild_artifacts),
        "clean_count": len(clean_artifacts),
        "removed_count": len(removed_artifacts),
        "total_artifacts_considered": len(rebuild_artifacts)
        + len(clean_artifacts)
        + len(removed_artifacts),
        "requires_rebuild": bool(rebuild_artifacts),
        "is_full_rebuild": bool(rebuild_artifacts) and not clean_artifacts,
    }