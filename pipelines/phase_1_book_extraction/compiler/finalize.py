"""
compiler/finalize.py — Phase B5.3: Compiler Finalization & Phase B Completion.

SCOPE (read this before touching anything else): Phase A, Phase B0,
Phase B1, Phase B1b, Phase B1c, Phase B2, Phase B3, Phase B4, Phase B5.1,
and Phase B5.2 are frozen -- this module does not redesign
RegistryManager (compiler/registry_manager.py), CanonicalRegistry
(compiler/registry.py), compiler/state.py's existing _CURRENT_* lifecycle,
compiler/enrichment.py, compiler/normalization.py, compiler/references.py,
compiler/relationships.py, compiler/validation.py, compiler/build.py, or
compiler/fingerprints.py. It also does not touch json_writer.py /
schemas/chapter_schema.py / ChapterJSON. It ONLY adds an eighth,
read-only compiler pass that AGGREGATES what Phases A-B5.2 already
computed into one final Build Summary and one final compiler status --
it never generates, repairs, recomputes, or mutates a single field
anywhere in the compiler IR, and it never inserts into, updates, or
removes from any registry.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
Knowledge Graph (or any graph construction/traversal/dependency/learning
graph), not Incremental Compilation, not a Compiler Cache, not Automatic
Repair, and not Semantic/LLM Reasoning. It performs no new validation or
readiness checking of its own -- see TASK 2 below.

REUSE, DON'T RECOMPUTE (mirrors every earlier compiler pass's own rule):
every field below is read from artifacts Phases B4/B5.1/B5.2 already
produced this chapter -- `validation_report` (compiler.validation.
validate_compiler_state()), `manifest`/`statistics` (compiler.build.
generate_compiler_manifest()/generate_compiler_statistics()), and
`registry_fingerprints`/`compiler_fingerprint`/`readiness_report`
(compiler.fingerprints.generate_compiler_fingerprints()). Nothing in
this module re-scans a registry, re-derives a fingerprint, or
re-validates the compiler IR a second time.

TASK 1 -- Compiler Build Summary: `generate_compiler_build_summary(...)`
returns one deterministic dict aggregating the manifest, statistics,
fingerprints, and readiness report already produced this chapter (task's
own "Suggested fields" list: compiler_version, schema_version,
compiler_status, build_status, total_registries, total_objects,
total_relationships, validation_summary, readiness_summary,
compiler_fingerprint, overall_summary), PLUS `finalize_version` (audit
refinement, additive -- this module's own FINALIZE_VERSION constant,
embedded here following the same convention `compiler/build.py`'s
CompilerManifest already uses for BUILD_VERSION). It performs no new
computation over the compiler IR itself -- every field is a read, or a
small string built from already-computed reads.

TASK 2 -- Final Compiler Status: `determine_final_compiler_status(...)`
derives one of READY / READY_WITH_WARNINGS / FAILED from EXACTLY TWO
already-computed artifacts -- `validation_report["status"]` (Phase B4)
and `readiness_report["ready"]`/`readiness_report["warnings"]` (Phase
B5.2) -- and nothing else. It never re-validates the compiler IR, never
re-runs a readiness check, and never inspects a registry directly.

  * FAILED               -- validation did not pass, OR readiness found
                             at least one failed check.
  * READY_WITH_WARNINGS  -- validation passed AND readiness is ready,
                             but validation and/or readiness carries at
                             least one warning.
  * READY                -- validation passed, readiness is ready, and
                             neither report carries any warning.

TASK 4 -- Pipeline Finalization: `finalize_compiler_build(...)` is the
one pipeline.py integration point (mirrors generate_compiler_manifest()'s
and generate_compiler_fingerprints()'s own shape). It must run AFTER
compiler.fingerprints.generate_compiler_fingerprints() (so there is a
readiness report / compiler fingerprint to aggregate) and BEFORE the
compiler state for this chapter is considered complete -- see
pipeline.py's own integration comment at the call site. It runs Task 2
before Task 1 (the build summary's own `build_status` field carries the
Task 2 verdict) and returns both results together, ready to be handed to
compiler_state.set_current_compiler_build_summary() /
set_current_final_compiler_status() (Phase B5.3's own additions to
compiler/state.py -- see that module's docstring). This pass performs no
analysis of its own: it only assembles artifacts Phases B4-B5.2 already
produced.

BACKWARD COMPATIBILITY: every field this module reads (from
`validation_report`, `manifest`, `statistics`, `registry_fingerprints`,
`compiler_fingerprint`, `readiness_report`) is only ever read, never
changed. No existing registry, field, relationship, manifest, statistics,
fingerprint, readiness report, or Chapter JSON output changes as a result
of this module existing. The only new compiler artifacts are the build
summary dict and the final status string (plus the four small, additive
get/set/has functions in compiler/state.py that hold them).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .registry_manager import RegistryManager

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of every earlier phase's
# own *_VERSION constant). Bump only if the build-summary/final-status
# SHAPE this file produces itself changes in a way a consumer of
# `build_summary`/`final_status` should be able to detect.
FINALIZE_VERSION = "1.0.0"

# The three allowed Final Compiler Status values (task's own "Suggested
# values" list) -- a closed set, not free-form text.
STATUS_READY = "READY"
STATUS_READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
STATUS_FAILED = "FAILED"


# --------------------------------------------------------------------------
# Task 2: Final Compiler Status
# --------------------------------------------------------------------------

def determine_final_compiler_status(
    validation_report: Optional[Dict[str, Any]],
    readiness_report: Optional[Dict[str, Any]],
) -> str:
    """Phase B5.3 Task 2. Derived ONLY from `validation_report` (Phase
    B4's own verdict) and `readiness_report` (Phase B5.2's own verdict)
    -- never performs additional validation, never re-checks readiness,
    never touches a registry. See module docstring's TASK 2 section for
    the exact decision rule.

    Missing input (None) is treated the same as a failing verdict for
    that input -- a build that never validated, or was never assessed
    for readiness, cannot be reported READY or READY_WITH_WARNINGS."""
    validation_status = (validation_report or {}).get("status")
    validation_passed = validation_status == "pass"

    ready = bool(readiness_report) and bool(readiness_report.get("ready"))

    if not validation_passed or not ready:
        return STATUS_FAILED

    warning_count = len((validation_report or {}).get("warnings") or []) + len(
        (readiness_report or {}).get("warnings") or []
    )
    if warning_count:
        return STATUS_READY_WITH_WARNINGS
    return STATUS_READY


# --------------------------------------------------------------------------
# Task 1: Compiler Build Summary
# --------------------------------------------------------------------------

@dataclass
class CompilerBuildSummary:
    """The full Phase B5.3 build-summary artifact -- see module
    docstring's TASK 1 section. Purely a data holder; all the actual
    aggregation happens in generate_compiler_build_summary() below,
    which reads already-computed compiler state and folds it into one
    of these. Field set is exactly the task's own "Suggested fields"
    list, plus `generated_at` (additive, matching every earlier
    artifact's own convention)."""

    generated_at: str
    compiler_version: str
    schema_version: str
    finalize_version: str
    compiler_status: str
    build_status: str
    total_registries: int
    total_objects: int
    total_relationships: int
    validation_summary: Dict[str, Any]
    readiness_summary: Dict[str, Any]
    compiler_fingerprint: Optional[str]
    overall_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_compiler_build_summary(
    manager: RegistryManager,
    validation_report: Optional[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    compiler_fingerprint: Optional[str],
    readiness_report: Optional[Dict[str, Any]],
    final_status: str,
) -> Dict[str, Any]:
    """Phase B5.3 Task 1. Aggregates the manifest, statistics,
    fingerprints, and readiness report already produced this chapter --
    never recomputes any of them. `manager` is accepted only so
    `total_registries`/`total_objects` can fall back to `manager`'s own
    cheap aggregate accessors (`.names()`, `.total_size()`) the same way
    compiler.build.generate_compiler_manifest() already does, for a
    caller-supplied `manifest` that does not carry the expected fields
    (e.g. a hand-built test fixture) -- never by iterating every
    registry's items itself.

    `final_status` is Task 2's own verdict, computed once by the caller
    (finalize_compiler_build() below) and threaded through here so this
    module derives it exactly once -- never a second, independently
    computed judgment.

    Read-only over every argument. Returned as a plain dict
    (summary.to_dict()), matching every earlier artifact's own "plain,
    storable dict" convention."""
    manifest = manifest or {}
    statistics = statistics or {}
    readiness_report = readiness_report or {}
    validation_report = validation_report or {}

    compiler_version = manifest.get("compiler_version", "unknown")
    schema_version = manifest.get("schema_version", "unknown")
    # Same carry-forward pattern compiler/build.py's own `compiler_status`
    # and compiler/fingerprints.py's own readiness `compiler_status`
    # already document: the only status judgment Phase B4 itself computes
    # is `validation_report["status"]`, so `compiler_status` here is that
    # same verdict, exposed under this artifact's own field name -- not a
    # third, independently-computed judgment.
    compiler_status = manifest.get(
        "compiler_status", validation_report.get("status", "unknown")
    )

    total_registries = manifest.get("registry_count", len(manager.names()))
    total_objects = manifest.get("object_count", manager.total_size())
    total_relationships = manifest.get(
        "relationship_count", statistics.get("total_relationships", 0)
    )

    validation_summary = {
        "status": validation_report.get("status", "unknown"),
        "error_count": len(validation_report.get("errors") or []),
        "warning_count": len(validation_report.get("warnings") or []),
    }
    readiness_summary = dict(
        readiness_report.get("readiness_summary")
        or {
            "total_checks": 0,
            "passed_count": 0,
            "failed_count": 0,
            "warning_count": 0,
        }
    )

    overall_summary = (
        f"Compiler build {final_status}: {total_registries} registr"
        f"{'y' if total_registries == 1 else 'ies'}, {total_objects} "
        f"object{'s' if total_objects != 1 else ''}, "
        f"{total_relationships} relationship"
        f"{'s' if total_relationships != 1 else ''}; "
        f"validation={validation_summary['status']} "
        f"({validation_summary['error_count']} error(s), "
        f"{validation_summary['warning_count']} warning(s)); "
        f"readiness={'ready' if readiness_report.get('ready') else 'not ready'} "
        f"({readiness_summary.get('passed_count', 0)}/"
        f"{readiness_summary.get('total_checks', 0)} checks passed)."
    )

    summary = CompilerBuildSummary(
        generated_at=datetime.now(timezone.utc).isoformat(),
        compiler_version=compiler_version,
        schema_version=schema_version,
        # This module's own version marker (see FINALIZE_VERSION above),
        # embedded in the Build Summary following the same convention
        # every earlier phase uses for its own artifact (e.g.
        # compiler/build.py's CompilerManifest.build_version carries
        # BUILD_VERSION). Lets a consumer detect the SHAPE of this
        # Build Summary independent of `compiler_version`/`schema_version`.
        finalize_version=FINALIZE_VERSION,
        compiler_status=compiler_status,
        build_status=final_status,
        total_registries=total_registries,
        total_objects=total_objects,
        total_relationships=total_relationships,
        validation_summary=validation_summary,
        readiness_summary=readiness_summary,
        compiler_fingerprint=compiler_fingerprint,
        overall_summary=overall_summary,
    )
    return summary.to_dict()


# --------------------------------------------------------------------------
# Task 4: Pipeline Integration -- the one pass pipeline.py calls
# --------------------------------------------------------------------------

def finalize_compiler_build(
    manager: RegistryManager,
    *,
    validation_report: Optional[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    compiler_fingerprint: Optional[str],
    readiness_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase B5.3's single pipeline.py integration point (mirrors
    compiler.build.generate_compiler_manifest()'s and compiler.
    fingerprints.generate_compiler_fingerprints()'s own shape). Must run
    AFTER compiler.fingerprints.generate_compiler_fingerprints() (so
    `readiness_report`/`compiler_fingerprint` are available to aggregate)
    and BEFORE the compiler state for this chapter is considered complete
    -- see module docstring's TASK 4 section and pipeline.py's own
    comment at the call site.

    Runs Task 2 (final status) before Task 1 (build summary), since the
    build summary's own `build_status` field carries the Task 2 verdict,
    and returns both together as one plain dict, ready to be handed to
    compiler_state.set_current_compiler_build_summary() /
    set_current_final_compiler_status() (task's own "store inside
    Compiler State" requirement).

    Read-only over every argument, and performs no new analysis of its
    own -- see module docstring's opening SCOPE paragraph."""
    final_status = determine_final_compiler_status(validation_report, readiness_report)
    build_summary = generate_compiler_build_summary(
        manager,
        validation_report,
        manifest,
        statistics,
        registry_fingerprints,
        compiler_fingerprint,
        readiness_report,
        final_status,
    )
    return {
        "build_summary": build_summary,
        "final_status": final_status,
    }
