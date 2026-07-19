"""
tests/test_m54_knowledge_optimization.py — M5.4 unit tests.

Coverage: all 10 deliverables + backward compatibility + determinism.
"""
from __future__ import annotations

import json, sys, unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ── Prior-milestone imports (backward-compat guard) ──────────────────────
from modules.educational_object_framework.validation import SUCCESS
from modules.master_knowledge_compiler.models import (
    CompilerManifest, CompilerStatistics, CompilerVersion, ConceptEntry,
    ConceptIndex, ConceptStatistics, CrossReferenceEntry, CrossReferenceIndex,
    DependencyEdge, DependencyMap, DependencyStatistics, IndexEntry,
    LearningProgression, LearningStep, MasterKnowledgePackage,
    MetadataEntry, MetadataIndex, RetrievalIndex,
)
from modules.master_knowledge_compiler.enums import (
    CompilationOutcome, ConceptCategory, DependencyType, IndexType,
    PackageStatus, ProgressionStrategy,
)

# ── M5.4 imports ─────────────────────────────────────────────────────────
from modules.knowledge_optimization.enums import (
    CacheType, LinkType, OptimizationOutcome, OptimizationStatus,
    QualityIssueSeverity, QualityIssueType, SearchIndexType,
)
from modules.knowledge_optimization.models import (
    CacheEntry, ConceptAnalytics, CrossChapterLink, CrossChapterLinkIndex,
    KnowledgeQualityReport, LearningAnalytics, OptimizationManifest,
    OptimizationStatistics, OptimizedIndexEntry, OptimizedKnowledgePackage,
    OptimizedRetrievalIndex, QualityIssue, RuntimeCache, SearchEntry,
    SemanticSearchIndex,
)
from modules.knowledge_optimization.config import (
    DEFAULT_OPTIMIZER_VERSION, KnowledgeOptimizationConfig, default_config,
)
from modules.knowledge_optimization.exceptions import (
    KnowledgeOptimizationError, OptimizedPackageBuildError,
)
from modules.knowledge_optimization.package_validator import PackageValidator
from modules.knowledge_optimization.knowledge_optimizer import KnowledgeOptimizer
from modules.knowledge_optimization.cross_chapter_linker import CrossChapterLinker
from modules.knowledge_optimization.semantic_search_builder import SemanticSearchBuilder
from modules.knowledge_optimization.runtime_cache_builder import RuntimeCacheBuilder
from modules.knowledge_optimization.learning_analytics_builder import LearningAnalyticsBuilder
from modules.knowledge_optimization.quality_analyzer import KnowledgeQualityAnalyzer
from modules.knowledge_optimization.serializer import OptimizationSerializer
from modules.knowledge_optimization.engine import (
    KnowledgeOptimizationEngine, optimize, default_engine,
)
from modules.knowledge_optimization.validation import (
    validate_analytics, validate_optimized_package,
    validate_retrieval_index, validate_runtime_cache, validate_serialization,
)

# ── Test helpers ─────────────────────────────────────────────────────────

def _ce(nid, ok="obj", otk="concept", role="defines_concept",
        cat=ConceptCategory.CONCEPT, conf=0.85, pk="definition"):
    return ConceptEntry(
        node_id=nid, object_key=ok + "_" + nid, object_type_key=otk,
        semantic_role=role, category=cat, confidence=conf,
        pattern_key=pk, related_node_ids=(),
    )


def _make_concept_index(n=3) -> ConceptIndex:
    entries = tuple(_ce(f"n{i}", conf=0.8+i*0.01) for i in range(1, n+1))
    stats = ConceptStatistics(
        total_concepts=len(entries),
        by_category={"concept": len(entries)},
        by_semantic_role={"defines_concept": len(entries)},
        average_confidence=0.85, min_confidence=0.80, max_confidence=0.90,
    )
    return ConceptIndex(entries=entries, statistics=stats, outcome=CompilationOutcome.COMPLETE)


