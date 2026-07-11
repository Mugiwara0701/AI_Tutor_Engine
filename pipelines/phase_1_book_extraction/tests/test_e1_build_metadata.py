"""
tests/test_e1_build_metadata.py — unit tests for Phase E1: Build
Metadata (build_metadata/), and its pipeline.py / build_metadata.state
integration.

This file does NOT re-test Compiler IR construction/validation/
fingerprinting/finalization (compiler/, already covered by
tests/test_c4_1_manifest_statistics.py, tests/test_c4_2_fingerprints_
readiness.py, tests/test_c4_3_finalization.py), Knowledge Graph
construction/validation/fingerprinting/finalization (knowledge_graph/,
already covered by the same-shaped tests one package over), System
Integrity (tests/test_d1_system_integrity.py), Determinism
(tests/test_d2_determinism.py), or Release Readiness
(tests/test_d3_release_readiness.py) directly -- it treats all of those
as frozen, already-tested dependencies. Two kinds of fixtures are used
below:

  * Hand-built, minimal dicts for the pure aggregation unit tests
    (CompilerMetadata / GraphMetadata / CompilationMetadata /
    ConfigurationMetadata / VersionMetadata / BuildMetadata shape and
    missing-artifact-handling) -- these exercise
    build_metadata.build.generate_compiler_metadata() /
    generate_graph_metadata() / generate_build_metadata() and
    build_metadata.compilation_metadata.generate_compilation_metadata()/
    build_metadata.configuration_metadata.
    generate_configuration_metadata()/build_metadata.version_metadata.
    generate_version_metadata() directly, without paying for a full
    Phase B->D3 pipeline run per case.
  * A real, full Phase B (Compiler IR) -> Phase C (Knowledge Graph) ->
    Phase D1 -> Phase D2 -> Phase D3 pipeline run
    (`build_full_pipeline_state()`, the same shape tests/
    test_d3_release_readiness.py's own same-named helper already
    establishes, duplicated here rather than cross-imported -- this repo
    has no tests/__init__.py, so tests/ is not a package, and every
    existing test file already follows this "no test-to-test import
    dependency" convention) for the pipeline-integration-shaped tests
    (state integration, pipeline integration, determinism of
    ConfigurationMetadata's own fingerprint, read-only behavior,
    backward compatibility).
"""
from __future__ import annotations

import copy
import os
import tempfile
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
    graph_id as expected_graph_id,
    graph_urn as expected_graph_urn,
)
from knowledge_graph.schema import KnowledgeGraphMetadata
from knowledge_graph.fingerprints import generate_graph_fingerprints
from knowledge_graph.finalize import finalize_knowledge_graph

from validation.system_integrity import validate_system_integrity
from validation.determinism import validate_determinism
from validation.release import finalize_release

from build_metadata.build import (
    BUILD_METADATA_VERSION,
    generate_compiler_metadata,
    generate_graph_metadata,
    generate_build_metadata,
    finalize_build_metadata,
)
from build_metadata.compilation_metadata import generate_compilation_metadata
from build_metadata.configuration_metadata import generate_configuration_metadata
from build_metadata.version_metadata import generate_version_metadata
from build_metadata import state as build_metadata_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- hand-built, minimal fixtures for the pure aggregation tests.
# --------------------------------------------------------------------------

def _compiler_metadata_kwargs(**overrides):
    kwargs = dict(
        compiler_manifest={"compiler_version": "B5.1", "schema_version": "2.0.0",
                            "build_version": "1.0.0"},
        compiler_statistics={"total_objects": 3},
        registry_fingerprints={"topics": "fp1"},
        compiler_fingerprint="cfp123",
        compiler_readiness_report={"ready": True, "warnings": []},
        compiler_build_summary={"build_status": "READY"},
        final_compiler_status="READY",
    )
    kwargs.update(overrides)
    return kwargs


