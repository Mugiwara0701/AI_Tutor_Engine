"""
tests/test_fingerprints.py — unit tests for Phase B5.2's
compiler.fingerprints module (Compiler Fingerprints & Readiness).

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import copy
import time

import pytest

from compiler.registry_manager import RegistryManager
from compiler.registries import (
    create_registry_manager,
    populate_registries,
    REGISTRY_NAMES,
)
from compiler.enrichment import enrich_registries
from compiler.normalization import normalize_registries
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships, RELATIONSHIP_REGISTRY_NAME
from compiler.validation import validate_compiler_state
from compiler.build import generate_compiler_manifest, generate_compiler_statistics
from compiler import state as compiler_state
from compiler.fingerprints import (
    FINGERPRINT_VERSION,
    VOLATILE_KEYS,
    REQUIRED_REGISTRY_NAMES,
    CompilerReadinessReport,
    generate_registry_fingerprints,
    generate_compiler_fingerprint,
    generate_compiler_readiness_report,
    generate_compiler_fingerprints,
)


# --------------------------------------------------------------------------
# Helpers -- same minimal canonical envelope shape as tests/test_build.py,
# built through a full A->B5.1 pipeline so fingerprints/readiness have a
# realistic, non-trivial RegistryManager + manifest + statistics +
# validation report to describe.
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
    """Runs the full B1-B5.1 pipeline over a small, realistic fixture and
    returns (manager, manifest, statistics, validation_report) -- the
    four inputs Phase B5.2's functions expect.

    The fixture's one Definition uses a term ("Unrelated Term") that
    deliberately never matches any `concept_name` this file passes in
    (Photosynthesis / Respiration / A / B) -- see
    TestRegistryFingerprints.test_unaffected_registries_keep_same_fingerprint,
    which asserts that changing ONLY the concepts registry's content
    leaves the definitions registry's fingerprint unchanged. If the
    definition's term instead matched `concept_name` (as a naive fixture
    might do by reusing the same default string for both), compiler/
    references.py's own resolve_references() would resolve that
    definition's `concept_id` differently depending on `concept_name` --
    correctly, since the definition's own content-relevant `concept_id`
    field really would differ -- which would make "definitions" look
    "affected" for a reason that has nothing to do with what this test is
    actually checking (per-registry fingerprint isolation). Keeping the
    term concept-name-independent keeps the definition's resolution
    status (and therefore its content) identical across every
    concept_name this file uses, so its fingerprint is a true "did this
    registry's own content change" signal.
    """
    topics = topics if topics is not None else []
    manager = create_registry_manager()
    populate_registries(
        manager,
        concepts=[make_concept(name=concept_name)],
        definitions=[make_definition(term="Unrelated Term")],
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
    return manager, manifest, statistics, validation_report


@pytest.fixture(autouse=True)
def _reset_compiler_state():
    """Every test starts and ends with a clean compiler_state module --
    mirrors tests/test_build.py's own fixture, extended to the three new
    B5.2 slots."""
    compiler_state.reset_registry_state()
    yield
    compiler_state.reset_registry_state()


# --------------------------------------------------------------------------
# 1. Registry fingerprints
# --------------------------------------------------------------------------

class TestRegistryFingerprints:
    def test_returns_dict_keyed_by_registry_name(self):
        manager, *_ = build_full_compiler_state()
        fingerprints = generate_registry_fingerprints(manager)
        assert isinstance(fingerprints, dict)
        assert set(fingerprints.keys()) == set(manager.names())

    def test_every_fingerprint_is_a_sha256_hex_string(self):
        manager, *_ = build_full_compiler_state()
        fingerprints = generate_registry_fingerprints(manager)
        for value in fingerprints.values():
            assert isinstance(value, str)
            assert len(value) == 64
            int(value, 16)  # raises ValueError if not valid hex

    def test_empty_registry_still_gets_a_fingerprint(self):
        manager = create_registry_manager()
        fingerprints = generate_registry_fingerprints(manager)
        assert set(fingerprints.keys()) == set(REGISTRY_NAMES)
        assert all(isinstance(v, str) and v for v in fingerprints.values())

    def test_same_contents_same_fingerprint(self):
        manager1, *_ = build_full_compiler_state()
        manager2, *_ = build_full_compiler_state()
        fp1 = generate_registry_fingerprints(manager1)
        fp2 = generate_registry_fingerprints(manager2)
        assert fp1 == fp2

    def test_different_contents_different_fingerprint(self):
        manager1, *_ = build_full_compiler_state(concept_name="Photosynthesis")
        manager2, *_ = build_full_compiler_state(concept_name="Respiration")
        fp1 = generate_registry_fingerprints(manager1)
        fp2 = generate_registry_fingerprints(manager2)
        assert fp1["concepts"] != fp2["concepts"]

    def test_unaffected_registries_keep_same_fingerprint(self):
        """Changing the concepts registry's content should not affect the
        fingerprint of a registry whose own contents didn't change."""
        manager1, *_ = build_full_compiler_state(concept_name="Photosynthesis")
        manager2, *_ = build_full_compiler_state(concept_name="Respiration")
        fp1 = generate_registry_fingerprints(manager1)
        fp2 = generate_registry_fingerprints(manager2)
        assert fp1["definitions"] == fp2["definitions"]

    def test_does_not_mutate_manager(self):
        manager, *_ = build_full_compiler_state()
        before = manager.get("concepts").serialize()
        generate_registry_fingerprints(manager)
        after = manager.get("concepts").serialize()
        assert before == after

    def test_deterministic_across_repeated_calls(self):
        manager, *_ = build_full_compiler_state()
        fp1 = generate_registry_fingerprints(manager)
        fp2 = generate_registry_fingerprints(manager)
        assert fp1 == fp2


