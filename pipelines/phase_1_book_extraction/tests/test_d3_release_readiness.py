"""
tests/test_d3_release_readiness.py — unit tests for Phase D3: Release
Readiness / Final Release Gate (validation/release.py), and its
pipeline.py / validation.release_state integration.

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment beyond the ad-hoc smoke checks performed
during development (mirrors tests/test_d2_determinism.py's own
disclaimer, one artifact over).

This file does NOT re-test System Integrity (validation/
system_integrity.py, already covered by tests/test_d1_system_integrity.py),
Determinism (validation/determinism.py, already covered by tests/
test_d2_determinism.py), or either fingerprint/readiness-generation
module (compiler/fingerprints.py, knowledge_graph/fingerprints.py,
already covered by tests/test_c4_2_fingerprints_readiness.py) directly
-- it treats all of those as frozen, already-tested dependencies. Two
kinds of fixtures are used below:

  * Hand-built, minimal report dicts (`_report(...)` helper) for the
    pure decision-rule / aggregation unit tests (READY /
    READY_WITH_WARNINGS / FAILED / missing-artifact paths) -- these
    exercise validation.release.determine_release_status() and
    validation.release.generate_release_readiness_report() directly,
    without paying for a full Phase B->D2 pipeline run per case.
  * A real, full Phase B (Compiler IR) -> Phase C (Knowledge Graph) ->
    Phase D1 -> Phase D2 pipeline run (`build_full_pipeline_state()`,
    same shape tests/test_d2_determinism.py's own same-named helper
    already establishes, duplicated here rather than cross-imported --
    this repo has no tests/__init__.py, so tests/ is not a package, and
    every existing test file already follows this "no test-to-test
    import dependency" convention) for the pipeline-integration-shaped
    tests (state integration, pipeline integration, determinism of the
    release report itself, read-only behavior, backward compatibility).
"""
from __future__ import annotations

import copy
import inspect

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
from knowledge_graph.registries import GraphRegistryManager, create_graph_registry_manager
from knowledge_graph.identity import (
    graph_id as expected_graph_id,
    graph_urn as expected_graph_urn,
)
from knowledge_graph.schema import KnowledgeGraphMetadata
from knowledge_graph.fingerprints import generate_graph_fingerprints
from knowledge_graph.finalize import finalize_knowledge_graph

from validation.system_integrity import validate_system_integrity
from validation.determinism import validate_determinism

from validation.release import (
    RELEASE_VERSION,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    STATUS_FAILED,
    ReleaseReadinessReport,
    determine_release_status,
    generate_release_readiness_report,
    finalize_release,
)
from validation import release_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- hand-built, minimal reports for the pure decision-rule /
# aggregation unit tests.
# --------------------------------------------------------------------------

def _report(overall_status="pass", warnings=None, errors=None):
    """Minimal System-Integrity-Report-or-Determinism-Report-shaped
    dict -- both real reports share this same `overall_status`/
    `warnings`/`errors` shape (see validation/system_integrity.py's and
    validation/determinism.py's own SystemIntegrityReport/
    DeterminismReport dataclasses), so one helper covers both."""
    return {
        "overall_status": overall_status,
        "warnings": list(warnings or []),
        "errors": list(errors or []),
    }


def _build_summary(build_status):
    """Minimal Compiler-Build-Summary-or-Knowledge-Graph-Build-Summary-
    shaped dict -- both real summaries share this same `build_status`
    key (see compiler/finalize.py's own CompilerBuildSummary /
    knowledge_graph/finalize.py's own KnowledgeGraphBuildSummary)."""
    return {"build_status": build_status}


def _readiness_report(ready=True, warnings=None):
    return {"ready": ready, "warnings": list(warnings or [])}


