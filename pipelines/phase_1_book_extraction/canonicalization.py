"""
canonicalization.py — Shared canonicalization primitives.

SCOPE: this module is the single source of truth for the canonicalization
strategy every fingerprint-producing and fingerprint-checking pass in this
codebase already relies on: which field names are volatile (VOLATILE_KEYS),
how they're stripped before hashing/comparison (strip_volatile()), how a
stripped value is turned into deterministic JSON text (canonical_json()),
and how that text is turned into a digest (sha256_hexdigest()).

WHY THIS EXISTS: compiler/fingerprints.py (Phase B5.2), knowledge_graph/
fingerprints.py (Phase C4.2), and validation/determinism.py (Phase D2) each
independently implemented this exact same four-piece strategy -- three
behaviorally-identical copies with no shared enforcement that they stay
that way. This module consolidates all three into one place; the three
call sites now import from here instead of hand-rolling their own copy.
This is a pure maintenance consolidation -- see each call site's own
docstring for why the algorithm looks the way it does (timestamp
stripping, sort_keys, compact separators, etc.); nothing about the
algorithm itself changed in this consolidation, so every fingerprint any
of the three modules already produced continues to be byte-identical.

NEVER DEPENDS ON: timestamps, memory addresses, object identities,
dictionary/set ordering, or random values -- see VOLATILE_KEYS below and
each consumer's own module docstring for exactly how each of these is
avoided.

Consumed by (as of this consolidation):
  - compiler/fingerprints.py       (Phase B5.2 registry/compiler fingerprints)
  - knowledge_graph/fingerprints.py (Phase C4.2 registry/graph fingerprints)
  - validation/determinism.py       (Phase D2 determinism validation)

This module has no dependency on any of the three -- it sits below all of
them, imports nothing project-specific, and never imports from compiler/,
knowledge_graph/, or validation/ (avoiding any risk of a circular import
with any of its three consumers).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# --------------------------------------------------------------------------
# Static, deterministic constant
# --------------------------------------------------------------------------

# Every key name any pass in this codebase excludes from fingerprinting /
# determinism comparison, at any nesting depth, in any registry item /
# manifest / statistics / build-summary / report dict. See compiler/
# fingerprints.py's own module docstring (VOLATILE FIELD FILTERING
# section) for exactly which earlier-phase field each entry corresponds
# to and why. Moved here (from compiler/fingerprints.py) as part of this
# consolidation so it lives alongside the helpers that consume it, rather
# than being owned by one of its three consumers; compiler/fingerprints.py
# re-exports it under its original name so `from compiler.fingerprints
# import VOLATILE_KEYS` (already used elsewhere in this codebase and in
# its tests) continues to work unchanged.
VOLATILE_KEYS = frozenset({
    "generated_at",             # ValidationReport / CompilerManifest / CompilerStatistics
    "enriched_at",               # compiler/enrichment.py: registry_metadata.enriched_at
    "normalized_at",             # compiler/normalization.py: normalization.normalized_at
    "resolved_at",                # compiler/references.py & compiler/relationships.py
    "created_at",                 # modules/canonical.py: creation_metadata.created_at
    "timestamp",                   # modules/canonical.py: provenance.timestamp
    "approx_memory_bytes",         # compiler/registry.py: RegistryStatistics (memory-derived)
})


# --------------------------------------------------------------------------
# Canonicalization helpers
# --------------------------------------------------------------------------

def strip_volatile(value: Any) -> Any:
    """Recursively returns a copy of `value` with every VOLATILE_KEYS
    entry removed from every dict at every nesting depth. Lists are
    walked (not sorted -- every list any consumer of this module ever
    fingerprints/compares is already produced in a deterministic,
    insertion/explicit-sort order by its owning phase; re-sorting here
    would be new, unrequested normalization behavior, not
    canonicalization). Scalars pass through unchanged. Never mutates
    `value` itself."""
    if isinstance(value, dict):
        return {
            key: strip_volatile(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [strip_volatile(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Deterministic JSON text for `value`: volatile fields stripped
    (see strip_volatile), keys sorted (so hash-randomized dict iteration
    order can never affect the result), and a compact, fixed separator
    style (so incidental whitespace differences never affect the result
    either). `default=str` is a defensive fallback only -- every value
    any consumer of this module ever canonicalizes is already plain
    JSON-compatible data (CanonicalRegistry.serialize() output, a
    manifest/statistics/build-summary/report dict), never a live
    object."""
    return json.dumps(
        strip_volatile(value),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_hexdigest(text: str) -> str:
    """SHA-256 hex digest of `text` (UTF-8 encoded) -- the final step
    every fingerprint generator in this codebase applies to
    canonical_json()'s own output."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()