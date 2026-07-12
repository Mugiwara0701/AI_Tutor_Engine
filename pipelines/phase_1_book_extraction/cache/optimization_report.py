"""
cache/optimization_report.py — Phase F4.2: the CacheOptimizationReport
data holder.

Matches every earlier phase's own "dataclass + to_dict(), all
computation happens in the owning module" convention (see
cache/report.py's own CacheValidationReport, F4.1, one responsibility
over). All computation itself happens in reuse.py's own
analyze_cache_reuse() -- never here.

WHAT THIS REPORTS: cross-run cache reuse analysis over every build
Phase F4.1's own snapshot_store/index already persisted -- how many
builds have a readable/valid fingerprint snapshot, how often
consecutive builds' own fingerprints actually changed (fingerprint
"churn"), and the longest run of consecutive builds whose fingerprints
stayed identical (a proxy for how "cache-friendly" this project's own
build history has been). This is purely read-only, purely derived from
already-persisted CacheEntry records -- it introduces no new
persistence of its own (every field here is recomputed fresh on every
call from cache.index.cache_history()'s own already-persisted history,
never itself written to storage).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase, bumped only if the REPORT SHAPE
# this module produces itself changes in a way a consumer should be
# able to detect.
CACHE_OPTIMIZATION_REPORT_VERSION = "F4.2"


@dataclass
class CacheOptimizationReport:
    """The full Phase F4.2 Cache Optimization Report -- a cross-run
    analysis over every persisted CacheEntry (Phase F4.1's own
    cache.index.cache_history()), not a single-run report.

    FIELD NOTES:
    - `total_builds`: how many build_ids cache.index.list_cache_entries()
      currently returns, regardless of whether each one's own record
      could be loaded.
    - `readable_snapshots` / `invalid_or_corrupt_snapshots`: how many of
      those builds' own persisted records could be loaded AND passed
      Phase F4.2's own structural validation (reuse.validate_cache_entry())
      vs. could not (unreadable via CacheReadError, or read but
      malformed via CacheSnapshotInvalidError) -- always sums to
      `total_builds`.
    - `comparable_pairs`: how many CONSECUTIVE pairs of readable
      snapshots this report could actually compare (one fewer than
      `readable_snapshots` when every readable snapshot is itself
      contiguous; fewer still if an unreadable/invalid snapshot sits
      between two readable ones, breaking that particular pair).
    - `unchanged_pairs` / `changed_pairs`: of `comparable_pairs`, how
      many had identical vs. differing `fingerprint_snapshot` dicts --
      the exact same pure equality comparison Phase F4.1's own
      cache.validation._fingerprints_changed() already performs
      per-run, applied here across the whole persisted history instead
      of just "this run vs. the previous one."
    - `fingerprint_churn_rate`: `changed_pairs / comparable_pairs`, or
      None if `comparable_pairs` is 0 (fewer than two comparable
      snapshots exist yet -- not zero, since zero would misleadingly
      imply "no churn" rather than "not enough data").
    - `longest_unchanged_streak`: the longest run of consecutive
      comparable pairs that were all unchanged (a proxy for how
      "cache-friendly", i.e. how reusable, this project's own recent
      build history has been) -- 0 if `comparable_pairs` is 0.
    - `most_recent_build_id` / `most_recent_status`: the newest
      persisted build's own id and CacheEntry `build_status`, or None
      if `total_builds` is 0.
    - `warnings`: human-readable notes (e.g. which build_ids were
      unreadable/invalid) -- never raised, mirroring every other Phase
      F report's own "observability, not a failure" convention.
    """

    generated_at: str
    cache_optimization_report_version: str
    total_builds: int
    readable_snapshots: int
    invalid_or_corrupt_snapshots: int
    comparable_pairs: int
    unchanged_pairs: int
    changed_pairs: int
    fingerprint_churn_rate: Optional[float]
    longest_unchanged_streak: int
    most_recent_build_id: Optional[str] = None
    most_recent_status: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def new_generated_at(generated_at: Optional[str] = None) -> str:
    """Small shared helper so reuse.py never hand-rolls its own
    `datetime.now(timezone.utc).isoformat()` call a second time --
    mirrors cache.report.new_generated_at()'s own role, F4.1, one
    responsibility over."""
    return generated_at or datetime.now(timezone.utc).isoformat()
