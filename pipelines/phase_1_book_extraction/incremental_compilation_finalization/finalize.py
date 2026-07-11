"""
incremental_compilation_finalization/finalize.py — Phase E5.2:
Incremental Compilation Finalization Engine.

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C, Phase D, Phase E1 (Build Metadata), Phase E2 (Build
Dependency Graph), Phase E3 (Change Detection), Phase E4 (Incremental
Compilation), and Phase E5.1 (Incremental Compilation Validation) are
all frozen -- this module does not redesign compiler/, knowledge_graph/,
validation/, build_metadata/, dependency_graph/, change_detection/,
incremental_compilation/, or incremental_compilation_validation/. It
ONLY adds one more read-only pass that AGGREGATES the already-computed
Phase E4 IncrementalCompilationPlan and Phase E5.1
IncrementalCompilationValidationReport into one final Incremental
Compilation Final Status, one Readiness Report, and one Build Summary
-- it never performs validation, never performs planning, never
detects changes, never traverses the dependency graph, never rebuilds
a compiler artifact, and never mutates a single field anywhere in
either input.

REUSE, DON'T RECOMPUTE (task's own explicit requirement, "Consume ONLY
existing outputs ... Never regenerate any of them"): every count,
status, and verdict this module reports is read directly off the
`incremental_compilation_plan` and `incremental_compilation_validation_
report` arguments, exactly as Phase E4/E5.1 already computed them --
this module never reruns change_detection.compare.compare_snapshots(),
change_detection.traversal.compute_affected_artifacts(),
incremental_compilation.planner.plan_rebuild(),
incremental_compilation.traversal.compute_rebuild_order(), or
incremental_compilation_validation.validator.
validate_incremental_compilation_plan(). No new classification
algorithm, no new ordering algorithm, no new validation-check logic,
and no new fingerprint implementation of any kind is introduced
anywhere in this module -- this module introduces no fingerprint of
its own at all; task's own "Reuse existing canonicalization utilities.
Do NOT introduce another fingerprint implementation" is satisfied
trivially, by not needing one (every field either report produces is a
direct read or a `len()`/string-join over an already-computed field).

READ-ONLY / DETERMINISTIC: like every finalization pass in this
codebase, this module only ever reads its arguments -- nothing here
mutates the IncrementalCompilationPlan or the
IncrementalCompilationValidationReport it is handed. Given the same
inputs, every function below always returns the same result (modulo
`generated_at`).

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Phase F, not incremental compilation execution, not a cache, not a
persistence layer, not distributed compilation, not parallel
execution, not Master JSON, and not video generation -- this module
finalizes a validated plan that already exists and reports what it
finds, and nothing else.

DECISION RULE (Task 2 -- one final Incremental Compilation Final
Status, derived exclusively from the already-computed Plan and
Validation Report above, mirrors compiler.finalize.
determine_final_compiler_status()'s and validation.release.
determine_release_status()'s own two-already-computed-verdicts
precedent, applied one/two layers over):

  * FAILED               -- no IncrementalCompilationPlan was
                             supplied, OR the plan itself carries at
                             least one error, OR no
                             IncrementalCompilationValidationReport was
                             supplied, OR that report's own
                             `plan_available` is not True, OR that
                             report's own `overall_status` is not
                             `"pass"`.
  * READY_WITH_WARNINGS  -- none of the above FAILED conditions hold,
                             but the plan's own `warnings` and/or the
                             validation report's own `warnings` carry
                             at least one entry.
  * READY                -- none of the above FAILED conditions hold,
                             and neither the plan nor the validation
                             report carries any warning.

Missing input is treated the same way compiler.finalize.
determine_final_compiler_status()'s and validation.release.
determine_release_status()'s own "Missing input (None) is treated the
same as a failing verdict" precedent already treats it: a plan that
was never validated, or a validation report with nothing to validate,
cannot be finalized READY or READY_WITH_WARNINGS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .report import (
    IncrementalCompilationBuildSummary,
    IncrementalCompilationReadinessReport,
)

# The three allowed Incremental Compilation Final Status values (task's
# own "Reuse existing project conventions: READY / READY_WITH_WARNINGS
# / FAILED" instruction) -- a closed set, not free-form text, reusing
# the exact same string VALUES compiler.finalize.STATUS_*/validation.
# release.STATUS_* already establish, rather than inventing a fourth,
# differently-spelled status system.
STATUS_READY = "READY"
STATUS_READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
STATUS_FAILED = "FAILED"


# --------------------------------------------------------------------------
# Task 2: Incremental Compilation Final Status
# --------------------------------------------------------------------------

def determine_final_incremental_compilation_status(
    incremental_compilation_plan: Optional[Dict[str, Any]],
    incremental_compilation_validation_report: Optional[Dict[str, Any]],
) -> str:
    """Phase E5.2 Task 2. Derived ONLY from `incremental_compilation_plan`
    (Phase E4's own artifact) and `incremental_compilation_validation_
    report` (Phase E5.1's own verdict) -- never re-plans, never
    re-validates, never re-detects changes, never re-traverses the
    dependency graph. See module docstring's DECISION RULE section for
    the exact rule."""
    plan_ok = bool(incremental_compilation_plan) and not (
        incremental_compilation_plan.get("errors") or []
    )
    validation_ok = (
        bool(incremental_compilation_validation_report)
        and incremental_compilation_validation_report.get("plan_available") is True
        and incremental_compilation_validation_report.get("overall_status") == "pass"
    )

    if not plan_ok or not validation_ok:
        return STATUS_FAILED

    warning_count = len((incremental_compilation_plan or {}).get("warnings") or []) + len(
        (incremental_compilation_validation_report or {}).get("warnings") or []
    )
    if warning_count:
        return STATUS_READY_WITH_WARNINGS
    return STATUS_READY


# --------------------------------------------------------------------------
# Task 3: Incremental Compilation Readiness Report
# --------------------------------------------------------------------------

def generate_incremental_compilation_readiness_report(
    *,
    namespace: str,
    incremental_compilation_plan: Optional[Dict[str, Any]],
    incremental_compilation_validation_report: Optional[Dict[str, Any]],
    readiness_status: str,
) -> Dict[str, Any]:
    """Phase E5.2 Task 3. Aggregates the Phase E4 plan and Phase E5.1
    validation report already produced this chapter -- never
    recomputes any field of either. `readiness_status` is Task 2's own
    verdict, computed once by the caller (finalize_incremental_
    compilation() below) and threaded through here so this module
    derives it exactly once -- never a second, independently computed
    judgment.

    Read-only over every argument. Returned as a plain dict
    (report.to_dict()), matching every earlier artifact's own "plain,
    storable dict" convention."""
    plan = incremental_compilation_plan or {}
    validation_report = incremental_compilation_validation_report or {}

    plan_available = bool(incremental_compilation_plan)
    validation_available = bool(incremental_compilation_validation_report)

    validation_summary = {
        "overall_status": validation_report.get("overall_status", "unknown"),
        "checks_passed_count": len(validation_report.get("checks_passed") or []),
        "checks_failed_count": len(validation_report.get("checks_failed") or []),
        "error_count": len(validation_report.get("errors") or []),
        "warning_count": len(validation_report.get("warnings") or []),
    }
    # Phase E4's own `summary` block, reused verbatim -- never a
    # second, independently computed count over the plan's own
    # dirty/affected/rebuild/clean/removed lists (module docstring's
    # REUSE, DON'T RECOMPUTE section).
    rebuild_statistics = dict(plan.get("summary") or {})

    plan_errors = list(plan.get("errors") or [])
    plan_warnings = list(plan.get("warnings") or [])
    validation_errors = list(validation_report.get("errors") or [])
    validation_warnings = list(validation_report.get("warnings") or [])

    errors = list(plan_errors) + [
        (e.get("message") if isinstance(e, dict) else str(e)) for e in validation_errors
    ]
    warnings = list(plan_warnings) + [
        (w.get("message") if isinstance(w, dict) else str(w)) for w in validation_warnings
    ]

    if not plan_available:
        errors.append(
            "incremental compilation finalization: no IncrementalCompilationPlan "
            "was supplied -- there is nothing for Phase E5.2 to finalize"
        )
    if not validation_available:
        errors.append(
            "incremental compilation finalization: no "
            "IncrementalCompilationValidationReport was supplied -- this plan "
            "was never validated by Phase E5.1"
        )

    recommendations = {
        STATUS_READY: (
            "This IncrementalCompilationPlan passed Phase E5.1 validation with "
            "no warnings and is ready for compiler consumption."
        ),
        STATUS_READY_WITH_WARNINGS: (
            "This IncrementalCompilationPlan passed Phase E5.1 validation but "
            "carries one or more warnings -- safe to proceed, review the "
            "warnings below."
        ),
        STATUS_FAILED: (
            "This IncrementalCompilationPlan is NOT ready for compiler "
            "consumption -- either the plan itself, or Phase E5.1's own "
            "validation of it, reported at least one error, or one of the two "
            "was never supplied."
        ),
    }
    overall_recommendation = recommendations.get(
        readiness_status, "Incremental compilation readiness could not be determined."
    )

    summary = (
        f"Incremental compilation readiness {readiness_status}: "
        f"{rebuild_statistics.get('rebuild_count', 0)} artifact(s) to rebuild, "
        f"{rebuild_statistics.get('clean_count', 0)} reused; "
        f"validation={validation_summary['overall_status']} "
        f"({validation_summary['error_count']} error(s), "
        f"{validation_summary['warning_count']} warning(s) from Phase E5.1); "
        f"{len(errors)} total error(s), {len(warnings)} total warning(s)."
    )

    report = IncrementalCompilationReadinessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        namespace=namespace,
        plan_available=plan_available,
        validation_available=validation_available,
        readiness_status=readiness_status,
        validation_summary=validation_summary,
        rebuild_statistics=rebuild_statistics,
        warning_count=len(warnings),
        error_count=len(errors),
        errors=errors,
        warnings=warnings,
        overall_recommendation=overall_recommendation,
        summary=summary,
    )
    return report.to_dict()


# --------------------------------------------------------------------------
# Task 4: Incremental Compilation Build Summary
# --------------------------------------------------------------------------

def generate_incremental_compilation_build_summary(
    *,
    namespace: str,
    incremental_compilation_plan: Optional[Dict[str, Any]],
    incremental_compilation_validation_report: Optional[Dict[str, Any]],
    final_status: str,
) -> Dict[str, Any]:
    """Phase E5.2 Task 4. Aggregates the same two already-computed
    artifacts generate_incremental_compilation_readiness_report() does,
    into one deterministic Build Summary -- never recomputes any field
    of either. `final_status` is Task 2's own verdict, computed once by
    the caller and threaded through here so this module derives it
    exactly once, mirroring compiler.finalize.
    generate_compiler_build_summary()'s own `final_status` parameter
    one layer down.

    Read-only over every argument. Returned as a plain dict
    (summary.to_dict()), matching every earlier artifact's own "plain,
    storable dict" convention."""
    plan = incremental_compilation_plan or {}
    validation_report = incremental_compilation_validation_report or {}
    plan_summary = plan.get("summary") or {}

    rebuild_target_count = plan_summary.get("rebuild_count", len(plan.get("rebuild_artifacts") or []))
    reused_artifact_count = plan_summary.get("clean_count", len(plan.get("clean_artifacts") or []))
    dirty_artifact_count = plan_summary.get("dirty_count", len(plan.get("dirty_artifacts") or []))
    clean_artifact_count = reused_artifact_count
    removed_artifact_count = plan_summary.get("removed_count", len(plan.get("removed_artifacts") or []))

    validation_statistics = {
        "overall_status": validation_report.get("overall_status", "unknown"),
        "checks_passed_count": len(validation_report.get("checks_passed") or []),
        "checks_failed_count": len(validation_report.get("checks_failed") or []),
        "error_count": len(validation_report.get("errors") or []),
        "warning_count": len(validation_report.get("warnings") or []),
    }

    warning_count = len(plan.get("warnings") or []) + validation_statistics["warning_count"]
    error_count = len(plan.get("errors") or []) + validation_statistics["error_count"]

    overall_summary = (
        f"Incremental compilation build {final_status}: {rebuild_target_count} "
        f"rebuild target(s), {reused_artifact_count} reused artifact(s) "
        f"({dirty_artifact_count} dirty, {removed_artifact_count} removed); "
        f"validation={validation_statistics['overall_status']}; "
        f"{error_count} error(s), {warning_count} warning(s) across the plan "
        "and its Phase E5.1 validation report."
    )

    summary = IncrementalCompilationBuildSummary(
        generated_at=datetime.now(timezone.utc).isoformat(),
        namespace=namespace,
        final_status=final_status,
        rebuild_target_count=rebuild_target_count,
        reused_artifact_count=reused_artifact_count,
        dirty_artifact_count=dirty_artifact_count,
        clean_artifact_count=clean_artifact_count,
        removed_artifact_count=removed_artifact_count,
        validation_statistics=validation_statistics,
        warning_count=warning_count,
        error_count=error_count,
        overall_summary=overall_summary,
    )
    return summary.to_dict()


# --------------------------------------------------------------------------
# Task 6/7: single pipeline.py integration point
# --------------------------------------------------------------------------

def finalize_incremental_compilation(
    *,
    namespace: str,
    # Phase E4 (Incremental Compilation), already in scope -- the plan
    # this module exists to finalize.
    incremental_compilation_plan: Optional[Dict[str, Any]],
    # Phase E5.1 (Incremental Compilation Validation), already in
    # scope -- the verdict over that plan this module exists to
    # finalize.
    incremental_compilation_validation_report: Optional[Dict[str, Any]],
    # Phase E1 (Build Metadata), already in scope -- accepted purely
    # for optional, read-only provenance context (task's own
    # "Optionally read: Build Metadata"); no field of it drives
    # `readiness_status`/`final_status` (module docstring's DECISION
    # RULE uses only the plan and the validation report).
    build_metadata: Optional[Dict[str, Any]] = None,
    # Phase E2 (Build Dependency Graph), already in scope -- accepted
    # purely for optional, read-only context; never re-traversed here
    # (that is Phase E4's own, already-frozen job).
    dependency_graph: Optional[Dict[str, Any]] = None,
    # Phase E3 (Change Detection), already in scope -- accepted purely
    # for optional, read-only context; never re-diffed here (that is
    # Phase E3's own, already-frozen job).
    change_detection_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase E5.2's single pipeline.py integration point (mirrors
    compiler.finalize.finalize_compiler_build()'s and validation.
    release.finalize_release()'s own "aggregate what earlier phases
    already computed into one final verdict" shape). Must run AFTER
    incremental_compilation_validation.engine.
    validate_incremental_compilation() (so there is an
    IncrementalCompilationValidationReport to finalize) and is the
    last artifact computed for this chapter's incremental-compilation
    pipeline segment, immediately before any future Phase F.

    Runs Task 2 (final status) before Tasks 3/4 (readiness report,
    build summary), since both reports' own `readiness_status`/
    `final_status` field carries the Task 2 verdict, and returns all
    three together, ready to be handed to incremental_compilation_
    finalization.state.set_current_incremental_compilation_readiness_
    report() / set_current_incremental_compilation_build_summary() /
    set_current_incremental_compilation_final_status().

    Read-only over every argument; performs no validation, no
    planning, no change detection, no dependency-graph traversal, and
    no rebuild of anything -- see module docstring's opening SCOPE
    paragraph. `build_metadata`/`dependency_graph`/
    `change_detection_report` are accepted but never read by the
    decision rule or either report generator above; they exist solely
    so a caller does not have to special-case this function's own
    signature relative to every other Phase E entry point.

    Returns:
        {
            "incremental_compilation_readiness_report": <dict>,
            "incremental_compilation_build_summary": <dict>,
            "incremental_compilation_final_status": <str>,
        }
    """
    final_status = determine_final_incremental_compilation_status(
        incremental_compilation_plan,
        incremental_compilation_validation_report,
    )
    readiness_report = generate_incremental_compilation_readiness_report(
        namespace=namespace,
        incremental_compilation_plan=incremental_compilation_plan,
        incremental_compilation_validation_report=incremental_compilation_validation_report,
        readiness_status=final_status,
    )
    build_summary = generate_incremental_compilation_build_summary(
        namespace=namespace,
        incremental_compilation_plan=incremental_compilation_plan,
        incremental_compilation_validation_report=incremental_compilation_validation_report,
        final_status=final_status,
    )
    return {
        "incremental_compilation_readiness_report": readiness_report,
        "incremental_compilation_build_summary": build_summary,
        "incremental_compilation_final_status": final_status,
    }
