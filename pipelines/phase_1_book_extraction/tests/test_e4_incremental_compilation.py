"""
tests/test_e4_incremental_compilation.py — unit tests for Phase E4:
Incremental Compilation (incremental_compilation/), and its pipeline.py
/ incremental_compilation.state integration.

This file does NOT re-test Compiler IR / Knowledge Graph / Validation /
Build Metadata / Build Dependency Graph / Change Detection construction
directly -- it treats all of those as frozen, already-tested
dependencies (see tests/test_e1_build_metadata.py,
tests/test_e2_dependency_graph.py, and
tests/test_e3_change_detection.py, which this file's own
`build_full_pipeline_state()` helper extends by one more phase,
following those files' own "duplicated here, not imported" convention
-- this repo has no tests/__init__.py, so tests/ is not a package).
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

from incremental_compilation.engine import (
    INCREMENTAL_COMPILATION_VERSION,
    plan_incremental_compilation,
)
from incremental_compilation.exceptions import InvalidChangeDetectionReportError
from incremental_compilation.plan import IncrementalCompilationPlan
from incremental_compilation.planner import plan_rebuild
from incremental_compilation.traversal import compute_rebuild_order
from incremental_compilation import state as incremental_compilation_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- full Phase B->E3 pipeline fixture (same shape
# tests/test_e3_change_detection.py's own build_full_pipeline_state()
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
    -> Phase E1 -> Phase E2 -> Phase E3, exactly the sequence
    pipeline.py runs immediately before its own Phase E4 integration
    point. Returns a dict of every artifact
    plan_incremental_compilation() consumes."""
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
    return state


def run_plan_incremental_compilation(state: dict, *, namespace=NAMESPACE, **overrides) -> dict:
    """Calls plan_incremental_compilation() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names -- exactly pipeline.py's own Phase
    E4 integration-point call shape."""
    kwargs = dict(
        namespace=namespace,
        change_detection_report=state["change_detection_report"],
        dependency_graph=state["dependency_graph"],
        build_metadata=state["build_metadata"],
    )
    kwargs.update(overrides)
    return plan_incremental_compilation(**kwargs)


def second_build_change_detection_report(state: dict, *, mutated_build_metadata=None):
    """Runs detect_changes() a second time, using the first build's own
    current_build_snapshot as `previous_build` -- the standard
    "two consecutive real builds" shape several E4 tests below need."""
    return detect_changes(
        namespace=NAMESPACE,
        dependency_graph=state["dependency_graph"],
        build_metadata=mutated_build_metadata or state["build_metadata"],
        release_readiness_report=state["release_readiness_report"],
        previous_build=state["current_build_snapshot"],
    )


@pytest.fixture(autouse=True)
def _reset_incremental_compilation_state():
    """Every test starts and ends with a clean
    incremental_compilation.state module -- mirrors
    tests/test_e3_change_detection.py's own
    _reset_change_detection_state fixture, one phase over."""
    incremental_compilation_state.reset_incremental_compilation_state()
    yield
    incremental_compilation_state.reset_incremental_compilation_state()


# --------------------------------------------------------------------------
# 1. Dependency Graph Traversal (rebuild order)
# --------------------------------------------------------------------------

