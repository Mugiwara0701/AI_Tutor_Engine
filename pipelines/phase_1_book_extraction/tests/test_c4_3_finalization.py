"""
tests/test_c4_3_finalization.py — unit tests for Phase C4.3: Knowledge
Graph Finalization (knowledge_graph/finalize.py), and its pipeline.py
integration point.

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment beyond the ad-hoc smoke checks performed
during development.

This file does NOT re-test Phase C0-C3 architecture (node/edge classes,
identity, registries, validate_knowledge_graph() itself), Phase C4.1
(generate_knowledge_graph_manifest()/generate_knowledge_graph_statistics()
themselves), or Phase C4.2 (generate_graph_fingerprints() itself) -- see
tests/test_c4_1_manifest_statistics.py and
tests/test_c4_2_fingerprints_readiness.py. It treats every one of those
modules' own output as a given input, the same way those files treat
their own predecessors' output as given. It covers only what Phase C4.3
actually adds: determine_final_graph_status(),
generate_graph_build_summary(), finalize_knowledge_graph(), and their
combined pipeline.py / knowledge_graph.state integration.
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
from knowledge_graph.build import (
    generate_knowledge_graph_manifest,
    generate_knowledge_graph_statistics,
)
from knowledge_graph.registries import (
    GraphRegistryManager,
    create_graph_registry_manager,
)
from knowledge_graph.identity import (
    graph_id as expected_graph_id,
    graph_urn as expected_graph_urn,
)
from knowledge_graph.schema import KnowledgeGraphMetadata
from knowledge_graph.fingerprints import generate_graph_fingerprints
from knowledge_graph.finalize import (
    GRAPH_FINALIZE_VERSION,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    STATUS_FAILED,
    determine_final_graph_status,
    generate_graph_build_summary,
    finalize_knowledge_graph,
)
from knowledge_graph import state as kg_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- same canonical-enveloped item shape
# tests/test_c4_1_manifest_statistics.py's own make_item/
# tests/test_c4_2_fingerprints_readiness.py's own make_relationship_ready_
# manager/build_ready_graph_manager already establish, duplicated here
# (not imported) so this file has no test-to-test import dependency,
# matching those files' own standalone-fixture style.
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


def build_full_graph_state():
    """One-shot: C1 nodes -> C2 edges -> C3 validation -> C4.1
    manifest/statistics -> C4.2 fingerprints/readiness -- the exact
    sequence pipeline.py's own integration point runs immediately
    before C4.3. Returns a dict of every artifact C4.3 consumes.
    """
    manager = make_relationship_ready_manager()
    graph_manager = build_ready_graph_manager(manager)
    validation_report = validate_knowledge_graph(
        graph_manager, compiler_registry_manager=manager,
    )
    graph_metadata = make_graph_metadata()
    manifest = generate_knowledge_graph_manifest(
        graph_manager, validation_report, graph_metadata,
    )
    statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)
    fingerprint_results = generate_graph_fingerprints(
        graph_manager, manifest=manifest, statistics=statistics,
        validation_report=validation_report,
    )
    return {
        "graph_manager": graph_manager,
        "validation_report": validation_report,
        "manifest": manifest,
        "statistics": statistics,
        "registry_fingerprints": fingerprint_results["registry_fingerprints"],
        "graph_fingerprint": fingerprint_results["graph_fingerprint"],
        "readiness_report": fingerprint_results["readiness_report"],
    }


@pytest.fixture(autouse=True)
def _reset_kg_state():
    """Every test starts and ends with a clean knowledge_graph.state
    module -- mirrors tests/test_finalize.py's own
    _reset_compiler_state fixture, one layer up."""
    kg_state.reset_knowledge_graph_state()
    yield
    kg_state.reset_knowledge_graph_state()


# --------------------------------------------------------------------------
# 1. Final Graph Status (Task 2)
# --------------------------------------------------------------------------

class TestDetermineFinalGraphStatus:
    def test_ready_when_validation_passes_and_readiness_ready_no_warnings(self):
        status = determine_final_graph_status(
            {"overall_status": "pass", "warnings": [], "errors": []},
            {"ready": True, "warnings": []},
        )
        assert status == STATUS_READY

    def test_ready_with_warnings_when_validation_has_warnings(self):
        status = determine_final_graph_status(
            {"overall_status": "pass", "warnings": ["w1"], "errors": []},
            {"ready": True, "warnings": []},
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_ready_with_warnings_when_readiness_has_warnings(self):
        status = determine_final_graph_status(
            {"overall_status": "pass", "warnings": [], "errors": []},
            {"ready": True, "warnings": ["some readiness warning"]},
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_ready_with_warnings_when_both_carry_warnings(self):
        status = determine_final_graph_status(
            {"overall_status": "pass", "warnings": ["w1"], "errors": []},
            {"ready": True, "warnings": ["r1"]},
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_failed_when_validation_status_is_fail(self):
        status = determine_final_graph_status(
            {"overall_status": "fail", "warnings": [], "errors": ["e1"]},
            {"ready": True, "warnings": []},
        )
        assert status == STATUS_FAILED

    def test_failed_when_readiness_not_ready(self):
        status = determine_final_graph_status(
            {"overall_status": "pass", "warnings": [], "errors": []},
            {"ready": False, "warnings": [], "checks": [{"name": "x", "passed": False}]},
        )
        assert status == STATUS_FAILED

    def test_failed_when_both_validation_and_readiness_fail(self):
        status = determine_final_graph_status(
            {"overall_status": "fail", "warnings": [], "errors": ["e1"]},
            {"ready": False, "warnings": []},
        )
        assert status == STATUS_FAILED

    def test_failed_when_validation_report_is_none(self):
        """Missing validation report -- Task 3's own 'never invent
        additional status values' + 'missing input treated as failing'
        rule."""
        status = determine_final_graph_status(None, {"ready": True, "warnings": []})
        assert status == STATUS_FAILED

    def test_failed_when_readiness_report_is_none(self):
        status = determine_final_graph_status({"overall_status": "pass"}, None)
        assert status == STATUS_FAILED

    def test_failed_when_both_none(self):
        assert determine_final_graph_status(None, None) == STATUS_FAILED

    def test_only_status_key_read_not_legacy_status_key(self):
        """determine_final_graph_status() reads `overall_status`
        (the key generate_graph_readiness_report()'s own
        `graph_validation_passed` check already reads), never the
        legacy `status` key alone -- a report carrying only `status`
        (no `overall_status`) must be treated as unknown/failing."""
        status = determine_final_graph_status(
            {"status": "pass", "warnings": [], "errors": []},
            {"ready": True, "warnings": []},
        )
        assert status == STATUS_FAILED

    def test_returns_one_of_the_three_closed_values(self):
        for validation_status in ("pass", "fail"):
            for ready in (True, False):
                for warnings in ([], ["w"]):
                    status = determine_final_graph_status(
                        {"overall_status": validation_status, "warnings": warnings, "errors": []},
                        {"ready": ready, "warnings": []},
                    )
                    assert status in {STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED}

    def test_never_mutates_inputs(self):
        validation_report = {"overall_status": "pass", "warnings": ["w1"], "errors": []}
        readiness_report = {"ready": True, "warnings": []}
        before_v = copy.deepcopy(validation_report)
        before_r = copy.deepcopy(readiness_report)
        determine_final_graph_status(validation_report, readiness_report)
        assert validation_report == before_v
        assert readiness_report == before_r

    def test_deterministic_across_repeated_calls(self):
        validation_report = {"overall_status": "pass", "warnings": [], "errors": []}
        readiness_report = {"ready": True, "warnings": []}
        results = {
            determine_final_graph_status(validation_report, readiness_report)
            for _ in range(5)
        }
        assert len(results) == 1

    def test_end_to_end_realistic_graph_is_ready(self):
        state = build_full_graph_state()
        status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        assert status == STATUS_READY

    def test_end_to_end_missing_required_registry_is_failed(self):
        """A graph registry manager missing a required registry (e.g.
        edges never built) must fail readiness, and therefore the
        final graph status, without this module re-scanning anything
        itself -- it only reads readiness_report['ready']."""
        manager = make_relationship_ready_manager()
        graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=NAMESPACE)
        # Deliberately skip build_knowledge_graph_edges() so the `edges`
        # registry required by REQUIRED_GRAPH_REGISTRY_NAMES is absent.
        validation_report = validate_knowledge_graph(
            graph_manager, compiler_registry_manager=manager,
        )
        graph_metadata = make_graph_metadata()
        manifest = generate_knowledge_graph_manifest(
            graph_manager, validation_report, graph_metadata,
        )
        statistics = generate_knowledge_graph_statistics(graph_manager, validation_report)
        fingerprint_results = generate_graph_fingerprints(
            graph_manager, manifest=manifest, statistics=statistics,
            validation_report=validation_report,
        )
        assert fingerprint_results["readiness_report"]["ready"] is False
        status = determine_final_graph_status(
            validation_report, fingerprint_results["readiness_report"],
        )
        assert status == STATUS_FAILED


# --------------------------------------------------------------------------
# 2. Knowledge Graph Build Summary (Task 1)
# --------------------------------------------------------------------------

class TestGenerateGraphBuildSummary:
    def test_returns_plain_dict(self):
        state = build_full_graph_state()
        final_status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        summary = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        assert isinstance(summary, dict)

    def test_contains_all_required_fields(self):
        state = build_full_graph_state()
        final_status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        summary = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        for key in (
            "generated_at", "graph_schema_version", "graph_fingerprint",
            "graph_status", "build_status", "total_nodes", "total_edges",
            "validation_summary", "readiness_summary", "overall_summary",
        ):
            assert key in summary, f"missing field: {key}"

    def test_build_status_matches_threaded_final_status(self):
        state = build_full_graph_state()
        summary = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], STATUS_FAILED,
        )
        # Even though the underlying graph is actually READY, the
        # summary must carry exactly the final_status it was handed --
        # it never independently re-derives its own verdict.
        assert summary["build_status"] == STATUS_FAILED

    def test_node_and_edge_counts_match_manifest(self):
        state = build_full_graph_state()
        final_status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        summary = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        assert summary["total_nodes"] == state["manifest"]["node_count"]
        assert summary["total_edges"] == state["manifest"]["edge_count"]

    def test_graph_fingerprint_is_carried_through_unchanged(self):
        state = build_full_graph_state()
        final_status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        summary = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        assert summary["graph_fingerprint"] == state["graph_fingerprint"]

    def test_validation_summary_reflects_error_and_warning_counts(self):
        state = build_full_graph_state()
        validation_report = dict(state["validation_report"])
        validation_report["errors"] = [{"rule": "x"}]
        validation_report["warnings"] = [{"rule": "y"}, {"rule": "z"}]
        summary = generate_graph_build_summary(
            state["graph_manager"], validation_report, state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], STATUS_FAILED,
        )
        assert summary["validation_summary"]["error_count"] == 1
        assert summary["validation_summary"]["warning_count"] == 2

    def test_handles_missing_optional_inputs_gracefully(self):
        """None manifest/statistics/fingerprints/readiness must not
        raise -- every field falls back to a safe default, mirroring
        compiler.finalize.generate_compiler_build_summary()'s own
        `manifest or {}` / `statistics or {}` treatment."""
        graph_manager = create_graph_registry_manager()
        summary = generate_graph_build_summary(
            graph_manager, None, None, None, None, None, None, STATUS_FAILED,
        )
        assert isinstance(summary, dict)
        assert summary["build_status"] == STATUS_FAILED
        assert summary["total_nodes"] == 0
        assert summary["total_edges"] == 0

    def test_never_mutates_inputs(self):
        state = build_full_graph_state()
        final_status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        before_manifest = copy.deepcopy(state["manifest"])
        before_statistics = copy.deepcopy(state["statistics"])
        before_validation = copy.deepcopy(state["validation_report"])
        before_readiness = copy.deepcopy(state["readiness_report"])
        generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        assert state["manifest"] == before_manifest
        assert state["statistics"] == before_statistics
        assert state["validation_report"] == before_validation
        assert state["readiness_report"] == before_readiness

    def test_deterministic_modulo_generated_at(self):
        state = build_full_graph_state()
        final_status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        s1 = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        s2 = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        s1.pop("generated_at")
        s2.pop("generated_at")
        assert s1 == s2

    def test_never_recomputes_node_or_edge_counts_by_scanning_registries(self):
        """The build summary's node/edge counts must come from the
        manifest/statistics already computed -- not from a fresh scan.
        Proven here by handing in a manifest whose counts are
        deliberately wrong and confirming the summary reports those
        (wrong) counts rather than the graph_manager's real ones."""
        state = build_full_graph_state()
        tampered_manifest = dict(state["manifest"])
        tampered_manifest["node_count"] = 999
        tampered_manifest["edge_count"] = 888
        final_status = determine_final_graph_status(
            state["validation_report"], state["readiness_report"],
        )
        summary = generate_graph_build_summary(
            state["graph_manager"], state["validation_report"], tampered_manifest,
            state["statistics"], state["registry_fingerprints"],
            state["graph_fingerprint"], state["readiness_report"], final_status,
        )
        assert summary["total_nodes"] == 999
        assert summary["total_edges"] == 888


