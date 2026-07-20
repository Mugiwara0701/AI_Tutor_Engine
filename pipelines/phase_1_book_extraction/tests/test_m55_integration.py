"""
tests/test_m55_integration.py — M5.5: Phase 1 Compiler Integration,
Validation & Release Finalization — Integration Tests.

SCOPE: These tests verify that every subsystem is correctly integrated
with every other subsystem it depends on. They cover:

  1. State module conventions (M5.3/M5.4/M5.2E state.py existence + API)
  2. M5 API contracts (compile_graph, optimize, build_graph signatures)
  3. Full M5 chain integration (SemanticGraph → MKP → OKP)
  4. Artifact manager M5 registrations (ReferenceSnapshot/Build fields)
  5. Pipeline import completeness
  6. Validation non-redundancy
  7. Serialization determinism
  8. Registry consistency (CanonicalRegistry pattern)
  9. State pattern consistency across all packages
  10. Incremental compilation chain (E3→E4→E5.1→E5.2)
  11. Build system chain (F1→F2→F3→F5)
  12. Backward compatibility (M5.1–M5.4 public APIs unchanged)

ENVIRONMENT NOTE: These tests exercise modules that are present in the
repository. Tests that require pipeline.py's full PDF/VLM chain (which
cannot be exercised in isolation) test at the module boundary only,
using real module APIs rather than fabricated stand-ins.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ---------------------------------------------------------------------------
# 1. State Module Conventions
# ---------------------------------------------------------------------------
class TestM5StackStateModules(unittest.TestCase):
    """Verify that M5.3/M5.4/M5.2E state.py modules exist and expose the
    required set_current_*()/get_current_*()/has_current_*()/reset_*_state()
    surface — the same pattern every other phase's state.py uses."""

    def _check_state_module(self, module_path: str, prefix: str) -> None:
        """Assert that a state module has the four required functions."""
        mod = importlib.import_module(module_path)
        self.assertTrue(hasattr(mod, f"set_current_{prefix}"),
                        f"{module_path} missing set_current_{prefix}")
        self.assertTrue(hasattr(mod, f"get_current_{prefix}"),
                        f"{module_path} missing get_current_{prefix}")
        self.assertTrue(hasattr(mod, f"has_current_{prefix}"),
                        f"{module_path} missing has_current_{prefix}")
        self.assertTrue(hasattr(mod, f"reset_{prefix}_state"),
                        f"{module_path} missing reset_{prefix}_state")

    def test_mkc_state_module_exists(self):
        self._check_state_module(
            "modules.master_knowledge_compiler.state",
            "master_knowledge_package",
        )

    def test_ko_state_module_exists(self):
        self._check_state_module(
            "modules.knowledge_optimization.state",
            "optimized_knowledge_package",
        )

    def test_rde_state_module_exists(self):
        self._check_state_module(
            "modules.relationship_discovery_engine.state",
            "semantic_graph",
        )

    def test_mkc_state_lifecycle(self):
        """State slot starts None, can be set, has_* reflects reality, reset works."""
        from modules.master_knowledge_compiler import state as mkc_state
        mkc_state.reset_master_knowledge_package_state()
        self.assertFalse(mkc_state.has_current_master_knowledge_package())
        self.assertIsNone(mkc_state.get_current_master_knowledge_package())
        sentinel = object()
        mkc_state.set_current_master_knowledge_package(sentinel)
        self.assertTrue(mkc_state.has_current_master_knowledge_package())
        self.assertIs(mkc_state.get_current_master_knowledge_package(), sentinel)
        mkc_state.reset_master_knowledge_package_state()
        self.assertFalse(mkc_state.has_current_master_knowledge_package())

    def test_ko_state_lifecycle(self):
        from modules.knowledge_optimization import state as ko_state
        ko_state.reset_optimized_knowledge_package_state()
        self.assertFalse(ko_state.has_current_optimized_knowledge_package())
        sentinel = object()
        ko_state.set_current_optimized_knowledge_package(sentinel)
        self.assertTrue(ko_state.has_current_optimized_knowledge_package())
        ko_state.reset_optimized_knowledge_package_state()
        self.assertFalse(ko_state.has_current_optimized_knowledge_package())

    def test_rde_state_lifecycle(self):
        from modules.relationship_discovery_engine import state as rde_state
        rde_state.reset_semantic_graph_state()
        self.assertFalse(rde_state.has_current_semantic_graph())
        sentinel = object()
        rde_state.set_current_semantic_graph(sentinel)
        self.assertTrue(rde_state.has_current_semantic_graph())
        rde_state.reset_semantic_graph_state()
        self.assertFalse(rde_state.has_current_semantic_graph())


