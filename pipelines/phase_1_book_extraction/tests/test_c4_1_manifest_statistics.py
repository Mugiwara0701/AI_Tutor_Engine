"""
tests/test_c4_1_manifest_statistics.py — unit tests for Phase C4.1:
Knowledge Graph Manifest & Statistics (knowledge_graph/build.py, and its
pipeline.py integration point).

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment.

This file does NOT re-test Phase C0-C2 architecture (node/edge classes,
identity, registries) or Phase C3 (validate_knowledge_graph() itself --
see tests/test_c3_graph_validation.py). It treats
knowledge_graph.validation.validate_knowledge_graph()'s own output as a
given input, the same way tests/test_c3_graph_validation.py treats
Phase C1/C2's own builders as given inputs. It covers only what Phase
C4.1 actually adds: generate_knowledge_graph_manifest(),
generate_knowledge_graph_statistics(), and their combined pipeline.py
integration.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.registry_manager import RegistryManager
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships

from knowledge_graph.build_nodes import build_knowledge_graph_nodes
from knowledge_graph.build_edges import build_knowledge_graph_edges
from knowledge_graph.validation import validate_knowledge_graph
from knowledge_graph.registries import (
    NODE_REGISTRY_NAME,
    EDGE_REGISTRY_NAME,
    GraphRegistryManager,
    create_graph_registry_manager,
)
from knowledge_graph.identity import (
    graph_id as expected_graph_id,
    graph_urn as expected_graph_urn,
    IDENTITY_VERSION,
)
from knowledge_graph.schema import (
    KNOWLEDGE_GRAPH_SCHEMA_VERSION,
    KnowledgeGraphMetadata,
)
from knowledge_graph.build import (
    GRAPH_BUILD_VERSION,
    generate_knowledge_graph_manifest,
    generate_knowledge_graph_statistics,
)

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- same canonical-enveloped item shape
# tests/test_c3_graph_validation.py::make_item / make_relationship_ready_
# manager / build_ready_graph_manager already establish, duplicated here
# (not imported) so this file has no test-to-test import dependency,
# matching that file's own standalone-fixture style.
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
    graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
    graph_manager = build_knowledge_graph_edges(
        manager, graph_manager, graph_namespace=NAMESPACE,
    )
    return graph_manager


def make_graph_metadata(*, source_compiler_version="B5.1") -> KnowledgeGraphMetadata:
    return KnowledgeGraphMetadata(
        graph_id=expected_graph_id(NAMESPACE),
        graph_urn=expected_graph_urn(NAMESPACE),
        source_chapter_identifier=NAMESPACE,
        source_compiler_version=source_compiler_version,
    )


def build_everything():
    """One-shot: C1 nodes -> C2 edges -> C3 validation -- the exact
    sequence pipeline.py's own integration point runs immediately before
    C4.1. Returns (graph_manager, validation_report, graph_metadata)."""
    manager = make_relationship_ready_manager()
    graph_manager = build_ready_graph_manager(manager)
    validation_report = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)
    graph_metadata = make_graph_metadata()
    return graph_manager, validation_report, graph_metadata


# --------------------------------------------------------------------------
# Task 3 -- Manifest generation
# --------------------------------------------------------------------------

class TestManifestGeneration:
    def test_manifest_has_all_required_fields(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)

        for key in (
            "generated_at", "graph_schema_version", "identity_version",
            "graph_id", "graph_urn", "source_chapter_identifier",
            "node_registry_versions", "node_count", "edge_count",
            "node_type_counts", "edge_type_counts", "graph_status",
            "graph_generation_status",
        ):
            assert key in manifest

    def test_manifest_identity_matches_graph_metadata(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)

        assert manifest["graph_id"] == graph_metadata.graph_id
        assert manifest["graph_urn"] == graph_metadata.graph_urn
        assert manifest["source_chapter_identifier"] == graph_metadata.source_chapter_identifier

    def test_manifest_versions_match_schema_constants(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)

        assert manifest["graph_schema_version"] == KNOWLEDGE_GRAPH_SCHEMA_VERSION
        assert manifest["identity_version"] == IDENTITY_VERSION
        assert manifest["node_registry_versions"]["build"] == GRAPH_BUILD_VERSION

    def test_manifest_counts_match_validation_report_not_a_rescan(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)

        assert manifest["node_count"] == validation_report["node_summary"]["total"]
        assert manifest["edge_count"] == validation_report["edge_summary"]["total"]
        assert manifest["node_type_counts"] == validation_report["node_summary"]["by_node_type"]
        assert manifest["edge_type_counts"] == validation_report["edge_summary"]["by_edge_type"]
        assert manifest["node_count"] > 0
        assert manifest["edge_count"] > 0

    def test_manifest_generation_status_is_generated_regardless_of_validation_outcome(self):
        # graph_status/graph_generation_status report only that manifest
        # generation itself completed -- never a correctness verdict.
        graph_manager, validation_report, graph_metadata = build_everything()
        failing_report = copy.deepcopy(validation_report)
        failing_report["overall_status"] = "fail"
        failing_report["failed_checks"] = ["no_dangling_edges"]

        manifest = generate_knowledge_graph_manifest(graph_manager, failing_report, graph_metadata)

        assert manifest["graph_status"] == "generated"
        assert manifest["graph_generation_status"] == "generated"

    def test_source_compiler_version_folded_into_registry_versions(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)

        assert manifest["node_registry_versions"]["source_compiler"] == "B5.1"

    def test_missing_source_compiler_version_handled_without_error(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        graph_metadata_no_compiler = make_graph_metadata(source_compiler_version=None)

        manifest = generate_knowledge_graph_manifest(
            graph_manager, validation_report, graph_metadata_no_compiler,
        )
        assert manifest["node_registry_versions"]["source_compiler"] == ""


# --------------------------------------------------------------------------
# Task 4 -- Statistics generation
# --------------------------------------------------------------------------

class TestStatisticsGeneration:
    def test_statistics_has_all_required_fields(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)

        for key in (
            "generated_at", "node_registry_sizes", "edges_by_type",
            "total_nodes", "total_edges", "nodes_by_source_registry",
            "validation_summary",
        ):
            assert key in statistics

    def test_statistics_totals_match_validation_report(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert statistics["total_nodes"] == validation_report["node_summary"]["total"]
        assert statistics["total_edges"] == validation_report["edge_summary"]["total"]
        assert statistics["edges_by_type"] == validation_report["edge_summary"]["by_edge_type"]

    def test_registry_sizes_match_validation_registry_summary(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert statistics["node_registry_sizes"] == validation_report["registry_summary"]["registry_sizes"]

    def test_nodes_by_source_registry_sums_to_total_nodes(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert sum(statistics["nodes_by_source_registry"].values()) == statistics["total_nodes"]
        # Every node in the fixture wraps a real compiler object, so every
        # compiler registry name present is one this fixture actually
        # populated (topics/concepts/definitions/glossary/equations/
        # figures/activities).
        assert set(statistics["nodes_by_source_registry"]) <= {
            "topics", "concepts", "definitions", "glossary", "equations",
            "figures", "diagrams", "tables", "activities", "boxes",
            "warnings", "notes", "examples",
        }

    def test_validation_summary_carries_forward_overall_status(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert statistics["validation_summary"]["status"] == validation_report["overall_status"]

    def test_empty_graph_produces_zeroed_statistics_without_error(self):
        graph_manager = create_graph_registry_manager()
        validation_report = validate_knowledge_graph(graph_manager)
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert statistics["total_nodes"] == 0
        assert statistics["total_edges"] == 0
        assert statistics["nodes_by_source_registry"] == {}


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_manifest_stable_across_repeated_calls(self):
        graph_manager, validation_report, graph_metadata = build_everything()

        manifest_one = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        manifest_two = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        manifest_one.pop("generated_at")
        manifest_two.pop("generated_at")
        assert manifest_one == manifest_two

    def test_statistics_stable_across_repeated_calls(self):
        graph_manager, validation_report, graph_metadata = build_everything()

        statistics_one = generate_knowledge_graph_statistics(graph_manager, validation_report)
        statistics_two = generate_knowledge_graph_statistics(graph_manager, validation_report)
        statistics_one.pop("generated_at")
        statistics_two.pop("generated_at")
        assert statistics_one == statistics_two

    def test_rebuilding_the_same_input_graph_yields_the_same_manifest_and_statistics(self):
        manager = make_relationship_ready_manager()
        graph_manager_a = build_ready_graph_manager(manager)
        graph_manager_b = build_ready_graph_manager(manager)
        report_a = validate_knowledge_graph(graph_manager_a)
        report_b = validate_knowledge_graph(graph_manager_b)
        graph_metadata = make_graph_metadata()

        manifest_a = generate_knowledge_graph_manifest(graph_manager_a, report_a, graph_metadata)
        manifest_b = generate_knowledge_graph_manifest(graph_manager_b, report_b, graph_metadata)
        manifest_a.pop("generated_at")
        manifest_b.pop("generated_at")
        assert manifest_a == manifest_b

        statistics_a = generate_knowledge_graph_statistics(graph_manager_a, report_a)
        statistics_b = generate_knowledge_graph_statistics(graph_manager_b, report_b)
        statistics_a.pop("generated_at")
        statistics_b.pop("generated_at")
        assert statistics_a == statistics_b


# --------------------------------------------------------------------------
# Read-only behavior
# --------------------------------------------------------------------------

class TestReadOnlyBehavior:
    def test_node_and_edge_registries_unchanged_after_manifest_and_statistics(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        node_ids_before = sorted(graph_manager.get(NODE_REGISTRY_NAME).ids())
        edge_ids_before = sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids())

        generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert sorted(graph_manager.get(NODE_REGISTRY_NAME).ids()) == node_ids_before
        assert sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids()) == edge_ids_before

    def test_validation_report_argument_unchanged(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        report_before = copy.deepcopy(validation_report)

        generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert validation_report == report_before

    def test_graph_metadata_argument_unchanged(self):
        graph_manager, validation_report, graph_metadata = build_everything()
        metadata_before = copy.deepcopy(graph_metadata)

        generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)

        assert graph_metadata == metadata_before


# --------------------------------------------------------------------------
# State integration (Task 5)
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_manifest_and_statistics_round_trip_through_knowledge_graph_state(self):
        from knowledge_graph import state as kg_state

        kg_state.reset_knowledge_graph_state()
        assert kg_state.has_current_knowledge_graph_manifest() is False
        assert kg_state.has_current_knowledge_graph_statistics() is False

        graph_manager, validation_report, graph_metadata = build_everything()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)

        kg_state.set_current_knowledge_graph_manifest(manifest)
        kg_state.set_current_knowledge_graph_statistics(statistics)

        assert kg_state.has_current_knowledge_graph_manifest() is True
        assert kg_state.has_current_knowledge_graph_statistics() is True
        assert kg_state.get_current_knowledge_graph_manifest() == manifest
        assert kg_state.get_current_knowledge_graph_statistics() == statistics

        kg_state.reset_knowledge_graph_state()
        assert kg_state.has_current_knowledge_graph_manifest() is False
        assert kg_state.has_current_knowledge_graph_statistics() is False


# --------------------------------------------------------------------------
# Pipeline integration (Task 6)
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_pipeline_imports_and_calls_both_generators(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        assert (
            "from knowledge_graph.build import generate_knowledge_graph_manifest, "
            "generate_knowledge_graph_statistics" in source
        )
        assert "generate_knowledge_graph_manifest(" in source
        assert "generate_knowledge_graph_statistics(" in source
        assert "kg_state.set_current_knowledge_graph_manifest(" in source
        assert "kg_state.set_current_knowledge_graph_statistics(" in source

    def test_call_site_is_after_c3_validation_and_before_json_assembly(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        validate_idx = source.index("validate_knowledge_graph(\n")
        manifest_idx = source.index("generate_knowledge_graph_manifest(\n")
        statistics_idx = source.index("generate_knowledge_graph_statistics(\n")
        json_idx = source.index("json_writer.assemble_chapter_json(")

        assert validate_idx < manifest_idx < statistics_idx < json_idx

    def test_exactly_one_pipeline_call_site_each(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        assert source.count("generate_knowledge_graph_manifest(\n") == 1
        assert source.count("generate_knowledge_graph_statistics(\n") == 1


# --------------------------------------------------------------------------
# Backward compatibility / out-of-scope guards
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_knowledge_graph_schema_field_sets_unchanged(self):
        import dataclasses
        from knowledge_graph.schema import KnowledgeGraphManifest, KnowledgeGraphStatistics

        manifest_fields = {f.name for f in dataclasses.fields(KnowledgeGraphManifest)}
        statistics_fields = {f.name for f in dataclasses.fields(KnowledgeGraphStatistics)}

        assert manifest_fields == {
            "generated_at", "graph_schema_version", "identity_version",
            "graph_id", "graph_urn", "source_chapter_identifier",
            "node_registry_versions", "node_count", "edge_count",
            "node_type_counts", "edge_type_counts", "graph_status",
            "graph_generation_status",
        }
        assert statistics_fields == {
            "generated_at", "node_registry_sizes", "edges_by_type",
            "total_nodes", "total_edges", "nodes_by_source_registry",
            "validation_summary",
        }

    def test_no_fingerprint_readiness_or_build_summary_symbols_exist(self):
        """Architectural guard for the task's own DO NOT IMPLEMENT list:
        confirms knowledge_graph/build.py exposes no fingerprint/
        readiness/build-summary/final-status symbol under any of the
        obvious names."""
        import knowledge_graph.build as build_module

        forbidden_substrings = (
            "fingerprint", "readiness", "buildsummary", "build_summary",
            "final_status", "finalstatus",
        )
        names = [n.lower() for n in dir(build_module)]
        for forbidden in forbidden_substrings:
            assert not any(forbidden in name for name in names)

    def test_no_query_index_traversal_or_optimization_symbols_exist(self):
        import knowledge_graph.build as build_module

        forbidden_substrings = (
            "query", "index", "traverse", "bfs", "dfs", "optimi", "cache",
        )
        # Only this module's OWN public/private symbols -- dunder
        # attributes every module carries regardless of its own content
        # (e.g. `__cached__`, the stdlib-populated path to this module's
        # own .pyc) are not something Phase C4.1 authored, so they are
        # excluded here rather than producing a false positive against
        # Python's own module machinery.
        names = [
            n.lower() for n in dir(build_module)
            if not (n.startswith("__") and n.endswith("__"))
        ]
        for forbidden in forbidden_substrings:
            assert not any(forbidden in name for name in names)

    def test_compiler_ir_unchanged_after_c4_1(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        validation_report = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)
        graph_metadata = make_graph_metadata()
        stats_before = manager.statistics()

        generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        generate_knowledge_graph_statistics(graph_manager, validation_report)

        assert manager.statistics() == stats_before