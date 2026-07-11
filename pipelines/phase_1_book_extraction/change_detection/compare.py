"""
change_detection/compare.py — Phase E3: Artifact Comparison,
Fingerprint Comparison, and Changed Artifact Detection.

SCOPE: `compare_snapshots()` is a pure function of two BuildSnapshots
(snapshot.py's own `artifact_fingerprints` maps) -- no I/O, no registry
access, no dependency-graph traversal (that is traversal.py's own,
separate concern -- see that module). Given a PREVIOUS snapshot (or
`None` -- see MISSING PREVIOUS BUILD below) and the CURRENT snapshot,
it determines, for every artifact key seen in either:

  - added:    present in current, absent from previous
  - removed:  present in previous, absent from current
  - modified: present in both, fingerprint differs
  - unchanged_candidates: present in both, fingerprint identical

"unchanged_candidates" (not "unchanged") is deliberate: an artifact
whose OWN fingerprint is identical across builds can still have
CHANGED transitively, if something it depends on changed -- resolving
that is traversal.py's job, not this module's (see engine.py, which
subtracts traversal.py's own `affected` set from this module's
`unchanged_candidates` to get the final "genuinely unchanged" list).
This module only ever compares two flat fingerprint maps; it has no
notion of "depends on" and never reads a DependencyGraph.

DETERMINISM: every returned list is sorted (artifact keys are plain
strings -- dependency_graph.identity.node_id() values or the two
synthetic keys snapshot.py defines), so two independent runs over the
same two snapshots always return byte-identical results, independent
of dict iteration order.

MISSING PREVIOUS BUILD: `previous_fingerprints=None` (no earlier
snapshot to compare against -- e.g. this chapter's first-ever build in
this process) is treated exactly like `previous_fingerprints={}`: every
current artifact key is "added", nothing is "removed" or "modified".
This is not a special case in the code below -- `dict()` (empty) and
`None` collapse to the same `set()` either way.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def compare_snapshots(
    previous_fingerprints: Optional[Dict[str, str]],
    current_fingerprints: Dict[str, str],
) -> Dict[str, List[str]]:
    """Compares two flat `{artifact_key: fingerprint}` maps (module
    docstring). Read-only over both arguments; returns a brand new dict
    of four sorted lists -- never mutates either input map.

    `previous_fingerprints` may be `None` (see module docstring's
    MISSING PREVIOUS BUILD). `current_fingerprints` is required (Phase
    E3 always has a current build to describe -- see engine.py, which
    is the only caller and always supplies snapshot.build_snapshot()'s
    own `artifact_fingerprints` here)."""
    previous_fingerprints = previous_fingerprints or {}

    previous_keys = set(previous_fingerprints)
    current_keys = set(current_fingerprints)
    common_keys = previous_keys & current_keys

    added = sorted(current_keys - previous_keys)
    removed = sorted(previous_keys - current_keys)
    modified = sorted(
        key for key in common_keys if previous_fingerprints[key] != current_fingerprints[key]
    )
    unchanged_candidates = sorted(
        key for key in common_keys if previous_fingerprints[key] == current_fingerprints[key]
    )

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged_candidates": unchanged_candidates,
    }