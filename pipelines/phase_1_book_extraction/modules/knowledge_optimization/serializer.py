"""
modules/knowledge_optimization/serializer.py — M5.4
Deliverable #10: Deterministic Serializer.

Produces canonical, stable, byte-identical JSON from an
OptimizedKnowledgePackage.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from modules.knowledge_optimization.enums import OptimizationOutcome
from modules.knowledge_optimization.exceptions import OptimizationSerializationError
from modules.knowledge_optimization.models import OptimizedKnowledgePackage

__all__ = ["OptimizationSerializer", "SerializationResult", "default_serializer"]


class SerializationResult:
    """Result of OptimizationSerializer.serialize()."""
    __slots__ = ("package", "payload", "package_id", "byte_count")

    def __init__(self, package: OptimizedKnowledgePackage, payload: Any) -> None:
        self.package    = package
        self.payload    = payload
        self.package_id = package.manifest.optimized_package_id
        self.byte_count = len(payload.encode("utf-8")) if isinstance(payload, str) else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "byte_count": self.byte_count,
            "outcome": self.package.outcome.value,
        }


class OptimizationSerializer:
    """
    Serializes an OptimizedKnowledgePackage to canonical JSON.
    sort_keys=True guarantees byte-identical output across runs.
    """

    def serialize(
        self,
        package: OptimizedKnowledgePackage,
        indent: Optional[int] = 2,
    ) -> SerializationResult:
        try:
            d = package.to_dict()
        except Exception as exc:
            raise OptimizationSerializationError(
                f"to_dict() failed for {package.manifest.optimized_package_id!r}: {exc}"
            ) from exc
        try:
            payload = json.dumps(d, ensure_ascii=False, indent=indent, sort_keys=True)
        except Exception as exc:
            raise OptimizationSerializationError(
                f"JSON serialization failed: {exc}"
            ) from exc
        return SerializationResult(package=package, payload=payload)

    def to_json(self, package: OptimizedKnowledgePackage, indent: int = 2) -> str:
        return self.serialize(package, indent=indent).payload

    def to_dict_payload(self, package: OptimizedKnowledgePackage) -> Dict[str, Any]:
        return package.to_dict()


default_serializer = OptimizationSerializer()
