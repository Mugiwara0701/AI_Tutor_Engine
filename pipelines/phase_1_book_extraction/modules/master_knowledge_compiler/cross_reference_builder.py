"""
modules/master_knowledge_compiler/cross_reference_builder.py — M5.3
Deliverable #7: Cross Reference Builder.

Builds pre-resolved cross-reference indexes so every concept's related
objects (examples, figures, experiments, etc.) can be retrieved in O(1)
without graph traversal.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.master_knowledge_compiler.config import MasterKnowledgeCompilerConfig, default_config
from modules.master_knowledge_compiler.enums import CompilationOutcome, ConceptCategory
from modules.master_knowledge_compiler.models import (
    ConceptIndex,
    CrossReferenceEntry,
    CrossReferenceIndex,
)

__all__ = [
    "CrossReferenceBuilder",
    "default_cross_reference_builder",
]

# Map ConceptCategory → cross-reference bucket name
_CAT_TO_BUCKET: Dict[ConceptCategory, str] = {
    ConceptCategory.EXAMPLE: "examples",
    ConceptCategory.FIGURE: "figures",
    ConceptCategory.EXPERIMENT: "experiments",
    ConceptCategory.PROCEDURE: "procedures",
    ConceptCategory.ASSESSMENT: "assessments",
    ConceptCategory.TABLE: "tables",
}


class CrossReferenceBuilder:
    """
    Builds a CrossReferenceIndex from the ConceptIndex and the graph edges.

    Every cross-reference entry is pre-resolved — no graph traversal at
    lookup time.
    """

    def __init__(self, config: Optional[MasterKnowledgeCompilerConfig] = None) -> None:
        self._cfg = config or default_config

    def build(self, concept_index: ConceptIndex, graph: object) -> CrossReferenceIndex:
        edges = getattr(graph, "edges", ())

        # Build adjacency from graph edges
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        for edge in edges:
            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            if src and tgt:
                adjacency[src].add(tgt)
                adjacency[tgt].add(src)

        # Build category lookup for fast bucket assignment
        category_map: Dict[str, ConceptCategory] = {
            e.node_id: e.category for e in concept_index.entries
        }

        entries: List[CrossReferenceEntry] = []
        total_refs = 0

        for entry in concept_index.entries:
            node_id = entry.node_id
            neighbours = adjacency.get(node_id, set())

            # Classify each neighbour into its bucket
            buckets: Dict[str, List[str]] = defaultdict(list)
            for nid in neighbours:
                cat = category_map.get(nid, ConceptCategory.OTHER)
                bucket = _CAT_TO_BUCKET.get(cat, "related")
                buckets[bucket].append(nid)

            def _sorted(b: str) -> Tuple[str, ...]:
                return tuple(sorted(buckets.get(b, [])))

            xref = CrossReferenceEntry(
                node_id=node_id,
                object_key=entry.object_key,
                examples=_sorted("examples"),
                figures=_sorted("figures"),
                experiments=_sorted("experiments"),
                procedures=_sorted("procedures"),
                assessments=_sorted("assessments"),
                tables=_sorted("tables"),
                related=_sorted("related"),
            )
            entries.append(xref)
            total_refs += (
                len(xref.examples) + len(xref.figures) + len(xref.experiments)
                + len(xref.procedures) + len(xref.assessments)
                + len(xref.tables) + len(xref.related)
            )

        # Deterministic ordering
        entries.sort(key=lambda e: e.node_id)
        outcome = CompilationOutcome.COMPLETE if entries else CompilationOutcome.EMPTY

        return CrossReferenceIndex(
            entries=tuple(entries),
            total_references=total_refs,
            outcome=outcome,
        )


#: Module-level singleton.
default_cross_reference_builder = CrossReferenceBuilder()
