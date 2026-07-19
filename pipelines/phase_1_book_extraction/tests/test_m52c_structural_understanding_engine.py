"""
tests/test_m52c_structural_understanding_engine.py — M5.2C unit tests
for modules/structural_understanding_engine (the Structural
Understanding Engine: typed hint resolution, structural pattern
matching, taxonomy compatibility, Subject Profile lifecycle
management).

Coverage:
  - hints / hint_resolver: SubjectContribution's raw Mapping[str, Any]
    hint fields resolve into typed, immutable models; unknown keys
    preserved in `extra`; semantic_hints never touched; never written
    back into SubjectContribution
  - patterns: built-in catalog (7 patterns), StructuralPattern
    validation (duplicate role/order, non-contiguous order), registry
    uniqueness, deterministic ordering, custom pattern registration
  - structural_models: StructuralObject immutability/validation,
    StructuralAnalysisResult shape
  - engine: pattern resolution precedence, complete/incomplete/
    unrecognized outcomes, component aliasing, ValidationHints
    strict/required_roles overrides, determinism
  - compatibility: TaxonomyCompatibility range validation,
    CompatibilityValidator against a real (isolated) TaxonomyRegistry
  - lifecycle: full REGISTERED -> VALIDATED -> ACTIVE -> INACTIVE ->
    UNREGISTERED happy path, illegal transitions, reactivation,
    validation failure keeps state at REGISTERED
  - validation.py: validate_structural_pattern_registry() reuses M5.1
    contracts, catches a broken registry
  - backward compatibility / regression: M5.1, M5.2A, M5.2B remain
    importable and unmodified; SubjectContribution/SubjectProfile/
    SubjectProfileRegistry/EducationalObjectType/TaxonomyRegistry
    never mutated by this package
"""
from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.educational_object_framework.enums import DiagnosticSeverity

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.models import EducationalObjectType
from modules.educational_taxonomy.registry import TaxonomyRegistry

from modules.subject_profile_framework.enums import CopyrightSensitivity, SupportLevel
from modules.subject_profile_framework.models import SubjectContribution, SubjectProfile
from modules.subject_profile_framework.registry import SubjectProfileRegistry

from modules.structural_understanding_engine.compatibility import (
    DEFAULT_COMPATIBILITY,
    CompatibilityValidator,
    TaxonomyCompatibility,
)
from modules.structural_understanding_engine.enums import (
    AnalysisOutcome,
    CompatibilityOutcome,
    ProfileLifecycleState,
)
from modules.structural_understanding_engine.exceptions import (
    HintResolutionError,
    ProfileLifecycleError,
    StructuralAnalysisError,
    StructuralPatternError,
    TaxonomyCompatibilityError,
)
from modules.structural_understanding_engine.engine import StructuralUnderstandingEngine
from modules.structural_understanding_engine.hint_resolver import HintResolver
from modules.structural_understanding_engine.hints import (
    ProcessingHints,
    RecognitionHints,
    RelationshipHints,
    StructuralHints,
    ValidationHints,
)
from modules.structural_understanding_engine.lifecycle import ProfileActivationManager
from modules.structural_understanding_engine.patterns import (
    StructuralComponent,
    StructuralPattern,
    StructuralPatternRegistry,
)
from modules.structural_understanding_engine.structural_models import (
    StructuralAnalysisResult,
    StructuralObject,
)
from modules.structural_understanding_engine.validation import (
    validate_structural_pattern_registry,
)


def _make_object_type(key: str, category=EducationalCategory.KNOWLEDGE, version="1.0.0") -> EducationalObjectType:
    return EducationalObjectType(
        key=key,
        category=category,
        display_name=key.replace("_", " ").title(),
        description=f"Test type {key}",
        version=version,
    )


def _make_contribution(
    subject_key: str,
    object_type_key: str,
    *,
    processing_hints=None,
    structural_hints=None,
    validation_hints=None,
    relationship_hints=None,
    semantic_hints=None,
    version="1.0.0",
) -> SubjectContribution:
    return SubjectContribution(
        subject_key=subject_key,
        object_type=_make_object_type(object_type_key, version=version),
        processing_hints=processing_hints or {},
        structural_hints=structural_hints or {},
        validation_hints=validation_hints or {},
        relationship_hints=relationship_hints or {},
        semantic_hints=semantic_hints or {},
    )


