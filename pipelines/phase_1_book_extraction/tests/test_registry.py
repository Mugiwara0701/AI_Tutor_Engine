"""
tests/test_registry.py — unit tests for Phase B0's
compiler.registry.CanonicalRegistry.

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from compiler.registry import CanonicalRegistry, RegistryDiagnostic, RegistryStatistics
from compiler.exceptions import (
    RegistryError,
    DuplicateIdError,
    DuplicateUrnError,
    DuplicateNameError,
    ItemNotFoundError,
    RegistrySerializationError,
)


def make_item(id_, urn=None, name=None, **extra):
    d = {"id": id_}
    if urn is not None:
        d["urn"] = urn
    if name is not None:
        d["name"] = name
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# Registry creation
# --------------------------------------------------------------------------
class TestRegistryCreation:
    def test_empty_registry_has_zero_size(self):
        r = CanonicalRegistry(name="things")
        assert r.size() == 0
        assert len(r) == 0
        assert r.values() == []
        assert r.items() == []
        assert r.ids() == []

    def test_registry_name_property(self):
        r = CanonicalRegistry(name="concepts")
        assert r.name == "concepts"

    def test_default_name_is_registry(self):
        r = CanonicalRegistry()
        assert r.name == "registry"


# --------------------------------------------------------------------------
# Insertion
# --------------------------------------------------------------------------
class TestInsertion:
    def test_insert_returns_id(self):
        r = CanonicalRegistry()
        returned_id = r.insert(make_item("a1", name="Alpha"))
        assert returned_id == "a1"

    def test_insert_increases_size(self):
        r = CanonicalRegistry()
        r.insert(make_item("a1"))
        r.insert(make_item("a2"))
        assert r.size() == 2

    def test_insert_item_without_id_raises(self):
        r = CanonicalRegistry()
        with pytest.raises(RegistryError):
            r.insert({"name": "No id here"})

    def test_insert_item_with_empty_id_raises(self):
        r = CanonicalRegistry()
        with pytest.raises(RegistryError):
            r.insert({"id": "", "name": "Empty id"})

    def test_insert_without_urn_or_name_is_allowed(self):
        r = CanonicalRegistry()
        r.insert({"id": "bare-1"})
        assert r.contains("bare-1")

    def test_insert_accepts_pydantic_model_via_attribute_access(self):
        class Item(BaseModel):
            id: str
            urn: str | None = None
            name: str | None = None

        r = CanonicalRegistry()
        r.insert(Item(id="p1", urn="urn:p1", name="Pydantic Item"))
        assert r.get_by_id("p1").name == "Pydantic Item"
        assert r.get_by_urn("urn:p1").id == "p1"
        assert r.get_by_name("pydantic item").id == "p1"


# --------------------------------------------------------------------------
# Duplicate detection / rejection
# --------------------------------------------------------------------------
class TestDuplicateDetection:
    def test_duplicate_id_raises_and_does_not_overwrite(self):
        r = CanonicalRegistry()
        r.insert(make_item("dup", name="Original"))
        with pytest.raises(DuplicateIdError):
            r.insert(make_item("dup", name="Replacement"))
        assert r.get_by_id("dup")["name"] == "Original"

    def test_duplicate_urn_raises(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", urn="urn:shared"))
        with pytest.raises(DuplicateUrnError):
            r.insert(make_item("b", urn="urn:shared"))
        assert r.size() == 1

    def test_duplicate_name_raises_case_insensitively_by_default(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Photosynthesis"))
        with pytest.raises(DuplicateNameError):
            r.insert(make_item("b", name="photosynthesis"))
        assert r.size() == 1

    def test_case_sensitive_names_when_configured(self):
        r = CanonicalRegistry(case_insensitive_names=False)
        r.insert(make_item("a", name="Photosynthesis"))
        r.insert(make_item("b", name="photosynthesis"))  # different case -> allowed
        assert r.size() == 2

    def test_insert_or_report_does_not_raise_on_duplicate(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Alpha"))
        diagnostic = r.insert_or_report(make_item("a", name="Alpha again"))
        assert isinstance(diagnostic, RegistryDiagnostic)
        assert diagnostic.ok is False
        assert diagnostic.kind == "duplicate_id"
        assert r.size() == 1  # still not overwritten

    def test_insert_or_report_returns_ok_diagnostic_on_success(self):
        r = CanonicalRegistry()
        diagnostic = r.insert_or_report(make_item("a", name="Alpha"))
        assert diagnostic.ok is True
        assert diagnostic.kind == "ok"

    def test_duplicate_report_accumulates_every_conflict(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", urn="urn:a", name="Alpha"))
        r.insert_or_report(make_item("a", name="dup id"))
        r.insert_or_report(make_item("b", urn="urn:a", name="dup urn"))
        r.insert_or_report(make_item("c", name="alpha"))  # dup name
        report = r.duplicate_report()
        assert [d.kind for d in report] == ["duplicate_id", "duplicate_urn", "duplicate_name"]

    def test_duplicate_id_does_not_raise_urn_or_name_errors_first(self):
        # id collision should be detected before urn/name are even
        # considered, since id is the primary key.
        r = CanonicalRegistry()
        r.insert(make_item("a", urn="urn:a", name="Alpha"))
        with pytest.raises(DuplicateIdError):
            r.insert(make_item("a", urn="urn:different", name="Different"))


# --------------------------------------------------------------------------
# Lookup: get_by_id / get_by_urn / get_by_name / lookup()
# --------------------------------------------------------------------------
class TestLookup:
    @pytest.fixture
    def populated(self):
        r = CanonicalRegistry()
        r.insert(make_item("a1", urn="urn:a1", name="Alpha"))
        r.insert(make_item("b2", urn="urn:b2", name="Beta"))
        return r

    def test_get_by_id_hit(self, populated):
        assert populated.get_by_id("a1")["name"] == "Alpha"

    def test_get_by_id_miss_returns_none(self, populated):
        assert populated.get_by_id("nonexistent") is None

    def test_get_by_urn_hit(self, populated):
        assert populated.get_by_urn("urn:b2")["id"] == "b2"

    def test_get_by_urn_miss_returns_none(self, populated):
        assert populated.get_by_urn("urn:nonexistent") is None

    def test_get_by_name_hit_case_insensitive(self, populated):
        assert populated.get_by_name("ALPHA")["id"] == "a1"

    def test_get_by_name_miss_returns_none(self, populated):
        assert populated.get_by_name("Gamma") is None

    def test_lookup_dispatches_by_id(self, populated):
        assert populated.lookup(id="a1")["id"] == "a1"

    def test_lookup_dispatches_by_urn(self, populated):
        assert populated.lookup(urn="urn:b2")["id"] == "b2"

    def test_lookup_dispatches_by_name(self, populated):
        assert populated.lookup(name="Alpha")["id"] == "a1"

    def test_lookup_requires_exactly_one_kwarg(self, populated):
        with pytest.raises(ValueError):
            populated.lookup()

    def test_lookup_rejects_multiple_kwargs(self, populated):
        with pytest.raises(ValueError):
            populated.lookup(id="a1", name="Alpha")

    def test_contains(self, populated):
        assert populated.contains("a1") is True
        assert populated.contains("nonexistent") is False
        assert "a1" in populated
        assert "nonexistent" not in populated


# --------------------------------------------------------------------------
# Update
# --------------------------------------------------------------------------
class TestUpdate:
    def test_update_replaces_value(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Old"))
        r.update(make_item("a", name="New"))
        assert r.get_by_id("a")["name"] == "New"
        assert r.size() == 1

    def test_update_missing_id_raises(self):
        r = CanonicalRegistry()
        with pytest.raises(ItemNotFoundError):
            r.update(make_item("nonexistent", name="X"))

    def test_update_rewires_name_index(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Old Name"))
        r.update(make_item("a", name="New Name"))
        assert r.get_by_name("old name") is None
        assert r.get_by_name("new name")["id"] == "a"

    def test_update_rewires_urn_index(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", urn="urn:old"))
        r.update(make_item("a", urn="urn:new"))
        assert r.get_by_urn("urn:old") is None
        assert r.get_by_urn("urn:new")["id"] == "a"

    def test_update_to_urn_owned_by_different_id_raises(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", urn="urn:a"))
        r.insert(make_item("b", urn="urn:b"))
        with pytest.raises(DuplicateUrnError):
            r.update(make_item("b", urn="urn:a"))

    def test_update_to_name_owned_by_different_id_raises(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Alpha"))
        r.insert(make_item("b", name="Beta"))
        with pytest.raises(DuplicateNameError):
            r.update(make_item("b", name="Alpha"))

    def test_update_keeping_same_name_does_not_self_conflict(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Alpha", urn="urn:a"))
        # re-updating with the same name/urn should not raise against itself
        r.update(make_item("a", name="Alpha", urn="urn:a", extra="field"))
        assert r.get_by_id("a")["extra"] == "field"


# --------------------------------------------------------------------------
# Upsert
# --------------------------------------------------------------------------
class TestUpsert:
    def test_upsert_inserts_new_item(self):
        r = CanonicalRegistry()
        r.upsert(make_item("a", name="Alpha"))
        assert r.contains("a")
        assert r.statistics().inserts == 1
        assert r.statistics().updates == 0

    def test_upsert_updates_existing_item(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Alpha"))
        r.upsert(make_item("a", name="Alpha v2"))
        assert r.get_by_id("a")["name"] == "Alpha v2"
        assert r.statistics().updates == 1


# --------------------------------------------------------------------------
# Deletion
# --------------------------------------------------------------------------
class TestDeletion:
    def test_remove_returns_item_and_shrinks_registry(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Alpha"))
        removed = r.remove("a")
        assert removed["id"] == "a"
        assert r.size() == 0
        assert not r.contains("a")

    def test_remove_missing_id_raises(self):
        r = CanonicalRegistry()
        with pytest.raises(ItemNotFoundError):
            r.remove("nonexistent")

    def test_remove_clears_urn_and_name_indexes(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", urn="urn:a", name="Alpha"))
        r.remove("a")
        assert r.get_by_urn("urn:a") is None
        assert r.get_by_name("Alpha") is None
        # id should be reusable after removal
        r.insert(make_item("a", urn="urn:a", name="Alpha"))
        assert r.contains("a")

    def test_clear_empties_registry_but_keeps_lifetime_stats(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Alpha"))
        r.insert(make_item("b", name="Beta"))
        r.clear()
        assert r.size() == 0
        assert r.values() == []
        # lifetime insert counter is not reset by clear()
        assert r.statistics().inserts == 2


# --------------------------------------------------------------------------
# Deterministic ordering
# --------------------------------------------------------------------------
class TestDeterministicOrdering:
    def test_iteration_follows_insertion_order(self):
        r = CanonicalRegistry()
        for id_ in ["z", "a", "m"]:
            r.insert(make_item(id_))
        assert [item["id"] for item in r] == ["z", "a", "m"]

    def test_values_follows_insertion_order(self):
        r = CanonicalRegistry()
        for id_ in ["z", "a", "m"]:
            r.insert(make_item(id_))
        assert [item["id"] for item in r.values()] == ["z", "a", "m"]

    def test_items_follows_insertion_order(self):
        r = CanonicalRegistry()
        for id_ in ["z", "a", "m"]:
            r.insert(make_item(id_))
        assert [id_ for id_, _ in r.items()] == ["z", "a", "m"]

    def test_ids_follows_insertion_order(self):
        r = CanonicalRegistry()
        for id_ in ["z", "a", "m"]:
            r.insert(make_item(id_))
        assert r.ids() == ["z", "a", "m"]

    def test_order_survives_update(self):
        r = CanonicalRegistry()
        for id_ in ["z", "a", "m"]:
            r.insert(make_item(id_))
        r.update(make_item("a", name="renamed"))
        assert r.ids() == ["z", "a", "m"]

    def test_two_registries_built_in_same_order_produce_identical_serialization(self):
        r1 = CanonicalRegistry(name="things")
        r2 = CanonicalRegistry(name="things")
        for id_ in ["x1", "x2", "x3"]:
            r1.insert(make_item(id_, name=f"Name {id_}"))
            r2.insert(make_item(id_, name=f"Name {id_}"))
        assert r1.serialize() == r2.serialize()
        assert r1.to_json() == r2.to_json()


# --------------------------------------------------------------------------
# Serialization / deserialization
# --------------------------------------------------------------------------
class TestSerialization:
    def test_serialize_shape(self):
        r = CanonicalRegistry(name="concepts")
        r.insert(make_item("a", urn="urn:a", name="Alpha"))
        blob = r.serialize()
        assert blob["registry"] == "concepts"
        assert blob["version"] == 1
        assert blob["items"] == [{"id": "a", "urn": "urn:a", "name": "Alpha"}]

    def test_serialize_is_json_compatible(self):
        r = CanonicalRegistry(name="concepts")
        r.insert(make_item("a", name="Alpha"))
        # must not raise
        text = json.dumps(r.serialize())
        assert "Alpha" in text

    def test_to_json_round_trips_via_from_json(self):
        r = CanonicalRegistry(name="concepts")
        r.insert(make_item("a", urn="urn:a", name="Alpha"))
        r.insert(make_item("b", urn="urn:b", name="Beta"))
        text = r.to_json()
        restored = CanonicalRegistry.from_json(text)
        assert restored.name == "concepts"
        assert restored.ids() == ["a", "b"]
        assert restored.get_by_name("Beta")["id"] == "b"

    def test_deserialize_preserves_item_order(self):
        r = CanonicalRegistry(name="concepts")
        for id_ in ["z", "a", "m"]:
            r.insert(make_item(id_))
        restored = CanonicalRegistry.deserialize(r.serialize())
        assert restored.ids() == ["z", "a", "m"]

    def test_deserialize_missing_items_key_raises(self):
        with pytest.raises(RegistrySerializationError):
            CanonicalRegistry.deserialize({"registry": "x"})

    def test_deserialize_rejects_duplicate_items_in_payload(self):
        payload = {
            "registry": "concepts",
            "items": [{"id": "a", "name": "Alpha"}, {"id": "a", "name": "Alpha again"}],
        }
        with pytest.raises(DuplicateIdError):
            CanonicalRegistry.deserialize(payload)

    def test_default_serializer_uses_model_dump_for_pydantic(self):
        class Item(BaseModel):
            id: str
            name: str

        r = CanonicalRegistry()
        r.insert(Item(id="p1", name="Pydantic"))
        blob = r.serialize()
        assert blob["items"] == [{"id": "p1", "name": "Pydantic"}]

    def test_serializer_raises_for_unsupported_type(self):
        class Unsupported:
            def __init__(self):
                self.id = "u1"

        r = CanonicalRegistry()
        r.insert(Unsupported())
        with pytest.raises(RegistrySerializationError):
            r.serialize()

    def test_custom_serializer_and_deserializer_round_trip(self):
        class Item:
            def __init__(self, id_, name):
                self.id = id_
                self.name = name

        def ser(item):
            return {"id": item.id, "name": item.name}

        def deser(data):
            return Item(data["id"], data["name"])

        r = CanonicalRegistry(serializer=ser, deserializer=deser)
        r.insert(Item("a", "Alpha"))
        blob = r.serialize()
        restored = CanonicalRegistry.deserialize(blob, serializer=ser, deserializer=deser)
        assert restored.get_by_id("a").name == "Alpha"


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------
class TestStatistics:
    def test_statistics_initial_state(self):
        r = CanonicalRegistry(name="concepts")
        stats = r.statistics()
        assert isinstance(stats, RegistryStatistics)
        assert stats.name == "concepts"
        assert stats.size == 0
        assert stats.inserts == 0

    def test_statistics_tracks_inserts(self):
        r = CanonicalRegistry()
        r.insert(make_item("a"))
        r.insert(make_item("b"))
        assert r.statistics().inserts == 2
        assert r.statistics().size == 2

    def test_statistics_tracks_updates_and_removals(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", name="Alpha"))
        r.update(make_item("a", name="Alpha2"))
        r.remove("a")
        stats = r.statistics()
        assert stats.updates == 1
        assert stats.removals == 1
        assert stats.size == 0

    def test_statistics_tracks_duplicate_attempts(self):
        r = CanonicalRegistry()
        r.insert(make_item("a", urn="urn:a", name="Alpha"))
        r.insert_or_report(make_item("a", name="dup id"))
        r.insert_or_report(make_item("b", urn="urn:a"))
        r.insert_or_report(make_item("c", name="alpha"))
        stats = r.statistics()
        assert stats.duplicate_id_attempts == 1
        assert stats.duplicate_urn_attempts == 1
        assert stats.duplicate_name_attempts == 1

    def test_statistics_tracks_lookup_hits_and_misses(self):
        r = CanonicalRegistry()
        r.insert(make_item("a"))
        r.get_by_id("a")       # hit
        r.get_by_id("missing")  # miss
        stats = r.statistics()
        assert stats.lookups == 2
        assert stats.lookup_hits == 1
        assert stats.lookup_misses == 1

    def test_statistics_to_dict(self):
        r = CanonicalRegistry(name="concepts")
        r.insert(make_item("a"))
        as_dict = r.statistics().to_dict()
        assert as_dict["name"] == "concepts"
        assert as_dict["size"] == 1

    def test_statistics_includes_approx_memory_bytes(self):
        r = CanonicalRegistry()
        r.insert(make_item("a"))
        stats = r.statistics()
        assert isinstance(stats.approx_memory_bytes, int)
        assert stats.approx_memory_bytes > 0

    def test_statistics_size_reflects_clear(self):
        r = CanonicalRegistry()
        r.insert(make_item("a"))
        r.clear()
        assert r.statistics().size == 0
        assert r.statistics().inserts == 1  # lifetime counter unaffected


# --------------------------------------------------------------------------
# Backward compatibility with the pre-B0 concept_registry pattern
# (pipeline.py's hand-rolled dict-keyed-by-lowercase-name registry).
# --------------------------------------------------------------------------
class TestBackwardCompatibilityWithExistingConceptRegistryShape:
    def test_can_hold_canonical_fields_shaped_dicts(self):
        # Mirrors the exact shape modules/canonical.py::canonical_fields()
        # produces (id/urn/object_type/... top-level dict, plus per-type
        # extra keys such as "name" for a concept record).
        canonical_like = {
            "id": "photosynthesis-chapter-1-a1b2c3",
            "urn": "urn:ncert-kg:book:ch1:concept:photosynthesis",
            "object_type": "concept",
            "schema_version": "2.0.0",
            "name": "Photosynthesis",
            "topics": ["topic-1"],
        }
        r = CanonicalRegistry(name="concepts")
        r.insert(canonical_like)
        assert r.get_by_name("photosynthesis")["object_type"] == "concept"
        assert r.get_by_id("photosynthesis-chapter-1-a1b2c3")["topics"] == ["topic-1"]

    def test_same_name_different_topic_is_deduplicated_like_pre_b0_registry(self):
        # Pre-B0 pattern: same concept name mentioned in two topics gets
        # ONE canonical record, with a `topics` list appended to -- not
        # two competing records. CanonicalRegistry's generic insert()
        # rejects a second insert with the same name outright; a caller
        # reproducing the "append topic to existing record" behavior is
        # expected to check contains()/get_by_name() first and update()
        # if found, exactly as pipeline.py's own loop already does today
        # for its hand-rolled dict.
        r = CanonicalRegistry(name="concepts")
        first = {"id": "c1", "name": "Photosynthesis", "topics": ["topic-1"]}
        r.insert(first)

        existing = r.get_by_name("Photosynthesis")
        assert existing is not None
        existing["topics"].append("topic-2")
        r.update(existing)

        assert r.get_by_name("Photosynthesis")["topics"] == ["topic-1", "topic-2"]
        assert r.size() == 1
