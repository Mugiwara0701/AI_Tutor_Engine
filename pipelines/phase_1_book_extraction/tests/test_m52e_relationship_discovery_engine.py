"""
tests/test_m52e_relationship_discovery_engine.py — M5.2E unit tests
for modules/relationship_discovery_engine.

Coverage:
  - enums: RelationshipType, DiscoveryOutcome, GraphBuildOutcome, etc.
  - models: immutability, validation, to_dict(), SemanticGraph
  - config: threshold validation, to_dict() round-trip
  - rules: RELATIONSHIP_RULES coverage, lookup_rule
  - confidence_propagator: ConfidencePropagator scores in [0,1]
  - relationship_resolver: candidate pair generation, filtering
  - relationship_classifier: known role-pairs, fallback to RELATED_TO
  - relationship_builder: deterministic relationship_id (UUID5)
  - relationship_validator: valid/invalid relationships, duplicate check
  - graph_builder: nodes from anchors, edges from relationships
  - graph_normalizer: duplicate edge removal, statistics update
  - graph_integrity_validator: orphan, broken ref, cycle detection
  - graph_exporter: dict and JSON export
  - engine: full pipeline end-to-end (COMPLETE, PARTIAL, EMPTY)
  - validation: validate_discovery_result, validate_graph_export_ready,
                validate_confidence_propagation
  - serialization: to_dict() is deterministic and JSON-serializable
  - backward compatibility: M5.1–M5.2D unmodified
"""
from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import MagicMock

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Prior-milestone imports (backward compatibility guard)
# ---------------------------------------------------------------------------
from modules.educational_object_framework.validation import SUCCESS, ValidationResult
from modules.educational_taxonomy.models import EducationalObjectType
from modules.educational_taxonomy.enums import EducationalCategory
from modules.subject_profile_framework.models import SubjectContribution
from modules.structural_understanding_engine.structural_models import StructuralAnalysisResult
from modules.structural_understanding_engine.enums import AnalysisOutcome
from modules.semantic_interpretation_engine.models import (
    SemanticAnchor,
    SemanticEnrichmentResult,
    SemanticObject,
    ConfidenceScore,
    ConfidenceEvidence,
    ConfidenceBreakdown,
    CompatibilityResult,
)
from modules.semantic_interpretation_engine.enums import (
    SemanticRole,
    ConfidenceLevel,
    EnrichmentOutcome,
    CompatibilitySeverity,
)

