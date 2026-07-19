"""
modules/master_knowledge_compiler/retrieval_compiler.py — M5.3
Deliverable #5: Retrieval Index Compiler.

Generates optimized, flat indexes for O(1) lookup across all retrieval
dimensions — without requiring graph traversal at query time.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.master_knowledge_compiler.config import MasterKnowledgeCompilerConfig, default_config
from modules.master_knowledge_compiler.enums import CompilationOutcome, IndexType
from modules.master_knowledge_compiler.models import (
    ConceptIndex,
    DependencyMap,
    IndexEntry,
    RetrievalIndex,
)

__all__ = [
    "RetrievalIndexCompiler",
    "default_retrieval_compiler",
]


class RetrievalIndexCompiler:
    """
    Compiles a RetrievalIndex from the ConceptIndex and DependencyMap.
    All sub-indexes are deterministically ordered (sorted by key, then node_id).
    """

    def __init__(self, config: Optional[MasterKnowledgeCompilerConfig] = None) -> None:
        self._cfg = config or default_config

    def compile(
        self,
        concept_index: ConceptIndex,
        dependency_map: DependencyMap,
        graph: object,
    ) -> RetrievalIndex:
        entries = concept_index.entries
        edges = getattr(graph, "edges", ())

        # ── by_semantic_role ──────────────────────────────────────────
        by_role: Dict[str, List[str]] = defaultdict(list)
        for e in entries:
            by_role[e.semantic_role].append(e.node_id)

        # ── by_educational_role (concept_category) ────────────────────
        by_edu: Dict[str, List[str]] = defaultdict(list)
        for e in entries:
            by_edu[e.category.value].append(e.node_id)

        # ── by_taxonomy_key (object_type_key) ─────────────────────────
        by_tax: Dict[str, List[str]] = defaultdict(list)
        for e in entries:
            if e.object_type_key:
                by_tax[e.object_type_key].append(e.node_id)

        # ── by_concept_category ───────────────────────────────────────
        by_cat: Dict[str, List[str]] = defaultdict(list)
        for e in entries:
            by_cat[e.category.value].append(e.node_id)

        # ── by_pattern_key ────────────────────────────────────────────
        by_pattern: Dict[str, List[str]] = defaultdict(list)
        for e in entries:
            if e.pattern_key:
                by_pattern[e.pattern_key].append(e.node_id)

        # ── prerequisite_lookup ───────────────────────────────────────
        prereq_lookup: Dict[str, List[str]] = {}
        for node_id, prereqs in dependency_map.prerequisite_map.items():
            prereq_lookup[node_id] = sorted(prereqs)

        # ── relationship_lookup: node_id → adjacent node_ids ─────────
        rel_lookup: Dict[str, Set[str]] = defaultdict(set)
        for edge in edges:
            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            if src and tgt:
                rel_lookup[src].add(tgt)
                rel_lookup[tgt].add(src)

        # Convert Sets → sorted tuples for determinism
        def _sort_dict(d: Dict[str, list]) -> Dict[str, Tuple[str, ...]]:
            return {k: tuple(sorted(v)) for k, v in sorted(d.items())}

        def _sort_set_dict(d: Dict[str, Set[str]]) -> Dict[str, Tuple[str, ...]]:
            return {k: tuple(sorted(v)) for k, v in sorted(d.items())}

        # Build flat IndexEntry list
        index_entries: List[IndexEntry] = []
        for key, nids in sorted(by_role.items()):
            index_entries.append(IndexEntry(
                key=key, node_ids=tuple(sorted(nids)),
                index_type=IndexType.SEMANTIC_ROLE, count=len(nids)
            ))
        for key, nids in sorted(by_edu.items()):
            index_entries.append(IndexEntry(
                key=key, node_ids=tuple(sorted(nids)),
                index_type=IndexType.EDUCATIONAL_ROLE, count=len(nids)
            ))
        for key, nids in sorted(by_tax.items()):
            index_entries.append(IndexEntry(
                key=key, node_ids=tuple(sorted(nids)),
                index_type=IndexType.TAXONOMY, count=len(nids)
            ))

        outcome = CompilationOutcome.COMPLETE if entries else CompilationOutcome.EMPTY

        return RetrievalIndex(
            by_semantic_role=_sort_dict(by_role),
            by_educational_role=_sort_dict(by_edu),
            by_taxonomy_key=_sort_dict(by_tax),
            by_concept_category=_sort_dict(by_cat),
            by_pattern_key=_sort_dict(by_pattern),
            prerequisite_lookup=_sort_dict(prereq_lookup),
            relationship_lookup=_sort_set_dict(rel_lookup),
            entries=tuple(index_entries),
            outcome=outcome,
        )


#: Module-level singleton.
default_retrieval_compiler = RetrievalIndexCompiler()
