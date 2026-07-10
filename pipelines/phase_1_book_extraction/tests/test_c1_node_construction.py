"""
tests/test_c1_node_construction.py — unit tests for Phase C1: Knowledge
Graph Node Construction (knowledge_graph/nodes.py,
knowledge_graph/build_nodes.py, and their pipeline.py integration point).

Per task instructions, these tests are generated only: they are not
executed here as part of authoring them, and no claim is made about
whether they currently pass in the caller's environment beyond the
ad-hoc reasoning performed during development (see the module's own
manual smoke-test run, done separately, outside this file).

This file does NOT re-test Phase C0 architecture (GraphNodeBase's own
field set, the identity id/urn string shapes in isolation, the empty
GraphRegistryManager three-registry shape, ...) -- those are already
covered by tests/test_c01_audit_findings.py and any other existing C0
test file. It covers only what Phase C1 actually adds: the thirteen
concrete node classes, the Node Builder, and their combined behavior
against real (fixture) Compiler IR data.
"""
from __future__ import annotations

import dataclasses

import pytest

from compiler.registries import (
    REGISTRY_NAMES,
    create_registry_manager,
    populate_registries,
)
from compiler.registry_manager import RegistryManager

from knowledge_graph.node import GraphNodeBase, FUTURE_NODE_TYPES
from knowledge_graph.nodes import (
    NODE_CLASSES,
    TopicNode,
    ConceptNode,
    DefinitionNode,
    GlossaryNode,
    EquationNode,
    FigureNode,
    DiagramNode,
    TableNode,
    ActivityNode,
    ExampleNode,
    BoxNode,
    WarningNode,
    NoteNode,
)
from knowledge_graph.build_nodes import (
    NODE_TYPE_BY_COMPILER_REGISTRY,
    build_node,
    build_knowledge_graph_nodes,
)
from knowledge_graph.registries import (
    NODE_REGISTRY_NAME,
    EDGE_REGISTRY_NAME,
    METADATA_REGISTRY_NAME,
    create_graph_registry_manager,
)
from knowledge_graph.identity import node_id as expected_node_id, node_urn as expected_node_urn
from knowledge_graph.exceptions import GraphNodeError
from compiler.exceptions import DuplicateIdError


# --------------------------------------------------------------------------
# Helpers -- minimal canonical-enveloped item dicts, matching the exact
# shape modules/canonical.py::canonical_fields() + pipeline.py's own
# per-type extra fields produce (id/urn/object_type/provenance/
# creation_metadata always present; name/term/title present only for the
# object types that actually carry one -- see
# knowledge_graph/build_nodes.py's own _DISPLAY_NAME_KEY_BY_NODE_TYPE
# docstring).
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