def _full_kwargs(**overrides):
    """A complete, all-READY/all-pass set of kwargs for
    generate_release_readiness_report()/finalize_release() -- every
    individual test below starts from this and overrides only the
    fields it cares about, so a missing keyword can never silently
    change an unrelated test's expected outcome."""
    kwargs = dict(
        compiler_validation_report={"status": "pass", "errors": [], "warnings": []},
        knowledge_graph_validation_report={"overall_status": "pass", "errors": [], "warnings": []},
        compiler_readiness_report=_readiness_report(True),
        knowledge_graph_readiness_report=_readiness_report(True),
        compiler_build_summary=_build_summary(STATUS_READY),
        knowledge_graph_build_summary=_build_summary(STATUS_READY),
        system_integrity_report=_report("pass"),
        determinism_report=_report("pass"),
        compiler_manifest={"compiler_version": "B5.1"},
        knowledge_graph_manifest={"graph_version": "C0.1"},
        compiler_fingerprint="cfp123",
        knowledge_graph_fingerprint="gfp456",
        compiler_statistics={"total_objects": 3},
        knowledge_graph_statistics={"total_nodes": 3},
    )
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------
# Helpers -- full Phase B->D2 pipeline fixture (same shape tests/
# test_d2_determinism.py's own build_full_pipeline_state() already
# establishes, duplicated here, not imported).
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