def _make_dep_map() -> DependencyMap:
    edge = DependencyEdge("n1", "n2", DependencyType.REQUIRES, 0.75)
    stats = DependencyStatistics(
        total_edges=1, total_concepts=3, max_depth=1,
        by_dependency_type={"requires": 1},
    )
    return DependencyMap(
        edges=(edge,),
        prerequisite_map={"n1": ("n2",)},
        topological_order=("n2", "n3", "n1"),
        statistics=stats, outcome=CompilationOutcome.COMPLETE,
    )


def _make_learning_progression() -> LearningProgression:
    steps = (
        LearningStep(0, "n2", "obj_n2", "states_prerequisite", "concept", (), 0.85),
        LearningStep(1, "n3", "obj_n3", "defines_concept",     "concept", (), 0.82),
        LearningStep(2, "n1", "obj_n1", "defines_concept",     "concept", ("n2",), 0.85),
    )
    return LearningProgression(
        steps=steps, strategy=ProgressionStrategy.TOPOLOGICAL,
        total_steps=3, outcome=CompilationOutcome.COMPLETE,
    )


def _make_retrieval_index() -> RetrievalIndex:
    return RetrievalIndex(
        by_semantic_role={"defines_concept": ("n1", "n2", "n3")},
        by_educational_role={"concept": ("n1", "n2", "n3")},
        by_taxonomy_key={"concept": ("n1", "n2", "n3")},
        by_concept_category={"concept": ("n1", "n2", "n3")},
        by_pattern_key={"definition": ("n1", "n2", "n3")},
        prerequisite_lookup={"n1": ("n2",)},
        relationship_lookup={"n1": ("n2",), "n2": ("n1",)},
        entries=(IndexEntry("defines_concept", ("n1",), IndexType.SEMANTIC_ROLE, 1),),
        outcome=CompilationOutcome.COMPLETE,
    )


def _make_metadata_index() -> MetadataIndex:
    return MetadataIndex(
        taxonomy_metadata={"total_object_types": 1},
        semantic_metadata={"total_nodes": 3},
        compiler_metadata={"compiler_version": "1.0.0"},
        version_metadata={"m5_3": "1.0.0"},
        entries=(MetadataEntry("total_nodes", 3, "semantic"),),
        outcome=CompilationOutcome.COMPLETE,
    )


def _make_xref_index() -> CrossReferenceIndex:
    entries = tuple(
        CrossReferenceEntry(
            node_id=f"n{i}", object_key=f"obj_n{i}",
            examples=(), figures=(), experiments=(),
            procedures=(), assessments=(), tables=(), related=(),
        )
        for i in range(1, 4)
    )
    return CrossReferenceIndex(entries=entries, total_references=0, outcome=CompilationOutcome.COMPLETE)


def _make_statistics() -> CompilerStatistics:
    return CompilerStatistics(
        total_nodes_compiled=3, total_edges_compiled=1,
        total_concepts=3, total_dependencies=1, total_learning_steps=3,
        total_index_entries=1, total_cross_references=0, total_metadata_entries=1,
        compilation_outcome=CompilationOutcome.COMPLETE,
        compiler_version="1.0.0", package_version="1.0.0",
        graph_node_count=3, graph_edge_count=1,
    )


def _make_manifest() -> CompilerManifest:
    return CompilerManifest(
        package_id="test-pkg-001", graph_id="test-graph-001",
        graph_engine_version="1.0.0", graph_node_count=3, graph_edge_count=1,
        compiler_version=CompilerVersion("1.0.0", "1.0.0"),
        diagnostics=(), status=PackageStatus.SEALED,
    )


def _make_package() -> MasterKnowledgePackage:
    return MasterKnowledgePackage(
        manifest=_make_manifest(),
        concept_index=_make_concept_index(),
        dependency_map=_make_dep_map(),
        learning_progression=_make_learning_progression(),
        retrieval_index=_make_retrieval_index(),
        metadata_index=_make_metadata_index(),
        cross_reference_index=_make_xref_index(),
        statistics=_make_statistics(),
        outcome=CompilationOutcome.COMPLETE,
    )