def make_populated_manager() -> RegistryManager:
    """Builds one RegistryManager with exactly one item per registry --
    enough to exercise every node type at least once, without depending
    on pipeline.py/PDF extraction at all."""
    manager = create_registry_manager()
    populate_registries(
        manager,
        topics=[make_item("t1", "urn:t:t1", "topic", label_key="title", label_value="Motion")],
        concepts=[make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")],
        definitions=[make_item("d1", "urn:d:d1", "definition", label_key="term", label_value="Inertia")],
        glossary=[make_item("g1", "urn:g:g1", "glossary", label_key="term", label_value="Momentum")],
        figures=[make_item("f1", "urn:f:f1", "figure", label_key="title", label_value="Fig 1: Pulley")],
        diagrams=[make_item("dg1", "urn:dg:dg1", "diagram", label_key="title", label_value="Diagram 1")],
        tables=[make_item("tb1", "urn:tb:tb1", "table", label_key="title", label_value=None)],
        equations=[make_item("e1", "urn:e:e1", "equation")],
        activities=[make_item("a1", "urn:a:a1", "activity", label_key="title", label_value=None)],
        boxes=[make_item("b1", "urn:b:b1", "box", label_key="title", label_value=None)],
        warnings=[make_item("w1", "urn:w:w1", "warning", label_key="title", label_value=None)],
        notes=[make_item("n1", "urn:n:n1", "note", label_key="title", label_value=None)],
        examples=[make_item("x1", "urn:x:x1", "example", label_key="title", label_value=None)],
    )
    return manager


NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Task 2 -- concrete node classes
# --------------------------------------------------------------------------

class TestConcreteNodeClasses:
    def test_one_class_per_future_node_type(self):
        assert set(NODE_CLASSES) == set(FUTURE_NODE_TYPES)

    def test_every_class_subclasses_graph_node_base_only(self):
        for cls in NODE_CLASSES.values():
            assert issubclass(cls, GraphNodeBase)
            # No second base class introduced (Task 2's own instruction).
            assert cls.__mro__[1] is GraphNodeBase

    def test_no_new_fields_added_by_any_subclass(self):
        base_fields = {f.name for f in dataclasses.fields(GraphNodeBase)}
        for cls in NODE_CLASSES.values():
            assert {f.name for f in dataclasses.fields(cls)} == base_fields

    def test_node_type_class_var_matches_dict_key(self):
        for node_type, cls in NODE_CLASSES.items():
            assert cls.NODE_TYPE == node_type

    @pytest.mark.parametrize(
        "cls,node_type",
        [
            (TopicNode, "topic"),
            (ConceptNode, "concept"),
            (DefinitionNode, "definition"),
            (GlossaryNode, "glossary"),
            (EquationNode, "equation"),
            (FigureNode, "figure"),
            (DiagramNode, "diagram"),
            (TableNode, "table"),
            (ActivityNode, "activity"),
            (ExampleNode, "example"),
            (BoxNode, "box"),
            (WarningNode, "warning"),
            (NoteNode, "note"),
        ],
    )
    def test_instantiable_directly(self, cls, node_type):
        node = cls(
            node_id="node:x:1", node_urn="urn:x", node_type=node_type,
            graph_id="kg-x", graph_urn="urn:kg-x",
            compiler_object_id="1", compiler_object_urn="urn:c:1",
            compiler_object_type=node_type, compiler_registry="whatever",
        )
        assert node.node_type == node_type
        assert node.to_dict()["node_type"] == node_type


# --------------------------------------------------------------------------
# Task 4 -- Node Builder: registry <-> node-type mapping
# --------------------------------------------------------------------------

class TestNodeTypeMapping:
    def test_mapping_covers_every_compiler_registry_name(self):
        assert set(NODE_TYPE_BY_COMPILER_REGISTRY) == set(REGISTRY_NAMES)

    def test_mapping_values_cover_every_node_class(self):
        assert set(NODE_TYPE_BY_COMPILER_REGISTRY.values()) == set(NODE_CLASSES)

    def test_mapping_is_one_to_one(self):
        values = list(NODE_TYPE_BY_COMPILER_REGISTRY.values())
        assert len(values) == len(set(values))


# --------------------------------------------------------------------------
# Task 1 + Task 3 -- one compiler object -> one node, deterministic id
# --------------------------------------------------------------------------

class TestBuildNode:
    def test_build_node_returns_correct_class(self):
        item = make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        node = build_node(item, compiler_registry_name="concepts", graph_namespace=NAMESPACE)
        assert isinstance(node, ConceptNode)
        assert node.node_type == "concept"

    def test_deterministic_node_id(self):
        item = make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        node_a = build_node(item, compiler_registry_name="concepts", graph_namespace=NAMESPACE)
        node_b = build_node(dict(item), compiler_registry_name="concepts", graph_namespace=NAMESPACE)
        assert node_a.node_id == node_b.node_id == expected_node_id("concept", "c1")
        assert node_a.node_urn == node_b.node_urn == expected_node_urn(NAMESPACE, "concept", "c1")

    def test_node_id_distinct_across_node_types_for_same_source_id(self):
        # Same underlying compiler_object_id, two different node types --
        # must never collide (identity.py's own node_id() contract).
        topic_item = make_item("shared1", "urn:t:shared1", "topic", label_key="title", label_value="X")
        concept_item = make_item("shared1", "urn:c:shared1", "concept", label_key="name", label_value="X")
        topic_node = build_node(topic_item, compiler_registry_name="topics", graph_namespace=NAMESPACE)
        concept_node = build_node(concept_item, compiler_registry_name="concepts", graph_namespace=NAMESPACE)
        assert topic_node.node_id != concept_node.node_id

    def test_wraps_never_duplicates_compiler_ir_fields(self):
        item = make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        node = build_node(item, compiler_registry_name="concepts", graph_namespace=NAMESPACE)
        assert node.compiler_object_id == "c1"
        assert node.compiler_object_urn == "urn:c:c1"
        assert node.compiler_object_type == "concept"
        assert node.compiler_registry == "concepts"
        # provenance/compiler_version are read-only denormalized copies,
        # not references that could be used to mutate Compiler IR.
        assert node.provenance == item["provenance"]
        assert node.provenance is not item["provenance"]
        assert node.compiler_version == "B5.1"

    def test_does_not_mutate_source_item(self):
        item = make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        snapshot = dict(item)
        build_node(item, compiler_registry_name="concepts", graph_namespace=NAMESPACE)
        assert item == snapshot

    @pytest.mark.parametrize(
        "registry_name,label_key,label_value,expect_display_name",
        [
            ("concepts", "name", "Force", "Force"),
            ("definitions", "term", "Inertia", "Inertia"),
            ("glossary", "term", "Momentum", "Momentum"),
            ("topics", "title", "Motion", "Motion"),
            ("figures", "title", "Fig 1", "Fig 1"),
            ("equations", None, None, None),
        ],
    )
    def test_display_name_extraction(self, registry_name, label_key, label_value, expect_display_name):
        kwargs = {}
        if label_key is not None:
            kwargs = {"label_key": label_key, "label_value": label_value}
        item = make_item("i1", "urn:i:i1", NODE_TYPE_BY_COMPILER_REGISTRY[registry_name], **kwargs)
        node = build_node(item, compiler_registry_name=registry_name, graph_namespace=NAMESPACE)
        assert node.display_name == expect_display_name

    def test_unknown_registry_name_raises(self):
        item = make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        with pytest.raises(GraphNodeError):
            build_node(item, compiler_registry_name="not_a_real_registry", graph_namespace=NAMESPACE)

    def test_missing_id_or_urn_raises(self):
        item = make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        del item["urn"]
        with pytest.raises(GraphNodeError):
            build_node(item, compiler_registry_name="concepts", graph_namespace=NAMESPACE)


# --------------------------------------------------------------------------
# Task 4 + Task 5 -- full Node Builder pipeline: registry population
# --------------------------------------------------------------------------

class TestBuildKnowledgeGraphNodes:
    def test_one_node_per_compiler_object(self):
        manager = make_populated_manager()
        total_compiler_objects = manager.total_size()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        assert node_registry.size() == total_compiler_objects == 13

    def test_zero_edges_after_build(self):
        manager = make_populated_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        assert graph_manager.get(EDGE_REGISTRY_NAME).size() == 0

    def test_metadata_registry_untouched(self):
        manager = make_populated_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        assert graph_manager.get(METADATA_REGISTRY_NAME).size() == 0

    def test_every_node_type_represented(self):
        manager = make_populated_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_types_seen = {n.node_type for n in graph_manager.get(NODE_REGISTRY_NAME).values()}
        assert node_types_seen == set(FUTURE_NODE_TYPES)

    def test_ordering_matches_compiler_registry_names_order(self):
        manager = make_populated_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_types_in_order = [n.node_type for n in graph_manager.get(NODE_REGISTRY_NAME).values()]
        expected_order = [NODE_TYPE_BY_COMPILER_REGISTRY[name] for name in REGISTRY_NAMES]
        assert node_types_in_order == expected_order

    def test_determinism_across_independent_runs(self):
        manager_a = make_populated_manager()
        manager_b = make_populated_manager()
        graph_a = build_knowledge_graph_nodes(manager_a, graph_namespace=NAMESPACE)
        graph_b = build_knowledge_graph_nodes(manager_b, graph_namespace=NAMESPACE)
        ids_a = [n.node_id for n in graph_a.get(NODE_REGISTRY_NAME).values()]
        ids_b = [n.node_id for n in graph_b.get(NODE_REGISTRY_NAME).values()]
        assert ids_a == ids_b
        urns_a = [n.node_urn for n in graph_a.get(NODE_REGISTRY_NAME).values()]
        urns_b = [n.node_urn for n in graph_b.get(NODE_REGISTRY_NAME).values()]
        assert urns_a == urns_b

    def test_duplicate_prevention_on_rebuild_into_same_manager(self):
        manager = make_populated_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        with pytest.raises(DuplicateIdError):
            build_knowledge_graph_nodes(
                manager, graph_namespace=NAMESPACE, graph_registry_manager=graph_manager,
            )

    def test_fresh_manager_created_when_none_given(self):
        manager = make_populated_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        # A second, independent call with no explicit graph_registry_manager
        # must not reuse or collide with the first call's manager.
        graph_manager_2 = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        assert graph_manager is not graph_manager_2
        assert graph_manager_2.get(NODE_REGISTRY_NAME).size() == 13

    def test_partial_registry_manager_is_not_an_error(self):
        # A hand-built manager missing some of the thirteen registries
        # (e.g. a focused test fixture) must not raise -- mirrors
        # compiler.registries.populate_registries()'s own "partial
        # population is valid" contract.
        manager = RegistryManager()
        manager.create("concepts")
        manager.get("concepts").insert(
            make_item("c1", "urn:c:c1", "concept", label_key="name", label_value="Force")
        )
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        assert node_registry.size() == 1
        assert node_registry.values()[0].node_type == "concept"

    def test_empty_registry_manager_produces_zero_nodes(self):
        manager = create_registry_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        assert graph_manager.get(NODE_REGISTRY_NAME).size() == 0
        assert graph_manager.get(EDGE_REGISTRY_NAME).size() == 0

    def test_does_not_mutate_compiler_registry_manager(self):
        manager = make_populated_manager()
        before = manager.serialize()
        build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        after = manager.serialize()
        assert before == after

    def test_returns_the_given_manager_instance(self):
        manager = make_populated_manager()
        graph_manager = create_graph_registry_manager()
        returned = build_knowledge_graph_nodes(
            manager, graph_namespace=NAMESPACE, graph_registry_manager=graph_manager,
        )
        assert returned is graph_manager


# --------------------------------------------------------------------------
# Backward compatibility -- Phase C0/B artifacts remain exactly as they
# were; Phase C1 only adds new, additive behavior.
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_graph_node_base_shape_is_unchanged(self):
        # Same field set Phase C0.1 already established -- Phase C1 must
        # not have added, removed, or reordered any GraphNodeBase field.
        expected_fields = {
            "node_id", "node_urn", "node_type", "graph_id", "graph_urn",
            "compiler_object_id", "compiler_object_urn", "compiler_object_type",
            "compiler_registry", "display_name", "provenance",
            "compiler_version", "node_schema_version", "metadata",
        }
        assert set(GraphNodeBase.__dataclass_fields__) == expected_fields

    def test_compiler_registries_untouched_by_import(self):
        # Importing knowledge_graph.build_nodes must not register, patch,
        # or otherwise alter compiler.registries's own REGISTRY_NAMES.
        before = list(REGISTRY_NAMES)
        import knowledge_graph.build_nodes  # noqa: F401
        assert list(REGISTRY_NAMES) == before

    def test_empty_graph_registry_manager_still_has_three_registries(self):
        manager = create_graph_registry_manager()
        assert manager.get(NODE_REGISTRY_NAME).size() == 0
        assert manager.get(EDGE_REGISTRY_NAME).size() == 0
        assert manager.get(METADATA_REGISTRY_NAME).size() == 0