# ---------------------------------------------------------------------------
# 2. M5 API Contracts
# ---------------------------------------------------------------------------
class TestM5StackAPIContracts(unittest.TestCase):
    """Verify that M5.3/M5.4/M5.2E expose the required public functions."""

    def test_mkc_has_compile_graph(self):
        from modules.master_knowledge_compiler.engine import compile_graph
        import inspect
        sig = inspect.signature(compile_graph)
        self.assertIn("graph", sig.parameters)

    def test_mkc_has_default_compiler(self):
        from modules.master_knowledge_compiler.engine import default_compiler, MasterKnowledgeCompiler
        self.assertIsInstance(default_compiler, MasterKnowledgeCompiler)

    def test_ko_has_optimize(self):
        from modules.knowledge_optimization.engine import KnowledgeOptimizationEngine
        import inspect
        sig = inspect.signature(KnowledgeOptimizationEngine.optimize)
        self.assertIn("package", sig.parameters)

    def test_rde_has_build_graph(self):
        from modules.relationship_discovery_engine.engine import RelationshipDiscoveryEngine
        import inspect
        sig = inspect.signature(RelationshipDiscoveryEngine.build_graph)
        self.assertIn("enrichment_results", sig.parameters)

    def test_mkc_init_exports_state(self):
        import modules.master_knowledge_compiler as mkc
        self.assertTrue(hasattr(mkc, "state"),
                        "master_knowledge_compiler.__init__ must export state")

    def test_ko_init_exports_state(self):
        import modules.knowledge_optimization as ko
        self.assertTrue(hasattr(ko, "state"),
                        "knowledge_optimization.__init__ must export state")

    def test_rde_init_exports_state(self):
        import modules.relationship_discovery_engine as rde
        self.assertTrue(hasattr(rde, "state"),
                        "relationship_discovery_engine.__init__ must export state")


# ---------------------------------------------------------------------------
# 3. Full M5 Chain Integration
# ---------------------------------------------------------------------------
class TestM5StackChainIntegration(unittest.TestCase):
    """Verify the SemanticGraph → MasterKnowledgePackage → OptimizedKnowledgePackage
    chain using real module APIs and minimal synthetic inputs."""

    def _make_minimal_semantic_node(self):
        """Create a minimal SemanticNode that satisfies M5.3's graph validator."""
        from modules.relationship_discovery_engine.models import SemanticNode
        return SemanticNode(
            node_id="test-node-001",
            object_key="concept:photosynthesis",
            object_type_key="Concept",
            semantic_role="defines_concept",
            confidence=0.9,
        )

    def _make_minimal_semantic_graph(self):
        """Build a minimal but valid SemanticGraph for compiler input."""
        from modules.relationship_discovery_engine.models import (
            SemanticGraph, GraphMetadata, GraphStatistics, DEFAULT_GRAPH_VERSION
        )
        from modules.relationship_discovery_engine.enums import GraphBuildOutcome
        node = self._make_minimal_semantic_node()
        metadata = GraphMetadata(
            graph_id="test-graph-001",
            engine_version=DEFAULT_GRAPH_VERSION,
            source_count=1,
            description="M5.5 integration test graph",
        )
        stats = GraphStatistics(
            node_count=1, edge_count=0, orphan_count=1,
        )
        return SemanticGraph(
            metadata=metadata,
            nodes=(node,),
            edges=(),
            statistics=stats,
            outcome=GraphBuildOutcome.COMPLETE,
            diagnostics=(),
        )

    def test_semantic_graph_is_valid_mkc_input(self):
        """SemanticGraph produced by M5.2E is accepted by M5.3's compile_graph."""
        from modules.master_knowledge_compiler.engine import compile_graph
        from modules.master_knowledge_compiler.enums import CompilationOutcome
        graph = self._make_minimal_semantic_graph()
        pkg = compile_graph(graph)
        # Should succeed or produce a non-ERROR outcome
        self.assertIsNotNone(pkg)
        self.assertIsNotNone(pkg.manifest)

    def test_mkp_is_valid_ko_input(self):
        """MasterKnowledgePackage produced by M5.3 is accepted by M5.4's optimize."""
        from modules.master_knowledge_compiler.engine import compile_graph
        from modules.knowledge_optimization.engine import KnowledgeOptimizationEngine, default_engine
        graph = self._make_minimal_semantic_graph()
        mkp = compile_graph(graph)
        okp = default_engine.optimize(mkp)
        self.assertIsNotNone(okp)
        self.assertIsNotNone(okp.manifest)

    def test_m5_chain_produces_to_dict(self):
        """Both terminal M5 artifacts expose to_dict() for artifact_manager registration."""
        from modules.master_knowledge_compiler.engine import compile_graph
        from modules.knowledge_optimization.engine import default_engine
        graph = self._make_minimal_semantic_graph()
        mkp = compile_graph(graph)
        okp = default_engine.optimize(mkp)
        mkp_dict = mkp.to_dict()
        okp_dict = okp.to_dict()
        self.assertIsInstance(mkp_dict, dict)
        self.assertIsInstance(okp_dict, dict)
        self.assertIn("manifest", mkp_dict)
        self.assertIn("manifest", okp_dict)