# ===========================================================================
# Enum tests
# ===========================================================================
class TestEnums(unittest.TestCase):

    def test_optimization_outcome_is_str(self):
        for o in OptimizationOutcome:
            self.assertIsInstance(o.value, str)

    def test_link_type_values(self):
        expected = {"related_concept","prerequisite","successor","reinforcing",
                    "contrasting","cross_chapter","cross_book","glossary"}
        self.assertEqual(expected, {lt.value for lt in LinkType})

    def test_quality_issue_severity_order(self):
        sevs = [s.value for s in QualityIssueSeverity]
        self.assertIn("critical", sevs)
        self.assertIn("info", sevs)


# ===========================================================================
# Config tests
# ===========================================================================
class TestConfig(unittest.TestCase):

    def test_default_valid(self):
        cfg = KnowledgeOptimizationConfig()
        self.assertEqual(cfg.optimizer_version, DEFAULT_OPTIMIZER_VERSION)

    def test_invalid_confidence_raises(self):
        with self.assertRaises(ValueError):
            KnowledgeOptimizationConfig(min_confidence_threshold=1.5)

    def test_invalid_hops_raises(self):
        with self.assertRaises(ValueError):
            KnowledgeOptimizationConfig(cross_link_max_hops=0)

    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            default_config.optimizer_version = "2.0.0"  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        json.dumps(default_config.to_dict())


# ===========================================================================
# Model tests
# ===========================================================================
class TestCrossChapterLink(unittest.TestCase):

    def test_valid(self):
        l = CrossChapterLink("n1","n2", LinkType.PREREQUISITE, 0.8)
        self.assertEqual(l.source_node_id, "n1")

    def test_empty_source_raises(self):
        with self.assertRaises(KnowledgeOptimizationError):
            CrossChapterLink("", "n2", LinkType.PREREQUISITE, 0.8)

    def test_bad_confidence_raises(self):
        with self.assertRaises(KnowledgeOptimizationError):
            CrossChapterLink("n1", "n2", LinkType.PREREQUISITE, 1.5)

    def test_immutable(self):
        l = CrossChapterLink("n1","n2", LinkType.PREREQUISITE, 0.8)
        with self.assertRaises(FrozenInstanceError):
            l.confidence = 0.0  # type: ignore[misc]

    def test_to_dict(self):
        json.dumps(CrossChapterLink("n1","n2", LinkType.RELATED_CONCEPT, 0.75).to_dict())


class TestOptimizedKnowledgePackage(unittest.TestCase):

    def _build(self) -> OptimizedKnowledgePackage:
        return KnowledgeOptimizationEngine().optimize(_make_package())

    def test_is_complete(self):
        pkg = self._build()
        self.assertIn(pkg.outcome, (OptimizationOutcome.COMPLETE, OptimizationOutcome.PARTIAL))

    def test_is_sealed(self):
        pkg = self._build()
        self.assertTrue(pkg.is_sealed())

    def test_immutable(self):
        pkg = self._build()
        with self.assertRaises(FrozenInstanceError):
            pkg.outcome = OptimizationOutcome.FAILED  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        pkg = self._build()
        json.dumps(pkg.to_dict())

    def test_to_dict_deterministic(self):
        pkg = self._build()
        self.assertEqual(pkg.to_dict(), pkg.to_dict())


# ===========================================================================
# PackageValidator tests
# ===========================================================================
class TestPackageValidator(unittest.TestCase):

    def setUp(self):
        self.v = PackageValidator()

    def test_valid_package_passes(self):
        vr = self.v.validate(_make_package())
        self.assertFalse(vr.has_errors)

    def test_missing_manifest_fails(self):
        class Bad:
            manifest = None
            outcome = CompilationOutcome.COMPLETE
            concept_index = _make_concept_index()
            def to_dict(self): return {}
        vr = self.v.validate(Bad())
        self.assertTrue(vr.has_errors)

    def test_empty_package_id_fails(self):
        class BadManifest:
            package_id = ""
            graph_id   = "g1"
        class BadPkg:
            manifest = BadManifest()
            outcome  = CompilationOutcome.COMPLETE
            concept_index = _make_concept_index()
            def to_dict(self): return {}
        vr = self.v.validate(BadPkg())
        self.assertTrue(vr.has_errors)


