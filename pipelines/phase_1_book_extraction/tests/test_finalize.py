"""
tests/test_finalize.py — unit tests for Phase B5.3's compiler.finalize
module (Compiler Finalization & Phase B Completion): Compiler Build
Summary, Final Compiler Status, Compiler State integration, and pipeline
integration.

Per task instructions, these tests are generated only: they are not
executed here as part of authoring them, and no claim is made about
whether they currently pass in the caller's environment beyond the
ad-hoc smoke checks performed during development.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import enrich_registries
from compiler.normalization import normalize_registries
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships
from compiler.validation import validate_compiler_state
from compiler.build import generate_compiler_manifest, generate_compiler_statistics
from compiler.fingerprints import generate_compiler_fingerprints
from compiler import state as compiler_state
from compiler.finalize import (
    FINALIZE_VERSION,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    STATUS_FAILED,
    CompilerBuildSummary,
    generate_compiler_build_summary,
    determine_final_compiler_status,
    finalize_compiler_build,
)


# --------------------------------------------------------------------------
# Helpers -- same minimal canonical envelope shape as tests/test_build.py /
# tests/test_fingerprints.py, built through a full A->B5.2 pipeline so the
# build summary / final status have a realistic, non-trivial set of
# upstream artifacts to aggregate.
# --------------------------------------------------------------------------

def make_concept(id_="c1", name="Photosynthesis", aliases=None, topic_ids=None, **extra):
    d = {
        "id": id_, "urn": f"urn:concept:{id_}", "object_type": "concept",
        "schema_version": "1.0.0", "provenance": {"source": "test"},
        "validation_status": "validated",
        "creation_metadata": {"compiler_version": "1.0.0"},
        "name": name, "aliases": aliases if aliases is not None else [],
        "topic_ids": topic_ids if topic_ids is not None else [],
    }
    d.update(extra)
    return d


def make_definition(id_="d1", term="Photosynthesis", topic_ids=None, **extra):
    d = {
        "id": id_, "urn": f"urn:definition:{id_}", "object_type": "definition",
        "schema_version": "1.0.0", "provenance": {"source": "test"},
        "validation_status": "validated",
        "creation_metadata": {"compiler_version": "1.0.0"},
        "term": term, "topic_ids": topic_ids if topic_ids is not None else [],
    }
    d.update(extra)
    return d


def build_full_compiler_state(concept_name="Photosynthesis", topics=None):
    """Runs the full B1-B5.2 pipeline over a small, realistic fixture and
    returns a dict of every artifact Phase B5.3 consumes -- the same set
    pipeline.py's own finalize_compiler_build() call site is handed."""
    topics = topics if topics is not None else []
    manager = create_registry_manager()
    populate_registries(
        manager,
        concepts=[make_concept(name=concept_name)],
        definitions=[make_definition()],
    )
    enrich_registries(manager)
    normalize_registries(manager)
    resolve_references(manager, topics=topics)
    resolve_relationships(manager, topics=topics)
    validation_report = validate_compiler_state(manager, topics=topics)
    manifest = generate_compiler_manifest(
        manager, validation_report, chapter_identifier="book:ch1",
    )
    statistics = generate_compiler_statistics(manager, validation_report)
    fingerprint_results = generate_compiler_fingerprints(
        manager,
        manifest=manifest,
        statistics=statistics,
        validation_report=validation_report,
    )
    return {
        "manager": manager,
        "validation_report": validation_report,
        "manifest": manifest,
        "statistics": statistics,
        "registry_fingerprints": fingerprint_results["registry_fingerprints"],
        "compiler_fingerprint": fingerprint_results["compiler_fingerprint"],
        "readiness_report": fingerprint_results["readiness_report"],
    }


@pytest.fixture(autouse=True)
def _reset_compiler_state():
    """Every test starts and ends with a clean compiler_state module --
    mirrors tests/test_fingerprints.py's own fixture, extended to the two
    new B5.3 slots."""
    compiler_state.reset_registry_state()
    yield
    compiler_state.reset_registry_state()


# --------------------------------------------------------------------------
# 1. Final Compiler Status (Task 2)
# --------------------------------------------------------------------------

