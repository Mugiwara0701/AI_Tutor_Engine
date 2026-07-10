"""
tests/test_c2_edge_construction.py — unit tests for Phase C2: Knowledge
Graph Edge Construction (knowledge_graph/edges.py,
knowledge_graph/build_edges.py, and their pipeline.py integration point).

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment beyond the ad-hoc reasoning performed during
development (a manual smoke-test run, done separately, outside this
file, exercised the same code paths this file covers).

This file does NOT re-test Phase C0 architecture (GraphEdgeBase's own
field set, the identity edge-id/edge-urn string shapes in isolation, the
empty GraphRegistryManager three-registry shape, ...) or Phase C1
(GraphNodeBase, the thirteen node classes, the Node Builder) -- those
are already covered by tests/test_c01_audit_findings.py and
tests/test_c1_node_construction.py. It also does NOT re-test Phase B3
relationship generation itself (which relationship types are produced
from which source fields) -- that is already covered by
tests/test_relationships.py; this file treats
compiler.relationships.resolve_relationships()'s own output as a given
input. It covers only what Phase C2 actually adds: the nine concrete
edge classes, the Edge Builder, and their combined behavior against
real (fixture) Compiler IR + Knowledge Graph node data.
"""
from __future__ import annotations

import dataclasses

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.registry_manager import RegistryManager
from compiler.references import resolve_references
from compiler.relationships import (
    RELATIONSHIP_TYPES,
    resolve_relationships,
    ensure_relationship_registry,
)
from compiler.exceptions import DuplicateIdError

from knowledge_graph.edge import GraphEdgeBase
from knowledge_graph.edges import (
    EDGE_CLASSES,
    HasDefinitionEdge,
    ExplainsEdge,
    DescribedByEdge,
    ContainsEdge,
    AppearsInEdge,
    BelongsToEdge,
    UsesConceptEdge,
    IllustratesEdge,
    TeachesEdge,
)
from knowledge_graph.build_nodes import build_knowledge_graph_nodes
from knowledge_graph.build_edges import (
    _NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE,
    build_edge,
    build_knowledge_graph_edges,
)
from knowledge_graph.registries import (
    NODE_REGISTRY_NAME,
    EDGE_REGISTRY_NAME,
    METADATA_REGISTRY_NAME,
    create_graph_registry_manager,
)
from knowledge_graph.identity import (
    node_id as expected_node_id,
    edge_id as expected_edge_id,
    edge_urn as expected_edge_urn,
)
from knowledge_graph.exceptions import GraphEdgeError


NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- same canonical-enveloped item shape
# tests/test_c1_node_construction.py::make_item already establishes,
# duplicated here (not imported) so this file has no test-to-test import
# dependency, matching that file's own standalone-fixture style.
# --------------------------------------------------------------------------

def make_item(id_, urn, object_type, *, label_key=None, label_value=None,
              source_page=1, compiler_version="B5.1", **extra):
    d = {
        "id": id_,
        "urn": urn,
        "object_type": object_type,
        "provenance": {
            "source_page": source_page,
            "source_block_id": None,
            "extraction_method": "deterministic",
            "confidence": 0.9,
        },
        "creation_metadata": {
            "created_at": "2026-01-01T00:00:00+00:00",
            "compiler_version": compiler_version,
            "generator": None,
        },
    }
    if label_key is not None:
        d[label_key] = label_value
    d.update(extra)
    return d


def make_relationship_ready_manager() -> RegistryManager:
    """Builds one RegistryManager whose registries already carry
    Phase-B2-resolved reference fields (concept_id/topic_ids/...), so
    compiler.relationships.resolve_relationships() actually generates at
    least one relationship per RELATIONSHIP_TYPES entry -- covers every
    edge type at least once, without depending on pipeline.py/PDF
    extraction at all.

    Topology (deliberately small, one item per role):
      Topic t1 --contains--> Concept c1  (topic.concepts=["c1"])
      Concept c1 --appears_in--> Topic t1  (concept.topic_ids=["t1"])
      Concept c1 --has_definition--> Definition d1  (definition.concept_id="c1")
      Definition d1 --belongs_to--> Topic t1  (definition.topic_ids=["t1"])
      Glossary Entry g1 --explains--> Concept c1  (glossary.concept_id="c1")
      Concept c1 --described_by--> Glossary Entry g1  (same resolved ref)
      Glossary Entry g1 --belongs_to--> Topic t1  (glossary.topic_ids=["t1"])
      Equation e1 --uses_concept--> Concept c1  (equation.concept_ids=["c1"])
      Figure f1 --illustrates--> Concept c1  (figure.concept_ids=["c1"])
      Activity a1 --teaches--> Concept c1  (activity.concept_ids=["c1"])
    """
    topic = make_item(
        "t1", "urn:t:t1", "topic", label_key="title", label_value="Motion",
        concepts=["c1"],
    )
    concept = make_item(
        "c1", "urn:c:c1", "concept", label_key="name", label_value="Force",
        topic_ids=["t1"],
    )
    definition = make_item(
        "d1", "urn:d:d1", "definition", label_key="term", label_value="Force",
        topic_ids=["t1"],
    )
    glossary = make_item(
        "g1", "urn:g:g1", "glossary", label_key="term", label_value="Force",
        topic_ids=["t1"],
    )
    equation = make_item("e1", "urn:e:e1", "equation", concept_ids=["c1"])
    figure = make_item(
        "f1", "urn:f:f1", "figure", label_key="title", label_value="Fig 1",
        concept_ids=["c1"],
    )
    activity = make_item(
        "a1", "urn:a:a1", "activity", label_key="title", label_value=None,
        concept_ids=["c1"],
    )

    manager = create_registry_manager()
    populate_registries(
        manager,
        topics=[topic],
        concepts=[concept],
        definitions=[definition],
        glossary=[glossary],
        equations=[equation],
        figures=[figure],
        activities=[activity],
    )
    resolve_references(manager, topics=[topic])
    resolve_relationships(manager, topics=[topic])
    return manager


