"""
tests/test_c4_2_fingerprints_readiness.py — unit tests for Phase C4.2:
Knowledge Graph Fingerprints & Readiness (knowledge_graph/
fingerprints.py, and its pipeline.py integration point).

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment.

This file does NOT re-test Phase C0-C3 architecture (node/edge classes,
identity, registries, validate_knowledge_graph() itself) or Phase C4.1
(generate_knowledge_graph_manifest()/generate_knowledge_graph_
statistics() themselves -- see tests/test_c4_1_manifest_statistics.py).
It treats knowledge_graph.build's own manifest/statistics output, and
knowledge_graph.validation.validate_knowledge_graph()'s own output, as
given inputs, the same way tests/test_c4_1_manifest_statistics.py
treats Phase C1-C3's own builders as given inputs. It covers only what
Phase C4.2 actually adds: generate_registry_fingerprints(),
generate_graph_fingerprint(), generate_graph_readiness_report(), and
their combined pipeline.py integration.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.registry_manager import RegistryManager
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships
from compiler.fingerprints import VOLATILE_KEYS

from knowledge_graph.build_nodes import build_knowledge_graph_nodes
from knowledge_graph.build_edges import build_knowledge_graph_edges
from knowledge_graph.validation import validate_knowledge_graph
from knowledge_graph.build import (
    generate_knowledge_graph_manifest,
    generate_knowledge_graph_statistics,
)
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
)
from knowledge_graph.schema import KnowledgeGraphMetadata
from knowledge_graph.fingerprints import (
    GRAPH_FINGERPRINT_VERSION,
    REQUIRED_GRAPH_REGISTRY_NAMES,
    generate_registry_fingerprints,
    generate_graph_fingerprint,
    generate_graph_readiness_report,
    generate_graph_fingerprints,
)

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- same canonical-enveloped item shape
# tests/test_c4_1_manifest_statistics.py's own make_item/
# make_relationship_ready_manager/build_ready_graph_manager already
# establish, duplicated here (not imported) so this file has no
# test-to-test import dependency, matching that file's own standalone-
# fixture style.
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
    """One-shot: C1 nodes -> C2 edges -> C3 validation -> C4.1
    manifest/statistics -- the exact sequence pipeline.py's own
    integration point runs immediately before C4.2. Returns
    (graph_manager, validation_report, manifest, statistics).
    """
    manager = make_relationship_ready_manager()
    graph_manager = build_ready_graph_manager(manager)
    validation_report = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)
    graph_metadata = make_graph_metadata()
    manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
    statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)
    return graph_manager, validation_report, manifest, statistics


# --------------------------------------------------------------------------
# Task 3 -- Registry Fingerprints
# --------------------------------------------------------------------------

class TestRegistryFingerprints:
    def test_one_fingerprint_per_registry(self):
        graph_manager, *_ = build_everything()
        fingerprints = generate_registry_fingerprints(graph_manager)

        assert set(fingerprints) == set(graph_manager.names())
        assert set(fingerprints) == set(GRAPH_REGISTRY_NAMES)

    def test_fingerprints_are_sha256_hex_digests(self):
        graph_manager, *_ = build_everything()
        fingerprints = generate_registry_fingerprints(graph_manager)

        for digest in fingerprints.values():
            assert isinstance(digest, str)
            assert len(digest) == 64
            int(digest, 16)  # raises ValueError if not valid hex

    def test_empty_registry_still_gets_a_fingerprint(self):
        graph_manager = create_graph_registry_manager()
        fingerprints = generate_registry_fingerprints(graph_manager)

        assert set(fingerprints) == set(GRAPH_REGISTRY_NAMES)
        for digest in fingerprints.values():
            assert isinstance(digest, str) and len(digest) == 64

    def test_identical_registry_content_yields_identical_fingerprint(self):
        manager = make_relationship_ready_manager()
        graph_manager_a = build_ready_graph_manager(manager)
        graph_manager_b = build_ready_graph_manager(manager)

        fingerprints_a = generate_registry_fingerprints(graph_manager_a)
        fingerprints_b = generate_registry_fingerprints(graph_manager_b)
        assert fingerprints_a == fingerprints_b

    def test_modified_node_registry_content_changes_only_node_fingerprint(self):
        manager_a = make_relationship_ready_manager()
        graph_manager_a = build_ready_graph_manager(manager_a)

        manager_b = make_relationship_ready_manager()
        # Mutate the underlying compiler concept's own name, which flows
        # into the resulting concept node's display_name -- content-
        # relevant, so both the node registry AND that node's compiler-
        # side registries change, but the EDGE registry's own
        # relationship shape does not.
        concept_registry = manager_b.get("concepts")
        concept_item = concept_registry.lookup(id="c1")
        concept_item["name"] = "Momentum"
        graph_manager_b = build_ready_graph_manager(manager_b)

        fingerprints_a = generate_registry_fingerprints(graph_manager_a)
        fingerprints_b = generate_registry_fingerprints(graph_manager_b)

        assert fingerprints_a[NODE_REGISTRY_NAME] != fingerprints_b[NODE_REGISTRY_NAME]

    def test_read_only_over_registry_manager(self):
        graph_manager, *_ = build_everything()
        node_ids_before = sorted(graph_manager.get(NODE_REGISTRY_NAME).ids())
        edge_ids_before = sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids())

        generate_registry_fingerprints(graph_manager)

        assert sorted(graph_manager.get(NODE_REGISTRY_NAME).ids()) == node_ids_before
        assert sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids()) == edge_ids_before

    def test_volatile_provenance_timestamp_does_not_affect_fingerprint(self):
        # Every VOLATILE_KEYS entry (e.g. a hypothetical "timestamp" a
        # node's copied `provenance` dict might carry) must not affect
        # the digest -- see knowledge_graph/fingerprints.py's own
        # VOLATILE FIELD FILTERING section. Simulated here by directly
        # stamping a volatile key onto a node's provenance dict and
        # confirming the registry fingerprint is unchanged.
        graph_manager, *_ = build_everything()
        node_registry = graph_manager.get(NODE_REGISTRY_NAME)
        fingerprint_before = generate_registry_fingerprints(graph_manager)[NODE_REGISTRY_NAME]

        for node in node_registry.values():
            if getattr(node, "provenance", None) is not None:
                node.provenance["timestamp"] = "2099-01-01T00:00:00+00:00"

        fingerprint_after = generate_registry_fingerprints(graph_manager)[NODE_REGISTRY_NAME]
        assert fingerprint_before == fingerprint_after


# --------------------------------------------------------------------------
# Task 4 -- Knowledge Graph Fingerprint
# --------------------------------------------------------------------------

class TestGraphFingerprint:
    def test_graph_fingerprint_is_sha256_hex_digest(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64
        int(fingerprint, 16)

    def test_identical_graph_yields_identical_fingerprint(self):
        manager = make_relationship_ready_manager()

        graph_manager_a = build_ready_graph_manager(manager)
        report_a = validate_knowledge_graph(graph_manager_a)
        graph_metadata = make_graph_metadata()
        manifest_a = generate_knowledge_graph_manifest(graph_manager_a, report_a, graph_metadata)
        statistics_a = generate_knowledge_graph_statistics(graph_manager_a, report_a)
        fp_a = generate_graph_fingerprint(
            generate_registry_fingerprints(graph_manager_a), manifest_a, statistics_a,
        )

        graph_manager_b = build_ready_graph_manager(manager)
        report_b = validate_knowledge_graph(graph_manager_b)
        manifest_b = generate_knowledge_graph_manifest(graph_manager_b, report_b, graph_metadata)
        statistics_b = generate_knowledge_graph_statistics(graph_manager_b, report_b)
        fp_b = generate_graph_fingerprint(
            generate_registry_fingerprints(graph_manager_b), manifest_b, statistics_b,
        )

        assert fp_a == fp_b

    def test_modified_graph_yields_different_fingerprint(self):
        manager_a = make_relationship_ready_manager()
        graph_manager_a = build_ready_graph_manager(manager_a)
        report_a = validate_knowledge_graph(graph_manager_a, compiler_registry_manager=manager_a)
        graph_metadata = make_graph_metadata()
        manifest_a = generate_knowledge_graph_manifest(graph_manager_a, report_a, graph_metadata)
        statistics_a = generate_knowledge_graph_statistics(graph_manager_a, report_a)
        fp_a = generate_graph_fingerprint(
            generate_registry_fingerprints(graph_manager_a), manifest_a, statistics_a,
        )

        manager_b = make_relationship_ready_manager()
        concept_item = manager_b.get("concepts").lookup(id="c1")
        concept_item["name"] = "Momentum"
        graph_manager_b = build_ready_graph_manager(manager_b)
        report_b = validate_knowledge_graph(graph_manager_b, compiler_registry_manager=manager_b)
        manifest_b = generate_knowledge_graph_manifest(graph_manager_b, report_b, graph_metadata)
        statistics_b = generate_knowledge_graph_statistics(graph_manager_b, report_b)
        fp_b = generate_graph_fingerprint(
            generate_registry_fingerprints(graph_manager_b), manifest_b, statistics_b,
        )

        assert fp_a != fp_b

    def test_volatile_generated_at_fields_ignored(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)

        manifest_touched = copy.deepcopy(manifest)
        manifest_touched["generated_at"] = "2099-01-01T00:00:00+00:00"
        statistics_touched = copy.deepcopy(statistics)
        statistics_touched["generated_at"] = "2099-01-01T00:00:00+00:00"

        fp_original = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)
        fp_touched = generate_graph_fingerprint(
            registry_fingerprints, manifest_touched, statistics_touched,
        )
        assert fp_original == fp_touched

    def test_registry_fingerprint_key_order_does_not_affect_result(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)

        reordered = dict(reversed(list(registry_fingerprints.items())))
        fp_forward = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)
        fp_reversed = generate_graph_fingerprint(reordered, manifest, statistics)
        assert fp_forward == fp_reversed

    def test_changed_registry_fingerprint_changes_graph_fingerprint(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)

        mutated = dict(registry_fingerprints)
        mutated[NODE_REGISTRY_NAME] = "0" * 64
        fp_original = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)
        fp_mutated = generate_graph_fingerprint(mutated, manifest, statistics)
        assert fp_original != fp_mutated

    def test_missing_manifest_or_statistics_handled_without_error(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)

        fp_no_manifest = generate_graph_fingerprint(registry_fingerprints, None, statistics)
        fp_no_statistics = generate_graph_fingerprint(registry_fingerprints, manifest, None)
        assert isinstance(fp_no_manifest, str) and len(fp_no_manifest) == 64
        assert isinstance(fp_no_statistics, str) and len(fp_no_statistics) == 64
        assert fp_no_manifest != fp_no_statistics


# --------------------------------------------------------------------------
# Task 5 -- Knowledge Graph Readiness Report
# --------------------------------------------------------------------------

class TestReadinessReport:
    def test_readiness_has_all_required_fields(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        report = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, statistics,
            registry_fingerprints, graph_fingerprint,
        )
        for key in ("ready", "checks", "warnings", "readiness_summary"):
            assert key in report

    def test_fully_built_graph_is_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        report = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, statistics,
            registry_fingerprints, graph_fingerprint,
        )
        assert report["ready"] is True
        assert report["readiness_summary"]["failed_count"] == 0
        assert all(c["passed"] for c in report["checks"])

    def test_missing_manifest_marks_not_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        report = generate_graph_readiness_report(
            graph_manager, validation_report, None, statistics,
            registry_fingerprints, graph_fingerprint,
        )
        assert report["ready"] is False
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["graph_manifest_exists"] is False

    def test_missing_statistics_marks_not_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        report = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, None,
            registry_fingerprints, graph_fingerprint,
        )
        assert report["ready"] is False
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["graph_statistics_exists"] is False

    def test_missing_registry_fingerprints_marks_not_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        graph_fingerprint = "0" * 64

        report = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, statistics,
            None, graph_fingerprint,
        )
        assert report["ready"] is False
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["registry_fingerprints_generated"] is False

    def test_missing_graph_fingerprint_marks_not_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)

        report = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, statistics,
            registry_fingerprints, None,
        )
        assert report["ready"] is False
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["graph_fingerprint_generated"] is False

    def test_failing_validation_report_marks_not_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        failing_report = copy.deepcopy(validation_report)
        failing_report["overall_status"] = "fail"

        report = generate_graph_readiness_report(
            graph_manager, failing_report, manifest, statistics,
            registry_fingerprints, graph_fingerprint,
        )
        assert report["ready"] is False
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["graph_validation_passed"] is False

    def test_mismatched_node_count_marks_not_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        tampered_statistics = copy.deepcopy(statistics)
        tampered_statistics["total_nodes"] = manifest["node_count"] + 1

        report = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, tampered_statistics,
            registry_fingerprints, graph_fingerprint,
        )
        assert report["ready"] is False
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["node_count_matches_statistics"] is False

    def test_mismatched_edge_count_marks_not_ready(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        tampered_statistics = copy.deepcopy(statistics)
        tampered_statistics["total_edges"] = manifest["edge_count"] + 1

        report = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, tampered_statistics,
            registry_fingerprints, graph_fingerprint,
        )
        assert report["ready"] is False
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["edge_count_matches_statistics"] is False

    def test_missing_required_registry_marks_not_ready(self):
        graph_manager = create_graph_registry_manager()
        validation_report = validate_knowledge_graph(graph_manager)
        graph_metadata = make_graph_metadata()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        # Simulate a missing registry the required-registries check should
        # catch, without mutating the real GraphRegistryManager internals
        # -- a thin stand-in object exposing only the .has()/.names()
        # surface generate_graph_readiness_report() actually reads.
        class _MissingMetadataManager:
            def has(self, name):
                return name != METADATA_REGISTRY_NAME
            def names(self):
                return [n for n in graph_manager.names() if n != METADATA_REGISTRY_NAME]

        report = generate_graph_readiness_report(
            _MissingMetadataManager(), validation_report, manifest, statistics,
            registry_fingerprints, graph_fingerprint,
        )
        names = {c["name"]: c["passed"] for c in report["checks"]}
        assert names["required_registries_exist"] is False
        assert report["ready"] is False

    def test_never_repairs_anything(self):
        # Architectural requirement: "Produce findings only. Never repair
        # anything." A failing readiness report must not mutate any
        # argument it was given.
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        manifest_before = copy.deepcopy(manifest)
        statistics_before = copy.deepcopy(statistics)
        node_ids_before = sorted(graph_manager.get(NODE_REGISTRY_NAME).ids())

        generate_graph_readiness_report(
            graph_manager, validation_report, None, None,
            None, None,
        )

        assert manifest == manifest_before
        assert statistics == statistics_before
        assert sorted(graph_manager.get(NODE_REGISTRY_NAME).ids()) == node_ids_before


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_registry_fingerprints_stable_across_repeated_calls(self):
        graph_manager, *_ = build_everything()
        fp_one = generate_registry_fingerprints(graph_manager)
        fp_two = generate_registry_fingerprints(graph_manager)
        assert fp_one == fp_two

    def test_graph_fingerprint_stable_across_repeated_calls(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        fp_one = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)
        fp_two = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)
        assert fp_one == fp_two

    def test_readiness_report_stable_across_repeated_calls(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        registry_fingerprints = generate_registry_fingerprints(graph_manager)
        graph_fingerprint = generate_graph_fingerprint(registry_fingerprints, manifest, statistics)

        report_one = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, statistics,
            registry_fingerprints, graph_fingerprint,
        )
        report_two = generate_graph_readiness_report(
            graph_manager, validation_report, manifest, statistics,
            registry_fingerprints, graph_fingerprint,
        )
        assert report_one == report_two


# --------------------------------------------------------------------------
# Read-only behavior / backward compatibility
# --------------------------------------------------------------------------

class TestReadOnlyBehavior:
    def test_node_and_edge_registries_unchanged_after_full_pass(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        node_ids_before = sorted(graph_manager.get(NODE_REGISTRY_NAME).ids())
        edge_ids_before = sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids())

        results = generate_graph_fingerprints(
            graph_manager, manifest=manifest, statistics=statistics,
            validation_report=validation_report,
        )
        assert results["graph_fingerprint"]

        assert sorted(graph_manager.get(NODE_REGISTRY_NAME).ids()) == node_ids_before
        assert sorted(graph_manager.get(EDGE_REGISTRY_NAME).ids()) == edge_ids_before

    def test_compiler_ir_unchanged_after_c4_2(self):
        manager = make_relationship_ready_manager()
        graph_manager = build_ready_graph_manager(manager)
        validation_report = validate_knowledge_graph(graph_manager, compiler_registry_manager=manager)
        graph_metadata = make_graph_metadata()
        manifest = generate_knowledge_graph_manifest(graph_manager, validation_report, graph_metadata)
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)
        stats_before = manager.statistics()

        generate_graph_fingerprints(
            graph_manager, manifest=manifest, statistics=statistics,
            validation_report=validation_report,
        )

        assert manager.statistics() == stats_before

    def test_manifest_and_statistics_arguments_unchanged(self):
        graph_manager, validation_report, manifest, statistics = build_everything()
        manifest_before = copy.deepcopy(manifest)
        statistics_before = copy.deepcopy(statistics)

        generate_graph_fingerprints(
            graph_manager, manifest=manifest, statistics=statistics,
            validation_report=validation_report,
        )

        assert manifest == manifest_before
        assert statistics == statistics_before

    def test_no_query_index_traversal_or_optimization_symbols_exist(self):
        import knowledge_graph.fingerprints as fingerprints_module

        forbidden_substrings = (
            "query", "index", "traverse", "bfs", "dfs", "optimi", "serializ",
        )
        # Only this module's OWN public/private symbols -- dunder
        # attributes every module carries regardless of its own content
        # (e.g. `__cached__`) are excluded, matching tests/
        # test_c4_1_manifest_statistics.py's own identical fix for this
        # exact false-positive.
        names = [
            n.lower() for n in dir(fingerprints_module)
            if not (n.startswith("__") and n.endswith("__"))
        ]
        for forbidden in forbidden_substrings:
            assert not any(forbidden in name for name in names)


# --------------------------------------------------------------------------
# State integration (Task 6)
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_fingerprints_and_readiness_round_trip_through_knowledge_graph_state(self):
        from knowledge_graph import state as kg_state

        kg_state.reset_knowledge_graph_state()
        assert kg_state.has_current_registry_fingerprints() is False
        assert kg_state.has_current_graph_fingerprint() is False
        assert kg_state.has_current_knowledge_graph_readiness_report() is False

        graph_manager, validation_report, manifest, statistics = build_everything()
        results = generate_graph_fingerprints(
            graph_manager, manifest=manifest, statistics=statistics,
            validation_report=validation_report,
        )

        kg_state.set_current_registry_fingerprints(results["registry_fingerprints"])
        kg_state.set_current_graph_fingerprint(results["graph_fingerprint"])
        kg_state.set_current_knowledge_graph_readiness_report(results["readiness_report"])

        assert kg_state.has_current_registry_fingerprints() is True
        assert kg_state.has_current_graph_fingerprint() is True
        assert kg_state.has_current_knowledge_graph_readiness_report() is True
        assert kg_state.get_current_registry_fingerprints() == results["registry_fingerprints"]
        assert kg_state.get_current_graph_fingerprint() == results["graph_fingerprint"]
        assert kg_state.get_current_knowledge_graph_readiness_report() == results["readiness_report"]

        kg_state.reset_knowledge_graph_state()
        assert kg_state.has_current_registry_fingerprints() is False
        assert kg_state.has_current_graph_fingerprint() is False
        assert kg_state.has_current_knowledge_graph_readiness_report() is False


# --------------------------------------------------------------------------
# Pipeline integration (Task 7)
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_pipeline_imports_and_calls_generate_graph_fingerprints(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        assert "from knowledge_graph.fingerprints import generate_graph_fingerprints" in source
        assert "generate_graph_fingerprints(" in source
        assert "kg_state.set_current_registry_fingerprints(" in source
        assert "kg_state.set_current_graph_fingerprint(" in source
        assert "kg_state.set_current_knowledge_graph_readiness_report(" in source

    def test_call_site_is_after_c4_1_and_before_c4_3(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        c4_1_marker = source.index("kg_state.set_current_knowledge_graph_statistics(")
        c4_2_marker = source.index("generate_graph_fingerprints(")
        assert c4_1_marker < c4_2_marker

        # UPDATED FOR PHASE C4.3: this test originally guarded against
        # Phase C4.2 prematurely beginning Phase C4.3 (back when C4.3
        # had not been authorized yet). Phase C4.3 has since been
        # implemented as its own sanctioned phase (see
        # knowledge_graph/finalize.py and tests/test_c4_3_finalization.py),
        # so the correct invariant this test enforces now is ordering,
        # not absence: wherever Phase C4.3's own call site appears, it
        # must come AFTER this C4.2 call site, never before/instead of
        # it. This still fails loudly if a future edit ever reorders
        # the two phases.
        if "generate_graph_build_summary(" in source:
            c4_3_marker = source.index("generate_graph_build_summary(")
            assert c4_2_marker < c4_3_marker

    def test_exactly_one_pipeline_call_site(self):
        import inspect
        import pipeline

        source = inspect.getsource(pipeline)
        assert source.count("generate_graph_fingerprints(") == 1


# --------------------------------------------------------------------------
# Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_c4_1_manifest_and_statistics_shape_unaffected(self):
        # Phase C4.2 must not have changed what Phase C4.1 produces.
        graph_manager, validation_report, manifest, statistics = build_everything()
        for key in (
            "generated_at", "graph_schema_version", "identity_version",
            "graph_id", "graph_urn", "source_chapter_identifier",
            "node_registry_versions", "node_count", "edge_count",
            "node_type_counts", "edge_type_counts", "graph_status",
            "graph_generation_status",
        ):
            assert key in manifest
        for key in (
            "generated_at", "node_registry_sizes", "edges_by_type",
            "total_nodes", "total_edges", "nodes_by_source_registry",
            "validation_summary",
        ):
            assert key in statistics

    def test_no_graph_build_summary_or_final_status_symbols(self):
        import knowledge_graph.fingerprints as fingerprints_module

        assert not hasattr(fingerprints_module, "generate_knowledge_graph_build_summary")
        assert not hasattr(fingerprints_module, "generate_final_graph_status")
        assert not hasattr(fingerprints_module, "KnowledgeGraphBuildSummary")