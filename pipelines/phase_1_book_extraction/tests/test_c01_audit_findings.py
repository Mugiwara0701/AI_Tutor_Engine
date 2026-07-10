"""
tests/test_c01_audit_findings.py — unit tests for the Phase C0.1
audit-findings resolution pass (Knowledge Graph Architecture
Refinement).

This file covers ONLY what the C0.1 refinement pass actually changed:

  1. Audit Finding 1 (Topic Registry): `populate_registries()`'s
     `topics=` keyword argument actually inserts canonical-enveloped
     topic items into the RegistryManager's `topics` registry, leaves
     `manager` returned, and never mutates the caller's own list/dicts.
     (`compiler/registries.py`'s `TopicRegistry` class itself, and its
     registration in `create_registry_manager()`, are already covered
     by `tests/test_registries.py::TestCreateRegistryManager` -- this
     file does not repeat those, only the previously-untested
     `topics=` population path.)

  2. Audit Finding 2 (GraphNodeBase field expansion):
     `knowledge_graph.node.GraphNodeBase` now exposes
     `compiler_object_id`, `compiler_object_urn`, `display_name`,
     `provenance`, `compiler_version`, and `metadata`, alongside its
     pre-existing `compiler_object_type`/`compiler_registry` (renamed
     from `source_object_type`/`source_registry`) fields, with no
     second base node class and no construction of any node anywhere
     else in this codebase.

Per task instructions, these tests are generated only: they are not
executed here as part of authoring them, and no claim is made about
whether they currently pass in the caller's environment beyond the
ad-hoc reasoning performed during development. This file does NOT
regenerate the full Phase C0 test suite -- see
tests/test_registries.py, tests/test_kg_readiness.py, and the other
existing Phase B/C0 test files for everything else.
"""
from __future__ import annotations

import pytest

from compiler.registries import (
    REGISTRY_NAMES,
    TopicRegistry,
    create_registry_manager,
    populate_registries,
)
from compiler.registry import DuplicateIdError, DuplicateUrnError

from knowledge_graph.node import (
    NODE_SCHEMA_VERSION,
    FUTURE_NODE_TYPES,
    GraphNodeBase,
    is_known_future_node_type,
)


# --------------------------------------------------------------------------
# Helpers -- minimal canonical-enveloped topic dicts, matching the shape
# pipeline.py's own canonical.canonical_fields(object_type="topic") snapshot
# copy carries (id/urn always present -- see compiler/registries.py's own
# module docstring).
# --------------------------------------------------------------------------

def make_topic(id_, title, urn=None, **extra):
    d = {
        "id": id_,
        "urn": urn or f"urn:topic:{id_}",
        "object_type": "topic",
        "title": title,
    }
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# Audit Finding 1 -- Topic Registry population via populate_registries()
# --------------------------------------------------------------------------

class TestTopicRegistryPopulation:
    def test_topics_kwarg_inserts_into_topics_registry(self):
        manager = create_registry_manager()
        items = [make_topic("t1", "Motion"), make_topic("t2", "Force")]
        populate_registries(manager, topics=items)

        registry = manager.get("topics")
        assert isinstance(registry, TopicRegistry)
        assert registry.size() == 2
        assert registry.get_by_id("t1")["title"] == "Motion"
        assert registry.get_by_id("t2")["title"] == "Force"

    def test_topics_defaults_to_empty_when_omitted(self):
        manager = create_registry_manager()
        populate_registries(manager, concepts=[])
        assert manager.get("topics").size() == 0

    def test_topics_insertion_order_preserved(self):
        manager = create_registry_manager()
        items = [make_topic("t3", "C"), make_topic("t1", "A"), make_topic("t2", "B")]
        populate_registries(manager, topics=items)
        assert [item["id"] for item in manager.get("topics").values()] == [
            "t3", "t1", "t2",
        ]

    def test_duplicate_topic_id_raises(self):
        manager = create_registry_manager()
        items = [make_topic("t1", "Motion"), make_topic("t1", "Motion Again")]
        with pytest.raises(DuplicateIdError):
            populate_registries(manager, topics=items)

    def test_duplicate_topic_urn_raises(self):
        manager = create_registry_manager()
        items = [
            make_topic("t1", "Motion", urn="urn:topic:shared"),
            make_topic("t2", "Force", urn="urn:topic:shared"),
        ]
        with pytest.raises(DuplicateUrnError):
            populate_registries(manager, topics=items)

    def test_populate_registries_does_not_mutate_input_list_or_dicts(self):
        manager = create_registry_manager()
        items = [make_topic("t1", "Motion")]
        snapshot_before = dict(items[0])
        populate_registries(manager, topics=items)
        assert items == [snapshot_before]

    def test_populate_registries_returns_the_same_manager(self):
        manager = create_registry_manager()
        result = populate_registries(manager, topics=[make_topic("t1", "Motion")])
        assert result is manager

    def test_topics_is_one_of_the_thirteen_registry_names(self):
        assert "topics" in REGISTRY_NAMES
        assert len(REGISTRY_NAMES) == 13


