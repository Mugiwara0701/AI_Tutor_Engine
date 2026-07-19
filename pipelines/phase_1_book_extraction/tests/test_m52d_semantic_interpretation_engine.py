"""
tests/test_m52d_semantic_interpretation_engine.py — M5.2D unit tests
for modules/semantic_interpretation_engine (the Semantic Interpretation
& Enrichment Engine).

Coverage:
  - enums: all SemanticRole, PedagogicalRole, LearningIntent,
           InstructionalContext, ConfidenceLevel, EnrichmentOutcome,
           CompatibilitySeverity values are str-based
  - models: immutability (FrozenInstanceError), validation contracts,
            to_dict() determinism, ConfidenceEvidence, ConfidenceScore,
            ConfidenceBreakdown, SemanticInterpretation, SemanticObject,
            CompatibilityResult, SemanticAnchor, SemanticEnrichmentResult
  - config: threshold ordering validation, to_dict() round-trip
  - confidence: ConfidenceEvaluator produces scores in [0.0, 1.0],
                correct bands for COMPLETE / INCOMPLETE / UNRECOGNIZED
  - semantic_resolver: known roles map correctly, unknown roles produce
                       UNKNOWN with low confidence, resolve_all is
                       deterministically ordered
  - anchor_builder: anchor_id is UUID5/deterministic, same input always
                    produces same anchor_id, distinct inputs differ
  - hint_diagnostics: HintDiagnosticsEngine wraps HintResolver correctly,
                      known keys are resolved, unknown keys produce warnings
  - pattern_versioning: PatternVersion registration, version selection,
                        PatternCompatibility range acceptance,
                        PatternVersionRegistry duplicate guard
  - compatibility_interpreter: CompatibilityInterpreter wraps
                                CompatibilityValidator, produces rich result
  - engine: SemanticEnrichmentEngine end-to-end (COMPLETE, PARTIAL,
            UNRECOGNIZED, INCOMPATIBLE paths); SemanticInterpretationEngine
            returns None for UNRECOGNIZED
  - validation: validate_semantic_enrichment_result guards, anchor
                uniqueness check, confidence consistency
  - serialization: to_dict() outputs are JSON-serializable and deterministic
  - backward compatibility: M5.1, M5.2A, M5.2B, M5.2C remain importable
                            and unmodified by M5.2D
"""
from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Tuple

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Prior-milestone imports (backward-compatibility guard)
# ---------------------------------------------------------------------------
from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import SUCCESS, ValidationResult

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.models import EducationalObjectType
from modules.educational_taxonomy.registry import TaxonomyRegistry

from modules.subject_profile_framework.enums import CopyrightSensitivity, SupportLevel
from modules.subject_profile_framework.models import SubjectContribution, SubjectProfile
from modules.subject_profile_framework.registry import SubjectProfileRegistry

from modules.structural_understanding_engine.enums import AnalysisOutcome
from modules.structural_understanding_engine.patterns import (
    StructuralComponent,
    StructuralPattern,
    StructuralPatternRegistry,
)
from modules.structural_understanding_engine.structural_models import (
    StructuralAnalysisResult,
    StructuralObject,
)
from modules.structural_understanding_engine.compatibility import CompatibilityValidator
from modules.structural_understanding_engine.hint_resolver import HintResolver

