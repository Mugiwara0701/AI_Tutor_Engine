"""
modules/knowledge_optimization/semantic_search_builder.py — M5.4
Deliverable #5: Semantic Search Index Preparation.

Generates normalized search keys, aliases, keyword expansions, and
role/category tags — no embedding models, no LLMs.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from modules.knowledge_optimization.config import KnowledgeOptimizationConfig, default_config
from modules.knowledge_optimization.enums import OptimizationOutcome
from modules.knowledge_optimization.models import SearchEntry, SemanticSearchIndex

__all__ = ["SemanticSearchBuilder", "default_semantic_search_builder"]

_STOPWORDS = frozenset({"a", "an", "the", "of", "in", "on", "at", "to",
                         "for", "with", "by", "from", "and", "or", "is", "are"})


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 _]", "", s.lower().strip())


def _keywords(s: str) -> Tuple[str, ...]:
    words = _normalize(s).split()
    kws = tuple(sorted(set(w for w in words if w not in _STOPWORDS and len(w) > 1)))
    return kws


def _search_rank(confidence: float, connectivity: int) -> float:
    """Deterministic rank: higher confidence + connectivity → higher rank."""
    raw = (confidence * 0.70) + (min(connectivity, 10) / 10.0 * 0.30)
    return round(min(1.0, max(0.0, raw)), 4)


class SemanticSearchBuilder:
    """Builds a SemanticSearchIndex from a ConceptIndex (M5.3)."""

    def __init__(self, config: Optional[KnowledgeOptimizationConfig] = None) -> None:
        self._cfg = config or default_config

    def build(self, package: object) -> SemanticSearchIndex:
        if not self._cfg.enable_semantic_search:
            return SemanticSearchIndex(
                entries=(), key_to_node_ids={}, alias_to_node_ids={},
                keyword_to_node_ids={}, role_to_node_ids={},
                category_to_node_ids={}, total_entries=0,
                outcome=OptimizationOutcome.EMPTY,
            )

        ci = getattr(package, "concept_index", None)
        entries_raw = getattr(ci, "entries", ()) if ci else ()

        # Build a connectivity proxy from cross_reference_index
        xr = getattr(package, "cross_reference_index", None)
        connectivity_map: Dict[str, int] = {}
        if xr:
            for xre in getattr(xr, "entries", ()):
                nid = getattr(xre, "node_id", "")
                total = sum(
                    len(getattr(xre, f, ()))
                    for f in ("examples", "figures", "experiments",
                              "procedures", "assessments", "tables", "related")
                )
                connectivity_map[nid] = total

        search_entries: List[SearchEntry] = []
        key_map: Dict[str, List[str]] = defaultdict(list)
        alias_map: Dict[str, List[str]] = defaultdict(list)
        kw_map: Dict[str, List[str]] = defaultdict(list)
        role_map: Dict[str, List[str]] = defaultdict(list)
        cat_map: Dict[str, List[str]] = defaultdict(list)

        for entry in entries_raw:
            nid  = getattr(entry, "node_id", "")
            ok   = getattr(entry, "object_key", "") or nid
            role = getattr(entry, "semantic_role", "")
            cat  = getattr(entry, "category", None)
            cat_v = cat.value if hasattr(cat, "value") else str(cat or "other")
            conf = float(getattr(entry, "confidence", 0.5))
            conn = connectivity_map.get(nid, 0)

            sk   = _normalize(ok)
            kws  = _keywords(ok)
            rank = _search_rank(conf, conn)

            # Aliases: object_type_key (normalized), semantic_role (normalized)
            otk = _normalize(getattr(entry, "object_type_key", "") or "")
            aliases = tuple(sorted(set(filter(None, [otk]))))

            search_entries.append(SearchEntry(
                node_id=nid,
                search_key=sk,
                aliases=aliases,
                keywords=kws,
                role_tag=role,
                category_tag=cat_v,
                search_rank=rank,
            ))

            key_map[sk].append(nid)
            for a in aliases:
                alias_map[a].append(nid)
            for kw in kws:
                kw_map[kw].append(nid)
            role_map[role].append(nid)
            cat_map[cat_v].append(nid)

        # Sort by descending rank, then node_id for determinism
        search_entries.sort(key=lambda e: (-e.search_rank, e.node_id))

        def _sd(d): return {k: tuple(sorted(v)) for k, v in sorted(d.items())}

        outcome = OptimizationOutcome.COMPLETE if search_entries else OptimizationOutcome.EMPTY

        return SemanticSearchIndex(
            entries=tuple(search_entries),
            key_to_node_ids=_sd(key_map),
            alias_to_node_ids=_sd(alias_map),
            keyword_to_node_ids=_sd(kw_map),
            role_to_node_ids=_sd(role_map),
            category_to_node_ids=_sd(cat_map),
            total_entries=len(search_entries),
            outcome=outcome,
        )


default_semantic_search_builder = SemanticSearchBuilder()
