"""
change_detection/report.py — Phase E3: Change Detection Report.

SCOPE: `ChangeDetectionReport` is the full Phase E3 artifact -- purely a
data holder, matching every earlier phase's own "dataclass + to_dict(),
all actual computation happens in the owning build.py/engine.py"
convention (compiler/build.py's CompilerManifest, knowledge_graph/
schema.py's KnowledgeGraph, dependency_graph/schema.py's
DependencyGraph, validation/release.py's ReleaseReadinessReport). All
construction happens in engine.py's `detect_changes()`.

READ-ONLY REPORTING (mirrors validation/release.py's own
ReleaseReadinessReport and compiler/fingerprints.py's own
CompilerReadinessReport): this report describes what changed, it never
repairs, rebuilds, or resolves anything it finds -- a `warnings`/
`errors` entry is reported, never acted on.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase. Bump only if the REPORT SHAPE
# this module produces itself changes in a way a consumer should be
# able to detect.
CHANGE_DETECTION_REPORT_VERSION = "E3.1"


@dataclass
class ChangeDetectionReport:
    """The full Phase E3 artifact.

    FIELD NOTES:
    - `namespace`: the same `chapter_reference` every earlier Phase
      B-E2 artifact for this chapter already uses -- reused unchanged,
      never a second, independently computed namespace.
    - `has_previous_build`: False when `previous_build` (engine.py) was
      `None` -- i.e. this comparison had nothing to compare the current
      build against, so every artifact is necessarily "added" (see
      compare.py's own MISSING PREVIOUS BUILD note).
    - `added_artifacts` / `removed_artifacts` / `modified_artifacts`:
      compare.py's own `added`/`removed`/`modified` lists, unchanged.
    - `affected_artifacts`: traversal.py's own
      `compute_affected_artifacts()` output -- artifacts that did not
      themselves change but transitively depend on one that did.
    - `unchanged_artifacts`: compare.py's own `unchanged_candidates`,
      MINUS every id already in `affected_artifacts` (an artifact
      downstream of a change is reported as "affected", never also
      listed as "unchanged", even if its own fingerprint didn't move --
      see engine.py).
    - `summary`: small, denormalized counts of the five lists above,
      for a consumer that only wants "how much changed" without
      counting lists itself -- never a second source of truth (every
      count is `len()` of one of this same report's own fields).
    - `warnings` / `errors`: plain strings, mirroring every earlier
      phase's own report convention (validation/release.py's
      ReleaseReadinessReport, compiler/fingerprints.py's
      CompilerReadinessReport) -- read-only observations, never
      repaired by this report itself.
    - `change_detection_report_version`: this module's own
      CHANGE_DETECTION_REPORT_VERSION, stamped per-instance.
    """

    generated_at: str
    change_detection_report_version: str
    namespace: str
    has_previous_build: bool
    added_artifacts: List[str] = field(default_factory=list)
    removed_artifacts: List[str] = field(default_factory=list)
    modified_artifacts: List[str] = field(default_factory=list)
    affected_artifacts: List[str] = field(default_factory=list)
    unchanged_artifacts: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_summary(
    *,
    added_artifacts: List[str],
    removed_artifacts: List[str],
    modified_artifacts: List[str],
    affected_artifacts: List[str],
    unchanged_artifacts: List[str],
) -> Dict[str, Any]:
    """Small, denormalized summary block -- every count is a direct
    `len()` of one of ChangeDetectionReport's own list fields, never
    independently computed or re-derived."""
    return {
        "added_count": len(added_artifacts),
        "removed_count": len(removed_artifacts),
        "modified_count": len(modified_artifacts),
        "affected_count": len(affected_artifacts),
        "unchanged_count": len(unchanged_artifacts),
        "total_artifacts_current": len(added_artifacts)
        + len(modified_artifacts)
        + len(affected_artifacts)
        + len(unchanged_artifacts),
        "has_changes": bool(added_artifacts or removed_artifacts or modified_artifacts),
    }