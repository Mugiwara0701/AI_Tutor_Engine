"""
tests/test_audit_refinements.py — unit tests for the post-Phase-B5.3
audit-findings resolution pass (see docs/phase_b_completion_report.md
§5a).

Covers, additively, only what changed in this refinement pass:

1. `build_status` disambiguation -- CompilerManifest now also exposes
   `manifest_generation_status` (identical value to its own
   `build_status`), and CompilerBuildSummary's `build_status` continues
   to carry the final READY/READY_WITH_WARNINGS/FAILED verdict,
   unchanged.
2. Dead code -- compiler/build.py no longer has an unused
   `registry_summary` local inside generate_compiler_statistics(), and
   generate_compiler_statistics() output is unaffected by its removal.
3. FINALIZE_VERSION is now embedded in CompilerBuildSummary as
   `finalize_version`.
4. compiler/__init__.py now exports the full B0-B5.3 public surface
   (previously only B0-B2 symbols were exported).

Per task instructions, these tests are generated only: they are not
executed here as part of authoring them, and no claim is made about
whether they currently pass in the caller's environment beyond the
ad-hoc smoke checks performed during development.
"""
from __future__ import annotations

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import enrich_registries
from compiler.normalization import normalize_registries
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships
from compiler.validation import validate_compiler_state
from compiler.build import (
    generate_compiler_manifest,
    generate_compiler_statistics,
    CompilerManifest,
)
from compiler.fingerprints import generate_compiler_fingerprints
from compiler.finalize import (
    FINALIZE_VERSION,
    CompilerBuildSummary,
    finalize_compiler_build,
)
from compiler import state as compiler_state


# --------------------------------------------------------------------------
# Helpers -- same minimal canonical envelope shape as tests/test_build.py /
# tests/test_finalize.py.
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


def build_full_pipeline_artifacts(topics=None):
    """Runs the full B1-B5.3 pipeline over a small fixture and returns
    every intermediate artifact, mirroring pipeline.py's own call order."""
    manager = create_registry_manager()
    populate_registries(manager, concepts=[make_concept()])
    enrich_registries(manager)
    normalize_registries(manager)
    resolve_references(manager, topics=topics)
    resolve_relationships(manager, topics=topics)
    report = validate_compiler_state(manager, topics=topics)
    manifest = generate_compiler_manifest(manager, report)
    statistics = generate_compiler_statistics(manager, report)
    fp = generate_compiler_fingerprints(
        manager, manifest=manifest, statistics=statistics, validation_report=report
    )
    result = finalize_compiler_build(
        manager,
        validation_report=report,
        manifest=manifest,
        statistics=statistics,
        registry_fingerprints=fp["registry_fingerprints"],
        compiler_fingerprint=fp["compiler_fingerprint"],
        readiness_report=fp["readiness_report"],
    )
    return manager, report, manifest, statistics, fp, result


@pytest.fixture(autouse=True)
def _reset_compiler_state():
    compiler_state.reset_registry_state()
    yield
    compiler_state.reset_registry_state()


# --------------------------------------------------------------------------
# 1. build_status disambiguation
# --------------------------------------------------------------------------

class TestBuildStatusDisambiguation:
    def test_manifest_still_exposes_build_status_generated(self):
        # Backward compatibility: the original field/value is untouched.
        _, _, manifest, _, _, _ = build_full_pipeline_artifacts()
        assert manifest["build_status"] == "generated"

    def test_manifest_exposes_new_manifest_generation_status(self):
        _, _, manifest, _, _, _ = build_full_pipeline_artifacts()
        assert manifest["manifest_generation_status"] == "generated"

    def test_manifest_generation_status_matches_build_status(self):
        _, _, manifest, _, _, _ = build_full_pipeline_artifacts()
        assert manifest["manifest_generation_status"] == manifest["build_status"]

    def test_manifest_dataclass_has_new_field(self):
        field_names = {f.name for f in CompilerManifest.__dataclass_fields__.values()}
        assert "manifest_generation_status" in field_names
        assert "build_status" in field_names

    def test_build_summary_build_status_is_final_status_not_generated(self):
        # CompilerBuildSummary.build_status must remain the final
        # READY/READY_WITH_WARNINGS/FAILED verdict -- never the string
        # "generated" that CompilerManifest.build_status carries.
        _, _, _, _, _, result = build_full_pipeline_artifacts()
        assert result["build_summary"]["build_status"] == result["final_status"]
        assert result["build_summary"]["build_status"] != "generated"

    def test_manifest_and_build_summary_build_status_differ_in_meaning(self):
        _, _, manifest, _, _, result = build_full_pipeline_artifacts()
        # Same field name, deliberately different values/meanings on the
        # two artifacts -- this is the audit finding being resolved, not
        # a bug: assert both keep their own distinct semantics.
        assert manifest["build_status"] == "generated"
        assert result["build_summary"]["build_status"] in {
            "READY", "READY_WITH_WARNINGS", "FAILED",
        }


