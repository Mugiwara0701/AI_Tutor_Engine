"""
tests/test_m52b_subject_profile_extension_framework.py — M5.2B unit
tests for modules/subject_profile_framework (the Subject Profile
Extension Framework: SubjectContribution, SubjectProfile,
SubjectProfileRegistry, and the validation helpers built on top of the
frozen M5.2A taxonomy).

Coverage:
  - enums: CopyrightSensitivity / SupportLevel membership,
    support_at_least() ordering
  - exceptions: hierarchy relationships
  - models: SubjectContribution / SubjectProfile validation,
    immutability, determinism of to_dict(), duplicate-identifier
    rejection within a single profile, to_dict()/from_dict()
    round-tripping
  - registry: profile registration, extension of an isolated
    TaxonomyRegistry, duplicate subject_key / duplicate object
    identifier rejection (within a profile and across profiles),
    atomic rollback on partial registration failure, unregister(),
    deterministic ordering (independent of registration/authoring
    order), capability-based queries (by category, symbolic content,
    copyright sensitivity, structural/semantic/relationship support)
  - validation: validate_subject_profile_registry() reuses M5.1's
    ValidationResult / ValidationDiagnostic / DiagnosticSeverity
    contracts; catches an intentionally-broken registry's
    inconsistencies
  - extensibility / backward compatibility: registering a new subject
    profile does not touch any pre-existing taxonomy entry or any
    other subject's contributions
  - regression: modules.educational_taxonomy (M5.2A) and
    modules.educational_object_framework (M5.1) remain importable and
    untouched by this package
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import ValidationResult

from modules.educational_taxonomy import catalog as taxonomy_catalog
from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.models import EducationalObjectType
from modules.educational_taxonomy.registry import TaxonomyRegistry

from modules.subject_profile_framework.enums import (
    CopyrightSensitivity,
    SupportLevel,
    support_at_least,
)
from modules.subject_profile_framework.exceptions import (
    SubjectContributionValidationError,
    SubjectProfileFrameworkError,
    SubjectProfileLookupError,
    SubjectProfileRegistrationError,
    TaxonomyExtensionError,
)
from modules.subject_profile_framework.models import (
    DEFAULT_CONTRIBUTION_VERSION,
    DEFAULT_PROFILE_VERSION,
    SubjectContribution,
    SubjectProfile,
)
from modules.subject_profile_framework.registry import SubjectProfileRegistry
from modules.subject_profile_framework.validation import validate_subject_profile_registry


def _isolated_taxonomy() -> TaxonomyRegistry:
    """A fresh TaxonomyRegistry seeded with the real built-in catalog
    — mirrors test_m52a's own isolation pattern so these tests never
    touch the shared, process-wide default_taxonomy / default_subject_
    profiles singletons."""
    registry = TaxonomyRegistry()
    taxonomy_catalog.seed(registry)
    return registry


def _math_contribution(
    key: str = "coordinate_geometry_figure",
    subject_key: str = "mathematics",
    aliases: tuple = ("coord_geo_figure",),
    **overrides,
) -> SubjectContribution:
    object_type_aliases = aliases if key == "coordinate_geometry_figure" else ()
    defaults = dict(
        subject_key=subject_key,
        object_type=EducationalObjectType(
            key=key,
            category=EducationalCategory.VISUAL,
            display_name="Coordinate Geometry Figure",
            description="A figure plotting points, lines, or curves on a coordinate plane.",
            aliases=object_type_aliases,
        ),
        symbolic_content=True,
        copyright_sensitivity=CopyrightSensitivity.LOW,
        structural_support=SupportLevel.PARTIAL,
        semantic_support=SupportLevel.FULL,
        relationship_support=SupportLevel.NONE,
        processing_hints={"expects_axes": True},
    )
    defaults.update(overrides)
    return SubjectContribution(**defaults)


def _math_profile(contributions=None) -> SubjectProfile:
    if contributions is None:
        contributions = (_math_contribution(),)
    return SubjectProfile(
        subject_key="mathematics",
        display_name="Mathematics",
        description="Subject profile for Mathematics educational objects.",
        contributions=tuple(contributions),
    )


# ---------------------------------------------------------------------------
# enums
# ---------------------------------------------------------------------------

class TestEnums(unittest.TestCase):
    def test_copyright_sensitivity_values(self) -> None:
        self.assertEqual(
            {m.value for m in CopyrightSensitivity},
            {"none", "low", "moderate", "high"},
        )

    def test_support_level_values(self) -> None:
        self.assertEqual({m.value for m in SupportLevel}, {"none", "partial", "full"})

    def test_support_at_least_ordering(self) -> None:
        self.assertTrue(support_at_least(SupportLevel.FULL, SupportLevel.NONE))
        self.assertTrue(support_at_least(SupportLevel.FULL, SupportLevel.FULL))
        self.assertTrue(support_at_least(SupportLevel.PARTIAL, SupportLevel.PARTIAL))
        self.assertFalse(support_at_least(SupportLevel.NONE, SupportLevel.PARTIAL))
        self.assertFalse(support_at_least(SupportLevel.PARTIAL, SupportLevel.FULL))

    def test_are_str_enums(self) -> None:
        self.assertEqual(CopyrightSensitivity.LOW, "low")
        self.assertEqual(SupportLevel.FULL, "full")


# ---------------------------------------------------------------------------
# exceptions
# ---------------------------------------------------------------------------

class TestExceptionHierarchy(unittest.TestCase):
    def test_all_subclass_base(self) -> None:
        for exc_type in (
            SubjectContributionValidationError,
            SubjectProfileRegistrationError,
            SubjectProfileLookupError,
            TaxonomyExtensionError,
        ):
            self.assertTrue(issubclass(exc_type, SubjectProfileFrameworkError))

    def test_lookup_error_is_also_lookup_error(self) -> None:
        self.assertTrue(issubclass(SubjectProfileLookupError, LookupError))

    def test_base_is_exception(self) -> None:
        self.assertTrue(issubclass(SubjectProfileFrameworkError, Exception))


# ---------------------------------------------------------------------------
# models — SubjectContribution
# ---------------------------------------------------------------------------

class TestSubjectContribution(unittest.TestCase):
    def test_valid_construction(self) -> None:
        contribution = _math_contribution()
        self.assertEqual(contribution.subject_key, "mathematics")
        self.assertEqual(contribution.object_type.key, "coordinate_geometry_figure")
        self.assertTrue(contribution.symbolic_content)
        self.assertEqual(contribution.version, DEFAULT_CONTRIBUTION_VERSION)

    def test_immutable(self) -> None:
        contribution = _math_contribution()
        with self.assertRaises(Exception):
            contribution.symbolic_content = False  # type: ignore[misc]

    def test_hints_are_frozen_copies(self) -> None:
        hints = {"a": 1}
        contribution = _math_contribution(processing_hints=hints)
        hints["a"] = 2
        self.assertEqual(contribution.processing_hints["a"], 1)

    def test_rejects_invalid_subject_key(self) -> None:
        with self.assertRaises(SubjectContributionValidationError):
            _math_contribution(subject_key="Mathematics")
        with self.assertRaises(SubjectContributionValidationError):
            _math_contribution(subject_key="")

    def test_rejects_non_educational_object_type(self) -> None:
        with self.assertRaises(SubjectContributionValidationError):
            SubjectContribution(subject_key="mathematics", object_type="not-a-type")  # type: ignore[arg-type]

    def test_rejects_wrong_enum_type(self) -> None:
        with self.assertRaises(SubjectContributionValidationError):
            _math_contribution(copyright_sensitivity="low")  # type: ignore[arg-type]

    def test_rejects_non_bool_symbolic_content(self) -> None:
        with self.assertRaises(SubjectContributionValidationError):
            _math_contribution(symbolic_content="yes")  # type: ignore[arg-type]

    def test_to_dict_is_deterministic_and_json_safe(self) -> None:
        contribution = _math_contribution()
        first = contribution.to_dict()
        second = contribution.to_dict()
        self.assertEqual(first, second)
        json.dumps(first)  # must not raise

    def test_to_dict_from_dict_roundtrip(self) -> None:
        contribution = _math_contribution()
        restored = SubjectContribution.from_dict(contribution.to_dict())
        self.assertEqual(contribution.to_dict(), restored.to_dict())

    def test_from_dict_missing_field_raises(self) -> None:
        data = _math_contribution().to_dict()
        del data["subject_key"]
        with self.assertRaises(SubjectContributionValidationError):
            SubjectContribution.from_dict(data)


# ---------------------------------------------------------------------------
# models — SubjectProfile
# ---------------------------------------------------------------------------

class TestSubjectProfile(unittest.TestCase):
    def test_valid_construction(self) -> None:
        profile = _math_profile()
        self.assertEqual(profile.subject_key, "mathematics")
        self.assertEqual(len(profile.contributions), 1)
        self.assertEqual(profile.version, DEFAULT_PROFILE_VERSION)

    def test_rejects_mismatched_contribution_subject_key(self) -> None:
        mismatched = _math_contribution(subject_key="physics")
        with self.assertRaises(SubjectContributionValidationError):
            _math_profile(contributions=(mismatched,))

    def test_rejects_duplicate_object_identifier_within_profile(self) -> None:
        one = _math_contribution(key="algebraic_identity")
        two = SubjectContribution(
            subject_key="mathematics",
            object_type=EducationalObjectType(
                key="number_line", category=EducationalCategory.VISUAL,
                display_name="Number Line", description="A visual number line.",
                aliases=("algebraic_identity",),  # collides with `one`'s key
            ),
        )
        with self.assertRaises(SubjectContributionValidationError):
            _math_profile(contributions=(one, two))

    def test_rejects_invalid_subject_key(self) -> None:
        with self.assertRaises(SubjectContributionValidationError):
            SubjectProfile(subject_key="1math", display_name="Math", description="x")

    def test_to_dict_orders_contributions_deterministically_regardless_of_authoring_order(self) -> None:
        a = _math_contribution(key="zzz_last", subject_key="mathematics")
        b = _math_contribution(key="aaa_first", subject_key="mathematics")
        profile_1 = _math_profile(contributions=(a, b))
        profile_2 = _math_profile(contributions=(b, a))
        self.assertEqual(profile_1.to_dict(), profile_2.to_dict())
        keys_in_order = [c["object_type"]["key"] for c in profile_1.to_dict()["contributions"]]
        self.assertEqual(keys_in_order, sorted(keys_in_order))

    def test_to_dict_from_dict_roundtrip(self) -> None:
        profile = _math_profile()
        restored = SubjectProfile.from_dict(profile.to_dict())
        self.assertEqual(profile.to_dict(), restored.to_dict())

    def test_immutable(self) -> None:
        profile = _math_profile()
        with self.assertRaises(Exception):
            profile.display_name = "Something Else"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# registry — registration / extension of the (isolated) taxonomy
# ---------------------------------------------------------------------------

class TestSubjectProfileRegistryRegistration(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = _isolated_taxonomy()
        self.registry = SubjectProfileRegistry(taxonomy_registry=self.taxonomy)

    def test_register_extends_the_taxonomy(self) -> None:
        profile = _math_profile()
        self.registry.register(profile)
        self.assertIn("coordinate_geometry_figure", self.taxonomy)
        self.assertIn("coord_geo_figure", self.taxonomy)  # alias resolves too
        self.assertIn("mathematics", self.registry)

    def test_register_does_not_touch_preexisting_entries(self) -> None:
        before = {key: self.taxonomy.get(key).to_dict() for key in self.taxonomy.keys()}
        self.registry.register(_math_profile())
        for key, snapshot in before.items():
            self.assertEqual(self.taxonomy.get(key).to_dict(), snapshot)

    def test_duplicate_subject_key_rejected(self) -> None:
        self.registry.register(_math_profile())
        with self.assertRaises(SubjectProfileRegistrationError):
            self.registry.register(_math_profile())

    def test_duplicate_object_identifier_across_profiles_rejected(self) -> None:
        self.registry.register(_math_profile())
        colliding = SubjectProfile(
            subject_key="physics",
            display_name="Physics",
            description="Subject profile for Physics.",
            contributions=(
                SubjectContribution(
                    subject_key="physics",
                    object_type=EducationalObjectType(
                        key="circuit_diagram", category=EducationalCategory.VISUAL,
                        display_name="Circuit Diagram", description="A circuit schematic.",
                        aliases=("coordinate_geometry_figure",),  # collides with Math's key
                    ),
                ),
            ),
        )
        with self.assertRaises(SubjectProfileRegistrationError):
            self.registry.register(colliding)
        # the colliding profile must not have been partially registered
        self.assertNotIn("physics", self.registry)
        self.assertNotIn("circuit_diagram", self.taxonomy)

    def test_collision_with_builtin_taxonomy_entry_rejected_and_rolled_back(self) -> None:
        colliding = SubjectProfile(
            subject_key="mathematics",
            display_name="Mathematics",
            description="Attempts to redefine a builtin type.",
            contributions=(
                _math_contribution(key="algebraic_identity"),
                SubjectContribution(
                    subject_key="mathematics",
                    object_type=EducationalObjectType(
                        key="concept",  # built-in taxonomy key — must collide
                        category=EducationalCategory.KNOWLEDGE,
                        display_name="Concept", description="Collides with the builtin.",
                    ),
                ),
            ),
        )
        with self.assertRaises(TaxonomyExtensionError):
            self.registry.register(colliding)
        # rollback: the first contribution must NOT remain registered
        self.assertNotIn("algebraic_identity", self.taxonomy)
        self.assertNotIn("mathematics", self.registry)

    def test_unregister_removes_taxonomy_entries_and_frees_identifiers(self) -> None:
        self.registry.register(_math_profile())
        self.registry.unregister("mathematics")
        self.assertNotIn("mathematics", self.registry)
        self.assertNotIn("coordinate_geometry_figure", self.taxonomy)
        self.assertNotIn("coord_geo_figure", self.taxonomy)
        # identifier is free again for a new registration
        self.registry.register(_math_profile())

    def test_unregister_unknown_subject_raises(self) -> None:
        with self.assertRaises(SubjectProfileLookupError):
            self.registry.unregister("nonexistent_subject")

    def test_get_unknown_subject_raises(self) -> None:
        with self.assertRaises(SubjectProfileLookupError):
            self.registry.get("nonexistent_subject")

    def test_register_non_subject_profile_raises(self) -> None:
        with self.assertRaises(SubjectProfileRegistrationError):
            self.registry.register("not-a-profile")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# registry — deterministic ordering
# ---------------------------------------------------------------------------

class TestDeterministicOrdering(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = _isolated_taxonomy()
        self.registry = SubjectProfileRegistry(taxonomy_registry=self.taxonomy)

    def test_all_profiles_ordered_by_subject_key_regardless_of_registration_order(self) -> None:
        physics = SubjectProfile(
            subject_key="physics", display_name="Physics", description="x",
            contributions=(
                SubjectContribution(
                    subject_key="physics",
                    object_type=EducationalObjectType(
                        key="force_diagram", category=EducationalCategory.VISUAL,
                        display_name="Force Diagram", description="x",
                    ),
                ),
            ),
        )
        self.registry.register(physics)
        self.registry.register(_math_profile())  # "mathematics" registered second
        self.assertEqual(self.registry.subject_keys(), ["mathematics", "physics"])
        self.assertEqual([p.subject_key for p in self.registry.all_profiles()], ["mathematics", "physics"])

    def test_all_contributions_ordered_deterministically(self) -> None:
        self.registry.register(_math_profile(contributions=(
            _math_contribution(key="zzz_last"),
            _math_contribution(key="aaa_first"),
        )))
        keys = [c.object_type.key for c in self.registry.all_contributions()]
        self.assertEqual(keys, sorted(keys))


# ---------------------------------------------------------------------------
# registry — capability-based queries
# ---------------------------------------------------------------------------

class TestCapabilityQueries(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = _isolated_taxonomy()
        self.registry = SubjectProfileRegistry(taxonomy_registry=self.taxonomy)
        self.registry.register(_math_profile(contributions=(
            _math_contribution(
                key="algebraic_identity", symbolic_content=True,
                copyright_sensitivity=CopyrightSensitivity.HIGH,
                structural_support=SupportLevel.FULL,
                semantic_support=SupportLevel.PARTIAL,
                relationship_support=SupportLevel.NONE,
            ),
            SubjectContribution(
                subject_key="mathematics",
                object_type=EducationalObjectType(
                    key="number_line", category=EducationalCategory.VISUAL,
                    display_name="Number Line", description="x",
                ),
                symbolic_content=False,
                copyright_sensitivity=CopyrightSensitivity.NONE,
                structural_support=SupportLevel.NONE,
                semantic_support=SupportLevel.NONE,
                relationship_support=SupportLevel.NONE,
            ),
        )))

    def test_contributions_by_category(self) -> None:
        visual = self.registry.contributions_by_category(EducationalCategory.VISUAL)
        self.assertEqual(len(visual), 2)
        knowledge = self.registry.contributions_by_category(EducationalCategory.KNOWLEDGE)
        self.assertEqual(knowledge, [])

    def test_contributions_with_symbolic_content(self) -> None:
        symbolic = self.registry.contributions_with_symbolic_content()
        self.assertEqual([c.object_type.key for c in symbolic], ["algebraic_identity"])

    def test_contributions_by_copyright_sensitivity(self) -> None:
        high = self.registry.contributions_by_copyright_sensitivity(CopyrightSensitivity.HIGH)
        self.assertEqual([c.object_type.key for c in high], ["algebraic_identity"])
        none_sensitivity = self.registry.contributions_by_copyright_sensitivity(CopyrightSensitivity.NONE)
        self.assertEqual([c.object_type.key for c in none_sensitivity], ["number_line"])

    def test_contributions_supporting_structural(self) -> None:
        full_support = self.registry.contributions_supporting("structural", minimum=SupportLevel.FULL)
        self.assertEqual([c.object_type.key for c in full_support], ["algebraic_identity"])
        any_support = self.registry.contributions_supporting("structural", minimum=SupportLevel.PARTIAL)
        self.assertEqual([c.object_type.key for c in any_support], ["algebraic_identity"])

    def test_contributions_supporting_unknown_capability_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.contributions_supporting("nonexistent_capability")


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

class TestValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = _isolated_taxonomy()
        self.registry = SubjectProfileRegistry(taxonomy_registry=self.taxonomy)

    def test_success_reuses_m51_validation_result(self) -> None:
        self.registry.register(_math_profile())
        result = validate_subject_profile_registry(self.registry)
        self.assertIsInstance(result, ValidationResult)
        self.assertTrue(result.is_success)
        self.assertFalse(result.has_errors)

    def test_empty_registry_is_success(self) -> None:
        result = validate_subject_profile_registry(self.registry)
        self.assertTrue(result.is_success)

    def test_taxonomy_drift_detected(self) -> None:
        self.registry.register(_math_profile())
        # Simulate external drift: unregister directly from the
        # taxonomy without going through SubjectProfileRegistry.
        self.taxonomy.unregister("coordinate_geometry_figure")
        result = validate_subject_profile_registry(self.registry)
        self.assertTrue(result.has_errors)
        self.assertTrue(any(d.code == "subject_profile.taxonomy_drift" for d in result.errors()))

    def test_non_semver_version_produces_warning(self) -> None:
        profile = SubjectProfile(
            subject_key="mathematics", display_name="Mathematics", description="x",
            contributions=(_math_contribution(),), version="not-a-version",
        )
        self.registry.register(profile)
        result = validate_subject_profile_registry(self.registry)
        self.assertTrue(result.has_warnings)
        self.assertTrue(any(d.code == "subject_profile.non_semver_profile_version" for d in result.warnings()))

    def test_diagnostics_carry_severity_code_and_message(self) -> None:
        self.registry.register(_math_profile())
        self.taxonomy.unregister("coordinate_geometry_figure")
        result = validate_subject_profile_registry(self.registry)
        for diagnostic in result.diagnostics:
            self.assertIsInstance(diagnostic.severity, DiagnosticSeverity)
            self.assertTrue(diagnostic.code)
            self.assertTrue(diagnostic.message)


# ---------------------------------------------------------------------------
# extensibility / backward compatibility
# ---------------------------------------------------------------------------

class TestExtensibilityAndBackwardCompatibility(unittest.TestCase):
    def test_multiple_subjects_extend_independently(self) -> None:
        taxonomy = _isolated_taxonomy()
        registry = SubjectProfileRegistry(taxonomy_registry=taxonomy)

        registry.register(_math_profile())
        physics = SubjectProfile(
            subject_key="physics", display_name="Physics", description="x",
            contributions=(
                SubjectContribution(
                    subject_key="physics",
                    object_type=EducationalObjectType(
                        key="force_diagram", category=EducationalCategory.VISUAL,
                        display_name="Force Diagram", description="x",
                    ),
                ),
            ),
        )
        registry.register(physics)

        self.assertIn("mathematics", registry)
        self.assertIn("physics", registry)
        self.assertIn("coordinate_geometry_figure", taxonomy)
        self.assertIn("force_diagram", taxonomy)

    def test_default_taxonomy_and_registry_singletons_roundtrip_cleanly(self) -> None:
        # Uses the real, shared default_taxonomy / default_subject_profiles
        # singletons — mirrors test_m52a's own singleton-registration test —
        # and always cleans up after itself.
        from modules.subject_profile_framework.registry import (
            default_subject_profiles,
            register,
            unregister,
        )

        profile = SubjectProfile(
            subject_key="temporary_m52b_test_subject",
            display_name="Temporary",
            description="Registered and removed within this test.",
            contributions=(
                SubjectContribution(
                    subject_key="temporary_m52b_test_subject",
                    object_type=EducationalObjectType(
                        key="temporary_m52b_test_object_type",
                        category=EducationalCategory.LEARNING,
                        display_name="Temporary", description="x",
                    ),
                ),
            ),
        )
        register(profile)
        try:
            self.assertIn("temporary_m52b_test_subject", default_subject_profiles)
        finally:
            unregister("temporary_m52b_test_subject")
        self.assertNotIn("temporary_m52b_test_subject", default_subject_profiles)


# ---------------------------------------------------------------------------
# regression — M5.1 / M5.2A untouched
# ---------------------------------------------------------------------------

class TestUpstreamFrameworksUntouched(unittest.TestCase):
    def test_educational_taxonomy_still_importable(self) -> None:
        import modules.educational_taxonomy  # noqa: F401

    def test_educational_object_framework_still_importable(self) -> None:
        import modules.educational_object_framework  # noqa: F401

    def test_educational_object_type_has_no_new_fields(self) -> None:
        # Confirms this package did not retrofit fields onto the frozen model.
        expected_fields = {"key", "category", "display_name", "description", "aliases", "version"}
        actual_fields = set(EducationalObjectType.__dataclass_fields__.keys())
        self.assertEqual(actual_fields, expected_fields)

    def test_taxonomy_registry_has_no_new_methods(self) -> None:
        expected_public_methods = {
            "register", "unregister", "get", "all_types", "types_by_category",
            "categories", "keys",
        }
        actual_public_methods = {
            name for name in dir(TaxonomyRegistry)
            if not name.startswith("_") and callable(getattr(TaxonomyRegistry, name))
        }
        self.assertEqual(actual_public_methods, expected_public_methods)


if __name__ == "__main__":
    unittest.main()
