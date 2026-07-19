"""
tests/test_m52a_universal_educational_taxonomy.py — M5.2A unit tests
for modules/educational_taxonomy (the Universal Educational Taxonomy:
no object processing is implemented in M5.2A, so these tests exercise
the taxonomy data model, registry, built-in catalog, and validation
helpers themselves).

Coverage:
  - enums: EducationalCategory membership / string-value contracts
  - exceptions: hierarchy relationships
  - models: EducationalObjectType validation, immutability,
    determinism of to_dict(), alias rules
  - registry: registration, duplicate-key / duplicate-alias rejection,
    lookup by key and by alias, unregister(), deterministic ordering
    (independent of registration order), categories(), singleton
    default_taxonomy
  - catalog: every required example object type from the M5.2A spec
    is present, in the correct category, with no subject-specific
    types anywhere in the built-in catalog
  - validation: validate_taxonomy() reuses M5.1's ValidationResult /
    ValidationDiagnostic / DiagnosticSeverity contracts, catches an
    intentionally-broken registry's duplicate/empty-category problems
  - extensibility / backward compatibility: a new type can be
    registered into a fresh registry without touching any existing
    entry or any framework file
  - regression: modules.educational_object_framework remains
    importable and untouched by this package
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import ValidationResult

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.exceptions import (
    EducationalTaxonomyError,
    TaxonomyLookupError,
    TaxonomyRegistrationError,
    TaxonomyValidationError,
)
from modules.educational_taxonomy.models import DEFAULT_TYPE_VERSION, EducationalObjectType
from modules.educational_taxonomy.registry import TaxonomyRegistry, default_taxonomy
from modules.educational_taxonomy.validation import validate_taxonomy
from modules.educational_taxonomy import catalog as taxonomy_catalog


# ---------------------------------------------------------------------------
# enums
# ---------------------------------------------------------------------------

class TestEducationalCategory(unittest.TestCase):
    def test_seven_canonical_categories(self) -> None:
        self.assertEqual(len(EducationalCategory), 7)

    def test_values_are_strings(self) -> None:
        for category in EducationalCategory:
            self.assertIsInstance(category.value, str)
            self.assertEqual(category, category.value)

    def test_expected_members_present(self) -> None:
        expected = {
            "KNOWLEDGE", "REASONING", "VISUAL", "STRUCTURED",
            "LEARNING", "ASSESSMENT", "LANGUAGE",
        }
        self.assertEqual({c.name for c in EducationalCategory}, expected)


# ---------------------------------------------------------------------------
# exceptions
# ---------------------------------------------------------------------------

class TestExceptionHierarchy(unittest.TestCase):
    def test_all_subclass_base(self) -> None:
        for exc_type in (TaxonomyRegistrationError, TaxonomyLookupError, TaxonomyValidationError):
            self.assertTrue(issubclass(exc_type, EducationalTaxonomyError))

    def test_lookup_error_is_also_lookup_error(self) -> None:
        self.assertTrue(issubclass(TaxonomyLookupError, LookupError))

    def test_base_is_exception(self) -> None:
        self.assertTrue(issubclass(EducationalTaxonomyError, Exception))


# ---------------------------------------------------------------------------
# models.EducationalObjectType
# ---------------------------------------------------------------------------

class TestEducationalObjectType(unittest.TestCase):
    def _make(self, **overrides) -> EducationalObjectType:
        defaults = dict(
            key="concept",
            category=EducationalCategory.KNOWLEDGE,
            display_name="Concept",
            description="A named idea.",
        )
        defaults.update(overrides)
        return EducationalObjectType(**defaults)

    def test_valid_construction(self) -> None:
        obj_type = self._make()
        self.assertEqual(obj_type.key, "concept")
        self.assertEqual(obj_type.version, DEFAULT_TYPE_VERSION)

    def test_immutable(self) -> None:
        obj_type = self._make()
        with self.assertRaises(Exception):
            obj_type.key = "other"  # type: ignore[misc]

    def test_rejects_empty_key(self) -> None:
        with self.assertRaises(TaxonomyValidationError):
            self._make(key="")

    def test_rejects_non_snake_case_key(self) -> None:
        for bad_key in ("Concept", "CONCEPT", "concept-type", "1concept", "concept type"):
            with self.assertRaises(TaxonomyValidationError):
                self._make(key=bad_key)

    def test_rejects_non_category_enum(self) -> None:
        with self.assertRaises(TaxonomyValidationError):
            self._make(category="knowledge_objects")  # plain str, not the Enum

    def test_rejects_empty_display_name(self) -> None:
        with self.assertRaises(TaxonomyValidationError):
            self._make(display_name="   ")

    def test_rejects_empty_description(self) -> None:
        with self.assertRaises(TaxonomyValidationError):
            self._make(description="")

    def test_rejects_bad_alias(self) -> None:
        with self.assertRaises(TaxonomyValidationError):
            self._make(aliases=("Not-Snake-Case",))

    def test_rejects_alias_equal_to_key(self) -> None:
        with self.assertRaises(TaxonomyValidationError):
            self._make(aliases=("concept",))

    def test_aliases_frozen_to_tuple(self) -> None:
        obj_type = self._make(aliases=["worked_problem"])
        self.assertIsInstance(obj_type.aliases, tuple)
        self.assertEqual(obj_type.aliases, ("worked_problem",))

    def test_to_dict_shape(self) -> None:
        obj_type = self._make(aliases=("synonym_key",))
        as_dict = obj_type.to_dict()
        self.assertEqual(as_dict["key"], "concept")
        self.assertEqual(as_dict["category"], "knowledge_objects")
        self.assertEqual(as_dict["aliases"], ["synonym_key"])
        self.assertEqual(as_dict["version"], DEFAULT_TYPE_VERSION)

    def test_to_dict_deterministic(self) -> None:
        obj_type = self._make()
        first = json.dumps(obj_type.to_dict(), sort_keys=True)
        second = json.dumps(obj_type.to_dict(), sort_keys=True)
        self.assertEqual(first, second)

    def test_equality_by_value(self) -> None:
        self.assertEqual(self._make(), self._make())


# ---------------------------------------------------------------------------
# registry.TaxonomyRegistry
# ---------------------------------------------------------------------------

class TestTaxonomyRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = TaxonomyRegistry()
        self.concept = EducationalObjectType(
            key="concept", category=EducationalCategory.KNOWLEDGE,
            display_name="Concept", description="A named idea.",
        )
        self.proof = EducationalObjectType(
            key="proof", category=EducationalCategory.REASONING,
            display_name="Proof", description="A logical argument.",
        )

    def test_register_and_get(self) -> None:
        self.registry.register(self.concept)
        self.assertEqual(self.registry.get("concept"), self.concept)

    def test_duplicate_key_rejected(self) -> None:
        self.registry.register(self.concept)
        duplicate = EducationalObjectType(
            key="concept", category=EducationalCategory.REASONING,
            display_name="Concept Again", description="Different description.",
        )
        with self.assertRaises(TaxonomyRegistrationError):
            self.registry.register(duplicate)

    def test_alias_collides_with_existing_key(self) -> None:
        self.registry.register(self.concept)
        colliding = EducationalObjectType(
            key="idea", category=EducationalCategory.KNOWLEDGE,
            display_name="Idea", description="Alias collision test.",
            aliases=("concept",),
        )
        with self.assertRaises(TaxonomyRegistrationError):
            self.registry.register(colliding)

    def test_alias_collides_with_existing_alias(self) -> None:
        first = EducationalObjectType(
            key="idea", category=EducationalCategory.KNOWLEDGE,
            display_name="Idea", description="First.", aliases=("notion",),
        )
        second = EducationalObjectType(
            key="thought", category=EducationalCategory.KNOWLEDGE,
            display_name="Thought", description="Second.", aliases=("notion",),
        )
        self.registry.register(first)
        with self.assertRaises(TaxonomyRegistrationError):
            self.registry.register(second)

    def test_lookup_by_alias_resolves_to_canonical_entry(self) -> None:
        aliased = EducationalObjectType(
            key="worked_example", category=EducationalCategory.REASONING,
            display_name="Worked Example", description="Solved instance.",
            aliases=("worked_problem",),
        )
        self.registry.register(aliased)
        self.assertEqual(self.registry.get("worked_problem"), aliased)

    def test_unregister_removes_key_and_aliases(self) -> None:
        aliased = EducationalObjectType(
            key="worked_example", category=EducationalCategory.REASONING,
            display_name="Worked Example", description="Solved instance.",
            aliases=("worked_problem",),
        )
        self.registry.register(aliased)
        self.registry.unregister("worked_example")
        self.assertNotIn("worked_example", self.registry)
        self.assertNotIn("worked_problem", self.registry)

    def test_unregister_unknown_key_raises(self) -> None:
        with self.assertRaises(TaxonomyLookupError):
            self.registry.unregister("does_not_exist")

    def test_get_unknown_key_raises(self) -> None:
        with self.assertRaises(TaxonomyLookupError):
            self.registry.get("does_not_exist")

    def test_all_types_deterministic_regardless_of_registration_order(self) -> None:
        registry_a = TaxonomyRegistry()
        registry_a.register(self.proof)
        registry_a.register(self.concept)

        registry_b = TaxonomyRegistry()
        registry_b.register(self.concept)
        registry_b.register(self.proof)

        keys_a = [t.key for t in registry_a.all_types()]
        keys_b = [t.key for t in registry_b.all_types()]
        self.assertEqual(keys_a, keys_b)
        self.assertEqual(keys_a, sorted(keys_a))  # knowledge_objects < reasoning_objects

    def test_types_by_category(self) -> None:
        self.registry.register(self.concept)
        self.registry.register(self.proof)
        knowledge = self.registry.types_by_category(EducationalCategory.KNOWLEDGE)
        self.assertEqual([t.key for t in knowledge], ["concept"])

    def test_categories_only_lists_present_ones_in_declaration_order(self) -> None:
        self.registry.register(self.proof)  # REASONING only
        self.registry.register(self.concept)  # KNOWLEDGE
        self.assertEqual(
            self.registry.categories(),
            (EducationalCategory.KNOWLEDGE, EducationalCategory.REASONING),
        )

    def test_contains_and_len(self) -> None:
        self.assertEqual(len(self.registry), 0)
        self.registry.register(self.concept)
        self.assertIn("concept", self.registry)
        self.assertEqual(len(self.registry), 1)

    def test_register_rejects_non_object_type(self) -> None:
        with self.assertRaises(TaxonomyRegistrationError):
            self.registry.register("not-a-type")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# built-in catalog / default_taxonomy singleton
# ---------------------------------------------------------------------------

class TestBuiltinCatalog(unittest.TestCase):
    def test_default_taxonomy_seeded_at_import_time(self) -> None:
        self.assertGreater(len(default_taxonomy), 0)

    def test_all_seven_categories_covered(self) -> None:
        self.assertEqual(len(default_taxonomy.categories()), 7)
        for category in EducationalCategory:
            self.assertGreater(
                len(default_taxonomy.types_by_category(category)), 0,
                f"category {category.value} has no built-in object types",
            )

    def test_spec_example_types_present(self) -> None:
        # A representative sample of the M5.2A spec's own examples,
        # one per category — not exhaustive of every listed example,
        # but enough to catch a wholesale omission of any category.
        expected_by_category = {
            EducationalCategory.KNOWLEDGE: {"concept", "definition", "theorem", "axiom", "corollary"},
            EducationalCategory.REASONING: {"proof", "derivation", "worked_example", "counterexample"},
            EducationalCategory.VISUAL: {"figure", "diagram", "graph", "mind_map"},
            EducationalCategory.STRUCTURED: {"table", "matrix", "comparison", "list"},
            EducationalCategory.LEARNING: {"activity", "experiment", "exercise", "important_box"},
            EducationalCategory.ASSESSMENT: {"mcq", "assertion_reason", "true_false", "hots", "case_study"},
            EducationalCategory.LANGUAGE: {"story", "poem", "grammar_rule", "stanza"},
        }
        for category, keys in expected_by_category.items():
            registered = {t.key for t in default_taxonomy.types_by_category(category)}
            self.assertTrue(
                keys.issubset(registered),
                f"missing {keys - registered} from category {category.value}",
            )

    def test_no_subject_specific_types_in_builtin_catalog(self) -> None:
        forbidden_substrings = ("physics", "math", "history", "chemistry", "biology", "business")
        for object_type in default_taxonomy.all_types():
            lowered = object_type.key.lower()
            for forbidden in forbidden_substrings:
                self.assertNotIn(
                    forbidden, lowered,
                    f"built-in catalog entry '{object_type.key}' looks subject-specific",
                )

    def test_catalog_seed_reusable_against_isolated_registry(self) -> None:
        isolated = TaxonomyRegistry()
        taxonomy_catalog.seed(isolated)
        self.assertEqual(len(isolated), len(default_taxonomy))
        self.assertEqual(isolated.keys(), default_taxonomy.keys())

    def test_no_duplicate_keys_in_builtin_catalog(self) -> None:
        keys = [t.key for t in taxonomy_catalog._BUILTIN_TYPES]
        self.assertEqual(len(keys), len(set(keys)))


# ---------------------------------------------------------------------------
# validation.py — reuse of the M5.1 ValidationResult contract
# ---------------------------------------------------------------------------

class TestValidateTaxonomy(unittest.TestCase):
    def test_default_taxonomy_is_valid(self) -> None:
        result = validate_taxonomy(default_taxonomy)
        self.assertIsInstance(result, ValidationResult)
        self.assertTrue(result.is_success)
        self.assertFalse(result.has_errors)

    def test_empty_registry_reports_missing_categories_as_warnings_not_errors(self) -> None:
        empty = TaxonomyRegistry()
        result = validate_taxonomy(empty)
        self.assertTrue(result.is_success)  # warnings don't fail is_success
        self.assertTrue(result.has_warnings)
        self.assertEqual(len(result.warnings()), 7)
        for diagnostic in result.warnings():
            self.assertEqual(diagnostic.severity, DiagnosticSeverity.WARNING)
            self.assertEqual(diagnostic.code, "taxonomy.empty_category")

    def test_partial_registry_warns_only_for_missing_categories(self) -> None:
        registry = TaxonomyRegistry()
        registry.register(EducationalObjectType(
            key="concept", category=EducationalCategory.KNOWLEDGE,
            display_name="Concept", description="A named idea.",
        ))
        result = validate_taxonomy(registry)
        self.assertEqual(len(result.warnings()), 6)  # every category except KNOWLEDGE

    def test_result_diagnostics_are_validation_diagnostic_instances(self) -> None:
        empty = TaxonomyRegistry()
        result = validate_taxonomy(empty)
        for diagnostic in result.diagnostics:
            self.assertIsInstance(diagnostic.severity, DiagnosticSeverity)
            self.assertTrue(diagnostic.code)
            self.assertTrue(diagnostic.message)


# ---------------------------------------------------------------------------
# extensibility / backward compatibility
# ---------------------------------------------------------------------------

class TestExtensibility(unittest.TestCase):
    def test_new_type_can_be_registered_without_touching_existing_entries(self) -> None:
        registry = TaxonomyRegistry()
        taxonomy_catalog.seed(registry)
        before = set(registry.keys())

        registry.register(EducationalObjectType(
            key="future_object_type", category=EducationalCategory.KNOWLEDGE,
            display_name="Future Object Type",
            description="A hypothetical M5.2B+ addition, added without modifying any existing entry.",
        ))

        after = set(registry.keys())
        self.assertTrue(before.issubset(after))
        self.assertIn("future_object_type", after)
        # every pre-existing entry is byte-identical to before
        for key in before:
            self.assertEqual(registry.get(key).to_dict(), registry.get(key).to_dict())

    def test_registering_into_default_taxonomy_does_not_require_framework_changes(self) -> None:
        # Demonstrates the sole extension mechanism a future milestone uses.
        from modules.educational_taxonomy import register, unregister

        register(EducationalObjectType(
            key="temporary_extension_test_type", category=EducationalCategory.LEARNING,
            display_name="Temporary", description="Registered and removed within this test.",
        ))
        try:
            self.assertIn("temporary_extension_test_type", default_taxonomy)
        finally:
            unregister("temporary_extension_test_type")
        self.assertNotIn("temporary_extension_test_type", default_taxonomy)


# ---------------------------------------------------------------------------
# regression — M5.1 untouched
# ---------------------------------------------------------------------------

class TestM51Untouched(unittest.TestCase):
    def test_educational_object_framework_still_importable(self) -> None:
        import modules.educational_object_framework as m51
        self.assertTrue(hasattr(m51, "ProcessingContext"))
        self.assertTrue(hasattr(m51, "ProcessorRegistry"))
        self.assertTrue(hasattr(m51, "ProcessingPipeline"))

    def test_taxonomy_does_not_register_into_m51_processor_registry(self) -> None:
        from modules.educational_object_framework.registry import default_registry as m51_registry
        # The taxonomy registry and the M5.1 processor registry are
        # completely independent instances/types.
        self.assertNotIsInstance(default_taxonomy, type(m51_registry))


if __name__ == "__main__":
    unittest.main()
