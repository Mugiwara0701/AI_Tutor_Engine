"""
compiler_release/finalize.py — Phase F5: Final Release Status
determination + CompilerReleaseManifest generation.

SCOPE: this is the only module in compiler_release/ with real logic.
Every function here is a PURE function of its own already-computed
arguments -- no I/O, no storage access, no new fingerprinting, no new
validation. Every field this module writes into a CompilerReleaseManifest
is read verbatim off an F1-F4 accessor already handed to it by the one
caller, CompilerRuntime._record_release() (runtime/runtime.py) -- this
module never imports runtime/artifact_manager/build_executor/cache
itself, so it can never be tempted to re-fetch or re-derive something
its caller already computed.

NEVER AUTHORITATIVE OVER ANY UPSTREAM DECISION: exactly like
cache.validation.validate_execution_against_cache()'s own
`overall_status`, the `final_release_status` this module computes is
purely observational. It never blocks, retries, or alters a future
run() call; a caller who wants to *act* on this verdict (e.g. refuse to
deploy a FAILED release) does so entirely outside CompilerRuntime --
Phase F5 reports, it never gates (same boundary cache/__init__.py's own
"WHAT THIS IS NOT" section already draws for itself, one package over).

ON `chapters_failed`: build_executor.plan.build_summary() (Phase F3's
own execution_statistics) carries `reused_count`/`rebuilt_count`/
`total_considered`/`requires_execution`/`is_full_reuse` -- reuse/rebuild
is a binary per-chapter decision, not a success/failure classification,
so Phase F3 has no failure count of its own to surface. The one place
this codebase already tracks "how many chapters failed this run" is
Phase F1's own runtime_state.get_current_progress()["chapters_failed"]
(see runtime/state.py) -- this module never recomputes that count, it
only accepts it as an explicit argument from its caller, which already
has it on hand.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .exceptions import ReleaseManifestError
from .report import (
    RELEASE_MANIFEST_VERSION,
    STATUS_FAILED,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    CompilerReleaseManifest,
    new_generated_at,
)

# Mirrors runtime.context.RuntimeStatus's own string values -- not
# imported directly (this module stays free of any F1-F4 import, per
# module docstring) so these are the two RuntimeStatus values this
# module treats as a closed-run failure, by their known string value.
_RUNTIME_STATUS_FAILED = "FAILED"
_RUNTIME_STATUS_CANCELLED = "CANCELLED"
_RUNTIME_STATUS_COMPLETED = "COMPLETED"

# Mirrors cache.report.STATUS_DIVERGENT's own string value -- not
# imported directly, same reason as above.
_CACHE_STATUS_DIVERGENT = "DIVERGENT"


def determine_final_release_status(
    runtime_status: str,
    execution_summary: Optional[Dict[str, Any]],
    cache_validation_report: Optional[Dict[str, Any]],
) -> str:
    """Pure function of three already-computed values -- no I/O, no new
    fingerprinting, no new validation.

        FAILED                if runtime_status is FAILED or CANCELLED
        READY_WITH_WARNINGS   if runtime_status is COMPLETED and
                               (chapters_failed > 0 or cache
                               overall_status == DIVERGENT)
        READY                 if runtime_status is COMPLETED and
                               chapters_failed == 0 and cache
                               overall_status in (CONSISTENT,
                               NO_BASELINE, None)

    Any runtime_status other than the three RuntimeStatus values this
    table names (e.g. a future RuntimeStatus this module has not been
    updated for) is treated as FAILED -- the same closed, conservative
    fallback every other phase's own three-way status function in this
    codebase already applies for an unrecognized input, so this
    function always returns one of exactly the three closed statuses
    and never raises."""
    execution_summary = execution_summary or {}
    cache_validation_report = cache_validation_report or {}

    if runtime_status not in (
        _RUNTIME_STATUS_COMPLETED,
        _RUNTIME_STATUS_FAILED,
        _RUNTIME_STATUS_CANCELLED,
    ):
        return STATUS_FAILED

    if runtime_status in (_RUNTIME_STATUS_FAILED, _RUNTIME_STATUS_CANCELLED):
        return STATUS_FAILED

    chapters_failed = int(execution_summary.get("chapters_failed") or 0)
    cache_overall_status = cache_validation_report.get("overall_status")

    if chapters_failed > 0 or cache_overall_status == _CACHE_STATUS_DIVERGENT:
        return STATUS_READY_WITH_WARNINGS

    return STATUS_READY


def generate_compiler_release_manifest(
    runtime_status: str,
    build: Any,
    execution_report: Optional[Dict[str, Any]],
    cache_entry: Optional[Dict[str, Any]],
    cache_validation_report: Optional[Dict[str, Any]],
    *,
    chapters_failed: int = 0,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministically generates this run's CompilerReleaseManifest.
    Pure aggregation -- no I/O, no new fingerprinting. Given
    byte-identical inputs and the same `generated_at` override, returns
    a byte-identical manifest every call (same contract
    cache.validation.validate_execution_against_cache() already
    documents for itself one package over).

    Raises ReleaseManifestError if `build` is None or has no
    `build_manifest` attached yet -- Phase F2's own _record_build()
    always attaches one via Build.with_manifest() before a successful
    run's Build is ever recorded (this only fires for a hand-constructed
    Build missing it, or a run where Phase F2's own bookkeeping itself
    already failed and logged -- see runtime/runtime.py's own
    _record_release() docstring for how that case is handled: it never
    even calls this function in that situation).

    `execution_report`/`cache_validation_report` may each be None (their
    own package's bookkeeping failed and was swallowed upstream) -- this
    degrades `execution_summary`/`cache_summary` to their null/default
    shape and still produces a manifest; a partial upstream failure must
    never prevent this aggregation from running (same "a broken observer
    must never abort the run" principle every other Phase F integration
    point already applies)."""
    if build is None or not getattr(build, "build_manifest", None):
        raise ReleaseManifestError(
            "generate_compiler_release_manifest(): build.build_manifest is "
            "required to assemble a CompilerReleaseManifest (Phase F2's "
            "own _record_build() always attaches one via "
            "Build.with_manifest() before a successful run is recorded)."
        )

    manifest = build.build_manifest
    warnings: list = []
    errors: list = []

    build_summary = {
        "build_id": build.build_id,
        "build_status": manifest.get("build_status"),
        "manifest_fingerprint": manifest.get("manifest_fingerprint"),
    }

    execution_summary: Optional[Dict[str, Any]]
    if execution_report is not None:
        execution_summary = dict(execution_report.get("execution_statistics") or {})
        execution_summary["chapters_failed"] = int(chapters_failed or 0)
    else:
        execution_summary = None
        warnings.append(
            "no ExecutionReport was recorded this run (Phase F3's own "
            "bookkeeping did not complete); execution_summary is null."
        )

    cache_entry = cache_entry or {}
    cache_validation_report = cache_validation_report or {}
    cache_summary = {
        "has_cache_entry": bool(cache_entry),
        "comparison_basis": cache_validation_report.get("comparison_basis"),
        "cache_overall_status": cache_validation_report.get("overall_status"),
    }
    if not cache_entry:
        warnings.append(
            "no CacheEntry was recorded this run (Phase F4's own "
            "bookkeeping did not complete); cache_summary reflects an "
            "empty cache state."
        )

    divergences = list(cache_validation_report.get("divergences") or [])

    final_release_status = determine_final_release_status(
        runtime_status, execution_summary, cache_validation_report,
    )

    return CompilerReleaseManifest(
        release_manifest_version=RELEASE_MANIFEST_VERSION,
        build_id=build.build_id,
        generated_at=new_generated_at(generated_at),
        runtime_status=runtime_status,
        final_release_status=final_release_status,
        build_summary=build_summary,
        execution_summary=execution_summary,
        cache_summary=cache_summary,
        divergences=divergences,
        warnings=warnings,
        errors=errors,
    ).to_dict()


def finalize_release(
    runtime_status: str,
    build: Any,
    execution_report: Optional[Dict[str, Any]],
    cache_entry: Optional[Dict[str, Any]],
    cache_validation_report: Optional[Dict[str, Any]],
    *,
    chapters_failed: int = 0,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Thin orchestration wrapper calling determine_final_release_status()
    (indirectly, via generate_compiler_release_manifest()) and
    generate_compiler_release_manifest() in order -- the one function
    CompilerRuntime._record_release() calls. Kept as its own function
    (rather than inlined into _record_release() itself) purely for
    symmetry with every other phase's own finalize_release()-shaped
    orchestration entry point (see e.g.
    incremental_compilation_finalization/finalize.py's own precedent)."""
    return generate_compiler_release_manifest(
        runtime_status,
        build,
        execution_report,
        cache_entry,
        cache_validation_report,
        chapters_failed=chapters_failed,
        generated_at=generated_at,
    )
