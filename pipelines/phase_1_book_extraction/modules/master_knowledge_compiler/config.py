"""
modules/master_knowledge_compiler/config.py — M5.3: immutable,
versioned configuration for the Master Knowledge Compiler.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from modules.master_knowledge_compiler.enums import (
    ProgressionStrategy,
    SerializationFormat,
)

__all__ = [
    "MasterKnowledgeCompilerConfig",
    "default_config",
    "DEFAULT_COMPILER_VERSION",
    "DEFAULT_PACKAGE_VERSION",
]

DEFAULT_COMPILER_VERSION = "1.0.0"
DEFAULT_PACKAGE_VERSION  = "1.0.0"


@dataclass(frozen=True)
class MasterKnowledgeCompilerConfig:
    """
    Immutable configuration for the MasterKnowledgeCompiler.

    Attributes:
        compiler_version:           Semantic version of the compiler.
        package_version:            Semantic version stamped on the output package.
        min_node_confidence:        Minimum node confidence to include in compilation.
        progression_strategy:       Ordering strategy for LearningProgression.
        serialization_format:       Default output format for MasterJSONSerializer.
        json_indent:                JSON indent level (None = compact).
        include_orphan_nodes:       Whether to include orphan nodes in indexes.
        strict_graph_validation:    If True, graph validation errors block compilation.
        extra:                      Reserved for future extension.
    """

    compiler_version: str = DEFAULT_COMPILER_VERSION
    package_version: str = DEFAULT_PACKAGE_VERSION
    min_node_confidence: float = 0.0
    progression_strategy: ProgressionStrategy = ProgressionStrategy.TOPOLOGICAL
    serialization_format: SerializationFormat = SerializationFormat.JSON
    json_indent: int = 2
    include_orphan_nodes: bool = True
    strict_graph_validation: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_node_confidence <= 1.0:
            raise ValueError(
                f"min_node_confidence must be in [0.0, 1.0]; "
                f"got {self.min_node_confidence!r}."
            )

    def to_dict(self) -> dict:
        return {
            "compiler_version": self.compiler_version,
            "package_version": self.package_version,
            "min_node_confidence": self.min_node_confidence,
            "progression_strategy": self.progression_strategy.value,
            "serialization_format": self.serialization_format.value,
            "json_indent": self.json_indent,
            "include_orphan_nodes": self.include_orphan_nodes,
            "strict_graph_validation": self.strict_graph_validation,
            "extra": dict(self.extra),
        }


#: Module-level singleton.
default_config = MasterKnowledgeCompilerConfig()
