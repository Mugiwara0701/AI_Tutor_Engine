"""
tests/test_d1_system_integrity.py — unit tests for Phase D1: System
Integrity Validation (validation/system_integrity.py), and its
pipeline.py / validation.state integration.

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment beyond the ad-hoc smoke checks performed
during development (mirrors tests/test_c4_3_finalization.py's own
disclaimer, one layer down).

This file does NOT re-test Compiler Validation (compiler/validation.py)
or Knowledge Graph Validation (knowledge_graph/validation.py) themselves
-- both are frozen, both already have their own test files (see
tests/test_validation.py and tests/test_c3_graph_validation.py). It
treats both passes' own output as a given input, exactly the way
validation/system_integrity.py itself does, and covers only what Phase
D1 actually adds: the six cross-artifact consistency checks, the
SystemIntegrityReport shape, validate_system_integrity() as a whole, and
its validation.state / pipeline.py integration.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.registry_manager import RegistryManager
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships
from compiler.validation import validate_compiler_state
from compiler.build import generate_compiler_manifest, generate_compiler_statistics
from compiler.fingerprints import generate_compiler_fingerprints
from compiler.finalize import finalize_compiler_build

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
from knowledge_graph.finalize import finalize_knowledge_graph

from validation.system_integrity import (
    SYSTEM_INTEGRITY_VERSION,
    SystemIntegrityReport,
    validate_system_integrity,
)
from validation import state as system_integrity_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- same canonical-enveloped item shape
# tests/test_c4_3_finalization.py's own make_item/make_relationship_
# ready_manager/build_ready_graph_manager already establish, duplicated
# here (not imported) so this file has no test-to-test import
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
    equation = make_item("e1", "urn:e:e1", "equation", concept_ids=["c1"])

    manager = create_registry_manager()
    populate_registries(
        manager,
        topics=[topic], concepts=[concept], definitions=[definition],
        equations=[equation],
    )
    resolve_references(manager, topics=[topic])
    resolve_relationships(manager, topics=[topic])
    return manager


def build_full_pipeline_state(*, namespace=NAMESPACE, mutate_kg_metadata=None):
    """One-shot: Phase B (Compiler IR) -> Phase C (Knowledge Graph),
    exactly the sequence pipeline.py runs immediately before its own
    Phase D1 integration point. Returns a dict of every artifact
    validate_system_integrity() consumes, keyed the same way that
    function's own parameter names read.

    `mutate_kg_metadata`, if given, is a callable applied to the
    KnowledgeGraphMetadata built for this run before it is folded into
    the Knowledge Graph Manifest -- lets a test inject exactly one
    cross-artifact inconsistency (e.g. a wrong source_chapter_identifier)
    without hand-building an entire alternate pipeline.
    """
    manager = make_relationship_ready_manager()
    compiler_validation_report = validate_compiler_state(
        manager, topics=[manager.get("topics").get_by_id("t1")],
    )
    compiler_manifest = generate_compiler_manifest(
        manager, compiler_validation_report, chapter_identifier=namespace,
    )
    compiler_statistics = generate_compiler_statistics(manager, compiler_validation_report)
    compiler_fp_results = generate_compiler_fingerprints(
        manager, manifest=compiler_manifest, statistics=compiler_statistics,
        validation_report=compiler_validation_report,
    )
    compiler_finalization = finalize_compiler_build(
        manager,
        validation_report=compiler_validation_report,
        manifest=compiler_manifest,
        statistics=compiler_statistics,
        registry_fingerprints=compiler_fp_results["registry_fingerprints"],
        compiler_fingerprint=compiler_fp_results["compiler_fingerprint"],
        readiness_report=compiler_fp_results["readiness_report"],
    )

    graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=namespace)
    graph_manager = build_knowledge_graph_edges(
        manager, graph_manager, graph_namespace=namespace,
    )
    kg_validation_report = validate_knowledge_graph(
        graph_manager, compiler_registry_manager=manager,
    )
    graph_metadata = KnowledgeGraphMetadata(
        graph_id=expected_graph_id(namespace),
        graph_urn=expected_graph_urn(namespace),
        source_chapter_identifier=namespace,
        source_compiler_version=compiler_manifest.get("compiler_version"),
    )
    if mutate_kg_metadata is not None:
        mutate_kg_metadata(graph_metadata)
    kg_manifest = generate_knowledge_graph_manifest(
        graph_manager, kg_validation_report, graph_metadata,
    )
    kg_statistics = generate_knowledge_graph_statistics(graph_manager, kg_validation_report)
    kg_fp_results = generate_graph_fingerprints(
        graph_manager, manifest=kg_manifest, statistics=kg_statistics,
        validation_report=kg_validation_report,
    )
    kg_finalization = finalize_knowledge_graph(
        graph_manager,
        validation_report=kg_validation_report,
        manifest=kg_manifest,
        statistics=kg_statistics,
        registry_fingerprints=kg_fp_results["registry_fingerprints"],
        graph_fingerprint=kg_fp_results["graph_fingerprint"],
        readiness_report=kg_fp_results["readiness_report"],
    )

    return {
        "compiler_registry_manager": manager,
        "compiler_validation_report": compiler_validation_report,
        "compiler_manifest": compiler_manifest,
        "compiler_statistics": compiler_statistics,
        "compiler_registry_fingerprints": compiler_fp_results["registry_fingerprints"],
        "compiler_fingerprint": compiler_fp_results["compiler_fingerprint"],
        "compiler_readiness_report": compiler_fp_results["readiness_report"],
        "compiler_build_summary": compiler_finalization["build_summary"],
        "graph_registry_manager": graph_manager,
        "knowledge_graph_validation_report": kg_validation_report,
        "knowledge_graph_manifest": kg_manifest,
        "knowledge_graph_statistics": kg_statistics,
        "knowledge_graph_registry_fingerprints": kg_fp_results["registry_fingerprints"],
        "knowledge_graph_fingerprint": kg_fp_results["graph_fingerprint"],
        "knowledge_graph_readiness_report": kg_fp_results["readiness_report"],
        "knowledge_graph_build_summary": kg_finalization["graph_build_summary"],
    }


def run_validate_system_integrity(state: dict) -> dict:
    """Calls validate_system_integrity() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names."""
    return validate_system_integrity(
        state["compiler_registry_manager"], state["graph_registry_manager"],
        compiler_validation_report=state["compiler_validation_report"],
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_fingerprint=state["compiler_fingerprint"],
        compiler_readiness_report=state["compiler_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_validation_report=state["knowledge_graph_validation_report"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
    )


@pytest.fixture(autouse=True)
def _reset_system_integrity_state():
    """Every test starts and ends with a clean validation.state module --
    mirrors tests/test_c4_3_finalization.py's own _reset_kg_state
    fixture, one layer down."""
    system_integrity_state.reset_system_integrity_state()
    yield
    system_integrity_state.reset_system_integrity_state()


# --------------------------------------------------------------------------
# 1. Valid compiler output -> a clean, passing report
# --------------------------------------------------------------------------

class TestValidPipelineOutput:
    def test_overall_status_is_pass(self):
        state = build_full_pipeline_state()
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "pass"
        assert report["errors"] == []
        assert report["checks_failed"] == []

    def test_every_declared_check_category_is_populated(self):
        state = build_full_pipeline_state()
        report = run_validate_system_integrity(state)
        for key in (
            "registry_consistency", "graph_consistency",
            "fingerprint_consistency", "manifest_consistency",
            "statistics_consistency", "build_summary_consistency",
        ):
            assert report[key], f"{key} summary unexpectedly empty"

    def test_report_is_deterministic_modulo_generated_at(self):
        state = build_full_pipeline_state()
        report_1 = run_validate_system_integrity(state)
        report_2 = run_validate_system_integrity(state)
        report_1.pop("generated_at")
        report_2.pop("generated_at")
        assert report_1 == report_2


# --------------------------------------------------------------------------
# 2. Missing compiler object referenced by the graph
# --------------------------------------------------------------------------

class TestMissingCompilerObject:
    def test_dangling_compiler_reference_fails_registry_consistency(self):
        state = build_full_pipeline_state()
        node_registry = state["graph_registry_manager"].get("nodes")
        some_id = node_registry.ids()[0]
        node = node_registry.get_by_id(some_id)
        node.compiler_object_id = "does-not-exist"
        # Re-run Knowledge Graph Validation over the tampered node so
        # its own node_summary reflects the dangling reference -- D1
        # reads that verdict, it does not re-walk the node registry
        # itself to discover it (see module docstring).
        state["knowledge_graph_validation_report"] = validate_knowledge_graph(
            state["graph_registry_manager"],
            compiler_registry_manager=state["compiler_registry_manager"],
        )
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "no_invalid_compiler_object_references" in report["checks_failed"]
        assert any(e["rule"] == "invalid_compiler_object_references" for e in report["errors"])

    def test_cross_check_not_performed_is_omitted_not_reported_as_passed(self):
        """Finding 3: when Knowledge Graph Validation ran WITHOUT a
        Compiler RegistryManager, node -> compiler-object reference
        resolution was never actually verified. Previously
        no_invalid_compiler_object_references still landed in
        checks_passed (because invalid_compiler_object_references
        defaults to 0 when unchecked); now it must be omitted from both
        checks_passed and checks_failed, with only the existing
        compiler_reference_cross_check_not_performed warning explaining
        why."""
        state = build_full_pipeline_state()
        # Re-run Knowledge Graph Validation with no compiler registry
        # manager supplied, so its own node_summary never resolves
        # compiler_object_id references at all.
        state["knowledge_graph_validation_report"] = validate_knowledge_graph(
            state["graph_registry_manager"],
        )
        report = run_validate_system_integrity(state)
        assert "no_invalid_compiler_object_references" not in report["checks_passed"]
        assert "no_invalid_compiler_object_references" not in report["checks_failed"]
        assert report["registry_consistency"]["compiler_reference_cross_check_performed"] is False
        assert any(
            w["rule"] == "compiler_reference_cross_check_not_performed"
            for w in report["warnings"]
        )


# --------------------------------------------------------------------------
# 3. Missing graph node (registry/graph count mismatch)
# --------------------------------------------------------------------------

class TestMissingGraphNode:
    def test_node_count_mismatch_fails_registry_consistency(self):
        state = build_full_pipeline_state()
        node_registry = state["graph_registry_manager"].get("nodes")
        some_id = node_registry.ids()[0]
        node_registry.remove(some_id)
        state["knowledge_graph_validation_report"] = validate_knowledge_graph(
            state["graph_registry_manager"],
            compiler_registry_manager=state["compiler_registry_manager"],
        )
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "registry_counts_match_graph_counts" in report["checks_failed"]


# --------------------------------------------------------------------------
# 3b. Compiler-version provenance mismatch between the two manifests
#     (Finding 2: implement the compiler_version <-> source_compiler
#     cross-check the docstring already claimed to make, reusing the
#     existing knowledge_graph_manifest["node_registry_versions"]
#     ["source_compiler"] field -- no new metadata invented)
# --------------------------------------------------------------------------

class TestCompilerVersionProvenanceMismatch:
    def test_mismatched_source_compiler_version_fails_manifest_consistency(self):
        state = build_full_pipeline_state(
            mutate_kg_metadata=lambda meta: setattr(
                meta, "source_compiler_version", "not-the-real-compiler-version",
            ),
        )
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "manifest_compiler_versions_consistent" in report["checks_failed"]
        assert report["manifest_consistency"]["compiler_version_matches"] is False
        assert any(e["rule"] == "compiler_version_mismatch" for e in report["errors"])

    def test_matching_source_compiler_version_passes(self):
        """build_full_pipeline_state()'s own default already sets
        source_compiler_version=compiler_manifest["compiler_version"], so
        an untampered run must not trip this check."""
        state = build_full_pipeline_state()
        report = run_validate_system_integrity(state)
        assert report["manifest_consistency"]["compiler_version_matches"] is True
        assert "manifest_compiler_versions_consistent" in report["checks_passed"]


# --------------------------------------------------------------------------
# 4. Orphan graph edge
# --------------------------------------------------------------------------

class TestOrphanGraphEdge:
    def test_dangling_edge_fails_graph_consistency(self):
        state = build_full_pipeline_state()
        edge_registry = state["graph_registry_manager"].get("edges")
        some_edge_id = edge_registry.ids()[0]
        edge = edge_registry.get_by_id(some_edge_id)
        edge.target_node_id = "no-such-node"
        state["knowledge_graph_validation_report"] = validate_knowledge_graph(
            state["graph_registry_manager"],
            compiler_registry_manager=state["compiler_registry_manager"],
        )
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "no_dangling_graph_edges" in report["checks_failed"]
        assert any(e["rule"] == "dangling_graph_edges" for e in report["errors"])

    def test_node_with_no_incident_edges_is_a_warning_not_an_error(self):
        state = build_full_pipeline_state()
        node_registry = state["graph_registry_manager"].get("nodes")
        from knowledge_graph.node import GraphNodeBase
        isolated = GraphNodeBase(
            node_id="isolated-node", node_urn="urn:kg:isolated-node",
            node_type="concept", graph_id=node_registry.get_by_id(node_registry.ids()[0]).graph_id,
            graph_urn=node_registry.get_by_id(node_registry.ids()[0]).graph_urn,
            compiler_object_id="c1", compiler_object_urn="urn:c:c1",
            compiler_object_type="concept", compiler_registry="concepts",
        )
        node_registry.insert(isolated)
        report = run_validate_system_integrity(state)
        assert report["graph_consistency"]["orphan_node_count"] >= 1
        assert not any(e["rule"] == "orphan_graph_nodes" for e in report["errors"])
        assert any(w["rule"] == "orphan_graph_nodes" for w in report["warnings"])


# --------------------------------------------------------------------------
# 5. Inconsistent counts (manifest vs statistics)
# --------------------------------------------------------------------------

class TestInconsistentCounts:
    def test_graph_readiness_node_count_verdict_is_consumed_not_recomputed(self):
        """Post-Finding-1: D1 no longer compares knowledge_graph_manifest
        against knowledge_graph_statistics itself -- it reads Knowledge
        Graph Readiness's own `node_count_matches_statistics` check
        verdict (knowledge_graph.fingerprints.
        generate_graph_readiness_report()'s checks 7/8) via
        _find_readiness_check(). So the fault is injected into the
        readiness report's own checks list, not the manifest -- tampering
        the manifest alone (the old pre-Finding-1 way this test used to
        inject the fault) would no longer be caught, since D1 never looks
        at the manifest/statistics pair directly for this check anymore."""
        state = build_full_pipeline_state()
        tampered_readiness = copy.deepcopy(state["knowledge_graph_readiness_report"])
        for check in tampered_readiness["checks"]:
            if check["name"] == "node_count_matches_statistics":
                check["passed"] = False
                check["detail"] = "manifest.node_count=6 != statistics.total_nodes=5"
        state["knowledge_graph_readiness_report"] = tampered_readiness
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "graph_manifest_counts_match_statistics" in report["checks_failed"]
        assert any(
            e["rule"] == "graph_manifest_statistics_node_count_mismatch"
            for e in report["errors"]
        )

    def test_graph_readiness_missing_count_checks_is_a_warning_not_a_failure(self):
        """Post-Finding-3's own principle applied to Finding 1's fix: if
        Knowledge Graph Readiness didn't carry a
        node_count_matches_statistics/edge_count_matches_statistics
        verdict to consume, D1 must not silently pass (nothing was
        verified) and must not recompute the comparison itself (that
        would resurrect the exact duplication Finding 1 removed) --
        it reports this as a warning and omits the check from both
        checks_passed and checks_failed."""
        state = build_full_pipeline_state()
        tampered_readiness = copy.deepcopy(state["knowledge_graph_readiness_report"])
        tampered_readiness["checks"] = [
            c for c in tampered_readiness["checks"]
            if c["name"] not in ("node_count_matches_statistics", "edge_count_matches_statistics")
        ]
        state["knowledge_graph_readiness_report"] = tampered_readiness
        report = run_validate_system_integrity(state)
        assert "graph_manifest_counts_match_statistics" not in report["checks_passed"]
        assert "graph_manifest_counts_match_statistics" not in report["checks_failed"]
        assert any(w["rule"] == "graph_node_count_consistency_not_verified" for w in report["warnings"])
        assert any(w["rule"] == "graph_edge_count_consistency_not_verified" for w in report["warnings"])

    def test_compiler_manifest_object_count_disagrees_with_statistics(self):
        state = build_full_pipeline_state()
        tampered_manifest = copy.deepcopy(state["compiler_manifest"])
        tampered_manifest["object_count"] = -1
        state["compiler_manifest"] = tampered_manifest
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert any(
            e["rule"] == "compiler_manifest_statistics_object_count_mismatch"
            for e in report["errors"]
        )


# --------------------------------------------------------------------------
# 6. Inconsistent fingerprints
# --------------------------------------------------------------------------

class TestInconsistentFingerprints:
    def test_build_summary_fingerprint_disagrees_with_generated_fingerprint(self):
        state = build_full_pipeline_state()
        tampered_summary = copy.deepcopy(state["knowledge_graph_build_summary"])
        tampered_summary["graph_fingerprint"] = "stale-fingerprint"
        state["knowledge_graph_build_summary"] = tampered_summary
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "build_summary_fingerprints_consistent" in report["checks_failed"]
        assert any(
            e["rule"] == "graph_build_summary_fingerprint_mismatch"
            for e in report["errors"]
        )


# --------------------------------------------------------------------------
# 7. Missing manifests / statistics / readiness reports / build summaries
# --------------------------------------------------------------------------

class TestMissingArtifacts:
    def test_missing_manifests_are_reported(self):
        state = build_full_pipeline_state()
        state["compiler_manifest"] = None
        state["knowledge_graph_manifest"] = None
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "manifests_exist" in report["checks_failed"]
        assert any(e["rule"] == "missing_compiler_manifest" for e in report["errors"])
        assert any(e["rule"] == "missing_graph_manifest" for e in report["errors"])

    def test_missing_statistics_are_reported(self):
        state = build_full_pipeline_state()
        state["compiler_statistics"] = None
        state["knowledge_graph_statistics"] = None
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "statistics_exist" in report["checks_failed"]

    def test_missing_readiness_reports_are_reported(self):
        state = build_full_pipeline_state()
        state["compiler_readiness_report"] = None
        state["knowledge_graph_readiness_report"] = None
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "readiness_reports_exist" in report["checks_failed"]
        assert any(e["rule"] == "missing_compiler_readiness_report" for e in report["errors"])
        assert any(e["rule"] == "missing_graph_readiness_report" for e in report["errors"])

    def test_missing_build_summaries_are_reported(self):
        state = build_full_pipeline_state()
        state["compiler_build_summary"] = None
        state["knowledge_graph_build_summary"] = None
        report = run_validate_system_integrity(state)
        assert report["overall_status"] == "fail"
        assert "build_summaries_exist" in report["checks_failed"]

    def test_all_optional_artifacts_missing_still_returns_a_report(self):
        """Calling with only the two registry managers -- every keyword
        artifact defaults to None -- still returns a well-formed,
        deterministic (modulo generated_at) failing report rather than
        raising."""
        manager = make_relationship_ready_manager()
        graph_manager = create_graph_registry_manager()
        report = validate_system_integrity(manager, graph_manager)
        assert report["overall_status"] == "fail"
        assert report["checks_failed"]
        assert isinstance(report["errors"], list) and report["errors"]


# --------------------------------------------------------------------------
# 8. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_produce_the_same_report_twice(self):
        state = build_full_pipeline_state()
        first = run_validate_system_integrity(state)
        second = run_validate_system_integrity(state)
        first.pop("generated_at")
        second.pop("generated_at")
        assert first == second

    def test_report_carries_its_own_version_marker(self):
        state = build_full_pipeline_state()
        report = run_validate_system_integrity(state)
        assert report["integrity_version"] == SYSTEM_INTEGRITY_VERSION


# --------------------------------------------------------------------------
# 9. Read-only behavior
# --------------------------------------------------------------------------

class TestReadOnlyBehavior:
    def test_compiler_registry_manager_is_unmutated(self):
        state = build_full_pipeline_state()
        before = state["compiler_registry_manager"].serialize()
        run_validate_system_integrity(state)
        after = state["compiler_registry_manager"].serialize()
        assert before == after

    def test_graph_registry_manager_is_unmutated(self):
        state = build_full_pipeline_state()
        before = state["graph_registry_manager"].serialize()
        run_validate_system_integrity(state)
        after = state["graph_registry_manager"].serialize()
        assert before == after

    def test_input_dicts_are_unmutated(self):
        state = build_full_pipeline_state()
        snapshots = {
            key: copy.deepcopy(value)
            for key, value in state.items()
            if key.endswith(("_manifest", "_statistics", "_report", "_summary"))
        }
        run_validate_system_integrity(state)
        for key, snapshot in snapshots.items():
            assert state[key] == snapshot, f"{key} was mutated"


# --------------------------------------------------------------------------
# 10. Pipeline / validation.state integration
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_report_round_trips_through_validation_state(self):
        state = build_full_pipeline_state()
        report = run_validate_system_integrity(state)
        assert system_integrity_state.has_current_system_integrity_report() is False
        system_integrity_state.set_current_system_integrity_report(report)
        assert system_integrity_state.has_current_system_integrity_report() is True
        assert system_integrity_state.get_current_system_integrity_report() == report

    def test_reset_clears_the_current_report(self):
        state = build_full_pipeline_state()
        report = run_validate_system_integrity(state)
        system_integrity_state.set_current_system_integrity_report(report)
        system_integrity_state.reset_system_integrity_state()
        assert system_integrity_state.has_current_system_integrity_report() is False
        assert system_integrity_state.get_current_system_integrity_report() is None

    def test_get_current_report_is_none_before_any_set(self):
        assert system_integrity_state.get_current_system_integrity_report() is None
        assert system_integrity_state.has_current_system_integrity_report() is False


# --------------------------------------------------------------------------
# 11. Backward compatibility -- SystemIntegrityReport is purely additive
#     plumbing; it must never require any change to a frozen Phase A-C
#     schema/registry/id/urn/manifest/statistics/fingerprint/readiness-
#     report/build-summary shape to run.
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_report_to_dict_contains_every_suggested_field(self):
        report = SystemIntegrityReport()
        d = report.to_dict()
        for field_name in (
            "generated_at", "overall_status", "errors", "warnings",
            "checks_passed", "checks_failed", "summary",
            "registry_consistency", "graph_consistency",
            "fingerprint_consistency", "manifest_consistency",
            "statistics_consistency", "build_summary_consistency",
        ):
            assert field_name in d

    def test_validate_system_integrity_does_not_require_optional_artifacts(self):
        """Confirms Task 6's own "reuse the existing state pattern... or
        implement only what is necessary" allowance: every artifact
        beyond the two registry managers is optional, so this function
        never forces a caller (or an earlier Phase A-C module) to change
        shape just to supply a value D1 could otherwise do without."""
        import inspect
        signature = inspect.signature(validate_system_integrity)
        required = [
            name for name, param in signature.parameters.items()
            if param.default is inspect._empty
            and param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ]
        assert required == ["compiler_registry_manager", "graph_registry_manager"]