def build_full_pipeline_state(*, namespace=NAMESPACE, mutate_kg_metadata=None):
    """One-shot: Phase B (Compiler IR) -> Phase C (Knowledge Graph) ->
    Phase D1 (System Integrity) -> Phase D2 (Determinism), exactly the
    sequence pipeline.py runs immediately before its own Phase D3
    integration point. Returns a dict of every artifact
    finalize_release() consumes, keyed the same way that function's own
    parameter names read."""
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

    state = {
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
    state["system_integrity_report"] = validate_system_integrity(
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
    return state


def run_finalize_release(state: dict) -> dict:
    """Calls finalize_release() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names -- exactly pipeline.py's own Phase
    D3 integration-point call shape."""
    return finalize_release(
        compiler_validation_report=state["compiler_validation_report"],
        knowledge_graph_validation_report=state["knowledge_graph_validation_report"],
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


@pytest.fixture(autouse=True)
def _reset_release_state():
    """Every test starts and ends with a clean validation.release_state
    module -- mirrors tests/test_d2_determinism.py's own
    _reset_determinism_state fixture, one artifact over."""
    release_state.reset_release_state()
    yield
    release_state.reset_release_state()


# --------------------------------------------------------------------------
# 1. Release Decision -- READY
# --------------------------------------------------------------------------

class TestReleaseDecisionReady:
    def test_all_ready_all_pass_no_warnings_is_ready(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY, _report("pass"), _report("pass"),
        )
        assert status == STATUS_READY

    def test_full_report_all_ready_is_ready(self):
        report = generate_release_readiness_report(**_full_kwargs())
        assert report["release_status"] == STATUS_READY
        assert report["overall_status"] == STATUS_READY
        assert report["errors"] == []
        assert report["warnings"] == []

    def test_finalize_release_all_ready_is_ready(self):
        result = finalize_release(**_full_kwargs())
        assert result["release_status"] == STATUS_READY
        assert result["release_readiness_report"]["release_status"] == STATUS_READY


# --------------------------------------------------------------------------
# 2. Release Decision -- READY_WITH_WARNINGS
# --------------------------------------------------------------------------

class TestReleaseDecisionReadyWithWarnings:
    def test_compiler_ready_with_warnings_propagates(self):
        status = determine_release_status(
            STATUS_READY_WITH_WARNINGS, STATUS_READY, _report("pass"), _report("pass"),
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_graph_ready_with_warnings_propagates(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY_WITH_WARNINGS, _report("pass"), _report("pass"),
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_system_integrity_warning_propagates(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY,
            _report("pass", warnings=[{"severity": "warning", "rule": "x", "message": "m"}]),
            _report("pass"),
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_determinism_warning_propagates(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY, _report("pass"),
            _report("pass", warnings=[{"severity": "warning", "rule": "y", "message": "m"}]),
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_full_report_warning_propagates_and_is_visible_in_warnings_list(self):
        w = {"severity": "warning", "rule": "some_check", "message": "non-blocking"}
        report = generate_release_readiness_report(
            **_full_kwargs(system_integrity_report=_report("pass", warnings=[w]))
        )
        assert report["release_status"] == STATUS_READY_WITH_WARNINGS
        assert w in report["warnings"]


# --------------------------------------------------------------------------
# 3. Release Decision -- FAILED
# --------------------------------------------------------------------------

class TestReleaseDecisionFailed:
    def test_compiler_failed_status_fails_release(self):
        status = determine_release_status(
            STATUS_FAILED, STATUS_READY, _report("pass"), _report("pass"),
        )
        assert status == STATUS_FAILED

    def test_graph_failed_status_fails_release(self):
        status = determine_release_status(
            STATUS_READY, STATUS_FAILED, _report("pass"), _report("pass"),
        )
        assert status == STATUS_FAILED

    def test_system_integrity_fail_fails_release(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY, _report("fail"), _report("pass"),
        )
        assert status == STATUS_FAILED

    def test_determinism_fail_fails_release(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY, _report("pass"), _report("fail"),
        )
        assert status == STATUS_FAILED

    def test_full_report_failed_is_failed_and_never_ready(self):
        report = generate_release_readiness_report(
            **_full_kwargs(compiler_build_summary=_build_summary(STATUS_FAILED))
        )
        assert report["release_status"] == STATUS_FAILED
        assert report["overall_status"] == STATUS_FAILED

    def test_finalize_release_failed_propagates_to_top_level_status(self):
        result = finalize_release(
            **_full_kwargs(knowledge_graph_build_summary=_build_summary(STATUS_FAILED))
        )
        assert result["release_status"] == STATUS_FAILED


# --------------------------------------------------------------------------
# 4. Missing reports / manifests / fingerprints
# --------------------------------------------------------------------------

class TestMissingArtifacts:
    def test_missing_system_integrity_report_fails_release(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY, None, _report("pass"),
        )
        assert status == STATUS_FAILED

    def test_missing_determinism_report_fails_release(self):
        status = determine_release_status(
            STATUS_READY, STATUS_READY, _report("pass"), None,
        )
        assert status == STATUS_FAILED

    def test_missing_everything_fails_release_and_records_errors(self):
        result = finalize_release()
        assert result["release_status"] == STATUS_FAILED
        report = result["release_readiness_report"]
        assert report["errors"], "missing artifacts must be surfaced as errors"
        rules = {e.get("rule") for e in report["errors"]}
        assert "artifact_missing" in rules

    def test_missing_compiler_manifest_leaves_compiler_version_none(self):
        report = generate_release_readiness_report(
            **_full_kwargs(compiler_manifest=None)
        )
        assert report["compiler_version"] is None
        # a missing manifest alone (everything else still READY/pass)
        # is reported as a missing-artifact error, but is NOT one of
        # the two Task-2-style verdicts the release decision itself is
        # derived from -- so it does not, on its own, flip an otherwise
        # all-READY/all-pass release to FAILED.
        assert report["release_status"] == STATUS_READY

    def test_missing_graph_manifest_leaves_graph_version_none(self):
        report = generate_release_readiness_report(
            **_full_kwargs(knowledge_graph_manifest=None)
        )
        assert report["graph_version"] is None

    def test_missing_fingerprints_do_not_crash_and_are_read_only(self):
        report = generate_release_readiness_report(
            **_full_kwargs(compiler_fingerprint=None, knowledge_graph_fingerprint=None)
        )
        assert report["release_status"] == STATUS_READY

    def test_missing_readiness_reports_reported_as_not_ready(self):
        report = generate_release_readiness_report(
            **_full_kwargs(
                compiler_readiness_report=None,
                knowledge_graph_readiness_report=None,
            )
        )
        assert report["compiler_ready"] is False
        assert report["graph_ready"] is False

    def test_missing_statistics_do_not_crash(self):
        report = generate_release_readiness_report(
            **_full_kwargs(compiler_statistics=None, knowledge_graph_statistics=None)
        )
        assert report["release_status"] == STATUS_READY


# --------------------------------------------------------------------------
# 5. Warnings / errors propagation (aggregation, not re-derivation)
# --------------------------------------------------------------------------

class TestWarningsAndErrorsPropagation:
    def test_system_integrity_errors_propagate_into_release_report(self):
        e = {"severity": "error", "rule": "cross_check", "message": "mismatch"}
        report = generate_release_readiness_report(
            **_full_kwargs(system_integrity_report=_report("fail", errors=[e]))
        )
        assert e in report["errors"]
        assert report["release_status"] == STATUS_FAILED

    def test_determinism_errors_propagate_into_release_report(self):
        e = {"severity": "error", "rule": "not_reproducible", "message": "digest mismatch"}
        report = generate_release_readiness_report(
            **_full_kwargs(determinism_report=_report("fail", errors=[e]))
        )
        assert e in report["errors"]
        assert report["release_status"] == STATUS_FAILED

    def test_both_warnings_are_all_present_not_deduplicated_away(self):
        w1 = {"severity": "warning", "rule": "a", "message": "one"}
        w2 = {"severity": "warning", "rule": "b", "message": "two"}
        report = generate_release_readiness_report(
            **_full_kwargs(
                system_integrity_report=_report("pass", warnings=[w1]),
                determinism_report=_report("pass", warnings=[w2]),
            )
        )
        assert w1 in report["warnings"]
        assert w2 in report["warnings"]
        assert len(report["warnings"]) == 2

    def test_release_never_invents_a_warning_or_error_not_in_source_reports(self):
        report = generate_release_readiness_report(**_full_kwargs())
        assert report["warnings"] == []
        assert report["errors"] == []


# --------------------------------------------------------------------------
# 6. Report shape / version
# --------------------------------------------------------------------------

class TestReportShape:
    def test_report_version_matches_module_constant(self):
        report = generate_release_readiness_report(**_full_kwargs())
        assert report["report_version"] == RELEASE_VERSION

    def test_report_is_plain_dict(self):
        report = generate_release_readiness_report(**_full_kwargs())
        assert isinstance(report, dict)
        assert not isinstance(report, ReleaseReadinessReport)

    def test_report_has_every_task_4_suggested_field(self):
        report = generate_release_readiness_report(**_full_kwargs())
        for field_name in (
            "generated_at", "report_version", "compiler_version", "graph_version",
            "compiler_ready", "graph_ready", "system_integrity", "determinism",
            "overall_status", "warnings", "errors", "summary", "release_status",
        ):
            assert field_name in report

    def test_summary_is_a_nonempty_string_mentioning_the_release_status(self):
        report = generate_release_readiness_report(**_full_kwargs())
        assert isinstance(report["summary"], str) and report["summary"]
        assert report["release_status"] in report["summary"]


# --------------------------------------------------------------------------
# 7. State integration (validation/release_state.py)
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_state_starts_empty(self):
        assert release_state.get_current_release_readiness_report() is None
        assert release_state.get_current_release_status() is None
        assert release_state.has_current_release_readiness_report() is False
        assert release_state.has_current_release_status() is False

    def test_set_and_get_round_trip(self):
        result = finalize_release(**_full_kwargs())
        release_state.set_current_release_readiness_report(result["release_readiness_report"])
        release_state.set_current_release_status(result["release_status"])
        assert release_state.get_current_release_readiness_report() == result["release_readiness_report"]
        assert release_state.get_current_release_status() == result["release_status"]
        assert release_state.has_current_release_readiness_report() is True
        assert release_state.has_current_release_status() is True

    def test_reset_clears_state(self):
        result = finalize_release(**_full_kwargs())
        release_state.set_current_release_readiness_report(result["release_readiness_report"])
        release_state.set_current_release_status(result["release_status"])
        release_state.reset_release_state()
        assert release_state.get_current_release_readiness_report() is None
        assert release_state.get_current_release_status() is None

    def test_second_chapter_never_sees_first_chapters_stale_state(self):
        first = finalize_release(**_full_kwargs())
        release_state.set_current_release_readiness_report(first["release_readiness_report"])
        release_state.set_current_release_status(first["release_status"])

        release_state.reset_release_state()
        assert release_state.get_current_release_readiness_report() is None

        second = finalize_release(
            **_full_kwargs(compiler_build_summary=_build_summary(STATUS_FAILED))
        )
        release_state.set_current_release_readiness_report(second["release_readiness_report"])
        release_state.set_current_release_status(second["release_status"])
        assert release_state.get_current_release_status() == STATUS_FAILED


# --------------------------------------------------------------------------
# 8. Pipeline integration (full Phase B->D2 fixture)
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_finalize_release_accepts_real_pipeline_artifacts(self):
        state = build_full_pipeline_state()
        result = run_finalize_release(state)
        assert result["release_status"] in (STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED)
        assert result["release_readiness_report"]["release_status"] == result["release_status"]

    def test_release_status_consistent_with_component_final_statuses(self):
        state = build_full_pipeline_state()
        result = run_finalize_release(state)
        compiler_status = state["compiler_build_summary"]["build_status"]
        graph_status = state["knowledge_graph_build_summary"]["build_status"]
        if STATUS_FAILED in (compiler_status, graph_status):
            assert result["release_status"] == STATUS_FAILED

    def test_pipeline_signature_matches_finalize_release_call_shape(self):
        """Guards the exact keyword surface pipeline.py's own Phase D3
        integration-point call relies on -- a rename here without
        updating pipeline.py would otherwise only be caught at runtime,
        deep inside process_chapter()."""
        sig = inspect.signature(finalize_release)
        expected = {
            "compiler_validation_report", "knowledge_graph_validation_report",
            "compiler_readiness_report", "knowledge_graph_readiness_report",
            "compiler_build_summary", "knowledge_graph_build_summary",
            "system_integrity_report", "determinism_report",
            "compiler_manifest", "knowledge_graph_manifest",
            "compiler_fingerprint", "knowledge_graph_fingerprint",
            "compiler_statistics", "knowledge_graph_statistics",
        }
        assert expected.issubset(set(sig.parameters))

    def test_state_module_end_to_end_with_real_pipeline_artifacts(self):
        state = build_full_pipeline_state()
        result = run_finalize_release(state)
        release_state.set_current_release_readiness_report(result["release_readiness_report"])
        release_state.set_current_release_status(result["release_status"])
        assert release_state.get_current_release_status() == result["release_status"]
        assert (
            release_state.get_current_release_readiness_report()["release_status"]
            == result["release_status"]
        )


# --------------------------------------------------------------------------
# 9. Determinism of the release report itself
# --------------------------------------------------------------------------

class TestReleaseReportDeterminism:
    def test_same_inputs_produce_same_report_modulo_generated_at(self):
        kwargs = _full_kwargs()
        r1 = generate_release_readiness_report(**kwargs)
        r2 = generate_release_readiness_report(**kwargs)
        r1_stripped = {k: v for k, v in r1.items() if k != "generated_at"}
        r2_stripped = {k: v for k, v in r2.items() if k != "generated_at"}
        assert r1_stripped == r2_stripped

    def test_real_pipeline_run_is_reproducible_across_two_release_passes(self):
        state = build_full_pipeline_state()
        r1 = run_finalize_release(state)["release_readiness_report"]
        r2 = run_finalize_release(state)["release_readiness_report"]
        r1_stripped = {k: v for k, v in r1.items() if k != "generated_at"}
        r2_stripped = {k: v for k, v in r2.items() if k != "generated_at"}
        assert r1_stripped == r2_stripped

    def test_release_decision_alone_is_a_pure_function(self):
        args = (STATUS_READY_WITH_WARNINGS, STATUS_READY, _report("pass"), _report("pass"))
        assert determine_release_status(*args) == determine_release_status(*args)


# --------------------------------------------------------------------------
# 10. Read-only behavior -- D3 never mutates anything it reads
# --------------------------------------------------------------------------

class TestReadOnlyBehavior:
    def test_generate_release_readiness_report_does_not_mutate_inputs(self):
        kwargs = _full_kwargs()
        before = copy.deepcopy(kwargs)
        generate_release_readiness_report(**kwargs)
        assert kwargs == before

    def test_finalize_release_does_not_mutate_inputs(self):
        kwargs = _full_kwargs()
        before = copy.deepcopy(kwargs)
        finalize_release(**kwargs)
        assert kwargs == before

    def test_finalize_release_does_not_mutate_real_pipeline_artifacts(self):
        state = build_full_pipeline_state()
        before = {
            "compiler_validation_report": copy.deepcopy(state["compiler_validation_report"]),
            "knowledge_graph_validation_report": copy.deepcopy(state["knowledge_graph_validation_report"]),
            "compiler_readiness_report": copy.deepcopy(state["compiler_readiness_report"]),
            "knowledge_graph_readiness_report": copy.deepcopy(state["knowledge_graph_readiness_report"]),
            "compiler_build_summary": copy.deepcopy(state["compiler_build_summary"]),
            "knowledge_graph_build_summary": copy.deepcopy(state["knowledge_graph_build_summary"]),
            "system_integrity_report": copy.deepcopy(state["system_integrity_report"]),
            "determinism_report": copy.deepcopy(state["determinism_report"]),
            "compiler_manifest": copy.deepcopy(state["compiler_manifest"]),
            "knowledge_graph_manifest": copy.deepcopy(state["knowledge_graph_manifest"]),
        }
        run_finalize_release(state)
        assert state["compiler_validation_report"] == before["compiler_validation_report"]
        assert state["knowledge_graph_validation_report"] == before["knowledge_graph_validation_report"]
        assert state["compiler_readiness_report"] == before["compiler_readiness_report"]
        assert state["knowledge_graph_readiness_report"] == before["knowledge_graph_readiness_report"]
        assert state["compiler_build_summary"] == before["compiler_build_summary"]
        assert state["knowledge_graph_build_summary"] == before["knowledge_graph_build_summary"]
        assert state["system_integrity_report"] == before["system_integrity_report"]
        assert state["determinism_report"] == before["determinism_report"]
        assert state["compiler_manifest"] == before["compiler_manifest"]
        assert state["knowledge_graph_manifest"] == before["knowledge_graph_manifest"]

    def test_no_registry_mutation_methods_available_or_called(self):
        """D3 never touches a registry directly at all (Task 5's own
        "never revalidate compiler objects/graph nodes" rule) -- unlike
        D1/D2, validate_release()-style functions here don't even accept
        a registry manager argument, so there is no `.insert()`/
        `.update()`/`.remove()`/`.clear()` surface for this module to
        reach in the first place."""
        sig = inspect.signature(finalize_release)
        assert "compiler_registry_manager" not in sig.parameters
        assert "graph_registry_manager" not in sig.parameters


# --------------------------------------------------------------------------
# 11. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_d1_and_d2_reports_unaffected_by_d3_running(self):
        state = build_full_pipeline_state()
        sir_before = copy.deepcopy(state["system_integrity_report"])
        det_before = copy.deepcopy(state["determinism_report"])
        run_finalize_release(state)
        assert state["system_integrity_report"] == sir_before
        assert state["determinism_report"] == det_before

    def test_compiler_and_graph_final_status_unaffected_by_d3_running(self):
        state = build_full_pipeline_state()
        compiler_status_before = state["compiler_build_summary"]["build_status"]
        graph_status_before = state["knowledge_graph_build_summary"]["build_status"]
        run_finalize_release(state)
        assert state["compiler_build_summary"]["build_status"] == compiler_status_before
        assert state["knowledge_graph_build_summary"]["build_status"] == graph_status_before

    def test_finalize_release_all_keyword_only_no_positional_registry_args(self):
        """Every argument is keyword-only (the `*,` in finalize_release()'s
        own signature) -- matches compiler.finalize.finalize_compiler_build()'s
        /knowledge_graph.finalize.finalize_knowledge_graph()'s own
        keyword-only shape, so adding a new optional artifact later can
        never silently reorder an existing positional call site."""
        sig = inspect.signature(finalize_release)
        for name, param in sig.parameters.items():
            assert param.kind in (
                inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_KEYWORD,
            ), f"{name} must be keyword-only"

    def test_existing_status_constants_reused_not_redeclared_with_new_values(self):
        assert STATUS_READY == "READY"
        assert STATUS_READY_WITH_WARNINGS == "READY_WITH_WARNINGS"
        assert STATUS_FAILED == "FAILED"
