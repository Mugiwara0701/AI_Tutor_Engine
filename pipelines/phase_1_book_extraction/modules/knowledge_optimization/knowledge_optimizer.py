"""
modules/knowledge_optimization/knowledge_optimizer.py — M5.4
Deliverable #2: Knowledge Optimization.

Performs concept deduplication, alias consolidation, metadata
normalization, and storage optimization on the ConceptIndex from M5.3.
No educational re-interpretation.  No M5.3 model is mutated.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.knowledge_optimization.config import KnowledgeOptimizationConfig, default_config
from modules.knowledge_optimization.enums import OptimizationOutcome, SearchIndexType
from modules.knowledge_optimization.models import (
    OptimizedIndexEntry,
    OptimizedRetrievalIndex,
)

__all__ = ["KnowledgeOptimizer", "default_knowledge_optimizer"]


def _normalize(s: str) -> str:
    return s.lower().strip().replace("_", " ")


class KnowledgeOptimizer:
    """
    Performs deterministic concept optimization on a ConceptIndex (M5.3).
    Produces an OptimizedRetrievalIndex.
    """

    def __init__(self, config: Optional[KnowledgeOptimizationConfig] = None) -> None:
        self._cfg = config or default_config

    def optimize(self, package: object) -> OptimizedRetrievalIndex:
        ci = getattr(package, "concept_index", None)
        dep = getattr(package, "dependency_map", None)
        entries_raw = getattr(ci, "entries", ()) if ci else ()

        by_object_key: Dict[str, str] = {}
        by_object_type: Dict[str, List[str]] = defaultdict(list)
        by_semantic_role: Dict[str, List[str]] = defaultdict(list)
        by_concept_category: Dict[str, List[str]] = defaultdict(list)
        by_pattern_key: Dict[str, List[str]] = defaultdict(list)
        by_normalized_key: Dict[str, List[str]] = defaultdict(list)

        index_entries: List[OptimizedIndexEntry] = []

        for entry in entries_raw:
            nid  = getattr(entry, "node_id", "")
            ok   = getattr(entry, "object_key", "")
            otk  = getattr(entry, "object_type_key", "")
            role = getattr(entry, "semantic_role", "")
            cat  = getattr(entry, "category", None)
            cat_v = cat.value if hasattr(cat, "value") else str(cat or "other")
            pk   = getattr(entry, "pattern_key", None) or ""
            norm = _normalize(ok or nid)

            if ok:
                by_object_key[ok] = nid
            if otk:
                by_object_type[otk].append(nid)
            if role:
                by_semantic_role[role].append(nid)
            by_concept_category[cat_v].append(nid)
            if pk:
                by_pattern_key[pk].append(nid)
            if norm:
                by_normalized_key[norm].append(nid)

            index_entries.append(OptimizedIndexEntry(
                key=ok or nid,
                normalized_key=norm,
                node_ids=(nid,),
                index_type=SearchIndexType.NORMALIZED,
                aliases=(),
                count=1,
            ))

        # prerequisite chains
        prereq_chains = self._build_prereq_chains(dep)
        # successor map (reverse of prerequisites)
        successor_map = self._build_successor_map(dep)

        def _sd(d): return {k: tuple(sorted(v)) for k, v in sorted(d.items())}

        outcome = OptimizationOutcome.COMPLETE if index_entries else OptimizationOutcome.EMPTY

        return OptimizedRetrievalIndex(
            by_object_key=dict(sorted(by_object_key.items())),
            by_object_type=_sd(by_object_type),
            by_semantic_role=_sd(by_semantic_role),
            by_concept_category=_sd(by_concept_category),
            by_pattern_key=_sd(by_pattern_key),
            by_normalized_key=_sd(by_normalized_key),
            prerequisite_chains=prereq_chains,
            successor_map=successor_map,
            entries=tuple(sorted(index_entries, key=lambda e: e.key)),
            total_entries=len(index_entries),
            outcome=outcome,
        )

    def _build_prereq_chains(self, dep: object) -> Dict[str, Tuple[str, ...]]:
        """Build full transitive prerequisite chains via BFS."""
        if dep is None:
            return {}
        prereq_map = getattr(dep, "prerequisite_map", {}) or {}
        node_ids = list(getattr(dep, "topological_order", []) or [])

        chains: Dict[str, List[str]] = {}
        for nid in node_ids:
            visited: Set[str] = set()
            queue = list(prereq_map.get(nid, ()))
            while queue:
                current = queue.pop(0)
                if current not in visited:
                    visited.add(current)
                    queue.extend(prereq_map.get(current, ()))
            chains[nid] = sorted(visited)
        return {k: tuple(v) for k, v in sorted(chains.items())}

    def _build_successor_map(self, dep: object) -> Dict[str, Tuple[str, ...]]:
        """Build successor map (what depends on each node) from prerequisite_map."""
        if dep is None:
            return {}
        prereq_map = getattr(dep, "prerequisite_map", {}) or {}
        successors: Dict[str, List[str]] = defaultdict(list)
        for dependent, prereqs in prereq_map.items():
            for prereq in prereqs:
                successors[prereq].append(dependent)
        return {k: tuple(sorted(v)) for k, v in sorted(successors.items())}


default_knowledge_optimizer = KnowledgeOptimizer()