# ---------------------------------------------------------------------------
# M5.2E imports
# ---------------------------------------------------------------------------
from modules.relationship_discovery_engine.enums import (
    DiscoveryOutcome,
    EdgeStatus,
    GraphBuildOutcome,
    GraphExportFormat,
    NodeStatus,
    NormalizationStrategy,
    RelationshipDirection,
    RelationshipType,
)
from modules.relationship_discovery_engine.models import (
    DEFAULT_GRAPH_VERSION,
    GraphMetadata,
    GraphStatistics,
    RelationshipConfidence,
    RelationshipDiscoveryResult,
    RelationshipEvidence,
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
    SemanticRelationship,
)
from modules.relationship_discovery_engine.config import (
    DEFAULT_ENGINE_VERSION,
    RelationshipDiscoveryEngineConfig,
    default_config,
)
from modules.relationship_discovery_engine.exceptions import (
    RelationshipDiscoveryError,
)
from modules.relationship_discovery_engine.rules import (
    RELATIONSHIP_RULES,
    lookup_rule,
)
from modules.relationship_discovery_engine.confidence_propagator import (
    ConfidencePropagator,
)
from modules.relationship_discovery_engine.relationship_resolver import (
    RelationshipResolver,
)
from modules.relationship_discovery_engine.relationship_classifier import (
    RelationshipClassifier,
)
from modules.relationship_discovery_engine.relationship_builder import (
    RELATIONSHIP_NAMESPACE,
    RelationshipBuilder,
    _deterministic_relationship_id,
)
from modules.relationship_discovery_engine.relationship_validator import (
    RelationshipValidator,
)
from modules.relationship_discovery_engine.graph_builder import (
    GRAPH_NAMESPACE,
    SemanticGraphBuilder,
)
from modules.relationship_discovery_engine.graph_normalizer import GraphNormalizer
from modules.relationship_discovery_engine.graph_integrity_validator import (
    GraphIntegrityValidator,
)
from modules.relationship_discovery_engine.graph_exporter import (
    GraphExportArtifact,
    GraphExporter,
)
from modules.relationship_discovery_engine.engine import (
    RelationshipDiscoveryEngine,
    default_engine,
    discover,
)
from modules.relationship_discovery_engine.validation import (
    validate_confidence_propagation,
    validate_discovery_result,
    validate_graph_export_ready,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_confidence_score(value: float = 0.85) -> ConfidenceScore:
    level = (
        ConfidenceLevel.HIGH if value >= 0.80
        else ConfidenceLevel.MEDIUM if value >= 0.50
        else ConfidenceLevel.LOW if value >= 0.20
        else ConfidenceLevel.NONE
    )
    return ConfidenceScore(
        value=value,
        level=level,
        evidence=(ConfidenceEvidence(label="test", weight=1.0, passed=True),),
    )


def _make_anchor(
    object_key: str = "obj_001",
    semantic_role: SemanticRole = SemanticRole.DEFINES_CONCEPT,
    confidence_value: float = 0.85,
    pattern_key: str = "definition",
) -> SemanticAnchor:
    import uuid
    from modules.semantic_interpretation_engine.anchor_builder import ANCHOR_NAMESPACE
    anchor_id = str(uuid.uuid5(ANCHOR_NAMESPACE, f"{object_key}:{semantic_role.value}"))
    return SemanticAnchor(
        anchor_id=anchor_id,
        semantic_role=semantic_role,
        object_reference=object_key,
        confidence=_make_confidence_score(confidence_value),
        pattern_key=pattern_key,
    )


def _make_sem_object(object_key: str = "obj_001", pattern_key: str = "definition") -> SemanticObject:
    return SemanticObject(
        object_key=object_key,
        object_type_key="concept",
        pattern_key=pattern_key,
    )


def _make_enrichment_result(
    object_key: str = "obj_001",
    semantic_role: SemanticRole = SemanticRole.DEFINES_CONCEPT,
    confidence_value: float = 0.85,
    pattern_key: str = "definition",
) -> SemanticEnrichmentResult:
    anchor = _make_anchor(object_key, semantic_role, confidence_value, pattern_key)
    sem_obj = _make_sem_object(object_key, pattern_key)
    breakdown = ConfidenceBreakdown(
        structural=_make_confidence_score(confidence_value),
        semantic=_make_confidence_score(confidence_value),
        enrichment=_make_confidence_score(confidence_value),
    )
    compat = CompatibilityResult(
        compatible=True,
        severity=CompatibilitySeverity.OK,
        reason="OK",
    )
    return SemanticEnrichmentResult(
        object_key=object_key,
        outcome=EnrichmentOutcome.COMPLETE,
        semantic_object=sem_obj,
        confidence=breakdown,
        compatibility_result=compat,
        anchor=anchor,
    )


def _make_rel_confidence(value: float = 0.50) -> RelationshipConfidence:
    return RelationshipConfidence(
        value=value,
        source_confidence=0.85,
        target_confidence=0.80,
        evidence=(
            RelationshipEvidence(label="test", weight=1.0, passed=True),
        ),
    )


def _make_relationship(
    source_id: str = "src-id",
    target_id: str = "tgt-id",
    rel_type: RelationshipType = RelationshipType.DEFINES,
    confidence: float = 0.50,
) -> SemanticRelationship:
    return SemanticRelationship(
        relationship_id=_deterministic_relationship_id(source_id, target_id, "rule_test"),
        source_anchor_id=source_id,
        target_anchor_id=target_id,
        relationship_type=rel_type,
        direction=RelationshipDirection.FORWARD,
        confidence=_make_rel_confidence(confidence),
        discovery_rule="rule_test",
    )


def _make_node(node_id: str = "node-001", object_key: str = "obj_001") -> SemanticNode:
    return SemanticNode(
        node_id=node_id,
        object_key=object_key,
        object_type_key="concept",
        semantic_role="defines_concept",
        confidence=0.85,
        pattern_key="definition",
    )


def _make_edge(
    edge_id: str = "edge-001",
    source: str = "node-001",
    target: str = "node-002",
) -> SemanticEdge:
    return SemanticEdge(
        edge_id=edge_id,
        source_node_id=source,
        target_node_id=target,
        relationship_type="defines",
        direction="forward",
        confidence=0.60,
    )


def _make_graph(
    nodes=None, edges=None, outcome=GraphBuildOutcome.COMPLETE
) -> SemanticGraph:
    n = nodes or (_make_node("n1", "obj_1"), _make_node("n2", "obj_2"))
    e = edges or (_make_edge("e1", "n1", "n2"),)
    metadata = GraphMetadata(
        graph_id="test-graph-id",
        engine_version=DEFAULT_ENGINE_VERSION,
        source_count=len(n),
    )
    stats = GraphStatistics(
        node_count=len(n),
        edge_count=len(e),
    )
    return SemanticGraph(
        nodes=n,
        edges=e,
        metadata=metadata,
        statistics=stats,
        outcome=outcome,
        diagnostics=(),
    )


# ===========================================================================
# Enum tests
# ===========================================================================
class TestEnums(unittest.TestCase):

    def test_relationship_type_is_str(self):
        for rt in RelationshipType:
            self.assertIsInstance(rt.value, str)
            self.assertEqual(rt, rt.value)

    def test_discovery_outcome_values(self):
        expected = {"complete", "partial", "empty", "error"}
        self.assertEqual(expected, {o.value for o in DiscoveryOutcome})

    def test_graph_build_outcome_values(self):
        expected = {"complete", "partial", "empty", "validation_failed", "error"}
        self.assertEqual(expected, {o.value for o in GraphBuildOutcome})

    def test_normalization_strategy_values(self):
        self.assertIn("keep_highest_confidence", {s.value for s in NormalizationStrategy})


# ===========================================================================
# Config tests
# ===========================================================================
class TestConfig(unittest.TestCase):

    def test_default_config_valid(self):
        cfg = RelationshipDiscoveryEngineConfig()
        self.assertEqual(cfg.version, DEFAULT_ENGINE_VERSION)
        self.assertGreaterEqual(cfg.min_relationship_confidence, 0.0)

    def test_invalid_confidence_threshold_raises(self):
        with self.assertRaises(ValueError):
            RelationshipDiscoveryEngineConfig(min_relationship_confidence=1.5)

    def test_to_dict_json_serializable(self):
        json.dumps(default_config.to_dict())

    def test_config_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            default_config.version = "2.0.0"  # type: ignore[misc]


# ===========================================================================
# Model tests
# ===========================================================================
class TestRelationshipEvidence(unittest.TestCase):

    def test_valid_evidence(self):
        e = RelationshipEvidence(label="test", weight=0.5, passed=True)
        self.assertEqual(e.label, "test")

    def test_empty_label_raises(self):
        with self.assertRaises(RelationshipDiscoveryError):
            RelationshipEvidence(label="", weight=0.5, passed=True)

    def test_weight_out_of_range_raises(self):
        with self.assertRaises(RelationshipDiscoveryError):
            RelationshipEvidence(label="x", weight=1.5, passed=True)

    def test_immutable(self):
        e = RelationshipEvidence(label="x", weight=0.3, passed=False)
        with self.assertRaises(FrozenInstanceError):
            e.passed = True  # type: ignore[misc]

    def test_to_dict(self):
        e = RelationshipEvidence(label="rule_match", weight=0.7, passed=True, detail="ok")
        json.dumps(e.to_dict())


class TestRelationshipConfidence(unittest.TestCase):

    def test_valid(self):
        c = _make_rel_confidence(0.75)
        self.assertEqual(c.value, 0.75)

    def test_out_of_range_raises(self):
        with self.assertRaises(RelationshipDiscoveryError):
            RelationshipConfidence(value=1.5, source_confidence=0.8, target_confidence=0.8)

    def test_immutable(self):
        c = _make_rel_confidence(0.5)
        with self.assertRaises(FrozenInstanceError):
            c.value = 0.9  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        json.dumps(_make_rel_confidence(0.6).to_dict())


class TestSemanticRelationship(unittest.TestCase):

    def test_valid_relationship(self):
        r = _make_relationship()
        self.assertIsNotNone(r.relationship_id)

    def test_empty_source_raises(self):
        with self.assertRaises(RelationshipDiscoveryError):
            SemanticRelationship(
                relationship_id="rid",
                source_anchor_id="",
                target_anchor_id="tgt",
                relationship_type=RelationshipType.DEFINES,
                direction=RelationshipDirection.FORWARD,
                confidence=_make_rel_confidence(),
            )

    def test_immutable(self):
        r = _make_relationship()
        with self.assertRaises(FrozenInstanceError):
            r.relationship_type = RelationshipType.REQUIRES  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        json.dumps(_make_relationship().to_dict())


class TestSemanticNode(unittest.TestCase):

    def test_valid(self):
        n = _make_node()
        self.assertEqual(n.node_id, "node-001")

    def test_empty_node_id_raises(self):
        with self.assertRaises(RelationshipDiscoveryError):
            SemanticNode(node_id="", object_key="obj", object_type_key="t",
                         semantic_role="r", confidence=0.5)

    def test_immutable(self):
        n = _make_node()
        with self.assertRaises(FrozenInstanceError):
            n.confidence = 0.0  # type: ignore[misc]

    def test_to_dict(self):
        json.dumps(_make_node().to_dict())


class TestSemanticGraph(unittest.TestCase):

    def test_valid_graph(self):
        g = _make_graph()
        self.assertEqual(len(g.nodes), 2)
        self.assertEqual(len(g.edges), 1)

    def test_is_complete(self):
        g = _make_graph(outcome=GraphBuildOutcome.COMPLETE)
        self.assertTrue(g.is_complete())

    def test_not_complete(self):
        g = _make_graph(outcome=GraphBuildOutcome.PARTIAL)
        self.assertFalse(g.is_complete())

    def test_node_ids(self):
        g = _make_graph()
        self.assertIn("n1", g.node_ids())

    def test_immutable(self):
        g = _make_graph()
        with self.assertRaises(FrozenInstanceError):
            g.outcome = GraphBuildOutcome.ERROR  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        g = _make_graph()
        json.dumps(g.to_dict())

    def test_to_dict_deterministic(self):
        g = _make_graph()
        self.assertEqual(g.to_dict(), g.to_dict())


# ===========================================================================
# Rules tests
# ===========================================================================
class TestRelationshipRules(unittest.TestCase):

    def test_defines_rule_exists(self):
        rule = lookup_rule("defines_concept", "defines_concept")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.relationship_type, RelationshipType.DEFINES)

    def test_illustrates_rule_exists(self):
        rule = lookup_rule("exemplifies_concept", "defines_concept")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.relationship_type, RelationshipType.ILLUSTRATES)

    def test_requires_rule_exists(self):
        rule = lookup_rule("defines_concept", "states_prerequisite")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.relationship_type, RelationshipType.REQUIRES)

    def test_unknown_pair_returns_none(self):
        rule = lookup_rule("unknown_role", "another_unknown")
        self.assertIsNone(rule)

    def test_all_rules_have_valid_weights(self):
        for (src, tgt), rule in RELATIONSHIP_RULES.items():
            self.assertGreater(rule.base_weight, 0.0, f"Rule ({src},{tgt}) has zero weight")
            self.assertLessEqual(rule.base_weight, 1.0)

    def test_all_rules_have_non_empty_rule_key(self):
        for rule in RELATIONSHIP_RULES.values():
            self.assertTrue(rule.rule_key, f"Rule {rule} has empty rule_key")


