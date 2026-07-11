"""
tests/test_e5_1_incremental_compilation_validation.py — unit tests for
Phase E5.1: Incremental Compilation Validation
(incremental_compilation_validation/), and its pipeline.py /
incremental_compilation_validation.state integration.

This file does NOT re-test Compiler IR / Knowledge Graph / Validation /
Build Metadata / Build Dependency Graph / Change Detection / Incremental
Compilation construction directly -- it treats all of those as frozen,
already-tested dependencies (see tests/test_e4_incremental_compilation.py,
which this file's own `build_full_pipeline_state()` helper extends by
one more phase, following that file's own "duplicated here, not
imported" convention -- this repo has no tests/__init__.py, so tests/
is not a package).
"""
from __future__ import annotations

import copy
import json
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

from change_detection.engine import detect_changes

from incremental_compilation.engine import plan_incremental_compilation

from incremental_compilation_validation.engine import (
    INCREMENTAL_COMPILATION_VALIDATION_ENGINE_VERSION,
    validate_incremental_compilation,
)
from incremental_compilation_validation.exceptions import (
    InvalidIncrementalCompilationPlanError,
)
from incremental_compilation_validation.report import (
    INCREMENTAL_COMPILATION_VALIDATION_VERSION,
    IncrementalCompilationValidationReport,
)
from incremental_compilation_validation.validator import (
    validate_incremental_compilation_plan,
)
from incremental_compilation_validation import state as icv_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- full Phase B->E4 pipeline fixture (same shape
# tests/test_e4_incremental_compilation.py's own build_full_pipeline_state()
# already establishes, extended one phase and duplicated here, not
# imported).
# --------------------------------------------------------------------------

def make_item(id_, urn, object_type, *, label_key=None, label_value=None,
              source_page=1, compiler_version="B5.1", **extra):
    d = {
        "id": id_,
        "urn": urn,
        "object_type": object_type,
        "source_page": source_page,
        "compiler_version": compiler_version,
    }
    if label_key is not None:
        d[label_key] = label_value
    d.update(extra)
    return d


def make_relationship_ready_manager() -> RegistryManager:
    manager = create_registry_manager()
    topics = [make_item("t1", "urn:topic:t1", "topic", label_key="title", label_value="Motion")]
    concepts = [make_item("c1", "urn:concept:c1", "concept", label_key="term", label_value="Velocity", topic_id="t1")]
    populate_registries(
        manager,
        topics=topics,
        concepts=concepts,
    )
    resolve_references(manager)
    resolve_relationships(manager)
    return manager


def build_full_pipeline_state(*, namespace=NAMESPACE):
    """One-shot: Phase B -> Phase C -> Phase D1 -> Phase D2 -> Phase D3
    -> Phase E1 -> Phase E2 -> Phase E3 -> Phase E4, exactly the
    sequence pipeline.py runs immediately before its own Phase E5.1
    integration point. Returns a dict of every artifact
    validate_incremental_compilation() consumes."""
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

    change_detection_result = detect_changes(
        namespace=namespace,
        dependency_graph=state["dependency_graph"],
        build_metadata=state["build_metadata"],
        release_readiness_report=state["release_readiness_report"],
        previous_build=None,
    )
    state["change_detection_report"] = change_detection_result["change_detection_report"]
    state["current_build_snapshot"] = change_detection_result["current_build_snapshot"]

    incremental_compilation_result = plan_incremental_compilation(
        namespace=namespace,
        change_detection_report=state["change_detection_report"],
        dependency_graph=state["dependency_graph"],
        build_metadata=state["build_metadata"],
    )
    state["incremental_compilation_plan"] = incremental_compilation_result["incremental_compilation_plan"]
    return state


def run_validate_incremental_compilation(state: dict, *, namespace=NAMESPACE, **overrides) -> dict:
    """Calls validate_incremental_compilation() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names -- exactly pipeline.py's own Phase
    E5.1 integration-point call shape."""
    kwargs = dict(
        namespace=namespace,
        incremental_compilation_plan=state["incremental_compilation_plan"],
        dependency_graph=state["dependency_graph"],
        change_detection_report=state["change_detection_report"],
    )
    kwargs.update(overrides)
    return validate_incremental_compilation(**kwargs)


@pytest.fixture(autouse=True)
def _reset_incremental_compilation_validation_state():
    """Every test starts and ends with a clean
    incremental_compilation_validation.state module -- mirrors
    tests/test_e4_incremental_compilation.py's own
    _reset_incremental_compilation_state fixture, one phase over."""
    icv_state.reset_incremental_compilation_validation_state()
    yield
    icv_state.reset_incremental_compilation_validation_state()


# --------------------------------------------------------------------------
# 1. Validation success (full, real pipeline fixture)
# --------------------------------------------------------------------------

class TestValidationSuccess:
    def test_full_pipeline_plan_validates_successfully(self):
        state = build_full_pipeline_state()
        result = run_validate_incremental_compilation(state)
        report = result["incremental_compilation_validation_report"]
        assert report["plan_available"] is True
        assert report["overall_status"] == "pass"
        assert report["errors"] == []
        assert "plan_exists" in report["checks_passed"]
        assert "rebuild_targets_exist" in report["checks_passed"]
        assert "dependency_references_exist" in report["checks_passed"]
        assert "dependency_ordering_is_valid" in report["checks_passed"]
        assert "no_circular_rebuild_ordering" in report["checks_passed"]
        assert "rebuild_reasons_exist" in report["checks_passed"]
        assert "reuse_reasons_exist" in report["checks_passed"]
        assert "deterministic_plan" in report["checks_passed"]
        assert "read_only_behaviour" in report["checks_passed"]
        assert report["checks_failed"] == []

    def test_second_identical_build_no_rebuild_plan_also_validates(self):
        state = build_full_pipeline_state()
        second_cdr = detect_changes(
            namespace=NAMESPACE,
            dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
            release_readiness_report=state["release_readiness_report"],
            previous_build=state["current_build_snapshot"],
        )
        state["change_detection_report"] = second_cdr["change_detection_report"]
        state["incremental_compilation_plan"] = plan_incremental_compilation(
            namespace=NAMESPACE,
            change_detection_report=state["change_detection_report"],
            dependency_graph=state["dependency_graph"],
            build_metadata=state["build_metadata"],
        )["incremental_compilation_plan"]
        result = run_validate_incremental_compilation(state)
        report = result["incremental_compilation_validation_report"]
        assert report["overall_status"] == "pass"
        assert report["classification_consistency"]["rebuild_artifacts_count"] == 0

    def test_report_version_and_namespace(self):
        state = build_full_pipeline_state()
        result = run_validate_incremental_compilation(state)
        report = result["incremental_compilation_validation_report"]
        assert report["namespace"] == NAMESPACE
        assert report["incremental_compilation_validation_version"] == INCREMENTAL_COMPILATION_VALIDATION_VERSION
        assert INCREMENTAL_COMPILATION_VALIDATION_ENGINE_VERSION


# --------------------------------------------------------------------------
# 2. Missing plan
# --------------------------------------------------------------------------

class TestMissingPlan:
    def test_none_plan_fails_with_missing_plan_error(self):
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=None,
        )
        assert result["plan_available"] is False
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "missing_plan" for e in result["errors"])
        assert "plan_exists" in result["checks_failed"]

    def test_malformed_plan_missing_required_keys_fails(self):
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE,
            incremental_compilation_plan={"namespace": NAMESPACE},
        )
        assert result["plan_available"] is False
        assert any(e["rule"] == "malformed_plan" for e in result["errors"])

    def test_invalid_plan_error_message_shape(self):
        exc = InvalidIncrementalCompilationPlanError("missing X")
        assert "incremental_compilation_plan" in str(exc)
        assert exc.reason == "missing X"