# --------------------------------------------------------------------------
# 2. Dead code removal (registry_summary local in generate_compiler_statistics)
# --------------------------------------------------------------------------

class TestDeadCodeRemoved:
    def test_generate_compiler_statistics_unaffected_by_removal(self):
        # generate_compiler_statistics() must still work correctly and
        # still expose every documented field -- the removed local was
        # provably unused (never read after assignment).
        manager, report, _, statistics, _, _ = build_full_pipeline_artifacts()
        assert isinstance(statistics, dict)
        required = {
            "registry_sizes", "relationships_by_type", "total_relationships",
            "total_objects", "validation_summary", "enrichment_summary",
            "normalization_summary", "reference_resolution_summary",
            "relationship_resolution_summary",
        }
        assert required.issubset(statistics.keys())

    def test_build_module_source_has_no_unused_registry_summary_local(self):
        import inspect
        from compiler import build as build_module
        source = inspect.getsource(build_module.generate_compiler_statistics)
        assert "registry_summary" not in source


# --------------------------------------------------------------------------
# 3. FINALIZE_VERSION embedding
# --------------------------------------------------------------------------

class TestFinalizeVersionEmbedded:
    def test_build_summary_contains_finalize_version(self):
        _, _, _, _, _, result = build_full_pipeline_artifacts()
        assert result["build_summary"]["finalize_version"] == FINALIZE_VERSION

    def test_build_summary_dataclass_has_finalize_version_field(self):
        field_names = {f.name for f in CompilerBuildSummary.__dataclass_fields__.values()}
        assert "finalize_version" in field_names

    def test_finalize_version_is_nonempty_string(self):
        assert isinstance(FINALIZE_VERSION, str)
        assert FINALIZE_VERSION


# --------------------------------------------------------------------------
# 4. Package export consistency (compiler/__init__.py)
# --------------------------------------------------------------------------

class TestPackageExportsConsistency:
    def test_package_exports_relationship_symbols(self):
        import compiler
        assert hasattr(compiler, "resolve_relationships")
        assert hasattr(compiler, "RELATIONSHIP_RESOLUTION_VERSION")
        assert hasattr(compiler, "RelationshipRegistry")

    def test_package_exports_validation_symbols(self):
        import compiler
        assert hasattr(compiler, "validate_compiler_state")
        assert hasattr(compiler, "VALIDATION_VERSION")
        assert hasattr(compiler, "ValidationReport")

    def test_package_exports_build_symbols(self):
        import compiler
        assert hasattr(compiler, "generate_compiler_manifest")
        assert hasattr(compiler, "generate_compiler_statistics")
        assert hasattr(compiler, "CompilerManifest")
        assert hasattr(compiler, "CompilerStatistics")

    def test_package_exports_fingerprints_symbols(self):
        import compiler
        assert hasattr(compiler, "generate_compiler_fingerprints")
        assert hasattr(compiler, "CompilerReadinessReport")

    def test_package_exports_finalize_symbols(self):
        import compiler
        assert hasattr(compiler, "finalize_compiler_build")
        assert hasattr(compiler, "CompilerBuildSummary")
        assert hasattr(compiler, "FINALIZE_VERSION")

    def test_all_names_in_dunder_all_are_actually_importable(self):
        import compiler
        missing = [name for name in compiler.__all__ if not hasattr(compiler, name)]
        assert missing == []

    def test_dunder_all_has_no_duplicates(self):
        import compiler
        assert len(compiler.__all__) == len(set(compiler.__all__))


# --------------------------------------------------------------------------
# 5. No functional/behavioral regressions from this refinement pass
# --------------------------------------------------------------------------

class TestNoRegressions:
    def test_compiler_ir_and_pipeline_still_produce_same_shape(self):
        # A basic end-to-end smoke check that the full B1-B5.3 pipeline
        # still runs to completion and produces the same overall shape
        # of artifacts as before this refinement pass.
        manager, report, manifest, statistics, fp, result = build_full_pipeline_artifacts()
        assert report["status"] in {"pass", "fail"}
        assert isinstance(manifest, dict)
        assert isinstance(statistics, dict)
        assert set(result.keys()) == {"build_summary", "final_status"}
        assert result["final_status"] in {"READY", "READY_WITH_WARNINGS", "FAILED"}