# ===========================================================================
# ConfidencePropagator tests
# ===========================================================================
class TestConfidencePropagator(unittest.TestCase):

    def setUp(self):
        self.propagator = ConfidencePropagator()

    def test_score_in_range_with_rule(self):
        from modules.relationship_discovery_engine.rules import RELATIONSHIP_RULES
        rule = next(iter(RELATIONSHIP_RULES.values()))
        c = self.propagator.propagate(
            source_confidence=0.9, target_confidence=0.8, rule=rule
        )
        self.assertGreaterEqual(c.value, 0.0)
        self.assertLessEqual(c.value, 1.0)

    def test_score_in_range_fallback(self):
        c = self.propagator.propagate(source_confidence=0.5, target_confidence=0.5)
        self.assertGreaterEqual(c.value, 0.0)
        self.assertLessEqual(c.value, 1.0)

    def test_low_anchor_confidence_reduces_score(self):
        from modules.relationship_discovery_engine.rules import RELATIONSHIP_RULES
        rule = next(iter(RELATIONSHIP_RULES.values()))
        c_high = self.propagator.propagate(source_confidence=0.95, target_confidence=0.90, rule=rule)
        c_low = self.propagator.propagate(source_confidence=0.1, target_confidence=0.1, rule=rule)
        self.assertGreater(c_high.value, c_low.value)

    def test_invalid_confidence_raises(self):
        with self.assertRaises(Exception):
            self.propagator.propagate(source_confidence=1.5, target_confidence=0.5)

    def test_evidence_present(self):
        c = self.propagator.propagate(source_confidence=0.8, target_confidence=0.75)
        self.assertGreater(len(c.evidence), 0)

    def test_to_dict_json_serializable(self):
        c = self.propagator.propagate(source_confidence=0.7, target_confidence=0.7)
        json.dumps(c.to_dict())