# --------------------------------------------------------------------------
# 3. Duplicate rebuild targets
# --------------------------------------------------------------------------

class TestDuplicateRebuildTargets:
    def _base_plan(self, **overrides):
        plan = dict(
            namespace=NAMESPACE,
            has_previous_build=False,
            dirty_artifacts=["a", "b"],
            affected_artifacts=[],
            rebuild_artifacts=["a", "b"],
            clean_artifacts=[],
            removed_artifacts=[],
            rebuild_order=["a", "b"],
            rebuild_reasons={"a": "added", "b": "added"},
            reuse_reasons={},
            dependency_traversal_summary={"cycle_detected": False, "cycle_node_ids": []},
        )
        plan.update(overrides)
        return plan

    def test_duplicate_rebuild_artifacts_fails(self):
        plan = self._base_plan(rebuild_artifacts=["a", "a", "b"])
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan,
        )
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "duplicate_entries_in_rebuild_artifacts" for e in result["errors"])
        assert "no_duplicate_artifact_entries" in result["checks_failed"]


# --------------------------------------------------------------------------
# 4. Duplicate rebuild order
# --------------------------------------------------------------------------

class TestDuplicateRebuildOrder:
    def test_duplicate_rebuild_order_fails(self):
        plan = TestDuplicateRebuildTargets()._base_plan(rebuild_order=["a", "a", "b"])
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan,
        )
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "duplicate_entries_in_rebuild_order" for e in result["errors"])