class TestComputeRebuildOrder:
    def _linear_graph(self):
        # a <- b <- c  (b depends_on a, c depends_on b)
        return {
            "edges": [
                {"source_node_id": "b", "target_node_id": "a"},
                {"source_node_id": "c", "target_node_id": "b"},
            ],
        }

    def test_dependency_ordered_before_dependent(self):
        graph = self._linear_graph()
        result = compute_rebuild_order(graph, {"a", "b", "c"})
        assert result["order"] == ["a", "b", "c"]
        assert result["cycle_detected"] is False

    def test_only_edges_within_node_ids_constrain_order(self):
        graph = self._linear_graph()
        # "a" excluded from the rebuild set -- "b" has no remaining
        # in-set predecessor, so "b" and "c" simply order by the
        # remaining constraint (c depends on b).
        result = compute_rebuild_order(graph, {"b", "c"})
        assert result["order"] == ["b", "c"]

    def test_unrelated_nodes_break_ties_alphabetically(self):
        graph = {"edges": []}
        result = compute_rebuild_order(graph, {"z", "a", "m"})
        assert result["order"] == ["a", "m", "z"]

    def test_empty_node_ids_yields_empty_order(self):
        result = compute_rebuild_order(self._linear_graph(), set())
        assert result["order"] == []
        assert result["cycle_detected"] is False

    def test_none_dependency_graph_still_orders_deterministically(self):
        result = compute_rebuild_order(None, {"z", "a"})
        assert result["order"] == ["a", "z"]

    def test_cycle_is_detected_and_falls_back_to_sorted_order(self):
        graph = {
            "edges": [
                {"source_node_id": "a", "target_node_id": "b"},
                {"source_node_id": "b", "target_node_id": "a"},
            ],
        }
        result = compute_rebuild_order(graph, {"a", "b"})
        assert result["cycle_detected"] is True
        assert result["cycle_node_ids"] == ["a", "b"]
        assert result["order"] == ["a", "b"]

    def test_never_mutates_dependency_graph(self):
        graph = self._linear_graph()
        before = copy.deepcopy(graph)
        compute_rebuild_order(graph, {"a", "b", "c"})
        assert graph == before

    def test_result_is_deterministic_across_calls(self):
        graph = self._linear_graph()
        r1 = compute_rebuild_order(graph, {"a", "b", "c"})
        r2 = compute_rebuild_order(graph, {"a", "b", "c"})
        assert r1 == r2

    def test_synthetic_keys_absent_from_graph_are_treated_as_unconstrained(self):
        """Mirrors change_detection/snapshot.py's own "configuration"/
        "dependency_graph" synthetic artifact keys, which have no
        DependencyNode/edge of their own in Phase E2's graph -- module
        docstring's ARTIFACT KEYS NOT MODELED AS A DEPENDENCYNODE
        section."""
        graph = self._linear_graph()
        result = compute_rebuild_order(graph, {"a", "b", "c", "configuration"})
        assert set(result["order"]) == {"a", "b", "c", "configuration"}
        assert result["order"].index("a") < result["order"].index("b")
        assert result["order"].index("b") < result["order"].index("c")


# --------------------------------------------------------------------------
# 2. Minimal Rebuild Planner (hand-built ChangeDetectionReport shapes)
# --------------------------------------------------------------------------

