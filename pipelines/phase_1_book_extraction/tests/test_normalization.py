"""
tests/test_normalization.py — unit tests for Phase B1c's
compiler.normalization module (Canonical Normalization Layer).

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import enrich_registries
from compiler.normalization import (
    NORMALIZATION_VERSION,
    NORMALIZATION_FIELDS,
    normalize_text,
    canonical_lookup_key,
    compute_normalization,
    normalize_item,
    normalize_registry,
    normalize_registries,
)


# --------------------------------------------------------------------------
# Helpers -- minimal stand-ins for the canonical envelope, matching the
# style already used in tests/test_registry_enrichment.py.
# --------------------------------------------------------------------------

def make_concept(id_="c1", name="Photosynthesis", aliases=None, **extra):
    d = {
        "id": id_, "urn": f"urn:concept:{name}", "object_type": "concept",
        "name": name, "aliases": aliases if aliases is not None else [],
    }
    d.update(extra)
    return d


def make_figure(id_="f1", title="Fig 1", caption="The water cycle", **extra):
    d = {
        "id": id_, "urn": f"urn:figure:{id_}", "object_type": "figure",
        "title": title, "caption": caption,
    }
    d.update(extra)
    return d


def make_definition(id_="d1", term="Inflation", **extra):
    d = {
        "id": id_, "urn": f"urn:definition:{term}", "object_type": "definition",
        "term": term,
    }
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# normalize_text() -- deep textual normalization
# --------------------------------------------------------------------------

class TestNormalizeText:
    def test_collapses_repeated_whitespace(self):
        assert normalize_text("Hydrogen    Ion") == "Hydrogen Ion"

    def test_strips_leading_and_trailing_whitespace(self):
        assert normalize_text("   Hydrogen Ion   ") == "Hydrogen Ion"

    def test_collapses_mixed_whitespace_including_tabs_and_newlines(self):
        assert normalize_text("Hydrogen\t\nIon") == "Hydrogen Ion"

    def test_normalizes_curly_single_quotes_to_ascii(self):
        assert normalize_text("Newton\u2019s Law") == "Newton's Law"
        assert normalize_text("Newton\u2018s Law") == "Newton's Law"

    def test_normalizes_curly_double_quotes_to_ascii(self):
        assert normalize_text("\u201cQuoted\u201d") == '"Quoted"'

    def test_normalizes_en_and_em_dashes_to_hyphen(self):
        assert normalize_text("Fig. 3 \u2013 Water cycle") == "Fig. 3 - Water cycle"
        assert normalize_text("Fig. 3 \u2014 Water cycle") == "Fig. 3 - Water cycle"

    def test_normalizes_minus_sign_to_hyphen(self):
        assert normalize_text("5\u22123") == "5-3"

    def test_strips_zero_width_and_invisible_characters(self):
        assert normalize_text("Hydro\u200bgen") == "Hydrogen"
        assert normalize_text("Hydro\ufeffgen") == "Hydrogen"
        assert normalize_text("Hydro\u00adgen") == "Hydrogen"

    def test_unicode_nfkc_normalization_of_compatibility_forms(self):
        # U+FF28 FULLWIDTH LATIN CAPITAL LETTER H -> "H" under NFKC
        assert normalize_text("\uff28ydrogen") == "Hydrogen"

    def test_preserves_case(self):
        # normalize_text is not a casefold -- canonical_lookup_key is
        # responsible for casing, not this function.
        assert normalize_text("Hydrogen Ion") == "Hydrogen Ion"

    def test_empty_string_returns_empty_string(self):
        assert normalize_text("") == ""

    def test_non_string_input_returns_empty_string(self):
        assert normalize_text(None) == ""
        assert normalize_text(123) == ""

    def test_idempotent(self):
        value = "  Newton\u2019s   Law \u2014 Test  "
        once = normalize_text(value)
        twice = normalize_text(once)
        assert once == twice

    def test_does_not_alter_internal_hyphens(self):
        # a genuine hyphen inside a word must never be stripped --
        # only edge punctuation is touched, and only by
        # canonical_lookup_key, never by normalize_text.
        assert normalize_text("co-operative") == "co-operative"


# --------------------------------------------------------------------------
# canonical_lookup_key() -- deterministic lookup key derivation
# --------------------------------------------------------------------------

class TestCanonicalLookupKey:
    def test_casefolds(self):
        assert canonical_lookup_key("Hydrogen Ion") == "hydrogen ion"

    def test_applies_full_normalize_text_pipeline_first(self):
        assert canonical_lookup_key("  Hydrogen\u2019s   ION  ") == "hydrogen's ion"

    def test_strips_edge_punctuation(self):
        assert canonical_lookup_key("(Hydrogen Ion).") == "hydrogen ion"

    def test_does_not_strip_internal_punctuation(self):
        assert canonical_lookup_key("Co-operative Society") == "co-operative society"

    def test_none_for_none_input(self):
        assert canonical_lookup_key(None) is None

    def test_none_for_empty_string(self):
        assert canonical_lookup_key("") is None

    def test_none_for_whitespace_only(self):
        assert canonical_lookup_key("   ") is None

    def test_none_for_punctuation_only(self):
        assert canonical_lookup_key("...") is None

    def test_deterministic_across_calls(self):
        value = "Hydrogen Ion"
        assert canonical_lookup_key(value) == canonical_lookup_key(value)

    def test_different_raw_forms_fold_to_the_same_key(self):
        # curly vs straight apostrophe, extra whitespace, different case
        # -- all legitimate variants of the *same* string should
        # produce the same lookup key (this is normalization, not alias
        # resolution: these are the same characters up to formatting).
        assert canonical_lookup_key("Newton\u2019s Law") == canonical_lookup_key("  newton's   LAW  ")


# --------------------------------------------------------------------------
# compute_normalization() -- per-item field derivation
# --------------------------------------------------------------------------

class TestComputeNormalizationCore:
    def test_returns_canonical_lookup_key_from_name(self):
        item = make_concept(name="Hydrogen Ion")
        result = compute_normalization(item)
        assert result["canonical_lookup_key"] == "hydrogen ion"

    def test_returns_canonical_lookup_key_from_title(self):
        item = make_figure(title="Fig. 3\u2014Water Cycle")
        result = compute_normalization(item)
        assert result["canonical_lookup_key"] == "fig. 3-water cycle"

    def test_returns_canonical_lookup_key_from_term(self):
        item = make_definition(term="Inflation")
        result = compute_normalization(item)
        assert result["canonical_lookup_key"] == "inflation"

    def test_lookup_key_none_when_no_display_name_field(self):
        item = {"id": "x1", "urn": "urn:x", "object_type": "table"}
        result = compute_normalization(item)
        assert result["canonical_lookup_key"] is None

    def test_does_not_mutate_input_item(self):
        item = make_concept(name="Photosynthesis")
        before = copy.deepcopy(item)
        compute_normalization(item)
        assert item == before

    def test_never_raises_on_malformed_item(self):
        # missing every expected key -- should degrade to None fields,
        # never raise.
        result = compute_normalization({})
        assert result["canonical_lookup_key"] is None


class TestCanonicalAliases:
    def test_none_when_no_aliases_key(self):
        item = make_definition(term="Inflation")
        assert "aliases" not in item
        result = compute_normalization(item)
        assert "canonical_aliases" not in result

    def test_normalizes_each_alias_string(self):
        item = make_concept(name="Hydrogen Ion", aliases=["Hydrogen\u2019s Ion", "H+   ion"])
        result = compute_normalization(item)
        assert result["canonical_aliases"] == ["Hydrogen's Ion", "H+ ion"]

    def test_preserves_alias_order(self):
        item = make_concept(name="X", aliases=["Zebra", "Apple", "Mango"])
        result = compute_normalization(item)
        assert result["canonical_aliases"] == ["Zebra", "Apple", "Mango"]

    def test_preserves_alias_count_including_duplicates(self):
        # normalization must not deduplicate or merge -- that is alias
        # resolution, explicitly out of scope.
        item = make_concept(name="X", aliases=["Same", "Same"])
        result = compute_normalization(item)
        assert result["canonical_aliases"] == ["Same", "Same"]

    def test_empty_aliases_list_stays_empty(self):
        item = make_concept(name="X", aliases=[])
        result = compute_normalization(item)
        assert result["canonical_aliases"] == []

    def test_never_invents_aliases_from_nothing(self):
        item = make_concept(name="X", aliases=[])
        result = compute_normalization(item)
        assert result["canonical_aliases"] == []
        assert len(result["canonical_aliases"]) == 0


class TestNormalizationMetadata:
    def test_records_version(self):
        item = make_concept(name="X")
        result = compute_normalization(item)
        assert result["normalization"]["version"] == NORMALIZATION_VERSION

    def test_status_normalized_when_lookup_key_present(self):
        item = make_concept(name="Photosynthesis")
        result = compute_normalization(item)
        assert result["normalization"]["status"] == "normalized"

    def test_status_skipped_when_no_display_name(self):
        item = {"id": "x1", "urn": "urn:x", "object_type": "table"}
        result = compute_normalization(item)
        assert result["normalization"]["status"] == "skipped_no_display_name"

    def test_normalized_fields_lists_canonical_lookup_key_when_present(self):
        item = make_definition(term="Inflation")
        result = compute_normalization(item)
        assert "canonical_lookup_key" in result["normalization"]["normalized_fields"]
        assert "canonical_aliases" not in result["normalization"]["normalized_fields"]

    def test_normalized_fields_lists_canonical_aliases_when_present(self):
        item = make_concept(name="X", aliases=["Y"])
        result = compute_normalization(item)
        assert "canonical_aliases" in result["normalization"]["normalized_fields"]

    def test_normalized_at_is_iso_timestamp_string(self):
        item = make_concept(name="X")
        result = compute_normalization(item)
        # Should be parseable as an ISO-8601 timestamp.
        from datetime import datetime
        datetime.fromisoformat(result["normalization"]["normalized_at"])


# --------------------------------------------------------------------------
# normalize_item() -- in-place mutation, additive-only guarantees
# --------------------------------------------------------------------------

class TestNormalizeItemInPlace:
    def test_mutates_item_in_place_and_returns_it(self):
        item = make_concept(name="Photosynthesis")
        result = normalize_item(item)
        assert result is item
        assert item["canonical_lookup_key"] == "photosynthesis"

    def test_does_not_overwrite_existing_unrelated_keys(self):
        item = make_concept(name="Photosynthesis", importance="high")
        normalize_item(item)
        assert item["importance"] == "high"
        assert item["name"] == "Photosynthesis"
        assert item["id"] == "c1"
        assert item["urn"] == "urn:concept:Photosynthesis"

    def test_does_not_touch_b1b_enrichment_fields(self):
        # Simulate an already-enriched item (B1b ran first, as it always
        # does in the real pipeline) and confirm normalization adds only
        # its own keys.
        item = make_concept(name="Photosynthesis")
        item["canonical_display_name"] = "Photosynthesis"
        item["normalized_name"] = "photosynthesis"
        item["educational_role"] = "concept"
        normalize_item(item)
        assert item["canonical_display_name"] == "Photosynthesis"
        assert item["normalized_name"] == "photosynthesis"
        assert item["educational_role"] == "concept"
        assert item["canonical_lookup_key"] == "photosynthesis"

    def test_non_dict_item_returned_unchanged(self):
        class Sentinel:
            pass
        s = Sentinel()
        assert normalize_item(s) is s

    def test_idempotent_except_timestamp(self):
        item = make_concept(name="Photosynthesis")
        normalize_item(item)
        first_key = item["canonical_lookup_key"]
        first_aliases = item["canonical_aliases"]
        normalize_item(item)
        assert item["canonical_lookup_key"] == first_key
        assert item["canonical_aliases"] == first_aliases

    def test_never_changes_id_or_urn(self):
        item = make_concept(id_="c99", name="X")
        original_id, original_urn = item["id"], item["urn"]
        normalize_item(item)
        assert item["id"] == original_id
        assert item["urn"] == original_urn


# --------------------------------------------------------------------------
# normalize_registry() / normalize_registries() -- registry-level API
# --------------------------------------------------------------------------

class TestNormalizeRegistry:
    def test_normalizes_every_item_in_registry(self):
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept(id_="c1", name="Alpha"),
                      make_concept(id_="c2", name="Beta")],
            definitions=[], glossary=[], figures=[], diagrams=[], tables=[],
            equations=[], activities=[], boxes=[], warnings=[], notes=[],
            examples=[],
        )
        count = normalize_registry(manager.get("concepts"))
        assert count == 2
        assert manager.get("concepts").get_by_id("c1")["canonical_lookup_key"] == "alpha"
        assert manager.get("concepts").get_by_id("c2")["canonical_lookup_key"] == "beta"

    def test_preserves_insertion_order(self):
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept(id_="c1", name="Zebra"),
                      make_concept(id_="c2", name="Apple")],
            definitions=[], glossary=[], figures=[], diagrams=[], tables=[],
            equations=[], activities=[], boxes=[], warnings=[], notes=[],
            examples=[],
        )
        normalize_registry(manager.get("concepts"))
        ids_in_order = [item["id"] for item in manager.get("concepts").values()]
        assert ids_in_order == ["c1", "c2"]

    def test_safe_to_run_twice(self):
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept(id_="c1", name="Alpha")],
            definitions=[], glossary=[], figures=[], diagrams=[], tables=[],
            equations=[], activities=[], boxes=[], warnings=[], notes=[],
            examples=[],
        )
        normalize_registry(manager.get("concepts"))
        normalize_registry(manager.get("concepts"))
        assert manager.get("concepts").get_by_id("c1")["canonical_lookup_key"] == "alpha"


class TestNormalizeRegistries:
    def test_normalizes_every_registry_manager_owns(self):
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept(id_="c1", name="Alpha")],
            definitions=[make_definition(id_="d1", term="Inflation")],
            glossary=[], figures=[make_figure(id_="f1", title="Fig 1")],
            diagrams=[], tables=[], equations=[], activities=[], boxes=[],
            warnings=[], notes=[], examples=[],
        )
        counts = normalize_registries(manager)
        assert counts["concepts"] == 1
        assert counts["definitions"] == 1
        assert counts["figures"] == 1
        assert manager.get("concepts").get_by_id("c1")["canonical_lookup_key"] == "alpha"
        assert manager.get("definitions").get_by_id("d1")["canonical_lookup_key"] == "inflation"
        assert manager.get("figures").get_by_id("f1")["canonical_lookup_key"] == "fig 1"

    def test_runs_after_enrichment_without_conflict(self):
        # Confirms B1c composes cleanly on top of B1b: enrich first (as
        # pipeline.py always does), then normalize, and check both
        # passes' fields coexist on the same item.
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept(id_="c1", name="Photosynthesis")],
            definitions=[], glossary=[], figures=[], diagrams=[], tables=[],
            equations=[], activities=[], boxes=[], warnings=[], notes=[],
            examples=[],
        )
        enrich_registries(manager)
        normalize_registries(manager)
        item = manager.get("concepts").get_by_id("c1")
        assert item["canonical_display_name"] == "Photosynthesis"  # B1b field
        assert item["canonical_lookup_key"] == "photosynthesis"    # B1c field
        assert "normalization" in item
        assert "registry_metadata" in item  # B1b field untouched


# --------------------------------------------------------------------------
# Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_normalization_fields_is_a_stable_public_list(self):
        assert NORMALIZATION_FIELDS == [
            "canonical_lookup_key",
            "canonical_aliases",
            "normalization",
        ]

    def test_ids_and_urns_never_change(self):
        item = make_concept(id_="c1", name="Water Cycle")
        original = copy.deepcopy(item)
        normalize_item(item)
        assert item["id"] == original["id"]
        assert item["urn"] == original["urn"]

    def test_existing_keys_are_never_overwritten_with_different_values(self):
        item = make_concept(name="Water Cycle", importance="high", difficulty="low")
        before = copy.deepcopy(item)
        normalize_item(item)
        for key, value in before.items():
            assert item[key] == value

    def test_output_is_json_serializable(self):
        import json
        item = make_concept(name="Photosynthesis", aliases=["Photo synthesis"])
        normalize_item(item)
        json.dumps(item)  # should not raise