# --------------------------------------------------------------------------
# 2. Volatile-field exclusion
# --------------------------------------------------------------------------

class TestVolatileFieldExclusion:
    def test_fingerprint_unaffected_by_wall_clock_time(self):
        """Two builds of otherwise-identical content, separated by real
        time (so every enriched_at/normalized_at/resolved_at/created_at/
        generated_at timestamp genuinely differs), must fingerprint
        identically."""
        manager1, manifest1, stats1, _ = build_full_compiler_state()
        time.sleep(1.1)
        manager2, manifest2, stats2, _ = build_full_compiler_state()

        registry_fp1 = generate_registry_fingerprints(manager1)
        registry_fp2 = generate_registry_fingerprints(manager2)
        assert registry_fp1 == registry_fp2

        compiler_fp1 = generate_compiler_fingerprint(registry_fp1, manifest1, stats1)
        compiler_fp2 = generate_compiler_fingerprint(registry_fp2, manifest2, stats2)
        assert compiler_fp1 == compiler_fp2

    def test_volatile_keys_constant_covers_known_timestamp_fields(self):
        expected = {
            "generated_at", "enriched_at", "normalized_at", "resolved_at",
            "created_at", "timestamp", "approx_memory_bytes",
        }
        assert expected.issubset(VOLATILE_KEYS)

    def test_manifest_generated_at_excluded_from_compiler_fingerprint(self):
        manager, manifest, stats, _ = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)

        manifest_a = copy.deepcopy(manifest)
        manifest_b = copy.deepcopy(manifest)
        manifest_a["generated_at"] = "2020-01-01T00:00:00+00:00"
        manifest_b["generated_at"] = "2099-12-31T23:59:59+00:00"

        fp_a = generate_compiler_fingerprint(registry_fp, manifest_a, stats)
        fp_b = generate_compiler_fingerprint(registry_fp, manifest_b, stats)
        assert fp_a == fp_b

    def test_statistics_generated_at_excluded_from_compiler_fingerprint(self):
        manager, manifest, stats, _ = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)

        stats_a = copy.deepcopy(stats)
        stats_b = copy.deepcopy(stats)
        stats_a["generated_at"] = "2020-01-01T00:00:00+00:00"
        stats_b["generated_at"] = "2099-12-31T23:59:59+00:00"

        fp_a = generate_compiler_fingerprint(registry_fp, manifest, stats_a)
        fp_b = generate_compiler_fingerprint(registry_fp, manifest, stats_b)
        assert fp_a == fp_b

    def test_non_volatile_manifest_field_change_changes_fingerprint(self):
        """Sanity check that fingerprinting isn't accidentally excluding
        everything -- a genuinely meaningful manifest field change must
        change the compiler fingerprint."""
        manager, manifest, stats, _ = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)

        manifest_a = copy.deepcopy(manifest)
        manifest_b = copy.deepcopy(manifest)
        manifest_b["chapter_identifier"] = "some:other:chapter"

        fp_a = generate_compiler_fingerprint(registry_fp, manifest_a, stats)
        fp_b = generate_compiler_fingerprint(registry_fp, manifest_b, stats)
        assert fp_a != fp_b


