"""
compiler_release/report.py — Phase F5: the CompilerReleaseManifest data
holder.

Matches every earlier phase's own "dataclass + to_dict(), all
computation happens in the owning module" convention (see
cache/report.py's own CacheValidationReport, one package over). All
computation itself happens in finalize.py, never here.

STATUS CONSTANTS: reuse compiler/finalize.py's own STATUS_READY/
STATUS_READY_WITH_WARNINGS/STATUS_FAILED string VALUES verbatim (not
new, synonymous strings) so a downstream consumer comparing statuses
across compiler-level and release-level verdicts compares like-for-like
values -- see finalize.py's own module docstring.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase, bumped only if the MANIFEST
# SHAPE this module produces itself changes in a way a consumer should
# be able to detect.
RELEASE_MANIFEST_VERSION = "F5.1"

# Reused verbatim from compiler/finalize.py -- see module docstring.
STATUS_READY = "READY"
STATUS_READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
STATUS_FAILED = "FAILED"


@dataclass
class CompilerReleaseManifest:
    """The full Phase F5 Compiler Release Manifest for one
    CompilerRuntime run.

    FIELD NOTES:
    - `build_id`: this run's own Build id (Phase F2), read verbatim.
    - `runtime_status`: this run's own RuntimeStatus value (Phase F1),
      read verbatim -- never re-derived.
    - `final_release_status`: the one new verdict this package itself
      computes -- see finalize.determine_final_release_status().
    - `build_summary`: `build_id`/`build_status`/`manifest_fingerprint`,
      each read verbatim off this run's own Build/Build Manifest
      (Phase F2). `manifest_fingerprint` is None when Phase F2's own
      manifest carries no single overall fingerprint field of its own
      (see artifact_manager/manifest.py) -- this package never derives
      one itself.
    - `execution_summary`: this run's own ExecutionReport
      `execution_statistics` dict (Phase F3, build_executor/plan.py's
      own build_summary() -- `reused_count`/`rebuilt_count`/
      `total_considered`/`requires_execution`/`is_full_reuse`), copied
      verbatim, plus `chapters_failed` -- the one count Phase F3's own
      ExecutionPlan does not itself carry (reuse/rebuild is a binary
      decision, not a success/failure classification), sourced instead
      from Phase F1's own runtime_state.get_current_progress(), the one
      existing accessor that already tracks it (see runtime/state.py).
      None if no ExecutionReport was recorded this run.
    - `cache_summary`: `has_cache_entry`/`comparison_basis`/
      `cache_overall_status`, each read verbatim off this run's own
      CacheEntry/CacheValidationReport (Phase F4).
    - `divergences`: verbatim, copied from this run's own
      CacheValidationReport.
    - `warnings` / `errors`: populated only from THIS package's own
      aggregation gaps (e.g. "no ExecutionReport was recorded this
      run") -- never a re-check of F1-F4's own already-reported issues,
      which are surfaced via `divergences` instead (see finalize.py).
    """

    release_manifest_version: str
    build_id: str
    generated_at: str

    runtime_status: str
    final_release_status: str

    build_summary: Dict[str, Any] = field(default_factory=dict)
    execution_summary: Optional[Dict[str, Any]] = None
    cache_summary: Dict[str, Any] = field(default_factory=dict)

    divergences: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def new_generated_at(generated_at: Optional[str] = None) -> str:
    """Small shared helper so finalize.py never hand-rolls its own
    `datetime.now(timezone.utc).isoformat()` call a second time --
    mirrors cache.report.new_generated_at()'s own precedent, one
    package over."""
    return generated_at or datetime.now(timezone.utc).isoformat()
