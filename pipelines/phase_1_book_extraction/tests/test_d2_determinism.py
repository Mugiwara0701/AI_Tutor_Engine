"""
tests/test_d2_determinism.py — unit tests for Phase D2: Determinism &
Reproducibility Validation (validation/determinism.py), and its
pipeline.py / validation.determinism_state integration.

Per task instructions ("Generate tests only. Do NOT execute them."),
these tests are generated only: they are not executed here as part of
authoring them, and no claim is made about whether they currently pass
in the caller's environment beyond the ad-hoc smoke checks performed
during development (mirrors tests/test_d1_system_integrity.py's own
disclaimer, one artifact over).

This file does NOT re-test System Integrity (validation/
system_integrity.py, already covered by tests/test_d1_system_integrity.py)
or either fingerprint-generation module (compiler/fingerprints.py,
knowledge_graph/fingerprints.py, already covered by tests/
test_c4_2_fingerprints_readiness.py) directly -- it treats all three as
frozen, already-tested dependencies. The fixture-building helpers below
(make_item / make_relationship_ready_manager / build_full_pipeline_state
/ run_validate_system_integrity) are the SAME shape tests/
test_d1_system_integrity.py's own helpers already establish, duplicated
here (not imported) rather than cross-imported from that file's own
module -- this repo has no tests/__init__.py, so tests/ is not a
package, and every existing test file (see tests/
test_d1_system_integrity.py's own "Helpers" comment, tests/
test_c4_3_finalization.py's own make_item/make_relationship_ready_
manager) already follows this exact "no test-to-test import
dependency" convention rather than relying on pytest's rootdir-
insertion import mechanics to resolve a `tests.something` module path.
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

from validation.system_integrity import validate_system_integrity
from validation.determinism import (
    DETERMINISM_VERSION,
    DeterminismReport,
    validate_determinism,
)
from validation import determinism_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- same canonical-enveloped item shape / same full-pipeline-
# state builder tests/test_d1_system_integrity.py's own make_item/
# make_relationship_ready_manager/build_full_pipeline_state already
# establish, duplicated here (not imported) so this file has no test-
# to-test import dependency -- see module docstring above.
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
    """One-shot: Phase B (Compiler IR) -> Phase C (Knowledge Graph) ->
    Phase D1 (System Integrity), exactly the sequence pipeline.py runs
    immediately before its own Phase D2 integration point. Returns a
    dict of every artifact validate_determinism() consumes, keyed the
    same way that function's own parameter names read, plus the D1
    System Integrity Report under "system_integrity_report" (D2's own
    eleventh named artifact -- see validation/determinism.py's own
    module docstring)."""
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
    state["system_integrity_report"] = run_validate_system_integrity(state)
    return state


def run_validate_system_integrity(state: dict) -> dict:
    """Calls validate_system_integrity() with every artifact
    build_full_pipeline_state() has produced so far, keyword-mapped
    onto that function's own parameter names -- same shape tests/
    test_d1_system_integrity.py's own same-named helper already
    establishes."""
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


def run_validate_determinism(state: dict, *, system_integrity_report=...) -> dict:
    """Calls validate_determinism() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names. `system_integrity_report` defaults
    to whatever build_full_pipeline_state() itself computed
    (state["system_integrity_report"]); pass None explicitly (not the
    default sentinel) to exercise D2's own "no D1 report supplied"
    path."""
    sir = state.get("system_integrity_report") if system_integrity_report is ... else system_integrity_report
    return validate_determinism(
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
        system_integrity_report=sir,
    )


def build_state_with_system_integrity(**kwargs):
    """Back-compat alias: build_full_pipeline_state() already computes
    and attaches its own system_integrity_report (see above). Returns
    the (state, system_integrity_report) pair the rest of this file's
    test bodies expect."""
    state = build_full_pipeline_state(**kwargs)
    return state, state["system_integrity_report"]


@pytest.fixture(autouse=True)
def _reset_determinism_state():
    """Every test starts and ends with a clean validation.
    determinism_state module -- mirrors tests/test_d1_system_integrity.py's
    own _reset_system_integrity_state fixture, one artifact over."""
    determinism_state.reset_determinism_state()
    yield
    determinism_state.reset_determinism_state()


# --------------------------------------------------------------------------
# 1. Identical compiler runs -- registry/compiler fingerprint
#    reproducibility
# --------------------------------------------------------------------------

class TestIdenticalCompilerRuns:
    def test_valid_pipeline_output_passes(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "pass"
        assert report["errors"] == []

    def test_compiler_registry_fingerprints_reproducible_check_present(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert "compiler_registry_fingerprints_reproducible" in report["checks_passed"]

    def test_compiler_fingerprint_reproducible_check_present(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert "compiler_fingerprint_reproducible" in report["checks_passed"]

    def test_tampered_compiler_fingerprint_is_caught(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["compiler_fingerprint"] = "0" * 64
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        assert "compiler_fingerprint_matches_supplied" in report["checks_failed"]

    def test_tampered_compiler_registry_fingerprints_are_caught(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        mutated = dict(state["compiler_registry_fingerprints"])
        first_key = next(iter(mutated))
        mutated[first_key] = "0" * 64
        state["compiler_registry_fingerprints"] = mutated
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        assert "compiler_registry_fingerprints_match_supplied" in report["checks_failed"]


# --------------------------------------------------------------------------
# 2. Identical graph runs -- graph registry/fingerprint reproducibility
# --------------------------------------------------------------------------

class TestIdenticalGraphRuns:
    def test_graph_registry_fingerprints_reproducible_check_present(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert "graph_registry_fingerprints_reproducible" in report["checks_passed"]

    def test_graph_fingerprint_reproducible_check_present(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert "graph_fingerprint_reproducible" in report["checks_passed"]

    def test_tampered_graph_fingerprint_is_caught(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["knowledge_graph_fingerprint"] = "0" * 64
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        assert "graph_fingerprint_matches_supplied" in report["checks_failed"]

    def test_tampered_graph_registry_fingerprints_are_caught(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        mutated = dict(state["knowledge_graph_registry_fingerprints"])
        first_key = next(iter(mutated))
        mutated[first_key] = "0" * 64
        state["knowledge_graph_registry_fingerprints"] = mutated
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        assert "graph_registry_fingerprints_match_supplied" in report["checks_failed"]


# --------------------------------------------------------------------------
# 3. Fingerprint determinism -- missing/None fingerprints are warned about,
#    never silently treated as passing
# --------------------------------------------------------------------------

class TestFingerprintDeterminism:
    def test_missing_compiler_fingerprint_is_a_warning_not_a_silent_pass(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["compiler_fingerprint"] = None
        state["compiler_registry_fingerprints"] = None
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert any(w["rule"] == "compiler_fingerprint_missing" for w in report["warnings"])
        assert "compiler_fingerprint_matches_supplied" not in report["checks_passed"]
        assert "compiler_fingerprint_matches_supplied" not in report["checks_failed"]
        # Reproducibility itself is still checked even with nothing to compare against.
        assert "compiler_fingerprint_reproducible" in report["checks_passed"]

    def test_missing_graph_fingerprint_is_a_warning_not_a_silent_pass(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["knowledge_graph_fingerprint"] = None
        state["knowledge_graph_registry_fingerprints"] = None
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert any(w["rule"] == "graph_fingerprint_missing" for w in report["warnings"])
        assert "graph_fingerprint_matches_supplied" not in report["checks_passed"]
        assert "graph_fingerprint_matches_supplied" not in report["checks_failed"]


# --------------------------------------------------------------------------
# 4. Manifest determinism -- key-order independence
# --------------------------------------------------------------------------

class TestManifestDeterminism:
    def test_compiler_manifest_key_order_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["manifest_determinism"]["compiler_manifest_key_order_independent"] is True

    def test_graph_manifest_key_order_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["manifest_determinism"]["graph_manifest_key_order_independent"] is True

    def test_missing_compiler_manifest_is_an_error(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["compiler_manifest"] = None
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        assert any(e["rule"] == "compiler_manifest_missing" for e in report["errors"])

    def test_missing_graph_manifest_is_an_error(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["knowledge_graph_manifest"] = None
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        assert any(e["rule"] == "graph_manifest_missing" for e in report["errors"])


# --------------------------------------------------------------------------
# 5. Statistics determinism -- key-order independence
# --------------------------------------------------------------------------

class TestStatisticsDeterminism:
    def test_compiler_statistics_key_order_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["statistics_determinism"]["compiler_statistics_key_order_independent"] is True

    def test_graph_statistics_key_order_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["statistics_determinism"]["graph_statistics_key_order_independent"] is True

    def test_missing_statistics_are_errors(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["compiler_statistics"] = None
        state["knowledge_graph_statistics"] = None
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        rules = {e["rule"] for e in report["errors"]}
        assert "compiler_statistics_missing" in rules
        assert "graph_statistics_missing" in rules


# --------------------------------------------------------------------------
# 6. Ordering determinism -- registry name / node / edge ordering
# --------------------------------------------------------------------------

class TestOrderingDeterminism:
    def test_compiler_registry_name_ordering_stable(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["ordering_determinism"]["compiler_registry_name_ordering_stable"] is True

    def test_graph_registry_name_ordering_stable(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["ordering_determinism"]["graph_registry_name_ordering_stable"] is True

    def test_node_ordering_stable(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["ordering_determinism"]["node_ordering_stable"] is True

    def test_edge_ordering_stable(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["ordering_determinism"]["edge_ordering_stable"] is True

    def test_compiler_registry_serialization_stable(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["ordering_determinism"]["compiler_registry_serialization_stable"] is True
        assert report["ordering_determinism"]["unstable_compiler_registries"] == []

    def test_graph_registry_serialization_stable(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["ordering_determinism"]["graph_registry_serialization_stable"] is True
        assert report["ordering_determinism"]["unstable_graph_registries"] == []


# --------------------------------------------------------------------------
# 7. Timestamp exclusion -- fingerprints must not change when a volatile
#    (timestamp-shaped) field does
# --------------------------------------------------------------------------

class TestTimestampExclusion:
    def test_compiler_fingerprint_is_timestamp_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["fingerprint_determinism"]["compiler_fingerprint_timestamp_independent"] is True
        assert "compiler_fingerprint_timestamp_independent" in report["checks_passed"]

    def test_graph_fingerprint_is_timestamp_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["fingerprint_determinism"]["graph_fingerprint_timestamp_independent"] is True
        assert "graph_fingerprint_timestamp_independent" in report["checks_passed"]

    def test_mutating_manifest_generated_at_does_not_change_recomputed_fingerprint(self):
        """Directly exercises the same property the module's own
        _check uses internally, from the outside: two manifests
        differing ONLY in a volatile field must fingerprint identically
        via the frozen compiler.fingerprints.generate_compiler_fingerprint()."""
        state, _ = build_state_with_system_integrity()
        from compiler.fingerprints import generate_compiler_fingerprint

        mutated_manifest = copy.deepcopy(state["compiler_manifest"])
        mutated_manifest["generated_at"] = "1999-01-01T00:00:00+00:00"
        original_fp = generate_compiler_fingerprint(
            state["compiler_registry_fingerprints"], state["compiler_manifest"], state["compiler_statistics"],
        )
        mutated_fp = generate_compiler_fingerprint(
            state["compiler_registry_fingerprints"], mutated_manifest, state["compiler_statistics"],
        )
        assert original_fp == mutated_fp


# --------------------------------------------------------------------------
# 8. Build summary determinism
# --------------------------------------------------------------------------

class TestBuildSummaryDeterminism:
    def test_compiler_build_summary_key_order_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["build_summary_determinism"]["compiler_build_summary_key_order_independent"] is True

    def test_graph_build_summary_key_order_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["build_summary_determinism"]["graph_build_summary_key_order_independent"] is True

    def test_build_summary_fingerprint_consistency_checked(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["build_summary_determinism"]["compiler_build_summary_fingerprint_consistent"] is True
        assert report["build_summary_determinism"]["graph_build_summary_fingerprint_consistent"] is True

    def test_missing_build_summaries_are_errors(self):
        state, sir = build_state_with_system_integrity()
        state = dict(state)
        state["compiler_build_summary"] = None
        state["knowledge_graph_build_summary"] = None
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["overall_status"] == "fail"
        rules = {e["rule"] for e in report["errors"]}
        assert "compiler_build_summary_missing" in rules
        assert "graph_build_summary_missing" in rules


# --------------------------------------------------------------------------
# 9. System Integrity Report determinism (Task 3's own eleventh artifact)
# --------------------------------------------------------------------------

class TestSystemIntegrityReportDeterminism:
    def test_system_integrity_report_key_order_independent(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["system_integrity_determinism"]["system_integrity_report_key_order_independent"] is True

    def test_missing_system_integrity_report_is_a_warning_not_an_error(self):
        state, _ = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=None)
        assert report["system_integrity_determinism"]["system_integrity_report_present"] is False
        assert any(w["rule"] == "system_integrity_report_not_supplied" for w in report["warnings"])
        assert not any(e["rule"].startswith("system_integrity_report") for e in report["errors"])


# --------------------------------------------------------------------------
# 10. Determinism of validate_determinism() itself, and its own version
#     marker
# --------------------------------------------------------------------------

class TestDeterminismOfDeterminism:
    def test_same_inputs_produce_the_same_report_twice(self):
        state, sir = build_state_with_system_integrity()
        first = run_validate_determinism(state, system_integrity_report=sir)
        second = run_validate_determinism(state, system_integrity_report=sir)
        first.pop("generated_at")
        second.pop("generated_at")
        assert first == second

    def test_report_carries_its_own_version_marker(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert report["report_version"] == DETERMINISM_VERSION


# --------------------------------------------------------------------------
# 11. Read-only behavior
# --------------------------------------------------------------------------

class TestReadOnlyBehavior:
    def test_compiler_registry_manager_is_unmutated(self):
        state, sir = build_state_with_system_integrity()
        before = state["compiler_registry_manager"].serialize()
        run_validate_determinism(state, system_integrity_report=sir)
        after = state["compiler_registry_manager"].serialize()
        assert before == after

    def test_graph_registry_manager_is_unmutated(self):
        state, sir = build_state_with_system_integrity()
        before = state["graph_registry_manager"].serialize()
        run_validate_determinism(state, system_integrity_report=sir)
        after = state["graph_registry_manager"].serialize()
        assert before == after

    def test_input_dicts_are_unmutated(self):
        state, sir = build_state_with_system_integrity()
        snapshots = {
            key: copy.deepcopy(value)
            for key, value in state.items()
            if key.endswith(("_manifest", "_statistics", "_report", "_summary"))
        }
        sir_snapshot = copy.deepcopy(sir)
        run_validate_determinism(state, system_integrity_report=sir)
        for key, snapshot in snapshots.items():
            assert state[key] == snapshot, f"{key} was mutated"
        assert sir == sir_snapshot, "system_integrity_report was mutated"


# --------------------------------------------------------------------------
# 12. Pipeline / validation.determinism_state integration
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_report_round_trips_through_determinism_state(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        assert determinism_state.has_current_determinism_report() is False
        determinism_state.set_current_determinism_report(report)
        assert determinism_state.has_current_determinism_report() is True
        assert determinism_state.get_current_determinism_report() == report

    def test_reset_clears_the_current_report(self):
        state, sir = build_state_with_system_integrity()
        report = run_validate_determinism(state, system_integrity_report=sir)
        determinism_state.set_current_determinism_report(report)
        determinism_state.reset_determinism_state()
        assert determinism_state.has_current_determinism_report() is False
        assert determinism_state.get_current_determinism_report() is None

    def test_get_current_report_is_none_before_any_set(self):
        assert determinism_state.get_current_determinism_report() is None
        assert determinism_state.has_current_determinism_report() is False


# --------------------------------------------------------------------------
# 13. Backward compatibility -- DeterminismReport is purely additive
#     plumbing; it must never require any change to a frozen Phase A-D1
#     schema/registry/id/urn/manifest/statistics/fingerprint/build-
#     summary/System-Integrity-Report shape to run.
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_report_to_dict_contains_every_suggested_field(self):
        report = DeterminismReport()
        d = report.to_dict()
        for field_name in (
            "generated_at", "overall_status", "checks_passed", "checks_failed",
            "warnings", "errors", "summary", "fingerprint_determinism",
            "manifest_determinism", "statistics_determinism",
            "ordering_determinism", "report_version",
        ):
            assert field_name in d

    def test_validate_determinism_does_not_require_optional_artifacts(self):
        """Confirms Task 6's own "reuse the existing state pattern...
        or implement only what is necessary" allowance: every artifact
        beyond the two registry managers is optional, so this function
        never forces a caller (or an earlier Phase A-D1 module) to
        change shape just to supply a value D2 could otherwise do
        without."""
        signature = inspect.signature(validate_determinism)
        required = [
            name for name, param in signature.parameters.items()
            if param.default is inspect._empty
            and param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ]
        assert required == ["compiler_registry_manager", "graph_registry_manager"]

    def test_validate_determinism_never_mutates_registries_or_dicts_even_with_all_artifacts_missing(self):
        """A degenerate call (only the two required registry managers) is
        still fully read-only and still returns a well-formed report --
        no artifact this module might one day be handed is assumed to
        exist just because most callers (pipeline.py) always supply it."""
        state, _ = build_state_with_system_integrity()
        before_compiler = state["compiler_registry_manager"].serialize()
        before_graph = state["graph_registry_manager"].serialize()
        report = validate_determinism(
            state["compiler_registry_manager"], state["graph_registry_manager"],
        )
        assert isinstance(report, dict)
        assert state["compiler_registry_manager"].serialize() == before_compiler
        assert state["graph_registry_manager"].serialize() == before_graph
