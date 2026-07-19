"""
modules/master_knowledge_compiler/statistics.py — M5.3
Deliverable #8: Compiler Statistics Builder.

Assembles immutable CompilerStatistics from all compiled artifacts.
"""
from __future__ import annotations

from modules.master_knowledge_compiler.enums import CompilationOutcome
from modules.master_knowledge_compiler.models import (
    CompilerStatistics,
    ConceptIndex,
    CrossReferenceIndex,
    DependencyMap,
    LearningProgression,
    MetadataIndex,
    RetrievalIndex,
)

__all__ = [
    "CompilerStatisticsBuilder",
    "default_statistics_builder",
]


class CompilerStatisticsBuilder:
    """Assembles CompilerStatistics from all compiled M5.3 artifacts."""

    def build(
        self,
        graph: object,
        concept_index: ConceptIndex,
        dependency_map: DependencyMap,
        learning_progression: LearningProgression,
        retrieval_index: RetrievalIndex,
        metadata_index: MetadataIndex,
        cross_reference_index: CrossReferenceIndex,
        compiler_version: str,
        package_version: str,
    ) -> CompilerStatistics:
        nodes = getattr(graph, "nodes", ())
        edges = getattr(graph, "edges", ())

        all_outcomes = [
            concept_index.outcome,
            dependency_map.outcome,
            learning_progression.outcome,
            retrieval_index.outcome,
            metadata_index.outcome,
            cross_reference_index.outcome,
        ]

        if all(o == CompilationOutcome.COMPLETE for o in all_outcomes):
            overall = CompilationOutcome.COMPLETE
        elif any(o == CompilationOutcome.ERROR for o in all_outcomes):
            overall = CompilationOutcome.ERROR
        elif all(o == CompilationOutcome.EMPTY for o in all_outcomes):
            overall = CompilationOutcome.EMPTY
        else:
            overall = CompilationOutcome.PARTIAL

        return CompilerStatistics(
            total_nodes_compiled=len(concept_index.entries),
            total_edges_compiled=len(dependency_map.edges),
            total_concepts=concept_index.statistics.total_concepts,
            total_dependencies=dependency_map.statistics.total_edges,
            total_learning_steps=learning_progression.total_steps,
            total_index_entries=len(retrieval_index.entries),
            total_cross_references=cross_reference_index.total_references,
            total_metadata_entries=len(metadata_index.entries),
            compilation_outcome=overall,
            compiler_version=compiler_version,
            package_version=package_version,
            graph_node_count=len(nodes),
            graph_edge_count=len(edges),
        )


#: Module-level singleton.
default_statistics_builder = CompilerStatisticsBuilder()