class TestPlanRebuild:
    def _graph(self):
        # manifest <- readiness, manifest <- build_summary, statistics <- build_summary
        return {
            "nodes": [
                {"node_id": "manifest"}, {"node_id": "statistics"},
                {"node_id": "readiness"}, {"node_id": "build_summary"},
            ],
            "edges": [
                {"source_node_id": "readiness", "target_node_id": "manifest"},
                {"source_node_id": "build_summary", "target_node_id": "manifest"},
                {"source_node_id": "build_summary", "target_node_id": "statistics"},
            ],
        }

    def _report(self, **overrides):
        base = dict(
            has_previous_build=True,
            added_artifacts=[],
            removed_artifacts=[],
            modified_artifacts=[],
            affected_artifacts=[],
            unchanged_artifacts=[],
        )
        base.update(overrides)
        return base

    def test_no_change_build_has_empty_rebuild_set(self):
        report = self._report(
            unchanged_artifacts=["manifest", "statistics", "readiness", "build_summary"],
        )
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph(),
        )
        assert result["rebuild_artifacts"] == []
        assert result["rebuild_order"] == []
        assert result["clean_artifacts"] == ["build_summary", "manifest", "readiness", "statistics"]
        assert result["errors"] == []

    def test_single_artifact_change_marks_only_direct_dependents_affected(self):
        report = self._report(
            modified_artifacts=["manifest"],
            affected_artifacts=["readiness", "build_summary"],
            unchanged_artifacts=["statistics"],
        )
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph(),
        )
        assert result["dirty_artifacts"] == ["manifest"]
        assert result["rebuild_artifacts"] == ["build_summary", "manifest", "readiness"]
        assert result["rebuild_order"][0] == "manifest"
        assert result["rebuild_reasons"]["manifest"].startswith("modified")
        assert "manifest" in result["rebuild_reasons"]["readiness"]
        assert "manifest" in result["rebuild_reasons"]["build_summary"]
        assert result["clean_artifacts"] == ["statistics"]

    def test_multiple_artifact_changes_all_marked_dirty(self):
        report = self._report(
            modified_artifacts=["manifest", "statistics"],
            affected_artifacts=["readiness", "build_summary"],
        )
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph(),
        )
        assert result["dirty_artifacts"] == ["manifest", "statistics"]
        assert set(result["rebuild_artifacts"]) == {
            "manifest", "statistics", "readiness", "build_summary",
        }
        # manifest and statistics have no rebuilding predecessor of their
        # own -- both must be orderable before their dependents.
        order = result["rebuild_order"]
        assert order.index("manifest") < order.index("build_summary")
        assert order.index("statistics") < order.index("build_summary")

    def test_added_artifact_is_dirty_with_added_reason(self):
        report = self._report(has_previous_build=False, added_artifacts=["manifest"])
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph(),
        )
        assert result["dirty_artifacts"] == ["manifest"]
        assert result["rebuild_reasons"]["manifest"].startswith("added")

    def test_removed_artifact_is_surfaced_but_never_rebuilt(self):
        report = self._report(removed_artifacts=["old_artifact"])
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph(),
        )
        assert result["removed_artifacts"] == ["old_artifact"]
        assert "old_artifact" not in result["rebuild_artifacts"]
        assert "old_artifact" not in result["rebuild_order"]

    def test_first_build_everything_dirty_is_a_full_rebuild(self):
        report = self._report(
            has_previous_build=False,
            added_artifacts=["manifest", "statistics", "readiness", "build_summary"],
        )
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph(),
        )
        assert set(result["rebuild_artifacts"]) == {
            "manifest", "statistics", "readiness", "build_summary",
        }
        assert result["clean_artifacts"] == []

    def test_none_change_detection_report_degrades_to_empty_plan_with_warning(self):
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=None, dependency_graph=self._graph(),
        )
        assert result["rebuild_artifacts"] == []
        assert result["clean_artifacts"] == []
        assert any("no current ChangeDetectionReport" in w for w in result["warnings"])
        assert result["errors"] == []

    def test_malformed_change_detection_report_degrades_to_warning_not_exception(self):
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report={"not": "a report"},
            dependency_graph=self._graph(),
        )
        assert result["rebuild_artifacts"] == []
        assert any("change_detection_report" in w for w in result["warnings"])

    def test_none_dependency_graph_falls_back_to_sorted_order_with_warning(self):
        report = self._report(modified_artifacts=["manifest"], affected_artifacts=["readiness"])
        result = plan_rebuild(
            namespace=NAMESPACE, change_detection_report=report, dependency_graph=None,
        )
        assert result["rebuild_order"] == sorted(result["rebuild_artifacts"])
        assert any("no current DependencyGraph" in w for w in result["warnings"])

    def test_never_mutates_inputs(self):
        report = self._report(modified_artifacts=["manifest"], affected_artifacts=["readiness"])
        graph = self._graph()
        before_report, before_graph = copy.deepcopy(report), copy.deepcopy(graph)
        plan_rebuild(namespace=NAMESPACE, change_detection_report=report, dependency_graph=graph)
        assert report == before_report
        assert graph == before_graph

    def test_result_is_deterministic_across_calls(self):
        report = self._report(
            modified_artifacts=["manifest", "statistics"],
            affected_artifacts=["readiness", "build_summary"],
        )
        r1 = plan_rebuild(namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph())
        r2 = plan_rebuild(namespace=NAMESPACE, change_detection_report=report, dependency_graph=self._graph())
        assert r1 == r2


# --------------------------------------------------------------------------
# 3. Incremental Compilation Engine (full pipeline fixture)
# --------------------------------------------------------------------------

