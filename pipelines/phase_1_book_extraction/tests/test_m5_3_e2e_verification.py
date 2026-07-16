"""
tests/test_m5_3_e2e_verification.py — Milestone 5.3: End-to-End
Verification & Regression Validation.

SCOPE. M5.3's own instructions rule out modifying architecture, schema,
DST models, the builder, the validation engine, serialization, artifact
registration, pipeline integration, build metadata, or manifest design
-- this file adds verification only, exactly like M5.1/M5.2's own test
files (tests/test_pipeline_dst_integration.py, tests/
test_m5_2_dst_artifact_registration.py), whose helper/fixture
conventions this file reuses rather than reinvents.

WHAT "END-TO-END" MEANS HERE, AND WHAT IT CANNOT MEAN IN THIS
ENVIRONMENT. A true end-to-end run would be `pipeline.py` processing a
real PDF: OCR -> layout detection -> VLM semantics -> Chapter JSON ->
DST -> artifact registration -> build metadata -> manifest. That is not
executable in this environment: `pipeline.py` imports ~17 submodules
under `modules/` (pdf_parser, layout_detector, ocr_engine, vlm_inference,
...) and `book_orchestrator.py`/`runtime.runtime.CompilerRuntime` import
further packages (`modules`, `config`, `storage`, `runtime`), none of
which are present in the uploaded archive (confirmed: `pytest
--collect-only` on this suite still raises `ModuleNotFoundError` for
`modules` and `runtime` -- see the M5.2 review's test-results table).
Fabricating stand-ins for a 17-module PDF/VLM extraction pipeline and a
not-yet-provided runtime layer would mean verifying against invented
behavior, not the real compiler flow -- the opposite of what "using the
real compiler flow" is supposed to guarantee.

What IS executable, and what this file actually does: every module
between "a compiled chapter's registries already exist" and "a Build
Manifest is written" IS present and real (compiler/, document_structure_
tree/, artifact_manager/, build_metadata/) -- this is the exact
boundary tests/test_pipeline_dst_integration.py's own module docstring
already draws for M5.1 ("pipeline.py itself cannot be imported in
isolation ... this module does not import it. Instead it exercises
exactly the sequence Milestone 5.1's own integration block runs, in the
same order, against the same real collaborators"). This file extends
that same real sequence one milestone further: Compiler build (B1-B5.3,
real) -> DST build (M1-M5.2, real) -> artifact registration (real) ->
build_metadata aggregation (real) -> Build Manifest (real). No stand-in
is used anywhere in this chain; the only thing not exercised is PDF/VLM
extraction and CompilerRuntime's own orchestration loop, both flagged
explicitly below and in the conformance review as blocked on
not-yet-provided infrastructure, not silently skipped.
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
from compiler.finalize import finalize_compiler_build
from compiler import state as compiler_state

from document_structure_tree import state as dst_state
from document_structure_tree.artifact import generate_artifact
from document_structure_tree.builder import build_tree_from_chapter_json
from document_structure_tree.enums import ValidationStatus as DSTValidationStatus
from document_structure_tree.primitives import ChapterId, CompilerVersion, SchemaVersion
from document_structure_tree.registry_snapshot import CompilerRegistrySnapshot
from schemas.chapter_schema import ChapterJSON, Definition, Figure, TopicNode

from artifact_manager.build import build_reference_snapshot, create_build
from artifact_manager.manifest import generate_build_manifest

from build_metadata.build import (
    attach_dst_metadata,
    finalize_build_metadata,
    generate_dst_metadata,
)
from build_metadata import state as build_metadata_state


CHAPTER_REFERENCE = "class-11-physics:chap-07"
DST_SCHEMA_VERSION = SchemaVersion("1.1.0")
DST_COMPILER_VERSION = CompilerVersion("1.0.0")


# ---------------------------------------------------------------------------
# Fixtures — reuse of tests/test_finalize.py's and
# tests/test_pipeline_dst_integration.py's own conventions, one chapter
# whose compiler registries and DST content ids agree with each other
# (so both artifacts validate 'pass' for the happy-path tests).
# ---------------------------------------------------------------------------

def make_concept(id_="c1", name="Newton's Second Law", topic_ids=None, **extra):
    d = {
        "id": id_, "urn": f"urn:concept:{id_}", "object_type": "concept",
        "schema_version": "1.0.0", "provenance": {"source": "test"},
        "validation_status": "validated",
        "creation_metadata": {"compiler_version": "1.0.0"},
        "name": name, "aliases": [], "topic_ids": topic_ids or [],
    }
    d.update(extra)
    return d


def make_definition(id_="def-1", term="Force", topic_ids=None, **extra):
    d = {
        "id": id_, "urn": f"urn:definition:{id_}", "object_type": "definition",
        "schema_version": "1.0.0", "provenance": {"source": "test"},
        "validation_status": "validated",
        "creation_metadata": {"compiler_version": "1.0.0"},
        "term": term, "topic_ids": topic_ids or [],
    }
    d.update(extra)
    return d


def make_topic(id_="h1", title="Newton's Second Law", **extra):
    d = {
        "id": id_, "urn": f"urn:topic:{id_}", "object_type": "topic",
        "schema_version": "1.0.0", "provenance": {"source": "test"},
        "validation_status": "validated",
        "creation_metadata": {"compiler_version": "1.0.0"},
        "title": title,
    }
    d.update(extra)
    return d


def make_figure(id_="fig-1", **extra):
    d = {
        "id": id_, "urn": f"urn:figure:{id_}", "object_type": "figure",
        "schema_version": "1.0.0", "provenance": {"source": "test"},
        "validation_status": "validated",
        "creation_metadata": {"compiler_version": "1.0.0"},
    }
    d.update(extra)
    return d


def _well_formed_chapter_json() -> ChapterJSON:
    topics = [
        TopicNode(
            id="h1", title="Newton's Second Law", numbering="4.1", parent=None,
            page_start=10, page_end=12, reading_order=0,
            bbox={"x0": 0.0, "y0": 100.0, "x1": 0.0, "y1": 0.0, "page": 10},
            definitions=["def-1"],
        ),
        TopicNode(
            id="h2", title="Momentum", numbering="4.1.1", parent="h1",
            page_start=11, page_end=11, reading_order=1,
            bbox={"x0": 0.0, "y0": 50.0, "x1": 0.0, "y1": 0.0, "page": 11},
            figures=["fig-1"],
        ),
    ]
    return ChapterJSON(
        topics=topics,
        definitions=[Definition(id="def-1", object_type="definition", term="Force", page=10, topic="h1")],
        figures=[Figure(id="fig-1", object_type="figure", page=11, topic="h2")],
    )


def run_full_compiler_flow(topics=None):
    """B1-B5.3, real: registries -> enrich -> normalize -> resolve refs
    -> resolve relationships -> validate -> manifest -> statistics ->
    fingerprints -> finalize. Mirrors tests/test_finalize.py's own
    build_full_compiler_state()/finalize_compiler_build() sequence,
    additionally registering every artifact into compiler.state exactly
    as pipeline.py's own process_chapter() does, so
    build_reference_snapshot() has a real compiler_ir_reference to read.
    """
    topics = topics if topics is not None else [
        make_topic(id_="h1", title="Newton's Second Law"),
        make_topic(id_="h2", title="Momentum"),
    ]
    manager = create_registry_manager()
    populate_registries(
        manager,
        topics=topics,
        concepts=[make_concept()],
        definitions=[make_definition()],
        figures=[make_figure(id_="fig-1")],
    )
    enrich_registries(manager)
    normalize_registries(manager)
    resolve_references(manager, topics=topics)
    resolve_relationships(manager, topics=topics)
    validation_report = validate_compiler_state(manager, topics=topics)
    manifest = generate_compiler_manifest(manager, validation_report, chapter_identifier=CHAPTER_REFERENCE)
    statistics = generate_compiler_statistics(manager, validation_report)
    fingerprint_results = generate_compiler_fingerprints(
        manager, manifest=manifest, statistics=statistics, validation_report=validation_report,
    )
    finalize_result = finalize_compiler_build(
        manager,
        validation_report=validation_report,
        manifest=manifest,
        statistics=statistics,
        registry_fingerprints=fingerprint_results["registry_fingerprints"],
        compiler_fingerprint=fingerprint_results["compiler_fingerprint"],
        readiness_report=fingerprint_results["readiness_report"],
    )
    # Register into compiler.state exactly as process_chapter() does,
    # so this chapter's compiler artifacts are the "current" ones
    # build_reference_snapshot() reads (real collaborator, not a stub).
    compiler_state.set_current_registry_manager(manager)
    compiler_state.set_current_compiler_manifest(manifest)
    compiler_state.set_current_compiler_statistics(statistics)
    return {
        "manager": manager, "validation_report": validation_report,
        "manifest": manifest, "statistics": statistics,
        "registry_fingerprints": fingerprint_results["registry_fingerprints"],
        "compiler_fingerprint": fingerprint_results["compiler_fingerprint"],
        "readiness_report": fingerprint_results["readiness_report"],
        "finalize_result": finalize_result,
    }


def run_dst_step(chapter_json, registry_manager):
    """M1-M5.1, real: the exact sequence pipeline.py's own M5.1
    integration block runs (mirrors tests/test_pipeline_dst_integration.
    py's own _run_dst_pipeline_step())."""
    chapter_id = ChapterId(CHAPTER_REFERENCE)
    built = build_tree_from_chapter_json(chapter_id, chapter_json)
    snapshot = CompilerRegistrySnapshot(registry_manager=registry_manager, chapter_id=chapter_id)
    dst = generate_artifact(
        tree=built.tree, chapter_id=chapter_id,
        schema_version=DST_SCHEMA_VERSION, compiler_version=DST_COMPILER_VERSION,
        canonical_registry_snapshot_ref=CHAPTER_REFERENCE, registry=snapshot,
    )
    dst_state.set_current_document_structure_tree(dst)
    return dst


@pytest.fixture(autouse=True)
def _reset_all_state():
    compiler_state.reset_registry_state()
    dst_state.reset_document_structure_tree_state()
    build_metadata_state.reset_build_metadata_state()
    yield
    compiler_state.reset_registry_state()
    dst_state.reset_document_structure_tree_state()
    build_metadata_state.reset_build_metadata_state()


def _make_build(all_stats=None):
    class _Ctx:
        use_vlm = False
        page_batch_size = 6
        force = False
        pdf_input_folder = None

    from datetime import datetime, timezone
    return create_build(
        context=_Ctx(), status="COMPLETED",
        all_stats=all_stats if all_stats is not None else [],
        error=None, started_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# 1. End-to-end: DST generation for a successful chapter compilation
# ---------------------------------------------------------------------------

class TestEndToEndSuccessfulChapterCompilation:
    def test_full_chain_produces_passing_compiler_and_dst_artifacts(self):
        compiler_result = run_full_compiler_flow()
        dst = run_dst_step(_well_formed_chapter_json(), compiler_result["manager"])
        assert compiler_result["finalize_result"]["final_status"] in (
            "READY", "READY_WITH_WARNINGS",
        )
        assert dst.validation_metadata.validation_status == DSTValidationStatus.PASS
        # root + h1 + h2
        assert len(dst.tree) == 3

    def test_dst_chapter_reference_matches_compiler_chapter_reference(self):
        compiler_result = run_full_compiler_flow()
        dst = run_dst_step(_well_formed_chapter_json(), compiler_result["manager"])
        assert dst.build_provenance.canonical_registry_snapshot_ref == CHAPTER_REFERENCE
        assert compiler_result["manifest"].get("chapter_identifier") == CHAPTER_REFERENCE


# ---------------------------------------------------------------------------
# 2. Artifact registration & persistence (real Build, not a stand-in)
# ---------------------------------------------------------------------------

class TestArtifactRegistrationEndToEnd:
    def test_build_registers_both_compiler_and_dst_references_together(self):
        compiler_result = run_full_compiler_flow()
        run_dst_step(_well_formed_chapter_json(), compiler_result["manager"])
        build = _make_build()
        assert build.compiler_ir_reference is not None
        assert build.document_structure_tree_reference is not None
        # both artifacts are snapshots of the SAME chapter's work
        assert (
            compiler_result["manifest"]["chapter_identifier"]
            == build.document_structure_tree_reference["artifact"]["build_provenance"][
                "canonical_registry_snapshot_ref"
            ]
        )

    def test_build_without_a_dst_step_still_registers_compiler_alone(self):
        """Regression guard: a chapter that never reaches the DST step
        (or predates Milestone 5.1) must not be blocked or broken by
        DST's presence in artifact_manager -- compiler_ir_reference is
        unaffected either way."""
        run_full_compiler_flow()
        build = _make_build()
        assert build.compiler_ir_reference is not None
        assert build.document_structure_tree_reference is None


# ---------------------------------------------------------------------------
# 3. build_metadata / manifest consistency, end to end
# ---------------------------------------------------------------------------

class TestBuildMetadataAndManifestConsistency:
    def test_build_metadata_aggregates_compiler_and_dst_together(self):
        compiler_result = run_full_compiler_flow()
        dst = run_dst_step(_well_formed_chapter_json(), compiler_result["manager"])

        base_result = finalize_build_metadata(
            compiler_manifest=compiler_result["manifest"],
            compiler_statistics=compiler_result["statistics"],
            compiler_registry_fingerprints=compiler_result["registry_fingerprints"],
            compiler_fingerprint=compiler_result["compiler_fingerprint"],
            compiler_readiness_report=compiler_result["readiness_report"],
            compiler_build_summary=compiler_result["finalize_result"].get("build_summary"),
            final_compiler_status=compiler_result["finalize_result"]["final_status"],
            knowledge_graph_manifest=None, knowledge_graph_statistics=None,
            knowledge_graph_registry_fingerprints=None, knowledge_graph_fingerprint=None,
            knowledge_graph_readiness_report=None, knowledge_graph_build_summary=None,
            final_graph_status=None,
            release_status=None, pdf_path=None,
        )
        dst_block = generate_dst_metadata(
            document_structure_tree_artifact_metadata=dst.artifact_metadata.to_json(),
            document_structure_tree_validation_metadata=dst.validation_metadata.to_json(),
            dst_chapter_fingerprint=dst.artifact_metadata.chapter_fingerprint.to_json(),
            dst_node_count=len(dst.tree),
            final_dst_status=dst.validation_metadata.validation_status.to_json(),
        )
        final_bm = attach_dst_metadata(base_result["build_metadata"], dst_metadata=dst_block)
        build_metadata_state.set_current_build_metadata(final_bm)

        # Compiler's own fingerprint/status survive DST's later attach
        # untouched (attach_dst_metadata's own "return a new dict,
        # replace only dst_metadata" contract).
        assert final_bm["compiler_metadata"]["compiler_fingerprint"] == compiler_result["compiler_fingerprint"]
        assert final_bm["compiler_metadata"]["final_compiler_status"] == (
            compiler_result["finalize_result"]["final_status"]
        )
        assert final_bm["dst_metadata"]["final_dst_status"] == "pass"
        assert final_bm["dst_metadata"]["dst_node_count"] == 3

    def test_manifest_reflects_the_same_build_metadata_snapshot_the_build_carries(self):
        compiler_result = run_full_compiler_flow()
        dst = run_dst_step(_well_formed_chapter_json(), compiler_result["manager"])

        base_result = finalize_build_metadata(
            compiler_manifest=compiler_result["manifest"],
            compiler_statistics=compiler_result["statistics"],
            compiler_registry_fingerprints=compiler_result["registry_fingerprints"],
            compiler_fingerprint=compiler_result["compiler_fingerprint"],
            compiler_readiness_report=compiler_result["readiness_report"],
            compiler_build_summary=compiler_result["finalize_result"].get("build_summary"),
            final_compiler_status=compiler_result["finalize_result"]["final_status"],
            knowledge_graph_manifest=None, knowledge_graph_statistics=None,
            knowledge_graph_registry_fingerprints=None, knowledge_graph_fingerprint=None,
            knowledge_graph_readiness_report=None, knowledge_graph_build_summary=None,
            final_graph_status=None,
            release_status=None, pdf_path=None,
        )
        dst_block = generate_dst_metadata(
            document_structure_tree_artifact_metadata=dst.artifact_metadata.to_json(),
            document_structure_tree_validation_metadata=dst.validation_metadata.to_json(),
            dst_chapter_fingerprint=dst.artifact_metadata.chapter_fingerprint.to_json(),
            dst_node_count=len(dst.tree),
            final_dst_status=dst.validation_metadata.validation_status.to_json(),
        )
        final_bm = attach_dst_metadata(base_result["build_metadata"], dst_metadata=dst_block)
        build_metadata_state.set_current_build_metadata(final_bm)

        build = _make_build()
        manifest = generate_build_manifest(build)

        # The manifest's compiler_fingerprint comes from the SAME
        # build_metadata_reference the Build carries (not recomputed).
        assert (
            manifest["fingerprints"]["compiler_fingerprint"]
            == build.build_metadata_reference["artifact"]["compiler_metadata"]["compiler_fingerprint"]
        )
        # DST reference in chapter_state_references is the SAME object
        # the DST artifact-registration test above already verified.
        assert (
            manifest["chapter_state_references"]["document_structure_tree_reference"]["artifact"]["tree"]
            == build.document_structure_tree_reference["artifact"]["tree"]
        )


# ---------------------------------------------------------------------------
# 4. Regression: compiler output is unaffected by whether the DST step runs
# ---------------------------------------------------------------------------

class TestCompilerOutputRegression:
    def test_compiler_manifest_and_statistics_identical_with_or_without_dst_step(self):
        """DST integration (M5.1/5.2) must be purely additive: running
        the DST step after the compiler flow must not change a single
        byte of the compiler's own already-computed manifest/statistics.
        Regression-guards architecture §6/§7's DST/compiler separation."""
        compiler_result_a = run_full_compiler_flow()
        manifest_before = copy.deepcopy(compiler_result_a["manifest"])
        statistics_before = copy.deepcopy(compiler_result_a["statistics"])

        run_dst_step(_well_formed_chapter_json(), compiler_result_a["manager"])

        assert compiler_result_a["manifest"] == manifest_before
        assert compiler_result_a["statistics"] == statistics_before

    def test_dst_build_failure_does_not_corrupt_already_registered_compiler_state(self):
        """A DST precondition failure (e.g. duplicate topic ids) must
        propagate as DSTBuildError without touching compiler.state --
        the chapter's compiler artifacts must still be exactly what
        run_full_compiler_flow() produced."""
        from document_structure_tree.exceptions import DSTBuildError

        compiler_result = run_full_compiler_flow()
        manifest_before = copy.deepcopy(compiler_result["manifest"])

        broken_chapter = ChapterJSON(
            topics=[
                TopicNode(id="h1", title="A", parent=None, reading_order=0),
                TopicNode(id="h1", title="B (duplicate id)", parent=None, reading_order=1),
            ],
        )
        with pytest.raises(DSTBuildError):
            run_dst_step(broken_chapter, compiler_result["manager"])

        assert compiler_state.get_current_compiler_manifest() == manifest_before
        assert not dst_state.has_current_document_structure_tree()