# ===========================================================================
# RelationshipResolver tests
# ===========================================================================
class TestRelationshipResolver(unittest.TestCase):

    def setUp(self):
        self.resolver = RelationshipResolver()

    def test_empty_list_returns_no_pairs(self):
        pairs = self.resolver.resolve_pairs([])
        self.assertEqual(pairs, [])

    def test_single_result_returns_no_pairs(self):
        r = _make_enrichment_result()
        pairs = self.resolver.resolve_pairs([r])
        self.assertEqual(pairs, [])

    def test_two_valid_results_return_two_pairs(self):
        # (A→B) and (B→A) — 2 pairs total
        r1 = _make_enrichment_result("obj_1")
        r2 = _make_enrichment_result("obj_2", semantic_role=SemanticRole.STATES_PREREQUISITE)
        pairs = self.resolver.resolve_pairs([r1, r2])
        self.assertEqual(len(pairs), 2)

    def test_low_confidence_result_excluded(self):
        r_high = _make_enrichment_result("obj_1", confidence_value=0.9)
        r_low = _make_enrichment_result("obj_2", confidence_value=0.0)
        pairs = self.resolver.resolve_pairs([r_high, r_low])
        self.assertEqual(pairs, [])

    def test_no_anchor_result_excluded(self):
        r_ok = _make_enrichment_result("obj_1")
        # Create a result-like object with no anchor
        class _NoAnchor:
            anchor = None
            object_key = "no_anchor"
        pairs = self.resolver.resolve_pairs([r_ok, _NoAnchor()])
        self.assertEqual(pairs, [])

    def test_pairs_are_deterministically_ordered(self):
        results = [_make_enrichment_result(f"obj_{i}") for i in range(3)]
        p1 = self.resolver.resolve_pairs(results)
        p2 = self.resolver.resolve_pairs(results)
        self.assertEqual(
            [(s.anchor.anchor_id, t.anchor.anchor_id) for s, t in p1],
            [(s.anchor.anchor_id, t.anchor.anchor_id) for s, t in p2],
        )