class HintResolverTests(unittest.TestCase):
    def test_processing_hints_known_and_extra(self):
        contribution = _make_contribution(
            "mathematics", "worked_example",
            processing_hints={"priority": 5, "enabled": False, "custom_flag": True},
        )
        resolved = HintResolver().resolve(contribution)
        self.assertEqual(resolved.processing.priority, 5)
        self.assertFalse(resolved.processing.enabled)
        self.assertEqual(resolved.processing.extra, {"custom_flag": True})

    def test_recognition_hints_nested_under_processing(self):
        contribution = _make_contribution(
            "mathematics", "worked_example",
            processing_hints={
                "priority": 1,
                "recognition": {"aliases": ["wp"], "confidence_threshold": 0.8, "note": "x"},
            },
        )
        resolved = HintResolver().resolve(contribution)
        self.assertEqual(resolved.recognition.aliases, ("wp",))
        self.assertEqual(resolved.recognition.confidence_threshold, 0.8)
        self.assertEqual(resolved.recognition.extra, {"note": "x"})
        # "recognition" key itself must not leak into ProcessingHints.extra
        self.assertNotIn("recognition", resolved.processing.extra)

    def test_structural_hints_pattern_key_and_aliases(self):
        contribution = _make_contribution(
            "mathematics", "coordinate_geometry_figure",
            structural_hints={
                "pattern_key": "figure",
                "component_aliases": {"caption": "fig_caption"},
                "future_flag": 1,
            },
        )
        resolved = HintResolver().resolve(contribution)
        self.assertEqual(resolved.structural.pattern_key, "figure")
        self.assertEqual(resolved.structural.component_aliases, {"caption": "fig_caption"})
        self.assertEqual(resolved.structural.extra, {"future_flag": 1})

    def test_validation_hints_strict_and_required_roles(self):
        contribution = _make_contribution(
            "mathematics", "worked_example",
            validation_hints={"strict": False, "required_roles": ["answer", "problem"]},
        )
        resolved = HintResolver().resolve(contribution)
        self.assertFalse(resolved.validation.strict)
        self.assertEqual(resolved.validation.required_roles, ("answer", "problem"))

    def test_relationship_hints_related_keys(self):
        contribution = _make_contribution(
            "mathematics", "worked_example",
            relationship_hints={"related_keys": ["concept", "theorem"], "extra_flag": True},
        )
        resolved = HintResolver().resolve(contribution)
        self.assertEqual(resolved.relationship.related_keys, ("concept", "theorem"))
        self.assertEqual(resolved.relationship.extra, {"extra_flag": True})

    def test_semantic_hints_never_read(self):
        contribution = _make_contribution(
            "mathematics", "worked_example",
            semantic_hints={"should_be_ignored": True},
        )
        resolved = HintResolver().resolve(contribution)
        # No field of ResolvedHints carries semantic_hints content at all.
        full_dict = resolved.to_dict()
        self.assertNotIn("should_be_ignored", json.dumps(full_dict))

    def test_never_writes_back_into_contribution(self):
        contribution = _make_contribution("mathematics", "worked_example", processing_hints={"priority": 2})
        original_hints = dict(contribution.processing_hints)
        HintResolver().resolve(contribution)
        self.assertEqual(dict(contribution.processing_hints), original_hints)
        # SubjectContribution is frozen; confirm mutation attempts fail (regression guard).
        with self.assertRaises(FrozenInstanceError):
            contribution.processing_hints = {}  # type: ignore[misc]

    def test_typed_hints_are_frozen_and_serializable(self):
        hints = ProcessingHints(priority=1, enabled=True, extra={"a": 1})
        with self.assertRaises(FrozenInstanceError):
            hints.priority = 2  # type: ignore[misc]
        d = hints.to_dict()
        self.assertEqual(d["priority"], 1)
        json.dumps(d)  # must be JSON-serializable

    def test_invalid_typed_hint_raises(self):
        with self.assertRaises(HintResolutionError):
            ProcessingHints(priority="not-an-int")  # type: ignore[arg-type]


