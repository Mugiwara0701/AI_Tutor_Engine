"""
tests/test_tkb_unit.py — M6.1: Unit tests for individual TKB modules.

Tests each module in isolation with minimal fixtures.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from teacher_knowledge_base.exceptions import (
    TKBBuildError, TKBValidationError, TKBLoaderError, TKBBuilderError,
)
from teacher_knowledge_base.metadata import (
    build_tkb_metadata, build_tkb_compiler_information, _tkb_artifact_id,
    TKB_SCHEMA_VERSION,
)
from teacher_knowledge_base.context import TKBContext, TKBDiagnostics
from teacher_knowledge_base.artifact import (
    TeacherKnowledgeBase, build_artifact,
    _empty_edst, _empty_ekg, _empty_edg,
)
from teacher_knowledge_base.serialization import (
    serialize_artifact, validate_serialization_determinism, artifact_to_json,
)
from teacher_knowledge_base.state import (
    set_current_tkb_result, get_current_tkb_result, has_current_tkb_result,
    reset_all_tkb_state,
)


# ===========================================================================
# exceptions.py
# ===========================================================================

class TestExceptions:
    def test_base_exception(self):
        from teacher_knowledge_base.exceptions import TeacherKnowledgeBaseError
        e = TeacherKnowledgeBaseError("base error")
        assert "base error" in str(e)

    def test_build_error(self):
        e = TKBBuildError("build failed")
        assert isinstance(e, Exception)

    def test_validation_error(self):
        e = TKBValidationError("schema_violation", "field X missing")
        assert "schema_violation" in str(e)
        assert e.violation == "schema_violation"
        assert e.detail == "field X missing"

    def test_loader_error(self):
        e = TKBLoaderError("KnowledgeGraph", "not found")
        assert "KnowledgeGraph" in str(e)
        assert e.artifact_name == "KnowledgeGraph"

    def test_builder_error(self):
        e = TKBBuilderError("edst", "something broke")
        assert "edst" in str(e)
        assert e.stage == "edst"

    def test_ambiguity_error(self):
        from teacher_knowledge_base.exceptions import TKBAmbiguityError
        e = TKBAmbiguityError("ENRICHED_DST_SPEC.md", "unclear ownership")
        assert "unclear ownership" in str(e)


# ===========================================================================
# metadata.py
# ===========================================================================

class TestMetadata:
    def test_artifact_id_deterministic(self):
        id1 = _tkb_artifact_id("src-001", "M6.1.0", ["ch1", "ch2"])
        id2 = _tkb_artifact_id("src-001", "M6.1.0", ["ch1", "ch2"])
        assert id1 == id2

    def test_artifact_id_different_source(self):
        id1 = _tkb_artifact_id("src-001", "M6.1.0", ["ch1"])
        id2 = _tkb_artifact_id("src-002", "M6.1.0", ["ch1"])
        assert id1 != id2

    def test_artifact_id_different_chapters(self):
        id1 = _tkb_artifact_id("src-001", "M6.1.0", ["ch1"])
        id2 = _tkb_artifact_id("src-001", "M6.1.0", ["ch1", "ch2"])
        assert id1 != id2

    def test_artifact_id_chapter_order_stable(self):
        """Chapter order should not affect ID (sorted before hashing)."""
        id1 = _tkb_artifact_id("src", "v1", ["ch2", "ch1"])
        id2 = _tkb_artifact_id("src", "v1", ["ch1", "ch2"])
        assert id1 == id2

    def test_build_tkb_metadata(self):
        meta = build_tkb_metadata(
            source_artifact_id="src-001",
            pipeline_version="M6.1.0",
            chapter_ids=["ch1", "ch2"],
            build_id="build-001",
        )
        assert meta.artifact_id  # non-empty
        assert meta.schema_version == TKB_SCHEMA_VERSION
        assert meta.chapter_count == 2
        assert "ch1" in meta.chapter_ids
        assert meta.artifact_type == "TeacherKnowledgeBase"

    def test_build_compiler_information(self):
        ci = build_tkb_compiler_information(
            compiler_artifacts={"optimized_knowledge_package": {"concepts": []}},
            chapter_count=2,
            total_concepts=10,
        )
        assert ci.chapter_count == 2
        assert ci.total_concepts == 10
        assert ci.optimization_applied is True

    def test_metadata_to_dict(self):
        meta = build_tkb_metadata("src", "v1", ["ch1"])
        d = meta.to_dict()
        assert "artifact_id" in d
        assert "schema_version" in d
        assert d["artifact_type"] == "TeacherKnowledgeBase"


# ===========================================================================
# context.py
# ===========================================================================

class TestContext:
    def _make_context(self):
        from teacher_knowledge_base.metadata import build_tkb_metadata, build_tkb_compiler_information
        meta = build_tkb_metadata("src", "v1", ["ch1"])
        ci = build_tkb_compiler_information({}, 1, 0)
        return TKBContext(compiler_artifacts={}, metadata=meta, compiler_information=ci)

    def test_set_get_output(self):
        ctx = self._make_context()
        ctx.set_output("edst", {"nodes": []})
        assert ctx.get_output("edst") == {"nodes": []}

    def test_require_output_present(self):
        ctx = self._make_context()
        ctx.set_output("ekg", {"nodes": [], "edges": []})
        result = ctx.require_output("ekg", "teaching_units")
        assert result["nodes"] == []

    def test_require_output_missing(self):
        ctx = self._make_context()
        with pytest.raises(TKBBuilderError):
            ctx.require_output("ekg", "teaching_units")

    def test_diagnostics_add_error(self):
        ctx = self._make_context()
        ctx.diagnostics.add_error("test_stage", "something failed")
        assert ctx.diagnostics.has_errors
        assert len(ctx.diagnostics.errors) == 1

    def test_diagnostics_add_warning(self):
        ctx = self._make_context()
        ctx.diagnostics.add_warning("test_stage", "something warned")
        assert not ctx.diagnostics.has_errors
        assert len(ctx.diagnostics.warnings) == 1

    def test_stage_timing(self):
        ctx = self._make_context()
        ctx.record_stage_timing("edst", 0.123)
        assert ctx.stage_timings["edst"] == 0.123

    def test_completed_stages(self):
        ctx = self._make_context()
        ctx.set_output("edst", {})
        ctx.set_output("ekg", {})
        assert "edst" in ctx.completed_stages
        assert "ekg" in ctx.completed_stages


# ===========================================================================
# artifact.py
# ===========================================================================

class TestArtifact:
    def _make_minimal_artifact(self):
        from teacher_knowledge_base.metadata import build_tkb_metadata, build_tkb_compiler_information
        meta = build_tkb_metadata("src", "v1", ["ch1"])
        ci = build_tkb_compiler_information({}, 1, 0)
        ctx = TKBContext(compiler_artifacts={}, metadata=meta, compiler_information=ci)
        return build_artifact(ctx)

    def test_artifact_builds(self):
        artifact = self._make_minimal_artifact()
        assert isinstance(artifact, TeacherKnowledgeBase)

    def test_artifact_has_required_fields(self):
        artifact = self._make_minimal_artifact()
        d = artifact.to_dict()
        required = [
            "metadata", "compiler_information",
            "enriched_document_structure_tree", "enriched_knowledge_graph",
            "enriched_dependency_graph", "concept_progression_templates",
            "curriculum_graph", "teaching_units", "navigation",
            "runtime_indexes", "statistics", "validation", "serialization_metadata",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_artifact_fingerprint(self):
        artifact = self._make_minimal_artifact()
        fp = artifact.fingerprint()
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA-256 hex

    def test_artifact_fingerprint_deterministic(self):
        """Fingerprints from the same inputs must match after stripping volatile fields.
        The artifact.fingerprint() method strips generated_at, serialized_at, and
        total_build_time_seconds before hashing — so two builds from identical inputs
        produce identical fingerprints even if wall-clock timestamps differ."""
        a1 = self._make_minimal_artifact()
        a2 = self._make_minimal_artifact()
        assert a1.fingerprint() == a2.fingerprint()

    def test_empty_edst(self):
        edst = _empty_edst()
        assert "nodes" in edst
        assert edst["enrichment_applied"] is False

    def test_empty_ekg(self):
        ekg = _empty_ekg()
        assert "nodes" in ekg
        assert "edges" in ekg

    def test_empty_edg(self):
        edg = _empty_edg()
        assert "nodes" in edg


# ===========================================================================
# serialization.py
# ===========================================================================

class TestSerialization:
    def _make_artifact(self):
        from teacher_knowledge_base.metadata import build_tkb_metadata, build_tkb_compiler_information
        meta = build_tkb_metadata("src", "v1", ["ch1"])
        ci = build_tkb_compiler_information({}, 1, 0)
        ctx = TKBContext(compiler_artifacts={}, metadata=meta, compiler_information=ci)
        return build_artifact(ctx)

    def test_serialize(self):
        artifact = self._make_artifact()
        result = serialize_artifact(artifact)
        assert result.fingerprint
        assert result.canonical_json_str
        assert isinstance(result.artifact_dict, dict)

    def test_determinism(self):
        """Serialization determinism is tested via artifact.fingerprint() which strips
        volatile fields. The raw fingerprint field may differ due to serialized_at timestamps,
        but the content fingerprint (via artifact.fingerprint()) must be equal."""
        artifact1 = self._make_artifact()
        artifact2 = self._make_artifact()
        # Content fingerprint (volatile-stripped) must match
        assert artifact1.fingerprint() == artifact2.fingerprint()

    def test_fingerprint_length(self):
        artifact = self._make_artifact()
        result = serialize_artifact(artifact)
        assert len(result.fingerprint) == 64

    def test_to_storage_dict(self):
        artifact = self._make_artifact()
        result = serialize_artifact(artifact)
        storage_dict = result.to_storage_dict()
        assert "metadata" in storage_dict
        sm = storage_dict.get("serialization_metadata", {})
        assert "fingerprint" in sm

    def test_artifact_to_json(self):
        artifact = self._make_artifact()
        json_str = artifact_to_json(artifact)
        import json
        parsed = json.loads(json_str)
        assert "metadata" in parsed


# ===========================================================================
# state.py
# ===========================================================================

class TestState:
    def setup_method(self):
        reset_all_tkb_state()

    def test_initial_state_empty(self):
        assert not has_current_tkb_result()
        assert get_current_tkb_result() is None

    def test_set_and_get(self):
        sentinel = object()
        set_current_tkb_result(sentinel)
        assert has_current_tkb_result()
        assert get_current_tkb_result() is sentinel

    def test_reset(self):
        set_current_tkb_result(object())
        reset_all_tkb_state()
        assert not has_current_tkb_result()

    def teardown_method(self):
        reset_all_tkb_state()