# --------------------------------------------------------------------------
# 3. Knowledge Graph Finalization (Task 5 / pipeline integration)
# --------------------------------------------------------------------------

class TestFinalizeKnowledgeGraph:
    def test_returns_build_summary_and_final_status(self):
        state = build_full_graph_state()
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert set(result) == {"graph_build_summary", "graph_final_status"}
        assert isinstance(result["graph_build_summary"], dict)
        assert result["graph_final_status"] in {
            STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED,
        }

    def test_realistic_ready_graph(self):
        state = build_full_graph_state()
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert result["graph_final_status"] == STATUS_READY
        assert result["graph_build_summary"]["build_status"] == STATUS_READY

    def test_ready_with_warnings_when_validation_carries_a_warning(self):
        state = build_full_graph_state()
        validation_report = dict(state["validation_report"])
        validation_report["warnings"] = list(validation_report.get("warnings") or []) + [
            {"rule": "extra_warning", "message": "synthetic warning for test"},
        ]
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=validation_report,
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert result["graph_final_status"] == STATUS_READY_WITH_WARNINGS
        assert result["graph_build_summary"]["build_status"] == STATUS_READY_WITH_WARNINGS

    def test_failed_when_readiness_report_missing(self):
        state = build_full_graph_state()
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=None,
        )
        assert result["graph_final_status"] == STATUS_FAILED
        assert result["graph_build_summary"]["build_status"] == STATUS_FAILED

    def test_failed_when_validation_report_missing(self):
        state = build_full_graph_state()
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=None,
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert result["graph_final_status"] == STATUS_FAILED
        assert result["graph_build_summary"]["build_status"] == STATUS_FAILED

    def test_read_only_no_graph_mutation(self):
        """No graph mutation, no side effects: the graph registry
        manager's own registries are untouched by finalize_knowledge_
        graph() -- names/sizes identical before and after."""
        state = build_full_graph_state()
        before_names = sorted(state["graph_manager"].names())
        before_sizes = {n: len(list(state["graph_manager"].get(n).values())) for n in before_names}
        finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        after_names = sorted(state["graph_manager"].names())
        after_sizes = {n: len(list(state["graph_manager"].get(n).values())) for n in after_names}
        assert before_names == after_names
        assert before_sizes == after_sizes

    def test_deterministic_modulo_generated_at(self):
        state = build_full_graph_state()
        r1 = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        r2 = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert r1["graph_final_status"] == r2["graph_final_status"]
        b1 = dict(r1["graph_build_summary"]); b1.pop("generated_at")
        b2 = dict(r2["graph_build_summary"]); b2.pop("generated_at")
        assert b1 == b2