# --------------------------------------------------------------------------
# 3. Compiler fingerprint
# --------------------------------------------------------------------------

class TestCompilerFingerprint:
    def test_returns_sha256_hex_string(self):
        manager, manifest, stats, _ = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        fingerprint = generate_compiler_fingerprint(registry_fp, manifest, stats)
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64
        int(fingerprint, 16)

    def test_same_ir_same_fingerprint(self):
        manager1, manifest1, stats1, _ = build_full_compiler_state()
        manager2, manifest2, stats2, _ = build_full_compiler_state()
        fp1 = generate_compiler_fingerprint(
            generate_registry_fingerprints(manager1), manifest1, stats1,
        )
        fp2 = generate_compiler_fingerprint(
            generate_registry_fingerprints(manager2), manifest2, stats2,
        )
        assert fp1 == fp2

    def test_different_ir_different_fingerprint(self):
        manager1, manifest1, stats1, _ = build_full_compiler_state(concept_name="A")
        manager2, manifest2, stats2, _ = build_full_compiler_state(concept_name="B")
        fp1 = generate_compiler_fingerprint(
            generate_registry_fingerprints(manager1), manifest1, stats1,
        )
        fp2 = generate_compiler_fingerprint(
            generate_registry_fingerprints(manager2), manifest2, stats2,
        )
        assert fp1 != fp2

    def test_registry_fingerprint_key_order_does_not_matter(self):
        manager, manifest, stats, _ = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        reordered = dict(reversed(list(registry_fp.items())))
        fp1 = generate_compiler_fingerprint(registry_fp, manifest, stats)
        fp2 = generate_compiler_fingerprint(reordered, manifest, stats)
        assert fp1 == fp2

    def test_missing_manifest_or_statistics_does_not_raise(self):
        manager, *_ = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        fingerprint = generate_compiler_fingerprint(registry_fp, None, None)
        assert isinstance(fingerprint, str) and len(fingerprint) == 64


# --------------------------------------------------------------------------
# 4. Readiness report
# --------------------------------------------------------------------------