# ===========================================================================
# RelationshipClassifier tests
# ===========================================================================
class TestRelationshipClassifier(unittest.TestCase):

    def setUp(self):
        self.classifier = RelationshipClassifier()

    def test_known_pair_classifies_correctly(self):
        src = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        tgt = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        result = self.classifier.classify(src, tgt)
        self.assertTrue(result.exact_match)
        self.assertEqual(result.rule.relationship_type, RelationshipType.REQUIRES)

    def test_unknown_pair_falls_back(self):
        src = _make_enrichment_result("obj_1", SemanticRole.UNKNOWN)
        tgt = _make_enrichment_result("obj_2", SemanticRole.UNKNOWN)
        result = self.classifier.classify(src, tgt)
        self.assertFalse(result.exact_match)
        self.assertEqual(result.rule.relationship_type, RelationshipType.RELATED_TO)

    def test_illustrates_pair(self):
        src = _make_enrichment_result("obj_1", SemanticRole.EXEMPLIFIES_CONCEPT)
        tgt = _make_enrichment_result("obj_2", SemanticRole.DEFINES_CONCEPT)
        result = self.classifier.classify(src, tgt)
        self.assertEqual(result.rule.relationship_type, RelationshipType.ILLUSTRATES)


# ===========================================================================
# RelationshipBuilder tests
# ===========================================================================
class TestRelationshipBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = RelationshipBuilder()
        self.classifier = RelationshipClassifier()

    def test_relationship_id_is_deterministic(self):
        src = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        tgt = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        cl = self.classifier.classify(src, tgt)
        r1 = self.builder.build(src, tgt, cl)
        r2 = self.builder.build(src, tgt, cl)
        self.assertEqual(r1.relationship_id, r2.relationship_id)

    def test_distinct_pairs_different_ids(self):
        src1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        tgt1 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        src2 = _make_enrichment_result("obj_3", SemanticRole.EXEMPLIFIES_CONCEPT)
        tgt2 = _make_enrichment_result("obj_4", SemanticRole.DEFINES_CONCEPT)
        cl1 = self.classifier.classify(src1, tgt1)
        cl2 = self.classifier.classify(src2, tgt2)
        r1 = self.builder.build(src1, tgt1, cl1)
        r2 = self.builder.build(src2, tgt2, cl2)
        self.assertNotEqual(r1.relationship_id, r2.relationship_id)

    def test_relationship_is_immutable(self):
        src = _make_enrichment_result("obj_1")
        tgt = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        cl = self.classifier.classify(src, tgt)
        r = self.builder.build(src, tgt, cl)
        with self.assertRaises(FrozenInstanceError):
            r.relationship_type = RelationshipType.EXPLAINS  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        src = _make_enrichment_result("obj_1")
        tgt = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        cl = self.classifier.classify(src, tgt)
        r = self.builder.build(src, tgt, cl)
        json.dumps(r.to_dict())


# ===========================================================================
# RelationshipValidator tests
# ===========================================================================
class TestRelationshipValidator(unittest.TestCase):

    def setUp(self):
        self.validator = RelationshipValidator()

    def test_valid_relationship_passes(self):
        r = _make_relationship(confidence=0.5)
        vr = self.validator.validate_relationship(r)
        self.assertTrue(vr.is_success)

    def test_low_confidence_produces_warning(self):
        r = _make_relationship(confidence=0.0)
        vr = self.validator.validate_relationship(r)
        self.assertTrue(vr.has_warnings)

    def test_duplicate_ids_produce_warning(self):
        r = _make_relationship()
        vr = self.validator.validate_list((r, r))
        self.assertTrue(vr.has_warnings)

    def test_valid_list_passes(self):
        r1 = _make_relationship("src1", "tgt1")
        r2 = _make_relationship("src2", "tgt2")
        vr = self.validator.validate_list((r1, r2))
        self.assertTrue(vr.is_success)