# ===========================================================================
# KnowledgeOptimizer tests
# ===========================================================================
class TestKnowledgeOptimizer(unittest.TestCase):

    def setUp(self):
        self.opt = KnowledgeOptimizer()

    def test_builds_retrieval_index(self):
        ri = self.opt.optimize(_make_package())
        self.assertIsInstance(ri, OptimizedRetrievalIndex)
        self.assertGreater(len(ri.entries), 0)

    def test_entries_ordered_by_key(self):
        ri = self.opt.optimize(_make_package())
        keys = [e.key for e in ri.entries]
        self.assertEqual(keys, sorted(keys))

    def test_by_semantic_role_populated(self):
        ri = self.opt.optimize(_make_package())
        self.assertGreater(len(ri.by_semantic_role), 0)

    def test_empty_package_produces_empty_index(self):
        class Empty:
            concept_index = ConceptIndex(
                entries=(), outcome=CompilationOutcome.EMPTY,
                statistics=ConceptStatistics(0,{},{},0.0,0.0,0.0)
            )
            dependency_map = None
        ri = self.opt.optimize(Empty())
        self.assertEqual(ri.outcome, OptimizationOutcome.EMPTY)

    def test_prerequisite_chains_built(self):
        ri = self.opt.optimize(_make_package())
        self.assertIsInstance(ri.prerequisite_chains, dict)

    def test_to_dict_json_serializable(self):
        ri = self.opt.optimize(_make_package())
        json.dumps(ri.to_dict())


# ===========================================================================
# CrossChapterLinker tests
# ===========================================================================
class TestCrossChapterLinker(unittest.TestCase):

    def setUp(self):
        self.linker = CrossChapterLinker()

    def test_builds_links(self):
        idx = self.linker.build(_make_package())
        self.assertIsInstance(idx, CrossChapterLinkIndex)

    def test_prerequisite_links_generated(self):
        idx = self.linker.build(_make_package())
        types = {lk.link_type for lk in idx.links}
        self.assertIn(LinkType.PREREQUISITE, types)

    def test_successor_links_generated(self):
        idx = self.linker.build(_make_package())
        types = {lk.link_type for lk in idx.links}
        self.assertIn(LinkType.SUCCESSOR, types)

    def test_links_ordered_deterministically(self):
        idx1 = self.linker.build(_make_package())
        idx2 = self.linker.build(_make_package())
        self.assertEqual(
            [(l.source_node_id, l.target_node_id, l.link_type.value) for l in idx1.links],
            [(l.source_node_id, l.target_node_id, l.link_type.value) for l in idx2.links],
        )

    def test_to_dict_json_serializable(self):
        json.dumps(self.linker.build(_make_package()).to_dict())


# ===========================================================================
# SemanticSearchBuilder tests
# ===========================================================================
class TestSemanticSearchBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = SemanticSearchBuilder()

    def test_builds_search_index(self):
        idx = self.builder.build(_make_package())
        self.assertIsInstance(idx, SemanticSearchIndex)

    def test_entries_have_search_keys(self):
        idx = self.builder.build(_make_package())
        for e in idx.entries:
            self.assertTrue(len(e.search_key) > 0)

    def test_search_rank_in_range(self):
        idx = self.builder.build(_make_package())
        for e in idx.entries:
            self.assertGreaterEqual(e.search_rank, 0.0)
            self.assertLessEqual(e.search_rank, 1.0)

    def test_key_to_node_ids_populated(self):
        idx = self.builder.build(_make_package())
        self.assertGreater(len(idx.key_to_node_ids), 0)

    def test_disabled_returns_empty(self):
        cfg = KnowledgeOptimizationConfig(enable_semantic_search=False)
        builder = SemanticSearchBuilder(config=cfg)
        idx = builder.build(_make_package())
        self.assertEqual(idx.outcome, OptimizationOutcome.EMPTY)

    def test_to_dict_json_serializable(self):
        json.dumps(self.builder.build(_make_package()).to_dict())


