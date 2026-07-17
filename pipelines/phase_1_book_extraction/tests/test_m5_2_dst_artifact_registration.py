"""
tests/test_m5_2_dst_artifact_registration.py — Milestone 5.2: DST
artifact registration / build_metadata integration tests.

SCOPE: these tests exercise exactly the Milestone 5.2 surface described
in the roadmap-status doc's "Already Implemented" list --

  * DST artifact registration        -> artifact_manager.build.
                                         ReferenceSnapshot/Build's
                                         document_structure_tree_reference
                                         field + build_reference_snapshot()
  * manifest integration             -> artifact_manager.manifest's
                                         chapter_state_references /
                                         fingerprints / warnings sections
  * build_metadata integration       -> build_metadata.build.
                                         DSTMetadata / generate_dst_metadata /
                                         attach_dst_metadata

WHY THIS FILE IS SEPARATE FROM tests/test_f2_artifact_manager.py: that
file's own integration tests exercise the whole Phase F2 surface via
`runtime.runtime.CompilerRuntime`, which imports `runtime.context` and
`modules.json_writer` -- neither package is present in this archive
(confirmed: `ModuleNotFoundError: No module named 'runtime'` / 'modules'
during collection). Reconstructing CompilerRuntime/book_orchestrator's
PDF-processing dependency chain is out of Milestone 5.2's scope and
would mean testing against a fabricated stand-in rather than the real
system. These tests instead call artifact_manager.build's own
module-level functions (`create_build`, `build_reference_snapshot`) and
artifact_manager.manifest's functions directly, using only
document_structure_tree's *real* state module (chapter-scoped, no
CompilerRuntime needed) -- exactly the seam Milestone 5.2's own code
comments point to.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from artifact_manager.build import (  # noqa: E402
    Build,
    ReferenceSnapshot,
    build_reference_snapshot,
    create_build,
)
from artifact_manager.manifest import generate_build_manifest  # noqa: E402
from document_structure_tree import state as dst_state  # noqa: E402
from document_structure_tree.artifact import generate_artifact  # noqa: E402

from tests.fixtures import (  # noqa: E402
    CHAPTER_ID,
    COMPILER_VERSION,
    SCHEMA_VERSION,
    build_small_clean_tree,
    clean_registry,
)

from build_metadata import (  # noqa: E402
    DSTMetadata,
    attach_dst_metadata,
    finalize_build_metadata,
    generate_dst_metadata,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _build_sample_dst(chapter_id=CHAPTER_ID):
    """Builds a real, fully-passing DST artifact from this test
    module's own shared fixtures (tests/fixtures.py -- the same
    building blocks test_generate_artifact.py etc. already use) and
    registers it as "current" exactly the way Milestone 5.1's
    pipeline.py integration point does."""
    dst_state.reset_document_structure_tree_state()
    built = build_small_clean_tree()
    dst = generate_artifact(
        tree=built.tree,
        chapter_id=chapter_id,
        schema_version=SCHEMA_VERSION,
        compiler_version=COMPILER_VERSION,
        canonical_registry_snapshot_ref="registry-snap-2026-07-01",
        registry=clean_registry(chapter_id),
    )
    dst_state.set_current_document_structure_tree(dst)
    return dst


@pytest.fixture(autouse=True)
def _reset_dst_state():
    dst_state.reset_document_structure_tree_state()
    yield
    dst_state.reset_document_structure_tree_state()


def _make_build(all_stats=None) -> Build:
    class _Ctx:
        use_vlm = False
        page_batch_size = 6
        force = False
        pdf_input_folder = None

    return create_build(
        context=_Ctx(),
        status="COMPLETED",
        all_stats=all_stats if all_stats is not None else [],
        error=None,
        started_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# DST artifact registration (ReferenceSnapshot / Build)
# ---------------------------------------------------------------------------

class TestDSTArtifactRegistration:
    def test_reference_snapshot_has_dst_field(self):
        assert "document_structure_tree_reference" in ReferenceSnapshot.__dataclass_fields__

    def test_snapshot_dst_reference_none_when_no_dst_built(self):
        snapshot = build_reference_snapshot()
        assert snapshot.document_structure_tree_reference is None

    def test_snapshot_dst_reference_present_after_dst_built(self):
        _build_sample_dst()
        snapshot = build_reference_snapshot()
        assert snapshot.document_structure_tree_reference is not None
        assert snapshot.document_structure_tree_reference["source"] == "last_processed_chapter"
        assert "artifact" in snapshot.document_structure_tree_reference

    def test_snapshot_dst_reference_artifact_is_canonical_json_shape(self):
        _build_sample_dst()
        snapshot = build_reference_snapshot()
        artifact = snapshot.document_structure_tree_reference["artifact"]
        # schema §2.2 top-level DST artifact keys
        assert "artifact_metadata" in artifact
        assert "validation_metadata" in artifact
        assert "tree" in artifact

    def test_build_carries_dst_reference_through_to_the_build_object(self):
        _build_sample_dst()
        build = _make_build()
        assert build.document_structure_tree_reference is not None
        assert build.document_structure_tree_reference["artifact"]["tree"]

    def test_build_dst_reference_none_when_dst_never_built(self):
        build = _make_build()
        assert build.document_structure_tree_reference is None

    def test_two_snapshots_after_reset_do_not_leak_stale_dst(self):
        _build_sample_dst()
        assert build_reference_snapshot().document_structure_tree_reference is not None
        dst_state.reset_document_structure_tree_state()
        assert build_reference_snapshot().document_structure_tree_reference is None


# ---------------------------------------------------------------------------
# Manifest integration
# ---------------------------------------------------------------------------

class TestDSTManifestIntegration:
    def test_manifest_chapter_state_references_includes_dst_key(self):
        _build_sample_dst()
        build = _make_build()
        manifest = generate_build_manifest(build)
        assert "document_structure_tree_reference" in manifest["chapter_state_references"]
        assert manifest["chapter_state_references"]["document_structure_tree_reference"] == (
            build.document_structure_tree_reference
        )

    def test_manifest_chapter_state_references_dst_key_present_even_when_absent(self):
        build = _make_build()
        manifest = generate_build_manifest(build)
        assert manifest["chapter_state_references"]["document_structure_tree_reference"] is None

    def test_manifest_fingerprints_do_not_yet_surface_dst_fingerprint(self):
        """CONFORMANCE GAP (see review): compiler_fingerprint/graph_fingerprint
        are surfaced as their own top-level `fingerprints` entries (manifest.py
        _collect_fingerprints()), each with its own dedicated field. No
        analogous `dst_chapter_fingerprint` entry exists, even though
        `dst_metadata.dst_chapter_fingerprint` is available on
        build_metadata_reference once Milestone 5.2's attach_dst_metadata()
        has run. This test documents the CURRENT (asymmetric) behavior --
        it is not asserting this is correct, only that it is what the
        code does today, so a future fix is a deliberate, visible change
        rather than a silent one."""
        _build_sample_dst()
        build = _make_build()
        manifest = generate_build_manifest(build)
        assert "dst_chapter_fingerprint" not in manifest["fingerprints"]
        assert set(manifest["fingerprints"].keys()) == {
            "compiler_fingerprint", "graph_fingerprint", "configuration_fingerprint",
        }

    def test_manifest_warnings_do_not_yet_reflect_final_dst_status(self):
        """CONFORMANCE GAP companion to the fingerprint test above:
        final_compiler_status/final_graph_status not READY each produce a
        manifest warning (_collect_warnings_and_errors()); final_dst_status
        has no equivalent check, so a build whose DST failed validation
        produces no manifest-level warning about it today."""
        dst = _build_sample_dst()
        build = _make_build()
        # Attach a build_metadata_reference whose dst_metadata reports a
        # failing DST status, mirroring what attach_dst_metadata() would
        # produce for a chapter whose DST failed §15 invariants.
        bm_artifact = {
            "compiler_metadata": {}, "graph_metadata": {}, "configuration_metadata": {},
            "version_metadata": {},
            "dst_metadata": generate_dst_metadata(final_dst_status="fail"),
        }
        object.__setattr__(build, "build_metadata_reference", {
            "source": "last_processed_chapter", "artifact": bm_artifact,
        })
        manifest = generate_build_manifest(build)
        assert not any("dst" in w.lower() for w in manifest["warnings"])


# ---------------------------------------------------------------------------
# build_metadata integration (DSTMetadata / attach_dst_metadata)
# ---------------------------------------------------------------------------

class TestDSTMetadataAggregation:
    def test_generate_dst_metadata_all_none_by_default(self):
        block = generate_dst_metadata()
        assert block == {
            "document_structure_tree_artifact_metadata": None,
            "document_structure_tree_validation_metadata": None,
            "dst_chapter_fingerprint": None,
            "dst_node_count": None,
            "final_dst_status": None,
        }

    def test_generate_dst_metadata_reads_arguments_verbatim(self):
        block = generate_dst_metadata(
            document_structure_tree_artifact_metadata={"a": 1},
            document_structure_tree_validation_metadata={"b": 2},
            dst_chapter_fingerprint="deadbeef" * 8,
            dst_node_count=3,
            final_dst_status="pass",
        )
        assert block["document_structure_tree_artifact_metadata"] == {"a": 1}
        assert block["dst_node_count"] == 3
        assert block["final_dst_status"] == "pass"

    def test_finalize_build_metadata_dst_block_defaults_to_none(self):
        result = finalize_build_metadata(
            compiler_manifest=None, compiler_statistics=None,
            compiler_registry_fingerprints=None, compiler_fingerprint=None,
            compiler_readiness_report=None, compiler_build_summary=None,
            final_compiler_status=None,
            knowledge_graph_manifest=None, knowledge_graph_statistics=None,
            knowledge_graph_registry_fingerprints=None, knowledge_graph_fingerprint=None,
            knowledge_graph_readiness_report=None, knowledge_graph_build_summary=None,
            final_graph_status=None,
            release_status=None, pdf_path=None,
        )
        dst_block = result["build_metadata"]["dst_metadata"]
        assert dst_block["final_dst_status"] is None

    def test_attach_dst_metadata_returns_new_dict_without_mutating_input(self):
        original = {"dst_metadata": generate_dst_metadata(), "other_field": "unchanged"}
        new_dst_block = generate_dst_metadata(final_dst_status="pass", dst_node_count=5)
        updated = attach_dst_metadata(original, dst_metadata=new_dst_block)
        assert original["dst_metadata"]["final_dst_status"] is None  # untouched
        assert updated["dst_metadata"]["final_dst_status"] == "pass"
        assert updated["other_field"] == "unchanged"
        assert updated is not original

    def test_end_to_end_pipeline_style_dst_metadata_attachment(self):
        """Mirrors pipeline.py's own M5.2 integration block: build a real
        DST artifact, derive a DSTMetadata block from it exactly the way
        that block does, and attach it to an already-finalized
        BuildMetadata dict."""
        dst = _build_sample_dst()
        base_result = finalize_build_metadata(
            compiler_manifest=None, compiler_statistics=None,
            compiler_registry_fingerprints=None, compiler_fingerprint=None,
            compiler_readiness_report=None, compiler_build_summary=None,
            final_compiler_status=None,
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
        final = attach_dst_metadata(base_result["build_metadata"], dst_metadata=dst_block)
        assert final["dst_metadata"]["dst_node_count"] == len(dst.tree) == 4
        assert final["dst_metadata"]["final_dst_status"] in ("pass", "fail")
        assert final["dst_metadata"]["dst_chapter_fingerprint"]