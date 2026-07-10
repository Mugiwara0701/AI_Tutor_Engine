"""
tests/test_c3_graph_validation.py — unit tests for Phase C3: Knowledge
Graph Validation & Integrity (knowledge_graph/validation.py's concrete
`validate_knowledge_graph()` pass, and its pipeline.py integration
point).

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment.

This file does NOT re-test Phase C0 architecture (the six ABC
contracts at the top of knowledge_graph/validation.py, which stay
untouched and unimplemented), Phase C1 (node construction -- see
tests/test_c1_node_construction.py), or Phase C2 (edge construction --
see tests/test_c2_edge_construction.py). It covers only what Phase C3
adds: `_validate_registry_integrity`, `_validate_node_integrity`,
`_validate_edge_integrity`, `_validate_graph_integrity`,
`_check_graph_determinism`, and the composed `validate_knowledge_graph()`
entry point, against both a real, fully-built graph (via Phase
C1+C2's own builders) and small hand-crafted fixtures for scenarios
CanonicalRegistry's own duplicate-insertion protection makes impossible
to reach through normal construction (duplicate ids/urns).
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.registry_manager import RegistryManager
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships

from knowledge_graph.node import GraphNodeBase
from knowledge_graph.edge import GraphEdgeBase
from knowledge_graph.build_nodes import build_knowledge_graph_nodes
from knowledge_graph.build_edges import build_knowledge_graph_edges
from knowledge_graph.registries import (
    NODE_REGISTRY_NAME,
    EDGE_REGISTRY_NAME,
    METADATA_REGISTRY_NAME,
    GRAPH_REGISTRY_NAMES,
    GraphRegistryManager,
    create_graph_registry_manager,
)
from knowledge_graph.identity import (
    graph_id as expected_graph_id,
    graph_urn as expected_graph_urn,
    node_id as expected_node_id,
    edge_id as expected_edge_id,
)
from knowledge_graph.validation import (
    GRAPH_VALIDATION_VERSION,
    validate_knowledge_graph,
    _validate_registry_integrity,
    _validate_node_integrity,
    _validate_edge_integrity,
    _validate_graph_integrity,
    _check_graph_determinism,
)

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- same canonical-enveloped item shape
# tests/test_c1_node_construction.py::make_item /
# tests/test_c2_edge_construction.py::make_item already establish,
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
    """One topic / one concept / one definition / one glossary entry /
    one equation / one figure / one activity, fully cross-referenced --
    small but enough for resolve_relationships() to generate at least
    one relationship of several distinct types, so build_knowledge_graph_edges()
    produces a non-empty, non-trivial edge registry. Mirrors
    tests/test_c2_edge_construction.py::make_relationship_ready_manager
    exactly (duplicated, not imported -- see module docstring)."""
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
        topics=[topic], concepts=[concept], definitions=[definition],
        glossary=[glossary], equations=[equation], figures=[figure],
        activities=[activity],
    )
    resolve_references(manager, topics=[topic])
    resolve_relationships(manager, topics=[topic])
    return manager


def build_ready_graph_manager(manager: RegistryManager) -> GraphRegistryManager:
    """Phase C1 node construction, then Phase C2 edge construction, into
    the same GraphRegistryManager -- the exact sequence pipeline.py's own
    integration point runs, immediately before Phase C3 validation."""
    graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
    graph_manager = build_knowledge_graph_edges(
        manager, graph_manager, graph_namespace=NAMESPACE,
    )
    return graph_manager


def make_node(node_id_, compiler_object_id, *, node_type="concept", **overrides):
    fields = dict(
        node_id=node_id_,
        node_urn=f"urn:kg:node:{node_id_}",
        node_type=node_type,
        graph_id=expected_graph_id(NAMESPACE),
        graph_urn=expected_graph_urn(NAMESPACE),
        compiler_object_id=compiler_object_id,
        compiler_object_urn=f"urn:c:{compiler_object_id}",
        compiler_object_type=node_type,
        compiler_registry="concepts",
    )
    fields.update(overrides)
    return GraphNodeBase(**fields)


def make_edge(edge_id_, source_node_id, target_node_id, *, edge_type="related_to", **overrides):
    fields = dict(
        edge_id=edge_id_,
        edge_urn=f"urn:kg:edge:{edge_id_}",
        edge_type=edge_type,
        graph_id=expected_graph_id(NAMESPACE),
        graph_urn=expected_graph_urn(NAMESPACE),
        source_node_id=source_node_id,
        target_node_id=target_node_id,
    )
    fields.update(overrides)
    return GraphEdgeBase(**fields)


# --------------------------------------------------------------------------
# Task 6 -- overall report shape, on a genuinely valid graph
# --------------------------------------------------------------------------

class TestValidGraph:
    def test_valid_graph_passes(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        report = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)

        assert report["overall_status"] == "pass"
        assert report["status"] == "pass"
        assert report["errors"] == []
        assert report["failed_checks"] == []
        assert report["validation_version"] == GRAPH_VALIDATION_VERSION

    def test_report_has_all_task6_fields(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        report = validate_knowledge_graph(graph_manager)

        for key in (
            "overall_status", "passed_checks", "failed_checks", "warnings",
            "node_summary", "edge_summary", "registry_summary",
            "validation_statistics", "validation_version",
        ):
            assert key in report

    def test_node_and_edge_summaries_reflect_real_counts(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        report = validate_knowledge_graph(graph_manager)

        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        edge_registry = graph_manager.get(EDGE_REGISTRY_NAME)
        assert report["node_summary"]["total"] == node_registry.size()
        assert report["edge_summary"]["total"] == edge_registry.size()
        assert node_registry.size() > 0
        assert edge_registry.size() > 0

    def test_compiler_cross_check_counts_match_when_supplied(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        report = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)

        expected_counts = report["integrity_summary"]["expected_counts"]
        assert expected_counts["checked"] is True
        assert expected_counts["node_count_matches"] is True
        assert expected_counts["edge_count_matches"] is True

    def test_compiler_cross_check_skipped_when_omitted(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        report = validate_knowledge_graph(graph_manager)

        assert report["integrity_summary"]["expected_counts"] == {"checked": False}
        assert report["node_summary"]["compiler_cross_check_performed"] is False


# --------------------------------------------------------------------------
# Task 3 / Task 5 -- missing source / missing target node
# --------------------------------------------------------------------------

class TestMissingEndpoints:
    def _graph_with_one_dangling_edge(self, *, break_source: bool, break_target: bool):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        any_node_id = node_registry.ids()[0]

        bad_source = "node:concept:does-not-exist" if break_source else any_node_id
        bad_target = "node:concept:also-missing" if break_target else any_node_id
        bad_edge = make_edge(
            expected_edge_id("related_to", bad_source, bad_target),
            bad_source, bad_target, edge_type="related_to",
        )
        graph_manager.get(EDGE_REGISTRY_NAME).insert(bad_edge)
        return graph_manager

    def test_missing_source_node_is_reported(self):
        graph_manager = self._graph_with_one_dangling_edge(break_source=True, break_target=False)
        issues, summary = _validate_edge_integrity(graph_manager)

        assert summary["broken_source"] == 1
        assert any(i["rule"] == "missing_source_node" for i in issues)

    def test_missing_target_node_is_reported(self):
        graph_manager = self._graph_with_one_dangling_edge(break_source=False, break_target=True)
        issues, summary = _validate_edge_integrity(graph_manager)

        assert summary["broken_target"] == 1
        assert any(i["rule"] == "missing_target_node" for i in issues)

    def test_both_endpoints_missing_counts_as_orphan(self):
        graph_manager = self._graph_with_one_dangling_edge(break_source=True, break_target=True)
        issues, summary = _validate_edge_integrity(graph_manager)

        assert summary["orphans"] == 1
        assert summary["dangling"] == 1

    def test_dangling_edge_fails_overall_validation(self):
        graph_manager = self._graph_with_one_dangling_edge(break_source=True, break_target=False)
        report = validate_knowledge_graph(graph_manager)

        assert report["overall_status"] == "fail"
        assert "no_dangling_edges" in report["failed_checks"]
        assert report["integrity_summary"]["dangling_edges"] == 1
        assert any(e["rule"] == "dangling_edges_present" for e in report["errors"])


# --------------------------------------------------------------------------
# Task 2 / Task 3 -- duplicate node ids / duplicate edge ids
# --------------------------------------------------------------------------
#
# compiler.registry.CanonicalRegistry.insert() structurally prevents a
# real duplicate id/urn from ever being stored (DuplicateIdError /
# DuplicateUrnError -- see tests/test_c1_node_construction.py::
# test_duplicate_prevention_on_rebuild_into_same_manager and
# tests/test_c2_edge_construction.py's own analogue), so the scenario
# Task 9 asks for is exercised directly against
# `_validate_node_integrity`/`_validate_edge_integrity`, using a minimal
# read-only registry-manager double that duck-types exactly the subset
# of the CanonicalRegistry/RegistryManager interface this module ever
# calls (`.has()`, `.get()`, and, on the registry itself, `.ids()`/
# `.get_by_id()`/`.values()`/`.size()`/`.name`/`.contains()`) -- this is
# the same kind of interface these validation functions themselves
# document depending on (see validation.py's own PHASE C3 section
# docstring), independent of whether CanonicalRegistry could ever
# actually reach this state.
# --------------------------------------------------------------------------

class _FakeRegistry:
    def __init__(self, name, items_by_id):
        self.name = name
        self._items_by_id = items_by_id

    def ids(self):
        return list(self._items_by_id.keys())

    def get_by_id(self, id_):
        return self._items_by_id.get(id_)

    def values(self):
        return list(self._items_by_id.values())

    def size(self):
        return len(self._items_by_id)

    def contains(self, id_):
        return id_ in self._items_by_id


class _FakeGraphRegistryManager:
    def __init__(self, registries):
        self._registries = registries

    def has(self, name):
        return name in self._registries

    def get(self, name):
        return self._registries[name]


class TestDuplicateIds:
    def test_duplicate_node_ids_reported(self):
        node_a = make_node("node:concept:dup", "dup")
        # A second, distinct node object stored under the SAME key as
        # node_a in the underlying mapping this fake's own .ids() reads
        # from is impossible to express as two dict entries (a dict
        # can't have two values for one key) -- instead, .ids() is
        # overridden directly below to return the id twice, the exact
        # shape `_validate_node_integrity`'s own
        # `len(ids) != len(set(ids))` check is written against.
        registry = _FakeRegistry(NODE_REGISTRY_NAME, {"node:concept:dup": node_a})
        registry.ids = lambda: ["node:concept:dup", "node:concept:dup"]
        manager = _FakeGraphRegistryManager({NODE_REGISTRY_NAME: registry})

        issues, summary = _validate_node_integrity(manager)

        assert any(i["rule"] == "duplicate_node_id" for i in issues)

    def test_duplicate_node_urns_reported(self):
        shared_urn = "urn:kg:node:shared"
        node_a = make_node("node:concept:a", "a", node_urn=shared_urn)
        node_b = make_node("node:concept:b", "b", node_urn=shared_urn)
        registry = _FakeRegistry(
            NODE_REGISTRY_NAME,
            {"node:concept:a": node_a, "node:concept:b": node_b},
        )
        manager = _FakeGraphRegistryManager({NODE_REGISTRY_NAME: registry})

        issues, summary = _validate_node_integrity(manager)

        assert summary["duplicate_urns"] == 1
        assert any(i["rule"] == "duplicate_node_urn" for i in issues)

    def test_duplicate_edge_ids_reported(self):
        edge_a = make_edge("edge:related_to:x:y", "node:concept:x", "node:concept:y")
        registry = _FakeRegistry(EDGE_REGISTRY_NAME, {"edge:related_to:x:y": edge_a})
        registry.ids = lambda: ["edge:related_to:x:y", "edge:related_to:x:y"]
        node_registry = _FakeRegistry(NODE_REGISTRY_NAME, {})
        manager = _FakeGraphRegistryManager({
            EDGE_REGISTRY_NAME: registry, NODE_REGISTRY_NAME: node_registry,
        })

        issues, summary = _validate_edge_integrity(manager)

        assert any(i["rule"] == "duplicate_edge_id" for i in issues)

    def test_duplicate_edge_urns_reported(self):
        shared_urn = "urn:kg:edge:shared"
        edge_a = make_edge("edge:related_to:x:y", "node:concept:x", "node:concept:y", edge_urn=shared_urn)
        edge_b = make_edge("edge:related_to:y:x", "node:concept:y", "node:concept:x", edge_urn=shared_urn)
        registry = _FakeRegistry(
            EDGE_REGISTRY_NAME,
            {"edge:related_to:x:y": edge_a, "edge:related_to:y:x": edge_b},
        )
        node_registry = _FakeRegistry(NODE_REGISTRY_NAME, {})
        manager = _FakeGraphRegistryManager({
            EDGE_REGISTRY_NAME: registry, NODE_REGISTRY_NAME: node_registry,
        })

        issues, summary = _validate_edge_integrity(manager)

        assert summary["duplicate_urns"] == 1
        assert any(i["rule"] == "duplicate_edge_urn" for i in issues)

    def test_real_registries_structurally_prevent_duplicate_insertion(self):
        """The positive-path complement to the fakes above: confirms
        Task 4's own "duplicate insertion impossible" claim against a
        REAL GraphRegistryManager, via _validate_registry_integrity's own
        `duplicate_insertion_structurally_impossible` flag."""
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        issues, summary = _validate_registry_integrity(graph_manager)

        assert summary["duplicate_insertion_structurally_impossible"] is True


# --------------------------------------------------------------------------
# Task 2 / Task 3 -- invalid node types / invalid edge types
# --------------------------------------------------------------------------

class TestInvalidTypes:
    def test_invalid_node_type_reported(self):
        graph_manager = create_graph_registry_manager()
        bad_node = make_node("node:mystery:1", "1", node_type="not_a_real_node_type")
        graph_manager.get(NODE_REGISTRY_NAME).insert(bad_node)

        issues, summary = _validate_node_integrity(graph_manager)

        assert summary["invalid_node_type_count"] == 1
        assert any(i["rule"] == "invalid_node_type" for i in issues)

    def test_invalid_edge_type_reported(self):
        graph_manager = create_graph_registry_manager()
        node_a = make_node("node:concept:a", "a")
        node_b = make_node("node:concept:b", "b")
        graph_manager.get(NODE_REGISTRY_NAME).insert(node_a)
        graph_manager.get(NODE_REGISTRY_NAME).insert(node_b)
        bad_edge = make_edge(
            "edge:mystery:a:b", "node:concept:a", "node:concept:b",
            edge_type="not_a_real_edge_type",
        )
        graph_manager.get(EDGE_REGISTRY_NAME).insert(bad_edge)

        issues, summary = _validate_edge_integrity(graph_manager)

        assert summary["invalid_edge_type_count"] == 1
        assert any(i["rule"] == "invalid_edge_type" for i in issues)

    def test_valid_node_and_edge_types_produce_zero_invalid_counts(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)

        _, node_summary = _validate_node_integrity(graph_manager)
        _, edge_summary = _validate_edge_integrity(graph_manager)

        assert node_summary["invalid_node_type_count"] == 0
        assert edge_summary["invalid_edge_type_count"] == 0


# --------------------------------------------------------------------------
# Task 4 -- registry validation
# --------------------------------------------------------------------------

class TestRegistryValidation:
    def test_all_three_registries_present_on_a_fresh_manager(self):
        graph_manager = create_graph_registry_manager()
        issues, summary = _validate_registry_integrity(graph_manager)

        assert issues == []
        assert summary["required_registries_present"] is True
        assert summary["missing_registries"] == []
        assert set(summary["registries_present"]) == set(GRAPH_REGISTRY_NAMES)

    def test_missing_registry_reported(self):
        # A manager missing the metadata registry entirely -- the
        # `.has()`-driven "missing_graph_registry" path.
        manager = _FakeGraphRegistryManager({
            NODE_REGISTRY_NAME: _FakeRegistry(NODE_REGISTRY_NAME, {}),
            EDGE_REGISTRY_NAME: _FakeRegistry(EDGE_REGISTRY_NAME, {}),
        })
        issues, summary = _validate_registry_integrity(manager)

        assert METADATA_REGISTRY_NAME in summary["missing_registries"]
        assert any(i["rule"] == "missing_graph_registry" for i in issues)

    def test_registry_sizes_reflect_real_content(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        issues, summary = _validate_registry_integrity(graph_manager)

        assert summary["registry_sizes"][NODE_REGISTRY_NAME] == graph_manager.get(NODE_REGISTRY_NAME).size()
        assert summary["registry_sizes"][EDGE_REGISTRY_NAME] == graph_manager.get(EDGE_REGISTRY_NAME).size()


# --------------------------------------------------------------------------
# Task 5 -- graph integrity (namespace/urn consistency)
# --------------------------------------------------------------------------

class TestGraphIntegrity:
    def test_namespace_and_urn_consistent_on_real_graph(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        _, edge_summary = _validate_edge_integrity(graph_manager)
        issues, summary = _validate_graph_integrity(graph_manager, edge_summary)

        assert summary["graph_namespace_consistent"] is True
        assert summary["graph_urn_consistent"] is True
        assert len(summary["distinct_graph_ids"]) == 1

    def test_inconsistent_graph_id_reported(self):
        graph_manager = create_graph_registry_manager()
        node_a = make_node("node:concept:a", "a", graph_id="kg-namespace-one")
        node_b = make_node("node:concept:b", "b", graph_id="kg-namespace-two")
        graph_manager.get(NODE_REGISTRY_NAME).insert(node_a)
        graph_manager.get(NODE_REGISTRY_NAME).insert(node_b)
        _, edge_summary = _validate_edge_integrity(graph_manager)

        issues, summary = _validate_graph_integrity(graph_manager, edge_summary)

        assert summary["graph_namespace_consistent"] is False
        assert any(i["rule"] == "graph_namespace_inconsistent" for i in issues)

    def test_no_traversal_helpers_are_implemented(self):
        """Architectural guard for the task's own "Do NOT implement
        traversal/BFS/DFS/shortest path" list: confirms the validation
        module exposes no such symbol under any of the obvious names."""
        import knowledge_graph.validation as validation_module

        forbidden_substrings = ("bfs", "dfs", "traverse", "shortest_path", "adjacency")
        public_and_private_names = [n.lower() for n in dir(validation_module)]
        for forbidden in forbidden_substrings:
            assert not any(forbidden in name for name in public_and_private_names)


# --------------------------------------------------------------------------
# Determinism (last bullet of Task 3's own "Edge Integrity" list:
# "deterministic edge identity" -- see _validate_edge_integrity's own
# docstring for why it lives in _check_graph_determinism instead)
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_real_ids_are_reproducible(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        issues, summary = _check_graph_determinism(graph_manager)

        assert summary["node_id_recomputation_mismatches"] == 0
        assert summary["edge_id_recomputation_mismatches"] == 0
        assert summary["node_id_shape_violations"] == 0
        assert summary["edge_id_shape_violations"] == 0

    def test_tampered_node_id_flagged_as_non_reproducible(self):
        graph_manager = create_graph_registry_manager()
        # node_id deliberately does NOT match identity.node_id(node_type,
        # compiler_object_id) for this node's own stored fields.
        tampered = make_node("node:concept:not-the-real-id", "real-compiler-id")
        graph_manager.get(NODE_REGISTRY_NAME).insert(tampered)

        issues, summary = _check_graph_determinism(graph_manager)

        assert summary["node_id_recomputation_mismatches"] == 1
        assert any(i["rule"] == "node_id_not_reproducible" for i in issues)
        # A recomputation mismatch is a warning, never an error -- see
        # _check_graph_determinism's own docstring for why.
        assert all(i["severity"] == "warning" for i in issues)


# --------------------------------------------------------------------------
# Task 6 -- deterministic validation report
# --------------------------------------------------------------------------

class TestDeterministicReport:
    def test_report_is_stable_across_repeated_calls_on_same_graph(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)

        report_one = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)
        report_two = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)

        # `generated_at` is a timestamp and is expected to differ; every
        # other field must be byte-for-byte identical given the same,
        # unmutated input graph.
        r1 = copy.deepcopy(report_one)
        r2 = copy.deepcopy(report_two)
        r1.pop("generated_at")
        r2.pop("generated_at")
        assert r1 == r2

    def test_rebuilding_the_same_input_graph_yields_the_same_report(self):
        manager = make_relationship_ready_manager()
        graph_manager_a = build_ready_graph_manager(manager)
        graph_manager_b = build_ready_graph_manager(manager)

        report_a = validate_knowledge_graph(graph_manager_a)
        report_b = validate_knowledge_graph(graph_manager_b)
        report_a.pop("generated_at")
        report_b.pop("generated_at")
        assert report_a == report_b


# --------------------------------------------------------------------------
# Architectural requirement -- validation never mutates its inputs
# --------------------------------------------------------------------------

class TestReadOnlyValidation:
    def test_node_and_edge_registries_are_unchanged_after_validation(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        node_ids_before = sorted(graph_manager.get(NODE_REGISTRY_NAME).ids())
        edge_ids_before = sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids())
        nodes_before = copy.deepcopy(
            [graph_manager.get(NODE_REGISTRY_NAME).get_by_id(i) for i in node_ids_before]
        )
        edges_before = copy.deepcopy(
            [graph_manager.get(EDGE_REGISTRY_NAME).get_by_id(i) for i in edge_ids_before]
        )

        validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)

        assert sorted(graph_manager.get(NODE_REGISTRY_NAME).ids()) == node_ids_before
        assert sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids()) == edge_ids_before
        nodes_after = [graph_manager.get(NODE_REGISTRY_NAME).get_by_id(i) for i in node_ids_before]
        edges_after = [graph_manager.get(EDGE_REGISTRY_NAME).get_by_id(i) for i in edge_ids_before]
        assert nodes_after == nodes_before
        assert edges_after == edges_before

    def test_compiler_registry_manager_is_unchanged_after_validation(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        stats_before = manager.statistics()

        validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)

        assert manager.statistics() == stats_before


# --------------------------------------------------------------------------
# Task 7 -- Compiler State storage (knowledge_graph/state.py)
# --------------------------------------------------------------------------

class TestValidationReportStorage:
    def test_report_round_trips_through_knowledge_graph_state(self):
        from knowledge_graph import state as kg_state

        kg_state.reset_knowledge_graph_state()
        assert kg_state.has_current_knowledge_graph_validation_report() is False

        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        report = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)

        kg_state.set_current_knowledge_graph_validation_report(report)
        assert kg_state.has_current_knowledge_graph_validation_report() is True
        assert kg_state.get_current_knowledge_graph_validation_report() == report

        kg_state.reset_knowledge_graph_state()
        assert kg_state.has_current_knowledge_graph_validation_report() is False


# --------------------------------------------------------------------------
# Task 8 -- pipeline.py integration point
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_pipeline_imports_and_calls_validate_knowledge_graph(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        assert "from knowledge_graph.validation import validate_knowledge_graph" in source
        assert "validate_knowledge_graph(" in source
        assert "kg_state.set_current_knowledge_graph_validation_report(" in source

    def test_validation_call_site_is_after_edge_construction_and_before_json_assembly(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        edges_idx = source.index("build_knowledge_graph_edges(")
        validate_idx = source.index("validate_knowledge_graph(\n")
        json_idx = source.index("json_writer.assemble_chapter_json(")

        assert edges_idx < validate_idx < json_idx

    def test_exactly_one_pipeline_call_site(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        assert source.count("validate_knowledge_graph(\n") == 1


# --------------------------------------------------------------------------
# Backward compatibility -- Phase C0's six ABC contracts stay untouched
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_abc_contracts_are_still_unimplemented(self):
        from knowledge_graph.validation import (
            NodeValidator, EdgeValidator, GraphValidator,
            IntegrityValidator, DeterminismValidator, ReadinessValidator,
        )

        for cls in (
            NodeValidator, EdgeValidator, GraphValidator,
            IntegrityValidator, DeterminismValidator, ReadinessValidator,
        ):
            with pytest.raises(TypeError):
                cls()  # still abstract -- cannot be instantiated directly

    def test_validate_knowledge_graph_never_mutates_compiler_ir_or_educational_json(self):
        # Re-stated at the report level: a chapter's own compiler
        # manifest/statistics are unaffected by running C3 validation on
        # its Knowledge Graph.
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        before = manager.statistics()
        validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)
        after = manager.statistics()
        assert before == after

    def test_empty_graph_is_handled_without_error(self):
        graph_manager = create_graph_registry_manager()
        report = validate_knowledge_graph(graph_manager)

        assert report["node_summary"]["total"] == 0
        assert report["edge_summary"]["total"] == 0
        # No dangling edges is vacuously true with zero edges.
        assert "no_dangling_edges" in report["passed_checks"]