# ===========================================================================
# RuntimeCacheBuilder tests
# ===========================================================================
class TestRuntimeCacheBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = RuntimeCacheBuilder()

    def test_concept_lookup_populated(self):
        cache = self.builder.build(_make_package())
        self.assertGreater(len(cache.concept_lookup), 0)

    def test_learning_path_populated(self):
        cache = self.builder.build(_make_package())
        self.assertGreater(len(cache.learning_path), 0)

    def test_educational_objects_populated(self):
        cache = self.builder.build(_make_package())
        self.assertGreater(len(cache.educational_objects), 0)

    def test_dependency_traversal_built(self):
        cache = self.builder.build(_make_package())
        self.assertIsInstance(cache.dependency_traversal, dict)

    def test_cache_is_deterministic(self):
        c1 = self.builder.build(_make_package())
        c2 = self.builder.build(_make_package())
        self.assertEqual(dict(c1.concept_lookup), dict(c2.concept_lookup))

    def test_to_dict_json_serializable(self):
        json.dumps(self.builder.build(_make_package()).to_dict())


# ===========================================================================
# LearningAnalyticsBuilder tests
# ===========================================================================
class TestLearningAnalyticsBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = LearningAnalyticsBuilder()

    def test_builds_analytics(self):
        a = self.builder.build(_make_package())
        self.assertEqual(a.total_concepts_analyzed, 3)

    def test_graph_density_in_range(self):
        a = self.builder.build(_make_package())
        self.assertGreaterEqual(a.graph_density, 0.0)
        self.assertLessEqual(a.graph_density, 1.0)

    def test_orphan_ratio_in_range(self):
        a = self.builder.build(_make_package())
        self.assertGreaterEqual(a.orphan_ratio, 0.0)
        self.assertLessEqual(a.orphan_ratio, 1.0)

    def test_per_concept_count_correct(self):
        a = self.builder.build(_make_package())
        self.assertEqual(len(a.per_concept), a.total_concepts_analyzed)

    def test_importance_in_range(self):
        a = self.builder.build(_make_package())
        for ca in a.per_concept:
            self.assertGreaterEqual(ca.importance, 0.0)
            self.assertLessEqual(ca.importance, 1.0)

    def test_to_dict_json_serializable(self):
        json.dumps(self.builder.build(_make_package()).to_dict())

    def test_empty_package_returns_empty(self):
        class Empty:
            concept_index = ConceptIndex(
                entries=(), outcome=CompilationOutcome.EMPTY,
                statistics=ConceptStatistics(0,{},{},0.0,0.0,0.0)
            )
            dependency_map = None
            learning_progression = None
        a = self.builder.build(Empty())
        self.assertEqual(a.outcome, OptimizationOutcome.EMPTY)