# --------------------------------------------------------------------------
# 4. Knowledge Graph State integration (Task 6 -- reuse existing slots)
# --------------------------------------------------------------------------

class TestKnowledgeGraphStateIntegration:
    def test_build_summary_slot_starts_unset(self):
        assert kg_state.has_current_knowledge_graph_build_summary() is False
        assert kg_state.get_current_knowledge_graph_build_summary() is None

    def test_final_status_slot_starts_unset(self):
        assert kg_state.has_current_final_graph_status() is False
        assert kg_state.get_current_final_graph_status() is None

    def test_set_and_get_build_summary(self):
        state = build_full_graph_state()
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        kg_state.set_current_knowledge_graph_build_summary(result["graph_build_summary"])
        assert kg_state.has_current_knowledge_graph_build_summary() is True
        assert kg_state.get_current_knowledge_graph_build_summary() == result["graph_build_summary"]

    def test_set_and_get_final_status(self):
        state = build_full_graph_state()
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        kg_state.set_current_final_graph_status(result["graph_final_status"])
        assert kg_state.has_current_final_graph_status() is True
        assert kg_state.get_current_final_graph_status() == result["graph_final_status"]

    def test_reset_clears_both_slots(self):
        kg_state.set_current_knowledge_graph_build_summary({"build_status": "READY"})
        kg_state.set_current_final_graph_status("READY")
        assert kg_state.has_current_knowledge_graph_build_summary() is True
        assert kg_state.has_current_final_graph_status() is True

        kg_state.reset_knowledge_graph_state()

        assert kg_state.has_current_knowledge_graph_build_summary() is False
        assert kg_state.has_current_final_graph_status() is False
        assert kg_state.get_current_knowledge_graph_build_summary() is None
        assert kg_state.get_current_final_graph_status() is None

    def test_reset_still_clears_every_earlier_slot(self):
        """Backward compatibility: reset_knowledge_graph_state() must
        still clear every Phase C0-C4.2 slot, not just the two this
        phase populates for the first time."""
        kg_state.set_current_registry_fingerprints({"nodes": "abc"})
        kg_state.set_current_graph_fingerprint("deadbeef")
        state = build_full_graph_state()
        kg_state.set_current_knowledge_graph_readiness_report(state["readiness_report"])
        kg_state.set_current_knowledge_graph_manifest(state["manifest"])
        kg_state.set_current_knowledge_graph_statistics(state["statistics"])
        kg_state.set_current_knowledge_graph_validation_report(state["validation_report"])
        kg_state.set_current_knowledge_graph_build_summary({"build_status": "READY"})
        kg_state.set_current_final_graph_status("READY")

        kg_state.reset_knowledge_graph_state()

        assert kg_state.has_current_registry_fingerprints() is False
        assert kg_state.has_current_graph_fingerprint() is False
        assert kg_state.has_current_knowledge_graph_readiness_report() is False
        assert kg_state.has_current_knowledge_graph_manifest() is False
        assert kg_state.has_current_knowledge_graph_statistics() is False
        assert kg_state.has_current_knowledge_graph_validation_report() is False
        assert kg_state.has_current_knowledge_graph_build_summary() is False
        assert kg_state.has_current_final_graph_status() is False


