"""
teacher_knowledge_base/serialization.py — M6.1 (remediated)

Deterministic serialization of TeacherKnowledgeBase.
Computes content_hash and byte_size per TKBSerializationMetadata spec §9.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from canonicalization import canonical_json, sha256_hexdigest, strip_volatile

from .artifact import TeacherKnowledgeBase, _strip_extra_volatile_recursive
from .exceptions import TKBSerializationError

logger = logging.getLogger("teacher_knowledge_base.serialization")

STAGE = "serialization"


@dataclass
class TKBSerializationResult:
    artifact: TeacherKnowledgeBase
    artifact_dict: Dict[str, Any]
    canonical_json_str: str
    fingerprint: str                  # content fingerprint (volatile-stripped)
    serialization_fingerprint: str    # fingerprint of canonical_json_str

    def to_storage_dict(self) -> Dict[str, Any]:
        import copy
        d = copy.deepcopy(self.artifact_dict)
        sm = d.get("serialization_metadata") or {}
        sm["fingerprint"] = self.fingerprint
        sm["serialization_fingerprint"] = self.serialization_fingerprint
        # Inject content_hash and byte_size (spec §9)
        sm["content_hash"] = self.fingerprint
        encoded = json.dumps(d, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        sm["byte_size"] = len(encoded)
        d["serialization_metadata"] = sm
        return d


def serialize_artifact(artifact: TeacherKnowledgeBase) -> TKBSerializationResult:
    try:
        artifact_dict = artifact.to_dict()
    except Exception as exc:
        raise TKBSerializationError(f"to_dict() failed: {exc}") from exc

    try:
        canonical_str = canonical_json(artifact_dict)
    except Exception as exc:
        raise TKBSerializationError(f"canonical_json() failed: {exc}") from exc

    try:
        import copy
        stripped = strip_volatile(copy.deepcopy(artifact_dict))
        _strip_extra_volatile_recursive(stripped)
        fingerprint = sha256_hexdigest(canonical_json(stripped))
        serialization_fingerprint = sha256_hexdigest(canonical_str)
    except Exception as exc:
        raise TKBSerializationError(f"fingerprint computation failed: {exc}") from exc

    logger.info("TKB serialization: tkb_id=%s fingerprint=%s...",
                artifact.get_tkb_id(), fingerprint[:12])
    return TKBSerializationResult(
        artifact=artifact,
        artifact_dict=artifact_dict,
        canonical_json_str=canonical_str,
        fingerprint=fingerprint,
        serialization_fingerprint=serialization_fingerprint,
    )


def artifact_to_json(artifact: TeacherKnowledgeBase) -> str:
    try:
        return json.dumps(artifact.to_dict(), indent=2, sort_keys=True, default=str)
    except Exception as exc:
        raise TKBSerializationError(f"json.dumps failed: {exc}") from exc