# --------------------------------------------------------------------------
# 5. Invalid references
# --------------------------------------------------------------------------

class TestInvalidReferences:
    def test_unknown_artifact_key_fails(self):
        plan = TestDuplicateRebuildTargets()._base_plan(
            dirty_artifacts=["a", "ghost"],
            rebuild_artifacts=["a", "ghost"],
            rebuild_order=["a", "ghost"],
            rebuild_reasons={"a": "added", "ghost": "added"},
        )
        graph = {"nodes": [{"node_id": "a"}, {"node_id": "b"}], "edges": []}
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=graph,
        )
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "unknown_artifact_reference" for e in result["errors"])
        assert "ghost" in result["reference_consistency"]["unknown_artifact_keys"]

    def test_synthetic_keys_are_not_unknown(self):
        plan = TestDuplicateRebuildTargets()._base_plan(
            dirty_artifacts=["a", "configuration"],
            rebuild_artifacts=["a", "configuration"],
            rebuild_order=["a", "configuration"],
            rebuild_reasons={"a": "added", "configuration": "added"},
        )
        graph = {"nodes": [{"node_id": "a"}], "edges": []}
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=graph,
        )
        assert result["reference_consistency"]["unknown_artifact_keys"] == []

    def test_no_dependency_graph_omits_reference_checks(self):
        plan = TestDuplicateRebuildTargets()._base_plan()
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=None,
        )
        assert "rebuild_targets_exist" not in result["checks_passed"]
        assert "rebuild_targets_exist" not in result["checks_failed"]
        assert any(w["rule"] == "reference_consistency_not_verified" for w in result["warnings"])


# --------------------------------------------------------------------------
# 6. Missing dependency (dangling edge endpoint)
# --------------------------------------------------------------------------

class TestMissingDependency:
    def test_dangling_edge_endpoint_fails(self):
        plan = TestDuplicateRebuildTargets()._base_plan()
        graph = {
            "nodes": [{"node_id": "a"}, {"node_id": "b"}],
            "edges": [{"edge_id": "e1", "source_node_id": "a", "target_node_id": "missing"}],
        }
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=graph,
        )
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "dangling_dependency_edge_endpoint" for e in result["errors"])


# --------------------------------------------------------------------------
# 7. Circular rebuild order
# --------------------------------------------------------------------------

class TestCircularRebuildOrder:
    def test_cycle_flag_from_plan_reported_as_error(self):
        plan = TestDuplicateRebuildTargets()._base_plan(
            dependency_traversal_summary={"cycle_detected": True, "cycle_node_ids": ["a", "b"]},
        )
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan,
        )
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "cycle_detected_in_rebuild_order" for e in result["errors"])
        assert "no_circular_rebuild_ordering" in result["checks_failed"]

    def test_ordering_violation_detected_against_dependency_graph(self):
        # "a" depends_on "b" (a must come AFTER b), but rebuild_order
        # places "a" before "b" -- a genuine ordering violation.
        plan = TestDuplicateRebuildTargets()._base_plan(rebuild_order=["a", "b"])
        graph = {
            "nodes": [{"node_id": "a"}, {"node_id": "b"}],
            "edges": [{"edge_id": "e1", "source_node_id": "a", "target_node_id": "b"}],
        }
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=graph,
        )
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "dependency_ordering_violated" for e in result["errors"])

    def test_correct_ordering_passes(self):
        plan = TestDuplicateRebuildTargets()._base_plan(rebuild_order=["b", "a"])
        graph = {
            "nodes": [{"node_id": "a"}, {"node_id": "b"}],
            "edges": [{"edge_id": "e1", "source_node_id": "a", "target_node_id": "b"}],
        }
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=graph,
        )
        assert "dependency_ordering_is_valid" in result["checks_passed"]


