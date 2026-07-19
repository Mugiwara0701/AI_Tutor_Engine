"""
modules/master_knowledge_compiler/engine.py — M5.3: the
MasterKnowledgeCompiler — top-level pipeline coordinator.

Consumes a SemanticGraph (M5.2E) and produces a sealed, immutable
MasterKnowledgePackage ready for Phase 2.

Pipeline:
  1. GraphReadinessValidator   → validate graph readiness
  2. ConceptCompiler           → ConceptIndex
  3. DependencyCompiler        → DependencyMap
  4. LearningProgressionCompiler → LearningProgression
  5. RetrievalIndexCompiler    → RetrievalIndex
  6. MetadataCompiler          → MetadataIndex
  7. CrossReferenceBuilder     → CrossReferenceIndex
  8. CompilerStatisticsBuilder → CompilerStatistics
  9. Package assembly          → MasterKnowledgePackage (Deliverable #9)
 10. MasterJSONSerializer      → SerializationResult (Deliverable #10)

Nothing in M5.1–M5.2E is modified.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from modules.master_knowledge_compiler.config import (
    MasterKnowledgeCompilerConfig,
    default_config,
)
from modules.master_knowledge_compiler.concept_compiler import (
    ConceptCompiler,
    default_concept_compiler,
)
from modules.master_knowledge_compiler.cross_reference_builder import (
    CrossReferenceBuilder,
    default_cross_reference_builder,
)
from modules.master_knowledge_compiler.dependency_compiler import (
    DependencyCompiler,
    default_dependency_compiler,
)
from modules.master_knowledge_compiler.enums import CompilationOutcome, PackageStatus
from modules.master_knowledge_compiler.exceptions import (
    MasterKnowledgeCompilerError,
    PackageBuildError,
)
from modules.master_knowledge_compiler.graph_validator import (
    GraphReadinessValidator,
    default_graph_readiness_validator,
)
from modules.master_knowledge_compiler.learning_compiler import (
    LearningProgressionCompiler,
    default_learning_compiler,
)
from modules.master_knowledge_compiler.metadata_compiler import (
    MetadataCompiler,
    default_metadata_compiler,
)
from modules.master_knowledge_compiler.models import (
    DEFAULT_PACKAGE_MODEL_VERSION,
    CompilerManifest,
    CompilerVersion,
    MasterKnowledgePackage,
)
from modules.master_knowledge_compiler.retrieval_compiler import (
    RetrievalIndexCompiler,
    default_retrieval_compiler,
)
from modules.master_knowledge_compiler.serializer import (
    MasterJSONSerializer,
    SerializationResult,
    default_serializer,
)
from modules.master_knowledge_compiler.statistics import (
    CompilerStatisticsBuilder,
    default_statistics_builder,
)

__all__ = [
    "MasterKnowledgeCompiler",
    "default_compiler",
    "compile_graph",
]

# Stable UUID namespace for package_id generation (UUID5).
_PACKAGE_NAMESPACE = uuid.UUID("d4e5f6a7-b8c9-0123-def0-234567890123")


def _deterministic_package_id(graph_id: str, compiler_version: str) -> str:
    name = f"{graph_id}:{compiler_version}"
    return str(uuid.uuid5(_PACKAGE_NAMESPACE, name or "empty"))


class MasterKnowledgeCompiler:
    """
    Top-level M5.3 compiler.  Accepts a SemanticGraph from M5.2E and
    produces an immutable, versioned MasterKnowledgePackage.

    Usage:
        compiler = MasterKnowledgeCompiler()
        package = compiler.compile(semantic_graph)
        result  = compiler.serialize(package)
    """

    def __init__(
        self,
        config: Optional[MasterKnowledgeCompilerConfig] = None,
        graph_validator: Optional[GraphReadinessValidator] = None,
        concept_compiler: Optional[ConceptCompiler] = None,
        dependency_compiler: Optional[DependencyCompiler] = None,
        learning_compiler: Optional[LearningProgressionCompiler] = None,
        retrieval_compiler: Optional[RetrievalIndexCompiler] = None,
        metadata_compiler: Optional[MetadataCompiler] = None,
        cross_reference_builder: Optional[CrossReferenceBuilder] = None,
        statistics_builder: Optional[CompilerStatisticsBuilder] = None,
        serializer: Optional[MasterJSONSerializer] = None,
    ) -> None:
        self._cfg = config or default_config
        self._validator = graph_validator or GraphReadinessValidator(config=self._cfg)
        self._concept = concept_compiler or ConceptCompiler(config=self._cfg)
        self._dependency = dependency_compiler or DependencyCompiler(config=self._cfg)
        self._learning = learning_compiler or LearningProgressionCompiler(config=self._cfg)
        self._retrieval = retrieval_compiler or RetrievalIndexCompiler(config=self._cfg)
        self._metadata = metadata_compiler or MetadataCompiler(config=self._cfg)
        self._xref = cross_reference_builder or CrossReferenceBuilder(config=self._cfg)
        self._stats = statistics_builder or default_statistics_builder
        self._serializer = serializer or default_serializer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile(self, graph: object) -> MasterKnowledgePackage:
        """
        Full pipeline: validate → compile → assemble → seal.

        Returns a sealed MasterKnowledgePackage.
        """
        diagnostics: List[str] = []

        try:
            return self._run_pipeline(graph, diagnostics)
        except MasterKnowledgeCompilerError:
            raise
        except Exception as exc:
            raise PackageBuildError(
                f"Unexpected error in MasterKnowledgeCompiler: {exc}"
            ) from exc

    def serialize(self, package: MasterKnowledgePackage) -> SerializationResult:
        """Serialize *package* to JSON using the configured serializer."""
        return self._serializer.serialize(package, indent=self._cfg.json_indent)

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        graph: object,
        diagnostics: List[str],
    ) -> MasterKnowledgePackage:

        # 1. Graph readiness validation
        vr = self._validator.validate(graph)
        if vr.diagnostics:
            diagnostics.extend(
                f"[GraphValidation] {d.code}: {d.message}" for d in vr.diagnostics
            )
            if vr.has_errors and self._cfg.strict_graph_validation:
                raise PackageBuildError(
                    "Graph readiness validation failed (strict mode): "
                    + "; ".join(d.message for d in vr.diagnostics if d.severity.value == "error")
                )

        # 2. Concept compilation
        concept_index = self._concept.compile(graph)

        # 3. Dependency compilation
        dependency_map = self._dependency.compile(graph)

        # 4. Learning progression
        learning_progression = self._learning.compile(concept_index, dependency_map)

        # 5. Retrieval index
        retrieval_index = self._retrieval.compile(concept_index, dependency_map, graph)

        # 6. Metadata
        metadata_index = self._metadata.compile(graph)

        # 7. Cross references
        cross_reference_index = self._xref.build(concept_index, graph)

        # 8. Statistics
        statistics = self._stats.build(
            graph=graph,
            concept_index=concept_index,
            dependency_map=dependency_map,
            learning_progression=learning_progression,
            retrieval_index=retrieval_index,
            metadata_index=metadata_index,
            cross_reference_index=cross_reference_index,
            compiler_version=self._cfg.compiler_version,
            package_version=self._cfg.package_version,
        )

        # 9. Overall outcome
        outcome = statistics.compilation_outcome

        # 10. Manifest + Version
        graph_metadata = getattr(graph, "metadata", None)
        graph_id = getattr(graph_metadata, "graph_id", "") if graph_metadata else ""
        engine_version = getattr(graph_metadata, "engine_version", "") if graph_metadata else ""
        graph_nodes = getattr(graph, "nodes", ())
        graph_edges = getattr(graph, "edges", ())

        compiler_version_obj = CompilerVersion(
            compiler_version=self._cfg.compiler_version,
            package_version=self._cfg.package_version,
        )

        package_id = _deterministic_package_id(graph_id, self._cfg.compiler_version)

        manifest = CompilerManifest(
            package_id=package_id,
            graph_id=graph_id,
            graph_engine_version=engine_version,
            graph_node_count=len(graph_nodes),
            graph_edge_count=len(graph_edges),
            compiler_version=compiler_version_obj,
            diagnostics=tuple(diagnostics),
            status=PackageStatus.SEALED,
        )

        return MasterKnowledgePackage(
            manifest=manifest,
            concept_index=concept_index,
            dependency_map=dependency_map,
            learning_progression=learning_progression,
            retrieval_index=retrieval_index,
            metadata_index=metadata_index,
            cross_reference_index=cross_reference_index,
            statistics=statistics,
            outcome=outcome,
        )


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

#: Module-level singleton compiler.
default_compiler = MasterKnowledgeCompiler()


def compile_graph(graph: object) -> MasterKnowledgePackage:
    """Convenience function: compile via the module-level default compiler."""
    return default_compiler.compile(graph)