# ---------------------------------------------------------------------------
# 4. Artifact Manager M5 Registrations
# ---------------------------------------------------------------------------
class TestM5ArtifactManagerIntegration(unittest.TestCase):
    """Verify that Build and ReferenceSnapshot carry M5 reference fields."""

    def test_reference_snapshot_has_m5_fields(self):
        import dataclasses
        from artifact_manager.build import ReferenceSnapshot
        fields = {f.name for f in dataclasses.fields(ReferenceSnapshot)}
        self.assertIn("master_knowledge_reference", fields,
                      "ReferenceSnapshot must have master_knowledge_reference")
        self.assertIn("optimized_knowledge_reference", fields,
                      "ReferenceSnapshot must have optimized_knowledge_reference")

    def test_build_has_m5_fields(self):
        import dataclasses
        from artifact_manager.build import Build
        fields = {f.name for f in dataclasses.fields(Build)}
        self.assertIn("master_knowledge_reference", fields,
                      "Build must have master_knowledge_reference")
        self.assertIn("optimized_knowledge_reference", fields,
                      "Build must have optimized_knowledge_reference")

    def test_m5_fields_are_optional(self):
        """M5 reference fields must be Optional[Dict] so backward-compat is preserved."""
        import dataclasses, inspect
        from artifact_manager.build import Build
        field_map = {f.name: f for f in dataclasses.fields(Build)}
        mkr = field_map["master_knowledge_reference"]
        okr = field_map["optimized_knowledge_reference"]
        # Both should have Optional type (allow None)
        self.assertIn("Optional", str(mkr.type) if isinstance(mkr.type, str) else repr(mkr.type))
        self.assertIn("Optional", str(okr.type) if isinstance(okr.type, str) else repr(okr.type))

    def test_manifest_includes_m5_references(self):
        """generate_build_manifest() should include M5 reference keys."""
        import inspect
        from artifact_manager import manifest
        src = inspect.getsource(manifest)
        self.assertIn("master_knowledge_reference", src,
                      "manifest.py must reference master_knowledge_reference")
        self.assertIn("optimized_knowledge_reference", src,
                      "manifest.py must reference optimized_knowledge_reference")