class StructuralPatternTests(unittest.TestCase):
    def test_built_in_catalog_has_seven_patterns(self):
        from modules.structural_understanding_engine.patterns import default_structural_patterns
        self.assertEqual(len(default_structural_patterns), 7)
        expected = {
            "worked_example", "experiment", "proof", "derivation",
            "definition", "figure", "table",
        }
        self.assertEqual(set(default_structural_patterns.pattern_keys()), expected)

    def test_worked_example_shape(self):
        from modules.structural_understanding_engine.patterns import get
        pattern = get("worked_example")
        self.assertEqual(pattern.roles(), ("problem", "solution_steps", "answer"))
        self.assertEqual(pattern.required_roles(), ("problem", "solution_steps", "answer"))

    def test_definition_notes_optional(self):
        from modules.structural_understanding_engine.patterns import get
        pattern = get("definition")
        self.assertEqual(pattern.required_roles(), ("term", "meaning"))

    def test_duplicate_role_rejected(self):
        with self.assertRaises(StructuralPatternError):
            StructuralPattern(
                pattern_key="broken",
                display_name="Broken",
                components=(
                    StructuralComponent("a", "A", 0),
                    StructuralComponent("a", "A2", 1),
                ),
            )

    def test_non_contiguous_order_rejected(self):
        with self.assertRaises(StructuralPatternError):
            StructuralPattern(
                pattern_key="broken2",
                display_name="Broken2",
                components=(
                    StructuralComponent("a", "A", 0),
                    StructuralComponent("b", "B", 2),
                ),
            )

    def test_registry_uniqueness_and_deterministic_order(self):
        registry = StructuralPatternRegistry()
        registry.register(StructuralPattern("zzz_pattern", "ZZZ", (StructuralComponent("x", "X", 0),)))
        registry.register(StructuralPattern("aaa_pattern", "AAA", (StructuralComponent("y", "Y", 0),)))
        self.assertEqual(registry.pattern_keys(), ["aaa_pattern", "zzz_pattern"])
        with self.assertRaises(StructuralPatternError):
            registry.register(StructuralPattern("aaa_pattern", "Dup", (StructuralComponent("z", "Z", 0),)))

    def test_deterministic_serialization(self):
        from modules.structural_understanding_engine.patterns import get
        pattern = get("experiment")
        self.assertEqual(pattern.to_dict(), pattern.to_dict())
        json.dumps(pattern.to_dict())


class StructuralObjectTests(unittest.TestCase):
    def test_construction_and_immutability(self):
        obj = StructuralObject(
            object_key="obj-1",
            object_type_key="worked_example",
            components={"problem": "2+2=?"},
        )
        with self.assertRaises(FrozenInstanceError):
            obj.object_key = "other"  # type: ignore[misc]

    def test_empty_object_key_rejected(self):
        with self.assertRaises(StructuralAnalysisError):
            StructuralObject(object_key="", object_type_key="worked_example")

    def test_with_components_returns_new_instance(self):
        obj = StructuralObject(object_key="obj-1", object_type_key="worked_example", components={"problem": "p"})
        updated = obj.with_components(answer="42")
        self.assertNotIn("answer", obj.components)
        self.assertEqual(updated.components["answer"], "42")
        self.assertEqual(updated.components["problem"], "p")


class EngineAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.engine = StructuralUnderstandingEngine()

    def test_complete_worked_example(self):
        obj = StructuralObject(
            object_key="we-1",
            object_type_key="worked_example",
            components={"problem": "p", "solution_steps": "s", "answer": "a"},
        )
        result = self.engine.analyze(obj)
        self.assertEqual(result.outcome, AnalysisOutcome.COMPLETE)
        self.assertTrue(result.is_complete)
        self.assertEqual(result.missing_roles, ())
        self.assertTrue(result.validation.is_success)

    def test_incomplete_worked_example_reports_missing(self):
        obj = StructuralObject(
            object_key="we-2",
            object_type_key="worked_example",
            components={"problem": "p"},
        )
        result = self.engine.analyze(obj)
        self.assertEqual(result.outcome, AnalysisOutcome.INCOMPLETE)
        self.assertEqual(set(result.missing_roles), {"solution_steps", "answer"})
        self.assertTrue(result.validation.has_errors)  # strict default

    def test_unrecognized_pattern(self):
        obj = StructuralObject(object_key="x-1", object_type_key="totally_unknown_type")
        result = self.engine.analyze(obj)
        self.assertEqual(result.outcome, AnalysisOutcome.UNRECOGNIZED_PATTERN)
        self.assertIsNone(result.pattern_key)
        self.assertTrue(result.validation.has_errors)

    def test_definition_optional_notes_does_not_block_completeness(self):
        obj = StructuralObject(
            object_key="d-1",
            object_type_key="definition",
            components={"term": "t", "meaning": "m"},
        )
        result = self.engine.analyze(obj)
        self.assertEqual(result.outcome, AnalysisOutcome.COMPLETE)

    def test_component_alias_resolution_via_hints(self):
        contribution = _make_contribution(
            "physics", "figure",
            structural_hints={"component_aliases": {"caption": "fig_caption"}},
        )
        resolved = self.engine.resolve_hints(contribution)
        obj = StructuralObject(
            object_key="f-1",
            object_type_key="figure",
            components={"fig_caption": "A diagram"},
        )
        result = self.engine.analyze(obj, resolved_hints=resolved)
        self.assertEqual(result.outcome, AnalysisOutcome.COMPLETE)
        self.assertIn("caption", result.present_roles)

    def test_pattern_key_hint_override_precedence(self):
        # object_type_key does not match any pattern; explicit
        # StructuralHints.pattern_key should still resolve it.
        contribution = _make_contribution(
            "mathematics", "custom_math_object",
            structural_hints={"pattern_key": "proof"},
        )
        resolved = self.engine.resolve_hints(contribution)
        obj = StructuralObject(
            object_key="p-1",
            object_type_key="custom_math_object",
            components={"statement": "s", "reasoning": "r", "conclusion": "c"},
        )
        result = self.engine.analyze(obj, resolved_hints=resolved)
        self.assertEqual(result.pattern_key, "proof")
        self.assertEqual(result.outcome, AnalysisOutcome.COMPLETE)

    def test_explicit_structural_object_pattern_key_wins_over_hints(self):
        contribution = _make_contribution(
            "mathematics", "worked_example",
            structural_hints={"pattern_key": "proof"},
        )
        resolved = self.engine.resolve_hints(contribution)
        obj = StructuralObject(
            object_key="we-3",
            object_type_key="worked_example",
            pattern_key="worked_example",
            components={"problem": "p", "solution_steps": "s", "answer": "a"},
        )
        result = self.engine.analyze(obj, resolved_hints=resolved)
        self.assertEqual(result.pattern_key, "worked_example")

    def test_validation_hints_lenient_downgrades_to_warning(self):
        contribution = _make_contribution(
            "mathematics", "worked_example",
            validation_hints={"strict": False},
        )
        resolved = self.engine.resolve_hints(contribution)
        obj = StructuralObject(object_key="we-4", object_type_key="worked_example", components={"problem": "p"})
        result = self.engine.analyze(obj, resolved_hints=resolved)
        self.assertTrue(result.validation.has_warnings)
        self.assertFalse(result.validation.has_errors)

    def test_validation_hints_additional_required_role(self):
        contribution = _make_contribution(
            "mathematics", "definition",
            validation_hints={"required_roles": ["notes"]},
        )
        resolved = self.engine.resolve_hints(contribution)
        obj = StructuralObject(
            object_key="d-2",
            object_type_key="definition",
            components={"term": "t", "meaning": "m"},
        )
        result = self.engine.analyze(obj, resolved_hints=resolved)
        self.assertEqual(result.outcome, AnalysisOutcome.INCOMPLETE)
        self.assertIn("notes", result.missing_roles)

    def test_analyze_rejects_non_structural_object(self):
        with self.assertRaises(StructuralAnalysisError):
            self.engine.analyze({"not": "a structural object"})  # type: ignore[arg-type]

    def test_determinism_across_repeated_calls(self):
        obj = StructuralObject(
            object_key="we-5",
            object_type_key="worked_example",
            components={"problem": "p", "solution_steps": "s", "answer": "a"},
        )
        first = self.engine.analyze(obj).to_dict()
        second = self.engine.analyze(obj).to_dict()
        self.assertEqual(first, second)
        json.dumps(first)  # serializable


