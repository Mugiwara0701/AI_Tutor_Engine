"""
build_executor/report.py — Phase F3: deterministic Execution Report
generation.

SCOPE: `generate_execution_report()` aggregates an already-generated
ExecutionPlan (plan.py) plus this run's own wall-clock duration into one
Execution Report -- the thing CompilerRuntime._execute() attaches to
build_executor.state once per run (see executor.
aggregate_run_execution_report()). Every classification/count/ordering
field is read straight from the ExecutionPlan already handed to this
module; this module performs no new reuse/rebuild decision, no new
ordering, and no new fingerprinting of its own -- it only adds the one
new fact an ExecutionPlan does not itself carry: how long this run's
actual execution took, and a plain-language summary of the outcome.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .exceptions import ExecutionReportError

# This module's own version marker -- bumped only if the REPORT SHAPE
# this module produces itself changes in a way a consumer should be
# able to detect.
EXECUTION_REPORT_VERSION = "F3.1"


@dataclass
class ExecutionReport:
    """The full Phase F3 Execution Report for one CompilerRuntime run.

    FIELD NOTES:
    - `executed_artifacts` / `reused_artifacts`: the ExecutionPlan's own
      `rebuilt_artifacts`/`reused_artifacts`, renamed here to
      "executed" (rather than "rebuilt") since this report describes
      what actually happened this run, not merely what a plan called
      for -- for this package's own executor.execute_chapter(), a
      "rebuild" decision and an "executed" outcome are the same set (a
      rebuild decision always results in pipeline.process_chapter()
      actually being called -- see executor.py), so no divergence is
      possible between the two names; both are surfaced under
      `execution_statistics` below too, for a caller that only wants
      one field to check.
    - `skipped_artifacts`: reserved for a future cooperative-
      cancellation interaction (a chapter this run's ExecutionPlan
      never got to consider at all, e.g. cancel_check fired before it)
      -- always empty in the current implementation, since
      executor.execute_chapter() is only ever called for a chapter
      pipeline.process_all_pdfs()'s own cancel_check has already let
      through; kept as a field (rather than omitted) so a future,
      finer-grained Phase F3 refinement can populate it without
      changing this report's shape.
    - `execution_order`: the ExecutionPlan's own `execution_order`,
      unchanged.
    - `dependency_rebuild_order`: the ExecutionPlan's own
      `dependency_rebuild_order` (Phase E4's own already-computed
      `rebuild_order`, surfaced verbatim -- see plan.py's own module
      docstring), unchanged. Purely informational context alongside
      `execution_order` above; never a second source of truth for this
      report's own ordering, and never recomputed here.
    - `execution_duration_seconds`: this run's own wall-clock duration,
      read verbatim off Build's own `execution_summary.
      duration_seconds` (Phase F2, artifact_manager/build.py) when
      available -- never independently re-timed, so Phase F3's own
      reported duration always agrees with Phase F2's.
    - `execution_statistics`: the ExecutionPlan's own `summary` dict,
      surfaced verbatim (never recomputed a second time).
    - `warnings` / `errors`: the ExecutionPlan's own `warnings`/`errors`,
      unchanged.
    """

    generated_at: str
    execution_report_version: str
    namespace: str
    executed_artifacts: List[str] = field(default_factory=list)
    reused_artifacts: List[str] = field(default_factory=list)
    skipped_artifacts: List[str] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)
    dependency_rebuild_order: List[str] = field(default_factory=list)
    execution_duration_seconds: Optional[float] = None
    execution_statistics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_execution_report(
    execution_plan: Dict[str, Any],
    *,
    execution_duration_seconds: Optional[float] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministically generates this run's Execution Report from an
    already-assembled ExecutionPlan (plan.py's own
    aggregate_execution_plan() output, in the current single
    integration point -- see executor.aggregate_run_execution_report()).
    Pure function of `execution_plan`'s own already-set fields plus
    `execution_duration_seconds` (Build's own already-computed
    duration, read verbatim -- never re-timed here).

    Raises ExecutionReportError if `execution_plan` is missing
    `execution_order` (the one field every other report field is
    ultimately derived from -- generate_execution_plan()/
    aggregate_execution_plan() always set it, so this only fires for a
    hand-constructed plan missing it)."""
    if execution_plan is None or "execution_order" not in execution_plan:
        raise ExecutionReportError(
            "generate_execution_report(): execution_plan is required (and "
            "must carry 'execution_order') to generate an Execution Report "
            "(generate_execution_plan()/aggregate_execution_plan() always "
            "set it)."
        )

    reused = list(execution_plan.get("reused_artifacts") or [])
    rebuilt = list(execution_plan.get("rebuilt_artifacts") or [])
    order = list(execution_plan.get("execution_order") or [])
    dependency_rebuild_order = list(
        execution_plan.get("dependency_rebuild_order") or []
    )
    summary = dict(execution_plan.get("summary") or {})
    warnings = list(execution_plan.get("warnings") or [])
    errors = list(execution_plan.get("errors") or [])

    report = ExecutionReport(
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        execution_report_version=EXECUTION_REPORT_VERSION,
        namespace=execution_plan.get("namespace", "<run>"),
        executed_artifacts=rebuilt,
        reused_artifacts=reused,
        skipped_artifacts=[],
        execution_order=order,
        dependency_rebuild_order=dependency_rebuild_order,
        execution_duration_seconds=execution_duration_seconds,
        execution_statistics=summary,
        warnings=warnings,
        errors=errors,
    )
    return report.to_dict()