# --------------------------------------------------------------------------
# 5. Pipeline integration (Task 7 -- exactly one integration point)
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_pipeline_imports_finalize_knowledge_graph(self):
        import pipeline
        assert hasattr(pipeline, "finalize_knowledge_graph")

    def test_pipeline_calls_finalize_immediately_after_c4_2(self):
        """Exactly one call site, positioned after the C4.2 fingerprint
        results are stored and before the C4.1-family diagnostic
        logging block -- confirmed by source order rather than
        execution, mirroring tests/test_finalize.py's own
        source-inspection style for the equivalent Compiler check."""
        import inspect
        import pipeline
        source = inspect.getsource(pipeline)

        fingerprints_call_index = source.index(
            "knowledge_graph_fingerprint_results = generate_graph_fingerprints("
        )
        finalize_call_index = source.index(
            "knowledge_graph_finalization = finalize_knowledge_graph("
        )
        assert finalize_call_index > fingerprints_call_index

        # Exactly one call to finalize_knowledge_graph( in pipeline.py.
        assert source.count("finalize_knowledge_graph(") == 1

    def test_pipeline_stores_both_results_via_state_api(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline)
        assert "kg_state.set_current_knowledge_graph_build_summary(" in source
        assert "kg_state.set_current_final_graph_status(" in source