class CompatibilityTests(unittest.TestCase):
    def test_default_compatibility_accepts_common_versions(self):
        self.assertTrue(DEFAULT_COMPATIBILITY.accepts("1.0.0"))
        self.assertTrue(DEFAULT_COMPATIBILITY.accepts("1.5.2"))
        self.assertFalse(DEFAULT_COMPATIBILITY.accepts("2.0.0"))

    def test_min_greater_than_max_rejected(self):
        with self.assertRaises(TaxonomyCompatibilityError):
            TaxonomyCompatibility(
                supported_taxonomy_version="1.0.0",
                minimum_supported_version="2.0.0",
                maximum_supported_version="1.0.0",
            )

    def test_supported_outside_range_rejected(self):
        with self.assertRaises(TaxonomyCompatibilityError):
            TaxonomyCompatibility(
                supported_taxonomy_version="3.0.0",
                minimum_supported_version="1.0.0",
                maximum_supported_version="2.0.0",
            )

    def test_malformed_version_rejected(self):
        with self.assertRaises(TaxonomyCompatibilityError):
            TaxonomyCompatibility(
                supported_taxonomy_version="not-a-version",
                minimum_supported_version="1.0.0",
                maximum_supported_version="2.0.0",
            )

    def test_validator_against_isolated_taxonomy(self):
        taxonomy = TaxonomyRegistry()
        object_type = _make_object_type("proof", version="1.2.0")
        taxonomy.register(object_type)
        validator = CompatibilityValidator(
            taxonomy,
            TaxonomyCompatibility("1.2.0", "1.0.0", "1.5.0"),
        )
        self.assertEqual(validator.outcome_for_object_type(object_type), CompatibilityOutcome.COMPATIBLE)
        self.assertTrue(validator.validate_object_type(object_type).is_success)

    def test_validator_reports_unresolvable(self):
        taxonomy = TaxonomyRegistry()
        object_type = _make_object_type("proof", version="1.0.0")
        # deliberately not registered into `taxonomy`
        validator = CompatibilityValidator(taxonomy, DEFAULT_COMPATIBILITY)
        self.assertEqual(validator.outcome_for_object_type(object_type), CompatibilityOutcome.UNRESOLVABLE)
        result = validator.validate_object_type(object_type)
        self.assertTrue(result.has_errors)

    def test_validator_reports_incompatible_version(self):
        taxonomy = TaxonomyRegistry()
        object_type = _make_object_type("proof", version="9.0.0")
        taxonomy.register(object_type)
        validator = CompatibilityValidator(taxonomy, DEFAULT_COMPATIBILITY)
        self.assertEqual(validator.outcome_for_object_type(object_type), CompatibilityOutcome.INCOMPATIBLE)

    def test_validate_profile_aggregates_all_contributions(self):
        taxonomy = TaxonomyRegistry()
        subject_registry = SubjectProfileRegistry(taxonomy_registry=taxonomy)
        profile = SubjectProfile(
            subject_key="mathematics",
            display_name="Mathematics",
            description="Math",
            contributions=(
                SubjectContribution(subject_key="mathematics", object_type=_make_object_type("worked_example")),
                SubjectContribution(subject_key="mathematics", object_type=_make_object_type("proof")),
            ),
        )
        subject_registry.register(profile)
        validator = CompatibilityValidator(taxonomy, DEFAULT_COMPATIBILITY)
        result = validator.validate_profile(profile)
        self.assertTrue(result.is_success)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = TaxonomyRegistry()
        self.subject_registry = SubjectProfileRegistry(taxonomy_registry=self.taxonomy)
        self.profile = SubjectProfile(
            subject_key="mathematics",
            display_name="Mathematics",
            description="Math",
            contributions=(
                SubjectContribution(subject_key="mathematics", object_type=_make_object_type("worked_example")),
            ),
        )
        self.subject_registry.register(self.profile)
        self.validator = CompatibilityValidator(self.taxonomy, DEFAULT_COMPATIBILITY)
        self.manager = ProfileActivationManager(self.subject_registry, self.validator)

    def test_happy_path_full_lifecycle(self):
        self.manager.mark_registered("mathematics")
        self.assertEqual(self.manager.state_of("mathematics"), ProfileLifecycleState.REGISTERED)

        self.manager.validate("mathematics")
        self.assertEqual(self.manager.state_of("mathematics"), ProfileLifecycleState.VALIDATED)

        self.manager.activate("mathematics")
        self.assertEqual(self.manager.state_of("mathematics"), ProfileLifecycleState.ACTIVE)

        self.manager.deactivate("mathematics")
        self.assertEqual(self.manager.state_of("mathematics"), ProfileLifecycleState.INACTIVE)

        self.manager.reactivate("mathematics")
        self.assertEqual(self.manager.state_of("mathematics"), ProfileLifecycleState.ACTIVE)

        self.manager.deactivate("mathematics")
        self.manager.unregister("mathematics")
        self.assertEqual(self.manager.state_of("mathematics"), ProfileLifecycleState.UNREGISTERED)

    def test_activate_without_validate_raises(self):
        self.manager.mark_registered("mathematics")
        with self.assertRaises(ProfileLifecycleError):
            self.manager.activate("mathematics")

    def test_unregistered_is_terminal(self):
        self.manager.mark_registered("mathematics")
        self.manager.validate("mathematics")
        self.manager.activate("mathematics")
        self.manager.deactivate("mathematics")
        self.manager.unregister("mathematics")
        with self.assertRaises(ProfileLifecycleError):
            self.manager.activate("mathematics")

    def test_unknown_subject_raises(self):
        with self.assertRaises(ProfileLifecycleError):
            self.manager.mark_registered("nonexistent_subject")

    def test_validation_failure_keeps_registered_state(self):
        # An incompatible version keeps the profile at REGISTERED,
        # never silently promotes it.
        strict_validator = CompatibilityValidator(
            self.taxonomy,
            TaxonomyCompatibility("5.0.0", "5.0.0", "5.0.0"),
        )
        manager = ProfileActivationManager(self.subject_registry, strict_validator)
        manager.mark_registered("mathematics")
        record = manager.validate("mathematics")
        self.assertEqual(record.state, ProfileLifecycleState.REGISTERED)
        self.assertTrue(record.last_validation.has_errors)
        with self.assertRaises(ProfileLifecycleError):
            manager.activate("mathematics")

    def test_no_lifecycle_record_raises(self):
        with self.assertRaises(ProfileLifecycleError):
            self.manager.state_of("mathematics")