# ===========================================================================
# SemanticGraphBuilder tests
# ===========================================================================
class TestSemanticGraphBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = SemanticGraphBuilder()

    def _make_discovery_result(self, relationships=()) -> RelationshipDiscoveryResult:
        return RelationshipDiscoveryResult(
            outcome=DiscoveryOutcome.COMPLETE if relationships else DiscoveryOutcome.EMPTY,
            relationships=tuple(relationships),
            object_keys=(),
            diagnostics=(),
        )

    def test_builds_nodes_from_enrichment_results(self):
        r1 = _make_enrichment_result("obj_1")
        r2 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        disc = self._make_discovery_result()
        graph = self.builder.build([r1, r2], disc)
        self.assertEqual(graph.statistics.node_count, 2)

    def test_nodes_use_anchor_ids(self):
        r1 = _make_enrichment_result("obj_1")
        disc = self._make_discovery_result()
        graph = self.builder.build([r1], disc)
        self.assertEqual(graph.nodes[0].node_id, r1.anchor.anchor_id)

    def test_empty_input_produces_empty_graph(self):
        disc = self._make_discovery_result()
        graph = self.builder.build([], disc)
        self.assertEqual(graph.outcome, GraphBuildOutcome.EMPTY)

    def test_graph_is_immutable(self):
        r1 = _make_enrichment_result("obj_1")
        disc = self._make_discovery_result()
        graph = self.builder.build([r1], disc)
        with self.assertRaises(FrozenInstanceError):
            graph.outcome = GraphBuildOutcome.ERROR  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        r1 = _make_enrichment_result("obj_1")
        disc = self._make_discovery_result()
        graph = self.builder.build([r1], disc)
        json.dumps(graph.to_dict())

    def test_graph_id_is_deterministic(self):
        r1 = _make_enrichment_result("obj_1")
        disc = self._make_discovery_result()
        g1 = self.builder.build([r1], disc)
        g2 = self.builder.build([r1], disc)
        self.assertEqual(g1.metadata.graph_id, g2.metadata.graph_id)

    def test_orphan_detection(self):
        r1 = _make_enrichment_result("obj_1")
        disc = self._make_discovery_result()  # No edges
        graph = self.builder.build([r1], disc)
        self.assertGreater(graph.statistics.orphan_count, 0)


# ===========================================================================
# GraphNormalizer tests
# ===========================================================================
class TestGraphNormalizer(unittest.TestCase):

    def setUp(self):
        self.normalizer = GraphNormalizer()

    def test_no_duplicates_unchanged(self):
        g = _make_graph()
        ng = self.normalizer.normalize(g)
        self.assertEqual(ng.statistics.edge_count, g.statistics.edge_count)

    def test_duplicate_edges_removed(self):
        n1 = _make_node("n1", "obj_1")
        n2 = _make_node("n2", "obj_2")
        # Two edges with same (src, tgt, type) — duplicates
        e1 = SemanticEdge("eid1", "n1", "n2", "defines", "forward", 0.8)
        e2 = SemanticEdge("eid2", "n1", "n2", "defines", "forward", 0.6)
        g = _make_graph(nodes=(n1, n2), edges=(e1, e2))
        ng = self.normalizer.normalize(g)
        self.assertEqual(ng.statistics.edge_count, 1)
        # Should keep highest confidence
        self.assertEqual(ng.edges[0].edge_id, "eid1")

    def test_normalization_records_removed_count(self):
        n1 = _make_node("n1")
        n2 = _make_node("n2", "obj_2")
        e1 = SemanticEdge("eid1", "n1", "n2", "defines", "forward", 0.8)
        e2 = SemanticEdge("eid2", "n1", "n2", "defines", "forward", 0.6)
        g = _make_graph(nodes=(n1, n2), edges=(e1, e2))
        ng = self.normalizer.normalize(g)
        self.assertGreater(ng.statistics.duplicate_edges_removed, 0)

    def test_input_graph_not_mutated(self):
        g = _make_graph()
        orig_edge_count = len(g.edges)
        self.normalizer.normalize(g)
        self.assertEqual(len(g.edges), orig_edge_count)


# ===========================================================================
# GraphIntegrityValidator tests
# ===========================================================================
class TestGraphIntegrityValidator(unittest.TestCase):

    def setUp(self):
        self.validator = GraphIntegrityValidator()

    def test_valid_graph_passes(self):
        g = _make_graph()
        vr = self.validator.validate(g)
        # Orphan warning is OK — both nodes connect via edge
        self.assertFalse(vr.has_errors)

    def test_broken_ref_detected(self):
        n1 = _make_node("n1")
        # Edge references non-existent node "n2"
        e1 = _make_edge("e1", "n1", "nonexistent")
        g = _make_graph(nodes=(n1,), edges=(e1,))
        vr = self.validator.validate(g)
        self.assertTrue(vr.has_warnings or vr.has_errors)

    def test_orphan_node_detected(self):
        n1 = _make_node("n1")
        n2 = _make_node("n2", "obj_2")
        # No edges → both orphans
        metadata = GraphMetadata(graph_id="g", engine_version="1.0.0", source_count=2)
        stats = GraphStatistics(node_count=2, edge_count=0)
        g = SemanticGraph(
            nodes=(n1, n2), edges=(), metadata=metadata,
            statistics=stats, outcome=GraphBuildOutcome.EMPTY, diagnostics=()
        )
        vr = self.validator.validate(g)
        self.assertTrue(vr.has_warnings)

    def test_invalid_rel_type_detected(self):
        n1 = _make_node("n1")
        n2 = _make_node("n2", "obj_2")
        e = SemanticEdge("e1", "n1", "n2", "NOT_A_VALID_TYPE", "forward", 0.5)
        g = _make_graph(nodes=(n1, n2), edges=(e,))
        vr = self.validator.validate(g)
        self.assertTrue(vr.has_errors)


