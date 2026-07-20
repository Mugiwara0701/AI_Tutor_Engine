"""
teacher_knowledge_base/serialization.py — M6.1: TKB deterministic
serialization.

SCOPE (per M6.1 spec §7): implements deterministic serialization of the
TeacherKnowledgeBase artifact.

DETERMINISM GUARANTEES:
  - Stable key ordering: sort_keys=True everywhere
  - Stable list ordering: all list fields are pre-sorted by builders;
    serialization never re-sorts (would break teacher-defined ordering)
  - Stable IDs: all IDs are UUID5 (content-derived) — never random
  - Stable output: identical input always produces identical JSON bytes
  - Volatile fields excluded from fingerprint: generated_at, serialized_at
    are present in the output for human readability but stripped from
    fingerprint computation (via canonicalization.strip_volatile())

REUSE: uses canonicalization.canonical_json() and sha256_hexdigest() —
the exact same strategy every other phase in this codebase already uses.
No new serialization format, no new hashing strategy.

This module produces:
  1. The raw artifact dict (for in-process use / passing to artifact manager)
  2. The canonical JSON string (for storage / fingerprinting)
  3. The serialization fingerprint (SHA-256 of canonical JSON)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from canonicalization import canonical_json, sha256_hexdigest, strip_volatile

from .artifact import TeacherKnowledgeBase
from .exceptions import TKBSerializationError

logger = logging.getLogger("teacher_knowledge_base.serialization")

STAGE = "serialization"


@dataclass
class TKBSerializationResult:
    """Output of serialize_artifact() — the artifact in all its forms."""

    artifact: TeacherKnowledgeBase
    artifact_dict: Dict[str, Any]        # JSON-safe dict
    canonical_json_str: str              # sorted, compact JSON string
    fingerprint: str                     # SHA-256 hex digest
    serialization_fingerprint: str       # fingerprint of the canonical JSON itself

    def to_storage_dict(self) -> Dict[str, Any]:
        """The dict written to storage — artifact_dict with serialization
        metadata injected at the top level (same pattern as Build Manifest)."""
        d = dict(self.artifact_dict)
        d["serialization_metadata"]["fingerprint"] = self.fingerprint
        d["serialization_metadata"]["serialization_fingerprint"] = self.serialization_fingerprint
        return d


def serialize_artifact(
    artifact: TeacherKnowledgeBase,
) -> TKBSerializationResult:
    """Serializes a TeacherKnowledgeBase to its canonical JSON form.

    Steps:
      1. artifact.to_dict() — deterministic Python dict
      2. canonical_json() — sorted, compact JSON string
      3. strip_volatile() + sha256_hexdigest() — content fingerprint
      4. sha256_hexdigest(canonical_json_str) — serialization fingerprint

    Raises TKBSerializationError if any step fails.
    """
    try:
        artifact_dict = artifact.to_dict()
    except Exception as exc:
        raise TKBSerializationError(f"to_dict() failed: {exc}") from exc

    try:
        canonical_str = canonical_json(artifact_dict)
    except Exception as exc:
        raise TKBSerializationError(f"canonical_json() failed: {exc}") from exc

    try:
        fingerprint = sha256_hexdigest(canonical_json(strip_volatile(artifact_dict)))
        serialization_fingerprint = sha256_hexdigest(canonical_str)
    except Exception as exc:
        raise TKBSerializationError(f"fingerprint computation failed: {exc}") from exc

    logger.info(
        "TKB serialization: artifact_id=%s fingerprint=%s...",
        artifact.get_artifact_id(), fingerprint[:12],
    )
    return TKBSerializationResult(
        artifact=artifact,
        artifact_dict=artifact_dict,
        canonical_json_str=canonical_str,
        fingerprint=fingerprint,
        serialization_fingerprint=serialization_fingerprint,
    )


def validate_serialization_determinism(
    result1: TKBSerializationResult,
    result2: TKBSerializationResult,
) -> bool:
    """Returns True if two serialization results from the same input
    produce identical fingerprints (determinism check).
    Called by the determinism test in tests/."""
    return result1.fingerprint == result2.fingerprint and \
           result1.serialization_fingerprint == result2.serialization_fingerprint


def artifact_to_json(artifact: TeacherKnowledgeBase) -> str:
    """Convenience: serialize an artifact to a pretty-printed JSON string
    for human-readable storage / file output. Not the canonical form —
    use canonical_json_str for fingerprinting."""
    try:
        return json.dumps(artifact.to_dict(), indent=2, sort_keys=True, default=str)
    except Exception as exc:
        raise TKBSerializationError(f"json.dumps failed: {exc}") from exc