# --------------------------------------------------------------------------
# 8. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_reproducible_order_passes(self):
        plan = TestDuplicateRebuildTargets()._base_plan(rebuild_order=["a", "b"])
        graph = {"nodes": [{"node_id": "a"}, {"node_id": "b"}], "edges": []}
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=graph,
        )
        assert "deterministic_plan" in result["checks_passed"]
        assert result["determinism_consistency"]["reproduced_order_matches"] is True

    def test_tampered_order_fails_determinism(self):
        # Recorded rebuild_order deliberately does not match what
        # compute_rebuild_order() would produce for this rebuild set
        # over this graph.
        plan = TestDuplicateRebuildTargets()._base_plan(rebuild_order=["b", "a"])
        graph = {"nodes": [{"node_id": "a"}, {"node_id": "b"}], "edges": []}
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=graph,
        )
        assert result["overall_status"] == "fail"
        assert any(e["rule"] == "non_deterministic_rebuild_order" for e in result["errors"])

    def test_no_dependency_graph_omits_determinism_check(self):
        plan = TestDuplicateRebuildTargets()._base_plan()
        result = validate_incremental_compilation_plan(
            namespace=NAMESPACE, incremental_compilation_plan=plan, dependency_graph=None,
        )
        assert "deterministic_plan" not in result["checks_passed"]
        assert "deterministic_plan" not in result["checks_failed"]

    def test_full_pipeline_plan_deterministic_across_repeated_validation(self):
        state = build_full_pipeline_state()
        r1 = run_validate_incremental_compilation(state)
        r2 = run_validate_incremental_compilation(state)
        report_a = copy.deepcopy(r1["incremental_compilation_validation_report"])
        report_b = copy.deepcopy(r2["incremental_compilation_validation_report"])
        report_a.pop("generated_at")
        report_b.pop("generated_at")
        assert report_a == report_b


# --------------------------------------------------------------------------
# 9. Read-only behaviour
# --------------------------------------------------------------------------

class TestReadOnlyBehaviour:
    def test_read_only_check_passes_on_untouched_inputs(self):
        state = build_full_pipeline_state()
        result = run_validate_incremental_compilation(state)
        report = result["incremental_compilation_validation_report"]
        assert report["read_only_consistency"]["plan_unmutated"] is True
        assert report["read_only_consistency"]["dependency_graph_unmutated"] is True
        assert report["read_only_consistency"]["change_detection_report_unmutated"] is True
        assert "read_only_behaviour" in report["checks_passed"]

    def test_never_mutates_plan_dependency_graph_or_change_detection_report(self):
        state = build_full_pipeline_state()
        before_plan = copy.deepcopy(state["incremental_compilation_plan"])
        before_dg = copy.deepcopy(state["dependency_graph"])
        before_cdr = copy.deepcopy(state["change_detection_report"])
        run_validate_incremental_compilation(state)
        assert state["incremental_compilation_plan"] == before_plan
        assert state["dependency_graph"] == before_dg
        assert state["change_detection_report"] == before_cdr

    def test_never_mutates_registry_managers(self):
        state = build_full_pipeline_state()
        compiler_sizes_before = {
            name: state["compiler_registry_manager"].get(name).size()
            for name in state["compiler_registry_manager"].names()
        }
        run_validate_incremental_compilation(state)
        for name, size in compiler_sizes_before.items():
            assert state["compiler_registry_manager"].get(name).size() == size


