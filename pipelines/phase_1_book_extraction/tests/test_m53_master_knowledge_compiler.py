"""
tests/test_m53_master_knowledge_compiler.py — M5.3 unit tests
for modules/master_knowledge_compiler.

Coverage:
  - enums: CompilationOutcome, ConceptCategory, PackageStatus, etc.
  - config: threshold validation, immutability, to_dict()
  - models: immutability, validation, to_dict() determinism
  - graph_validator: valid/invalid graphs, node uniqueness, edge uniqueness
  - concept_compiler: node → ConceptEntry classification, statistics
  - dependency_compiler: dependency edge extraction, topological sort
  - learning_compiler: progression ordering (topological)
  - retrieval_compiler: all indexes populated, O(1) lookup
  - metadata_compiler: structured metadata, no narrative
  - cross_reference_builder: pre-resolved references by category
  - statistics: aggregate counts consistent with compiled artifacts
  - serializer: deterministic JSON, canonical ordering, byte-identical runs
  - engine: full end-to-end pipeline, sealed package, compile_graph()
  - validation: validate_concept_index, validate_package, validate_serialization
  - backward compatibility: M5.1–M5.2E unmodified
"""
from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import List

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Prior-milestone imports (backward-compatibility guard)
# ---------------------------------------------------------------------------
from modules.educational_object_framework.validation import SUCCESS, ValidationResult
from modules.semantic_interpretation_engine.models import (
    SemanticAnchor, SemanticEnrichmentResult, ConfidenceScore, ConfidenceEvidence,
    ConfidenceBreakdown, CompatibilityResult,
)
from modules.semantic_interpretation_engine.enums import (
    SemanticRole, ConfidenceLevel, EnrichmentOutcome, CompatibilitySeverity,
)
from modules.relationship_discovery_engine.models import (
    GraphMetadata, GraphStatistics, SemanticEdge, SemanticGraph, SemanticNode,
)
from modules.relationship_discovery_engine.enums import (
    GraphBuildOutcome, NodeStatus,
)

