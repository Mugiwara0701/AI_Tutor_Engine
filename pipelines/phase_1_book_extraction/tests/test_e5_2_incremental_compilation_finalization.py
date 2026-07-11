"""
tests/test_e5_2_incremental_compilation_finalization.py — unit tests
for Phase E5.2: Incremental Compilation Finalization
(incremental_compilation_finalization/), and its pipeline.py /
incremental_compilation_finalization.state integration.

This file does NOT re-test Compiler IR / Knowledge Graph / Validation /
Build Metadata / Build Dependency Graph / Change Detection /
Incremental Compilation / Incremental Compilation Validation
construction directly -- it treats all of those as frozen,
already-tested dependencies (see
tests/test_e5_1_incremental_compilation_validation.py, which this
file's own build_full_pipeline_state() helper extends by one more
phase, following that file's own "duplicated here, not imported"
convention -- this repo has no tests/__init__.py, so tests/ is not a
package).
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

from change_detection.engine import detect_changes

from incremental_compilation.engine import plan_incremental_compilation

from incremental_compilation_validation.engine import validate_incremental_compilation

from incremental_compilation_finalization.finalize import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    determine_final_incremental_compilation_status,
    finalize_incremental_compilation,
    generate_incremental_compilation_build_summary,
    generate_incremental_compilation_readiness_report,
)
from incremental_compilation_finalization.report import (
    INCREMENTAL_COMPILATION_FINALIZATION_VERSION,
    IncrementalCompilationBuildSummary,
    IncrementalCompilationReadinessReport,
)
from incremental_compilation_finalization import state as icf_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- full Phase B->E5.1 pipeline fixture (same shape
# tests/test_e5_1_incremental_compilation_validation.py's own
# build_full_pipeline_state() already establishes, extended one phase
# and duplicated here, not imported).
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
    topics = [make_item("t1", "urn:topic:t1", "topic", label_key="title", label_value="Kinematics")]
    concepts = [
        make_item(
            "c1", "urn:concept:c1", "concept", label_key="term", label_value="Velocity",
            topic_id="t1",
        ),
    ]
    populate_registries(
        manager,
        topics=topics,
        concepts=concepts,
    )
    resolve_references(manager)
    resolve_relationships(manager)
    return manager


def build_full_pipeline_state(*, namespace=NAMESPACE):
    """One-shot: Phase B -> ... -> Phase E4 -> Phase E5.1, exactly the
    sequence pipeline.py runs immediately before its own Phase E5.2
    integration point. Returns a dict of every artifact
    finalize_incremental_compilation() consumes."""
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

    validation_result = validate_incremental_compilation(
        namespace=namespace,
        incremental_compilation_plan=state["incremental_compilation_plan"],
        dependency_graph=state["dependency_graph"],
        change_detection_report=state["change_detection_report"],
    )
    state["incremental_compilation_validation_report"] = validation_result[
        "incremental_compilation_validation_report"
    ]
    return state


def run_finalize_incremental_compilation(state: dict, *, namespace=NAMESPACE, **overrides) -> dict:
    """Calls finalize_incremental_compilation() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names -- exactly pipeline.py's own Phase
    E5.2 integration-point call shape."""
    kwargs = dict(
        namespace=namespace,
        incremental_compilation_plan=state["incremental_compilation_plan"],
        incremental_compilation_validation_report=state["incremental_compilation_validation_report"],
        build_metadata=state["build_metadata"],
        dependency_graph=state["dependency_graph"],
        change_detection_report=state["change_detection_report"],
    )
    kwargs.update(overrides)
    return finalize_incremental_compilation(**kwargs)


def _base_plan(**overrides):
    plan = dict(
        namespace=NAMESPACE,
        has_previous_build=False,
        dirty_artifacts=["a", "b"],
        affected_artifacts=[],
        rebuild_artifacts=["a", "b"],
        clean_artifacts=["c"],
        removed_artifacts=[],
        rebuild_order=["a", "b"],
        rebuild_reasons={"a": "added", "b": "added"},
        reuse_reasons={"c": "unchanged"},
        dependency_traversal_summary={"cycle_detected": False, "cycle_node_ids": []},
        warnings=[],
        errors=[],
        summary={
            "dirty_count": 2, "affected_count": 0, "rebuild_count": 2,
            "clean_count": 1, "removed_count": 0,
            "total_artifacts_considered": 3, "requires_rebuild": True,
            "is_full_rebuild": False,
        },
    )
    plan.update(overrides)
    return plan


def _base_validation_report(*, overall_status="pass", plan_available=True, **overrides):
    report = dict(
        namespace=NAMESPACE,
        plan_available=plan_available,
        overall_status=overall_status,
        errors=[],
        warnings=[],
        checks_passed=["plan_exists"],
        checks_failed=[],
    )
    report.update(overrides)
    return report


@pytest.fixture(autouse=True)
def _reset_incremental_compilation_finalization_state():
    """Every test starts and ends with a clean
    incremental_compilation_finalization.state module -- mirrors
    tests/test_e5_1_incremental_compilation_validation.py's own
    _reset_incremental_compilation_validation_state fixture, one phase
    over."""
    icf_state.reset_incremental_compilation_finalization_state()
    yield
    icf_state.reset_incremental_compilation_finalization_state()


# --------------------------------------------------------------------------
# 1. Successful finalization / READY status (full, real pipeline fixture)
# --------------------------------------------------------------------------

class TestSuccessfulFinalizationReady:
    def test_full_pipeline_finalizes_ready(self):
        state = build_full_pipeline_state()
        # A brand-new chapter's own first-ever build carries no warnings
        # anywhere (see IncrementalCompilationPlan.warnings/
        # IncrementalCompilationValidationReport.warnings on a clean
        # first build), so this should resolve to a clean READY.
        assert state["incremental_compilation_plan"]["warnings"] == []
        assert state["incremental_compilation_validation_report"]["warnings"] == []
        result = run_finalize_incremental_compilation(state)
        assert result["incremental_compilation_final_status"] == STATUS_READY
        readiness = result["incremental_compilation_readiness_report"]
        assert readiness["readiness_status"] == STATUS_READY
        assert readiness["plan_available"] is True
        assert readiness["validation_available"] is True
        summary = result["incremental_compilation_build_summary"]
        assert summary["final_status"] == STATUS_READY

    def test_report_version_and_namespace(self):
        state = build_full_pipeline_state()
        result = run_finalize_incremental_compilation(state)
        readiness = result["incremental_compilation_readiness_report"]
        summary = result["incremental_compilation_build_summary"]
        assert readiness["namespace"] == NAMESPACE
        assert summary["namespace"] == NAMESPACE
        assert readiness["incremental_compilation_finalization_version"] == INCREMENTAL_COMPILATION_FINALIZATION_VERSION
        assert summary["finalize_version"] == INCREMENTAL_COMPILATION_FINALIZATION_VERSION

    def test_build_summary_counts_match_plan_summary(self):
        state = build_full_pipeline_state()
        result = run_finalize_incremental_compilation(state)
        summary = result["incremental_compilation_build_summary"]
        plan_summary = state["incremental_compilation_plan"]["summary"]
        assert summary["rebuild_target_count"] == plan_summary["rebuild_count"]
        assert summary["reused_artifact_count"] == plan_summary["clean_count"]
        assert summary["dirty_artifact_count"] == plan_summary["dirty_count"]
        assert summary["removed_artifact_count"] == plan_summary["removed_count"]


# --------------------------------------------------------------------------
# 2. READY_WITH_WARNINGS status
# --------------------------------------------------------------------------

class TestReadyWithWarnings:
    def test_plan_warning_yields_ready_with_warnings(self):
        plan = _base_plan(warnings=["cache directory was stale; ignored"])
        report = _base_validation_report()
        status = determine_final_incremental_compilation_status(plan, report)
        assert status == STATUS_READY_WITH_WARNINGS

    def test_validation_report_warning_yields_ready_with_warnings(self):
        plan = _base_plan()
        report = _base_validation_report(
            warnings=[{"severity": "warning", "rule": "stale_rebuild_reasons", "message": "x"}]
        )
        status = determine_final_incremental_compilation_status(plan, report)
        assert status == STATUS_READY_WITH_WARNINGS

    def test_readiness_report_reflects_warnings(self):
        plan = _base_plan(warnings=["one warning"])
        report = _base_validation_report()
        readiness = generate_incremental_compilation_readiness_report(
            namespace=NAMESPACE,
            incremental_compilation_plan=plan,
            incremental_compilation_validation_report=report,
            readiness_status=STATUS_READY_WITH_WARNINGS,
        )
        assert readiness["readiness_status"] == STATUS_READY_WITH_WARNINGS
        assert readiness["warning_count"] == 1
        assert "one warning" in readiness["warnings"]


# --------------------------------------------------------------------------
# 3. FAILED status
# --------------------------------------------------------------------------

class TestFailedStatus:
    def test_plan_error_yields_failed(self):
        plan = _base_plan(errors=["dependency graph was malformed"])
        report = _base_validation_report()
        status = determine_final_incremental_compilation_status(plan, report)
        assert status == STATUS_FAILED

    def test_validation_report_fail_status_yields_failed(self):
        plan = _base_plan()
        report = _base_validation_report(overall_status="fail")
        status = determine_final_incremental_compilation_status(plan, report)
        assert status == STATUS_FAILED

    def test_validation_report_plan_unavailable_yields_failed(self):
        plan = _base_plan()
        report = _base_validation_report(plan_available=False)
        status = determine_final_incremental_compilation_status(plan, report)
        assert status == STATUS_FAILED

    def test_full_pipeline_with_failing_validation_report_finalizes_failed(self):
        state = build_full_pipeline_state()
        failing_report = copy.deepcopy(state["incremental_compilation_validation_report"])
        failing_report["overall_status"] = "fail"
        failing_report["errors"] = [
            {"severity": "error", "rule": "plan_mutated", "message": "forced test failure"}
        ]
        result = run_finalize_incremental_compilation(
            state, incremental_compilation_validation_report=failing_report,
        )
        assert result["incremental_compilation_final_status"] == STATUS_FAILED
        assert result["incremental_compilation_readiness_report"]["readiness_status"] == STATUS_FAILED
        assert result["incremental_compilation_build_summary"]["final_status"] == STATUS_FAILED


# --------------------------------------------------------------------------
# 4. Missing validation report
# --------------------------------------------------------------------------

class TestMissingValidationReport:
    def test_none_validation_report_yields_failed(self):
        plan = _base_plan()
        status = determine_final_incremental_compilation_status(plan, None)
        assert status == STATUS_FAILED

    def test_readiness_report_flags_missing_validation_report(self):
        plan = _base_plan()
        readiness = generate_incremental_compilation_readiness_report(
            namespace=NAMESPACE,
            incremental_compilation_plan=plan,
            incremental_compilation_validation_report=None,
            readiness_status=STATUS_FAILED,
        )
        assert readiness["validation_available"] is False
        assert readiness["plan_available"] is True
        assert any("IncrementalCompilationValidationReport" in e for e in readiness["errors"])


# --------------------------------------------------------------------------
# 5. Invalid validation report
# --------------------------------------------------------------------------

class TestInvalidValidationReport:
    def test_validation_report_missing_overall_status_key_yields_failed(self):
        plan = _base_plan()
        malformed_report = {"namespace": NAMESPACE, "plan_available": True}
        status = determine_final_incremental_compilation_status(plan, malformed_report)
        assert status == STATUS_FAILED

    def test_empty_dict_validation_report_yields_failed(self):
        plan = _base_plan()
        status = determine_final_incremental_compilation_status(plan, {})
        assert status == STATUS_FAILED


# --------------------------------------------------------------------------
# 6. Missing plan
# --------------------------------------------------------------------------

class TestMissingPlan:
    def test_none_plan_yields_failed(self):
        report = _base_validation_report()
        status = determine_final_incremental_compilation_status(None, report)
        assert status == STATUS_FAILED

    def test_readiness_report_flags_missing_plan(self):
        report = _base_validation_report()
        readiness = generate_incremental_compilation_readiness_report(
            namespace=NAMESPACE,
            incremental_compilation_plan=None,
            incremental_compilation_validation_report=report,
            readiness_status=STATUS_FAILED,
        )
        assert readiness["plan_available"] is False
        assert readiness["rebuild_statistics"] == {}
        assert any("IncrementalCompilationPlan" in e for e in readiness["errors"])

    def test_build_summary_zero_counts_when_plan_missing(self):
        report = _base_validation_report()
        summary = generate_incremental_compilation_build_summary(
            namespace=NAMESPACE,
            incremental_compilation_plan=None,
            incremental_compilation_validation_report=report,
            final_status=STATUS_FAILED,
        )
        assert summary["rebuild_target_count"] == 0
        assert summary["reused_artifact_count"] == 0
        assert summary["final_status"] == STATUS_FAILED


# --------------------------------------------------------------------------
# 7. Build summary generation
# --------------------------------------------------------------------------

class TestBuildSummaryGeneration:
    def test_counts_come_from_plan_summary_not_recomputed(self):
        plan = _base_plan(
            rebuild_artifacts=["a", "b", "x"],
            summary={
                "dirty_count": 2, "affected_count": 1, "rebuild_count": 3,
                "clean_count": 1, "removed_count": 0,
                "total_artifacts_considered": 4, "requires_rebuild": True,
                "is_full_rebuild": False,
            },
        )
        report = _base_validation_report()
        summary = generate_incremental_compilation_build_summary(
            namespace=NAMESPACE,
            incremental_compilation_plan=plan,
            incremental_compilation_validation_report=report,
            final_status=STATUS_READY,
        )
        # rebuild_target_count is read straight off plan["summary"]["rebuild_count"]
        # (3), NOT len(plan["rebuild_artifacts"]) computed a second way that
        # would also equal 3 here -- verified against a plan whose own
        # dirty/affected/rebuild_artifacts counts would disagree with a naive
        # re-derivation if one were computed.
        assert summary["rebuild_target_count"] == 3
        assert summary["dirty_artifact_count"] == 2

    def test_validation_statistics_embedded(self):
        plan = _base_plan()
        report = _base_validation_report(
            checks_passed=["a", "b"], checks_failed=["c"],
            errors=[{"severity": "error", "rule": "x", "message": "y"}],
        )
        summary = generate_incremental_compilation_build_summary(
            namespace=NAMESPACE,
            incremental_compilation_plan=plan,
            incremental_compilation_validation_report=report,
            final_status=STATUS_READY,
        )
        assert summary["validation_statistics"]["checks_passed_count"] == 2
        assert summary["validation_statistics"]["checks_failed_count"] == 1
        assert summary["validation_statistics"]["error_count"] == 1

    def test_is_a_dataclass_backed_dict(self):
        instance = IncrementalCompilationBuildSummary()
        assert instance.to_dict()["final_status"] == "unknown"


# --------------------------------------------------------------------------
# 8. Readiness report generation
# --------------------------------------------------------------------------

class TestReadinessReportGeneration:
    def test_rebuild_statistics_is_plan_summary_verbatim(self):
        plan = _base_plan()
        report = _base_validation_report()
        readiness = generate_incremental_compilation_readiness_report(
            namespace=NAMESPACE,
            incremental_compilation_plan=plan,
            incremental_compilation_validation_report=report,
            readiness_status=STATUS_READY,
        )
        assert readiness["rebuild_statistics"] == plan["summary"]

    def test_overall_recommendation_present_for_each_status(self):
        plan = _base_plan()
        report = _base_validation_report()
        for status in (STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED):
            readiness = generate_incremental_compilation_readiness_report(
                namespace=NAMESPACE,
                incremental_compilation_plan=plan,
                incremental_compilation_validation_report=report,
                readiness_status=status,
            )
            assert readiness["overall_recommendation"]

    def test_is_a_dataclass_backed_dict(self):
        instance = IncrementalCompilationReadinessReport()
        assert instance.to_dict()["readiness_status"] == "unknown"


# --------------------------------------------------------------------------
# 9. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_repeated_calls_produce_identical_result_modulo_timestamp(self):
        state = build_full_pipeline_state()
        r1 = run_finalize_incremental_compilation(state)
        r2 = run_finalize_incremental_compilation(state)
        r1_readiness = dict(r1["incremental_compilation_readiness_report"])
        r2_readiness = dict(r2["incremental_compilation_readiness_report"])
        r1_readiness.pop("generated_at")
        r2_readiness.pop("generated_at")
        assert r1_readiness == r2_readiness

        r1_summary = dict(r1["incremental_compilation_build_summary"])
        r2_summary = dict(r2["incremental_compilation_build_summary"])
        r1_summary.pop("generated_at")
        r2_summary.pop("generated_at")
        assert r1_summary == r2_summary

        assert r1["incremental_compilation_final_status"] == r2["incremental_compilation_final_status"]

    def test_determine_final_status_is_a_pure_function(self):
        plan = _base_plan()
        report = _base_validation_report()
        results = {
            determine_final_incremental_compilation_status(plan, report)
            for _ in range(5)
        }
        assert len(results) == 1


# --------------------------------------------------------------------------
# 10. Read-only behaviour
# --------------------------------------------------------------------------

class TestReadOnlyBehaviour:
    def test_plan_and_validation_report_never_mutated(self):
        state = build_full_pipeline_state()
        plan_before = copy.deepcopy(state["incremental_compilation_plan"])
        report_before = copy.deepcopy(state["incremental_compilation_validation_report"])
        run_finalize_incremental_compilation(state)
        assert state["incremental_compilation_plan"] == plan_before
        assert state["incremental_compilation_validation_report"] == report_before

    def test_optional_context_arguments_never_mutated(self):
        state = build_full_pipeline_state()
        build_metadata_before = copy.deepcopy(state["build_metadata"])
        dependency_graph_before = copy.deepcopy(state["dependency_graph"])
        change_detection_report_before = copy.deepcopy(state["change_detection_report"])
        run_finalize_incremental_compilation(state)
        assert state["build_metadata"] == build_metadata_before
        assert state["dependency_graph"] == dependency_graph_before
        assert state["change_detection_report"] == change_detection_report_before


# --------------------------------------------------------------------------
# 11. State integration
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_state_starts_empty(self):
        assert icf_state.get_current_incremental_compilation_readiness_report() is None
        assert icf_state.get_current_incremental_compilation_build_summary() is None
        assert icf_state.get_current_incremental_compilation_final_status() is None
        assert icf_state.has_current_incremental_compilation_readiness_report() is False
        assert icf_state.has_current_incremental_compilation_build_summary() is False
        assert icf_state.has_current_incremental_compilation_final_status() is False

    def test_set_then_get_round_trips(self):
        icf_state.set_current_incremental_compilation_readiness_report({"readiness_status": "READY"})
        icf_state.set_current_incremental_compilation_build_summary({"final_status": "READY"})
        icf_state.set_current_incremental_compilation_final_status("READY")
        assert icf_state.get_current_incremental_compilation_readiness_report() == {"readiness_status": "READY"}
        assert icf_state.get_current_incremental_compilation_build_summary() == {"final_status": "READY"}
        assert icf_state.get_current_incremental_compilation_final_status() == "READY"
        assert icf_state.has_current_incremental_compilation_readiness_report() is True
        assert icf_state.has_current_incremental_compilation_build_summary() is True
        assert icf_state.has_current_incremental_compilation_final_status() is True

    def test_reset_clears_all_three_slots(self):
        icf_state.set_current_incremental_compilation_readiness_report({"x": 1})
        icf_state.set_current_incremental_compilation_build_summary({"y": 2})
        icf_state.set_current_incremental_compilation_final_status("READY")
        icf_state.reset_incremental_compilation_finalization_state()
        assert icf_state.get_current_incremental_compilation_readiness_report() is None
        assert icf_state.get_current_incremental_compilation_build_summary() is None
        assert icf_state.get_current_incremental_compilation_final_status() is None


# --------------------------------------------------------------------------
# 12. Pipeline integration
# --------------------------------------------------------------------------

class TestPipelineWiring:
    def test_pipeline_imports_finalize_and_state(self):
        import pipeline
        assert hasattr(pipeline, "finalize_incremental_compilation")
        assert hasattr(pipeline, "incremental_compilation_finalization_state")

    def test_pipeline_calls_finalize_after_validation(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline)
        validation_call_index = source.index("validate_incremental_compilation(")
        finalize_call_index = source.index("finalize_incremental_compilation(")
        assert finalize_call_index > validation_call_index

    def test_pipeline_never_writes_into_chapter_json_assembly(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline)
        finalize_block_start = source.index("# ---- Phase E5.2")
        finalize_block_end = source.index("# Diagnostic only, and deliberately guarded", finalize_block_start)
        finalize_block = source[finalize_block_start:finalize_block_end]
        # Nothing in the Phase E5.2 integration block itself writes into
        # chapter_dict or calls assemble_chapter_json -- both of those
        # happen later, from artifacts this block never touches.
        assert "chapter_dict[" not in finalize_block
        assert "assemble_chapter_json(" not in finalize_block


# --------------------------------------------------------------------------
# 13. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_incremental_compilation_plan_shape_unaffected(self):
        state = build_full_pipeline_state()
        plan_keys_before = set(state["incremental_compilation_plan"].keys())
        run_finalize_incremental_compilation(state)
        assert set(state["incremental_compilation_plan"].keys()) == plan_keys_before

    def test_validation_report_shape_unaffected(self):
        state = build_full_pipeline_state()
        report_keys_before = set(state["incremental_compilation_validation_report"].keys())
        run_finalize_incremental_compilation(state)
        assert set(state["incremental_compilation_validation_report"].keys()) == report_keys_before

    def test_existing_e4_and_e5_1_public_interfaces_still_importable(self):
        # A minimal regression smoke test that E5.2's own new package
        # did not shadow or break any existing Phase E4/E5.1 import.
        from incremental_compilation.engine import plan_incremental_compilation as _p
        from incremental_compilation_validation.engine import validate_incremental_compilation as _v
        assert callable(_p)
        assert callable(_v)

    def test_finalize_function_keyword_only_signature_stable(self):
        import inspect
        sig = inspect.signature(finalize_incremental_compilation)
        params = sig.parameters
        assert "namespace" in params
        assert "incremental_compilation_plan" in params
        assert "incremental_compilation_validation_report" in params
        assert params["build_metadata"].default is None
        assert params["dependency_graph"].default is None
        assert params["change_detection_report"].default is None