def _graph_metadata_kwargs(**overrides):
    kwargs = dict(
        knowledge_graph_manifest={"graph_schema_version": "C0.1", "identity_version": "C0.1"},
        knowledge_graph_statistics={"total_nodes": 3},
        registry_fingerprints={"nodes": "gfp1"},
        graph_fingerprint="gfp456",
        knowledge_graph_readiness_report={"ready": True, "warnings": []},
        knowledge_graph_build_summary={"build_status": "READY"},
        final_graph_status="READY",
    )
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------
# Helpers -- full Phase B->D3 pipeline fixture (same shape tests/
# test_d3_release_readiness.py's own build_full_pipeline_state()
# already establishes, duplicated here, not imported).
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
    """One-shot: Phase B (Compiler IR) -> Phase C (Knowledge Graph) ->
    Phase D1 (System Integrity) -> Phase D2 (Determinism) -> Phase D3
    (Release Readiness), exactly the sequence pipeline.py runs
    immediately before its own Phase E1 integration point. Returns a
    dict of every artifact finalize_build_metadata() consumes, keyed
    the same way that function's own parameter names read."""
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
        graph_id=expected_graph_id(namespace),
        graph_urn=expected_graph_urn(namespace),
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
        "compiler_validation_report": compiler_validation_report,
        "compiler_manifest": compiler_manifest,
        "compiler_statistics": compiler_statistics,
        "compiler_registry_fingerprints": compiler_fp_results["registry_fingerprints"],
        "compiler_fingerprint": compiler_fp_results["compiler_fingerprint"],
        "compiler_readiness_report": compiler_fp_results["readiness_report"],
        "compiler_build_summary": compiler_finalization["build_summary"],
        "final_compiler_status": compiler_finalization["final_status"],
        "graph_registry_manager": graph_manager,
        "knowledge_graph_validation_report": kg_validation_report,
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
    release_finalization = finalize_release(
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
    state["release_readiness_report"] = release_finalization["release_readiness_report"]
    state["release_status"] = release_finalization["release_status"]
    return state


def run_finalize_build_metadata(state: dict, **overrides) -> dict:
    """Calls finalize_build_metadata() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names -- exactly pipeline.py's own Phase
    E1 integration-point call shape."""
    kwargs = dict(
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
    kwargs.update(overrides)
    return finalize_build_metadata(**kwargs)


@pytest.fixture(autouse=True)
def _reset_build_metadata_state():
    """Every test starts and ends with a clean build_metadata.state
    module -- mirrors tests/test_d3_release_readiness.py's own
    _reset_release_state fixture, one artifact over."""
    build_metadata_state.reset_build_metadata_state()
    yield
    build_metadata_state.reset_build_metadata_state()


# --------------------------------------------------------------------------
# 1. CompilerMetadata aggregation
# --------------------------------------------------------------------------

class TestCompilerMetadata:
    def test_aggregates_every_field_verbatim(self):
        kwargs = _compiler_metadata_kwargs()
        result = generate_compiler_metadata(**kwargs)
        assert result["compiler_manifest"] == kwargs["compiler_manifest"]
        assert result["compiler_statistics"] == kwargs["compiler_statistics"]
        assert result["registry_fingerprints"] == kwargs["registry_fingerprints"]
        assert result["compiler_fingerprint"] == kwargs["compiler_fingerprint"]
        assert result["compiler_readiness_report"] == kwargs["compiler_readiness_report"]
        assert result["compiler_build_summary"] == kwargs["compiler_build_summary"]
        assert result["final_compiler_status"] == kwargs["final_compiler_status"]

    def test_missing_artifacts_become_none_not_an_error(self):
        result = generate_compiler_metadata(
            compiler_manifest=None, compiler_statistics=None,
            registry_fingerprints=None, compiler_fingerprint=None,
            compiler_readiness_report=None, compiler_build_summary=None,
            final_compiler_status=None,
        )
        assert result["compiler_manifest"] is None
        assert result["final_compiler_status"] is None

    def test_never_mutates_inputs(self):
        kwargs = _compiler_metadata_kwargs()
        before = copy.deepcopy(kwargs)
        generate_compiler_metadata(**kwargs)
        assert kwargs == before


# --------------------------------------------------------------------------
# 2. GraphMetadata aggregation
# --------------------------------------------------------------------------

class TestGraphMetadata:
    def test_aggregates_every_field_verbatim(self):
        kwargs = _graph_metadata_kwargs()
        result = generate_graph_metadata(**kwargs)
        assert result["knowledge_graph_manifest"] == kwargs["knowledge_graph_manifest"]
        assert result["knowledge_graph_statistics"] == kwargs["knowledge_graph_statistics"]
        assert result["registry_fingerprints"] == kwargs["registry_fingerprints"]
        assert result["graph_fingerprint"] == kwargs["graph_fingerprint"]
        assert result["knowledge_graph_readiness_report"] == kwargs["knowledge_graph_readiness_report"]
        assert result["knowledge_graph_build_summary"] == kwargs["knowledge_graph_build_summary"]
        assert result["final_graph_status"] == kwargs["final_graph_status"]

    def test_missing_artifacts_become_none_not_an_error(self):
        result = generate_graph_metadata(
            knowledge_graph_manifest=None, knowledge_graph_statistics=None,
            registry_fingerprints=None, graph_fingerprint=None,
            knowledge_graph_readiness_report=None, knowledge_graph_build_summary=None,
            final_graph_status=None,
        )
        assert result["knowledge_graph_manifest"] is None
        assert result["final_graph_status"] is None


# --------------------------------------------------------------------------
# 3. CompilationMetadata -- operational, never fingerprinted
# --------------------------------------------------------------------------

class TestCompilationMetadata:
    def test_missing_pdf_path_is_handled_gracefully(self):
        result = generate_compilation_metadata(
            pdf_path=None, compilation_start=None, compilation_end=None,
        )
        assert result["source_pdf"] is None
        assert result["source_pdf_content_hash"] is None

    def test_content_hash_is_computed_from_real_file(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake pdf bytes for hashing")
            path = f.name
        try:
            result = generate_compilation_metadata(pdf_path=path)
            assert result["source_pdf_content_hash"] is not None
            assert len(result["source_pdf_content_hash"]) == 64  # sha256 hex digest
            assert result["source_pdf"] == os.path.basename(path)
        finally:
            os.unlink(path)

    def test_nonexistent_pdf_path_does_not_raise(self):
        result = generate_compilation_metadata(pdf_path="/nonexistent/path/does-not-exist.pdf")
        assert result["source_pdf_content_hash"] is None

    def test_processing_time_falls_back_to_start_end_difference(self):
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
        result = generate_compilation_metadata(
            pdf_path=None, compilation_start=start, compilation_end=end,
        )
        assert result["processing_time_seconds"] == 10.0

    def test_explicit_processing_time_is_not_overridden(self):
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
        result = generate_compilation_metadata(
            pdf_path=None, compilation_start=start, compilation_end=end,
            processing_time_seconds=3.14,
        )
        assert result["processing_time_seconds"] == 3.14

    def test_cli_invocation_carries_run_arguments(self):
        result = generate_compilation_metadata(
            pdf_path=None, use_vlm=False, page_batch_size=8, force=True,
        )
        assert result["cli_invocation"] == {
            "use_vlm": False, "page_batch_size": 8, "force": True,
        }


# --------------------------------------------------------------------------
# 4. ConfigurationMetadata -- deterministic, single fingerprint
# --------------------------------------------------------------------------

class TestConfigurationMetadata:
    def test_fingerprint_is_deterministic_across_calls(self):
        first = generate_configuration_metadata()
        second = generate_configuration_metadata()
        assert first["configuration_fingerprint"] == second["configuration_fingerprint"]

    def test_fingerprint_excludes_generated_at(self):
        first = generate_configuration_metadata()
        second = generate_configuration_metadata()
        # generated_at is a wall-clock timestamp; it may differ between
        # the two calls above (rare, but possible), yet the fingerprint
        # must never change as a result -- this is exactly what
        # canonicalization.py's own VOLATILE_KEYS stripping guarantees.
        assert first["configuration_fingerprint"] == second["configuration_fingerprint"]

    def test_prompt_versions_come_from_task_registry(self):
        result = generate_configuration_metadata()
        from prompt_manager.task_registry import TASKS
        assert result["prompt_versions"] == {
            name: spec.current_version for name, spec in TASKS.items()
        }

    def test_reuses_shared_canonicalization_utilities(self):
        from canonicalization import canonical_json, sha256_hexdigest
        result = generate_configuration_metadata()
        payload = {
            "compiler_config": result["compiler_config"],
            "model_config": result["model_config"],
            "prompt_versions": result["prompt_versions"],
            "extraction_policy": result["extraction_policy"],
            "deterministic_thresholds": result["deterministic_thresholds"],
            "feature_flags": result["feature_flags"],
        }
        expected = sha256_hexdigest(canonical_json(payload))
        assert result["configuration_fingerprint"] == expected

    def test_never_participates_in_compilation_metadata(self):
        # CompilationMetadata (operational) and ConfigurationMetadata
        # (deterministic) are computed independently -- CompilationMetadata
        # never receives or references configuration_fingerprint.
        compilation = generate_compilation_metadata(pdf_path=None)
        assert "configuration_fingerprint" not in compilation


# --------------------------------------------------------------------------
# 5. VersionMetadata -- aggregation only, never duplicates a version field
# --------------------------------------------------------------------------

class TestVersionMetadata:
    def test_aggregates_from_manifests_and_owning_modules(self):
        from compiler.finalize import FINALIZE_VERSION as COMPILER_FINALIZE_VERSION
        from knowledge_graph.finalize import GRAPH_FINALIZE_VERSION
        from validation.release import RELEASE_VERSION

        result = generate_version_metadata(
            compiler_manifest={"compiler_version": "B5.1", "schema_version": "2.0.0",
                                "build_version": "1.0.0"},
            knowledge_graph_manifest={"graph_schema_version": "C0.1", "identity_version": "C0.1"},
            final_compiler_status="READY",
            final_graph_status="READY",
            release_status="READY",
        )
        assert result["compiler_version"] == "B5.1"
        assert result["schema_version"] == "2.0.0"
        assert result["build_version"] == "1.0.0"
        assert result["graph_schema_version"] == "C0.1"
        assert result["identity_version"] == "C0.1"
        assert result["phase_versions"]["compiler_finalize"] == COMPILER_FINALIZE_VERSION
        assert result["phase_versions"]["graph_finalize"] == GRAPH_FINALIZE_VERSION
        assert result["phase_versions"]["release"] == RELEASE_VERSION
        assert result["phase_completion"] == {
            "compiler": "READY", "knowledge_graph": "READY", "release": "READY",
        }

    def test_missing_manifests_do_not_raise(self):
        result = generate_version_metadata(
            compiler_manifest=None, knowledge_graph_manifest=None,
            final_compiler_status=None, final_graph_status=None, release_status=None,
        )
        assert result["compiler_version"] is None
        assert result["graph_schema_version"] is None


# --------------------------------------------------------------------------
# 6. BuildMetadata -- top-level aggregation
# --------------------------------------------------------------------------

class TestBuildMetadataAssembly:
    def test_wraps_all_five_sub_blocks(self):
        compiler_metadata = generate_compiler_metadata(**_compiler_metadata_kwargs())
        graph_metadata = generate_graph_metadata(**_graph_metadata_kwargs())
        compilation_metadata = generate_compilation_metadata(pdf_path=None)
        configuration_metadata = generate_configuration_metadata()
        version_metadata = generate_version_metadata(
            compiler_manifest=None, knowledge_graph_manifest=None,
            final_compiler_status=None, final_graph_status=None, release_status=None,
        )
        result = generate_build_metadata(
            compiler_metadata=compiler_metadata,
            graph_metadata=graph_metadata,
            compilation_metadata=compilation_metadata,
            configuration_metadata=configuration_metadata,
            version_metadata=version_metadata,
        )
        assert result["compiler_metadata"] == compiler_metadata
        assert result["graph_metadata"] == graph_metadata
        assert result["compilation_metadata"] == compilation_metadata
        assert result["configuration_metadata"] == configuration_metadata
        assert result["version_metadata"] == version_metadata
        assert result["build_metadata_version"] == BUILD_METADATA_VERSION
        assert "generated_at" in result


# --------------------------------------------------------------------------
# 7. finalize_build_metadata() -- full pipeline integration
# --------------------------------------------------------------------------

class TestFinalizeBuildMetadataPipelineIntegration:
    def test_full_pipeline_produces_complete_build_metadata(self):
        state = build_full_pipeline_state()
        result = run_finalize_build_metadata(state)
        build_metadata = result["build_metadata"]

        assert build_metadata["compiler_metadata"]["compiler_fingerprint"] == state["compiler_fingerprint"]
        assert build_metadata["compiler_metadata"]["final_compiler_status"] == state["final_compiler_status"]
        assert build_metadata["graph_metadata"]["graph_fingerprint"] == state["knowledge_graph_fingerprint"]
        assert build_metadata["graph_metadata"]["final_graph_status"] == state["final_graph_status"]
        assert build_metadata["version_metadata"]["phase_completion"]["release"] == state["release_status"]
        assert build_metadata["compilation_metadata"]["processing_time_seconds"] == 5.0
        assert "configuration_fingerprint" in build_metadata["configuration_metadata"]

    def test_read_only_over_every_input(self):
        # Read-only requirement: finalize_build_metadata() must never
        # mutate any Phase B-D3 artifact it aggregates.
        state = build_full_pipeline_state()
        before = copy.deepcopy({
            k: v for k, v in state.items()
            if k not in ("compiler_registry_manager", "graph_registry_manager")
        })
        run_finalize_build_metadata(state)
        after = {
            k: v for k, v in state.items()
            if k not in ("compiler_registry_manager", "graph_registry_manager")
        }
        assert after == before

    def test_never_mutates_registry_managers(self):
        state = build_full_pipeline_state()
        compiler_names_before = sorted(state["compiler_registry_manager"].names())
        graph_names_before = sorted(state["graph_registry_manager"].names())
        run_finalize_build_metadata(state)
        assert sorted(state["compiler_registry_manager"].names()) == compiler_names_before
        assert sorted(state["graph_registry_manager"].names()) == graph_names_before


# --------------------------------------------------------------------------
# 8. State integration -- build_metadata.state
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_has_current_is_false_before_set(self):
        assert build_metadata_state.has_current_build_metadata() is False
        assert build_metadata_state.get_current_build_metadata() is None

    def test_set_then_get_returns_same_object(self):
        state = build_full_pipeline_state()
        result = run_finalize_build_metadata(state)
        build_metadata_state.set_current_build_metadata(result["build_metadata"])
        assert build_metadata_state.has_current_build_metadata() is True
        assert build_metadata_state.get_current_build_metadata() is result["build_metadata"]

    def test_reset_clears_state(self):
        state = build_full_pipeline_state()
        result = run_finalize_build_metadata(state)
        build_metadata_state.set_current_build_metadata(result["build_metadata"])
        build_metadata_state.reset_build_metadata_state()
        assert build_metadata_state.has_current_build_metadata() is False
        assert build_metadata_state.get_current_build_metadata() is None


# --------------------------------------------------------------------------
# 9. Pipeline integration -- pipeline.py wiring
# --------------------------------------------------------------------------

class TestPipelineWiring:
    def test_pipeline_imports_build_metadata_integration_point(self):
        import pipeline
        assert hasattr(pipeline, "finalize_build_metadata")
        assert hasattr(pipeline, "build_metadata_state")

    def test_process_chapter_source_calls_e1_after_d3(self):
        # Static check that the Phase E1 call site is wired in after the
        # Phase D3 (release_finalization) call site, without needing a
        # full PDF fixture to exercise process_chapter() end-to-end.
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        d3_index = source.index("finalize_release(")
        e1_index = source.index("finalize_build_metadata(")
        assert d3_index < e1_index

    def test_e1_call_site_never_touches_chapter_dict(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e1_index = source.index("finalize_build_metadata(")
        chapter_dict_index = source.index("chapter_dict = json_writer.assemble_chapter_json")
        # The Phase E1 call happens before Chapter JSON assembly, and no
        # build_metadata result is threaded into assemble_chapter_json's
        # own call below (read-only / never serialized requirement).
        assert e1_index < chapter_dict_index
        assemble_call = source[chapter_dict_index:]
        assert "build_metadata" not in assemble_call.split(")")[0]


# --------------------------------------------------------------------------
# 10. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_release_state_untouched_by_e1(self):
        # E1 must not read from or write to validation.release_state --
        # it only reads the already-in-scope release_status value the
        # caller passes in explicitly (pipeline.py's own local variable).
        from validation import release_state
        release_state.reset_release_state()
        state = build_full_pipeline_state()
        run_finalize_build_metadata(state)
        # finalize_build_metadata() never calls release_state.set_*, so
        # the module-level state here must remain exactly as
        # build_full_pipeline_state() (which itself never sets it
        # either) left it: unset.
        assert release_state.has_current_release_readiness_report() is False

    def test_compiler_manifest_fields_unchanged(self):
        state = build_full_pipeline_state()
        manifest_before = copy.deepcopy(state["compiler_manifest"])
        run_finalize_build_metadata(state)
        assert state["compiler_manifest"] == manifest_before