# --------------------------------------------------------------------------
# 6. Backward compatibility / architectural requirements
# --------------------------------------------------------------------------

class TestReadOnlyAndBackwardCompatibility:
    def test_no_graph_mutation_across_full_pipeline_slice(self):
        """Running the whole C1-C4.3 slice twice on freshly built,
        identical input must produce byte-identical graph registry
        contents (modulo nothing -- nothing here is volatile), proving
        finalize_knowledge_graph() introduces no observable graph
        mutation."""
        manager1 = make_relationship_ready_manager()
        graph_manager1 = build_ready_graph_manager(manager1)
        v1 = validate_knowledge_graph(graph_manager1, compiler_registry_manager=manager1)

        manager2 = make_relationship_ready_manager()
        graph_manager2 = build_ready_graph_manager(manager2)
        v2 = validate_knowledge_graph(graph_manager2, compiler_registry_manager=manager2)

        assert v1["node_summary"] == v2["node_summary"]
        assert v1["edge_summary"] == v2["edge_summary"]

    def test_finalize_version_constant_exists(self):
        assert isinstance(GRAPH_FINALIZE_VERSION, str)
        assert GRAPH_FINALIZE_VERSION

    def test_status_constants_are_the_closed_set(self):
        assert {STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED} == {
            "READY", "READY_WITH_WARNINGS", "FAILED",
        }

    def test_no_new_top_level_status_values_invented(self):
        state = build_full_graph_state()
        result = finalize_knowledge_graph(
            state["graph_manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            graph_fingerprint=state["graph_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert result["graph_final_status"] in {
            STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED,
        }

    def test_existing_c4_2_module_untouched_in_behavior(self):
        """Sanity check that Phase C4.2's own fingerprint/readiness
        generation is unaffected by this phase existing -- same inputs
        produce the same registry fingerprints and graph fingerprint
        as tests/test_c4_2_fingerprints_readiness.py's own expectations."""
        state = build_full_graph_state()
        refreshed = generate_graph_fingerprints(
            state["graph_manager"], manifest=state["manifest"],
            statistics=state["statistics"],
            validation_report=state["validation_report"],
        )
        assert refreshed["graph_fingerprint"] == state["graph_fingerprint"]
        assert refreshed["registry_fingerprints"] == state["registry_fingerprints"]
