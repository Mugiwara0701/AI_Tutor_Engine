"""
modules/knowledge_optimization/runtime_cache_builder.py — M5.4
Deliverable #6: Runtime Cache Generation.

Pre-computes all caches needed by Phase 2 runtime systems.
Eliminates repeated traversal of dependency graphs or concept indexes.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

from modules.knowledge_optimization.config import KnowledgeOptimizationConfig, default_config
from modules.knowledge_optimization.enums import CacheType, OptimizationOutcome
from modules.knowledge_optimization.models import CacheEntry, RuntimeCache

__all__ = ["RuntimeCacheBuilder", "default_runtime_cache_builder"]


def _transitive_prereqs(
    node_id: str,
    prereq_map: Dict[str, Tuple[str, ...]],
) -> Tuple[str, ...]:
    """BFS transitive prerequisite traversal."""
    visited: Set[str] = set()
    queue: deque = deque(prereq_map.get(node_id, ()))
    while queue:
        curr = queue.popleft()
        if curr not in visited:
            visited.add(curr)
            queue.extend(prereq_map.get(curr, ()))
    return tuple(sorted(visited))


class RuntimeCacheBuilder:
    """Builds a RuntimeCache from a MasterKnowledgePackage (M5.3)."""

    def __init__(self, config: Optional[KnowledgeOptimizationConfig] = None) -> None:
        self._cfg = config or default_config

    def build(self, package: object) -> RuntimeCache:
        ci  = getattr(package, "concept_index", None)
        dep = getattr(package, "dependency_map", None)
        lp  = getattr(package, "learning_progression", None)
        xr  = getattr(package, "cross_reference_index", None)

        entries_raw = getattr(ci, "entries", ()) if ci else ()
        prereq_map: Dict[str, Tuple[str, ...]] = {}
        if dep:
            prereq_map = {k: tuple(v) for k, v in (getattr(dep, "prerequisite_map", {}) or {}).items()}

        # concept_lookup: node_id → object_key
        concept_lookup: Dict[str, str] = {}
        educational_objects: Dict[str, str] = {}
        for e in entries_raw:
            nid = getattr(e, "node_id", "")
            ok  = getattr(e, "object_key", "")
            if nid:
                concept_lookup[nid] = ok
            if ok and nid:
                educational_objects[ok] = nid

        # dependency_traversal: node_id → all transitive prereqs
        dep_traversal: Dict[str, Tuple[str, ...]] = {
            nid: _transitive_prereqs(nid, prereq_map)
            for nid in sorted(concept_lookup)
        }

        # prerequisite_chains: ordered chain (closest first)
        prereq_chains: Dict[str, Tuple[str, ...]] = {
            nid: prereq_map.get(nid, ())
            for nid in sorted(concept_lookup)
        }

        # related_concepts: from cross-reference index
        related: Dict[str, Tuple[str, ...]] = {}
        if xr:
            for xre in getattr(xr, "entries", ()):
                nid = getattr(xre, "node_id", "")
                all_related = tuple(sorted(set(
                    list(getattr(xre, "examples", ())) +
                    list(getattr(xre, "figures", ())) +
                    list(getattr(xre, "related", ()))
                )))
                related[nid] = all_related

        # learning_path: topological order from LearningProgression
        learning_path: Tuple[str, ...] = ()
        if lp:
            steps = getattr(lp, "steps", ())
            learning_path = tuple(s.node_id for s in sorted(steps, key=lambda s: s.position))

        # Build flat CacheEntry list
        cache_entries: List[CacheEntry] = []
        for nid, ok in sorted(concept_lookup.items()):
            cache_entries.append(CacheEntry(
                key=nid, value=ok,
                cache_type=CacheType.CONCEPT_LOOKUP,
                hit_priority=1,
            ))
        for nid, deps in sorted(dep_traversal.items()):
            cache_entries.append(CacheEntry(
                key=nid, value=list(deps),
                cache_type=CacheType.DEPENDENCY_TRAVERSAL,
                hit_priority=2,
            ))

        outcome = OptimizationOutcome.COMPLETE if concept_lookup else OptimizationOutcome.EMPTY

        return RuntimeCache(
            concept_lookup=dict(sorted(concept_lookup.items())),
            dependency_traversal=dict(sorted(dep_traversal.items())),
            related_concepts=dict(sorted(related.items())),
            learning_path=learning_path,
            educational_objects=dict(sorted(educational_objects.items())),
            prerequisite_chains=dict(sorted(prereq_chains.items())),
            entries=tuple(cache_entries),
            total_entries=len(cache_entries),
            outcome=outcome,
        )


default_runtime_cache_builder = RuntimeCacheBuilder()
