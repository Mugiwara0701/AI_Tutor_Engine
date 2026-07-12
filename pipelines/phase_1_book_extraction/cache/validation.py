"""
cache/validation.py — Phase F4.1: the Cache Validation Engine.

SCOPE: `validate_execution_against_cache()` answers exactly one
question -- given this run's own fingerprint snapshot, the previous
run's own cached fingerprint snapshot (if any), and Phase F3's own
already-made ExecutionPlan, DOES a fingerprint-based comparison agree
with what Phase F3's own existence-based Reuse Decision Engine actually
decided? It is NOT a reuse decision engine of its own (see cache/
__init__.py's own "WHAT THIS IS NOT" section) -- it never returns
"reuse"/"rebuild" for anything, never calls process_chapter_fn, and
never feeds back into build_executor.executor.execute_chapter()'s own
decision this run or any future run. This mirrors
incremental_compilation_validation.validator.
validate_incremental_compilation_plan()'s own "validate an
already-made decision, never re-decide it" precedent, one layer up.

REUSE, DON'T RECOMPUTE: every fingerprint compared here was already
computed by Phase B5.2/C4.2 and already surfaced verbatim by Phase F2
(artifact_manager/manifest.py) and Phase F4.1's own
snapshot_store.build_cache_entry() -- this module performs no new
fingerprinting of its own, only a plain equality comparison over
already-computed dicts. Every reused/rebuilt count compared here was
already computed by Phase F3 (build_executor/plan.py's own
`build_summary()`) -- this module reads `execution_plan["summary"]`
verbatim, never re-classifies a single chapter itself.

READ-ONLY: `execution_plan`, `current_snapshot`, and `previous_snapshot`
are only ever read here -- none is inserted into, updated, or removed
from, and this function returns a brand new dict every call.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .exceptions import CacheValidationError
from .report import (
    CACHE_REPORT_VERSION,
    STATUS_CONSISTENT,
    STATUS_DIVERGENT,
    STATUS_NO_BASELINE,
    CacheValidationReport,
    new_generated_at,
)


def _fingerprints_changed(
    current_snapshot: Dict[str, Any], previous_snapshot: Dict[str, Any]
) -> bool:
    """Pure equality comparison over two already-computed fingerprint
    maps -- every key either snapshot carries. Not a new fingerprint
    algorithm: this compares strings/None values Phase B5.2/C4.2/F2
    already produced, it never re-derives one."""
    keys = set(current_snapshot) | set(previous_snapshot)
    return any(current_snapshot.get(key) != previous_snapshot.get(key) for key in keys)


def validate_execution_against_cache(
    execution_plan: Dict[str, Any],
    current_snapshot: Dict[str, Any],
    previous_snapshot: Optional[Dict[str, Any]],
    *,
    build_id: str,
    previous_build_id: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministically generates this run's CacheValidationReport.
    Pure function of its own already-computed arguments -- no I/O, no
    storage access, no new fingerprinting.

    Raises CacheValidationError if `execution_plan` is missing
    `summary` (the one field this report's own verdict is ultimately
    derived from -- build_executor.plan.generate_execution_plan()/
    aggregate_execution_plan() always set it, so this only fires for a
    hand-constructed plan missing it)."""
    if execution_plan is None or "summary" not in execution_plan:
        raise CacheValidationError(
            "validate_execution_against_cache(): execution_plan is required "
            "(and must carry 'summary') to generate a CacheValidationReport "
            "(build_executor.plan.generate_execution_plan()/"
            "aggregate_execution_plan() always set it)."
        )

    current_snapshot = dict(current_snapshot or {})
    plan_summary = dict(execution_plan.get("summary") or {})
    rebuilt_count = int(plan_summary.get("rebuilt_count") or 0)
    divergences = []

    if previous_snapshot is None:
        return CacheValidationReport(
            generated_at=new_generated_at(generated_at),
            cache_report_version=CACHE_REPORT_VERSION,
            build_id=build_id,
            previous_build_id=None,
            comparison_basis="no_previous_snapshot",
            fingerprints_changed=None,
            execution_plan_summary=plan_summary,
            overall_status=STATUS_NO_BASELINE,
            divergences=[],
            warnings=[],
            errors=[],
        ).to_dict()

    fingerprints_changed = _fingerprints_changed(current_snapshot, dict(previous_snapshot))

    if fingerprints_changed and rebuilt_count == 0:
        overall_status = STATUS_DIVERGENT
        divergences.append(
            "fingerprints changed since the previous cached build "
            f"({previous_build_id!r}), but this run's Execution Plan "
            "reused every chapter it considered (rebuilt_count=0). This "
            "is expected, not a defect: Phase F3's own Reuse Decision "
            "Engine is existence-based (modules.json_writer."
            "is_already_extracted()), not fingerprint-based -- see "
            "build_executor/__init__.py's own 'WHAT REUSE MEANS HERE, "
            "HONESTLY' section. Surfaced here purely for observability."
        )
    elif not fingerprints_changed and rebuilt_count > 0:
        overall_status = STATUS_DIVERGENT
        divergences.append(
            "fingerprints are unchanged since the previous cached build "
            f"({previous_build_id!r}), but this run's Execution Plan "
            f"rebuilt {rebuilt_count} chapter(s). Consistent with Phase "
            "F3's reuse signal being existence-based rather than "
            "content-based (e.g. a chapter JSON was deleted/moved "
            "without its underlying content changing) -- not "
            "necessarily a defect. Surfaced here purely for "
            "observability."
        )
    else:
        overall_status = STATUS_CONSISTENT

    return CacheValidationReport(
        generated_at=new_generated_at(generated_at),
        cache_report_version=CACHE_REPORT_VERSION,
        build_id=build_id,
        previous_build_id=previous_build_id,
        comparison_basis="previous_snapshot",
        fingerprints_changed=fingerprints_changed,
        execution_plan_summary=plan_summary,
        overall_status=overall_status,
        divergences=divergences,
        warnings=[],
        errors=[],
    ).to_dict()