# --------------------------------------------------------------------------
# Audit Finding 2 -- GraphNodeBase field expansion
# --------------------------------------------------------------------------

def make_node(**overrides):
    """Builds a GraphNodeBase with every required field filled in, so
    individual tests only need to override the field(s) they care
    about."""
    fields = dict(
        node_id="node:concept:c1",
        node_urn="urn:ncert-kg:kg:physics-ch3:node:concept:c1",
        node_type="concept",
        graph_id="kg-physics-ch3",
        graph_urn="urn:ncert-kg:kg:physics-ch3",
        compiler_object_id="c1",
        compiler_object_urn="urn:concept:c1",
        compiler_object_type="concept",
        compiler_registry="concepts",
    )
    fields.update(overrides)
    return GraphNodeBase(**fields)


class TestGraphNodeBaseFieldExpansion:
    def test_required_provenance_fields_are_present(self):
        node = make_node()
        assert node.compiler_object_id == "c1"
        assert node.compiler_object_urn == "urn:concept:c1"
        assert node.compiler_object_type == "concept"
        assert node.compiler_registry == "concepts"

    def test_new_convenience_fields_default_to_none(self):
        node = make_node()
        assert node.display_name is None
        assert node.provenance is None
        assert node.compiler_version is None

    def test_new_convenience_fields_can_be_set(self):
        node = make_node(
            display_name="Photosynthesis",
            provenance={"source": "ncert-physics-ch3.pdf", "page": 12},
            compiler_version="B5.1",
        )
        assert node.display_name == "Photosynthesis"
        assert node.provenance == {"source": "ncert-physics-ch3.pdf", "page": 12}
        assert node.compiler_version == "B5.1"

    def test_metadata_defaults_to_empty_dict_and_is_independent_per_instance(self):
        node_a = make_node()
        node_b = make_node()
        assert node_a.metadata == {}
        node_a.metadata["k"] = "v"
        assert node_b.metadata == {}

    def test_node_schema_version_defaults_to_module_constant(self):
        node = make_node()
        assert node.node_schema_version == NODE_SCHEMA_VERSION

    def test_to_dict_includes_every_expanded_field(self):
        node = make_node(
            display_name="Photosynthesis",
            provenance={"source": "test"},
            compiler_version="B5.1",
            metadata={"note": "x"},
        )
        d = node.to_dict()
        for key in (
            "node_id", "node_urn", "node_type", "graph_id", "graph_urn",
            "compiler_object_id", "compiler_object_urn", "compiler_object_type",
            "compiler_registry", "display_name", "provenance",
            "compiler_version", "node_schema_version", "metadata",
        ):
            assert key in d

    def test_old_pre_c01_field_names_no_longer_exist(self):
        node = make_node()
        assert not hasattr(node, "source_object_id")
        assert not hasattr(node, "source_object_type")
        assert not hasattr(node, "source_registry")

    def test_no_second_base_node_class_was_introduced(self):
        import knowledge_graph.node as node_module

        base_classes = [
            obj for name, obj in vars(node_module).items()
            if isinstance(obj, type) and name.endswith("Base")
        ]
        assert base_classes == [GraphNodeBase]

    def test_future_node_types_unchanged_by_this_refinement(self):
        assert set(FUTURE_NODE_TYPES) == {
            "topic", "concept", "definition", "glossary", "equation",
            "figure", "diagram", "table", "activity", "example", "box",
            "warning", "note",
        }
        assert is_known_future_node_type("topic")
        assert not is_known_future_node_type("not-a-real-type")
