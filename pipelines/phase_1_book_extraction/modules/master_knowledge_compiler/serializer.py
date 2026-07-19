"""
modules/master_knowledge_compiler/serializer.py — M5.3
Deliverable #10: Master JSON Serializer.

Produces deterministic, versioned, canonically ordered JSON from a
MasterKnowledgePackage.  Same input always produces byte-identical output.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from modules.master_knowledge_compiler.enums import SerializationFormat
from modules.master_knowledge_compiler.exceptions import SerializationError
from modules.master_knowledge_compiler.models import MasterKnowledgePackage

__all__ = [
    "MasterJSONSerializer",
    "SerializationResult",
    "default_serializer",
]


class SerializationResult:
    """
    The result of a serialization run.

    Attributes:
        package:        The original MasterKnowledgePackage (unchanged).
        format:         The serialization format used.
        payload:        The serialized payload (dict or JSON string).
        package_id:     Manifest package_id.
        byte_count:     Byte length of the payload (for JSON format).
    """

    __slots__ = ("package", "format", "payload", "package_id", "byte_count")

    def __init__(
        self,
        package: MasterKnowledgePackage,
        format: SerializationFormat,
        payload: Any,
    ) -> None:
        self.package = package
        self.format = format
        self.payload = payload
        self.package_id = package.manifest.package_id
        self.byte_count = len(payload.encode("utf-8")) if isinstance(payload, str) else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "format": self.format.value,
            "byte_count": self.byte_count,
            "outcome": self.package.outcome.value,
        }


class MasterJSONSerializer:
    """
    Serializes a MasterKnowledgePackage to a deterministic JSON string
    or plain dict.

    Requirements:
    - Sorted keys for canonical ordering.
    - Deterministic: same input always produces identical output.
    - Versioned: package version is embedded in the output.
    - Immutable: never modifies the input package.
    """

    def serialize(
        self,
        package: MasterKnowledgePackage,
        format: SerializationFormat = SerializationFormat.JSON,
        indent: Optional[int] = 2,
    ) -> SerializationResult:
        """
        Serialize *package* to *format*.

        Parameters
        ----------
        package:
            The MasterKnowledgePackage to serialize.
        format:
            JSON (default) or DICT.
        indent:
            JSON indent level (2 by default for readability).
        """
        try:
            package_dict = package.to_dict()
        except Exception as exc:
            raise SerializationError(
                f"MasterKnowledgePackage.to_dict() failed: {exc}"
            ) from exc

        if format == SerializationFormat.JSON:
            try:
                # sort_keys=True ensures canonical ordering
                payload = json.dumps(
                    package_dict,
                    ensure_ascii=False,
                    indent=indent,
                    sort_keys=True,
                )
            except Exception as exc:
                raise SerializationError(
                    f"JSON serialization failed for package "
                    f"{package.manifest.package_id!r}: {exc}"
                ) from exc
        else:
            payload = package_dict

        return SerializationResult(
            package=package,
            format=format,
            payload=payload,
        )

    def to_json(self, package: MasterKnowledgePackage, indent: int = 2) -> str:
        """Convenience: serialize to JSON string."""
        result = self.serialize(package, format=SerializationFormat.JSON, indent=indent)
        return result.payload  # type: ignore[return-value]

    def to_dict(self, package: MasterKnowledgePackage) -> Dict[str, Any]:
        """Convenience: serialize to plain dict."""
        result = self.serialize(package, format=SerializationFormat.DICT)
        return result.payload  # type: ignore[return-value]


#: Module-level singleton.
default_serializer = MasterJSONSerializer()
