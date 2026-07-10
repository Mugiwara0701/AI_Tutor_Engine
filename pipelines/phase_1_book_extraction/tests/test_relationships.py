"""
tests/test_relationships.py — unit tests for Phase B3's compiler.relationships
module (Canonical Semantic Relationship Resolution).

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import enrich_registries
from compiler.normalization import normalize_registries
from compiler.references import resolve_references
from compiler import state as compiler_state
from compiler.relationships import (
    RELATIONSHIP_RESOLUTION_VERSION,
    RELATIONSHIP_REGISTRY_NAME,
    RELATIONSHIP_TYPES,
    RelationshipRegistry,
    ensure_relationship_registry,
    resolve_relationships,
    _relationship_id,
)


# --------------------------------------------------------------------------
# Helpers -- same minimal stand-ins for the canonical envelope used by
# tests/test_references.py, extended with topic_ids where relevant since
# that is this module's own additional deterministic source field.
# --------------------------------------------------------------------------

def make_concept(id_="c1", name="Photosynthesis", aliases=None, topic_ids=None, **extra):
    d = {
        "id": id_, "urn": f"urn:concept:{id_}", "object_type": "concept",
        "name": name, "aliases": aliases if aliases is not None else [],
        "topic_ids": topic_ids if topic_ids is not None else [],
    }
    d.update(extra)
    return d


def make_definition(id_="d1", term="Inflation", topic_ids=None, **extra):
    d = {
        "id": id_, "urn": f"urn:definition:{id_}", "object_type": "definition",
        "term": term, "topic_ids": topic_ids if topic_ids is not None else [],
    }
    d.update(extra)
    return d


def make_glossary(id_="g1", term="Inflation", topic_ids=None, **extra):
    d = {
        "id": id_, "urn": f"urn:glossary:{id_}", "object_type": "glossary_entry",
        "term": term, "topic_ids": topic_ids if topic_ids is not None else [],
    }
    d.update(extra)
    return d


def make_figure(id_="f1", title="Fig 1", **extra):
    d = {
        "id": id_, "urn": f"urn:figure:{id_}", "object_type": "figure",
        "title": title,
    }
    d.update(extra)
    return d


def make_diagram(id_="dg1", title="Diagram 1", **extra):
    d = {
        "id": id_, "urn": f"urn:diagram:{id_}", "object_type": "diagram",
        "title": title,
    }
    d.update(extra)
    return d


def make_table(id_="tb1", title="Table 1", **extra):
    d = {
        "id": id_, "urn": f"urn:table:{id_}", "object_type": "table",
        "title": title,
    }
    d.update(extra)
    return d


def make_equation(id_="e1", latex="a^2", **extra):
    d = {
        "id": id_, "urn": f"urn:equation:{id_}", "object_type": "equation",
        "latex": latex,
    }
    d.update(extra)
    return d


def make_activity(id_="a1", title="Activity 1", **extra):
    d = {
        "id": id_, "urn": f"urn:activity:{id_}", "object_type": "activity",
        "title": title,
    }
    d.update(extra)
    return d


def make_topic(id_="t1", concepts=None, **extra):
    d = {"id": id_, "concepts": concepts if concepts is not None else []}
    d.update(extra)
    return d


def build_manager(**populate_kwargs):
    """create_registry_manager() -> populate_registries() ->
    enrich_registries() -> normalize_registries() -> resolve_references(),
    the exact pipeline.py order resolve_relationships() expects to run
    after."""
    manager = create_registry_manager()
    populate_registries(manager, **populate_kwargs)
    enrich_registries(manager)
    normalize_registries(manager)
    resolve_references(manager)
    return manager


def relationships_of_type(manager, rel_type):
    return [
        item for item in manager.get(RELATIONSHIP_REGISTRY_NAME).values()
        if item["type"] == rel_type
    ]


# --------------------------------------------------------------------------
# Relationship generation -- one class per relationship type, mirroring
# the task's own "RELATIONSHIP TYPES" list.
# --------------------------------------------------------------------------

class TestHasDefinitionRelationship:
    def test_generated_when_definition_resolves_to_concept(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "has_definition")
        assert len(rels) == 1
        assert rels[0]["source_type"] == "concept"
        assert rels[0]["source_id"] == "c1"
        assert rels[0]["target_type"] == "definition"
        assert rels[0]["target_id"] == "d1"

    def test_not_generated_when_definition_unresolved(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Something Else Entirely")],
        )
        resolve_relationships(manager)
        assert relationships_of_type(manager, "has_definition") == []

    def test_multiple_definitions_same_concept_generate_two_relationships(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[
                make_definition("d1", "Inflation", page=1),
                make_definition("d2", "Inflation", page=7),
            ],
        )
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "has_definition")
        assert {r["target_id"] for r in rels} == {"d1", "d2"}
        assert all(r["source_id"] == "c1" for r in rels)


class TestGlossaryConceptRelationships:
    def test_explains_and_described_by_both_generated(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            glossary=[make_glossary("g1", "Inflation")],
        )
        resolve_relationships(manager)
        explains = relationships_of_type(manager, "explains")
        described_by = relationships_of_type(manager, "described_by")
        assert len(explains) == 1
        assert explains[0]["source_type"] == "glossary_entry"
        assert explains[0]["source_id"] == "g1"
        assert explains[0]["target_type"] == "concept"
        assert explains[0]["target_id"] == "c1"

        assert len(described_by) == 1
        assert described_by[0]["source_type"] == "concept"
        assert described_by[0]["source_id"] == "c1"
        assert described_by[0]["target_type"] == "glossary_entry"
        assert described_by[0]["target_id"] == "g1"

    def test_not_generated_when_glossary_entry_unresolved(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            glossary=[make_glossary("g1", "Deflation")],
        )
        resolve_relationships(manager)
        assert relationships_of_type(manager, "explains") == []
        assert relationships_of_type(manager, "described_by") == []


class TestTopicContainsAndAppearsIn:
    def test_contains_generated_from_topic_concepts(self):
        manager = build_manager(concepts=[make_concept("c1", "Inflation")])
        topics = [make_topic("t1", concepts=["c1"])]
        resolve_relationships(manager, topics=topics)
        rels = relationships_of_type(manager, "contains")
        assert len(rels) == 1
        assert rels[0]["source_type"] == "topic"
        assert rels[0]["source_id"] == "t1"
        assert rels[0]["target_type"] == "concept"
        assert rels[0]["target_id"] == "c1"

    def test_appears_in_generated_from_concept_topic_ids(self):
        manager = build_manager(concepts=[make_concept("c1", "Inflation", topic_ids=["t1"])])
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "appears_in")
        assert len(rels) == 1
        assert rels[0]["source_type"] == "concept"
        assert rels[0]["source_id"] == "c1"
        assert rels[0]["target_type"] == "topic"
        assert rels[0]["target_id"] == "t1"

    def test_no_topics_argument_means_no_contains_relationships(self):
        manager = build_manager(concepts=[make_concept("c1", "Inflation")])
        resolve_relationships(manager)  # topics=None
        assert relationships_of_type(manager, "contains") == []

    def test_empty_topic_concepts_generates_nothing(self):
        manager = build_manager(concepts=[make_concept("c1", "Inflation")])
        topics = [make_topic("t1", concepts=[])]
        resolve_relationships(manager, topics=topics)
        assert relationships_of_type(manager, "contains") == []

    def test_topic_dict_never_mutated(self):
        manager = build_manager(concepts=[make_concept("c1", "Inflation")])
        topic = make_topic("t1", concepts=["c1"])
        before = copy.deepcopy(topic)
        resolve_relationships(manager, topics=[topic])
        assert topic == before


class TestBelongsToRelationships:
    def test_definition_belongs_to_topic(self):
        manager = build_manager(
            definitions=[make_definition("d1", "Inflation", topic_ids=["t1"])],
        )
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "belongs_to")
        assert any(
            r["source_type"] == "definition" and r["source_id"] == "d1"
            and r["target_type"] == "topic" and r["target_id"] == "t1"
            for r in rels
        )

    def test_glossary_belongs_to_topic(self):
        manager = build_manager(
            glossary=[make_glossary("g1", "Inflation", topic_ids=["t1"])],
        )
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "belongs_to")
        assert any(
            r["source_type"] == "glossary_entry" and r["source_id"] == "g1"
            and r["target_type"] == "topic" and r["target_id"] == "t1"
            for r in rels
        )

    def test_multiple_topic_ids_generate_one_relationship_each(self):
        manager = build_manager(
            definitions=[make_definition("d1", "Inflation", topic_ids=["t1", "t2"])],
        )
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "belongs_to")
        targets = {r["target_id"] for r in rels if r["source_id"] == "d1"}
        assert targets == {"t1", "t2"}

    def test_empty_topic_ids_generates_nothing(self):
        manager = build_manager(definitions=[make_definition("d1", "Inflation", topic_ids=[])])
        resolve_relationships(manager)
        assert relationships_of_type(manager, "belongs_to") == []


class TestConceptIdsGatedRelationships:
    """uses_concept / illustrates / teaches -- ONLY if deterministic
    concept_ids already exist on the source item (see task's own
    'ONLY if deterministic concept_ids already exist' qualifier)."""

    def test_equation_uses_concept_absent_by_default(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Ohm's Law")],
            equations=[make_equation("e1")],
        )
        resolve_relationships(manager)
        assert relationships_of_type(manager, "uses_concept") == []

    def test_figure_illustrates_absent_by_default(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Ohm's Law")],
            figures=[make_figure("f1")],
        )
        resolve_relationships(manager)
        assert relationships_of_type(manager, "illustrates") == []

    def test_equation_uses_concept_generated_when_concept_ids_present(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Ohm's Law")],
            equations=[make_equation("e1")],
        )
        # Simulate a future phase having deterministically populated
        # concept_ids on the equation (today always [] per B2 -- see
        # compiler/references.py). resolve_relationships() must react to
        # whatever concept_ids actually holds, never special-case "empty
        # today" as "always empty."
        equation = manager.get("equations").get_by_id("e1")
        equation["concept_ids"] = ["c1"]
        manager.get("equations").update(equation)
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "uses_concept")
        assert len(rels) == 1
        assert rels[0]["source_type"] == "equation"
        assert rels[0]["source_id"] == "e1"
        assert rels[0]["target_id"] == "c1"

    def test_figure_diagram_table_illustrate_when_concept_ids_present(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Ohm's Law")],
            figures=[make_figure("f1")],
            diagrams=[make_diagram("dg1")],
            tables=[make_table("tb1")],
        )
        for registry_name, item_id in (("figures", "f1"), ("diagrams", "dg1"), ("tables", "tb1")):
            registry = manager.get(registry_name)
            item = registry.get_by_id(item_id)
            item["concept_ids"] = ["c1"]
            registry.update(item)
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "illustrates")
        assert {(r["source_type"], r["source_id"]) for r in rels} == {
            ("figure", "f1"), ("diagram", "dg1"), ("table", "tb1"),
        }
        assert all(r["target_id"] == "c1" for r in rels)

    def test_activity_teaches_when_concept_ids_present(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Ohm's Law")],
            activities=[make_activity("a1")],
        )
        activity = manager.get("activities").get_by_id("a1")
        activity["concept_ids"] = ["c1"]
        manager.get("activities").update(activity)
        resolve_relationships(manager)
        rels = relationships_of_type(manager, "teaches")
        assert len(rels) == 1
        assert rels[0]["source_type"] == "activity"
        assert rels[0]["source_id"] == "a1"
        assert rels[0]["target_id"] == "c1"


# --------------------------------------------------------------------------
# Duplicate prevention
# --------------------------------------------------------------------------

class TestDuplicatePrevention:
    def test_calling_resolve_relationships_twice_does_not_duplicate(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        stats1 = resolve_relationships(manager)
        stats2 = resolve_relationships(manager)
        assert stats1["total"] == stats2["total"]
        assert relationships_of_type(manager, "has_definition")[0:1] and \
            len(relationships_of_type(manager, "has_definition")) == 1

    def test_repeated_generation_never_raises_duplicate_id_error(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation", topic_ids=["t1"])],
            definitions=[make_definition("d1", "Inflation", topic_ids=["t1"])],
            glossary=[make_glossary("g1", "Inflation", topic_ids=["t1"])],
        )
        topics = [make_topic("t1", concepts=["c1"])]
        # Three calls in a row must be fully idempotent and never raise.
        resolve_relationships(manager, topics=topics)
        resolve_relationships(manager, topics=topics)
        stats = resolve_relationships(manager, topics=topics)
        assert stats["total"] == manager.get(RELATIONSHIP_REGISTRY_NAME).size()


# --------------------------------------------------------------------------
# Deterministic IDs
# --------------------------------------------------------------------------

class TestDeterministicIds:
    def test_same_triple_always_yields_same_id(self):
        id1 = _relationship_id("relationship", "has_definition", "c1", "d1")
        id2 = _relationship_id("relationship", "has_definition", "c1", "d1")
        assert id1 == id2

    def test_different_triples_yield_different_ids(self):
        id1 = _relationship_id("relationship", "has_definition", "c1", "d1")
        id2 = _relationship_id("relationship", "has_definition", "c1", "d2")
        id3 = _relationship_id("relationship", "explains", "c1", "d1")
        assert len({id1, id2, id3}) == 3

    def test_relationship_id_stable_across_two_independent_runs(self):
        manager1 = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        manager2 = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager1)
        resolve_relationships(manager2)
        ids1 = sorted(manager1.get(RELATIONSHIP_REGISTRY_NAME).ids())
        ids2 = sorted(manager2.get(RELATIONSHIP_REGISTRY_NAME).ids())
        assert ids1 == ids2


# --------------------------------------------------------------------------
# Deterministic ordering
# --------------------------------------------------------------------------

class TestDeterministicOrdering:
    def test_insertion_order_stable_across_runs(self):
        def build_and_resolve():
            manager = build_manager(
                concepts=[make_concept("c1", "Inflation"), make_concept("c2", "Deflation")],
                definitions=[make_definition("d1", "Inflation"), make_definition("d2", "Deflation")],
            )
            resolve_relationships(manager)
            return manager.get(RELATIONSHIP_REGISTRY_NAME).ids()

        assert build_and_resolve() == build_and_resolve()

    def test_serialize_output_is_order_preserving(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
            glossary=[make_glossary("g1", "Inflation")],
        )
        resolve_relationships(manager)
        registry = manager.get(RELATIONSHIP_REGISTRY_NAME)
        serialized_ids = [item["id"] for item in registry.serialize()["items"]]
        assert serialized_ids == registry.ids()


# --------------------------------------------------------------------------
# Unresolved references
# --------------------------------------------------------------------------

class TestUnresolvedReferences:
    def test_unresolved_definition_generates_no_relationship(self):
        manager = build_manager(
            definitions=[make_definition("d1", "Nothing Matches")],
        )
        resolve_relationships(manager)
        assert manager.get(RELATIONSHIP_REGISTRY_NAME).size() == 0

    def test_missing_topic_ids_generates_no_appears_in_or_belongs_to(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager)
        assert relationships_of_type(manager, "appears_in") == []
        assert relationships_of_type(manager, "belongs_to") == []

    def test_empty_registries_produce_empty_relationship_registry(self):
        manager = build_manager()
        stats = resolve_relationships(manager)
        assert stats["total"] == 0
        assert manager.get(RELATIONSHIP_REGISTRY_NAME).size() == 0


# --------------------------------------------------------------------------
# Compiler state integration
# --------------------------------------------------------------------------

class TestCompilerStateIntegration:
    def teardown_method(self):
        compiler_state.reset_registry_state()

    def test_relationship_registry_reachable_via_current_registry_manager(self):
        compiler_state.reset_registry_state()
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager)
        compiler_state.set_current_registry_manager(manager)

        current = compiler_state.get_current_registry_manager()
        assert current is manager
        assert current.has(RELATIONSHIP_REGISTRY_NAME)
        assert current.get(RELATIONSHIP_REGISTRY_NAME).size() == 1

    def test_reset_registry_state_clears_relationship_visibility(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager)
        compiler_state.set_current_registry_manager(manager)
        compiler_state.reset_registry_state()
        assert compiler_state.get_current_registry_manager() is None


# --------------------------------------------------------------------------
# Registry integration
# --------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_ensure_relationship_registry_creates_once(self):
        manager = create_registry_manager()
        registry1 = ensure_relationship_registry(manager)
        registry2 = ensure_relationship_registry(manager)
        assert registry1 is registry2
        assert isinstance(registry1, RelationshipRegistry)
        assert manager.has(RELATIONSHIP_REGISTRY_NAME)

    def test_relationship_registry_is_a_canonical_registry_instance(self):
        manager = create_registry_manager()
        registry = ensure_relationship_registry(manager)
        assert registry.name == RELATIONSHIP_REGISTRY_NAME
        assert registry.size() == 0

    def test_relationship_registry_serializes_like_any_other_registry(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager)
        serialized = manager.get(RELATIONSHIP_REGISTRY_NAME).serialize()
        assert serialized["registry"] == RELATIONSHIP_REGISTRY_NAME
        assert isinstance(serialized["items"], list)
        assert len(serialized["items"]) == 1

    def test_relationship_registry_appears_in_manager_names(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager)
        assert RELATIONSHIP_REGISTRY_NAME in manager.names()

    def test_pre_existing_non_relationship_registry_with_same_name_raises(self):
        manager = create_registry_manager()
        # Simulate a misconfigured caller having already registered an
        # unrelated CanonicalRegistry under the reserved name.
        from compiler.registry import CanonicalRegistry
        manager.register(CanonicalRegistry(name=RELATIONSHIP_REGISTRY_NAME))
        with pytest.raises(TypeError):
            ensure_relationship_registry(manager)


# --------------------------------------------------------------------------
# Pipeline integration (structural / stats-shape checks -- full pipeline.py
# execution is out of scope for a unit test file)
# --------------------------------------------------------------------------

class TestPipelineIntegrationShape:
    def test_resolve_relationships_returns_stats_dict_with_expected_keys(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        stats = resolve_relationships(manager)
        assert stats["version"] == RELATIONSHIP_RESOLUTION_VERSION
        assert "by_type" in stats
        assert "total" in stats
        for rel_type in RELATIONSHIP_TYPES:
            assert rel_type in stats["by_type"]

    def test_resolve_relationships_runs_after_resolve_references_in_expected_order(self):
        """Mirrors pipeline.py's own integration order: populate ->
        enrich -> normalize -> resolve_references -> resolve_relationships
        -> set_current_registry_manager. Calling resolve_relationships()
        before resolve_references() would leave concept_id/concept_ids
        absent, so no has_definition/explains/described_by relationships
        would be produced -- this test locks in why the order matters."""
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        enrich_registries(manager)
        normalize_registries(manager)
        # Deliberately skip resolve_references() here.
        resolve_relationships(manager)
        assert relationships_of_type(manager, "has_definition") == []

    def test_topics_argument_never_mutates_topics_list_itself(self):
        manager = build_manager(concepts=[make_concept("c1", "Inflation")])
        topics = [make_topic("t1", concepts=["c1"]), make_topic("t2", concepts=[])]
        before = copy.deepcopy(topics)
        resolve_relationships(manager, topics=topics)
        assert topics == before


# --------------------------------------------------------------------------
# Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_registry_items_unmutated_by_relationship_generation(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        concept_before = copy.deepcopy(manager.get("concepts").get_by_id("c1"))
        definition_before = copy.deepcopy(manager.get("definitions").get_by_id("d1"))

        resolve_relationships(manager)

        assert manager.get("concepts").get_by_id("c1") == concept_before
        assert manager.get("definitions").get_by_id("d1") == definition_before

    def test_existing_registries_untouched_by_new_registry_registration(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        names_before = set(manager.names())
        resolve_relationships(manager)
        names_after = set(manager.names())
        assert names_after == names_before | {RELATIONSHIP_REGISTRY_NAME}

    def test_ids_and_urns_of_existing_items_never_change(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        resolve_relationships(manager)
        concept = manager.get("concepts").get_by_id("c1")
        definition = manager.get("definitions").get_by_id("d1")
        assert concept["id"] == "c1"
        assert concept["urn"] == "urn:concept:c1"
        assert definition["id"] == "d1"
        assert definition["urn"] == "urn:definition:d1"

    def test_relationships_never_appear_on_educational_object_dicts(self):
        """The single most important invariant: no registry item outside
        the dedicated 'relationships' registry ever grows a 'relationships'
        (or similarly-named) key as a side effect of this module running
        -- relationships live ONLY in their own registry, never attached
        onto a Concept/Definition/... dict that could flow into
        json_writer.assemble_chapter_json's output."""
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
            glossary=[make_glossary("g1", "Inflation")],
        )
        resolve_relationships(manager)
        for registry_name in manager.names():
            if registry_name == RELATIONSHIP_REGISTRY_NAME:
                continue
            for item in manager.get(registry_name).values():
                assert "relationships" not in item
                assert "relationship_resolution" not in item