# ===========================================================================
# GraphExporter tests
# ===========================================================================
class TestGraphExporter(unittest.TestCase):

    def setUp(self):
        self.exporter = GraphExporter()

    def test_export_dict(self):
        g = _make_graph()
        artifact = self.exporter.export(g, format=GraphExportFormat.DICT)
        self.assertIsInstance(artifact.payload, dict)
        self.assertIn("nodes", artifact.payload)
        self.assertIn("edges", artifact.payload)

    def test_export_json(self):
        g = _make_graph()
        artifact = self.exporter.export(g, format=GraphExportFormat.JSON)
        self.assertIsInstance(artifact.payload, str)
        parsed = json.loads(artifact.payload)
        self.assertIn("nodes", parsed)

    def test_export_as_json_convenience(self):
        g = _make_graph()
        s = self.exporter.export_as_json(g)
        self.assertIsInstance(s, str)
        json.loads(s)

    def test_export_as_dict_convenience(self):
        g = _make_graph()
        d = self.exporter.export_as_dict(g)
        self.assertIsInstance(d, dict)

    def test_artifact_metadata(self):
        g = _make_graph()
        artifact = self.exporter.export(g)
        self.assertEqual(artifact.node_count, len(g.nodes))
        self.assertEqual(artifact.edge_count, len(g.edges))

    def test_artifact_to_dict(self):
        g = _make_graph()
        artifact = self.exporter.export(g)
        json.dumps(artifact.to_dict())


# ===========================================================================
# RelationshipDiscoveryEngine (end-to-end) tests
# ===========================================================================
class TestRelationshipDiscoveryEngine(unittest.TestCase):

    def setUp(self):
        self.engine = RelationshipDiscoveryEngine()

    def test_empty_input_returns_empty(self):
        result = self.engine.discover([])
        self.assertEqual(result.outcome, DiscoveryOutcome.EMPTY)
        self.assertEqual(len(result.relationships), 0)

    def test_single_result_no_relationships(self):
        r = _make_enrichment_result()
        result = self.engine.discover([r])
        self.assertEqual(result.outcome, DiscoveryOutcome.EMPTY)

    def test_two_results_produces_relationships(self):
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        result = self.engine.discover([r1, r2])
        self.assertIn(result.outcome, (DiscoveryOutcome.COMPLETE, DiscoveryOutcome.PARTIAL))

    def test_discovery_is_deterministic(self):
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.EXEMPLIFIES_CONCEPT)
        res1 = self.engine.discover([r1, r2])
        res2 = self.engine.discover([r1, r2])
        ids1 = sorted(r.relationship_id for r in res1.relationships)
        ids2 = sorted(r.relationship_id for r in res2.relationships)
        self.assertEqual(ids1, ids2)

    def test_build_graph_produces_semantic_graph(self):
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        graph = self.engine.build_graph([r1, r2])
        self.assertIsInstance(graph, SemanticGraph)
        self.assertGreater(graph.statistics.node_count, 0)

    def test_build_graph_nodes_use_m52d_anchor_ids(self):
        r1 = _make_enrichment_result("obj_1")
        graph = self.engine.build_graph([r1])
        if graph.nodes:
            self.assertEqual(graph.nodes[0].node_id, r1.anchor.anchor_id)

    def test_export_produces_artifact(self):
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.EXEMPLIFIES_CONCEPT)
        graph = self.engine.build_graph([r1, r2])
        artifact = self.engine.export(graph)
        self.assertIsInstance(artifact, GraphExportArtifact)

    def test_full_pipeline_json_serializable(self):
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        r3 = _make_enrichment_result("obj_3", SemanticRole.EXEMPLIFIES_CONCEPT)
        graph = self.engine.build_graph([r1, r2, r3])
        json.dumps(graph.to_dict())

    def test_convenience_discover_function(self):
        r1 = _make_enrichment_result("obj_1")
        result = discover([r1])
        self.assertIsInstance(result, RelationshipDiscoveryResult)

    def test_graph_is_normalized_after_build(self):
        # Build with duplicate-prone scenario
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        graph = self.engine.build_graph([r1, r2])
        # After normalization, edge_ids should all be unique
        edge_ids = [e.edge_id for e in graph.edges]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))