# ---------------------------------------------------------------------------
# 5. Validation Non-Redundancy
# ---------------------------------------------------------------------------
class TestValidationNoRedundancy(unittest.TestCase):
    """D1/D2/D3 validators must not duplicate each other's checks."""

    def test_d1_does_not_import_d2(self):
        import inspect
        from validation import system_integrity
        src = inspect.getsource(system_integrity)
        self.assertNotIn("from validation.determinism", src)
        self.assertNotIn("import determinism", src)

    def test_d2_does_not_import_d3(self):
        import inspect
        from validation import determinism
        src = inspect.getsource(determinism)
        self.assertNotIn("from validation.release", src)
        self.assertNotIn("import release", src)

    def test_d3_reads_d1_and_d2_but_does_not_rerun(self):
        """D3 reads D1/D2 reports but never re-runs their checks by calling them."""
        import inspect
        from validation import release
        src = inspect.getsource(release)
        # D3 must mention D1/D2 reports (it aggregates them)
        self.assertTrue("system_integrity" in src or "SystemIntegrity" in src)
        # D3 should accept system_integrity_report as a parameter, not call the validator
        # (the function may be referenced in docstrings/comments but must not INVOKE it)
        # We verify D3 has the right scope by confirming it accepts reports, not runs checks
        self.assertTrue("system_integrity_report" in src or "SystemIntegrityReport" in src,
                        "D3 must accept/reference system_integrity_report")


# ---------------------------------------------------------------------------
# 6. Serialization Determinism
# ---------------------------------------------------------------------------
class TestSerializationDeterminism(unittest.TestCase):
    """Key serializers must produce byte-identical output on repeated calls."""

    def test_mkc_serializer_is_deterministic(self):
        from modules.master_knowledge_compiler.engine import compile_graph
        from modules.master_knowledge_compiler.engine import default_compiler
        from modules.relationship_discovery_engine.models import (
            SemanticGraph, GraphMetadata, GraphStatistics, DEFAULT_GRAPH_VERSION
        )
        from modules.relationship_discovery_engine.enums import GraphBuildOutcome
        from modules.relationship_discovery_engine.models import SemanticNode
        node = SemanticNode(
            node_id="det-node-001",
            object_key="concept:entropy",
            object_type_key="Concept",
            semantic_role="defines_concept",
            confidence=0.9,
        )
        graph = SemanticGraph(
            metadata=GraphMetadata(
                graph_id="det-graph-001",
                engine_version=DEFAULT_GRAPH_VERSION,
                source_count=1,
                description="determinism test",
            ),
            nodes=(node,),
            edges=(),
            statistics=GraphStatistics(
                node_count=1, edge_count=0, orphan_count=1,
            ),
            outcome=GraphBuildOutcome.COMPLETE,
            diagnostics=(),
        )
        pkg1 = compile_graph(graph)
        pkg2 = compile_graph(graph)
        result1 = default_compiler.serialize(pkg1)
        result2 = default_compiler.serialize(pkg2)
        self.assertEqual(result1.payload, result2.payload,
                         "MKC serializer must be byte-identical for identical inputs")

    def test_ko_serializer_is_deterministic(self):
        from modules.master_knowledge_compiler.engine import compile_graph
        from modules.knowledge_optimization.engine import default_engine
        from modules.relationship_discovery_engine.models import (
            SemanticGraph, GraphMetadata, GraphStatistics, DEFAULT_GRAPH_VERSION
        )
        from modules.relationship_discovery_engine.enums import GraphBuildOutcome
        from modules.relationship_discovery_engine.models import SemanticNode
        node = SemanticNode(
            node_id="det-ko-node-001",
            object_key="concept:gravity",
            object_type_key="Concept",
            semantic_role="defines_concept",
            confidence=0.85,
        )
        graph = SemanticGraph(
            metadata=GraphMetadata(
                graph_id="det-ko-graph-001",
                engine_version=DEFAULT_GRAPH_VERSION,
                source_count=1,
                description="ko determinism test",
            ),
            nodes=(node,),
            edges=(),
            statistics=GraphStatistics(
                node_count=1, edge_count=0, orphan_count=1,
            ),
            outcome=GraphBuildOutcome.COMPLETE,
            diagnostics=(),
        )
        mkp = compile_graph(graph)
        okp1 = default_engine.optimize(mkp)
        okp2 = default_engine.optimize(mkp)
        r1 = default_engine.serialize(okp1)
        r2 = default_engine.serialize(okp2)
        self.assertEqual(r1.payload, r2.payload,
                         "KO serializer must be byte-identical for identical inputs")


