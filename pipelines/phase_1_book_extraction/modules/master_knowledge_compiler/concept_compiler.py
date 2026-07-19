"""
modules/master_knowledge_compiler/concept_compiler.py — M5.3
Deliverable #2: Concept Compiler.

Compiles SemanticNodes (M5.2E) into a ConceptIndex.
Never re-interprets educational meaning — classification uses
semantic_role and object_type_key from the graph directly.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.master_knowledge_compiler.config import MasterKnowledgeCompilerConfig, default_config
from modules.master_knowledge_compiler.enums import CompilationOutcome, ConceptCategory
from modules.master_knowledge_compiler.models import (
    ConceptEntry,
    ConceptIndex,
    ConceptStatistics,
)

__all__ = [
    "ConceptCompiler",
    "default_concept_compiler",
    "ROLE_TO_CATEGORY",
    "TYPE_TO_CATEGORY",
]

# ---------------------------------------------------------------------------
# Classification mappings (deterministic, no LLM)
# ---------------------------------------------------------------------------

ROLE_TO_CATEGORY: Dict[str, ConceptCategory] = {
    "defines_concept": ConceptCategory.CONCEPT,
    "states_prerequisite": ConceptCategory.CONCEPT,
    "frames_teaching_intent": ConceptCategory.CONCEPT,
    "surfaces_misconception": ConceptCategory.CONCEPT,
    "exemplifies_concept": ConceptCategory.EXAMPLE,
    "states_learning_objective": ConceptCategory.RULE,
    "describes_strategy": ConceptCategory.PROCEDURE,
    "sequences_instruction": ConceptCategory.PROCEDURE,
    "enables_transfer": ConceptCategory.PRINCIPLE,
    "states_scientific_goal": ConceptCategory.HYPOTHESIS,
    "directs_observation": ConceptCategory.EXPERIMENT,
    "frames_reasoning": ConceptCategory.PRINCIPLE,
    "references_concepts_visually": ConceptCategory.FIGURE,
    "serves_visual_purpose": ConceptCategory.FIGURE,
    "fulfills_teaching_function": ConceptCategory.FIGURE,
    "expresses_comparison": ConceptCategory.TABLE,
    "conveys_relationship": ConceptCategory.TABLE,
    "serves_educational_purpose": ConceptCategory.TABLE,
}

TYPE_TO_CATEGORY: Dict[str, ConceptCategory] = {
    "concept": ConceptCategory.CONCEPT,
    "definition": ConceptCategory.DEFINITION,
    "theorem": ConceptCategory.THEOREM,
    "principle": ConceptCategory.PRINCIPLE,
    "law": ConceptCategory.LAW,
    "formula": ConceptCategory.FORMULA,
    "hypothesis": ConceptCategory.HYPOTHESIS,
    "rule": ConceptCategory.RULE,
    "example": ConceptCategory.EXAMPLE,
    "figure": ConceptCategory.FIGURE,
    "table": ConceptCategory.TABLE,
    "experiment": ConceptCategory.EXPERIMENT,
    "procedure": ConceptCategory.PROCEDURE,
    "assessment": ConceptCategory.ASSESSMENT,
    "mcq": ConceptCategory.ASSESSMENT,
    "activity": ConceptCategory.PROCEDURE,
}


def _classify(node: object) -> ConceptCategory:
    """Deterministic classification from object_type_key then semantic_role."""
    type_key = str(getattr(node, "object_type_key", "") or "").lower().strip()
    role = str(getattr(node, "semantic_role", "") or "").lower().strip()

    if type_key in TYPE_TO_CATEGORY:
        return TYPE_TO_CATEGORY[type_key]
    if role in ROLE_TO_CATEGORY:
        return ROLE_TO_CATEGORY[role]
    return ConceptCategory.OTHER


class ConceptCompiler:
    """
    Compiles SemanticNodes from a SemanticGraph into a ConceptIndex.
    Never modifies M5.2E data.
    """

    def __init__(self, config: Optional[MasterKnowledgeCompilerConfig] = None) -> None:
        self._cfg = config or default_config

    def compile(
        self,
        graph: object,
    ) -> ConceptIndex:
        """
        Compile *graph* (SemanticGraph from M5.2E) into a ConceptIndex.
        """
        nodes = getattr(graph, "nodes", ())
        edges = getattr(graph, "edges", ())

        # Build neighbourhood map for related_node_ids
        neighbours: Dict[str, Set[str]] = defaultdict(set)
        for edge in edges:
            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            if src and tgt:
                neighbours[src].add(tgt)
                neighbours[tgt].add(src)

        entries: List[ConceptEntry] = []
        for node in nodes:
            node_id = getattr(node, "node_id", "")
            if not node_id:
                continue
            conf = float(getattr(node, "confidence", 0.0))
            if conf < self._cfg.min_node_confidence:
                continue

            category = _classify(node)
            related = tuple(sorted(neighbours.get(node_id, set())))

            entries.append(ConceptEntry(
                node_id=node_id,
                object_key=getattr(node, "object_key", ""),
                object_type_key=getattr(node, "object_type_key", ""),
                semantic_role=getattr(node, "semantic_role", "unknown"),
                category=category,
                confidence=conf,
                pattern_key=getattr(node, "pattern_key", None),
                related_node_ids=related,
            ))

        # Deterministic ordering by node_id
        entries.sort(key=lambda e: e.node_id)

        stats = self._compute_statistics(entries)
        outcome = CompilationOutcome.COMPLETE if entries else CompilationOutcome.EMPTY

        return ConceptIndex(
            entries=tuple(entries),
            statistics=stats,
            outcome=outcome,
        )

    @staticmethod
    def _compute_statistics(entries: List[ConceptEntry]) -> ConceptStatistics:
        by_cat: Dict[str, int] = defaultdict(int)
        by_role: Dict[str, int] = defaultdict(int)
        confidences = [e.confidence for e in entries]

        for e in entries:
            by_cat[e.category.value] += 1
            by_role[e.semantic_role] += 1

        avg = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        mn = round(min(confidences), 4) if confidences else 0.0
        mx = round(max(confidences), 4) if confidences else 0.0

        return ConceptStatistics(
            total_concepts=len(entries),
            by_category=dict(by_cat),
            by_semantic_role=dict(by_role),
            average_confidence=avg,
            min_confidence=mn,
            max_confidence=mx,
        )


#: Module-level singleton.
default_concept_compiler = ConceptCompiler()
