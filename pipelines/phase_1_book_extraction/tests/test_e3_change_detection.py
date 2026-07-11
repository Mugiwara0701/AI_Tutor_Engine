"""
tests/test_e3_change_detection.py — unit tests for Phase E3: Change
Detection (change_detection/), and its pipeline.py /
change_detection.state integration.

This file does NOT re-test Compiler IR / Knowledge Graph / Validation /
Build Metadata / Build Dependency Graph construction directly -- it
treats all of those as frozen, already-tested dependencies (see
tests/test_e1_build_metadata.py and tests/test_e2_dependency_graph.py,
which this file's own `build_full_pipeline_state()` helper extends by
one more phase, following those files' own "duplicated here, not
imported" convention -- this repo has no tests/__init__.py, so tests/
is not a package).
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

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
from knowledge_graph.identity import (
    graph_id as expected_kg_graph_id,
    graph_urn as expected_kg_graph_urn,
)
from knowledge_graph.schema import KnowledgeGraphMetadata
from knowledge_graph.fingerprints import generate_graph_fingerprints
from knowledge_graph.finalize import finalize_knowledge_graph

from validation.system_integrity import validate_system_integrity
from validation.determinism import validate_determinism
from validation.release import finalize_release

from build_metadata.build import finalize_build_metadata

from dependency_graph.build import generate_dependency_graph

from change_detection.compare import compare_snapshots
from change_detection.engine import CHANGE_DETECTION_VERSION, detect_changes
from change_detection.exceptions import InvalidPreviousBuildError
from change_detection.report import ChangeDetectionReport
from change_detection.snapshot import (
    CONFIGURATION_ARTIFACT_KEY,
    DEPENDENCY_GRAPH_ARTIFACT_KEY,
    build_snapshot,
    _build_metadata_fingerprint_source,
)
from change_detection.traversal import compute_affected_artifacts
from change_detection import state as change_detection_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- full Phase B->E2 pipeline fixture (same shape
# tests/test_e2_dependency_graph.py's own build_full_pipeline_state()
# already establishes, extended one phase and duplicated here, not
# imported).
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
    manager = create_registry_manager()
    populate_registries(manager, topics=[topic], concepts=[concept], definitions=[definition])
    resolve_references(manager)
    resolve_relationships(manager)
    return manager


def build_full_pipeline_state(*, namespace=NAMESPACE):
    """One-shot: Phase B -> Phase C -> Phase D1 -> Phase D2 -> Phase D3
    -> Phase E1 -> Phase E2, exactly the sequence pipeline.py runs
    immediately before its own Phase E3 integration point. Returns a
    dict of every artifact detect_changes() consumes."""
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
    graph_metadata_obj = KnowledgeGraphMetadata(
        graph_id=expected_kg_graph_id(namespace),
        graph_urn=expected_kg_graph_urn(namespace),
        source_chapter_identifier=namespace,
        source_compiler_version=compiler_manifest.get("compiler_version"),
    )
    kg_manifest = generate_knowledge_graph_manifest(
        graph_manager, kg_validation_report, graph_metadata_obj,
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

    state = {
        "compiler_registry_manager": manager,
        "compiler_manifest": compiler_manifest,
        "compiler_statistics": compiler_statistics,
        "compiler_registry_fingerprints": compiler_fp_results["registry_fingerprints"],
        "compiler_fingerprint": compiler_fp_results["compiler_fingerprint"],
        "compiler_readiness_report": compiler_fp_results["readiness_report"],
        "compiler_build_summary": compiler_finalization["build_summary"],
        "final_compiler_status": compiler_finalization["final_status"],
        "graph_registry_manager": graph_manager,
        "knowledge_graph_manifest": kg_manifest,
        "knowledge_graph_statistics": kg_statistics,
        "knowledge_graph_registry_fingerprints": kg_fp_results["registry_fingerprints"],
        "knowledge_graph_fingerprint": kg_fp_results["graph_fingerprint"],
        "knowledge_graph_readiness_report": kg_fp_results["readiness_report"],
        "knowledge_graph_build_summary": kg_finalization["graph_build_summary"],
        "final_graph_status": kg_finalization["graph_final_status"],
    }
    state["system_integrity_report"] = validate_system_integrity(
        state["compiler_registry_manager"], state["graph_registry_manager"],
        compiler_validation_report=compiler_validation_report,
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_fingerprint=state["compiler_fingerprint"],
        compiler_readiness_report=state["compiler_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_validation_report=kg_validation_report,
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
    )
    state["determinism_report"] = validate_determinism(
        state["compiler_registry_manager"], state["graph_registry_manager"],
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_fingerprint=state["compiler_fingerprint"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        system_integrity_report=state["system_integrity_report"],
    )
    release_finalization = finalize_release(
        compiler_validation_report=compiler_validation_report,
        knowledge_graph_validation_report=kg_validation_report,
        compiler_readiness_report=state["compiler_readiness_report"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        system_integrity_report=state["system_integrity_report"],
        determinism_report=state["determinism_report"],
        compiler_manifest=state["compiler_manifest"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        compiler_fingerprint=state["compiler_fingerprint"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        compiler_statistics=state["compiler_statistics"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
    )
    state["release_readiness_report"] = release_finalization["release_readiness_report"]
    state["release_status"] = release_finalization["release_status"]

    build_metadata_result = finalize_build_metadata(
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_fingerprint=state["compiler_fingerprint"],
        compiler_readiness_report=state["compiler_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        final_compiler_status=state["final_compiler_status"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        final_graph_status=state["final_graph_status"],
        release_status=state["release_status"],
        pdf_path=None,
        compilation_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        compilation_end=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        use_vlm=True,
        page_batch_size=6,
        force=False,
    )
    state["build_metadata"] = build_metadata_result["build_metadata"]

    dependency_graph_result = generate_dependency_graph(
        namespace=namespace,
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_readiness_report=state["compiler_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        release_readiness_report=state["release_readiness_report"],
        build_metadata=state["build_metadata"],
    )
    state["dependency_graph"] = dependency_graph_result["dependency_graph"]
    return state


def run_detect_changes(state: dict, *, namespace=NAMESPACE, **overrides) -> dict:
    """Calls detect_changes() with every artifact build_full_pipeline_
    state() produced, keyword-mapped onto that function's own parameter
    names -- exactly pipeline.py's own Phase E3 integration-point call
    shape."""
    kwargs = dict(
        namespace=namespace,
        dependency_graph=state["dependency_graph"],
        build_metadata=state["build_metadata"],
        release_readiness_report=state["release_readiness_report"],
        previous_build=None,
    )
    kwargs.update(overrides)
    return detect_changes(**kwargs)


@pytest.fixture(autouse=True)
def _reset_change_detection_state():
    """Every test starts and ends with a clean change_detection.state
    module -- mirrors tests/test_e2_dependency_graph.py's own
    _reset_dependency_graph_state fixture, one phase over."""
    change_detection_state.reset_change_detection_state()
    yield
    change_detection_state.reset_change_detection_state()


# --------------------------------------------------------------------------
# 1. Snapshot / Fingerprint Comparison (build side)
# --------------------------------------------------------------------------

class TestBuildSnapshot:
    def test_snapshot_has_one_entry_per_dependency_graph_node(self):
        state = build_full_pipeline_state()
        snapshot = build_snapshot(
            namespace=NAMESPACE,
            dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
        )
        node_ids = {n["node_id"] for n in state["dependency_graph"]["nodes"]}
        fingerprints = snapshot["artifact_fingerprints"]
        for node_id in node_ids:
            assert node_id in fingerprints

    def test_snapshot_includes_configuration_and_dependency_graph_keys(self):
        state = build_full_pipeline_state()
        snapshot = build_snapshot(
            namespace=NAMESPACE,
            dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
        )
        fingerprints = snapshot["artifact_fingerprints"]
        assert CONFIGURATION_ARTIFACT_KEY in fingerprints
        assert DEPENDENCY_GRAPH_ARTIFACT_KEY in fingerprints

    def test_registry_fingerprints_are_reused_verbatim_not_rederived(self):
        state = build_full_pipeline_state()
        snapshot = build_snapshot(
            namespace=NAMESPACE,
            dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
        )
        fingerprints = snapshot["artifact_fingerprints"]
        compiler_fp_node = next(
            n for n in state["dependency_graph"]["nodes"]
            if n["node_type"] == "compiler_fingerprints"
        )
        assert fingerprints[compiler_fp_node["node_id"]] == state["compiler_fingerprint"]

    def test_configuration_fingerprint_reused_verbatim(self):
        state = build_full_pipeline_state()
        snapshot = build_snapshot(
            namespace=NAMESPACE,
            dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
        )
        expected = state["build_metadata"]["configuration_metadata"]["configuration_fingerprint"]
        assert snapshot["artifact_fingerprints"][CONFIGURATION_ARTIFACT_KEY] == expected

    def test_missing_artifacts_are_simply_absent_not_fabricated(self):
        snapshot = build_snapshot(
            namespace=NAMESPACE, dependency_graph=None, build_metadata=None,
            release_readiness_report=None,
        )
        assert snapshot["artifact_fingerprints"] == {}

    def test_snapshot_is_deterministic_across_calls(self):
        state = build_full_pipeline_state()
        s1 = build_snapshot(
            namespace=NAMESPACE, dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
        )
        s2 = build_snapshot(
            namespace=NAMESPACE, dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
        )
        assert s1["artifact_fingerprints"] == s2["artifact_fingerprints"]

    def test_snapshot_never_mutates_its_inputs(self):
        state = build_full_pipeline_state()
        before_dg = copy.deepcopy(state["dependency_graph"])
        before_bm = copy.deepcopy(state["build_metadata"])
        build_snapshot(
            namespace=NAMESPACE, dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
        )
        assert state["dependency_graph"] == before_dg
        assert state["build_metadata"] == before_bm

    def _build_metadata_node_id(self, state):
        node = next(
            n for n in state["dependency_graph"]["nodes"]
            if n["node_type"] == "build_metadata"
        )
        return node["node_id"]

    def test_build_metadata_fingerprint_ignores_compilation_start_and_end(self):
        """Regression test for the audit's CRITICAL finding: the
        "build_metadata" artifact's fingerprint must be stable across
        two builds whose actual content is identical but whose wall-
        clock compilation_start/compilation_end/processing_time_seconds
        differ, exactly as build_metadata/compilation_metadata.py's own
        module docstring already requires ("NEVER PARTICIPATES IN ANY
        FINGERPRINT")."""
        state_a = build_full_pipeline_state()
        state_b = copy.deepcopy(state_a)
        state_b["build_metadata"] = copy.deepcopy(state_a["build_metadata"])
        state_b["build_metadata"]["compilation_metadata"]["compilation_start"] = (
            "2099-12-31T23:00:00+00:00"
        )
        state_b["build_metadata"]["compilation_metadata"]["compilation_end"] = (
            "2099-12-31T23:59:59+00:00"
        )
        state_b["build_metadata"]["compilation_metadata"]["processing_time_seconds"] = 3599.0

        snapshot_a = build_snapshot(
            namespace=NAMESPACE, dependency_graph=state_a["dependency_graph"],
            build_metadata=state_a["build_metadata"],
            release_readiness_report=state_a["release_readiness_report"],
        )
        snapshot_b = build_snapshot(
            namespace=NAMESPACE, dependency_graph=state_a["dependency_graph"],
            build_metadata=state_b["build_metadata"],
            release_readiness_report=state_a["release_readiness_report"],
        )

        node_id = self._build_metadata_node_id(state_a)
        assert node_id in snapshot_a["artifact_fingerprints"]
        assert (
            snapshot_a["artifact_fingerprints"][node_id]
            == snapshot_b["artifact_fingerprints"][node_id]
        )

    def test_build_metadata_fingerprint_still_detects_real_content_changes(self):
        """The fix for the above must not make the "build_metadata" node
        blind to genuine changes -- only the three named operational
        fields are excluded, everything else (e.g. release_status inside
        version_metadata's own phase_completion) still participates."""
        state_a = build_full_pipeline_state()
        state_b = copy.deepcopy(state_a)
        state_b["build_metadata"] = copy.deepcopy(state_a["build_metadata"])
        state_b["build_metadata"]["version_metadata"]["phase_completion"]["release"] = (
            "FAILED_FOR_TEST"
        )

        snapshot_a = build_snapshot(
            namespace=NAMESPACE, dependency_graph=state_a["dependency_graph"],
            build_metadata=state_a["build_metadata"],
            release_readiness_report=state_a["release_readiness_report"],
        )
        snapshot_b = build_snapshot(
            namespace=NAMESPACE, dependency_graph=state_a["dependency_graph"],
            build_metadata=state_b["build_metadata"],
            release_readiness_report=state_a["release_readiness_report"],
        )

        node_id = self._build_metadata_node_id(state_a)
        assert (
            snapshot_a["artifact_fingerprints"][node_id]
            != snapshot_b["artifact_fingerprints"][node_id]
        )

    def test_build_metadata_fingerprint_helper_never_mutates_input(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["build_metadata"])
        sanitized = _build_metadata_fingerprint_source(state["build_metadata"])
        assert state["build_metadata"] == before
        # Sanitized copy has the volatile keys removed, original untouched.
        assert "compilation_start" not in sanitized["compilation_metadata"]
        assert "compilation_start" in state["build_metadata"]["compilation_metadata"]

    def test_build_metadata_fingerprint_source_handles_none_and_missing_block(self):
        assert _build_metadata_fingerprint_source(None) is None
        # No compilation_metadata key at all -> returned unchanged.
        no_compilation_block = {"compiler_metadata": {}}
        assert _build_metadata_fingerprint_source(no_compilation_block) is no_compilation_block


# --------------------------------------------------------------------------
# 2. Artifact Comparison / Fingerprint Comparison / Changed Artifact
#    Detection
# --------------------------------------------------------------------------

class TestCompareSnapshots:
    def test_no_previous_build_means_everything_added(self):
        current = {"a": "fp1", "b": "fp2"}
        result = compare_snapshots(None, current)
        assert sorted(result["added"]) == ["a", "b"]
        assert result["removed"] == []
        assert result["modified"] == []
        assert result["unchanged_candidates"] == []

    def test_added_artifact(self):
        previous = {"a": "fp1"}
        current = {"a": "fp1", "b": "fp2"}
        result = compare_snapshots(previous, current)
        assert result["added"] == ["b"]

    def test_removed_artifact(self):
        previous = {"a": "fp1", "b": "fp2"}
        current = {"a": "fp1"}
        result = compare_snapshots(previous, current)
        assert result["removed"] == ["b"]

    def test_modified_artifact(self):
        previous = {"a": "fp1"}
        current = {"a": "fp1-changed"}
        result = compare_snapshots(previous, current)
        assert result["modified"] == ["a"]
        assert result["added"] == []
        assert result["removed"] == []

    def test_unchanged_artifact(self):
        previous = {"a": "fp1"}
        current = {"a": "fp1"}
        result = compare_snapshots(previous, current)
        assert result["unchanged_candidates"] == ["a"]
        assert result["modified"] == []

    def test_empty_previous_dict_behaves_like_none(self):
        current = {"a": "fp1"}
        assert compare_snapshots({}, current) == compare_snapshots(None, current)

    def test_never_mutates_inputs(self):
        previous = {"a": "fp1"}
        current = {"a": "fp1", "b": "fp2"}
        before_prev, before_curr = dict(previous), dict(current)
        compare_snapshots(previous, current)
        assert previous == before_prev
        assert current == before_curr

    def test_results_are_sorted(self):
        current = {"z": "1", "a": "2", "m": "3"}
        result = compare_snapshots(None, current)
        assert result["added"] == sorted(result["added"])


# --------------------------------------------------------------------------
# 3. Dependency Graph Traversal
# --------------------------------------------------------------------------

class TestDependencyGraphTraversal:
    def _linear_graph(self):
        # a <- b <- c  (b depends_on a, c depends_on b)
        return {
            "nodes": [{"node_id": "a"}, {"node_id": "b"}, {"node_id": "c"}],
            "edges": [
                {"source_node_id": "b", "target_node_id": "a"},
                {"source_node_id": "c", "target_node_id": "b"},
            ],
        }

    def test_direct_and_transitive_dependents_are_affected(self):
        graph = self._linear_graph()
        affected = compute_affected_artifacts(graph, ["a"])
        assert affected == ["b", "c"]

    def test_changed_nodes_are_excluded_from_affected(self):
        graph = self._linear_graph()
        affected = compute_affected_artifacts(graph, ["a", "b"])
        assert "a" not in affected
        assert "b" not in affected
        assert affected == ["c"]

    def test_leaf_change_has_no_affected_nodes(self):
        graph = self._linear_graph()
        assert compute_affected_artifacts(graph, ["c"]) == []

    def test_empty_changed_set_yields_no_affected_nodes(self):
        graph = self._linear_graph()
        assert compute_affected_artifacts(graph, []) == []

    def test_none_dependency_graph_yields_no_affected_nodes(self):
        assert compute_affected_artifacts(None, ["a"]) == []

    def test_never_mutates_dependency_graph(self):
        graph = self._linear_graph()
        before = copy.deepcopy(graph)
        compute_affected_artifacts(graph, ["a"])
        assert graph == before

    def test_result_is_sorted_and_deterministic(self):
        graph = self._linear_graph()
        r1 = compute_affected_artifacts(graph, ["a"])
        r2 = compute_affected_artifacts(graph, ["a"])
        assert r1 == r2 == sorted(r1)


# --------------------------------------------------------------------------
# 4. Change Detection Engine / Report (full pipeline fixture)
# --------------------------------------------------------------------------

class TestDetectChangesEngine:
    def test_first_build_reports_everything_as_added(self):
        state = build_full_pipeline_state()
        result = run_detect_changes(state)
        report = result["change_detection_report"]
        assert report["has_previous_build"] is False
        assert report["removed_artifacts"] == []
        assert report["modified_artifacts"] == []
        assert report["affected_artifacts"] == []
        assert report["unchanged_artifacts"] == []
        assert len(report["added_artifacts"]) > 0
        assert report["summary"]["added_count"] == len(report["added_artifacts"])
        assert report["summary"]["has_changes"] is True

    def test_identical_second_build_reports_everything_unchanged(self):
        state = build_full_pipeline_state()
        first = run_detect_changes(state)
        second = run_detect_changes(state, previous_build=first["current_build_snapshot"])
        report = second["change_detection_report"]
        assert report["has_previous_build"] is True
        assert report["added_artifacts"] == []
        assert report["removed_artifacts"] == []
        assert report["modified_artifacts"] == []
        assert report["affected_artifacts"] == []
        assert len(report["unchanged_artifacts"]) == len(first["change_detection_report"]["added_artifacts"])
        assert report["summary"]["has_changes"] is False

    def test_modified_compiler_manifest_marks_downstream_as_affected(self):
        state = build_full_pipeline_state()
        first = run_detect_changes(state)

        mutated_bm = copy.deepcopy(state["build_metadata"])
        mutated_bm["compiler_metadata"]["compiler_manifest"]["chapter_identifier"] = "changed-on-purpose"
        second = run_detect_changes(
            state, build_metadata=mutated_bm, previous_build=first["current_build_snapshot"],
        )
        report = second["change_detection_report"]
        manifest_node = next(
            n for n in state["dependency_graph"]["nodes"] if n["node_type"] == "compiler_manifest"
        )
        assert manifest_node["node_id"] in report["modified_artifacts"]
        # compiler_fingerprints/compiler_readiness/compiler_build_summary
        # nodes all depend (directly or transitively) on compiler_manifest
        # per dependency_graph/build.py's own documented shape.
        assert len(report["affected_artifacts"]) > 0

    def test_missing_previous_build_is_not_an_error(self):
        state = build_full_pipeline_state()
        result = run_detect_changes(state, previous_build=None)
        assert result["change_detection_report"]["errors"] == []

    def test_malformed_previous_build_degrades_to_warning_not_exception(self):
        state = build_full_pipeline_state()
        result = run_detect_changes(state, previous_build={"not": "a snapshot"})
        report = result["change_detection_report"]
        assert report["has_previous_build"] is False
        assert any("previous_build" in w for w in report["errors"] + report["warnings"])

    def test_report_version_and_namespace(self):
        state = build_full_pipeline_state()
        result = run_detect_changes(state)
        report = result["change_detection_report"]
        assert report["namespace"] == NAMESPACE
        assert report["change_detection_report_version"]

    def test_current_build_snapshot_is_returned_for_future_reuse(self):
        state = build_full_pipeline_state()
        result = run_detect_changes(state)
        assert "artifact_fingerprints" in result["current_build_snapshot"]
        assert result["current_build_snapshot"]["namespace"] == NAMESPACE


# --------------------------------------------------------------------------
# 5. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_produce_structurally_identical_reports(self):
        state = build_full_pipeline_state()
        r1 = run_detect_changes(state)
        r2 = run_detect_changes(state)
        report_a = copy.deepcopy(r1["change_detection_report"])
        report_b = copy.deepcopy(r2["change_detection_report"])
        report_a.pop("generated_at")
        report_b.pop("generated_at")
        assert report_a == report_b

    def test_snapshot_fingerprints_stable_across_runs(self):
        state = build_full_pipeline_state()
        r1 = run_detect_changes(state)
        r2 = run_detect_changes(state)
        assert (
            r1["current_build_snapshot"]["artifact_fingerprints"]
            == r2["current_build_snapshot"]["artifact_fingerprints"]
        )


# --------------------------------------------------------------------------
# 6. Read-only behaviour
# --------------------------------------------------------------------------

class TestReadOnlyBehaviour:
    def test_read_only_over_every_input(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy({
            k: v for k, v in state.items()
            if k not in ("compiler_registry_manager", "graph_registry_manager")
        })
        run_detect_changes(state)
        after = {
            k: v for k, v in state.items()
            if k not in ("compiler_registry_manager", "graph_registry_manager")
        }
        assert after == before

    def test_never_mutates_registry_managers(self):
        state = build_full_pipeline_state()
        compiler_sizes_before = {
            name: state["compiler_registry_manager"].get(name).size()
            for name in state["compiler_registry_manager"].names()
        }
        graph_sizes_before = {
            name: state["graph_registry_manager"].get(name).size()
            for name in state["graph_registry_manager"].names()
        }
        run_detect_changes(state)
        for name, size in compiler_sizes_before.items():
            assert state["compiler_registry_manager"].get(name).size() == size
        for name, size in graph_sizes_before.items():
            assert state["graph_registry_manager"].get(name).size() == size


# --------------------------------------------------------------------------
# 7. State integration -- change_detection.state
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_has_current_is_false_before_set(self):
        assert change_detection_state.has_current_change_detection_report() is False
        assert change_detection_state.get_current_change_detection_report() is None

    def test_set_then_get_returns_same_object(self):
        state = build_full_pipeline_state()
        result = run_detect_changes(state)
        change_detection_state.set_current_change_detection_report(
            result["change_detection_report"]
        )
        assert change_detection_state.has_current_change_detection_report() is True
        assert (
            change_detection_state.get_current_change_detection_report()
            is result["change_detection_report"]
        )

    def test_reset_clears_state(self):
        state = build_full_pipeline_state()
        result = run_detect_changes(state)
        change_detection_state.set_current_change_detection_report(
            result["change_detection_report"]
        )
        change_detection_state.reset_change_detection_state()
        assert change_detection_state.has_current_change_detection_report() is False
        assert change_detection_state.get_current_change_detection_report() is None


# --------------------------------------------------------------------------
# 8. Pipeline wiring
# --------------------------------------------------------------------------

class TestPipelineWiring:
    def test_pipeline_imports_change_detection_integration_point(self):
        import pipeline
        assert hasattr(pipeline, "detect_changes")
        assert hasattr(pipeline, "change_detection_state")

    def test_process_chapter_source_calls_e3_after_e2(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e2_index = source.index("generate_dependency_graph(")
        e3_index = source.index("detect_changes(")
        assert e2_index < e3_index, "Phase E3 must be called after Phase E2"

    def test_e3_call_site_never_touches_chapter_dict(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e3_index = source.index("detect_changes(")
        chapter_dict_index = source.index("chapter_dict = json_writer.assemble_chapter_json(")
        between = source[e3_index:chapter_dict_index]
        assert "chapter_dict[" not in between
        assert "chapter_dict.update" not in between

    def test_e3_reuses_the_same_namespace_as_the_dependency_graph(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e3_call_start = source.index("detect_changes(")
        e3_call_end = source.index(")", source.index("previous_build=", e3_call_start))
        call_block = source[e3_call_start:e3_call_end]
        assert "namespace=chapter_reference" in call_block


# --------------------------------------------------------------------------
# 9. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_dependency_graph_state_untouched_by_e3(self):
        from dependency_graph import state as dependency_graph_state
        dependency_graph_state.reset_dependency_graph_state()
        assert dependency_graph_state.has_current_dependency_graph() is False
        state = build_full_pipeline_state()
        run_detect_changes(state)
        # E3 never writes into dependency_graph.state -- only pipeline.py's
        # own E2 call site does, and this test never called that.
        assert dependency_graph_state.has_current_dependency_graph() is False

    def test_dependency_graph_dict_unchanged_by_snapshot_or_traversal(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["dependency_graph"])
        run_detect_changes(state)
        assert state["dependency_graph"] == before

    def test_build_metadata_dict_unchanged(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["build_metadata"])
        run_detect_changes(state)
        assert state["build_metadata"] == before