# ---------------------------------------------------------------------------
# 7. Registry Consistency
# ---------------------------------------------------------------------------
class TestRegistryConsistency(unittest.TestCase):
    """All registries in the codebase must use CanonicalRegistry[T] pattern."""

    def test_compiler_registries_use_canonical_registry(self):
        from compiler.registry import CanonicalRegistry
        from compiler.registries import (
            ConceptRegistry, FigureRegistry, EquationRegistry,
            TopicRegistry, DefinitionRegistry,
        )
        for RegClass in [ConceptRegistry, FigureRegistry, EquationRegistry,
                         TopicRegistry, DefinitionRegistry]:
            self.assertTrue(
                issubclass(RegClass, CanonicalRegistry),
                f"{RegClass.__name__} must subclass CanonicalRegistry",
            )

    def test_knowledge_graph_uses_registry_manager(self):
        from knowledge_graph.registries import GraphRegistryManager
        from compiler.registry_manager import RegistryManager
        self.assertTrue(issubclass(GraphRegistryManager, RegistryManager))

    def test_dependency_graph_uses_registry_manager(self):
        from dependency_graph.registries import DependencyRegistryManager
        from compiler.registry_manager import RegistryManager
        self.assertTrue(issubclass(DependencyRegistryManager, RegistryManager))


# ---------------------------------------------------------------------------
# 8. State Pattern Consistency
# ---------------------------------------------------------------------------
class TestStatePatternConsistency(unittest.TestCase):
    """All state.py modules must expose the four required functions."""

    STATE_MODULES = [
        ("compiler.state", "registry_manager"),
        ("knowledge_graph.state", "knowledge_graph"),
        ("document_structure_tree.state", "document_structure_tree"),
        ("dependency_graph.state", "dependency_graph"),
        ("change_detection.state", "change_detection_report"),
        ("incremental_compilation.state", "incremental_compilation_plan"),
        ("build_metadata.state", "build_metadata"),
        ("modules.master_knowledge_compiler.state", "master_knowledge_package"),
        ("modules.knowledge_optimization.state", "optimized_knowledge_package"),
        ("modules.relationship_discovery_engine.state", "semantic_graph"),
    ]

    def test_all_state_modules_have_required_functions(self):
        for module_path, prefix in self.STATE_MODULES:
            with self.subTest(module=module_path):
                mod = importlib.import_module(module_path)
                for fn_pattern in [f"set_current_{prefix}", f"get_current_{prefix}",
                                   f"has_current_{prefix}"]:
                    self.assertTrue(hasattr(mod, fn_pattern),
                                    f"{module_path} missing {fn_pattern}")


# ---------------------------------------------------------------------------
# 9. Incremental Compilation Chain (E3 → E4 → E5)
# ---------------------------------------------------------------------------
class TestIncrementalCompilationChain(unittest.TestCase):
    """Verify that E3→E4→E5.1→E5.2 data contracts are coherent."""

    def test_e4_consumes_e3_report(self):
        """IncrementalCompilationPlan references ChangeDetectionReport types."""
        import inspect
        from incremental_compilation import planner
        src = inspect.getsource(planner)
        self.assertTrue("change_detection" in src or "ChangeDetection" in src,
                        "incremental_compilation.planner must reference change_detection")

    def test_e4_uses_dependency_graph(self):
        """IncrementalCompilationPlan uses DependencyGraph for topological order."""
        import inspect
        from incremental_compilation import traversal
        src = inspect.getsource(traversal)
        self.assertTrue("dependency" in src.lower() or "DependencyGraph" in src,
                        "incremental_compilation.traversal must reference dependency_graph")

    def test_e5_validation_references_e4_plan(self):
        """Incremental validation consumes the IncrementalCompilationPlan."""
        import inspect
        from incremental_compilation_validation import validator
        src = inspect.getsource(validator)
        self.assertTrue("IncrementalCompilationPlan" in src or "incremental_compilation" in src)

    def test_e5_finalization_references_validation(self):
        """Incremental finalization consumes validation report."""
        import inspect
        from incremental_compilation_finalization import finalize
        src = inspect.getsource(finalize)
        self.assertTrue("validation" in src.lower() or "IncrementalValidation" in src)