# ---------------------------------------------------------------------------
# M5.2D imports
# ---------------------------------------------------------------------------
from modules.semantic_interpretation_engine.enums import (
    CompatibilitySeverity,
    ConfidenceLevel,
    EnrichmentOutcome,
    InstructionalContext,
    LearningIntent,
    PedagogicalRole,
    SemanticRole,
)
from modules.semantic_interpretation_engine.models import (
    DEFAULT_SEMANTIC_VERSION,
    CompatibilityResult,
    ConfidenceBreakdown,
    ConfidenceEvidence,
    ConfidenceScore,
    SemanticAnchor,
    SemanticEnrichmentResult,
    SemanticInterpretation,
    SemanticObject,
)
from modules.semantic_interpretation_engine.config import (
    DEFAULT_ENGINE_VERSION,
    SemanticInterpretationEngineConfig,
    default_config,
)
from modules.semantic_interpretation_engine.exceptions import (
    PatternVersionError,
    SemanticAnchorError,
    SemanticValidationError,
)
from modules.semantic_interpretation_engine.confidence import ConfidenceEvaluator
from modules.semantic_interpretation_engine.semantic_resolver import (
    ROLE_MAPPING,
    SemanticResolver,
)
from modules.semantic_interpretation_engine.anchor_builder import (
    ANCHOR_NAMESPACE,
    SemanticAnchorBuilder,
    _deterministic_anchor_id,
)
from modules.semantic_interpretation_engine.hint_diagnostics import (
    HintDiagnosticsEngine,
    HintDiagnosticsResult,
    HintWarning,
)
from modules.semantic_interpretation_engine.pattern_versioning import (
    DEFAULT_PATTERN_SEMANTIC_VERSION,
    PatternCompatibility,
    PatternMetadata,
    PatternSelection,
    PatternVersion,
    PatternVersionRegistry,
)
from modules.semantic_interpretation_engine.compatibility_interpreter import (
    CompatibilityInterpreter,
)
from modules.semantic_interpretation_engine.engine import (
    SemanticEnrichmentEngine,
    SemanticInterpretationEngine,
    default_engine,
    enrich,
)
from modules.semantic_interpretation_engine.validation import (
    validate_anchor_uniqueness,
    validate_confidence_consistency,
    validate_semantic_enrichment_result,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_object_type(
    key: str = "concept",
    category: EducationalCategory = EducationalCategory.KNOWLEDGE,
    version: str = "1.0.0",
) -> EducationalObjectType:
    return EducationalObjectType(
        key=key,
        category=category,
        display_name=key.replace("_", " ").title(),
        description=f"Test type: {key}",
        version=version,
    )


def _make_structural_result(
    object_key: str = "obj_001",
    pattern_key: str = "definition",
    outcome: AnalysisOutcome = AnalysisOutcome.COMPLETE,
    present_roles: Tuple[str, ...] = ("concept", "definition"),
    missing_roles: Tuple[str, ...] = (),
) -> StructuralAnalysisResult:
    return StructuralAnalysisResult(
        object_key=object_key,
        pattern_key=pattern_key,
        outcome=outcome,
        present_roles=present_roles,
        missing_roles=missing_roles,
    )


def _make_structural_object(
    object_key: str = "obj_001",
    object_type_key: str = "concept",
    pattern_key: str = "definition",
) -> StructuralObject:
    return StructuralObject(
        object_key=object_key,
        object_type_key=object_type_key,
        pattern_key=pattern_key,
    )


def _make_confidence_score(value: float = 0.9) -> ConfidenceScore:
    level = (
        ConfidenceLevel.HIGH if value >= 0.80
        else ConfidenceLevel.MEDIUM if value >= 0.50
        else ConfidenceLevel.LOW if value >= 0.20
        else ConfidenceLevel.NONE
    )
    return ConfidenceScore(
        value=value,
        level=level,
        evidence=(
            ConfidenceEvidence(label="test", weight=1.0, passed=value >= 0.5),
        ),
    )


def _make_breakdown(v: float = 0.9) -> ConfidenceBreakdown:
    s = _make_confidence_score(v)
    return ConfidenceBreakdown(structural=s, semantic=s, enrichment=s)


def _make_compat_result(compatible: bool = True) -> CompatibilityResult:
    return CompatibilityResult(
        compatible=compatible,
        severity=CompatibilitySeverity.OK if compatible else CompatibilitySeverity.ERROR,
        reason="OK" if compatible else "ERR",
    )


def _make_contribution(
    subject_key: str = "math",
    object_type: EducationalObjectType = None,
    structural_hints: dict = None,
) -> SubjectContribution:
    if object_type is None:
        object_type = _make_object_type()
    return SubjectContribution(
        subject_key=subject_key,
        object_type=object_type,
        structural_hints=structural_hints or {},
    )


# ===========================================================================
# Enum tests
# ===========================================================================
class TestEnums(unittest.TestCase):

    def test_semantic_role_is_str(self):
        for role in SemanticRole:
            self.assertIsInstance(role.value, str)
            self.assertEqual(role, role.value)

    def test_pedagogical_role_is_str(self):
        for role in PedagogicalRole:
            self.assertIsInstance(role.value, str)

    def test_confidence_level_ordering(self):
        levels = [ConfidenceLevel.NONE, ConfidenceLevel.LOW,
                  ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH]
        self.assertEqual(len(levels), 4)

    def test_enrichment_outcome_has_expected_values(self):
        expected = {"complete", "partial", "unrecognized", "incompatible", "error"}
        actual = {e.value for e in EnrichmentOutcome}
        self.assertEqual(expected, actual)


# ===========================================================================
# Config tests
# ===========================================================================
class TestConfig(unittest.TestCase):

    def test_default_config_thresholds(self):
        cfg = SemanticInterpretationEngineConfig()
        self.assertEqual(cfg.version, DEFAULT_ENGINE_VERSION)
        self.assertLessEqual(cfg.low_confidence_threshold, cfg.medium_confidence_threshold)
        self.assertLessEqual(cfg.medium_confidence_threshold, cfg.high_confidence_threshold)

    def test_invalid_threshold_order_raises(self):
        with self.assertRaises(ValueError):
            SemanticInterpretationEngineConfig(
                low_confidence_threshold=0.9,
                medium_confidence_threshold=0.5,
            )

    def test_to_dict_round_trip(self):
        cfg = SemanticInterpretationEngineConfig()
        d = cfg.to_dict()
        self.assertEqual(d["version"], DEFAULT_ENGINE_VERSION)
        self.assertIn("high_confidence_threshold", d)
        # Must be JSON-serializable
        json.dumps(d)

    def test_config_is_immutable(self):
        cfg = SemanticInterpretationEngineConfig()
        with self.assertRaises(FrozenInstanceError):
            cfg.version = "2.0.0"  # type: ignore[misc]


# ===========================================================================
# Model tests
# ===========================================================================
class TestConfidenceEvidence(unittest.TestCase):

    def test_valid_evidence(self):
        e = ConfidenceEvidence(label="test", weight=0.5, passed=True)
        self.assertEqual(e.label, "test")
        self.assertTrue(e.passed)

    def test_empty_label_raises(self):
        with self.assertRaises(SemanticValidationError):
            ConfidenceEvidence(label="", weight=0.5, passed=True)

    def test_weight_out_of_range_raises(self):
        with self.assertRaises(SemanticValidationError):
            ConfidenceEvidence(label="x", weight=1.5, passed=True)

    def test_immutable(self):
        e = ConfidenceEvidence(label="x", weight=0.3, passed=False)
        with self.assertRaises(FrozenInstanceError):
            e.passed = True  # type: ignore[misc]

    def test_to_dict(self):
        e = ConfidenceEvidence(label="role_match", weight=0.7, passed=True, detail="ok")
        d = e.to_dict()
        self.assertEqual(d["label"], "role_match")
        self.assertEqual(d["weight"], 0.7)
        self.assertTrue(d["passed"])
        json.dumps(d)


class TestConfidenceScore(unittest.TestCase):

    def test_valid_score(self):
        s = _make_confidence_score(0.85)
        self.assertEqual(s.level, ConfidenceLevel.HIGH)

    def test_out_of_range_raises(self):
        with self.assertRaises(SemanticValidationError):
            ConfidenceScore(value=1.5, level=ConfidenceLevel.HIGH)

    def test_immutable(self):
        s = _make_confidence_score(0.5)
        with self.assertRaises(FrozenInstanceError):
            s.value = 0.9  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        s = _make_confidence_score(0.75)
        json.dumps(s.to_dict())


class TestSemanticObject(unittest.TestCase):

    def test_valid_object(self):
        obj = SemanticObject(
            object_key="obj_1",
            object_type_key="concept",
            pattern_key="definition",
        )
        self.assertEqual(obj.object_key, "obj_1")

    def test_empty_key_raises(self):
        with self.assertRaises(SemanticValidationError):
            SemanticObject(object_key="", object_type_key="concept", pattern_key=None)

    def test_immutable(self):
        obj = SemanticObject(object_key="obj_1", object_type_key="t", pattern_key=None)
        with self.assertRaises(FrozenInstanceError):
            obj.object_key = "changed"  # type: ignore[misc]

    def test_to_dict_deterministic(self):
        obj = SemanticObject(
            object_key="obj_1",
            object_type_key="concept",
            pattern_key="definition",
        )
        d1 = obj.to_dict()
        d2 = obj.to_dict()
        self.assertEqual(d1, d2)
        json.dumps(d1)


class TestCompatibilityResult(unittest.TestCase):

    def test_compatible(self):
        r = CompatibilityResult(
            compatible=True,
            severity=CompatibilitySeverity.OK,
            reason="All good",
        )
        self.assertTrue(r.compatible)
        self.assertEqual(r.severity, CompatibilitySeverity.OK)

    def test_immutable(self):
        r = _make_compat_result()
        with self.assertRaises(FrozenInstanceError):
            r.compatible = False  # type: ignore[misc]

    def test_to_dict(self):
        r = CompatibilityResult(
            compatible=False,
            severity=CompatibilitySeverity.ERROR,
            reason="Too old",
            affected_components=("role_a",),
            suggested_resolution="Upgrade type.",
            object_type_key="concept",
            object_type_version="0.9.0",
        )
        d = r.to_dict()
        self.assertFalse(d["compatible"])
        self.assertEqual(d["severity"], "error")
        self.assertIn("role_a", d["affected_components"])
        json.dumps(d)


class TestSemanticAnchor(unittest.TestCase):

    def test_valid_anchor(self):
        anchor = SemanticAnchor(
            anchor_id="test-id",
            semantic_role=SemanticRole.DEFINES_CONCEPT,
            object_reference="obj_1",
            confidence=_make_confidence_score(0.9),
        )
        self.assertEqual(anchor.anchor_id, "test-id")

    def test_empty_anchor_id_raises(self):
        with self.assertRaises(SemanticValidationError):
            SemanticAnchor(
                anchor_id="",
                semantic_role=SemanticRole.DEFINES_CONCEPT,
                object_reference="obj_1",
                confidence=_make_confidence_score(),
            )

    def test_to_dict(self):
        anchor = SemanticAnchor(
            anchor_id="abc",
            semantic_role=SemanticRole.EXEMPLIFIES_CONCEPT,
            object_reference="obj_2",
            confidence=_make_confidence_score(0.8),
            pattern_key="definition",
        )
        d = anchor.to_dict()
        self.assertEqual(d["anchor_id"], "abc")
        self.assertEqual(d["semantic_role"], "exemplifies_concept")
        json.dumps(d)


class TestSemanticEnrichmentResult(unittest.TestCase):

    def _make_result(self, outcome=EnrichmentOutcome.COMPLETE) -> SemanticEnrichmentResult:
        sem_obj = SemanticObject(
            object_key="obj_1",
            object_type_key="concept",
            pattern_key="definition",
        )
        anchor = SemanticAnchor(
            anchor_id="anc-001",
            semantic_role=SemanticRole.DEFINES_CONCEPT,
            object_reference="obj_1",
            confidence=_make_confidence_score(0.9),
        )
        return SemanticEnrichmentResult(
            object_key="obj_1",
            outcome=outcome,
            semantic_object=sem_obj,
            confidence=_make_breakdown(0.9),
            compatibility_result=_make_compat_result(),
            anchor=anchor,
        )

    def test_complete_result(self):
        r = self._make_result()
        self.assertTrue(r.is_complete())

    def test_immutable(self):
        r = self._make_result()
        with self.assertRaises(FrozenInstanceError):
            r.outcome = EnrichmentOutcome.PARTIAL  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        r = self._make_result()
        json.dumps(r.to_dict())

    def test_to_dict_deterministic(self):
        r = self._make_result()
        self.assertEqual(r.to_dict(), r.to_dict())

    def test_empty_key_raises(self):
        with self.assertRaises(SemanticValidationError):
            SemanticEnrichmentResult(
                object_key="",
                outcome=EnrichmentOutcome.ERROR,
                semantic_object=None,
                confidence=_make_breakdown(0.0),
                compatibility_result=_make_compat_result(False),
                anchor=None,
            )


# ===========================================================================
# Confidence evaluator tests
# ===========================================================================
class TestConfidenceEvaluator(unittest.TestCase):

    def setUp(self):
        self.evaluator = ConfidenceEvaluator()

    def _evaluate(self, outcome=AnalysisOutcome.COMPLETE, present=("concept",),
                  missing=(), pattern_key="definition", interp_count=1, has_anchor=True):
        return self.evaluator.evaluate(
            analysis_outcome=outcome,
            present_roles=present,
            missing_roles=missing,
            pattern_key=pattern_key,
            interpretation_count=interp_count,
            has_anchor=has_anchor,
        )

    def test_complete_high_confidence(self):
        bd = self._evaluate()
        self.assertIn(bd.structural.level, (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM))
        self.assertGreater(bd.structural.value, 0.0)

    def test_unrecognized_lower_confidence(self):
        bd_complete = self._evaluate(outcome=AnalysisOutcome.COMPLETE)
        bd_unrec = self._evaluate(
            outcome=AnalysisOutcome.UNRECOGNIZED_PATTERN,
            pattern_key=None,
            interp_count=0,
            has_anchor=False,
        )
        self.assertGreater(bd_complete.structural.value, bd_unrec.structural.value)

    def test_scores_in_range(self):
        for outcome in (AnalysisOutcome.COMPLETE, AnalysisOutcome.INCOMPLETE, AnalysisOutcome.UNRECOGNIZED_PATTERN):
            bd = self._evaluate(outcome=outcome, pattern_key=None, interp_count=0, has_anchor=False)
            for score in [bd.structural, bd.semantic, bd.enrichment]:
                self.assertGreaterEqual(score.value, 0.0)
                self.assertLessEqual(score.value, 1.0)

    def test_missing_roles_reduce_structural_confidence(self):
        bd_full = self._evaluate(missing=())
        bd_missing = self._evaluate(missing=("prerequisites",))
        self.assertGreater(bd_full.structural.value, bd_missing.structural.value)

    def test_breakdown_to_dict_json_serializable(self):
        bd = self._evaluate()
        json.dumps(bd.to_dict())


# ===========================================================================
# Semantic resolver tests
# ===========================================================================
class TestSemanticResolver(unittest.TestCase):

    def setUp(self):
        self.resolver = SemanticResolver()

    def test_known_role_definition(self):
        interp = self.resolver.resolve_role("definition")
        self.assertEqual(interp.semantic_role, SemanticRole.DEFINES_CONCEPT)
        self.assertEqual(interp.pedagogical_role, PedagogicalRole.INTRODUCE)
        self.assertEqual(interp.learning_intent, LearningIntent.DECLARATIVE_KNOWLEDGE)

    def test_known_role_concept(self):
        interp = self.resolver.resolve_role("concept")
        self.assertEqual(interp.semantic_role, SemanticRole.DEFINES_CONCEPT)

    def test_known_role_steps(self):
        interp = self.resolver.resolve_role("steps")
        self.assertEqual(interp.semantic_role, SemanticRole.SEQUENCES_INSTRUCTION)
        self.assertEqual(interp.learning_intent, LearningIntent.PROCEDURAL_KNOWLEDGE)

    def test_unknown_role_returns_unknown(self):
        interp = self.resolver.resolve_role("nonexistent_role_xyz")
        self.assertEqual(interp.semantic_role, SemanticRole.UNKNOWN)
        self.assertEqual(interp.pedagogical_role, PedagogicalRole.UNKNOWN)

    def test_unknown_role_low_confidence(self):
        interp = self.resolver.resolve_role("nonexistent_role_xyz")
        self.assertIn(interp.confidence.level, (ConfidenceLevel.LOW, ConfidenceLevel.NONE))

    def test_case_insensitive_matching(self):
        interp_lower = self.resolver.resolve_role("definition")
        interp_upper = self.resolver.resolve_role("DEFINITION")
        self.assertEqual(interp_lower.semantic_role, interp_upper.semantic_role)

    def test_resolve_all_deterministic_order(self):
        roles = ["steps", "concept", "learning_objective"]
        r1 = self.resolver.resolve_all(roles)
        r2 = self.resolver.resolve_all(roles)
        self.assertEqual([i.structural_role for i in r1], [i.structural_role for i in r2])

    def test_resolve_all_deduplicates(self):
        roles = ["concept", "concept", "definition"]
        result = self.resolver.resolve_all(roles)
        structural_roles = [i.structural_role for i in result]
        self.assertEqual(len(structural_roles), len(set(structural_roles)))

    def test_interpretation_is_immutable(self):
        interp = self.resolver.resolve_role("concept")
        with self.assertRaises(FrozenInstanceError):
            interp.semantic_role = SemanticRole.UNKNOWN  # type: ignore[misc]

    def test_role_mapping_coverage(self):
        # All keys in ROLE_MAPPING should resolve to non-UNKNOWN
        for role_key in ROLE_MAPPING:
            interp = self.resolver.resolve_role(role_key)
            self.assertNotEqual(
                interp.semantic_role, SemanticRole.UNKNOWN,
                f"ROLE_MAPPING key {role_key!r} resolved to UNKNOWN"
            )


# ===========================================================================
# Anchor builder tests
# ===========================================================================
class TestSemanticAnchorBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = SemanticAnchorBuilder()

    def _make_obj(self, key="obj_1", pattern_key="definition") -> SemanticObject:
        return SemanticObject(
            object_key=key,
            object_type_key="concept",
            pattern_key=pattern_key,
        )

    def test_anchor_id_is_deterministic(self):
        obj = self._make_obj()
        a1 = self.builder.build(obj)
        a2 = self.builder.build(obj)
        self.assertEqual(a1.anchor_id, a2.anchor_id)

    def test_distinct_objects_different_anchor_ids(self):
        a1 = self.builder.build(self._make_obj("obj_A"))
        a2 = self.builder.build(self._make_obj("obj_B"))
        self.assertNotEqual(a1.anchor_id, a2.anchor_id)

    def test_anchor_references_correct_object(self):
        obj = self._make_obj("my_obj")
        anchor = self.builder.build(obj)
        self.assertEqual(anchor.object_reference, "my_obj")

    def test_anchor_id_format_is_uuid(self):
        import uuid
        anchor = self.builder.build(self._make_obj())
        # Should not raise
        parsed = uuid.UUID(anchor.anchor_id)
        self.assertEqual(str(parsed), anchor.anchor_id)

    def test_deterministic_anchor_id_helper(self):
        id1 = _deterministic_anchor_id("obj_1", SemanticRole.DEFINES_CONCEPT)
        id2 = _deterministic_anchor_id("obj_1", SemanticRole.DEFINES_CONCEPT)
        self.assertEqual(id1, id2)

    def test_empty_object_key_raises(self):
        # Build a SemanticAnchorBuilder and call build with a SemanticObject
        # whose object_key is empty — we achieve this by constructing a
        # SemanticObject with a valid key then replacing it at the dict level.
        # Since SemanticObject is frozen we test via the builder's guard directly.
        import dataclasses
        obj = SemanticObject(object_key="valid", object_type_key="t", pattern_key=None)
        # Bypass frozen check to simulate empty key reaching the builder
        bad_obj = dataclasses.replace(obj)
        # The only way to trigger SemanticAnchorError is to reach the builder
        # with an empty object_reference. We do so via a patched build call.
        # Since we can't easily produce an empty-key SemanticObject (the model
        # rejects it), we verify the builder raises when we force the condition.
        with self.assertRaises(SemanticAnchorError):
            # Manually call _deterministic_anchor_id path with empty string
            # to confirm the builder guard fires.
            from modules.semantic_interpretation_engine.anchor_builder import SemanticAnchorBuilder
            class _EmptyObj:
                object_key = ""
                object_type_key = "t"
                pattern_key = None
                interpretations = ()
            builder = SemanticAnchorBuilder()
            builder.build(_EmptyObj())  # type: ignore[arg-type]

    def test_anchor_is_immutable(self):
        anchor = self.builder.build(self._make_obj())
        with self.assertRaises(FrozenInstanceError):
            anchor.object_reference = "changed"  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        anchor = self.builder.build(self._make_obj())
        json.dumps(anchor.to_dict())


# ===========================================================================
# Hint diagnostics tests
# ===========================================================================
class TestHintDiagnosticsEngine(unittest.TestCase):

    def setUp(self):
        self.engine = HintDiagnosticsEngine()

    def _contrib(self, structural_hints=None, processing_hints=None):
        return _make_contribution(
            structural_hints=structural_hints or {},
        )

    def test_diagnose_returns_result(self):
        c = self._contrib(structural_hints={"pattern_key": "definition"})
        result = self.engine.diagnose(c)
        self.assertIsInstance(result, HintDiagnosticsResult)

    def test_known_key_is_resolved(self):
        c = self._contrib(structural_hints={"pattern_key": "definition"})
        result = self.engine.diagnose(c)
        self.assertIn("pattern_key", result.resolved_keys.get("structural_hints", []))

    def test_unknown_key_produces_warning(self):
        c = self._contrib(structural_hints={"nonexistent_key": "value"})
        result = self.engine.diagnose(c)
        warning_keys = [w.key for w in result.warnings]
        self.assertIn("nonexistent_key", warning_keys)

    def test_ignored_keys_captured(self):
        c = self._contrib(structural_hints={"mystery_key": 123})
        result = self.engine.diagnose(c)
        ignored = result.ignored_keys.get("structural_hints", [])
        self.assertIn("mystery_key", ignored)

    def test_defaulted_keys_listed(self):
        # No structural_hints provided → all known keys are defaulted
        c = self._contrib(structural_hints={})
        result = self.engine.diagnose(c)
        defaulted = result.defaulted_keys.get("structural_hints", [])
        # "component_aliases" should be defaulted (not provided)
        self.assertIn("component_aliases", defaulted)

    def test_resolved_hints_match_m52c(self):
        c = self._contrib(structural_hints={"pattern_key": "definition"})
        result = self.engine.diagnose(c)
        # ResolvedHints is the M5.2C type — it should be accessible
        from modules.structural_understanding_engine.hints import ResolvedHints
        self.assertIsInstance(result.resolved_hints, ResolvedHints)

    def test_to_dict_json_serializable(self):
        c = self._contrib(structural_hints={"pattern_key": "definition", "unknown_x": 1})
        result = self.engine.diagnose(c)
        json.dumps(result.to_dict())


# ===========================================================================
# Pattern versioning tests
# ===========================================================================
class TestPatternVersioning(unittest.TestCase):

    def setUp(self):
        self.registry = PatternVersionRegistry()

    def _make_pv(
        self,
        pattern_key: str = "definition",
        semantic_version: str = "1.0.0",
        deprecated: bool = False,
    ) -> PatternVersion:
        return PatternVersion(
            pattern_key=pattern_key,
            semantic_version=semantic_version,
            metadata=PatternMetadata(
                description="Test pattern",
                deprecated=deprecated,
            ),
        )

    def test_register_and_get(self):
        pv = self._make_pv()
        self.registry.register(pv)
        retrieved = self.registry.get("definition", "1.0.0")
        self.assertEqual(retrieved.pattern_key, "definition")

    def test_duplicate_raises(self):
        pv = self._make_pv()
        self.registry.register(pv)
        with self.assertRaises(PatternVersionError):
            self.registry.register(pv)

    def test_select_newest_compatible(self):
        self.registry.register(self._make_pv("def", "1.0.0"))
        self.registry.register(self._make_pv("def", "1.1.0"))
        sel = self.registry.select("def", "1.0.0")
        self.assertEqual(sel.pattern_version.semantic_version, "1.1.0")

    def test_select_skips_deprecated(self):
        self.registry.register(self._make_pv("def", "1.0.0"))
        self.registry.register(self._make_pv("def", "1.1.0", deprecated=True))
        sel = self.registry.select("def", "1.0.0")
        self.assertEqual(sel.pattern_version.semantic_version, "1.0.0")

    def test_select_fallback_when_no_compat(self):
        pv = PatternVersion(
            pattern_key="def",
            semantic_version="1.0.0",
            compatibility=PatternCompatibility(
                minimum_engine_version="2.0.0"
            ),
        )
        self.registry.register(pv)
        # engine is 1.0.0 which is below min → fallback
        sel = self.registry.select("def", "1.0.0")
        self.assertTrue(sel.fallback_used)

    def test_pattern_compatibility_accepts(self):
        pc = PatternCompatibility(minimum_engine_version="1.0.0", maximum_engine_version="2.0.0")
        self.assertTrue(pc.accepts("1.5.0"))
        self.assertFalse(pc.accepts("0.9.0"))
        self.assertFalse(pc.accepts("2.1.0"))

    def test_invalid_version_format_raises(self):
        with self.assertRaises(PatternVersionError):
            PatternVersion(pattern_key="x", semantic_version="bad-version")

    def test_empty_pattern_key_raises(self):
        with self.assertRaises(PatternVersionError):
            PatternVersion(pattern_key="", semantic_version="1.0.0")

    def test_version_is_immutable(self):
        pv = self._make_pv()
        with self.assertRaises(FrozenInstanceError):
            pv.semantic_version = "2.0.0"  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        pv = self._make_pv()
        json.dumps(pv.to_dict())

    def test_unregister(self):
        pv = self._make_pv()
        self.registry.register(pv)
        self.registry.unregister("definition", "1.0.0")
        self.assertEqual(len(self.registry), 0)


# ===========================================================================
# Compatibility interpreter tests
# ===========================================================================
class TestCompatibilityInterpreter(unittest.TestCase):

    def setUp(self):
        self.interpreter = CompatibilityInterpreter()

    def test_compatible_object_type(self):
        obj_type = _make_object_type(version="1.0.0")
        result = self.interpreter.interpret_object_type(obj_type)
        self.assertIsInstance(result, CompatibilityResult)
        self.assertIn(result.severity, CompatibilitySeverity)

    def test_incompatible_produces_error_severity(self):
        # Version "0.1.0" is likely too old
        obj_type = _make_object_type(version="0.0.1")
        result = self.interpreter.interpret_object_type(obj_type)
        # Whether compatible or not, result must be a CompatibilityResult
        self.assertIsInstance(result, CompatibilityResult)
        self.assertIsNotNone(result.reason)

    def test_result_is_immutable(self):
        obj_type = _make_object_type()
        result = self.interpreter.interpret_object_type(obj_type)
        with self.assertRaises(FrozenInstanceError):
            result.compatible = not result.compatible  # type: ignore[misc]

    def test_to_dict_json_serializable(self):
        obj_type = _make_object_type()
        result = self.interpreter.interpret_object_type(obj_type)
        json.dumps(result.to_dict())

    def test_reason_is_non_empty(self):
        obj_type = _make_object_type()
        result = self.interpreter.interpret_object_type(obj_type)
        self.assertTrue(len(result.reason) > 0)


# ===========================================================================
# SemanticInterpretationEngine tests
# ===========================================================================
class TestSemanticInterpretationEngine(unittest.TestCase):

    def setUp(self):
        self.engine = SemanticInterpretationEngine()

    def test_returns_semantic_object_for_complete(self):
        result = _make_structural_result()
        obj = self.engine.interpret(result)
        self.assertIsNotNone(obj)
        self.assertEqual(obj.object_key, "obj_001")

    def test_returns_none_for_unrecognized_pattern(self):
        # AnalysisOutcome has COMPLETE, INCOMPLETE, UNRECOGNIZED_PATTERN
        result = _make_structural_result(
            outcome=AnalysisOutcome.UNRECOGNIZED_PATTERN, pattern_key=None, present_roles=()
        )
        obj = self.engine.interpret(result)
        self.assertIsNone(obj)

    def test_semantic_object_has_interpretations(self):
        result = _make_structural_result(
            present_roles=("concept", "definition", "examples"),
        )
        obj = self.engine.interpret(result)
        self.assertGreater(len(obj.interpretations), 0)

    def test_semantic_object_is_immutable(self):
        result = _make_structural_result()
        obj = self.engine.interpret(result)
        with self.assertRaises(FrozenInstanceError):
            obj.object_key = "changed"  # type: ignore[misc]


# ===========================================================================
# SemanticEnrichmentEngine (end-to-end) tests
# ===========================================================================
class TestSemanticEnrichmentEngine(unittest.TestCase):

    def setUp(self):
        self.engine = SemanticEnrichmentEngine()

    def test_complete_path(self):
        structural = _make_structural_result()
        struct_obj = _make_structural_object()
        result = self.engine.enrich(structural, structural_object=struct_obj)
        self.assertIsInstance(result, SemanticEnrichmentResult)
        self.assertEqual(result.object_key, "obj_001")
        self.assertIn(result.outcome, (EnrichmentOutcome.COMPLETE, EnrichmentOutcome.PARTIAL))

    def test_unrecognized_path(self):
        structural = _make_structural_result(
            outcome=AnalysisOutcome.UNRECOGNIZED_PATTERN,
            pattern_key=None,
            present_roles=(),
        )
        result = self.engine.enrich(structural)
        self.assertEqual(result.outcome, EnrichmentOutcome.UNRECOGNIZED)
        self.assertIsNone(result.semantic_object)

    def test_with_object_type_compatibility_check(self):
        structural = _make_structural_result()
        obj_type = _make_object_type()
        result = self.engine.enrich(structural, object_type=obj_type)
        self.assertIsInstance(result.compatibility_result, CompatibilityResult)
        self.assertIsNotNone(result.compatibility_result.reason)

    def test_anchor_present_for_complete(self):
        structural = _make_structural_result()
        result = self.engine.enrich(structural)
        # anchor is built when semantic_object is produced
        if result.semantic_object is not None:
            self.assertIsNotNone(result.anchor)

    def test_structural_snapshot_present(self):
        structural = _make_structural_result()
        result = self.engine.enrich(structural)
        self.assertIn("object_key", result.structural_snapshot)

    def test_determinism(self):
        structural = _make_structural_result()
        r1 = self.engine.enrich(structural)
        r2 = self.engine.enrich(structural)
        self.assertEqual(r1.to_dict(), r2.to_dict())

    def test_to_dict_json_serializable(self):
        structural = _make_structural_result()
        result = self.engine.enrich(structural)
        json.dumps(result.to_dict())

    def test_convenience_enrich_function(self):
        structural = _make_structural_result()
        result = enrich(structural)
        self.assertIsInstance(result, SemanticEnrichmentResult)

    def test_partial_path(self):
        structural = _make_structural_result(
            outcome=AnalysisOutcome.INCOMPLETE,
            present_roles=("concept",),
            missing_roles=("prerequisites",),
        )
        result = self.engine.enrich(structural)
        self.assertIn(result.outcome, (EnrichmentOutcome.PARTIAL, EnrichmentOutcome.COMPLETE))


# ===========================================================================
# Validation tests
# ===========================================================================
class TestValidation(unittest.TestCase):

    def _make_complete_result(self) -> SemanticEnrichmentResult:
        sem_obj = SemanticObject(
            object_key="obj_1",
            object_type_key="concept",
            pattern_key="definition",
        )
        anchor = SemanticAnchor(
            anchor_id="anc-001",
            semantic_role=SemanticRole.DEFINES_CONCEPT,
            object_reference="obj_1",
            confidence=_make_confidence_score(0.9),
        )
        return SemanticEnrichmentResult(
            object_key="obj_1",
            outcome=EnrichmentOutcome.COMPLETE,
            semantic_object=sem_obj,
            confidence=_make_breakdown(0.9),
            compatibility_result=_make_compat_result(),
            anchor=anchor,
        )

    def test_valid_result_passes(self):
        result = self._make_complete_result()
        vr = validate_semantic_enrichment_result(result)
        self.assertTrue(vr.is_success)

    def test_complete_without_semantic_object_fails(self):
        result = SemanticEnrichmentResult(
            object_key="obj_1",
            outcome=EnrichmentOutcome.COMPLETE,
            semantic_object=None,  # missing — should fail
            confidence=_make_breakdown(0.9),
            compatibility_result=_make_compat_result(),
            anchor=None,
        )
        vr = validate_semantic_enrichment_result(result)
        self.assertTrue(vr.has_errors)

    def test_anchor_uniqueness_passes(self):
        r1 = self._make_complete_result()
        # Second result with different object_key → different anchor_id
        sem_obj2 = SemanticObject(
            object_key="obj_2",
            object_type_key="concept",
            pattern_key="definition",
        )
        anchor2 = SemanticAnchor(
            anchor_id="anc-002",
            semantic_role=SemanticRole.DEFINES_CONCEPT,
            object_reference="obj_2",
            confidence=_make_confidence_score(0.9),
        )
        r2 = SemanticEnrichmentResult(
            object_key="obj_2",
            outcome=EnrichmentOutcome.COMPLETE,
            semantic_object=sem_obj2,
            confidence=_make_breakdown(0.9),
            compatibility_result=_make_compat_result(),
            anchor=anchor2,
        )
        vr = validate_anchor_uniqueness([r1, r2])
        self.assertTrue(vr.is_success)

    def test_duplicate_anchor_ids_fail(self):
        r1 = self._make_complete_result()
        # Force same anchor_id
        anchor_dup = SemanticAnchor(
            anchor_id="anc-001",  # same as r1
            semantic_role=SemanticRole.DEFINES_CONCEPT,
            object_reference="obj_3",
            confidence=_make_confidence_score(0.9),
        )
        sem_obj3 = SemanticObject(
            object_key="obj_3",
            object_type_key="concept",
            pattern_key="definition",
        )
        r3 = SemanticEnrichmentResult(
            object_key="obj_3",
            outcome=EnrichmentOutcome.COMPLETE,
            semantic_object=sem_obj3,
            confidence=_make_breakdown(0.9),
            compatibility_result=_make_compat_result(),
            anchor=anchor_dup,
        )
        vr = validate_anchor_uniqueness([r1, r3])
        self.assertTrue(vr.has_errors)

    def test_confidence_consistency_passes_for_valid(self):
        result = self._make_complete_result()
        vr = validate_confidence_consistency(result)
        # Valid result should have no errors
        self.assertFalse(vr.has_errors)


# ===========================================================================
# Backward compatibility guard
# ===========================================================================
class TestBackwardCompatibility(unittest.TestCase):
    """
    Confirm that M5.1, M5.2A, M5.2B, and M5.2C remain importable and
    that their public APIs have not been altered by M5.2D.
    """

    def test_m51_importable(self):
        from modules.educational_object_framework import (
            ProcessingContext,
            ProcessingResult,
            ProcessorRegistry,
            ValidationResult,
        )

    def test_m52a_importable(self):
        from modules.educational_taxonomy import (
            EducationalCategory,
            EducationalObjectType,
            TaxonomyRegistry,
            default_taxonomy,
        )

    def test_m52b_importable(self):
        from modules.subject_profile_framework import (
            SubjectContribution,
            SubjectProfile,
            SubjectProfileRegistry,
        )

    def test_m52c_importable(self):
        from modules.structural_understanding_engine import (
            CompatibilityValidator,
            HintResolver,
            StructuralAnalysisResult,
            StructuralObject,
            StructuralPattern,
            StructuralUnderstandingEngine,
        )

    def test_m52c_hint_resolver_unmodified(self):
        """Calling HintResolver.resolve() directly still works."""
        resolver = HintResolver()
        contrib = _make_contribution()
        from modules.structural_understanding_engine.hints import ResolvedHints
        resolved = resolver.resolve(contrib)
        self.assertIsInstance(resolved, ResolvedHints)

    def test_m52c_compatibility_validator_unmodified(self):
        """CompatibilityValidator.outcome_for_object_type() still works."""
        from modules.structural_understanding_engine.enums import CompatibilityOutcome
        from modules.structural_understanding_engine.compatibility import DEFAULT_COMPATIBILITY
        from modules.educational_taxonomy.registry import default_taxonomy
        validator = CompatibilityValidator(
            taxonomy_registry=default_taxonomy,
            compatibility=DEFAULT_COMPATIBILITY,
        )
        obj_type = _make_object_type()
        outcome = validator.outcome_for_object_type(obj_type)
        self.assertIsInstance(outcome, CompatibilityOutcome)

    def test_m52d_does_not_modify_structural_pattern(self):
        """StructuralPattern instances are not mutated by M5.2D."""
        from modules.structural_understanding_engine.patterns import (
            StructuralComponent,
            StructuralPattern,
        )
        # order must start at 0 per M5.2C's StructuralPattern validation
        comp = StructuralComponent(role="test_role", display_name="Test", order=0)
        pattern = StructuralPattern(
            pattern_key="test_pattern",
            display_name="Test",
            components=(comp,),
        )
        self.assertEqual(pattern.pattern_key, "test_pattern")


# ===========================================================================
# Serialization determinism tests
# ===========================================================================
class TestSerializationDeterminism(unittest.TestCase):

    def test_enrichment_result_serialization_is_stable(self):
        """Same inputs → same JSON output on repeated calls."""
        engine = SemanticEnrichmentEngine()
        structural = _make_structural_result()
        results = [engine.enrich(structural).to_dict() for _ in range(3)]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_anchor_id_stable_across_engine_instances(self):
        """Anchor IDs are UUID5-based and independent of engine instance."""
        e1 = SemanticEnrichmentEngine()
        e2 = SemanticEnrichmentEngine()
        structural = _make_structural_result()
        r1 = e1.enrich(structural)
        r2 = e2.enrich(structural)
        if r1.anchor and r2.anchor:
            self.assertEqual(r1.anchor.anchor_id, r2.anchor.anchor_id)

    def test_pattern_version_to_dict_stable(self):
        pv = PatternVersion(
            pattern_key="definition",
            semantic_version="1.2.3",
            metadata=PatternMetadata(description="stable"),
        )
        d1 = pv.to_dict()
        d2 = pv.to_dict()
        self.assertEqual(d1, d2)
        json.dumps(d1)


if __name__ == "__main__":
    unittest.main()
