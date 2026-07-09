"""
tests/test_registry_enrichment.py — unit tests for Phase B1b's
compiler.enrichment module (canonical registry enrichment).

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registry import CanonicalRegistry
from compiler.registry_manager import RegistryManager
from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import (
    ENRICHMENT_VERSION,
    ENRICHMENT_FIELDS,
    EDUCATIONAL_ROLE_BY_OBJECT_TYPE,
    compute_enrichment,
    enrich_item,
    enrich_registry,
    enrich_registries,
)


# --------------------------------------------------------------------------
# Helpers -- minimal stand-ins for the canonical envelope
# modules/canonical.py::canonical_fields() + pipeline.py's
# _attach_canonical() actually build, keeping only the keys these tests
# care about (matches the style already used in tests/test_registries.py).
# --------------------------------------------------------------------------

def make_concept(id_="c1", name="Photosynthesis", aliases=None, importance="medium",
                  confidence=0.5, extraction_method="vlm", source_page=3, **extra):
    d = {
        "id": id_, "urn": f"urn:concept:{name}", "object_type": "concept",
        "name": name, "aliases": aliases if aliases is not None else [],
        "importance": importance,
        "provenance": {"source_page": source_page, "extraction_method": extraction_method,
                       "confidence": confidence},
        "extraction_confidence": confidence,
    }
    d.update(extra)
    return d


def make_figure(id_="f1", title="Fig 1", caption="The water cycle", page=1,
                semantic_description="", importance="medium", difficulty="medium",
                confidence=0.5, extraction_method="deterministic", figure_type="figure",
                object_type="figure", **extra):
    d = {
        "id": id_, "urn": f"urn:figure:{page}:{id_}", "object_type": object_type,
        "title": title, "caption": caption, "page": page,
        "figure_type": figure_type, "semantic_description": semantic_description,
        "importance": importance, "difficulty": difficulty,
        "provenance": {"source_page": page, "extraction_method": extraction_method,
                       "confidence": confidence},
        "extraction_confidence": confidence,
    }
    d.update(extra)
    return d


def make_table(id_="t1", title="Table 1", page=2, confidence=0.5, **extra):
    d = {
        "id": id_, "urn": f"urn:table:{page}:{id_}", "object_type": "table",
        "title": title, "page": page, "table_type": "data_table",
        "semantic_description": "", "importance": "medium", "difficulty": "medium",
        "provenance": {"source_page": page, "extraction_method": "deterministic",
                       "confidence": confidence},
        "extraction_confidence": confidence,
    }
    d.update(extra)
    return d


def make_definition(id_="d1", term="Inflation", page=4, confidence=0.6, **extra):
    d = {
        "id": id_, "urn": f"urn:definition:{term}:{page}", "object_type": "definition",
        "term": term, "page": page,
        "provenance": {"source_page": page, "extraction_method": "deterministic",
                       "confidence": confidence},
        "extraction_confidence": confidence,
    }
    d.update(extra)
    return d


def make_equation(id_="e1", page=5, confidence=0.5, **extra):
    d = {
        "id": id_, "urn": f"urn:equation:{page}:{id_}", "object_type": "equation",
        "page": page, "latex": "",
        "provenance": {"source_page": page, "extraction_method": "deterministic",
                       "confidence": confidence},
        "extraction_confidence": confidence,
    }
    d.update(extra)
    return d


def make_activity(id_="a1", activity_type="group_work", page=6, confidence=0.6, **extra):
    d = {
        "id": id_, "urn": f"urn:activity:{activity_type}:{page}", "object_type": "activity",
        "activity_type": activity_type, "page": page,
        "provenance": {"source_page": page, "extraction_method": "deterministic",
                       "confidence": confidence},
        "extraction_confidence": confidence,
    }
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# compute_enrichment() / enrich_item() -- pure per-item derivation
# --------------------------------------------------------------------------
class TestComputeEnrichmentDisplayNames:
    def test_concept_canonical_display_name_normalizes_whitespace(self):
        item = make_concept(name="  Photosynthesis   Process  ")
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["canonical_display_name"] == "Photosynthesis Process"

    def test_concept_normalized_name_is_casefolded(self):
        item = make_concept(name="Photosynthesis")
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["normalized_name"] == "photosynthesis"

    def test_figure_uses_title_as_display_name(self):
        item = make_figure(title="  Fig.  1  ")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["canonical_display_name"] == "Fig. 1"
        assert enrichment["normalized_name"] == "fig. 1"

    def test_definition_uses_term_as_display_name(self):
        item = make_definition(term="Inflation")
        enrichment = compute_enrichment(item, registry_name="definitions")
        assert enrichment["canonical_display_name"] == "Inflation"
        assert enrichment["normalized_name"] == "inflation"

    def test_item_with_no_display_field_gets_none(self):
        item = make_equation()
        enrichment = compute_enrichment(item, registry_name="equations")
        assert enrichment["canonical_display_name"] is None
        assert enrichment["normalized_name"] is None

    def test_blank_display_field_treated_as_absent(self):
        item = make_concept(name="   ")
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["canonical_display_name"] is None
        assert enrichment["normalized_name"] is None

    def test_display_name_priority_name_before_title(self):
        # An item that (hypothetically) carried both "name" and "title"
        # should prefer "name" -- matches concept's own precedence.
        item = make_concept(name="Concept Name", title="Some Title")
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["canonical_display_name"] == "Concept Name"


class TestAliases:
    def test_empty_aliases_gets_normalized_variant_when_it_differs(self):
        item = make_concept(name="Photosynthesis  ", aliases=[])
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["aliases"] == ["photosynthesis"]

    def test_aliases_untouched_when_already_populated(self):
        item = make_concept(name="Photosynthesis", aliases=["photo-synthesis"])
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["aliases"] == ["photo-synthesis"]

    def test_no_alias_added_when_normalized_name_equals_raw_name(self):
        # Already-lowercase, single-spaced name: normalized_name ==
        # name, so no alias variant is a genuinely new string.
        item = make_concept(name="photosynthesis", aliases=[])
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["aliases"] == []

    def test_items_without_aliases_key_get_no_aliases_field(self):
        item = make_figure()
        assert "aliases" not in item
        enrichment = compute_enrichment(item, registry_name="figures")
        assert "aliases" not in enrichment

    def test_enrich_item_does_not_add_aliases_key_where_absent(self):
        item = make_table()
        enrich_item(item, registry_name="tables")
        assert "aliases" not in item


class TestEducationalRole:
    @pytest.mark.parametrize("object_type,expected_role", list(EDUCATIONAL_ROLE_BY_OBJECT_TYPE.items()))
    def test_every_known_object_type_maps_to_its_fixed_role(self, object_type, expected_role):
        item = {"id": "x", "object_type": object_type}
        enrichment = compute_enrichment(item, registry_name="whatever")
        assert enrichment["educational_role"] == expected_role

    def test_unknown_object_type_maps_to_none(self):
        item = {"id": "x", "object_type": "some_future_type"}
        enrichment = compute_enrichment(item, registry_name="whatever")
        assert enrichment["educational_role"] is None

    def test_missing_object_type_maps_to_none(self):
        item = {"id": "x"}
        enrichment = compute_enrichment(item, registry_name="whatever")
        assert enrichment["educational_role"] is None

    def test_role_mapping_is_deterministic_static_table(self):
        assert EDUCATIONAL_ROLE_BY_OBJECT_TYPE["concept"] == "concept"
        assert EDUCATIONAL_ROLE_BY_OBJECT_TYPE["figure"] == "visual_aid"
        assert EDUCATIONAL_ROLE_BY_OBJECT_TYPE["diagram"] == "visual_aid"
        assert EDUCATIONAL_ROLE_BY_OBJECT_TYPE["equation"] == "formula"
        assert EDUCATIONAL_ROLE_BY_OBJECT_TYPE["example"] == "worked_example"


class TestObjectSubtype:
    def test_figure_subtype_copied_from_figure_type(self):
        item = make_figure(figure_type="figure")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["object_subtype"] == "figure"

    def test_diagram_subtype_copied_from_figure_type_field(self):
        item = make_figure(object_type="diagram", figure_type="diagram")
        enrichment = compute_enrichment(item, registry_name="diagrams")
        assert enrichment["object_subtype"] == "diagram"

    def test_table_subtype_copied_from_table_type(self):
        item = make_table()
        enrichment = compute_enrichment(item, registry_name="tables")
        assert enrichment["object_subtype"] == "data_table"

    def test_activity_subtype_copied_from_activity_type(self):
        item = make_activity(activity_type="role_play")
        enrichment = compute_enrichment(item, registry_name="activities")
        assert enrichment["object_subtype"] == "role_play"

    def test_item_with_no_subtype_field_gets_none(self):
        item = make_concept()
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["object_subtype"] is None


class TestConceptTypePlaceholder:
    def test_concept_type_is_always_none_today(self):
        for item in (make_concept(), make_figure(), make_table(), make_definition()):
            enrichment = compute_enrichment(item, registry_name="whatever")
            assert enrichment["concept_type"] is None

    def test_concept_type_field_always_present(self):
        item = make_equation()
        enrichment = compute_enrichment(item, registry_name="equations")
        assert "concept_type" in enrichment


class TestSemanticAndVisualSummary:
    # Phase B1b final-refinement pass (REFINEMENT 2): semantic_summary is
    # reserved and must never simply duplicate semantic_description --
    # see compiler/enrichment.py's _semantic_summary docstring. It is
    # always None today, regardless of what semantic_description holds.

    def test_semantic_summary_is_none_even_when_semantic_description_is_nonempty(self):
        item = make_figure(semantic_description="Shows the four stages of the cycle.")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["semantic_summary"] is None
        # explicitly not a copy of the raw field, whatever its value:
        assert enrichment["semantic_summary"] != item["semantic_description"]

    def test_semantic_summary_is_none_when_semantic_description_empty(self):
        item = make_figure(semantic_description="")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["semantic_summary"] is None

    def test_semantic_summary_is_none_for_types_without_the_field(self):
        item = make_concept()
        assert "semantic_description" not in item
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["semantic_summary"] is None

    def test_semantic_summary_is_none_for_activity_style_items_with_real_body_text(self):
        # activities/boxes/warnings/notes/examples populate
        # semantic_description with real (truncated) extracted body text
        # via pipeline.py's _finalize_blocks() -- confirms the reserved
        # field stays None even for the object types where the raw field
        # is genuinely non-empty in production, not just in this test.
        item = make_concept(object_type="activity",
                             semantic_description="Students measure the rate of photosynthesis.")
        enrichment = compute_enrichment(item, registry_name="activities")
        assert enrichment["semantic_summary"] is None

    def test_visual_summary_joins_title_and_caption_for_figures(self):
        item = make_figure(title="Fig. 3", caption="Water cycle")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["visual_summary"] == "Fig. 3 — Water cycle"

    def test_visual_summary_uses_only_nonempty_parts(self):
        item = make_figure(title="Fig. 3", caption="")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["visual_summary"] == "Fig. 3"

    def test_visual_summary_none_when_title_and_caption_both_empty(self):
        item = make_figure(title="", caption="")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["visual_summary"] is None

    def test_visual_summary_none_for_non_visual_object_types(self):
        item = make_table(title="Table 1")
        enrichment = compute_enrichment(item, registry_name="tables")
        assert enrichment["visual_summary"] is None

    def test_visual_summary_applies_to_diagrams_too(self):
        item = make_figure(object_type="diagram", title="Diagram A", caption="Blood flow")
        enrichment = compute_enrichment(item, registry_name="diagrams")
        assert enrichment["visual_summary"] == "Diagram A — Blood flow"


class TestEducationalImportanceAndDifficulty:
    def test_importance_and_difficulty_copied_through_for_figures(self):
        item = make_figure(importance="high", difficulty="low")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["educational_importance"] == "high"
        assert enrichment["educational_difficulty"] == "low"

    def test_importance_copied_for_concepts_without_difficulty_field(self):
        item = make_concept(importance="medium")
        assert "difficulty" not in item
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["educational_importance"] == "medium"
        assert enrichment["educational_difficulty"] is None

    def test_both_none_when_neither_field_present(self):
        item = make_definition()
        enrichment = compute_enrichment(item, registry_name="definitions")
        assert enrichment["educational_importance"] is None
        assert enrichment["educational_difficulty"] is None


class TestExtractionQuality:
    def test_confidence_band_high(self):
        item = make_concept(confidence=0.9)
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["confidence_band"] == "high"

    def test_confidence_band_medium(self):
        item = make_concept(confidence=0.5)
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["confidence_band"] == "medium"

    def test_confidence_band_low(self):
        item = make_concept(confidence=0.1)
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["confidence_band"] == "low"

    def test_confidence_band_boundary_values(self):
        assert compute_enrichment(make_concept(confidence=0.75), registry_name="c")[
            "extraction_quality"]["confidence_band"] == "high"
        assert compute_enrichment(make_concept(confidence=0.4), registry_name="c")[
            "extraction_quality"]["confidence_band"] == "medium"
        assert compute_enrichment(make_concept(confidence=0.399), registry_name="c")[
            "extraction_quality"]["confidence_band"] == "low"

    def test_confidence_band_none_for_unparseable_confidence(self):
        item = make_concept()
        item["extraction_confidence"] = None
        item["provenance"]["confidence"] = None
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["confidence_band"] is None

    def test_is_vlm_extracted_true_for_vlm_provenance(self):
        item = make_concept(extraction_method="vlm")
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["is_vlm_extracted"] is True

    def test_is_vlm_extracted_false_for_deterministic_provenance(self):
        item = make_figure(extraction_method="deterministic")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["extraction_quality"]["is_vlm_extracted"] is False

    def test_has_source_page_true_when_present(self):
        item = make_concept(source_page=7)
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["has_source_page"] is True

    def test_has_source_page_false_when_none(self):
        item = make_concept(source_page=None)
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["has_source_page"] is False

    def test_has_display_name_reflects_canonical_display_name(self):
        item = make_concept(name="Photosynthesis")
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["extraction_quality"]["has_display_name"] is True

    def test_has_semantic_and_visual_summary_flags(self):
        # semantic_summary is reserved (always None as of B1b.2 -- see
        # TestSemanticAndVisualSummary), so has_semantic_summary is always
        # False regardless of semantic_description; has_visual_summary
        # still reflects the real, non-reserved visual_summary field.
        item = make_figure(semantic_description="desc", title="T", caption="C")
        enrichment = compute_enrichment(item, registry_name="figures")
        assert enrichment["extraction_quality"]["has_semantic_summary"] is False
        assert enrichment["extraction_quality"]["has_visual_summary"] is True


class TestRegistryMetadata:
    def test_registry_metadata_records_registry_name_and_object_type(self):
        item = make_concept()
        enrichment = compute_enrichment(item, registry_name="concepts")
        meta = enrichment["registry_metadata"]
        assert meta["registry_name"] == "concepts"
        assert meta["object_type"] == "concept"

    def test_registry_metadata_records_enrichment_version(self):
        item = make_concept()
        enrichment = compute_enrichment(item, registry_name="concepts")
        assert enrichment["registry_metadata"]["enrichment_version"] == ENRICHMENT_VERSION

    def test_registry_metadata_enriched_at_is_iso_timestamp_string(self):
        item = make_concept()
        enrichment = compute_enrichment(item, registry_name="concepts")
        enriched_at = enrichment["registry_metadata"]["enriched_at"]
        assert isinstance(enriched_at, str)
        # Must round-trip through fromisoformat -- a real ISO-8601 stamp.
        import datetime as _dt
        _dt.datetime.fromisoformat(enriched_at)


# --------------------------------------------------------------------------
# enrich_item() -- in-place mutation contract
# --------------------------------------------------------------------------
class TestEnrichItemMutation:
    def test_enrich_item_mutates_and_returns_same_object(self):
        item = make_concept()
        result = enrich_item(item, registry_name="concepts")
        assert result is item

    def test_enrich_item_adds_every_documented_field_where_applicable(self):
        item = make_concept()
        enrich_item(item, registry_name="concepts")
        for field in ENRICHMENT_FIELDS:
            assert field in item

    def test_enrich_item_never_overwrites_existing_unrelated_keys(self):
        # "aliases" is intentionally excluded here: per the module's own
        # documented aliases rule, an empty aliases list IS allowed to
        # gain a deterministic normalized-name variant -- see
        # TestAliases above for that behavior's own dedicated coverage.
        # Every other pre-existing key must be left byte-for-byte
        # unchanged.
        item = make_concept(name="Photosynthesis")
        before = copy.deepcopy(item)
        enrich_item(item, registry_name="concepts")
        for key, value in before.items():
            if key == "aliases":
                continue
            assert item[key] == value

    def test_enrich_item_does_not_change_id_urn_or_object_type(self):
        item = make_concept(id_="c-42")
        before_id, before_urn, before_type = item["id"], item["urn"], item["object_type"]
        enrich_item(item, registry_name="concepts")
        assert item["id"] == before_id
        assert item["urn"] == before_urn
        assert item["object_type"] == before_type

    def test_enrich_item_on_non_dict_item_is_a_no_op(self):
        class NotADict:
            pass
        obj = NotADict()
        result = enrich_item(obj, registry_name="concepts")
        assert result is obj
        assert not hasattr(obj, "canonical_display_name")

    def test_enrich_item_is_idempotent_apart_from_timestamp(self):
        item = make_concept()
        enrich_item(item, registry_name="concepts")
        first_pass = copy.deepcopy(item)
        enrich_item(item, registry_name="concepts")
        second_pass = item
        first_pass["registry_metadata"].pop("enriched_at")
        second_pass_copy = copy.deepcopy(second_pass)
        second_pass_copy["registry_metadata"].pop("enriched_at")
        assert first_pass == second_pass_copy


# --------------------------------------------------------------------------
# enrich_registry() / enrich_registries() -- registry & manager level
# --------------------------------------------------------------------------
class TestEnrichRegistry:
    def test_enrich_registry_enriches_every_item(self):
        registry = CanonicalRegistry(name="concepts")
        registry.insert(make_concept(id_="c1", name="Alpha"))
        registry.insert(make_concept(id_="c2", name="Beta"))
        count = enrich_registry(registry)
        assert count == 2
        for item in registry.values():
            assert "canonical_display_name" in item

    def test_enrich_registry_preserves_insertion_order(self):
        registry = CanonicalRegistry(name="concepts")
        registry.insert(make_concept(id_="c1", name="Alpha"))
        registry.insert(make_concept(id_="c2", name="Beta"))
        registry.insert(make_concept(id_="c3", name="Gamma"))
        enrich_registry(registry)
        assert [item["id"] for item in registry.values()] == ["c1", "c2", "c3"]

    def test_enrich_registry_preserves_lookup_indices(self):
        registry = CanonicalRegistry(name="concepts")
        registry.insert(make_concept(id_="c1", name="Alpha"))
        enrich_registry(registry)
        assert registry.get_by_id("c1") is not None
        assert registry.get_by_name("Alpha") is not None
        assert registry.get_by_urn("urn:concept:Alpha") is not None

    def test_enrich_registry_on_empty_registry_returns_zero(self):
        registry = CanonicalRegistry(name="concepts")
        assert enrich_registry(registry) == 0

    def test_enrich_registry_uses_registry_name_in_metadata(self):
        registry = CanonicalRegistry(name="figures")
        registry.insert(make_figure(id_="f1"))
        enrich_registry(registry)
        item = registry.get_by_id("f1")
        assert item["registry_metadata"]["registry_name"] == "figures"


class TestEnrichRegistries:
    def _build_populated_manager(self) -> RegistryManager:
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept(id_="c1", name="Alpha")],
            definitions=[make_definition(id_="d1", term="Inflation")],
            figures=[make_figure(id_="f1", title="Fig 1")],
            tables=[make_table(id_="t1", title="Table 1")],
            equations=[make_equation(id_="e1")],
            activities=[make_activity(id_="a1")],
        )
        return manager

    def test_enrich_registries_returns_per_registry_counts(self):
        manager = self._build_populated_manager()
        counts = enrich_registries(manager)
        assert counts["concepts"] == 1
        assert counts["definitions"] == 1
        assert counts["figures"] == 1
        assert counts["tables"] == 1
        assert counts["equations"] == 1
        assert counts["activities"] == 1
        assert counts["glossary"] == 0
        assert counts["diagrams"] == 0

    def test_enrich_registries_enriches_every_registered_registry(self):
        manager = self._build_populated_manager()
        enrich_registries(manager)
        for registry in manager:
            for item in registry.values():
                assert "registry_metadata" in item
                assert item["registry_metadata"]["registry_name"] == registry.name

    def test_enrich_registries_covers_all_twelve_registry_names(self):
        manager = create_registry_manager()
        counts = enrich_registries(manager)
        assert set(counts.keys()) == set(manager.names())
        assert len(counts) == 12


# --------------------------------------------------------------------------
# Backward compatibility -- registries.py / registry.py / pipeline
# integration untouched by enrichment
# --------------------------------------------------------------------------
class TestBackwardCompatibility:
    def test_serialize_still_round_trips_after_enrichment(self):
        registry = CanonicalRegistry(name="concepts")
        registry.insert(make_concept(id_="c1", name="Alpha"))
        enrich_registry(registry)
        serialized = registry.serialize()
        restored = CanonicalRegistry.deserialize(serialized)
        assert restored.get_by_id("c1")["canonical_display_name"] == "Alpha"
        assert restored.get_by_id("c1")["id"] == "c1"

    def test_enrichment_does_not_introduce_new_registry_types(self):
        manager = create_registry_manager()
        before_names = set(manager.names())
        enrich_registries(manager)
        assert set(manager.names()) == before_names

    def test_duplicate_id_still_raises_after_enrichment_module_import(self):
        # Confirms compiler.enrichment does not alter B0's own duplicate
        # protection when imported/used alongside it.
        from compiler.exceptions import DuplicateIdError
        registry = CanonicalRegistry(name="concepts")
        registry.insert(make_concept(id_="c1", name="Alpha"))
        enrich_registry(registry)
        with pytest.raises(DuplicateIdError):
            registry.insert(make_concept(id_="c1", name="Alpha Duplicate"))

    def test_existing_object_dict_shape_is_a_strict_superset_after_enrichment(self):
        item = make_figure(id_="f1")
        original_keys = set(item.keys())
        enrich_item(item, registry_name="figures")
        assert original_keys.issubset(set(item.keys()))

    def test_enrichment_fields_constant_matches_what_enrich_item_adds(self):
        item = make_concept()
        enrich_item(item, registry_name="concepts")
        for field in ENRICHMENT_FIELDS:
            assert field in item


# --------------------------------------------------------------------------
# Determinism across independent runs
# --------------------------------------------------------------------------
class TestDeterminism:
    def test_two_independent_computations_agree_except_timestamp(self):
        item_a = make_concept(name="Photosynthesis")
        item_b = make_concept(name="Photosynthesis")
        enrichment_a = compute_enrichment(item_a, registry_name="concepts")
        enrichment_b = compute_enrichment(item_b, registry_name="concepts")
        enrichment_a["registry_metadata"].pop("enriched_at")
        enrichment_b["registry_metadata"].pop("enriched_at")
        assert enrichment_a == enrichment_b

    def test_enrichment_does_not_depend_on_dict_key_order(self):
        item_a = make_concept(name="Beta")
        item_b = {k: item_a[k] for k in reversed(list(item_a.keys()))}
        enrichment_a = compute_enrichment(item_a, registry_name="concepts")
        enrichment_b = compute_enrichment(item_b, registry_name="concepts")
        enrichment_a["registry_metadata"].pop("enriched_at")
        enrichment_b["registry_metadata"].pop("enriched_at")
        assert enrichment_a == enrichment_b

    def test_full_pipeline_style_population_and_enrichment_is_reproducible(self):
        def build_and_enrich():
            manager = create_registry_manager()
            populate_registries(manager, concepts=[make_concept(id_="c1", name="Alpha")])
            enrich_registries(manager)
            item = dict(manager.get("concepts").get_by_id("c1"))
            item["registry_metadata"] = dict(item["registry_metadata"])
            item["registry_metadata"].pop("enriched_at")
            return item

        assert build_and_enrich() == build_and_enrich()