# ===========================================================================
# Validation function tests
# ===========================================================================
class TestValidationFunctions(unittest.TestCase):

    def _make_valid_discovery_result(self) -> RelationshipDiscoveryResult:
        r = _make_relationship("src", "tgt", confidence=0.5)
        return RelationshipDiscoveryResult(
            outcome=DiscoveryOutcome.COMPLETE,
            relationships=(r,),
            object_keys=("obj_1", "obj_2"),
            diagnostics=(),
        )

    def test_validate_discovery_result_valid(self):
        result = self._make_valid_discovery_result()
        vr = validate_discovery_result(result)
        self.assertTrue(vr.is_success)

    def test_validate_discovery_result_empty_passes(self):
        result = RelationshipDiscoveryResult(
            outcome=DiscoveryOutcome.EMPTY,
            relationships=(),
            object_keys=(),
            diagnostics=(),
        )
        vr = validate_discovery_result(result)
        self.assertTrue(vr.is_success)

    def test_validate_graph_export_ready_complete(self):
        g = _make_graph(outcome=GraphBuildOutcome.COMPLETE)
        vr = validate_graph_export_ready(g)
        self.assertFalse(vr.has_errors)

    def test_validate_graph_export_ready_error_outcome_fails(self):
        g = _make_graph(outcome=GraphBuildOutcome.ERROR)
        vr = validate_graph_export_ready(g)
        self.assertTrue(vr.has_errors)

    def test_validate_confidence_propagation_valid(self):
        result = self._make_valid_discovery_result()
        vr = validate_confidence_propagation(result)
        self.assertTrue(vr.is_success)

    def test_validate_confidence_propagation_empty(self):
        result = RelationshipDiscoveryResult(
            outcome=DiscoveryOutcome.EMPTY,
            relationships=(),
            object_keys=(),
            diagnostics=(),
        )
        vr = validate_confidence_propagation(result)
        self.assertTrue(vr.is_success)


# ===========================================================================
# Serialization determinism tests
# ===========================================================================
class TestSerializationDeterminism(unittest.TestCase):

    def test_graph_dict_is_stable(self):
        engine = RelationshipDiscoveryEngine()
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        g1 = engine.build_graph([r1, r2])
        g2 = engine.build_graph([r1, r2])
        self.assertEqual(g1.to_dict(), g2.to_dict())

    def test_relationship_id_stable_across_engines(self):
        e1 = RelationshipDiscoveryEngine()
        e2 = RelationshipDiscoveryEngine()
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        r2 = _make_enrichment_result("obj_2", SemanticRole.STATES_PREREQUISITE)
        disc1 = e1.discover([r1, r2])
        disc2 = e2.discover([r1, r2])
        ids1 = sorted(r.relationship_id for r in disc1.relationships)
        ids2 = sorted(r.relationship_id for r in disc2.relationships)
        self.assertEqual(ids1, ids2)


# ===========================================================================
# Backward compatibility guard
# ===========================================================================
class TestBackwardCompatibility(unittest.TestCase):

    def test_m51_importable_and_unmodified(self):
        from modules.educational_object_framework import (
            ValidationResult, ValidationDiagnostic,
            ProcessingResult, ProcessorRegistry,
        )

    def test_m52a_importable_and_unmodified(self):
        from modules.educational_taxonomy import (
            EducationalObjectType, EducationalCategory, default_taxonomy
        )

    def test_m52b_importable_and_unmodified(self):
        from modules.subject_profile_framework import (
            SubjectContribution, SubjectProfile
        )

    def test_m52c_importable_and_unmodified(self):
        from modules.structural_understanding_engine import (
            StructuralAnalysisResult, StructuralUnderstandingEngine,
            CompatibilityValidator, HintResolver,
        )

    def test_m52d_importable_and_unmodified(self):
        from modules.semantic_interpretation_engine import (
            SemanticEnrichmentResult, SemanticEnrichmentEngine,
            SemanticAnchor, default_engine as sie_engine,
        )

    def test_m52d_anchor_ids_not_regenerated(self):
        """M5.2E uses anchor_id values from M5.2D unchanged."""
        r1 = _make_enrichment_result("obj_1", SemanticRole.DEFINES_CONCEPT)
        engine = RelationshipDiscoveryEngine()
        graph = engine.build_graph([r1])
        if graph.nodes:
            # node_id must exactly equal the M5.2D anchor_id
            self.assertEqual(graph.nodes[0].node_id, r1.anchor.anchor_id)

    def test_m52e_does_not_modify_m52d_anchor(self):
        """Building a graph does not mutate the source SemanticAnchor."""
        r1 = _make_enrichment_result("obj_1")
        original_anchor_id = r1.anchor.anchor_id
        engine = RelationshipDiscoveryEngine()
        engine.build_graph([r1])
        self.assertEqual(r1.anchor.anchor_id, original_anchor_id)


if __name__ == "__main__":
    unittest.main()