class TestPlanIncrementalCompilationEngine:
    def test_first_build_plans_a_full_rebuild(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state)
        plan = result["incremental_compilation_plan"]
        assert plan["has_previous_build"] is False
        assert len(plan["dirty_artifacts"]) > 0
        assert plan["clean_artifacts"] == []
        assert plan["removed_artifacts"] == []
        assert plan["summary"]["requires_rebuild"] is True
        assert plan["summary"]["is_full_rebuild"] is True

    def test_identical_second_build_plans_no_rebuild(self):
        state = build_full_pipeline_state()
        second_cdr = second_build_change_detection_report(state)
        state["change_detection_report"] = second_cdr["change_detection_report"]
        result = run_plan_incremental_compilation(state)
        plan = result["incremental_compilation_plan"]
        assert plan["has_previous_build"] is True
        assert plan["rebuild_artifacts"] == []
        assert plan["rebuild_order"] == []
        assert len(plan["clean_artifacts"]) > 0
        assert plan["summary"]["requires_rebuild"] is False

    def test_single_modified_artifact_produces_minimal_rebuild_set(self):
        state = build_full_pipeline_state()
        mutated_bm = copy.deepcopy(state["build_metadata"])
        mutated_bm["compiler_metadata"]["compiler_manifest"]["chapter_identifier"] = "changed"
        second_cdr = second_build_change_detection_report(state, mutated_build_metadata=mutated_bm)
        state["change_detection_report"] = second_cdr["change_detection_report"]
        result = run_plan_incremental_compilation(state, build_metadata=mutated_bm)
        plan = result["incremental_compilation_plan"]
        # Not every artifact needs rebuilding -- this is what makes it
        # "minimal": at minimum, some clean artifacts should remain.
        assert len(plan["rebuild_artifacts"]) < (
            len(plan["rebuild_artifacts"]) + len(plan["clean_artifacts"])
        )
        assert len(plan["clean_artifacts"]) > 0
        assert plan["summary"]["is_full_rebuild"] is False

    def test_plan_version_and_namespace(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state)
        plan = result["incremental_compilation_plan"]
        assert plan["namespace"] == NAMESPACE
        assert plan["incremental_compilation_plan_version"]
        assert INCREMENTAL_COMPILATION_VERSION

    def test_build_provenance_reused_verbatim_from_build_metadata(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state)
        plan = result["incremental_compilation_plan"]
        assert (
            plan["build_provenance"]["compiler_fingerprint"]
            == state["build_metadata"]["compiler_metadata"]["compiler_fingerprint"]
        )
        assert (
            plan["build_provenance"]["configuration_fingerprint"]
            == state["build_metadata"]["configuration_metadata"]["configuration_fingerprint"]
        )

    def test_none_build_metadata_yields_empty_provenance_not_fabricated(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state, build_metadata=None)
        assert result["incremental_compilation_plan"]["build_provenance"] == {}

    def test_rebuild_order_is_a_permutation_of_rebuild_artifacts(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state)
        plan = result["incremental_compilation_plan"]
        assert sorted(plan["rebuild_order"]) == sorted(plan["rebuild_artifacts"])

    def test_none_change_detection_report_surfaces_warning_at_engine_level(self):
        # Regression test: "E3 produced nothing this chapter" must be
        # distinguishable, via the plan's own `warnings`, from "E3 ran
        # and legitimately found no changes" (see
        # test_identical_second_build_plans_no_rebuild above, which
        # asserts the latter case produces an empty rebuild set with NO
        # such warning).
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state, change_detection_report=None)
        plan = result["incremental_compilation_plan"]
        assert plan["rebuild_artifacts"] == []
        assert plan["clean_artifacts"] == []
        assert any("no current ChangeDetectionReport" in w for w in plan["warnings"])

    def test_no_report_and_no_changes_are_distinguishable_by_warnings(self):
        # The two "nothing to rebuild" scenarios must not be
        # indistinguishable from a consumer's point of view.
        state = build_full_pipeline_state()

        no_report_result = run_plan_incremental_compilation(
            state, change_detection_report=None
        )
        no_report_plan = no_report_result["incremental_compilation_plan"]

        second_cdr = second_build_change_detection_report(state)
        state["change_detection_report"] = second_cdr["change_detection_report"]
        no_changes_result = run_plan_incremental_compilation(state)
        no_changes_plan = no_changes_result["incremental_compilation_plan"]

        assert no_report_plan["rebuild_artifacts"] == no_changes_plan["rebuild_artifacts"] == []
        assert any(
            "no current ChangeDetectionReport" in w for w in no_report_plan["warnings"]
        )
        assert not any(
            "no current ChangeDetectionReport" in w for w in no_changes_plan["warnings"]
        )


# --------------------------------------------------------------------------
# 4. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_produce_structurally_identical_plans(self):
        state = build_full_pipeline_state()
        r1 = run_plan_incremental_compilation(state)
        r2 = run_plan_incremental_compilation(state)
        plan_a = copy.deepcopy(r1["incremental_compilation_plan"])
        plan_b = copy.deepcopy(r2["incremental_compilation_plan"])
        plan_a.pop("generated_at")
        plan_b.pop("generated_at")
        assert plan_a == plan_b

    def test_rebuild_order_stable_across_runs(self):
        state = build_full_pipeline_state()
        r1 = run_plan_incremental_compilation(state)
        r2 = run_plan_incremental_compilation(state)
        assert (
            r1["incremental_compilation_plan"]["rebuild_order"]
            == r2["incremental_compilation_plan"]["rebuild_order"]
        )


