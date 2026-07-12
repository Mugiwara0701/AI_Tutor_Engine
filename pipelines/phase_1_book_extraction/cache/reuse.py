"""
cache/reuse.py — Phase F4.2: Cache Reuse (previous-snapshot discovery,
selection, loading, validation; cross-run cache optimization
reporting).

SCOPE: this module completes the cache lifecycle Phase F4.1 started --
F4.1 persists a run's own fingerprint snapshot so a LATER run can read
it; F4.2 is that later run's own read side. Everything here is a thin
layer over F4.1's already-existing surface (cache.index.
list_cache_entries()/cache_history(), cache.snapshot_store.
load_fingerprint_snapshot()) plus two things F4.1 does not itself do:

  1. VALIDATION -- F4.1's own load_fingerprint_snapshot() trusts
     storage.download_json()'s return value completely; it never checks
     the record it got back is actually shaped like a CacheEntry
     (build_cache_entry()'s own shape). validate_cache_entry() below is
     that check.

  2. FALLBACK SELECTION -- F4.1's own snapshot_store.
     load_previous_cache_entry() looks at exactly one candidate (the
     single most recent persisted build strictly before `before_build_id`)
     and returns None if that one candidate's record can't be loaded,
     even when an older, perfectly good snapshot exists right behind it.
     select_previous_snapshot() below walks the full persisted history
     newest-to-oldest and returns the first candidate that is both
     readable AND passes validate_cache_entry() -- "one bad record must
     never hide every other build's own reusable snapshot," the exact
     same principle cache.index.cache_history()'s own module docstring
     already states for cache history as a whole, applied here to
     previous-snapshot selection specifically.

REUSE, DON'T DUPLICATE (task's own explicit requirement): every
discovery/loading/persistence primitive this module calls is imported
from cache.index / cache.snapshot_store, unchanged. This module
introduces no new persistence format, no new storage client, and no
new fingerprint algorithm -- `_fingerprints_changed()` (cross-run churn
analysis, below) is the exact same pure equality comparison
cache.validation._fingerprints_changed() already performs per-run,
reused here by import rather than reimplemented, applied across the
whole persisted history instead of just "this run vs. the previous
one."

READ-ONLY: every function in this module only ever reads already-
persisted CacheEntry records via the reused storage instance; nothing
here writes to storage, mutates a Build/Build Manifest/ExecutionPlan,
or makes a reuse/rebuild decision for any chapter (see cache/__init__.py's
own "WHAT THIS IS NOT" section -- Phase F4 is never execution gating).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .exceptions import CacheReadError, CacheSnapshotInvalidError
from .index import cache_history, list_cache_entries
from .optimization_report import (
    CACHE_OPTIMIZATION_REPORT_VERSION,
    CacheOptimizationReport,
    new_generated_at,
)
from .snapshot_store import CACHE_ENTRY_VERSION, load_fingerprint_snapshot
from .validation import _fingerprints_changed

logger = logging.getLogger("cache.reuse")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_cache_entry(cache_entry: Any, build_id: str) -> Dict[str, Any]:
    """Structural validation for one previously persisted CacheEntry --
    the "is this actually a CacheEntry" check F4.1's own
    load_fingerprint_snapshot() never performs (see module docstring's
    point 1). `build_id` is the id this record was loaded FOR (the path
    it was read from), used both for error messages and to catch a
    record whose own `build_id` field doesn't match the path it was
    stored at.

    Returns `cache_entry` unchanged (never copies, never mutates --
    same read-only contract every other Phase F4 function in this
    package already follows) if it passes every check below. Raises
    CacheSnapshotInvalidError otherwise:

      * `cache_entry` is not a dict at all
      * missing `build_id`
      * `cache_entry["build_id"] != build_id` (a storage-layer mixup --
        this build_id's own record path somehow returned a different
        build's own entry)
      * missing `fingerprint_snapshot`, or `fingerprint_snapshot` is not
        itself a dict

    Deliberately tolerant of an unknown/missing `cache_entry_version`
    (logged as a warning, never raised) -- a future Phase F4.x that
    bumps CACHE_ENTRY_VERSION should still be able to read an older
    snapshot's own basic shape, same "forward-compatible reader" stance
    schema-versioned records elsewhere in this codebase already take
    (e.g. build_metadata's own *_VERSION constants are never enforced
    as a hard equality check on read)."""
    if not isinstance(cache_entry, dict):
        raise CacheSnapshotInvalidError(
            build_id, f"expected a dict, got {type(cache_entry).__name__}"
        )

    entry_build_id = cache_entry.get("build_id")
    if not entry_build_id:
        raise CacheSnapshotInvalidError(build_id, "missing required 'build_id' field")
    if entry_build_id != build_id:
        raise CacheSnapshotInvalidError(
            build_id,
            f"'build_id' field ({entry_build_id!r}) does not match the build "
            f"this record was loaded for ({build_id!r})",
        )

    if "fingerprint_snapshot" not in cache_entry:
        raise CacheSnapshotInvalidError(
            build_id, "missing required 'fingerprint_snapshot' field"
        )
    if not isinstance(cache_entry["fingerprint_snapshot"], dict):
        raise CacheSnapshotInvalidError(
            build_id,
            "'fingerprint_snapshot' must be a dict, got "
            f"{type(cache_entry['fingerprint_snapshot']).__name__}",
        )

    entry_version = cache_entry.get("cache_entry_version")
    if entry_version is not None and entry_version != CACHE_ENTRY_VERSION:
        logger.warning(
            "cache: fingerprint snapshot for build %r has cache_entry_version "
            "%r (expected %r) -- reading it anyway (forward-compatible: only "
            "the basic CacheEntry shape is enforced).",
            build_id, entry_version, CACHE_ENTRY_VERSION,
        )

    return cache_entry


def _load_and_validate(storage: Any, build_id: str) -> Optional[Dict[str, Any]]:
    """Loads (F4.1's own snapshot_store.load_fingerprint_snapshot()) and
    validates (validate_cache_entry() above) one build_id's own
    CacheEntry. Returns None -- never raises -- for either an unreadable
    record (CacheReadError) or a readable-but-malformed one
    (CacheSnapshotInvalidError), logging a warning identifying which,
    so a caller walking multiple candidates can simply skip to the next
    one."""
    try:
        cache_entry = load_fingerprint_snapshot(storage, build_id)
    except CacheReadError:
        logger.warning(
            "cache: skipping build %s while selecting a previous snapshot -- "
            "its fingerprint snapshot record could not be read.",
            build_id, exc_info=True,
        )
        return None

    try:
        return validate_cache_entry(cache_entry, build_id)
    except CacheSnapshotInvalidError:
        logger.warning(
            "cache: skipping build %s while selecting a previous snapshot -- "
            "its fingerprint snapshot record was read but is not a valid "
            "CacheEntry.",
            build_id, exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Discovery + selection
# ---------------------------------------------------------------------------

def discover_previous_snapshot_candidates(
    storage: Any, *, before_build_id: Optional[str] = None
) -> List[str]:
    """Every build_id with a persisted fingerprint snapshot, strictly
    before `before_build_id` (or every persisted build_id, if
    `before_build_id` is None), newest-looking-id first -- the exact
    candidate order select_previous_snapshot() below walks. Pure
    discovery: reuses cache.index.list_cache_entries() unchanged, this
    function only filters and reverses its own already-chronological
    return value; it never touches storage a second time."""
    entries = list_cache_entries(storage)
    if before_build_id is not None:
        entries = [build_id for build_id in entries if build_id < before_build_id]
    return list(reversed(entries))


def select_previous_snapshot(
    storage: Any,
    *,
    before_build_id: Optional[str] = None,
    max_candidates: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Discovers, selects, loads, AND validates the most recent usable
    previous CacheEntry -- see module docstring's point 2 for exactly
    how this differs from (and is a drop-in, more resilient replacement
    for) F4.1's own snapshot_store.load_previous_cache_entry(): where
    that function gives up after its one candidate fails to load, this
    one keeps walking older candidates until it finds one that is both
    readable and structurally valid, or the candidate list (optionally
    capped at `max_candidates`) is exhausted.

    Returns None if no candidate exists at all (first run ever), or if
    every candidate examined was unreadable/invalid -- not an error,
    same "nothing usable yet is a normal state" convention every other
    Phase F4 read path already applies. A run consuming this result
    therefore behaves exactly as if it had no cache history at all,
    never crashes because one or more older records happen to be
    corrupt.

    Never mutates any candidate it loads; returns the winning
    CacheEntry unchanged."""
    candidates = discover_previous_snapshot_candidates(
        storage, before_build_id=before_build_id
    )
    if max_candidates is not None:
        candidates = candidates[:max_candidates]

    for build_id in candidates:
        cache_entry = _load_and_validate(storage, build_id)
        if cache_entry is not None:
            return cache_entry

    return None


def select_previous_fingerprint_snapshot(
    storage: Any,
    *,
    before_build_id: Optional[str] = None,
    max_candidates: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Thin convenience wrapper around select_previous_snapshot() for a
    caller that only wants the winning CacheEntry's own
    `fingerprint_snapshot` sub-field -- mirrors F4.1's own
    snapshot_store.load_previous_fingerprint_snapshot()'s exact role,
    one function over."""
    cache_entry = select_previous_snapshot(
        storage, before_build_id=before_build_id, max_candidates=max_candidates
    )
    if cache_entry is None:
        return None
    return cache_entry.get("fingerprint_snapshot")


def list_reusable_snapshots(storage: Any) -> List[Dict[str, Any]]:
    """Every persisted CacheEntry that is both readable AND
    structurally valid, oldest first -- reuses cache.index.
    cache_history() (F4.1's own "one failure must never stop the rest"
    loader) and additionally filters out any entry cache_history()
    itself successfully loaded but that fails Phase F4.2's own
    validate_cache_entry() check. Used by analyze_cache_reuse() below,
    and available directly to any caller that wants the full reusable
    history rather than just the single most recent entry."""
    reusable: List[Dict[str, Any]] = []
    for cache_entry in cache_history(storage):
        build_id = cache_entry.get("build_id")
        try:
            reusable.append(validate_cache_entry(cache_entry, build_id))
        except CacheSnapshotInvalidError:
            logger.warning(
                "cache: excluding build %s from reusable-snapshot history -- "
                "its record was read but is not a valid CacheEntry.",
                build_id, exc_info=True,
            )
    return reusable


# ---------------------------------------------------------------------------
# Cross-run cache optimization reporting
# ---------------------------------------------------------------------------

def analyze_cache_reuse(
    storage: Any, *, generated_at: Optional[str] = None
) -> Dict[str, Any]:
    """Generates a CacheOptimizationReport (see optimization_report.py)
    -- a read-only, cross-run analysis of how "cache-friendly" this
    project's own persisted build history has been: how many builds
    have a usable snapshot, and how often consecutive builds' own
    fingerprints actually changed vs. stayed identical.

    Pure read + compute over cache.index.list_cache_entries()/
    cache_history() and this module's own validate_cache_entry() --
    performs no new fingerprinting (see `_fingerprints_changed()`,
    reused unchanged from cache.validation) and persists nothing of its
    own. Deterministic for a given persisted history and `generated_at`
    (same contract cache.validation.validate_execution_against_cache()
    already documents for its own report)."""
    all_build_ids = list_cache_entries(storage)
    total_builds = len(all_build_ids)

    warnings: List[str] = []
    # oldest -> newest, matching list_cache_entries()'s own chronological
    # order, so "consecutive pairs" below means "consecutive in time."
    ordered_entries: List[Optional[Dict[str, Any]]] = []
    for build_id in all_build_ids:
        entry = _load_and_validate(storage, build_id)
        if entry is None:
            warnings.append(
                f"build {build_id!r}: fingerprint snapshot unreadable or "
                "invalid -- excluded from churn analysis."
            )
        ordered_entries.append(entry)

    readable_snapshots = sum(1 for e in ordered_entries if e is not None)
    invalid_or_corrupt_snapshots = total_builds - readable_snapshots

    comparable_pairs = 0
    unchanged_pairs = 0
    changed_pairs = 0
    current_streak = 0
    longest_unchanged_streak = 0

    for previous_entry, current_entry in zip(ordered_entries, ordered_entries[1:]):
        if previous_entry is None or current_entry is None:
            # An unreadable/invalid record breaks the chain -- this pair
            # is simply not comparable, same "skip, don't fail" handling
            # every other Phase F4 aggregate already applies.
            current_streak = 0
            continue

        comparable_pairs += 1
        changed = _fingerprints_changed(
            current_entry.get("fingerprint_snapshot") or {},
            previous_entry.get("fingerprint_snapshot") or {},
        )
        if changed:
            changed_pairs += 1
            current_streak = 0
        else:
            unchanged_pairs += 1
            current_streak += 1
            longest_unchanged_streak = max(longest_unchanged_streak, current_streak)

    fingerprint_churn_rate = (
        (changed_pairs / comparable_pairs) if comparable_pairs else None
    )

    most_recent_build_id: Optional[str] = None
    most_recent_status: Optional[str] = None
    if all_build_ids:
        most_recent_build_id = all_build_ids[-1]
        most_recent_entry = ordered_entries[-1]
        if most_recent_entry is not None:
            most_recent_status = most_recent_entry.get("build_status")

    report = CacheOptimizationReport(
        generated_at=new_generated_at(generated_at),
        cache_optimization_report_version=CACHE_OPTIMIZATION_REPORT_VERSION,
        total_builds=total_builds,
        readable_snapshots=readable_snapshots,
        invalid_or_corrupt_snapshots=invalid_or_corrupt_snapshots,
        comparable_pairs=comparable_pairs,
        unchanged_pairs=unchanged_pairs,
        changed_pairs=changed_pairs,
        fingerprint_churn_rate=fingerprint_churn_rate,
        longest_unchanged_streak=longest_unchanged_streak,
        most_recent_build_id=most_recent_build_id,
        most_recent_status=most_recent_status,
        warnings=warnings,
    )
    return report.to_dict()