class TestDetermineFinalCompilerStatus:
    def test_ready_when_validation_passes_and_readiness_ready_no_warnings(self):
        status = determine_final_compiler_status(
            {"status": "pass", "warnings": [], "errors": []},
            {"ready": True, "warnings": []},
        )
        assert status == STATUS_READY

    def test_ready_with_warnings_when_validation_has_warnings(self):
        status = determine_final_compiler_status(
            {"status": "pass", "warnings": ["w1"], "errors": []},
            {"ready": True, "warnings": []},
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_ready_with_warnings_when_readiness_has_warnings(self):
        status = determine_final_compiler_status(
            {"status": "pass", "warnings": [], "errors": []},
            {"ready": True, "warnings": ["some readiness warning"]},
        )
        assert status == STATUS_READY_WITH_WARNINGS

    def test_failed_when_validation_status_is_fail(self):
        status = determine_final_compiler_status(
            {"status": "fail", "warnings": [], "errors": ["e1"]},
            {"ready": True, "warnings": []},
        )
        assert status == STATUS_FAILED

    def test_failed_when_readiness_not_ready(self):
        status = determine_final_compiler_status(
            {"status": "pass", "warnings": [], "errors": []},
            {"ready": False, "warnings": [], "failed_checks": ["manifest_exists"]},
        )
        assert status == STATUS_FAILED

    def test_failed_when_both_validation_and_readiness_fail(self):
        status = determine_final_compiler_status(
            {"status": "fail", "warnings": [], "errors": ["e1"]},
            {"ready": False, "warnings": []},
        )
        assert status == STATUS_FAILED

    def test_failed_when_validation_report_is_none(self):
        status = determine_final_compiler_status(None, {"ready": True, "warnings": []})
        assert status == STATUS_FAILED

    def test_failed_when_readiness_report_is_none(self):
        status = determine_final_compiler_status({"status": "pass"}, None)
        assert status == STATUS_FAILED

    def test_failed_when_both_none(self):
        assert determine_final_compiler_status(None, None) == STATUS_FAILED

    def test_returns_one_of_the_three_closed_values(self):
        for validation_status in ("pass", "fail"):
            for ready in (True, False):
                for warnings in ([], ["w"]):
                    status = determine_final_compiler_status(
                        {"status": validation_status, "warnings": warnings, "errors": []},
                        {"ready": ready, "warnings": []},
                    )
                    assert status in {STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED}

    def test_never_mutates_inputs(self):
        validation_report = {"status": "pass", "warnings": ["w1"], "errors": []}
        readiness_report = {"ready": True, "warnings": []}
        before_v = copy.deepcopy(validation_report)
        before_r = copy.deepcopy(readiness_report)
        determine_final_compiler_status(validation_report, readiness_report)
        assert validation_report == before_v
        assert readiness_report == before_r

    def test_deterministic_across_repeated_calls(self):
        validation_report = {"status": "pass", "warnings": [], "errors": []}
        readiness_report = {"ready": True, "warnings": []}
        results = {
            determine_final_compiler_status(validation_report, readiness_report)
            for _ in range(5)
        }
        assert len(results) == 1


# --------------------------------------------------------------------------
# 2. Compiler Build Summary (Task 1)
# --------------------------------------------------------------------------

class TestGenerateCompilerBuildSummary:
    def test_returns_plain_dict(self):
        state = build_full_compiler_state()
        final_status = determine_final_compiler_status(
            state["validation_report"], state["readiness_report"],
        )
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], final_status,
        )
        assert isinstance(summary, dict)

    def test_contains_all_suggested_fields(self):
        state = build_full_compiler_state()
        final_status = determine_final_compiler_status(
            state["validation_report"], state["readiness_report"],
        )
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], final_status,
        )
        required = {
            "compiler_version", "schema_version", "compiler_status",
            "build_status", "total_registries", "total_objects",
            "total_relationships", "validation_summary", "readiness_summary",
            "compiler_fingerprint", "overall_summary",
        }
        assert required.issubset(summary.keys())

    def test_build_status_carries_final_status_verbatim(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"],
            STATUS_READY_WITH_WARNINGS,
        )
        assert summary["build_status"] == STATUS_READY_WITH_WARNINGS

    def test_compiler_version_matches_manifest(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["compiler_version"] == state["manifest"]["compiler_version"]

    def test_schema_version_matches_manifest(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["schema_version"] == state["manifest"]["schema_version"]

    def test_total_registries_matches_manifest_registry_count(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["total_registries"] == state["manifest"]["registry_count"]

    def test_total_objects_matches_manifest_object_count(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["total_objects"] == state["manifest"]["object_count"]

    def test_total_relationships_matches_manifest_relationship_count(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["total_relationships"] == state["manifest"]["relationship_count"]

    def test_compiler_fingerprint_passed_through_verbatim(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["compiler_fingerprint"] == state["compiler_fingerprint"]

    def test_validation_summary_reflects_validation_report(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["validation_summary"]["status"] == state["validation_report"]["status"]
        assert summary["validation_summary"]["error_count"] == len(
            state["validation_report"].get("errors") or []
        )
        assert summary["validation_summary"]["warning_count"] == len(
            state["validation_report"].get("warnings") or []
        )

    def test_readiness_summary_reused_from_readiness_report(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["readiness_summary"] == state["readiness_report"]["readiness_summary"]

    def test_overall_summary_is_nonempty_string(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert isinstance(summary["overall_summary"], str)
        assert summary["overall_summary"]

    def test_does_not_recompute_never_rescans_registries(self):
        """The build summary's total_objects/total_registries must come
        from the manifest, not a fresh scan -- verified by mutating the
        manifest and confirming the summary reflects the mutated value,
        not the manager's own live count."""
        state = build_full_compiler_state()
        mutated_manifest = dict(state["manifest"])
        mutated_manifest["object_count"] = 999999
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], mutated_manifest,
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert summary["total_objects"] == 999999

    def test_does_not_mutate_any_input(self):
        state = build_full_compiler_state()
        before_manifest = copy.deepcopy(state["manifest"])
        before_statistics = copy.deepcopy(state["statistics"])
        before_validation = copy.deepcopy(state["validation_report"])
        before_readiness = copy.deepcopy(state["readiness_report"])
        generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert state["manifest"] == before_manifest
        assert state["statistics"] == before_statistics
        assert state["validation_report"] == before_validation
        assert state["readiness_report"] == before_readiness

    def test_does_not_mutate_manager(self):
        state = build_full_compiler_state()
        before = state["manager"].get("concepts").serialize()
        generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        after = state["manager"].get("concepts").serialize()
        assert before == after

    def test_deterministic_modulo_generated_at(self):
        state = build_full_compiler_state()
        summary1 = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        summary2 = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        s1 = dict(summary1); s1.pop("generated_at")
        s2 = dict(summary2); s2.pop("generated_at")
        assert s1 == s2

    def test_matches_compiler_build_summary_dataclass_shape(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], state["readiness_report"], STATUS_READY,
        )
        assert set(summary.keys()) == {f.name for f in CompilerBuildSummary.__dataclass_fields__.values()}


# --------------------------------------------------------------------------
# 3. Pipeline integration -- finalize_compiler_build()
# --------------------------------------------------------------------------

class TestFinalizeCompilerBuild:
    def test_returns_build_summary_and_final_status(self):
        state = build_full_compiler_state()
        result = finalize_compiler_build(
            state["manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert set(result.keys()) == {"build_summary", "final_status"}
        assert isinstance(result["build_summary"], dict)
        assert isinstance(result["final_status"], str)

    def test_build_summary_build_status_matches_final_status(self):
        state = build_full_compiler_state()
        result = finalize_compiler_build(
            state["manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert result["build_summary"]["build_status"] == result["final_status"]

    def test_final_status_matches_standalone_determination(self):
        state = build_full_compiler_state()
        result = finalize_compiler_build(
            state["manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        expected = determine_final_compiler_status(
            state["validation_report"], state["readiness_report"],
        )
        assert result["final_status"] == expected

    def test_does_not_mutate_manager_or_upstream_artifacts(self):
        state = build_full_compiler_state()
        before_manager = state["manager"].get("concepts").serialize()
        before_manifest = copy.deepcopy(state["manifest"])
        finalize_compiler_build(
            state["manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        assert state["manager"].get("concepts").serialize() == before_manager
        assert state["manifest"] == before_manifest

    def test_deterministic_across_repeated_calls(self):
        state = build_full_compiler_state()
        kwargs = dict(
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        result1 = finalize_compiler_build(state["manager"], **kwargs)
        result2 = finalize_compiler_build(state["manager"], **kwargs)
        s1 = dict(result1["build_summary"]); s1.pop("generated_at")
        s2 = dict(result2["build_summary"]); s2.pop("generated_at")
        assert s1 == s2
        assert result1["final_status"] == result2["final_status"]


# --------------------------------------------------------------------------
# 4. Compiler State integration (Task 3)
# --------------------------------------------------------------------------

class TestCompilerStateIntegration:
    def test_no_current_build_summary_before_set(self):
        assert not compiler_state.has_current_compiler_build_summary()
        assert compiler_state.get_current_compiler_build_summary() is None

    def test_no_current_final_status_before_set(self):
        assert not compiler_state.has_current_final_compiler_status()
        assert compiler_state.get_current_final_compiler_status() is None

    def test_set_and_get_build_summary(self):
        state = build_full_compiler_state()
        result = finalize_compiler_build(
            state["manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        compiler_state.set_current_compiler_build_summary(result["build_summary"])
        assert compiler_state.has_current_compiler_build_summary()
        assert compiler_state.get_current_compiler_build_summary() == result["build_summary"]

    def test_set_and_get_final_status(self):
        state = build_full_compiler_state()
        result = finalize_compiler_build(
            state["manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        compiler_state.set_current_final_compiler_status(result["final_status"])
        assert compiler_state.has_current_final_compiler_status()
        assert compiler_state.get_current_final_compiler_status() == result["final_status"]

    def test_reset_registry_state_clears_both_new_slots(self):
        compiler_state.set_current_compiler_build_summary({"build_status": "READY"})
        compiler_state.set_current_final_compiler_status("READY")
        compiler_state.reset_registry_state()
        assert not compiler_state.has_current_compiler_build_summary()
        assert not compiler_state.has_current_final_compiler_status()
        assert compiler_state.get_current_compiler_build_summary() is None
        assert compiler_state.get_current_final_compiler_status() is None

    def test_reset_registry_state_still_clears_every_earlier_slot(self):
        """Backward compatibility: the B5.3 slots must be additive, not a
        replacement of reset_registry_state()'s existing clearing
        behavior for every earlier phase's own slot."""
        state = build_full_compiler_state()
        compiler_state.set_current_registry_manager(state["manager"])
        compiler_state.set_current_validation_report(state["validation_report"])
        compiler_state.set_current_compiler_manifest(state["manifest"])
        compiler_state.set_current_compiler_statistics(state["statistics"])
        compiler_state.set_current_registry_fingerprints(state["registry_fingerprints"])
        compiler_state.set_current_compiler_fingerprint(state["compiler_fingerprint"])
        compiler_state.set_current_compiler_readiness_report(state["readiness_report"])
        compiler_state.set_current_compiler_build_summary({"build_status": "READY"})
        compiler_state.set_current_final_compiler_status("READY")

        compiler_state.reset_registry_state()

        assert not compiler_state.has_current_registry_manager()
        assert not compiler_state.has_current_validation_report()
        assert not compiler_state.has_current_compiler_manifest()
        assert not compiler_state.has_current_compiler_statistics()
        assert not compiler_state.has_current_registry_fingerprints()
        assert not compiler_state.has_current_compiler_fingerprint()
        assert not compiler_state.has_current_compiler_readiness_report()
        assert not compiler_state.has_current_compiler_build_summary()
        assert not compiler_state.has_current_final_compiler_status()

    def test_build_summary_survives_until_next_reset(self):
        compiler_state.set_current_compiler_build_summary({"build_status": "READY"})
        assert compiler_state.has_current_compiler_build_summary()
        assert compiler_state.get_current_compiler_build_summary() == {"build_status": "READY"}
        # unrelated reads don't clear it
        compiler_state.get_current_final_compiler_status()
        assert compiler_state.has_current_compiler_build_summary()


# --------------------------------------------------------------------------
# 5. Read-only behavior / backward compatibility
# --------------------------------------------------------------------------

class TestReadOnlyAndBackwardCompatibility:
    def test_finalize_never_inserts_into_any_registry(self):
        state = build_full_compiler_state()
        sizes_before = {
            name: state["manager"].get(name).size()
            for name in state["manager"].names()
        }
        finalize_compiler_build(
            state["manager"],
            validation_report=state["validation_report"],
            manifest=state["manifest"],
            statistics=state["statistics"],
            registry_fingerprints=state["registry_fingerprints"],
            compiler_fingerprint=state["compiler_fingerprint"],
            readiness_report=state["readiness_report"],
        )
        sizes_after = {
            name: state["manager"].get(name).size()
            for name in state["manager"].names()
        }
        assert sizes_before == sizes_after

    def test_missing_manifest_and_statistics_do_not_raise(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], None, None,
            state["registry_fingerprints"], state["compiler_fingerprint"],
            state["readiness_report"], STATUS_READY,
        )
        assert isinstance(summary, dict)
        assert summary["compiler_version"] == "unknown"

    def test_missing_readiness_report_does_not_raise(self):
        state = build_full_compiler_state()
        summary = generate_compiler_build_summary(
            state["manager"], state["validation_report"], state["manifest"],
            state["statistics"], state["registry_fingerprints"],
            state["compiler_fingerprint"], None, STATUS_FAILED,
        )
        assert isinstance(summary, dict)
        assert summary["readiness_summary"]["total_checks"] == 0

    def test_finalize_version_is_a_string_constant(self):
        assert isinstance(FINALIZE_VERSION, str)
        assert FINALIZE_VERSION

    def test_status_constants_are_the_three_closed_values(self):
        assert {STATUS_READY, STATUS_READY_WITH_WARNINGS, STATUS_FAILED} == {
            "READY", "READY_WITH_WARNINGS", "FAILED",
        }