# ===========================================================================
# KnowledgeQualityAnalyzer tests
# ===========================================================================
class TestKnowledgeQualityAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = KnowledgeQualityAnalyzer()

    def test_produces_quality_report(self):
        r = self.analyzer.analyze(_make_package())
        self.assertIsInstance(r, KnowledgeQualityReport)

    def test_quality_score_in_range(self):
        r = self.analyzer.analyze(_make_package())
        self.assertGreaterEqual(r.overall_quality_score, 0.0)
        self.assertLessEqual(r.overall_quality_score, 1.0)

    def test_isolated_concepts_detected(self):
        # Build a package with no dependency edges
        pkg = MasterKnowledgePackage(
            manifest=_make_manifest(),
            concept_index=_make_concept_index(),
            dependency_map=DependencyMap(
                edges=(), prerequisite_map={},
                topological_order=("n1","n2","n3"),
                statistics=DependencyStatistics(0,3,0,{},False),
                outcome=CompilationOutcome.EMPTY,
            ),
            learning_progression=_make_learning_progression(),
            retrieval_index=_make_retrieval_index(),
            metadata_index=_make_metadata_index(),
            cross_reference_index=_make_xref_index(),
            statistics=_make_statistics(),
            outcome=CompilationOutcome.COMPLETE,
        )
        r = self.analyzer.analyze(pkg)
        types = {i.issue_type for i in r.issues}
        self.assertIn(QualityIssueType.ISOLATED_CONCEPT, types)

    def test_to_dict_json_serializable(self):
        json.dumps(self.analyzer.analyze(_make_package()).to_dict())

    def test_cycle_detection_enabled(self):
        # Force a cycle: n1→n2, n2→n1
        from modules.master_knowledge_compiler.models import DependencyEdge
        e1 = DependencyEdge("n1","n2", DependencyType.REQUIRES, 0.7)
        e2 = DependencyEdge("n2","n1", DependencyType.REQUIRES, 0.7)
        pkg = MasterKnowledgePackage(
            manifest=_make_manifest(),
            concept_index=_make_concept_index(),
            dependency_map=DependencyMap(
                edges=(e1,e2), prerequisite_map={"n1":("n2",),"n2":("n1",)},
                topological_order=("n1","n2","n3"),
                statistics=DependencyStatistics(2,3,1,{"requires":2},has_cycles=True),
                outcome=CompilationOutcome.COMPLETE,
            ),
            learning_progression=_make_learning_progression(),
            retrieval_index=_make_retrieval_index(),
            metadata_index=_make_metadata_index(),
            cross_reference_index=_make_xref_index(),
            statistics=_make_statistics(),
            outcome=CompilationOutcome.COMPLETE,
        )
        r = self.analyzer.analyze(pkg)
        types = {i.issue_type for i in r.issues}
        self.assertIn(QualityIssueType.CIRCULAR_DEPENDENCY, types)


# ===========================================================================
# OptimizationSerializer tests
# ===========================================================================
class TestOptimizationSerializer(unittest.TestCase):

    def setUp(self):
        self.serializer = OptimizationSerializer()
        self.pkg = KnowledgeOptimizationEngine().optimize(_make_package())

    def test_produces_json(self):
        result = self.serializer.serialize(self.pkg)
        json.loads(result.payload)

    def test_byte_count_positive(self):
        result = self.serializer.serialize(self.pkg)
        self.assertGreater(result.byte_count, 0)

    def test_deterministic(self):
        j1 = self.serializer.to_json(self.pkg)
        j2 = self.serializer.to_json(self.pkg)
        self.assertEqual(j1, j2)

    def test_result_to_dict(self):
        result = self.serializer.serialize(self.pkg)
        json.dumps(result.to_dict())


# ===========================================================================
# KnowledgeOptimizationEngine (end-to-end) tests
# ===========================================================================
class TestKnowledgeOptimizationEngine(unittest.TestCase):

    def setUp(self):
        self.engine = KnowledgeOptimizationEngine()

    def test_produces_optimized_package(self):
        pkg = self.engine.optimize(_make_package())
        self.assertIsInstance(pkg, OptimizedKnowledgePackage)

    def test_package_is_sealed(self):
        pkg = self.engine.optimize(_make_package())
        self.assertTrue(pkg.is_sealed())

    def test_package_id_is_deterministic(self):
        p1 = self.engine.optimize(_make_package())
        p2 = self.engine.optimize(_make_package())
        self.assertEqual(p1.manifest.optimized_package_id, p2.manifest.optimized_package_id)

    def test_full_pipeline_json_serializable(self):
        pkg = self.engine.optimize(_make_package())
        json.dumps(pkg.to_dict())

    def test_source_package_id_recorded(self):
        pkg = self.engine.optimize(_make_package())
        self.assertEqual(pkg.source_package_id, "test-pkg-001")

    def test_convenience_optimize_function(self):
        pkg = optimize(_make_package())
        self.assertIsInstance(pkg, OptimizedKnowledgePackage)

    def test_serialization_produces_result(self):
        pkg = self.engine.optimize(_make_package())
        result = self.engine.serialize(pkg)
        json.loads(result.payload)

    def test_multi_concept_pipeline(self):
        pkg = MasterKnowledgePackage(
            manifest=_make_manifest(),
            concept_index=_make_concept_index(n=6),
            dependency_map=_make_dep_map(),
            learning_progression=_make_learning_progression(),
            retrieval_index=_make_retrieval_index(),
            metadata_index=_make_metadata_index(),
            cross_reference_index=_make_xref_index(),
            statistics=_make_statistics(),
            outcome=CompilationOutcome.COMPLETE,
        )
        opt = self.engine.optimize(pkg)
        self.assertGreater(opt.statistics.total_concepts_optimized, 0)

    def test_full_pipeline_deterministic(self):
        p1 = self.engine.optimize(_make_package())
        p2 = self.engine.optimize(_make_package())
        j1 = json.dumps(p1.to_dict(), sort_keys=True)
        j2 = json.dumps(p2.to_dict(), sort_keys=True)
        self.assertEqual(j1, j2)


