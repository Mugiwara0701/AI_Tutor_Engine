"""
incremental_compilation_finalization/report.py — Phase E5.2:
Incremental Compilation Readiness Report & Build Summary.

SCOPE: `IncrementalCompilationReadinessReport` and
`IncrementalCompilationBuildSummary` are the two full Phase E5.2
artifacts -- purely data holders, matching every earlier phase's own
"dataclass + to_dict(), all actual computation happens in the owning
finalize.py/engine.py" convention (incremental_compilation_validation.
report.IncrementalCompilationValidationReport, compiler.finalize.
CompilerBuildSummary, validation.release.ReleaseReadinessReport). All
construction happens in finalize.py's `generate_incremental_
compilation_readiness_report()` / `generate_incremental_compilation_
build_summary()`, orchestrated by finalize.py's own `finalize_
incremental_compilation()`.

READ-ONLY REPORTING, WITH A VERDICT (mirrors validation.release.
ReleaseReadinessReport's and compiler.finalize.CompilerBuildSummary's
own precedent, one/two layers over): both reports AGGREGATE the
already-computed Phase E4 IncrementalCompilationPlan and Phase E5.1
IncrementalCompilationValidationReport into one final
`readiness_status` / `final_status` verdict -- neither report ever
rebuilds, replans, revalidates, or mutates a single field of the plan
or the validation report it was computed from.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# This module's own version marker -- independent of every other
# *_VERSION/*_SCHEMA_VERSION constant in this codebase (same
# convention incremental_compilation_validation/report.py's own
# INCREMENTAL_COMPILATION_VALIDATION_VERSION and compiler/finalize.py's
# own FINALIZE_VERSION already establish). Bump only if either report's
# own SHAPE changes.
INCREMENTAL_COMPILATION_FINALIZATION_VERSION = "E5.2"


@dataclass
class IncrementalCompilationReadinessReport:
    """The first Phase E5.2 artifact -- see module docstring and
    task's own "Typical contents" list. Purely a data holder; all the
    actual aggregation happens in generate_incremental_compilation_
    readiness_report() below, which reads already-computed Phase
    E4/E5.1 state and folds it into one of these. This report is
    READ-ONLY reporting -- it never repairs, replans, or revalidates
    anything a failed check finds missing.

    FIELD NOTES:
    - `namespace`: the same `chapter_reference` the Phase E4 plan and
      Phase E5.1 report being finalized already carry as their own
      `namespace` field -- reused unchanged, never a second,
      independently computed namespace.
    - `plan_available` / `validation_available`: whether an
      IncrementalCompilationPlan / IncrementalCompilationValidationReport
      was supplied at all -- `False` degrades this report to a FAILED
      `readiness_status` (see finalize.py's own decision rule) rather
      than raising.
    - `readiness_status`: `"READY"` | `"READY_WITH_WARNINGS"` |
      `"FAILED"` -- identical closed set and decision rule to
      finalize.py's own `determine_final_incremental_compilation_
      status()`.
    - `validation_summary`: small, denormalized detail read straight
      off the Phase E5.1 report (`overall_status`, `checks_passed`/
      `checks_failed` counts, `errors`/`warnings` counts) -- never a
      second, independently computed verdict over the plan.
    - `rebuild_statistics`: the Phase E4 plan's own `summary` block,
      reused verbatim -- never a second, independently computed count
      over the plan's own dirty/affected/rebuild/clean/removed lists.
    - `warning_count` / `error_count`: total counts across both the
      plan's own `warnings`/`errors` and the validation report's own
      `warnings`/`errors` -- never independently re-derived.
    - `overall_recommendation`: one human-readable sentence describing
      whether this plan is safe to proceed with, and why.
    - `incremental_compilation_finalization_version`: this module's
      own INCREMENTAL_COMPILATION_FINALIZATION_VERSION, stamped
      per-instance.
    """

    generated_at: str = ""
    incremental_compilation_finalization_version: str = INCREMENTAL_COMPILATION_FINALIZATION_VERSION
    namespace: str = ""
    plan_available: bool = False
    validation_available: bool = False
    readiness_status: str = "unknown"  # "READY" | "READY_WITH_WARNINGS" | "FAILED" | "unknown"
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    rebuild_statistics: Dict[str, Any] = field(default_factory=dict)
    warning_count: int = 0
    error_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    overall_recommendation: str = ""
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IncrementalCompilationBuildSummary:
    """The second Phase E5.2 artifact -- see module docstring and
    task's own BUILD SUMMARY "Include" list. Purely a data holder; all
    the actual aggregation happens in generate_incremental_compilation_
    build_summary() below. Field set is exactly the task's own
    requested list (rebuild target count, reused artifact count, dirty
    artifact count, clean artifact count, validation statistics,
    warning count, error count, final status, summary), plus
    `removed_artifact_count` (additive, matching the plan's own
    `removed_artifacts` field so this summary is not silently
    incomplete relative to the plan it aggregates) and `generated_at`/
    `finalize_version` (matching every earlier artifact's own
    convention)."""

    generated_at: str = ""
    finalize_version: str = INCREMENTAL_COMPILATION_FINALIZATION_VERSION
    namespace: str = ""
    final_status: str = "unknown"  # "READY" | "READY_WITH_WARNINGS" | "FAILED" | "unknown"
    rebuild_target_count: int = 0
    reused_artifact_count: int = 0
    dirty_artifact_count: int = 0
    clean_artifact_count: int = 0
    removed_artifact_count: int = 0
    validation_statistics: Dict[str, Any] = field(default_factory=dict)
    warning_count: int = 0
    error_count: int = 0
    overall_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