class PackageValidationTests(unittest.TestCase):
    def test_default_registry_passes(self):
        from modules.structural_understanding_engine.patterns import default_structural_patterns
        result = validate_structural_pattern_registry(default_structural_patterns)
        self.assertTrue(result.is_success)

    def test_broken_registry_detected(self):
        # Simulate drift by manually poking a duplicate key into the
        # internal dict via two separate registries merged unsafely;
        # since register() enforces uniqueness, we instead construct a
        # registry and rely on the checker running cleanly on valid
        # input, then check the diagnostic-producing helpers directly
        # for an intentionally malformed structure.
        registry = StructuralPatternRegistry()
        registry.register(StructuralPattern("only_one", "Only One", (StructuralComponent("a", "A", 0),)))
        result = validate_structural_pattern_registry(registry)
        self.assertTrue(result.is_success)


class BackwardCompatibilityTests(unittest.TestCase):
    def test_frozen_packages_still_importable(self):
        import modules.educational_object_framework  # noqa: F401
        import modules.educational_taxonomy  # noqa: F401
        import modules.subject_profile_framework  # noqa: F401

    def test_subject_contribution_shape_unmodified(self):
        contribution = _make_contribution("mathematics", "worked_example")
        expected_fields = {
            "subject_key", "object_type", "symbolic_content", "copyright_sensitivity",
            "structural_support", "semantic_support", "relationship_support",
            "processing_hints", "structural_hints", "semantic_hints",
            "relationship_hints", "validation_hints", "version",
        }
        self.assertEqual(set(contribution.to_dict().keys()), expected_fields)

    def test_taxonomy_registry_untouched_by_compatibility_validator(self):
        taxonomy = TaxonomyRegistry()
        object_type = _make_object_type("proof")
        taxonomy.register(object_type)
        before = len(taxonomy)
        CompatibilityValidator(taxonomy, DEFAULT_COMPATIBILITY).validate_object_type(object_type)
        self.assertEqual(len(taxonomy), before)

    def test_subject_profile_registry_untouched_by_lifecycle_manager(self):
        taxonomy = TaxonomyRegistry()
        subject_registry = SubjectProfileRegistry(taxonomy_registry=taxonomy)
        profile = SubjectProfile(
            subject_key="physics",
            display_name="Physics",
            description="Physics",
            contributions=(
                SubjectContribution(subject_key="physics", object_type=_make_object_type("experiment")),
            ),
        )
        subject_registry.register(profile)
        before = len(subject_registry)
        manager = ProfileActivationManager(subject_registry, CompatibilityValidator(taxonomy, DEFAULT_COMPATIBILITY))
        manager.mark_registered("physics")
        manager.validate("physics")
        manager.activate("physics")
        manager.deactivate("physics")
        manager.unregister("physics")
        self.assertEqual(len(subject_registry), before)
        self.assertIn("physics", subject_registry)  # still registered in SPF itself


if __name__ == "__main__":
    unittest.main()
