"""
tests/test_registry_manager.py — unit tests for Phase B0's
compiler.registry_manager.RegistryManager.

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import pytest

from compiler.registry import CanonicalRegistry, RegistryStatistics
from compiler.registry_manager import RegistryManager
from compiler.exceptions import RegistryError, ItemNotFoundError


def make_item(id_, name=None, **extra):
    d = {"id": id_}
    if name is not None:
        d["name"] = name
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# Manager creation / registry lifecycle
# --------------------------------------------------------------------------
class TestRegistryManagerLifecycle:
    def test_new_manager_is_empty(self):
        mgr = RegistryManager()
        assert len(mgr) == 0
        assert mgr.names() == []
        assert mgr.total_size() == 0

    def test_create_returns_new_registry(self):
        mgr = RegistryManager()
        registry = mgr.create("concepts")
        assert isinstance(registry, CanonicalRegistry)
        assert registry.name == "concepts"
        assert len(mgr) == 1

    def test_create_duplicate_name_raises(self):
        mgr = RegistryManager()
        mgr.create("concepts")
        with pytest.raises(RegistryError):
            mgr.create("concepts")

    def test_register_takes_ownership_of_existing_registry(self):
        mgr = RegistryManager()
        registry = CanonicalRegistry(name="figures")
        mgr.register(registry)
        assert mgr.get("figures") is registry

    def test_register_duplicate_name_raises(self):
        mgr = RegistryManager()
        mgr.register(CanonicalRegistry(name="figures"))
        with pytest.raises(RegistryError):
            mgr.register(CanonicalRegistry(name="figures"))

    def test_get_missing_registry_raises(self):
        mgr = RegistryManager()
        with pytest.raises(ItemNotFoundError):
            mgr.get("nonexistent")

    def test_get_or_create_creates_when_missing(self):
        mgr = RegistryManager()
        registry = mgr.get_or_create("concepts")
        assert registry.name == "concepts"
        assert mgr.has("concepts")

    def test_get_or_create_returns_existing_when_present(self):
        mgr = RegistryManager()
        first = mgr.create("concepts")
        second = mgr.get_or_create("concepts")
        assert first is second

    def test_has_and_contains(self):
        mgr = RegistryManager()
        mgr.create("concepts")
        assert mgr.has("concepts") is True
        assert mgr.has("figures") is False
        assert "concepts" in mgr
        assert "figures" not in mgr

    def test_remove_unregisters_and_returns_registry(self):
        mgr = RegistryManager()
        registry = mgr.create("concepts")
        removed = mgr.remove("concepts")
        assert removed is registry
        assert not mgr.has("concepts")
        assert len(mgr) == 0

    def test_remove_missing_registry_raises(self):
        mgr = RegistryManager()
        with pytest.raises(ItemNotFoundError):
            mgr.remove("nonexistent")

    def test_names_reflects_registration_order(self):
        mgr = RegistryManager()
        mgr.create("z_registry")
        mgr.create("a_registry")
        mgr.create("m_registry")
        assert mgr.names() == ["z_registry", "a_registry", "m_registry"]

    def test_iteration_yields_registries(self):
        mgr = RegistryManager()
        mgr.create("concepts")
        mgr.create("figures")
        names = [registry.name for registry in mgr]
        assert names == ["concepts", "figures"]


# --------------------------------------------------------------------------
# Generic-ness: RegistryManager must not know about any educational
# object type.
# --------------------------------------------------------------------------
class TestRegistryManagerIsFullyGeneric:
    def test_manager_accepts_arbitrary_registry_names(self):
        mgr = RegistryManager()
        for name in ["concepts", "definitions", "equations", "anything_at_all"]:
            mgr.create(name)
        assert set(mgr.names()) == {"concepts", "definitions", "equations", "anything_at_all"}

    def test_manager_does_not_predeclare_any_registry(self):
        mgr = RegistryManager()
        # Phase B0: nothing is auto-created; every registry is explicit.
        assert mgr.names() == []


# --------------------------------------------------------------------------
# Aggregate reads
# --------------------------------------------------------------------------
class TestAggregateReads:
    def test_total_size_sums_across_registries(self):
        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        figures = mgr.create("figures")
        concepts.insert(make_item("c1"))
        concepts.insert(make_item("c2"))
        figures.insert(make_item("f1"))
        assert mgr.total_size() == 3

    def test_statistics_keyed_by_registry_name(self):
        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        concepts.insert(make_item("c1", name="Alpha"))
        stats = mgr.statistics()
        assert set(stats.keys()) == {"concepts"}
        assert isinstance(stats["concepts"], RegistryStatistics)
        assert stats["concepts"].size == 1

    def test_clear_single_registry_by_name(self):
        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        figures = mgr.create("figures")
        concepts.insert(make_item("c1"))
        figures.insert(make_item("f1"))
        mgr.clear("concepts")
        assert concepts.size() == 0
        assert figures.size() == 1
        # registry still registered, just emptied
        assert mgr.has("concepts")

    def test_clear_all_registries(self):
        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        figures = mgr.create("figures")
        concepts.insert(make_item("c1"))
        figures.insert(make_item("f1"))
        mgr.clear()
        assert concepts.size() == 0
        assert figures.size() == 0
        assert mgr.has("concepts") and mgr.has("figures")


# --------------------------------------------------------------------------
# Serialization / deserialization
# --------------------------------------------------------------------------
class TestRegistryManagerSerialization:
    def test_serialize_shape(self):
        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        concepts.insert(make_item("c1", name="Alpha"))
        blob = mgr.serialize()
        assert set(blob["registries"].keys()) == {"concepts"}
        assert blob["registries"]["concepts"]["items"] == [{"id": "c1", "name": "Alpha"}]

    def test_serialize_multiple_registries_preserves_registration_order(self):
        mgr = RegistryManager()
        mgr.create("z_registry")
        mgr.create("a_registry")
        blob = mgr.serialize()
        assert list(blob["registries"].keys()) == ["z_registry", "a_registry"]

    def test_to_json_is_valid_json(self):
        import json

        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        concepts.insert(make_item("c1", name="Alpha"))
        text = mgr.to_json()
        parsed = json.loads(text)
        assert parsed["registries"]["concepts"]["items"][0]["name"] == "Alpha"

    def test_deserialize_round_trip(self):
        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        figures = mgr.create("figures")
        concepts.insert(make_item("c1", name="Alpha"))
        figures.insert(make_item("f1", name="Figure One"))

        restored = RegistryManager.deserialize(mgr.serialize())
        assert restored.names() == mgr.names()
        assert restored.get("concepts").get_by_id("c1")["name"] == "Alpha"
        assert restored.get("figures").get_by_id("f1")["name"] == "Figure One"

    def test_from_json_round_trip(self):
        mgr = RegistryManager()
        concepts = mgr.create("concepts")
        concepts.insert(make_item("c1", name="Alpha"))

        text = mgr.to_json()
        restored = RegistryManager.from_json(text)
        assert restored.get("concepts").get_by_id("c1")["name"] == "Alpha"

    def test_deserialize_missing_registries_key_raises(self):
        with pytest.raises(RegistryError):
            RegistryManager.deserialize({"not_registries": {}})

    def test_deserialize_empty_manager_round_trips(self):
        mgr = RegistryManager()
        restored = RegistryManager.deserialize(mgr.serialize())
        assert restored.names() == []