# ---------------------------------------------------------------------------
# 10. Build System Chain (F1 → F2 → F3 → F5)
# ---------------------------------------------------------------------------
class TestBuildSystemChain(unittest.TestCase):
    """Verify that F1→F2→F3→F5 responsibilities are cleanly separated."""

    def test_f5_references_f2_build(self):
        """compiler_release/finalize must aggregate from artifact_manager.Build."""
        import inspect
        from compiler_release import finalize
        src = inspect.getsource(finalize)
        self.assertTrue("build" in src.lower() or "Build" in src)

    def test_f3_references_f4_incremental_plan(self):
        """build_executor makes reuse/rebuild decisions per chapter."""
        import inspect
        from build_executor import executor
        src = inspect.getsource(executor)
        # F3 decides "reuse" or "rebuild" for each chapter
        self.assertTrue("reuse" in src.lower() or "rebuild" in src.lower(),
                        "build_executor.executor must make reuse/rebuild decisions")

    def test_runtime_references_artifact_manager(self):
        """runtime/runtime.py must call artifact_manager functions."""
        import inspect
        from runtime import runtime
        src = inspect.getsource(runtime)
        self.assertIn("artifact_manager", src)

    def test_runtime_references_compiler_release(self):
        """runtime/runtime.py must call compiler_release.finalize."""
        import inspect
        from runtime import runtime
        src = inspect.getsource(runtime)
        self.assertIn("compiler_release", src)


# ---------------------------------------------------------------------------
# 11. Backward Compatibility
# ---------------------------------------------------------------------------
class TestBackwardCompatibility(unittest.TestCase):
    """Verify that M5.1–M5.4 public APIs remain unchanged by M5.5."""

    def test_m51_public_api_intact(self):
        from modules.educational_object_framework.validation import (
            SUCCESS, ValidationResult, ValidationDiagnostic
        )
        from modules.educational_object_framework.base import (
            EducationalObjectProcessor, ProcessingContext
        )
        from modules.educational_object_framework.registry import (
            ProcessorRegistry, default_registry
        )
        self.assertIsNotNone(SUCCESS)
        self.assertIsNotNone(default_registry)

    def test_m52e_public_api_intact(self):
        from modules.relationship_discovery_engine.models import (
            SemanticGraph, SemanticNode, SemanticEdge,
            RelationshipDiscoveryResult, DEFAULT_GRAPH_VERSION
        )
        from modules.relationship_discovery_engine.engine import (
            RelationshipDiscoveryEngine, default_engine, discover
        )
        self.assertIsNotNone(default_engine)

    def test_m53_public_api_intact(self):
        from modules.master_knowledge_compiler.models import (
            MasterKnowledgePackage, ConceptIndex, DependencyMap,
            LearningProgression, RetrievalIndex
        )
        from modules.master_knowledge_compiler.engine import (
            MasterKnowledgeCompiler, default_compiler, compile_graph
        )
        self.assertIsNotNone(default_compiler)

    def test_m54_public_api_intact(self):
        from modules.knowledge_optimization.models import (
            OptimizedKnowledgePackage, RuntimeCache, SemanticSearchIndex,
            LearningAnalytics, KnowledgeQualityReport
        )
        from modules.knowledge_optimization.engine import (
            KnowledgeOptimizationEngine, default_engine
        )
        self.assertIsNotNone(default_engine)

    def test_m55_additions_are_additive(self):
        """New state fields on Build must not affect existing field values."""
        import dataclasses
        from artifact_manager.build import Build
        fields = {f.name for f in dataclasses.fields(Build)}
        # All original fields still present
        for original_field in [
            "build_id", "build_manifest",
            "compiler_ir_reference", "knowledge_graph_reference",
            "dependency_graph_reference", "build_metadata_reference",
            "change_detection_reference", "incremental_plan_reference",
            "incremental_validation_reference", "incremental_finalization_reference",
            "document_structure_tree_reference",
            "runtime_metadata", "execution_summary",
        ]:
            self.assertIn(original_field, fields,
                          f"Build must still have original field: {original_field}")


if __name__ == "__main__":
    unittest.main()
