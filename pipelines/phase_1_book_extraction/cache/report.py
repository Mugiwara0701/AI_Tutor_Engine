"""
cache/report.py — Phase F4.1: the CacheValidationReport data holder.

Matches every earlier phase's own "dataclass + to_dict(), all
computation happens in the owning module" convention (see
build_executor/report.py's own ExecutionReport, one package over).
This report DOES carry one verdict (`overall_status`), mirroring
incremental_compilation_validation.report.
IncrementalCompilationValidationReport's own precedent -- all
computation itself happens in validation.py, never here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# This module's own version marker -- bumped only if the REPORT SHAPE
# this module produces itself changes in a way a consumer should be
# able to detect.
CACHE_REPORT_VERSION = "F4.1"

# Closed set of verdicts validation.py may assign. Exposed as constants
# so callers/tests never hand-roll these strings a second time.
STATUS_NO_BASELINE = "NO_BASELINE"
STATUS_CONSISTENT = "CONSISTENT"
STATUS_DIVERGENT = "DIVERGENT"


@dataclass
class CacheValidationReport:
    """The full Phase F4.1 Cache Validation Report for one
    CompilerRuntime run.

    FIELD NOTES:
    - `build_id`: this run's own Build id (Phase F2).
    - `previous_build_id`: the build id whose fingerprint snapshot this
      run's own snapshot was compared against, or None if no previous
      cache entry existed (`comparison_basis` is
      "no_previous_snapshot" in that case).
    - `comparison_basis`: "previous_snapshot" | "no_previous_snapshot"
      -- whether a real comparison was possible at all.
    - `fingerprints_changed`: True/False if a comparison was possible,
      None otherwise. A pure equality check over the current and
      previous fingerprint_snapshot dicts -- never a new fingerprint
      algorithm.
    - `execution_plan_summary`: Phase F3's own ExecutionPlan `summary`
      dict, surfaced verbatim (never recomputed a second time) so a
      reader of this report never needs to cross-reference the
      ExecutionReport separately for the basic reused/rebuilt counts
      this report's own verdict is based on.
    - `overall_status`: NO_BASELINE (no previous snapshot to compare
      against), CONSISTENT (fingerprint comparison and Phase F3's own
      reuse/rebuild outcome agree), or DIVERGENT (they disagree -- see
      `divergences` for why). Never authoritative over Phase F3's own
      decision; purely observational.
    - `divergences`: human-readable explanations for every DIVERGENT
      finding -- always empty for NO_BASELINE/CONSISTENT.
    - `warnings` / `errors`: plain strings, mirroring every earlier
      phase's own report convention.
    """

    generated_at: str
    cache_report_version: str
    build_id: str
    previous_build_id: Optional[str] = None
    comparison_basis: str = "no_previous_snapshot"
    fingerprints_changed: Optional[bool] = None
    execution_plan_summary: Dict[str, Any] = field(default_factory=dict)
    overall_status: str = STATUS_NO_BASELINE
    divergences: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def new_generated_at(generated_at: Optional[str] = None) -> str:
    """Small shared helper so validation.py never hand-rolls its own
    `datetime.now(timezone.utc).isoformat()` call a second time."""
    return generated_at or datetime.now(timezone.utc).isoformat()