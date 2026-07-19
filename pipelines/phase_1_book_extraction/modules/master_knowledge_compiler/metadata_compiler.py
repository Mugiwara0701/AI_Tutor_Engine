"""
modules/master_knowledge_compiler/metadata_compiler.py — M5.3
Deliverable #6: Metadata Compiler.

Compiles structured metadata from the SemanticGraph and compiler config
into a MetadataIndex.  No textbook narrative — only structured metadata.
"""
from __future__ import annotations

from typing import List, Optional

from modules.master_knowledge_compiler.config import (
    MasterKnowledgeCompilerConfig,
    default_config,
)
from modules.master_knowledge_compiler.enums import CompilationOutcome
from modules.master_knowledge_compiler.models import (
    MetadataEntry,
    MetadataIndex,
)

__all__ = [
    "MetadataCompiler",
    "default_metadata_compiler",
]


class MetadataCompiler:
    """
    Compiles a MetadataIndex from the SemanticGraph metadata and
    compiler configuration.  No M5.2 model is modified.
    """

    def __init__(self, config: Optional[MasterKnowledgeCompilerConfig] = None) -> None:
        self._cfg = config or default_config

    def compile(self, graph: object) -> MetadataIndex:
        """
        Compile a MetadataIndex from *graph* (SemanticGraph from M5.2E).
        """
        metadata = getattr(graph, "metadata", None)
        stats = getattr(graph, "statistics", None)
        nodes = getattr(graph, "nodes", ())
        edges = getattr(graph, "edges", ())

        # ── Taxonomy metadata ─────────────────────────────────────────
        taxonomy_meta = {
            "total_object_types": len(set(
                getattr(n, "object_type_key", "") for n in nodes
                if getattr(n, "object_type_key", "")
            )),
            "unique_semantic_roles": len(set(
                getattr(n, "semantic_role", "") for n in nodes
                if getattr(n, "semantic_role", "")
            )),
            "unique_pattern_keys": len(set(
                getattr(n, "pattern_key", "") for n in nodes
                if getattr(n, "pattern_key", None)
            )),
        }

        # ── Semantic metadata ─────────────────────────────────────────
        semantic_meta = {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "graph_id": getattr(metadata, "graph_id", "") if metadata else "",
            "graph_engine_version": getattr(metadata, "engine_version", "") if metadata else "",
            "graph_source_count": getattr(metadata, "source_count", 0) if metadata else 0,
            "average_node_confidence": (
                round(
                    sum(float(getattr(n, "confidence", 0.0)) for n in nodes) / len(nodes), 4
                ) if nodes else 0.0
            ),
        }

        # ── Compiler metadata ─────────────────────────────────────────
        compiler_meta = {
            "compiler_version": self._cfg.compiler_version,
            "package_version": self._cfg.package_version,
            "progression_strategy": self._cfg.progression_strategy.value,
            "include_orphan_nodes": self._cfg.include_orphan_nodes,
            "min_node_confidence": self._cfg.min_node_confidence,
        }

        # ── Version metadata ──────────────────────────────────────────
        version_meta = {
            "m5_1": "1.0.0",
            "m5_2a": "1.0.0",
            "m5_2b": "1.0.0",
            "m5_2c": "1.0.0",
            "m5_2d": "1.0.0",
            "m5_2e": "1.0.0",
            "m5_3": self._cfg.compiler_version,
        }

        # Flat entries list (deterministically sorted by key)
        entries: List[MetadataEntry] = []
        for k, v in sorted(taxonomy_meta.items()):
            entries.append(MetadataEntry(key=k, value=v, category="taxonomy"))
        for k, v in sorted(semantic_meta.items()):
            entries.append(MetadataEntry(key=k, value=v, category="semantic"))
        for k, v in sorted(compiler_meta.items()):
            entries.append(MetadataEntry(key=k, value=v, category="compiler"))
        for k, v in sorted(version_meta.items()):
            entries.append(MetadataEntry(key=k, value=v, category="version"))

        return MetadataIndex(
            taxonomy_metadata=taxonomy_meta,
            semantic_metadata=semantic_meta,
            compiler_metadata=compiler_meta,
            version_metadata=version_meta,
            entries=tuple(entries),
            outcome=CompilationOutcome.COMPLETE,
        )


#: Module-level singleton.
default_metadata_compiler = MetadataCompiler()