# ===========================================================================
# Validation function tests
# ===========================================================================
class TestValidationFunctions(unittest.TestCase):

    def _opt(self):
        return KnowledgeOptimizationEngine().optimize(_make_package())

    def test_validate_optimized_package_passes(self):
        vr = validate_optimized_package(self._opt())
        self.assertFalse(vr.has_errors)

    def test_validate_retrieval_index_passes(self):
        ri = KnowledgeOptimizer().optimize(_make_package())
        vr = validate_retrieval_index(ri)
        self.assertFalse(vr.has_errors)

    def test_validate_runtime_cache_passes(self):
        cache = RuntimeCacheBuilder().build(_make_package())
        vr = validate_runtime_cache(cache)
        self.assertFalse(vr.has_errors)

    def test_validate_analytics_passes(self):
        a = LearningAnalyticsBuilder().build(_make_package())
        vr = validate_analytics(a)
        self.assertFalse(vr.has_errors)

    def test_validate_serialization_passes(self):
        pkg = self._opt()
        vr = validate_serialization(pkg)
        self.assertTrue(vr.is_success)


# ===========================================================================
# Backward compatibility guard
# ===========================================================================
class TestBackwardCompatibility(unittest.TestCase):

    def test_m51_importable(self):
        from modules.educational_object_framework import (
            ValidationResult, ValidationDiagnostic,
        )

    def test_m52a_importable(self):
        from modules.educational_taxonomy import default_taxonomy

    def test_m52b_importable(self):
        from modules.subject_profile_framework import SubjectProfile

    def test_m52c_importable(self):
        from modules.structural_understanding_engine import StructuralUnderstandingEngine

    def test_m52d_importable(self):
        from modules.semantic_interpretation_engine import SemanticEnrichmentEngine

    def test_m52e_importable(self):
        from modules.relationship_discovery_engine import RelationshipDiscoveryEngine

    def test_m53_importable(self):
        from modules.master_knowledge_compiler import MasterKnowledgeCompiler

    def test_m54_does_not_modify_m53_package(self):
        pkg = _make_package()
        orig_id = pkg.manifest.package_id
        optimize(pkg)
        self.assertEqual(pkg.manifest.package_id, orig_id)

    def test_m54_node_ids_from_m53_preserved(self):
        pkg = _make_package()
        original_ids = {e.node_id for e in pkg.concept_index.entries}
        opt = optimize(pkg)
        cache_ids = set(opt.runtime_cache.concept_lookup.keys())
        self.assertTrue(cache_ids.issubset(original_ids))


# ===========================================================================
# Serialization determinism
# ===========================================================================
class TestSerializationDeterminism(unittest.TestCase):

    def test_identical_json_across_engine_instances(self):
        p1 = KnowledgeOptimizationEngine().optimize(_make_package())
        p2 = KnowledgeOptimizationEngine().optimize(_make_package())
        j1 = json.dumps(p1.to_dict(), sort_keys=True)
        j2 = json.dumps(p2.to_dict(), sort_keys=True)
        self.assertEqual(j1, j2)

    def test_package_id_stable_across_runs(self):
        p1 = KnowledgeOptimizationEngine().optimize(_make_package())
        p2 = KnowledgeOptimizationEngine().optimize(_make_package())
        self.assertEqual(
            p1.manifest.optimized_package_id,
            p2.manifest.optimized_package_id,
        )


if __name__ == "__main__":
    unittest.main()