# --------------------------------------------------------------------------
# 10. State integration -- incremental_compilation_validation.state
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_has_current_is_false_before_set(self):
        assert icv_state.has_current_incremental_compilation_validation_report() is False
        assert icv_state.get_current_incremental_compilation_validation_report() is None
        assert icv_state.has_current_incremental_compilation_validation_status() is False
        assert icv_state.get_current_incremental_compilation_validation_status() is None

    def test_set_then_get_returns_same_object_and_status(self):
        state = build_full_pipeline_state()
        result = run_validate_incremental_compilation(state)
        report = result["incremental_compilation_validation_report"]
        icv_state.set_current_incremental_compilation_validation_report(report)
        icv_state.set_current_incremental_compilation_validation_status(report["overall_status"])
        assert icv_state.has_current_incremental_compilation_validation_report() is True
        assert icv_state.get_current_incremental_compilation_validation_report() is report
        assert icv_state.get_current_incremental_compilation_validation_status() == "pass"

    def test_reset_clears_state(self):
        state = build_full_pipeline_state()
        result = run_validate_incremental_compilation(state)
        report = result["incremental_compilation_validation_report"]
        icv_state.set_current_incremental_compilation_validation_report(report)
        icv_state.set_current_incremental_compilation_validation_status(report["overall_status"])
        icv_state.reset_incremental_compilation_validation_state()
        assert icv_state.has_current_incremental_compilation_validation_report() is False
        assert icv_state.get_current_incremental_compilation_validation_report() is None
        assert icv_state.has_current_incremental_compilation_validation_status() is False
        assert icv_state.get_current_incremental_compilation_validation_status() is None


# --------------------------------------------------------------------------
# 11. Pipeline wiring
# --------------------------------------------------------------------------

class TestPipelineWiring:
    def test_pipeline_imports_incremental_compilation_validation_integration_point(self):
        import pipeline
        assert hasattr(pipeline, "validate_incremental_compilation")
        assert hasattr(pipeline, "incremental_compilation_validation_state")

    def test_process_chapter_source_calls_e5_1_after_e4(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e4_index = source.index("plan_incremental_compilation(")
        e5_1_index = source.index("validate_incremental_compilation(")
        assert e4_index < e5_1_index, "Phase E5.1 must be called after Phase E4"

    def test_e5_1_call_site_never_touches_chapter_dict(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e5_1_index = source.index("validate_incremental_compilation(")
        chapter_dict_index = source.index("chapter_dict = json_writer.assemble_chapter_json(")
        between = source[e5_1_index:chapter_dict_index]
        assert "chapter_dict[" not in between
        assert "chapter_dict.update" not in between

    def test_e5_1_reuses_the_same_namespace_as_incremental_compilation(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        call_start = source.index("validate_incremental_compilation(")
        call_end = source.index(")", source.index("change_detection_report=", call_start))
        call_block = source[call_start:call_end]
        assert "namespace=chapter_reference" in call_block

    def test_e5_1_never_calls_e5_2_or_phase_f(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        assert "finalize_incremental_compilation" not in source
        assert "execute_compilation" not in source


# --------------------------------------------------------------------------
# 12. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_incremental_compilation_state_untouched_by_e5_1(self):
        from incremental_compilation import state as incremental_compilation_state
        incremental_compilation_state.reset_incremental_compilation_state()
        assert incremental_compilation_state.has_current_incremental_compilation_plan() is False
        state = build_full_pipeline_state()
        run_validate_incremental_compilation(state)
        # E5.1 never writes into incremental_compilation.state -- only
        # pipeline.py's own E4 call site does, and this test never
        # called that.
        assert incremental_compilation_state.has_current_incremental_compilation_plan() is False

    def test_incremental_compilation_plan_dict_unchanged_by_validation(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["incremental_compilation_plan"])
        run_validate_incremental_compilation(state)
        assert state["incremental_compilation_plan"] == before

    def test_dependency_graph_dict_unchanged_by_validation(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["dependency_graph"])
        run_validate_incremental_compilation(state)
        assert state["dependency_graph"] == before

    def test_change_detection_report_dict_unchanged_by_validation(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["change_detection_report"])
        run_validate_incremental_compilation(state)
        assert state["change_detection_report"] == before

    def test_report_is_a_plain_serializable_dict(self):
        state = build_full_pipeline_state()
        result = run_validate_incremental_compilation(state)
        json.dumps(result["incremental_compilation_validation_report"])  # must not raise

    def test_report_dataclass_to_dict_matches_engine_output_shape(self):
        report = IncrementalCompilationValidationReport(
            generated_at="t", namespace=NAMESPACE,
        ).to_dict()
        state = build_full_pipeline_state()
        result = run_validate_incremental_compilation(state)
        assert set(report.keys()) == set(result["incremental_compilation_validation_report"].keys())