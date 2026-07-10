"""
tests/test_build.py — unit tests for Phase B5.1's compiler.build module
(Compiler Manifest & Statistics).

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import copy

import pytest

from config import SCHEMA_VERSION

from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import enrich_registries, ENRICHMENT_VERSION, ENRICHMENT_FIELDS
from compiler.normalization import normalize_registries, NORMALIZATION_VERSION, NORMALIZATION_FIELDS
from compiler.references import resolve_references, REFERENCE_RESOLUTION_VERSION
from compiler.relationships import (
    resolve_relationships,
    RELATIONSHIP_RESOLUTION_VERSION,
    RELATIONSHIP_REGISTRY_NAME,
)
from compiler.validation import validate_compiler_state, VALIDATION_VERSION
from compiler import state as compiler_state
from compiler.build import (
    COMPILER_VERSION,
    BUILD_VERSION,
    CompilerManifest,
    CompilerStatistics,
    generate_compiler_manifest,
    generate_compiler_statistics,
)


# --------------------------------------------------------------------------
# Helpers -- same minimal canonical envelope shape as
# tests/test_relationships.py / tests/test_validation.py, built through a
# full A->B4 pipeline so the manifest/statistics have a realistic,
# non-trivial RegistryManager + validation report to describe.
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


def build_manager_and_report(topics=None):
    """Runs the full B1-B4 pipeline (population, enrichment,
    normalization, reference resolution, relationship resolution,
    validation) over a small, realistic fixture and returns
    (manager, validation_report) -- exactly the two inputs
    generate_compiler_manifest()/generate_compiler_statistics() expect."""
    manager = create_registry_manager()
    populate_registries(
        manager,
        concepts=[make_concept()],
        definitions=[make_definition()],
    )
    enrich_registries(manager)
    normalize_registries(manager)
    resolve_references(manager, topics=topics)
    resolve_relationships(manager, topics=topics)
    report = validate_compiler_state(manager, topics=topics)
    return manager, report


@pytest.fixture(autouse=True)
def _reset_compiler_state():
    """Every test starts and ends with a clean compiler_state module --
    mirrors tests/test_validation.py's own fixture for
    _CURRENT_VALIDATION_REPORT, extended to the two new B5.1 slots."""
    compiler_state.reset_registry_state()
    yield
    compiler_state.reset_registry_state()


# --------------------------------------------------------------------------
# 1. Compiler manifest generation
# --------------------------------------------------------------------------

class TestCompilerManifestGeneration:
    def test_returns_plain_dict(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report, chapter_identifier="book:ch1")
        assert isinstance(manifest, dict)

    def test_contains_all_required_fields(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report, chapter_identifier="book:ch1")
        required = {
            "compiler_version", "schema_version", "build_version",
            "chapter_identifier", "registry_versions", "registry_count",
            "object_count", "relationship_count", "validation_status",
            "compiler_status", "build_status",
        }
        assert required.issubset(manifest.keys())

    def test_compiler_version_is_module_constant(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["compiler_version"] == COMPILER_VERSION

    def test_build_version_is_module_constant(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["build_version"] == BUILD_VERSION

    def test_schema_version_matches_config(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["schema_version"] == SCHEMA_VERSION

    def test_chapter_identifier_passed_through(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report, chapter_identifier="physics:ch3")
        assert manifest["chapter_identifier"] == "physics:ch3"

    def test_chapter_identifier_defaults_to_none(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["chapter_identifier"] is None

    def test_registry_versions_reuses_existing_version_constants(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["registry_versions"] == {
            "enrichment": ENRICHMENT_VERSION,
            "normalization": NORMALIZATION_VERSION,
            "reference_resolution": REFERENCE_RESOLUTION_VERSION,
            "relationship_resolution": RELATIONSHIP_RESOLUTION_VERSION,
            "validation": VALIDATION_VERSION,
        }

    def test_registry_count_matches_manager(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["registry_count"] == len(manager.names())

    def test_object_count_matches_manager_total_minus_relationships(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        # object_count reuses validation_report's own
        # total_canonical_objects, which deliberately excludes the
        # "relationships" registry (see compiler/validation.py's own
        # REGISTRY_NAMES-scoped sum) -- confirm it matches that, not
        # manager.total_size() (which WOULD include relationships).
        assert manifest["object_count"] == report["statistics"]["total_canonical_objects"]

    def test_relationship_count_matches_report(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["relationship_count"] == report["relationship_summary"]["total"]

    def test_validation_status_matches_report(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["validation_status"] == report["status"]

    def test_compiler_status_mirrors_validation_status(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["compiler_status"] == manifest["validation_status"]

    def test_build_status_is_generated(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["build_status"] == "generated"

    def test_generated_at_present_and_stringlike(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        assert isinstance(manifest["generated_at"], str) and manifest["generated_at"]

    def test_handles_failing_validation_report(self):
        # A validation report with errors (e.g. a broken reference) still
        # produces a complete manifest -- this pass never gates on
        # validation status, only reports it.
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept(topic_ids=["missing-topic"])])
        enrich_registries(manager)
        normalize_registries(manager)
        resolve_references(manager, topics=[])
        resolve_relationships(manager, topics=[])
        report = validate_compiler_state(manager, topics=[])
        assert report["status"] == "fail"
        manifest = generate_compiler_manifest(manager, report)
        assert manifest["validation_status"] == "fail"
        assert manifest["compiler_status"] == "fail"
        assert manifest["build_status"] == "generated"

    def test_falls_back_when_report_missing_statistics(self):
        # Defensive fallback: a caller-supplied report without the
        # expected "statistics"/"relationship_summary" blocks still
        # produces sane counts, read from `manager` directly.
        manager, _ = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, {"status": "pass"})
        assert manifest["registry_count"] == len(manager.names())
        assert manifest["object_count"] == manager.total_size()
        assert manifest["relationship_count"] == 0


# --------------------------------------------------------------------------
# 2. Compiler statistics generation
# --------------------------------------------------------------------------

class TestCompilerStatisticsGeneration:
    def test_returns_plain_dict(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert isinstance(stats, dict)

    def test_contains_expected_top_level_fields(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        expected = {
            "generated_at", "registry_sizes", "relationships_by_type",
            "total_relationships", "total_objects", "validation_summary",
            "enrichment_summary", "normalization_summary",
            "reference_resolution_summary", "relationship_resolution_summary",
        }
        assert expected.issubset(stats.keys())

    def test_registry_sizes_matches_manager_statistics(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        expected_sizes = {name: rs.size for name, rs in manager.statistics().items()}
        assert stats["registry_sizes"] == expected_sizes

    def test_registry_sizes_includes_every_registered_registry(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert set(stats["registry_sizes"].keys()) == set(manager.names())

    def test_relationships_by_type_matches_report(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert stats["relationships_by_type"] == report["relationship_summary"]["by_type"]

    def test_total_relationships_matches_report(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert stats["total_relationships"] == report["relationship_summary"]["total"]

    def test_total_objects_matches_report(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert stats["total_objects"] == report["statistics"]["total_canonical_objects"]

    def test_validation_summary_carries_report_statistics(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        for key, value in report["statistics"].items():
            assert stats["validation_summary"][key] == value
        assert stats["validation_summary"]["status"] == report["status"]

    def test_enrichment_summary_reuses_existing_constants(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert stats["enrichment_summary"]["version"] == ENRICHMENT_VERSION
        assert stats["enrichment_summary"]["fields"] == list(ENRICHMENT_FIELDS)

    def test_normalization_summary_reuses_existing_constants(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert stats["normalization_summary"]["version"] == NORMALIZATION_VERSION
        assert stats["normalization_summary"]["fields"] == list(NORMALIZATION_FIELDS)

    def test_reference_resolution_summary_reuses_report_summary(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert stats["reference_resolution_summary"]["version"] == REFERENCE_RESOLUTION_VERSION
        for key, value in report["reference_summary"].items():
            assert stats["reference_resolution_summary"][key] == value

    def test_relationship_resolution_summary_reuses_report_summary(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        rel_summary = stats["relationship_resolution_summary"]
        assert rel_summary["version"] == RELATIONSHIP_RESOLUTION_VERSION
        assert rel_summary["registry_name"] == RELATIONSHIP_REGISTRY_NAME
        for key, value in report["relationship_summary"].items():
            assert rel_summary[key] == value

    def test_does_not_mutate_manager_or_report(self):
        manager, report = build_manager_and_report(topics=[])
        manager_before = copy.deepcopy(manager.serialize())
        report_before = copy.deepcopy(report)
        generate_compiler_statistics(manager, report)
        assert manager.serialize() == manager_before
        assert report == report_before


# --------------------------------------------------------------------------
# 3. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def _strip_timestamps(self, d):
        d = dict(d)
        d.pop("generated_at", None)
        return d

    def test_manifest_deterministic_across_independent_builds(self):
        manager1, report1 = build_manager_and_report(topics=[])
        manager2, report2 = build_manager_and_report(topics=[])
        manifest1 = self._strip_timestamps(
            generate_compiler_manifest(manager1, report1, chapter_identifier="book:ch1")
        )
        manifest2 = self._strip_timestamps(
            generate_compiler_manifest(manager2, report2, chapter_identifier="book:ch1")
        )
        assert manifest1 == manifest2

    def test_statistics_deterministic_across_independent_builds(self):
        manager1, report1 = build_manager_and_report(topics=[])
        manager2, report2 = build_manager_and_report(topics=[])
        stats1 = self._strip_timestamps(generate_compiler_statistics(manager1, report1))
        stats2 = self._strip_timestamps(generate_compiler_statistics(manager2, report2))
        assert stats1 == stats2

    def test_manifest_deterministic_across_repeated_calls_same_inputs(self):
        manager, report = build_manager_and_report(topics=[])
        manifest1 = self._strip_timestamps(generate_compiler_manifest(manager, report))
        manifest2 = self._strip_timestamps(generate_compiler_manifest(manager, report))
        assert manifest1 == manifest2

    def test_statistics_deterministic_across_repeated_calls_same_inputs(self):
        manager, report = build_manager_and_report(topics=[])
        stats1 = self._strip_timestamps(generate_compiler_statistics(manager, report))
        stats2 = self._strip_timestamps(generate_compiler_statistics(manager, report))
        assert stats1 == stats2

    def test_registry_ordering_is_insertion_order_not_alphabetical(self):
        # registry_sizes' key order should mirror manager.names()'s own
        # deterministic (registration) order -- confirms this pass didn't
        # introduce e.g. an alphabetical re-sort anywhere.
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        assert list(stats["registry_sizes"].keys()) == manager.names()


# --------------------------------------------------------------------------
# 4. Compiler state integration
# --------------------------------------------------------------------------

class TestCompilerStateIntegration:
    def test_no_manifest_before_it_is_set(self):
        assert compiler_state.get_current_compiler_manifest() is None
        assert compiler_state.has_current_compiler_manifest() is False

    def test_no_statistics_before_it_is_set(self):
        assert compiler_state.get_current_compiler_statistics() is None
        assert compiler_state.has_current_compiler_statistics() is False

    def test_set_and_get_manifest_round_trips(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report, chapter_identifier="book:ch1")
        compiler_state.set_current_compiler_manifest(manifest)
        assert compiler_state.has_current_compiler_manifest() is True
        assert compiler_state.get_current_compiler_manifest() == manifest

    def test_set_and_get_statistics_round_trips(self):
        manager, report = build_manager_and_report(topics=[])
        stats = generate_compiler_statistics(manager, report)
        compiler_state.set_current_compiler_statistics(stats)
        assert compiler_state.has_current_compiler_statistics() is True
        assert compiler_state.get_current_compiler_statistics() == stats

    def test_reset_registry_state_clears_manifest_and_statistics(self):
        manager, report = build_manager_and_report(topics=[])
        compiler_state.set_current_compiler_manifest(
            generate_compiler_manifest(manager, report)
        )
        compiler_state.set_current_compiler_statistics(
            generate_compiler_statistics(manager, report)
        )
        assert compiler_state.has_current_compiler_manifest() is True
        assert compiler_state.has_current_compiler_statistics() is True

        compiler_state.reset_registry_state()

        assert compiler_state.get_current_compiler_manifest() is None
        assert compiler_state.get_current_compiler_statistics() is None
        assert compiler_state.has_current_compiler_manifest() is False
        assert compiler_state.has_current_compiler_statistics() is False

    def test_reset_registry_state_also_still_clears_pre_existing_slots(self):
        # Backward compatibility: reset_registry_state() must still clear
        # the RegistryManager and validation report slots exactly as
        # before this phase existed.
        manager, report = build_manager_and_report(topics=[])
        compiler_state.set_current_registry_manager(manager)
        compiler_state.set_current_validation_report(report)
        compiler_state.reset_registry_state()
        assert compiler_state.get_current_registry_manager() is None
        assert compiler_state.get_current_validation_report() is None

    def test_manifest_and_statistics_are_independent_slots(self):
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        compiler_state.set_current_compiler_manifest(manifest)
        # Statistics slot untouched by setting the manifest slot.
        assert compiler_state.get_current_compiler_statistics() is None


# --------------------------------------------------------------------------
# 5. Pipeline integration (structural — no PDF I/O here; see
#    tests/test_book_orchestrator.py / tests/test_pdf_parser_and_writer.py
#    for full end-to-end pipeline coverage)
# --------------------------------------------------------------------------

class TestPipelineIntegrationShape:
    def test_pipeline_imports_generate_compiler_manifest(self):
        import pipeline
        assert hasattr(pipeline, "generate_compiler_manifest")
        assert pipeline.generate_compiler_manifest is generate_compiler_manifest

    def test_pipeline_imports_generate_compiler_statistics(self):
        import pipeline
        assert hasattr(pipeline, "generate_compiler_statistics")
        assert pipeline.generate_compiler_statistics is generate_compiler_statistics

    def test_manifest_generation_runs_after_validation_before_state_finalization(self):
        # Simulates pipeline.py's own call order: validate, THEN generate
        # manifest/statistics, THEN finalize compiler state. Confirms the
        # manifest reflects the already-fully-resolved manager (relationships
        # registry present, reference fields resolved) -- i.e. that nothing
        # about calling generate_compiler_manifest() requires
        # set_current_registry_manager() to have already run.
        assert compiler_state.has_current_registry_manager() is False
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report, chapter_identifier="book:ch1")
        statistics = generate_compiler_statistics(manager, report)
        # Still nothing "current" yet -- generate_* calls are pure reads.
        assert compiler_state.has_current_registry_manager() is False
        compiler_state.set_current_registry_manager(manager)
        compiler_state.set_current_validation_report(report)
        compiler_state.set_current_compiler_manifest(manifest)
        compiler_state.set_current_compiler_statistics(statistics)
        assert compiler_state.has_current_registry_manager() is True
        assert compiler_state.get_current_compiler_manifest()["relationship_count"] == \
            report["relationship_summary"]["total"]


# --------------------------------------------------------------------------
# 6. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_does_not_mutate_registry_items(self):
        manager, report = build_manager_and_report(topics=[])
        concepts_before = copy.deepcopy(manager.get("concepts").serialize())
        generate_compiler_manifest(manager, report)
        generate_compiler_statistics(manager, report)
        assert manager.get("concepts").serialize() == concepts_before

    def test_does_not_add_registries(self):
        manager, report = build_manager_and_report(topics=[])
        names_before = set(manager.names())
        generate_compiler_manifest(manager, report)
        generate_compiler_statistics(manager, report)
        assert set(manager.names()) == names_before

    def test_does_not_change_validation_report(self):
        manager, report = build_manager_and_report(topics=[])
        report_before = copy.deepcopy(report)
        generate_compiler_manifest(manager, report)
        generate_compiler_statistics(manager, report)
        assert report == report_before

    def test_manifest_and_statistics_not_part_of_registry_serialization(self):
        # The manifest/statistics must never leak into
        # RegistryManager.serialize() (i.e. never get inserted as a fake
        # registry item) -- they are Compiler State artifacts, not IR.
        manager, report = build_manager_and_report(topics=[])
        manifest = generate_compiler_manifest(manager, report)
        statistics = generate_compiler_statistics(manager, report)
        serialized = manager.serialize()
        assert manifest not in serialized["registries"].values()
        assert statistics not in serialized["registries"].values()
        assert "compiler_manifest" not in serialized
        assert "compiler_statistics" not in serialized

    def test_existing_registry_manager_and_validation_report_slots_unaffected(self):
        # compiler_state's pre-existing get/set/has trio for
        # RegistryManager and ValidationReport keep working exactly as
        # before this phase's additions.
        manager, report = build_manager_and_report(topics=[])
        compiler_state.set_current_registry_manager(manager)
        compiler_state.set_current_validation_report(report)
        assert compiler_state.get_current_registry_manager() is manager
        assert compiler_state.get_current_validation_report() == report


# --------------------------------------------------------------------------
# 7. Dataclass sanity (to_dict() shape)
# --------------------------------------------------------------------------

class TestDataclassShapes:
    def test_compiler_manifest_to_dict_matches_generate_compiler_manifest(self):
        manager, report = build_manager_and_report(topics=[])
        manifest_dict = generate_compiler_manifest(manager, report, chapter_identifier="x")
        manifest_obj = CompilerManifest(**manifest_dict)
        assert manifest_obj.to_dict() == manifest_dict

    def test_compiler_statistics_to_dict_matches_generate_compiler_statistics(self):
        manager, report = build_manager_and_report(topics=[])
        stats_dict = generate_compiler_statistics(manager, report)
        stats_obj = CompilerStatistics(**stats_dict)
        assert stats_obj.to_dict() == stats_dict