def build_ready_graph_manager(manager: RegistryManager):
    """One-shot: Phase C1 node construction, then Phase C2 edge
    construction, into the same GraphRegistryManager -- the exact
    sequence pipeline.py's own integration point runs."""
    graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
    graph_manager = build_knowledge_graph_edges(
        manager, graph_manager, graph_namespace=NAMESPACE,
    )
    return graph_manager


# --------------------------------------------------------------------------
# Task 1 -- concrete edge classes
# --------------------------------------------------------------------------

class TestConcreteEdgeClasses:
    def test_one_class_per_b3_relationship_type(self):
        assert set(EDGE_CLASSES) == set(RELATIONSHIP_TYPES)

    def test_every_class_subclasses_graph_edge_base_only(self):
        for cls in EDGE_CLASSES.values():
            assert issubclass(cls, GraphEdgeBase)
            # No second base class introduced (Task 1's own instruction).
            assert cls.__mro__[1] is GraphEdgeBase

    def test_no_new_fields_added_by_any_subclass(self):
        base_fields = {f.name for f in dataclasses.fields(GraphEdgeBase)}
        for cls in EDGE_CLASSES.values():
            assert {f.name for f in dataclasses.fields(cls)} == base_fields

    def test_edge_type_class_var_matches_dict_key(self):
        for edge_type, cls in EDGE_CLASSES.items():
            assert cls.EDGE_TYPE == edge_type

    @pytest.mark.parametrize(
        "cls,edge_type",
        [
            (HasDefinitionEdge, "has_definition"),
            (ExplainsEdge, "explains"),
            (DescribedByEdge, "described_by"),
            (ContainsEdge, "contains"),
            (AppearsInEdge, "appears_in"),
            (BelongsToEdge, "belongs_to"),
            (UsesConceptEdge, "uses_concept"),
            (IllustratesEdge, "illustrates"),
            (TeachesEdge, "teaches"),
        ],
    )
    def test_instantiable_directly(self, cls, edge_type):
        edge = cls(
            edge_id="edge:x:1:2", edge_urn="urn:x", edge_type=edge_type,
            graph_id="kg-x", graph_urn="urn:kg-x",
            source_node_id="node:concept:1", target_node_id="node:concept:2",
        )
        assert edge.edge_type == edge_type
        assert edge.directed is True
        assert edge.to_dict()["edge_type"] == edge_type


# --------------------------------------------------------------------------
# Edge Builder: relationship-object-type <-> node-type mapping
# --------------------------------------------------------------------------

class TestNodeTypeMapping:
    def test_mapping_covers_every_relationship_object_type(self):
        # Every source_type/target_type compiler/relationships.py's own
        # generators ever stamp a relationship with.
        expected = {
            "topic", "concept", "definition", "glossary_entry",
            "equation", "figure", "diagram", "table", "activity",
        }
        assert set(_NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE) == expected

    def test_glossary_entry_maps_to_glossary_node_type(self):
        assert _NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE["glossary_entry"] == "glossary"

    def test_every_other_label_maps_to_itself(self):
        for label, node_type in _NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE.items():
            if label != "glossary_entry":
                assert node_type == label


# --------------------------------------------------------------------------
# Task 2 + Task 3 + Task 4 -- one compiler relationship -> one edge,
# deterministic id
# --------------------------------------------------------------------------