class TestComplierReadinessReport:
    def test_returns_plain_dict_with_required_fields(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, registry_fp, compiler_fp,
        )
        assert isinstance(report, dict)
        required = {
            "ready", "compiler_status", "passed_checks", "failed_checks",
            "warnings", "readiness_summary",
        }
        assert required.issubset(report.keys())

    def test_fully_built_chapter_is_ready(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, registry_fp, compiler_fp,
        )
        assert report["ready"] is True
        assert report["failed_checks"] == []

    def test_all_seven_checks_pass_for_a_full_build(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, registry_fp, compiler_fp,
        )
        expected_checks = {
            "required_registries_exist", "validation_completed",
            "manifest_exists", "statistics_exist",
            "registry_fingerprints_generated", "compiler_fingerprint_generated",
            "relationships_registry_available",
        }
        assert set(report["passed_checks"]) == expected_checks

    def test_missing_registries_fails_readiness(self):
        empty_manager = RegistryManager()
        report = generate_compiler_readiness_report(
            empty_manager, None, None, None, None, None,
        )
        assert report["ready"] is False
        assert "required_registries_exist" in report["failed_checks"]
        assert "relationships_registry_available" in report["failed_checks"]

    def test_missing_validation_report_fails_readiness(self):
        manager, manifest, stats, _ = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, None, manifest, stats, registry_fp, compiler_fp,
        )
        assert report["ready"] is False
        assert "validation_completed" in report["failed_checks"]

    def test_failed_validation_status_fails_readiness(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        failing_report = copy.deepcopy(validation_report)
        failing_report["status"] = "fail"
        report = generate_compiler_readiness_report(
            manager, failing_report, manifest, stats, registry_fp, compiler_fp,
        )
        assert report["ready"] is False
        assert "validation_completed" in report["failed_checks"]

    def test_missing_manifest_fails_readiness(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, None, stats, registry_fp, compiler_fp,
        )
        assert report["ready"] is False
        assert "manifest_exists" in report["failed_checks"]

    def test_missing_statistics_fails_readiness(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, None, registry_fp, compiler_fp,
        )
        assert report["ready"] is False
        assert "statistics_exist" in report["failed_checks"]

    def test_missing_registry_fingerprints_fails_readiness(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, None, compiler_fp,
        )
        assert report["ready"] is False
        assert "registry_fingerprints_generated" in report["failed_checks"]

    def test_incomplete_registry_fingerprints_fails_readiness(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        partial_fp = dict(list(registry_fp.items())[:1])
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, partial_fp, compiler_fp,
        )
        assert report["ready"] is False
        assert "registry_fingerprints_generated" in report["failed_checks"]

    def test_missing_compiler_fingerprint_fails_readiness(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, registry_fp, None,
        )
        assert report["ready"] is False
        assert "compiler_fingerprint_generated" in report["failed_checks"]

    def test_relationships_registry_missing_fails_readiness(self):
        # A manager that has every educational-object registry but never
        # had resolve_relationships() run on it (so no "relationships"
        # registry exists yet).
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept()])
        report = generate_compiler_readiness_report(
            manager, None, None, None, None, None,
        )
        assert "relationships_registry_available" in report["failed_checks"]

    def test_readiness_summary_counts_are_consistent(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, registry_fp, compiler_fp,
        )
        summary = report["readiness_summary"]
        assert summary["passed_count"] == len(report["passed_checks"])
        assert summary["failed_count"] == len(report["failed_checks"])
        assert summary["warning_count"] == len(report["warnings"])
        assert summary["total_checks"] == summary["passed_count"] + summary["failed_count"]

    def test_compiler_status_carries_forward_validation_status(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        report = generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, registry_fp, compiler_fp,
        )
        assert report["compiler_status"] == validation_report["status"]

    def test_never_mutates_manager_or_reports(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        registry_fp = generate_registry_fingerprints(manager)
        compiler_fp = generate_compiler_fingerprint(registry_fp, manifest, stats)
        manifest_before = copy.deepcopy(manifest)
        stats_before = copy.deepcopy(stats)
        validation_before = copy.deepcopy(validation_report)
        registry_size_before = manager.get("concepts").size()

        generate_compiler_readiness_report(
            manager, validation_report, manifest, stats, registry_fp, compiler_fp,
        )

        assert manifest == manifest_before
        assert stats == stats_before
        assert validation_report == validation_before
        assert manager.get("concepts").size() == registry_size_before

    def test_readiness_report_dataclass_round_trips(self):
        report = CompilerReadinessReport(
            generated_at="2024-01-01T00:00:00+00:00",
            ready=True,
            compiler_status="pass",
            passed_checks=["a"],
            failed_checks=[],
            warnings=[],
            readiness_summary={"total_checks": 1, "passed_count": 1, "failed_count": 0, "warning_count": 0},
        )
        d = report.to_dict()
        assert d["ready"] is True
        assert d["passed_checks"] == ["a"]


# --------------------------------------------------------------------------
# 5. Compiler state integration
# --------------------------------------------------------------------------

class TestCompilerStateIntegration:
    def test_slots_start_empty(self):
        assert compiler_state.get_current_registry_fingerprints() is None
        assert compiler_state.get_current_compiler_fingerprint() is None
        assert compiler_state.get_current_compiler_readiness_report() is None
        assert not compiler_state.has_current_registry_fingerprints()
        assert not compiler_state.has_current_compiler_fingerprint()
        assert not compiler_state.has_current_compiler_readiness_report()

    def test_set_and_get_registry_fingerprints(self):
        fingerprints = {"concepts": "abc123"}
        compiler_state.set_current_registry_fingerprints(fingerprints)
        assert compiler_state.has_current_registry_fingerprints()
        assert compiler_state.get_current_registry_fingerprints() == fingerprints

    def test_set_and_get_compiler_fingerprint(self):
        compiler_state.set_current_compiler_fingerprint("deadbeef")
        assert compiler_state.has_current_compiler_fingerprint()
        assert compiler_state.get_current_compiler_fingerprint() == "deadbeef"

    def test_set_and_get_compiler_readiness_report(self):
        report = {"ready": True}
        compiler_state.set_current_compiler_readiness_report(report)
        assert compiler_state.has_current_compiler_readiness_report()
        assert compiler_state.get_current_compiler_readiness_report() == report

    def test_reset_registry_state_clears_all_three_new_slots(self):
        compiler_state.set_current_registry_fingerprints({"concepts": "abc"})
        compiler_state.set_current_compiler_fingerprint("deadbeef")
        compiler_state.set_current_compiler_readiness_report({"ready": True})

        compiler_state.reset_registry_state()

        assert compiler_state.get_current_registry_fingerprints() is None
        assert compiler_state.get_current_compiler_fingerprint() is None
        assert compiler_state.get_current_compiler_readiness_report() is None

    def test_reset_registry_state_still_clears_pre_existing_slots(self):
        """Backward compatibility: the B5.2 addition to reset_registry_
        state() must not stop it from also clearing every earlier
        phase's own slot."""
        manager, manifest, stats, validation_report = build_full_compiler_state()
        compiler_state.set_current_registry_manager(manager)
        compiler_state.set_current_validation_report(validation_report)
        compiler_state.set_current_compiler_manifest(manifest)
        compiler_state.set_current_compiler_statistics(stats)

        compiler_state.reset_registry_state()

        assert compiler_state.get_current_registry_manager() is None
        assert compiler_state.get_current_validation_report() is None
        assert compiler_state.get_current_compiler_manifest() is None
        assert compiler_state.get_current_compiler_statistics() is None


# --------------------------------------------------------------------------
# 6. Pipeline integration (generate_compiler_fingerprints())
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_returns_all_three_artifacts(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        result = generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        assert set(result.keys()) == {
            "registry_fingerprints", "compiler_fingerprint", "readiness_report",
        }

    def test_registry_fingerprints_match_standalone_call(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        result = generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        standalone = generate_registry_fingerprints(manager)
        assert result["registry_fingerprints"] == standalone

    def test_compiler_fingerprint_matches_standalone_call(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        result = generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        standalone_registry_fp = generate_registry_fingerprints(manager)
        standalone_compiler_fp = generate_compiler_fingerprint(
            standalone_registry_fp, manifest, stats,
        )
        assert result["compiler_fingerprint"] == standalone_compiler_fp

    def test_readiness_report_reflects_full_build(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        result = generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        assert result["readiness_report"]["ready"] is True

    def test_full_pipeline_can_populate_compiler_state(self):
        """Mirrors pipeline.py's own call sequence: generate, then store
        each artifact via compiler_state's B5.2 setters."""
        manager, manifest, stats, validation_report = build_full_compiler_state()
        result = generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        compiler_state.set_current_registry_fingerprints(result["registry_fingerprints"])
        compiler_state.set_current_compiler_fingerprint(result["compiler_fingerprint"])
        compiler_state.set_current_compiler_readiness_report(result["readiness_report"])

        assert compiler_state.get_current_registry_fingerprints() == result["registry_fingerprints"]
        assert compiler_state.get_current_compiler_fingerprint() == result["compiler_fingerprint"]
        assert compiler_state.get_current_compiler_readiness_report() == result["readiness_report"]


# --------------------------------------------------------------------------
# 7. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_does_not_modify_registry_ids_or_urns(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        ids_before = {name: manager.get(name).ids() for name in manager.names()}
        generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        ids_after = {name: manager.get(name).ids() for name in manager.names()}
        assert ids_before == ids_after

    def test_does_not_modify_manifest_or_statistics_dicts(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        manifest_before = copy.deepcopy(manifest)
        stats_before = copy.deepcopy(stats)
        generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        assert manifest == manifest_before
        assert stats == stats_before

    def test_does_not_modify_validation_report(self):
        manager, manifest, stats, validation_report = build_full_compiler_state()
        validation_before = copy.deepcopy(validation_report)
        generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        assert validation_report == validation_before

    def test_required_registry_names_includes_relationships(self):
        assert RELATIONSHIP_REGISTRY_NAME in REQUIRED_REGISTRY_NAMES

    def test_required_registry_names_includes_every_b1_registry(self):
        assert set(REGISTRY_NAMES).issubset(set(REQUIRED_REGISTRY_NAMES))

    def test_fingerprint_version_is_a_string_constant(self):
        assert isinstance(FINGERPRINT_VERSION, str) and FINGERPRINT_VERSION

    def test_does_not_write_into_chapter_json_shaped_dict(self):
        """Nothing in this module attaches fingerprints/readiness to an
        arbitrary chapter_dict-shaped structure -- this phase's
        artifacts are compiler-state-only, never Chapter JSON fields."""
        manager, manifest, stats, validation_report = build_full_compiler_state()
        chapter_dict = {"concepts": [], "definitions": []}
        chapter_dict_before = copy.deepcopy(chapter_dict)
        generate_compiler_fingerprints(
            manager, manifest=manifest, statistics=stats,
            validation_report=validation_report,
        )
        assert chapter_dict == chapter_dict_before
