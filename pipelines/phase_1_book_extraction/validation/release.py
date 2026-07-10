"""
validation/release.py — Phase D3: Release Readiness (Final Release Gate).

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C, Phase D1 (System Integrity -- validation/system_integrity.py),
and Phase D2 (Determinism & Reproducibility -- validation/determinism.py)
are all frozen -- this module does not redesign compiler/, knowledge_graph/,
validation/system_integrity.py, or validation/determinism.py. It ONLY
adds one more read-only pass, mirroring compiler/finalize.py's and
knowledge_graph/finalize.py's own "aggregate what earlier phases already
computed into one final verdict" role, one layer up: it AGGREGATES the
fourteen already-computed artifacts Phases B-D2 produced into one final
Release Readiness Report and one Release Decision -- it never
regenerates, repairs, recomputes, or mutates a single field anywhere in
the Compiler IR, the Knowledge Graph, or any earlier report, and it
never inserts into, updates, or removes from any registry.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Phase E, not Incremental Compilation, not Compiler Metadata, not
Dependency Tracking, not Cache Management, not a Runtime API, not Graph
Queries/Traversal/Optimization, not Repair logic, not Release
Packaging, not Deployment, not CI/CD, and not a Master JSON. It performs
no new validation and no new determinism checking of its own -- every
check D3 needs, D1 and D2 already ran; D3 only reads their verdicts.

REUSE, DON'T RECOMPUTE (mirrors every earlier phase's own rule, applied
one layer up): every field below is read from artifacts Phases B-D2
already produced this chapter -- the Compiler Validation Report
(compiler.validation.validate_compiler_state()), the Knowledge Graph
Validation Report (knowledge_graph.validation.validate_knowledge_graph()),
the Compiler Readiness Report / Knowledge Graph Readiness Report
(compiler.fingerprints.generate_compiler_readiness_report()/
knowledge_graph.fingerprints.generate_graph_readiness_report()), the
Compiler Build Summary / Knowledge Graph Build Summary
(compiler.finalize.finalize_compiler_build()/knowledge_graph.finalize.
finalize_knowledge_graph(), which also each carry Task 2's own Final
Compiler/Graph Status), the System Integrity Report (validation.
system_integrity.validate_system_integrity()), the Determinism Report
(validation.determinism.validate_determinism()), the Compiler/Knowledge
Graph Manifests (compiler.build.generate_compiler_manifest()/
knowledge_graph.build.generate_knowledge_graph_manifest()), the
Compiler/Graph Fingerprints, and the Compiler/Graph Statistics. Nothing
here re-derives a fingerprint, re-validates a compiler object or graph
node, reruns D1, reruns D2, repairs data, or optimizes data (task's own
Task 5 "Aggregation Rules").

DECISION RULE (Task 3 -- one final compiler verdict, derived exclusively
from the already-computed reports above, never a registry/node/edge
directly):

  * FAILED               -- the Compiler Final Status is FAILED, OR the
                             Knowledge Graph Final Status is FAILED, OR
                             the System Integrity Report's own
                             `overall_status` is not "pass" (or the
                             report is missing), OR the Determinism
                             Report's own `overall_status` is not "pass"
                             (or the report is missing).
  * READY_WITH_WARNINGS  -- none of the above FAILED conditions hold,
                             but at least one of: the Compiler Final
                             Status is READY_WITH_WARNINGS, the
                             Knowledge Graph Final Status is
                             READY_WITH_WARNINGS, the System Integrity
                             Report carries at least one warning, or the
                             Determinism Report carries at least one
                             warning.
  * READY                -- both Final Statuses are READY, and neither
                             the System Integrity Report nor the
                             Determinism Report carries any warning.

Missing input is treated the same way every earlier phase's own
Task-2-style decision rule already treats it (compiler.finalize.
determine_final_compiler_status()'s and knowledge_graph.finalize.
determine_final_graph_status()'s own "Missing input (None) is treated
the same as a failing verdict" precedent, applied one layer up): a
release that never received a System Integrity Report or a Determinism
Report to aggregate cannot be reported READY or READY_WITH_WARNINGS.

READ-ONLY / NEVER MUTATES: nothing in this module calls `.insert()`,
`.update()`, `.upsert()`, `.remove()`, or `.clear()` on any registry,
and no manifest/statistics/fingerprint/readiness-report/build-summary/
validation-report/System-Integrity-Report/Determinism-Report dict
handed in is ever mutated in place. `determine_release_status()` and
`generate_release_readiness_report()` are both pure functions of their
arguments (modulo `generated_at`).

PIPELINE INTEGRATION: the one pipeline.py integration point
(`finalize_release()` below) runs immediately after Phase D2 -- after
`determinism_state.set_current_determinism_report()` -- so every
artifact D3 aggregates already exists. Stored via validation.
release_state (mirroring validation.state's/validation.
determinism_state's own "current chapter's artifacts" pattern one
artifact over).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker -- independent of every other
# *_VERSION/*_SCHEMA_VERSION/*_INTEGRITY_VERSION/DETERMINISM_VERSION
# constant in this codebase (same convention validation/
# system_integrity.py's SYSTEM_INTEGRITY_VERSION and validation/
# determinism.py's DETERMINISM_VERSION already establish). Bump only if
# this module's own decision rule or report SHAPE changes.
RELEASE_VERSION = "D3.1"

# The three allowed Release Decision values (task's own "Suggested
# values" list) -- a closed set, not free-form text, reusing the exact
# same string constants compiler.finalize.STATUS_*/knowledge_graph.
# finalize.STATUS_* already established two phases down, rather than
# redeclaring three new equivalent strings.
STATUS_READY = "READY"
STATUS_READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
STATUS_FAILED = "FAILED"


# --------------------------------------------------------------------------
# Task 3: Release Decision
# --------------------------------------------------------------------------

def determine_release_status(
    compiler_final_status: Optional[str],
    graph_final_status: Optional[str],
    system_integrity_report: Optional[Dict[str, Any]],
    determinism_report: Optional[Dict[str, Any]],
) -> str:
    """Phase D3 Task 3. Derived ONLY from `compiler_final_status`
    (compiler.finalize.determine_final_compiler_status()'s own verdict,
    already computed as part of `finalize_compiler_build()`),
    `graph_final_status` (knowledge_graph.finalize.
    determine_final_graph_status()'s own verdict, already computed as
    part of `finalize_knowledge_graph()`), `system_integrity_report`
    (Phase D1's own verdict), and `determinism_report` (Phase D2's own
    verdict) -- never re-validates the compiler IR or the graph, never
    reruns D1 or D2, never inspects a registry, node, or edge directly.
    See module docstring's DECISION RULE section for the exact rule.

    Missing input (None) is treated the same as a failing verdict for
    that input -- a release that was never assessed for system
    integrity or determinism cannot be reported READY or
    READY_WITH_WARNINGS (mirrors compiler.finalize.
    determine_final_compiler_status()'s and knowledge_graph.finalize.
    determine_final_graph_status()'s own identical precedent)."""
    compiler_failed = compiler_final_status != STATUS_READY and compiler_final_status != STATUS_READY_WITH_WARNINGS
    graph_failed = graph_final_status != STATUS_READY and graph_final_status != STATUS_READY_WITH_WARNINGS

    system_integrity_passed = (
        system_integrity_report is not None
        and system_integrity_report.get("overall_status") == "pass"
    )
    determinism_passed = (
        determinism_report is not None
        and determinism_report.get("overall_status") == "pass"
    )

    if compiler_failed or graph_failed or not system_integrity_passed or not determinism_passed:
        return STATUS_FAILED

    warning_count = (
        (1 if compiler_final_status == STATUS_READY_WITH_WARNINGS else 0)
        + (1 if graph_final_status == STATUS_READY_WITH_WARNINGS else 0)
        + len((system_integrity_report or {}).get("warnings") or [])
        + len((determinism_report or {}).get("warnings") or [])
    )
    if warning_count:
        return STATUS_READY_WITH_WARNINGS
    return STATUS_READY


# --------------------------------------------------------------------------
# Task 4: Release Readiness Report
# --------------------------------------------------------------------------

@dataclass
class ReleaseReadinessReport:
    """The full Phase D3 report artifact -- see module docstring and
    Task 4's own "Suggested fields" list. Purely a data holder; all the
    actual aggregation happens in generate_release_readiness_report()
    below, which reads already-computed compiler/knowledge-graph/
    validation state and folds it into one of these. This report is
    READ-ONLY reporting -- it never repairs, regenerates, or revalidates
    anything a failed check finds missing (Task 5's own "Aggregation
    Rules")."""

    generated_at: str = ""
    report_version: str = RELEASE_VERSION
    compiler_version: Optional[str] = None
    graph_version: Optional[str] = None
    compiler_ready: bool = False
    graph_ready: bool = False
    system_integrity: str = "unknown"  # System Integrity Report's own overall_status
    determinism: str = "unknown"  # Determinism Report's own overall_status
    overall_status: str = "unknown"  # READY | READY_WITH_WARNINGS | FAILED
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    release_status: str = "unknown"  # same closed set as overall_status -- the one final verdict

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_release_readiness_report(
    *,
    compiler_validation_report: Optional[Dict[str, Any]] = None,
    knowledge_graph_validation_report: Optional[Dict[str, Any]] = None,
    compiler_readiness_report: Optional[Dict[str, Any]] = None,
    knowledge_graph_readiness_report: Optional[Dict[str, Any]] = None,
    compiler_build_summary: Optional[Dict[str, Any]] = None,
    knowledge_graph_build_summary: Optional[Dict[str, Any]] = None,
    system_integrity_report: Optional[Dict[str, Any]] = None,
    determinism_report: Optional[Dict[str, Any]] = None,
    compiler_manifest: Optional[Dict[str, Any]] = None,
    knowledge_graph_manifest: Optional[Dict[str, Any]] = None,
    compiler_fingerprint: Optional[str] = None,
    knowledge_graph_fingerprint: Optional[str] = None,
    compiler_statistics: Optional[Dict[str, Any]] = None,
    knowledge_graph_statistics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase D3 Task 4. Aggregates the fourteen already-computed
    artifacts named in the task's own ARCHITECTURAL RESPONSIBILITY list
    -- never recomputes, revalidates, or repairs any of them (Task 5).
    Every argument defaults to None so this function can also be called
    against a partial/hand-built fixture (e.g. a test exercising a
    "missing report" path); a missing artifact is folded into the
    release decision as a failing verdict (see determine_release_status()
    above) and surfaced as a report-level error below, never guessed at.

    Read-only over every argument: nothing handed in is ever mutated.
    Returned as a plain dict (report.to_dict()), matching every earlier
    phase's own "plain, storable dict" convention, and so it can be
    handed directly to validation.release_state.
    set_current_release_readiness_report()."""
    compiler_build_summary = compiler_build_summary or {}
    knowledge_graph_build_summary = knowledge_graph_build_summary or {}
    compiler_manifest = compiler_manifest or {}
    knowledge_graph_manifest = knowledge_graph_manifest or {}

    compiler_final_status = compiler_build_summary.get("build_status")
    graph_final_status = knowledge_graph_build_summary.get("build_status")

    release_status = determine_release_status(
        compiler_final_status, graph_final_status,
        system_integrity_report, determinism_report,
    )

    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = list(
        (system_integrity_report or {}).get("warnings") or []
    ) + list(
        (determinism_report or {}).get("warnings") or []
    )

    def _missing(name: str, artifact: Optional[Any]) -> None:
        if artifact is None:
            errors.append({
                "severity": "error",
                "rule": "artifact_missing",
                "message": f"{name} was not supplied to Phase D3 -- "
                           "release readiness cannot be fully assessed.",
            })

    _missing("compiler_validation_report", compiler_validation_report)
    _missing("knowledge_graph_validation_report", knowledge_graph_validation_report)
    _missing("compiler_readiness_report", compiler_readiness_report)
    _missing("knowledge_graph_readiness_report", knowledge_graph_readiness_report)
    _missing("compiler_build_summary", compiler_build_summary or None)
    _missing("knowledge_graph_build_summary", knowledge_graph_build_summary or None)
    _missing("system_integrity_report", system_integrity_report)
    _missing("determinism_report", determinism_report)

    errors.extend((system_integrity_report or {}).get("errors") or [])
    errors.extend((determinism_report or {}).get("errors") or [])

    compiler_ready = bool(compiler_readiness_report) and bool(
        compiler_readiness_report.get("ready")
    )
    graph_ready = bool(knowledge_graph_readiness_report) and bool(
        knowledge_graph_readiness_report.get("ready")
    )
    system_integrity_status = (system_integrity_report or {}).get("overall_status", "unknown")
    determinism_status = (determinism_report or {}).get("overall_status", "unknown")

    compiler_version = compiler_manifest.get("compiler_version")
    graph_version = (
        knowledge_graph_manifest.get("graph_version")
        or knowledge_graph_manifest.get("graph_schema_version")
    )

    summary = (
        f"Release {release_status}: compiler={compiler_final_status or 'unknown'} "
        f"(ready={compiler_ready}), graph={graph_final_status or 'unknown'} "
        f"(ready={graph_ready}), system_integrity={system_integrity_status}, "
        f"determinism={determinism_status}; {len(errors)} error(s), "
        f"{len(warnings)} warning(s) across every existing Phase B-D2 "
        "report."
    )

    report = ReleaseReadinessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        compiler_version=compiler_version,
        graph_version=graph_version,
        compiler_ready=compiler_ready,
        graph_ready=graph_ready,
        system_integrity=system_integrity_status,
        determinism=determinism_status,
        overall_status=release_status,
        warnings=warnings,
        errors=errors,
        summary=summary,
        release_status=release_status,
    )
    return report.to_dict()


# --------------------------------------------------------------------------
# Task 7: Pipeline Integration -- the one pass pipeline.py calls
# --------------------------------------------------------------------------

def finalize_release(
    *,
    compiler_validation_report: Optional[Dict[str, Any]] = None,
    knowledge_graph_validation_report: Optional[Dict[str, Any]] = None,
    compiler_readiness_report: Optional[Dict[str, Any]] = None,
    knowledge_graph_readiness_report: Optional[Dict[str, Any]] = None,
    compiler_build_summary: Optional[Dict[str, Any]] = None,
    knowledge_graph_build_summary: Optional[Dict[str, Any]] = None,
    system_integrity_report: Optional[Dict[str, Any]] = None,
    determinism_report: Optional[Dict[str, Any]] = None,
    compiler_manifest: Optional[Dict[str, Any]] = None,
    knowledge_graph_manifest: Optional[Dict[str, Any]] = None,
    compiler_fingerprint: Optional[str] = None,
    knowledge_graph_fingerprint: Optional[str] = None,
    compiler_statistics: Optional[Dict[str, Any]] = None,
    knowledge_graph_statistics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase D3's single pipeline.py integration point (mirrors
    compiler.finalize.finalize_compiler_build()'s and knowledge_graph.
    finalize.finalize_knowledge_graph()'s own two-artifacts-together
    shape, one layer up). Must run AFTER validation.determinism.
    validate_determinism() (so `determinism_report` is available to
    aggregate) -- see module docstring's PIPELINE INTEGRATION section
    and pipeline.py's own comment at the call site.

    Returns both the release status and the full report together, ready
    to be handed to validation.release_state.
    set_current_release_readiness_report()/set_current_release_status().
    This pass performs no analysis of its own beyond
    generate_release_readiness_report()'s own aggregation (which itself
    calls determine_release_status() internally) -- it only assembles
    artifacts Phases B-D2 already produced.

    Read-only over every argument, and never regenerates, revalidates,
    or repairs a single field anywhere -- see module docstring's
    ARCHITECTURAL RESPONSIBILITY and Task 5's own AGGREGATION RULES."""
    report = generate_release_readiness_report(
        compiler_validation_report=compiler_validation_report,
        knowledge_graph_validation_report=knowledge_graph_validation_report,
        compiler_readiness_report=compiler_readiness_report,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        compiler_build_summary=compiler_build_summary,
        knowledge_graph_build_summary=knowledge_graph_build_summary,
        system_integrity_report=system_integrity_report,
        determinism_report=determinism_report,
        compiler_manifest=compiler_manifest,
        knowledge_graph_manifest=knowledge_graph_manifest,
        compiler_fingerprint=compiler_fingerprint,
        knowledge_graph_fingerprint=knowledge_graph_fingerprint,
        compiler_statistics=compiler_statistics,
        knowledge_graph_statistics=knowledge_graph_statistics,
    )
    return {
        "release_readiness_report": report,
        "release_status": report["release_status"],
    }