class TestBuildEdge:
    def test_build_edge_returns_correct_class_and_resolves_endpoints(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        relationship = next(
            r for r in manager.get("relationships").values() if r["type"] == "has_definition"
        )
        edge = build_edge(relationship, node_registry=node_registry, graph_namespace=NAMESPACE)
        assert isinstance(edge, HasDefinitionEdge)
        assert edge.edge_type == "has_definition"
        assert edge.source_node_id == expected_node_id("concept", "c1")
        assert edge.target_node_id == expected_node_id("definition", "d1")

    def test_deterministic_edge_id(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        relationship = next(
            r for r in manager.get("relationships").values() if r["type"] == "contains"
        )
        edge_a = build_edge(relationship, node_registry=node_registry, graph_namespace=NAMESPACE)
        edge_b = build_edge(dict(relationship), node_registry=node_registry, graph_namespace=NAMESPACE)
        source_node_id = expected_node_id("topic", "t1")
        target_node_id = expected_node_id("concept", "c1")
        assert edge_a.edge_id == edge_b.edge_id == expected_edge_id(
            "contains", source_node_id, target_node_id,
        )
        assert edge_a.edge_urn == edge_b.edge_urn == expected_edge_urn(
            NAMESPACE, "contains", source_node_id, target_node_id,
        )

    def test_edge_never_duplicates_or_replaces_compiler_relationship_fields(self):
        # GraphEdgeBase carries no compiler_relationship_* quartet the way
        # GraphNodeBase carries a compiler_object_* quartet (Task 1: no
        # new fields) -- the one pointer back to Compiler IR lives in the
        # open `metadata` bag instead.
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        relationship = next(
            r for r in manager.get("relationships").values() if r["type"] == "has_definition"
        )
        edge = build_edge(relationship, node_registry=node_registry, graph_namespace=NAMESPACE)
        assert edge.metadata["compiler_relationship_id"] == relationship["id"]

    def test_does_not_mutate_relationship_or_node_registry(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        relationship = next(
            r for r in manager.get("relationships").values() if r["type"] == "has_definition"
        )
        snapshot = dict(relationship)
        node_snapshot = node_registry.serialize()
        build_edge(relationship, node_registry=node_registry, graph_namespace=NAMESPACE)
        assert relationship == snapshot
        assert node_registry.serialize() == node_snapshot

    def test_unknown_relationship_type_raises(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        bad = {
            "id": "rel-x", "type": "prerequisite",
            "source_type": "concept", "source_id": "c1",
            "target_type": "concept", "target_id": "c1",
        }
        with pytest.raises(GraphEdgeError):
            build_edge(bad, node_registry=node_registry, graph_namespace=NAMESPACE)

    def test_unknown_source_type_raises(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        bad = {
            "id": "rel-x", "type": "has_definition",
            "source_type": "not_a_real_type", "source_id": "c1",
            "target_type": "definition", "target_id": "d1",
        }
        with pytest.raises(GraphEdgeError):
            build_edge(bad, node_registry=node_registry, graph_namespace=NAMESPACE)

    def test_missing_id_raises(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        bad = {
            "type": "has_definition",
            "source_type": "concept", "source_id": "c1",
            "target_type": "definition", "target_id": "d1",
        }
        with pytest.raises(GraphEdgeError):
            build_edge(bad, node_registry=node_registry, graph_namespace=NAMESPACE)

    def test_dangling_source_node_raises(self):
        # A relationship pointing at a compiler object no node was ever
        # built for (e.g. Phase C1 run against a different/partial
        # manager) must never silently fabricate or skip an edge.
        manager = make_relationship_ready_manager()
        empty_graph_manager = create_graph_registry_manager()
        node_registry = empty_graph_manager.get(NODE_REGISTRY_NAME)
        relationship = next(
            r for r in manager.get("relationships").values() if r["type"] == "has_definition"
        )
        with pytest.raises(GraphEdgeError):
            build_edge(relationship, node_registry=node_registry, graph_namespace=NAMESPACE)


# --------------------------------------------------------------------------
# Task 2 + Task 5 -- full Edge Builder pipeline: registry population
# --------------------------------------------------------------------------

class TestBuildKnowledgeGraphEdges:
    def test_one_edge_per_relationship(self):
        manager = make_relationship_ready_manager()
        total_relationships = manager.get("relationships").size()
        graph_manager = build_ready_graph_manager(manager)
        edge_registry = graph_manager.get(EDGE_REGISTRY_NAME)
        assert edge_registry.size() == total_relationships
        # The fixture topology (see make_relationship_ready_manager()'s own
        # docstring) has one relationship per RELATIONSHIP_TYPES entry
        # EXCEPT "belongs_to", which it deliberately generates TWICE
        # (definition d1 -> topic t1 AND glossary entry g1 -> topic t1) --
        # so the total relationship count is one more than the number of
        # distinct relationship types, not equal to it.
        assert total_relationships == len(RELATIONSHIP_TYPES) + 1

    def test_every_relationship_type_represented(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        edge_types_seen = {e.edge_type for e in graph_manager.get(EDGE_REGISTRY_NAME).values()}
        assert edge_types_seen == set(RELATIONSHIP_TYPES)

    def test_node_registry_untouched_by_edge_construction(self):
        manager = make_relationship_ready_manager()
        node_only_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_snapshot = node_only_manager.get(NODE_REGISTRY_NAME).serialize()
        build_knowledge_graph_edges(manager, node_only_manager, graph_namespace=NAMESPACE)
        assert node_only_manager.get(NODE_REGISTRY_NAME).serialize() == node_snapshot

    def test_metadata_registry_untouched(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        assert graph_manager.get(METADATA_REGISTRY_NAME).size() == 0

    def test_ordering_matches_relationship_registry_insertion_order(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        expected_order = [r["type"] for r in manager.get("relationships").values()]
        actual_order = [e.edge_type for e in graph_manager.get(EDGE_REGISTRY_NAME).values()]
        assert actual_order == expected_order

    def test_determinism_across_independent_runs(self):
        manager_a = make_relationship_ready_manager()
        manager_b = make_relationship_ready_manager()
        graph_a = build_ready_graph_manager(manager_a)
        graph_b = build_ready_graph_manager(manager_b)
        ids_a = sorted(e.edge_id for e in graph_a.get(EDGE_REGISTRY_NAME).values())
        ids_b = sorted(e.edge_id for e in graph_b.get(EDGE_REGISTRY_NAME).values())
        assert ids_a == ids_b

    def test_duplicate_prevention_on_rebuild_into_same_manager(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        with pytest.raises(DuplicateIdError):
            build_knowledge_graph_edges(manager, graph_manager, graph_namespace=NAMESPACE)

    def test_relationship_registry_absent_is_not_an_error(self):
        # A hand-built compiler manager with no "relationships" registry
        # at all (e.g. a focused test fixture, or Phase B3 never run)
        # must not raise -- mirrors build_knowledge_graph_nodes()'s own
        # "a registry name it does not itself own is silently skipped"
        # contract, one relationship type up.
        manager = RegistryManager()
        manager.create("concepts")
        manager.get("concepts").insert(
            make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        )
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        returned = build_knowledge_graph_edges(manager, graph_manager, graph_namespace=NAMESPACE)
        assert returned.get(EDGE_REGISTRY_NAME).size() == 0

    def test_empty_relationship_registry_produces_zero_edges(self):
        manager = create_registry_manager()
        ensure_relationship_registry(manager)  # present but empty
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        returned = build_knowledge_graph_edges(manager, graph_manager, graph_namespace=NAMESPACE)
        assert returned.get(EDGE_REGISTRY_NAME).size() == 0

    def test_does_not_mutate_compiler_registry_manager(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        before = manager.serialize()
        build_knowledge_graph_edges(manager, graph_manager, graph_namespace=NAMESPACE)
        after = manager.serialize()
        assert before == after

    def test_returns_the_given_graph_registry_manager_instance(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        returned = build_knowledge_graph_edges(manager, graph_manager, graph_namespace=NAMESPACE)
        assert returned is graph_manager


# --------------------------------------------------------------------------
# Backward compatibility -- Phase C0/C1/B artifacts remain exactly as
# they were; Phase C2 only adds new, additive behavior.
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_graph_edge_base_shape_is_unchanged(self):
        expected_fields = {
            "edge_id", "edge_urn", "edge_type", "graph_id", "graph_urn",
            "source_node_id", "target_node_id", "directed",
            "edge_schema_version", "metadata",
        }
        assert {f.name for f in dataclasses.fields(GraphEdgeBase)} == expected_fields

    def test_compiler_relationships_module_untouched_by_import(self):
        # Importing knowledge_graph.build_edges must not register, patch,
        # or otherwise alter compiler.relationships's own RELATIONSHIP_TYPES.
        before = list(RELATIONSHIP_TYPES)
        import knowledge_graph.build_edges  # noqa: F401
        assert list(RELATIONSHIP_TYPES) == before

    def test_node_construction_alone_still_produces_zero_edges(self):
        # Phase C1's own contract (tests/test_c1_node_construction.py::
        # TestBuildKnowledgeGraphNodes::test_zero_edges_after_build) must
        # still hold with knowledge_graph.build_edges imported alongside
        # it -- Phase C2 must never make node construction itself start
        # building edges as a side effect.
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        assert graph_manager.get(EDGE_REGISTRY_NAME).size() == 0

    def test_empty_graph_registry_manager_still_has_three_registries(self):
        manager = create_graph_registry_manager()
        assert manager.get(NODE_REGISTRY_NAME).size() == 0
        assert manager.get(EDGE_REGISTRY_NAME).size() == 0
        assert manager.get(METADATA_REGISTRY_NAME).size() == 0