# --------------------------------------------------------------------------
# 5. Read-only behaviour
# --------------------------------------------------------------------------

class TestReadOnlyBehaviour:
    def test_read_only_over_every_input(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy({
            k: v for k, v in state.items()
            if k not in ("compiler_registry_manager", "graph_registry_manager")
        })
        run_plan_incremental_compilation(state)
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
        run_plan_incremental_compilation(state)
        for name, size in compiler_sizes_before.items():
            assert state["compiler_registry_manager"].get(name).size() == size
        for name, size in graph_sizes_before.items():
            assert state["graph_registry_manager"].get(name).size() == size

    def test_never_mutates_change_detection_report_or_dependency_graph(self):
        state = build_full_pipeline_state()
        before_cdr = copy.deepcopy(state["change_detection_report"])
        before_dg = copy.deepcopy(state["dependency_graph"])
        run_plan_incremental_compilation(state)
        assert state["change_detection_report"] == before_cdr
        assert state["dependency_graph"] == before_dg


# --------------------------------------------------------------------------
# 6. State integration -- incremental_compilation.state
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_has_current_is_false_before_set(self):
        assert incremental_compilation_state.has_current_incremental_compilation_plan() is False
        assert incremental_compilation_state.get_current_incremental_compilation_plan() is None

    def test_set_then_get_returns_same_object(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state)
        incremental_compilation_state.set_current_incremental_compilation_plan(
            result["incremental_compilation_plan"]
        )
        assert incremental_compilation_state.has_current_incremental_compilation_plan() is True
        assert (
            incremental_compilation_state.get_current_incremental_compilation_plan()
            is result["incremental_compilation_plan"]
        )

    def test_reset_clears_state(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state)
        incremental_compilation_state.set_current_incremental_compilation_plan(
            result["incremental_compilation_plan"]
        )
        incremental_compilation_state.reset_incremental_compilation_state()
        assert incremental_compilation_state.has_current_incremental_compilation_plan() is False
        assert incremental_compilation_state.get_current_incremental_compilation_plan() is None


# --------------------------------------------------------------------------
# 7. Pipeline wiring
# --------------------------------------------------------------------------

class TestPipelineWiring:
    def test_pipeline_imports_incremental_compilation_integration_point(self):
        import pipeline
        assert hasattr(pipeline, "plan_incremental_compilation")
        assert hasattr(pipeline, "incremental_compilation_state")

    def test_process_chapter_source_calls_e4_after_e3(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e3_index = source.index("detect_changes(")
        e4_index = source.index("plan_incremental_compilation(")
        assert e3_index < e4_index, "Phase E4 must be called after Phase E3"

    def test_e4_call_site_never_touches_chapter_dict(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e4_index = source.index("plan_incremental_compilation(")
        chapter_dict_index = source.index("chapter_dict = json_writer.assemble_chapter_json(")
        between = source[e4_index:chapter_dict_index]
        assert "chapter_dict[" not in between
        assert "chapter_dict.update" not in between

    def test_e4_reuses_the_same_namespace_as_change_detection(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e4_call_start = source.index("plan_incremental_compilation(")
        e4_call_end = source.index(")", source.index("build_metadata=", e4_call_start))
        call_block = source[e4_call_start:e4_call_end]
        assert "namespace=chapter_reference" in call_block


# --------------------------------------------------------------------------
# 8. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_change_detection_state_untouched_by_e4(self):
        from change_detection import state as change_detection_state
        change_detection_state.reset_change_detection_state()
        assert change_detection_state.has_current_change_detection_report() is False
        state = build_full_pipeline_state()
        run_plan_incremental_compilation(state)
        # E4 never writes into change_detection.state -- only
        # pipeline.py's own E3 call site does, and this test never
        # called that.
        assert change_detection_state.has_current_change_detection_report() is False

    def test_change_detection_report_dict_unchanged_by_planning(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["change_detection_report"])
        run_plan_incremental_compilation(state)
        assert state["change_detection_report"] == before

    def test_dependency_graph_dict_unchanged_by_planning(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy(state["dependency_graph"])
        run_plan_incremental_compilation(state)
        assert state["dependency_graph"] == before

    def test_incremental_compilation_plan_is_a_plain_serializable_dict(self):
        state = build_full_pipeline_state()
        result = run_plan_incremental_compilation(state)
        import json
        json.dumps(result["incremental_compilation_plan"])  # must not raise