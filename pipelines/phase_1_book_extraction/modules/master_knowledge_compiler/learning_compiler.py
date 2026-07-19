"""
modules/master_knowledge_compiler/learning_compiler.py — M5.3
Deliverable #4: Learning Progression Compiler.

Generates a deterministic, dependency-respecting learning sequence from
the ConceptIndex and DependencyMap.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from modules.master_knowledge_compiler.config import MasterKnowledgeCompilerConfig, default_config
from modules.master_knowledge_compiler.enums import CompilationOutcome, ProgressionStrategy
from modules.master_knowledge_compiler.models import (
    ConceptIndex,
    DependencyMap,
    LearningProgression,
    LearningStep,
)

__all__ = [
    "LearningProgressionCompiler",
    "default_learning_compiler",
]


class LearningProgressionCompiler:
    """
    Compiles a deterministic LearningProgression from a ConceptIndex
    and DependencyMap.

    Strategy: TOPOLOGICAL — prerequisites appear before dependents.
    Tie-breaking: alphabetical node_id (fully deterministic).
    """

    def __init__(self, config: Optional[MasterKnowledgeCompilerConfig] = None) -> None:
        self._cfg = config or default_config

    def compile(
        self,
        concept_index: ConceptIndex,
        dependency_map: DependencyMap,
    ) -> LearningProgression:
        """
        Build a LearningProgression from *concept_index* and *dependency_map*.
        """
        # Build a lookup for concept entries
        concept_lookup: Dict[str, object] = {
            e.node_id: e for e in concept_index.entries
        }

        if self._cfg.progression_strategy == ProgressionStrategy.TOPOLOGICAL:
            ordered_ids = self._topological_order(concept_index, dependency_map)
        else:
            # Confidence-weighted: highest confidence first (secondary: node_id)
            ordered_ids = sorted(
                concept_lookup.keys(),
                key=lambda nid: (
                    -concept_lookup[nid].confidence,  # type: ignore[union-attr]
                    nid
                ),
            )

        steps: List[LearningStep] = []
        for position, node_id in enumerate(ordered_ids):
            entry = concept_lookup.get(node_id)
            if entry is None:
                continue
            prereqs = dependency_map.prerequisites_of(node_id)
            steps.append(LearningStep(
                position=position,
                node_id=node_id,
                object_key=entry.object_key,  # type: ignore[union-attr]
                semantic_role=entry.semantic_role,  # type: ignore[union-attr]
                concept_category=entry.category.value,  # type: ignore[union-attr]
                prerequisite_node_ids=prereqs,
                confidence=entry.confidence,  # type: ignore[union-attr]
            ))

        outcome = CompilationOutcome.COMPLETE if steps else CompilationOutcome.EMPTY

        return LearningProgression(
            steps=tuple(steps),
            strategy=self._cfg.progression_strategy,
            total_steps=len(steps),
            outcome=outcome,
        )

    def _topological_order(
        self,
        concept_index: ConceptIndex,
        dependency_map: DependencyMap,
    ) -> List[str]:
        """
        Use DependencyMap.topological_order when available, falling back to
        alphabetical sort of all concept node_ids.
        """
        known_ids: Set[str] = {e.node_id for e in concept_index.entries}
        topo = [nid for nid in dependency_map.topological_order if nid in known_ids]
        # Append any concept nodes not in the topological order (orphans / no deps)
        in_topo: Set[str] = set(topo)
        extras = sorted(nid for nid in known_ids if nid not in in_topo)
        return topo + extras


#: Module-level singleton.
default_learning_compiler = LearningProgressionCompiler()