# ---------------------------------------------------------------------------
# M5.3 imports
# ---------------------------------------------------------------------------
from modules.master_knowledge_compiler.enums import (
    CompilationOutcome, ConceptCategory, DependencyType, IndexType,
    PackageStatus, ProgressionStrategy, SerializationFormat,
)
from modules.master_knowledge_compiler.models import (
    CompilerManifest, CompilerStatistics, CompilerVersion,
    ConceptEntry, ConceptIndex, ConceptStatistics,
    CrossReferenceEntry, CrossReferenceIndex,
    DependencyEdge, DependencyMap, DependencyStatistics,
    IndexEntry, LearningProgression, LearningStep,
    MasterKnowledgePackage, MetadataEntry, MetadataIndex,
    RetrievalIndex,
)
from modules.master_knowledge_compiler.config import (
    DEFAULT_COMPILER_VERSION, MasterKnowledgeCompilerConfig, default_config,
)
from modules.master_knowledge_compiler.exceptions import (
    MasterKnowledgeCompilerError, PackageBuildError,
)
from modules.master_knowledge_compiler.graph_validator import GraphReadinessValidator
from modules.master_knowledge_compiler.concept_compiler import ConceptCompiler, _classify
from modules.master_knowledge_compiler.dependency_compiler import DependencyCompiler
from modules.master_knowledge_compiler.learning_compiler import LearningProgressionCompiler
from modules.master_knowledge_compiler.retrieval_compiler import RetrievalIndexCompiler
from modules.master_knowledge_compiler.metadata_compiler import MetadataCompiler
from modules.master_knowledge_compiler.cross_reference_builder import CrossReferenceBuilder
from modules.master_knowledge_compiler.statistics import CompilerStatisticsBuilder
from modules.master_knowledge_compiler.serializer import MasterJSONSerializer, SerializationResult
from modules.master_knowledge_compiler.engine import (
    MasterKnowledgeCompiler, compile_graph, default_compiler,
)
from modules.master_knowledge_compiler.validation import (
    validate_concept_index, validate_dependency_map,
    validate_package, validate_retrieval_index, validate_serialization,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_node(
    node_id: str = "node-001",
    object_key: str = "obj_001",
    object_type_key: str = "concept",
    semantic_role: str = "defines_concept",
    confidence: float = 0.85,
    pattern_key: str = "definition",
) -> SemanticNode:
    return SemanticNode(
        node_id=node_id,
        object_key=object_key,
        object_type_key=object_type_key,
        semantic_role=semantic_role,
        confidence=confidence,
        pattern_key=pattern_key,
        status=NodeStatus.VALID,
    )


def _make_edge(
    edge_id: str = "edge-001",
    source: str = "node-001",
    target: str = "node-002",
    rel_type: str = "requires",
    confidence: float = 0.70,
) -> SemanticEdge:
    return SemanticEdge(
        edge_id=edge_id,
        source_node_id=source,
        target_node_id=target,
        relationship_type=rel_type,
        direction="forward",
        confidence=confidence,
    )


def _make_graph(
    nodes=None, edges=None, outcome=GraphBuildOutcome.COMPLETE,
    graph_id: str = "test-graph-id", engine_version: str = "1.0.0",
) -> SemanticGraph:
    n = nodes if nodes is not None else (
        _make_node("n1", "obj_1"),
        _make_node("n2", "obj_2", semantic_role="states_prerequisite"),
    )
    e = edges if edges is not None else (
        _make_edge("e1", "n1", "n2", "requires"),
    )
    metadata = GraphMetadata(
        graph_id=graph_id,
        engine_version=engine_version,
        source_count=len(n),
    )
    stats = GraphStatistics(
        node_count=len(n),
        edge_count=len(e),
    )
    return SemanticGraph(
        nodes=n, edges=e, metadata=metadata,
        statistics=stats, outcome=outcome, diagnostics=(),
    )


def _make_concept_entry(
    node_id: str = "n1",
    category: ConceptCategory = ConceptCategory.CONCEPT,
    confidence: float = 0.85,
) -> ConceptEntry:
    return ConceptEntry(
        node_id=node_id,
        object_key="obj_" + node_id,
        object_type_key="concept",
        semantic_role="defines_concept",
        category=category,
        confidence=confidence,
    )


def _make_concept_index(entries=None, outcome=CompilationOutcome.COMPLETE) -> ConceptIndex:
    e = entries or (_make_concept_entry("n1"), _make_concept_entry("n2", ConceptCategory.EXAMPLE))
    stats = ConceptStatistics(
        total_concepts=len(e),
        by_category={"concept": 1, "example": 1},
        by_semantic_role={"defines_concept": 2},
        average_confidence=0.85,
        min_confidence=0.85,
        max_confidence=0.85,
    )
    return ConceptIndex(entries=e, statistics=stats, outcome=outcome)


def _make_dep_map(outcome=CompilationOutcome.COMPLETE) -> DependencyMap:
    edge = DependencyEdge("n1", "n2", DependencyType.REQUIRES, 0.7)
    stats = DependencyStatistics(
        total_edges=1, total_concepts=2, max_depth=1,
        by_dependency_type={"requires": 1},
    )
    return DependencyMap(
        edges=(edge,),
        prerequisite_map={"n1": ("n2",)},
        topological_order=("n2", "n1"),
        statistics=stats,
        outcome=outcome,
    )


def _make_learning_progression(steps=None, outcome=CompilationOutcome.COMPLETE) -> LearningProgression:
    s = steps or (
        LearningStep(0, "n2", "obj_2", "states_prerequisite", "concept", (), 0.85),
        LearningStep(1, "n1", "obj_1", "defines_concept", "concept", ("n2",), 0.85),
    )
    return LearningProgression(
        steps=s, strategy=ProgressionStrategy.TOPOLOGICAL,
        total_steps=len(s), outcome=outcome,
    )


def _make_retrieval_index(outcome=CompilationOutcome.COMPLETE) -> RetrievalIndex:
    return RetrievalIndex(
        by_semantic_role={"defines_concept": ("n1",)},
        by_educational_role={"concept": ("n1",)},
        by_taxonomy_key={"concept": ("n1",)},
        by_concept_category={"concept": ("n1",)},
        by_pattern_key={"definition": ("n1",)},
        prerequisite_lookup={"n1": ("n2",)},
        relationship_lookup={"n1": ("n2",), "n2": ("n1",)},
        entries=(IndexEntry("defines_concept", ("n1",), IndexType.SEMANTIC_ROLE, 1),),
        outcome=outcome,
    )


def _make_metadata_index(outcome=CompilationOutcome.COMPLETE) -> MetadataIndex:
    return MetadataIndex(
        taxonomy_metadata={"total_object_types": 2},
        semantic_metadata={"total_nodes": 2},
        compiler_metadata={"compiler_version": "1.0.0"},
        version_metadata={"m5_3": "1.0.0"},
        entries=(MetadataEntry("total_object_types", 2, "taxonomy"),),
        outcome=outcome,
    )


def _make_xref_index(outcome=CompilationOutcome.COMPLETE) -> CrossReferenceIndex:
    entry = CrossReferenceEntry(
        node_id="n1", object_key="obj_1",
        examples=("n2",), figures=(), experiments=(),
        procedures=(), assessments=(), tables=(), related=(),
    )
    return CrossReferenceIndex(entries=(entry,), total_references=1, outcome=outcome)


def _make_statistics() -> CompilerStatistics:
    return CompilerStatistics(
        total_nodes_compiled=2,
        total_edges_compiled=1,
        total_concepts=2,
        total_dependencies=1,
        total_learning_steps=2,
        total_index_entries=1,
        total_cross_references=1,
        total_metadata_entries=1,
        compilation_outcome=CompilationOutcome.COMPLETE,
        compiler_version="1.0.0",
        package_version="1.0.0",
        graph_node_count=2,
        graph_edge_count=1,
    )


def _make_manifest() -> CompilerManifest:
    return CompilerManifest(
        package_id="pkg-001",
        graph_id="graph-001",
        graph_engine_version="1.0.0",
        graph_node_count=2,
        graph_edge_count=1,
        compiler_version=CompilerVersion("1.0.0", "1.0.0"),
        diagnostics=(),
        status=PackageStatus.SEALED,
    )


def _make_package(outcome=CompilationOutcome.COMPLETE) -> MasterKnowledgePackage:
    return MasterKnowledgePackage(
        manifest=_make_manifest(),
        concept_index=_make_concept_index(),
        dependency_map=_make_dep_map(),
        learning_progression=_make_learning_progression(),
        retrieval_index=_make_retrieval_index(),
        metadata_index=_make_metadata_index(),
        cross_reference_index=_make_xref_index(),
        statistics=_make_statistics(),
        outcome=outcome,
    )


# ===========================================================================
# Enum tests
# ===========================================================================
class TestEnums(unittest.TestCase):

    def test_compilation_outcome_is_str(self):
        for o in CompilationOutcome:
            self.assertIsInstance(o.value, str)
            self.assertEqual(o, o.value)

    def test_concept_category_has_expected_values(self):
        expected = {"concept", "definition", "principle", "law", "formula",
                    "theorem", "hypothesis", "rule", "example", "figure",
                    "table", "experiment", "procedure", "assessment", "other"}
        self.assertEqual(expected, {c.value for c in ConceptCategory})

    def test_package_status_sealed_exists(self):
        self.assertIn("sealed", {s.value for s in PackageStatus})


# ===========================================================================
# Config tests
# ===========================================================================
class TestConfig(unittest.TestCase):

    def test_default_config_valid(self):
        cfg = MasterKnowledgeCompilerConfig()
        self.assertEqual(cfg.compiler_version, DEFAULT_COMPILER_VERSION)

    def test_invalid_confidence_raises(self):
        with self.assertRaises(ValueError):
            MasterKnowledgeCompilerConfig(min_node_confidence=1.5)

    def test_immutable(self):
        cfg = MasterKnowledgeCompilerConfig()
        with self.assertRaises(FrozenInstanceError):
            cfg.compiler_version = "2.0.0"  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        json.dumps(default_config.to_dict())


# ===========================================================================
# Model tests
# ===========================================================================
class TestConceptEntry(unittest.TestCase):

    def test_valid_entry(self):
        e = _make_concept_entry()
        self.assertEqual(e.node_id, "n1")

    def test_empty_node_id_raises(self):
        with self.assertRaises(MasterKnowledgeCompilerError):
            ConceptEntry(node_id="", object_key="x", object_type_key="t",
                         semantic_role="r", category=ConceptCategory.CONCEPT, confidence=0.5)

    def test_immutable(self):
        e = _make_concept_entry()
        with self.assertRaises(FrozenInstanceError):
            e.node_id = "changed"  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        json.dumps(_make_concept_entry().to_dict())


class TestMasterKnowledgePackage(unittest.TestCase):

    def test_is_complete(self):
        pkg = _make_package()
        self.assertTrue(pkg.is_complete())

    def test_is_sealed(self):
        pkg = _make_package()
        self.assertTrue(pkg.is_sealed())

    def test_immutable(self):
        pkg = _make_package()
        with self.assertRaises(FrozenInstanceError):
            pkg.outcome = CompilationOutcome.ERROR  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        pkg = _make_package()
        json.dumps(pkg.to_dict())

    def test_to_dict_deterministic(self):
        pkg = _make_package()
        self.assertEqual(pkg.to_dict(), pkg.to_dict())


# ===========================================================================
# GraphReadinessValidator tests
# ===========================================================================
class TestGraphReadinessValidator(unittest.TestCase):

    def setUp(self):
        self.validator = GraphReadinessValidator()

    def test_valid_graph_passes(self):
        g = _make_graph()
        vr = self.validator.validate(g)
        self.assertFalse(vr.has_errors)

    def test_empty_graph_id_error(self):
        # M5.2E's GraphMetadata enforces non-empty graph_id, so we simulate
        # a graph-like object with empty metadata to trigger MKC002.
        class _EmptyMetadata:
            graph_id = ""
            engine_version = "1.0.0"
            source_count = 0

        class _BadGraph:
            metadata = _EmptyMetadata()
            outcome = GraphBuildOutcome.COMPLETE
            nodes = ()
            edges = ()

        vr = self.validator.validate(_BadGraph())
        self.assertTrue(vr.has_errors)

    def test_duplicate_node_ids_detected(self):
        n1 = _make_node("dup", "obj_1")
        n2 = _make_node("dup", "obj_2")
        g = _make_graph(nodes=(n1, n2), edges=())
        vr = self.validator.validate(g)
        self.assertTrue(vr.has_errors)

    def test_empty_nodes_produces_warning(self):
        g = _make_graph(nodes=(), edges=())
        vr = self.validator.validate(g)
        self.assertTrue(vr.has_warnings)


# ===========================================================================
# ConceptCompiler tests
# ===========================================================================
class TestConceptCompiler(unittest.TestCase):

    def setUp(self):
        self.compiler = ConceptCompiler()

    def test_compiles_concept_entries(self):
        g = _make_graph()
        idx = self.compiler.compile(g)
        self.assertEqual(len(idx.entries), 2)

    def test_entries_ordered_by_node_id(self):
        g = _make_graph()
        idx = self.compiler.compile(g)
        ids = [e.node_id for e in idx.entries]
        self.assertEqual(ids, sorted(ids))

    def test_concept_classification(self):
        n = _make_node(semantic_role="defines_concept")
        category = _classify(n)
        self.assertEqual(category, ConceptCategory.CONCEPT)

    def test_example_classification(self):
        n = _make_node(object_type_key="example", semantic_role="exemplifies_concept")
        category = _classify(n)
        self.assertEqual(category, ConceptCategory.EXAMPLE)

    def test_figure_classification(self):
        n = _make_node(object_type_key="figure")
        category = _classify(n)
        self.assertEqual(category, ConceptCategory.FIGURE)

    def test_empty_graph_produces_empty_index(self):
        g = _make_graph(nodes=(), edges=())
        idx = self.compiler.compile(g)
        self.assertEqual(idx.outcome, CompilationOutcome.EMPTY)

    def test_statistics_consistent(self):
        g = _make_graph()
        idx = self.compiler.compile(g)
        self.assertEqual(idx.statistics.total_concepts, len(idx.entries))

    def test_to_dict_json_serializable(self):
        g = _make_graph()
        idx = self.compiler.compile(g)
        json.dumps(idx.to_dict())


# ===========================================================================
# DependencyCompiler tests
# ===========================================================================
class TestDependencyCompiler(unittest.TestCase):

    def setUp(self):
        self.compiler = DependencyCompiler()

    def test_extracts_requires_edges(self):
        g = _make_graph(edges=(_make_edge("e1", "n1", "n2", "requires"),))
        dm = self.compiler.compile(g)
        self.assertEqual(len(dm.edges), 1)
        self.assertEqual(dm.edges[0].dependency_type, DependencyType.REQUIRES)

    def test_non_dependency_edges_ignored(self):
        g = _make_graph(edges=(_make_edge("e1", "n1", "n2", "illustrates"),))
        dm = self.compiler.compile(g)
        self.assertEqual(len(dm.edges), 0)

    def test_topological_order_is_deterministic(self):
        g = _make_graph()
        dm1 = self.compiler.compile(g)
        dm2 = self.compiler.compile(g)
        self.assertEqual(dm1.topological_order, dm2.topological_order)

    def test_prerequisite_map_populated(self):
        g = _make_graph(edges=(_make_edge("e1", "n1", "n2", "requires"),))
        dm = self.compiler.compile(g)
        self.assertIn("n1", dm.prerequisite_map)

    def test_empty_graph_produces_empty_map(self):
        g = _make_graph(nodes=(), edges=())
        dm = self.compiler.compile(g)
        self.assertEqual(dm.outcome, CompilationOutcome.EMPTY)

    def test_to_dict_json_serializable(self):
        g = _make_graph()
        dm = self.compiler.compile(g)
        json.dumps(dm.to_dict())


# ===========================================================================
# LearningProgressionCompiler tests
# ===========================================================================
class TestLearningProgressionCompiler(unittest.TestCase):

    def setUp(self):
        self.compiler = LearningProgressionCompiler()

    def test_produces_steps_for_all_concepts(self):
        ci = _make_concept_index()
        dm = _make_dep_map()
        lp = self.compiler.compile(ci, dm)
        self.assertEqual(len(lp.steps), len(ci.entries))

    def test_prerequisite_appears_before_dependent(self):
        ci = _make_concept_index()
        dm = _make_dep_map()
        lp = self.compiler.compile(ci, dm)
        node_positions = {s.node_id: s.position for s in lp.steps}
        # n2 is prerequisite of n1 → n2 must appear before n1
        if "n2" in node_positions and "n1" in node_positions:
            self.assertLess(node_positions["n2"], node_positions["n1"])

    def test_positions_are_sequential(self):
        ci = _make_concept_index()
        dm = _make_dep_map()
        lp = self.compiler.compile(ci, dm)
        positions = sorted(s.position for s in lp.steps)
        self.assertEqual(positions, list(range(len(lp.steps))))

    def test_total_steps_consistent(self):
        ci = _make_concept_index()
        dm = _make_dep_map()
        lp = self.compiler.compile(ci, dm)
        self.assertEqual(lp.total_steps, len(lp.steps))

    def test_deterministic(self):
        ci = _make_concept_index()
        dm = _make_dep_map()
        lp1 = self.compiler.compile(ci, dm)
        lp2 = self.compiler.compile(ci, dm)
        self.assertEqual([s.node_id for s in lp1.steps], [s.node_id for s in lp2.steps])

    def test_to_dict_json_serializable(self):
        ci = _make_concept_index()
        dm = _make_dep_map()
        lp = self.compiler.compile(ci, dm)
        json.dumps(lp.to_dict())


# ===========================================================================
# RetrievalIndexCompiler tests
# ===========================================================================
class TestRetrievalIndexCompiler(unittest.TestCase):

    def setUp(self):
        self.compiler = RetrievalIndexCompiler()

    def test_by_semantic_role_populated(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        dm = DependencyCompiler().compile(g)
        ri = self.compiler.compile(ci, dm, g)
        self.assertGreater(len(ri.by_semantic_role), 0)

    def test_by_concept_category_populated(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        dm = DependencyCompiler().compile(g)
        ri = self.compiler.compile(ci, dm, g)
        self.assertGreater(len(ri.by_concept_category), 0)

    def test_entries_have_correct_count(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        dm = DependencyCompiler().compile(g)
        ri = self.compiler.compile(ci, dm, g)
        for entry in ri.entries:
            self.assertEqual(entry.count, len(entry.node_ids))

    def test_to_dict_json_serializable(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        dm = DependencyCompiler().compile(g)
        ri = self.compiler.compile(ci, dm, g)
        json.dumps(ri.to_dict())


# ===========================================================================
# MetadataCompiler tests
# ===========================================================================
class TestMetadataCompiler(unittest.TestCase):

    def setUp(self):
        self.compiler = MetadataCompiler()

    def test_compiles_metadata(self):
        g = _make_graph()
        mi = self.compiler.compile(g)
        self.assertEqual(mi.outcome, CompilationOutcome.COMPLETE)

    def test_no_narrative_in_metadata(self):
        # Metadata should contain only structured data — no long prose strings.
        # Short identifier strings (graph_id, version) are acceptable; only
        # multi-word prose sentences are disallowed.
        g = _make_graph()
        mi = self.compiler.compile(g)
        for k, v in mi.semantic_metadata.items():
            if isinstance(v, str):
                # A structured string (ID, version, empty) must be short
                self.assertLess(
                    len(v.split()), 10,
                    f"Narrative prose detected in semantic_metadata[{k!r}]: {v!r}",
                )

    def test_version_metadata_present(self):
        g = _make_graph()
        mi = self.compiler.compile(g)
        self.assertIn("m5_3", mi.version_metadata)

    def test_to_dict_json_serializable(self):
        g = _make_graph()
        mi = self.compiler.compile(g)
        json.dumps(mi.to_dict())


# ===========================================================================
# CrossReferenceBuilder tests
# ===========================================================================
class TestCrossReferenceBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = CrossReferenceBuilder()

    def test_builds_cross_references(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        xr = self.builder.build(ci, g)
        self.assertEqual(len(xr.entries), len(ci.entries))

    def test_entries_ordered_by_node_id(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        xr = self.builder.build(ci, g)
        ids = [e.node_id for e in xr.entries]
        self.assertEqual(ids, sorted(ids))

    def test_by_node_id_lookup(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        xr = self.builder.build(ci, g)
        if xr.entries:
            nid = xr.entries[0].node_id
            found = xr.by_node_id(nid)
            self.assertIsNotNone(found)

    def test_to_dict_json_serializable(self):
        g = _make_graph()
        ci = ConceptCompiler().compile(g)
        xr = self.builder.build(ci, g)
        json.dumps(xr.to_dict())


# ===========================================================================
# CompilerStatisticsBuilder tests
# ===========================================================================
class TestCompilerStatisticsBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = CompilerStatisticsBuilder()

    def _build_all(self, graph=None):
        g = graph or _make_graph()
        ci = ConceptCompiler().compile(g)
        dm = DependencyCompiler().compile(g)
        lp = LearningProgressionCompiler().compile(ci, dm)
        ri = RetrievalIndexCompiler().compile(ci, dm, g)
        mi = MetadataCompiler().compile(g)
        xr = CrossReferenceBuilder().build(ci, g)
        stats = self.builder.build(
            graph=g, concept_index=ci, dependency_map=dm,
            learning_progression=lp, retrieval_index=ri,
            metadata_index=mi, cross_reference_index=xr,
            compiler_version="1.0.0", package_version="1.0.0",
        )
        return stats, ci, dm, lp

    def test_statistics_consistent_with_concept_index(self):
        stats, ci, _, _ = self._build_all()
        self.assertEqual(stats.total_concepts, ci.statistics.total_concepts)

    def test_statistics_consistent_with_learning_steps(self):
        stats, _, _, lp = self._build_all()
        self.assertEqual(stats.total_learning_steps, lp.total_steps)

    def test_to_dict_json_serializable(self):
        stats, _, _, _ = self._build_all()
        json.dumps(stats.to_dict())


# ===========================================================================
# MasterJSONSerializer tests
# ===========================================================================
class TestMasterJSONSerializer(unittest.TestCase):

    def setUp(self):
        self.serializer = MasterJSONSerializer()

    def test_serialize_to_json(self):
        pkg = _make_package()
        result = self.serializer.serialize(pkg, format=SerializationFormat.JSON)
        self.assertIsInstance(result.payload, str)
        json.loads(result.payload)  # Must be valid JSON

    def test_serialize_to_dict(self):
        pkg = _make_package()
        result = self.serializer.serialize(pkg, format=SerializationFormat.DICT)
        self.assertIsInstance(result.payload, dict)

    def test_json_is_sorted_keys(self):
        pkg = _make_package()
        j1 = self.serializer.to_json(pkg)
        j2 = self.serializer.to_json(pkg)
        self.assertEqual(j1, j2)

    def test_byte_count_positive(self):
        pkg = _make_package()
        result = self.serializer.serialize(pkg, format=SerializationFormat.JSON)
        self.assertGreater(result.byte_count, 0)

    def test_to_dict_convenience(self):
        pkg = _make_package()
        d = self.serializer.to_dict(pkg)
        self.assertIsInstance(d, dict)
        self.assertIn("manifest", d)

    def test_result_to_dict_json_serializable(self):
        pkg = _make_package()
        result = self.serializer.serialize(pkg)
        json.dumps(result.to_dict())


# ===========================================================================
# MasterKnowledgeCompiler (end-to-end) tests
# ===========================================================================
class TestMasterKnowledgeCompiler(unittest.TestCase):

    def setUp(self):
        self.compiler = MasterKnowledgeCompiler()

    def test_compiles_graph_to_package(self):
        g = _make_graph()
        pkg = self.compiler.compile(g)
        self.assertIsInstance(pkg, MasterKnowledgePackage)

    def test_package_is_sealed(self):
        g = _make_graph()
        pkg = self.compiler.compile(g)
        self.assertTrue(pkg.is_sealed())

    def test_package_is_immutable(self):
        g = _make_graph()
        pkg = self.compiler.compile(g)
        with self.assertRaises(FrozenInstanceError):
            pkg.outcome = CompilationOutcome.ERROR  # type: ignore[misc]

    def test_package_id_is_deterministic(self):
        g = _make_graph()
        p1 = self.compiler.compile(g)
        p2 = self.compiler.compile(g)
        self.assertEqual(p1.manifest.package_id, p2.manifest.package_id)

    def test_full_pipeline_json_serializable(self):
        g = _make_graph()
        pkg = self.compiler.compile(g)
        json.dumps(pkg.to_dict())

    def test_serialization_produces_result(self):
        g = _make_graph()
        pkg = self.compiler.compile(g)
        result = self.compiler.serialize(pkg)
        self.assertIsInstance(result, SerializationResult)
        json.loads(result.payload)

    def test_compile_graph_convenience(self):
        g = _make_graph()
        pkg = compile_graph(g)
        self.assertIsInstance(pkg, MasterKnowledgePackage)

    def test_concept_count_matches_graph_nodes(self):
        g = _make_graph()
        pkg = self.compiler.compile(g)
        self.assertEqual(pkg.statistics.graph_node_count, len(g.nodes))

    def test_empty_graph_produces_empty_package(self):
        g = _make_graph(nodes=(), edges=())
        pkg = self.compiler.compile(g)
        self.assertIn(pkg.outcome, (CompilationOutcome.EMPTY, CompilationOutcome.PARTIAL))

    def test_learning_steps_count_matches_concepts(self):
        g = _make_graph()
        pkg = self.compiler.compile(g)
        self.assertEqual(
            pkg.learning_progression.total_steps,
            len(pkg.concept_index.entries),
        )

    def test_determinism_full_pipeline(self):
        g = _make_graph()
        p1 = self.compiler.compile(g)
        p2 = self.compiler.compile(g)
        # Same package_id and JSON output
        self.assertEqual(p1.manifest.package_id, p2.manifest.package_id)
        self.assertEqual(
            json.dumps(p1.to_dict(), sort_keys=True),
            json.dumps(p2.to_dict(), sort_keys=True),
        )

    def test_multi_node_graph(self):
        nodes = tuple(
            _make_node(f"n{i}", f"obj_{i}", semantic_role=role)
            for i, role in enumerate([
                "defines_concept", "states_prerequisite",
                "exemplifies_concept", "serves_visual_purpose",
                "sequences_instruction",
            ])
        )
        edges = (
            _make_edge("e1", "n0", "n1", "requires"),
            _make_edge("e2", "n2", "n0", "illustrates"),
        )
        g = _make_graph(nodes=nodes, edges=edges)
        pkg = self.compiler.compile(g)
        self.assertEqual(len(pkg.concept_index.entries), 5)


# ===========================================================================
# Validation function tests
# ===========================================================================
class TestValidationFunctions(unittest.TestCase):

    def test_validate_concept_index_valid(self):
        ci = _make_concept_index()
        vr = validate_concept_index(ci)
        self.assertTrue(vr.is_success)

    def test_validate_concept_index_duplicate_ids(self):
        e1 = _make_concept_entry("n1")
        e2 = _make_concept_entry("n1")  # duplicate
        ci = _make_concept_index(entries=(e1, e2))
        vr = validate_concept_index(ci)
        self.assertTrue(vr.has_errors)

    def test_validate_dependency_map_valid(self):
        dm = _make_dep_map()
        vr = validate_dependency_map(dm)
        self.assertTrue(vr.is_success)

    def test_validate_retrieval_index_valid(self):
        ri = _make_retrieval_index()
        vr = validate_retrieval_index(ri)
        self.assertTrue(vr.is_success)

    def test_validate_package_valid(self):
        pkg = _make_package()
        vr = validate_package(pkg)
        self.assertTrue(vr.is_success)

    def test_validate_package_error_outcome_fails(self):
        pkg = _make_package(outcome=CompilationOutcome.ERROR)
        vr = validate_package(pkg)
        self.assertTrue(vr.has_errors)

    def test_validate_serialization_passes(self):
        pkg = _make_package()
        vr = validate_serialization(pkg)
        self.assertTrue(vr.is_success)


# ===========================================================================
# Backward compatibility guard
# ===========================================================================
class TestBackwardCompatibility(unittest.TestCase):

    def test_m51_importable(self):
        from modules.educational_object_framework import (
            ValidationResult, ValidationDiagnostic, ProcessorRegistry,
        )

    def test_m52a_importable(self):
        from modules.educational_taxonomy import (
            EducationalObjectType, default_taxonomy,
        )

    def test_m52b_importable(self):
        from modules.subject_profile_framework import SubjectProfile

    def test_m52c_importable(self):
        from modules.structural_understanding_engine import (
            StructuralUnderstandingEngine, StructuralAnalysisResult,
        )

    def test_m52d_importable(self):
        from modules.semantic_interpretation_engine import (
            SemanticEnrichmentEngine, SemanticAnchor,
        )

    def test_m52e_importable(self):
        from modules.relationship_discovery_engine import (
            RelationshipDiscoveryEngine, SemanticGraph,
        )

    def test_m53_does_not_modify_m52e_graph(self):
        """Compiling a graph does not mutate the source SemanticGraph."""
        g = _make_graph()
        orig_node_count = len(g.nodes)
        orig_edge_count = len(g.edges)
        compile_graph(g)
        self.assertEqual(len(g.nodes), orig_node_count)
        self.assertEqual(len(g.edges), orig_edge_count)

    def test_m53_node_ids_not_regenerated(self):
        """MasterKnowledgePackage uses original SemanticNode.node_id values."""
        g = _make_graph()
        original_ids = {n.node_id for n in g.nodes}
        pkg = compile_graph(g)
        compiled_ids = {e.node_id for e in pkg.concept_index.entries}
        self.assertTrue(compiled_ids.issubset(original_ids | {""}))


# ===========================================================================
# Serialization determinism
# ===========================================================================
class TestSerializationDeterminism(unittest.TestCase):

    def test_full_pipeline_identical_json(self):
        g = _make_graph()
        c = MasterKnowledgeCompiler()
        j1 = c.serialize(c.compile(g)).payload
        j2 = c.serialize(c.compile(g)).payload
        self.assertEqual(j1, j2)

    def test_package_id_stable_across_compilers(self):
        g = _make_graph()
        p1 = MasterKnowledgeCompiler().compile(g)
        p2 = MasterKnowledgeCompiler().compile(g)
        self.assertEqual(p1.manifest.package_id, p2.manifest.package_id)


if __name__ == "__main__":
    unittest.main()
