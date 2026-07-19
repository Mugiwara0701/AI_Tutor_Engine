"""
modules/knowledge_optimization/cross_chapter_linker.py — M5.4
Deliverable #3: Cross-Chapter Knowledge Linking.

Discovers deterministic links between related, prerequisite, successor,
and reinforcing concepts across the compiled knowledge package.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.knowledge_optimization.config import KnowledgeOptimizationConfig, default_config
from modules.knowledge_optimization.enums import LinkType, OptimizationOutcome
from modules.knowledge_optimization.models import CrossChapterLink, CrossChapterLinkIndex

__all__ = ["CrossChapterLinker", "default_cross_chapter_linker"]

# Role pairs that form reinforcing links
_REINFORCING_PAIRS = {
    ("defines_concept",    "exemplifies_concept"),
    ("exemplifies_concept","defines_concept"),
    ("defines_concept",    "serves_visual_purpose"),
    ("defines_concept",    "expresses_comparison"),
    ("sequences_instruction","describes_strategy"),
}

_CONTRASTING_PAIRS = {
    ("defines_concept", "surfaces_misconception"),
    ("surfaces_misconception", "defines_concept"),
}


class CrossChapterLinker:
    """
    Produces CrossChapterLinks by combining dependency edges, cross-reference
    data, and semantic role pairs from the ConceptIndex.
    """

    def __init__(self, config: Optional[KnowledgeOptimizationConfig] = None) -> None:
        self._cfg = config or default_config

    def build(self, package: object) -> CrossChapterLinkIndex:
        ci  = getattr(package, "concept_index", None)
        dep = getattr(package, "dependency_map", None)
        xr  = getattr(package, "cross_reference_index", None)

        entries   = getattr(ci, "entries", ()) if ci else ()
        dep_edges = getattr(dep, "edges", ()) if dep else ()
        xr_entries = getattr(xr, "entries", ()) if xr else ()

        links: List[CrossChapterLink] = []
        seen: Set[Tuple[str, str, str]] = set()

        role_map: Dict[str, str] = {
            getattr(e, "node_id", ""): getattr(e, "semantic_role", "")
            for e in entries
        }
        conf_map: Dict[str, float] = {
            getattr(e, "node_id", ""): float(getattr(e, "confidence", 0.5))
            for e in entries
        }

        # 1. Prerequisite links from dependency edges
        for edge in dep_edges:
            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            key = (src, tgt, LinkType.PREREQUISITE.value)
            if src and tgt and key not in seen:
                seen.add(key)
                links.append(CrossChapterLink(
                    source_node_id=src,
                    target_node_id=tgt,
                    link_type=LinkType.PREREQUISITE,
                    confidence=min(1.0, float(getattr(edge, "confidence", 0.7))),
                ))

        # 2. Successor links (reverse of prerequisites)
        for edge in dep_edges:
            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            key = (tgt, src, LinkType.SUCCESSOR.value)
            if src and tgt and key not in seen:
                seen.add(key)
                links.append(CrossChapterLink(
                    source_node_id=tgt,
                    target_node_id=src,
                    link_type=LinkType.SUCCESSOR,
                    confidence=min(1.0, float(getattr(edge, "confidence", 0.7))),
                ))

        # 3. Reinforcing links from semantic role pairs
        node_ids = list(role_map.keys())
        for i, nid_a in enumerate(node_ids):
            for nid_b in node_ids[i + 1:]:
                role_a = role_map.get(nid_a, "")
                role_b = role_map.get(nid_b, "")
                pair = (role_a, role_b)
                if pair in _REINFORCING_PAIRS:
                    key = (nid_a, nid_b, LinkType.REINFORCING.value)
                    if key not in seen:
                        seen.add(key)
                        conf = round((conf_map.get(nid_a, 0.5) + conf_map.get(nid_b, 0.5)) / 2, 4)
                        links.append(CrossChapterLink(
                            source_node_id=nid_a, target_node_id=nid_b,
                            link_type=LinkType.REINFORCING, confidence=conf, hop_distance=2,
                        ))
                if pair in _CONTRASTING_PAIRS:
                    key = (nid_a, nid_b, LinkType.CONTRASTING.value)
                    if key not in seen:
                        seen.add(key)
                        conf = round((conf_map.get(nid_a, 0.5) + conf_map.get(nid_b, 0.5)) / 2, 4)
                        links.append(CrossChapterLink(
                            source_node_id=nid_a, target_node_id=nid_b,
                            link_type=LinkType.CONTRASTING, confidence=conf, hop_distance=1,
                        ))

        # 4. Related-concept links from cross-reference entries
        for xre in xr_entries:
            nid = getattr(xre, "node_id", "")
            related = getattr(xre, "related", ())
            for r in related:
                key = (nid, r, LinkType.RELATED_CONCEPT.value)
                if nid and r and key not in seen:
                    seen.add(key)
                    conf = round((conf_map.get(nid, 0.5) + conf_map.get(r, 0.5)) / 2, 4)
                    links.append(CrossChapterLink(
                        source_node_id=nid, target_node_id=r,
                        link_type=LinkType.RELATED_CONCEPT, confidence=conf,
                    ))

        # Deterministic ordering
        links.sort(key=lambda l: (l.source_node_id, l.target_node_id, l.link_type.value))

        # Build indexes
        by_src: Dict[str, List[str]] = defaultdict(list)
        by_tgt: Dict[str, List[str]] = defaultdict(list)
        by_ltype: Dict[str, List[str]] = defaultdict(list)
        for lk in links:
            by_src[lk.source_node_id].append(lk.target_node_id)
            by_tgt[lk.target_node_id].append(lk.source_node_id)
            by_ltype[lk.link_type.value].append(lk.source_node_id)

        outcome = OptimizationOutcome.COMPLETE if links else OptimizationOutcome.EMPTY

        return CrossChapterLinkIndex(
            links=tuple(links),
            by_source={k: tuple(sorted(set(v))) for k, v in sorted(by_src.items())},
            by_target={k: tuple(sorted(set(v))) for k, v in sorted(by_tgt.items())},
            by_link_type={k: tuple(sorted(set(v))) for k, v in sorted(by_ltype.items())},
            total_links=len(links),
            outcome=outcome,
        )


default_cross_chapter_linker = CrossChapterLinker()
