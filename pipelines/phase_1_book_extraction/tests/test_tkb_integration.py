"""
tests/test_tkb_integration.py — M6.1: Integration and artifact tests.

Tests the full TKB build pipeline end-to-end, artifact validation,
serialization determinism, and regression checks.
"""
import pytest
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from teacher_knowledge_base.builder import build_teacher_knowledge_base
from teacher_knowledge_base.state import reset_all_tkb_state
from teacher_knowledge_base.artifact import TeacherKnowledgeBase


@pytest.fixture(autouse=True)
def reset_state():
    """Reset TKB state before and after each test."""
    reset_all_tkb_state()
    yield
    reset_all_tkb_state()


# ===========================================================================
# Full pipeline integration tests
# ===========================================================================

class TestFullPipeline:
    def test_full_build_succeeds(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert result is not None

    def test_result_has_artifact(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert isinstance(result.artifact, TeacherKnowledgeBase)

    def test_result_has_fingerprint(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert len(result.fingerprint) == 64

    def test_artifact_id_non_empty(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert result.artifact.get_artifact_id()

    def test_artifact_has_teaching_units(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert isinstance(result.artifact.teaching_units, list)
        assert len(result.artifact.teaching_units) >= 1

    def test_artifact_has_ekg(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        ekg = result.artifact.enriched_knowledge_graph
        assert "nodes" in ekg
        assert len(ekg["nodes"]) == 12  # 12 concepts in fixture

    def test_artifact_has_edg(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        edg = result.artifact.enriched_dependency_graph
        assert "nodes" in edg

    def test_artifact_has_edst(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        edst = result.artifact.enriched_document_structure_tree
        assert "nodes" in edst

    def test_artifact_has_navigation(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        nav = result.artifact.navigation
        assert "concept_map" in nav
        assert "teaching_unit_map" in nav

    def test_artifact_has_runtime_indexes(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        ri = result.artifact.runtime_indexes
        assert "concept_by_id" in ri
        assert "teaching_unit_by_id" in ri

    def test_artifact_has_statistics(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        stats = result.artifact.statistics
        assert "concept_statistics" in stats
        assert stats["concept_statistics"]["total_concepts"] == 12

    def test_artifact_has_validation_block(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        val = result.artifact.validation
        assert "passed" in val
        assert "schema_validation" in val

    def test_artifact_is_json_serializable(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        d = result.artifact.to_dict()
        json_str = json.dumps(d, sort_keys=True, default=str)
        assert len(json_str) > 100

    def test_state_set_after_build(self, minimal_compiler_artifacts, test_config):
        from teacher_knowledge_base.state import has_current_tkb_result, get_current_tkb_result
        build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert has_current_tkb_result()
        result = get_current_tkb_result()
        assert result is not None


# ===========================================================================
# Determinism tests
# ===========================================================================

class TestDeterminism:
    def test_same_input_same_artifact_id(self, minimal_compiler_artifacts, test_config):
        r1 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert r1.artifact.get_artifact_id() == r2.artifact.get_artifact_id()

    def test_same_input_same_fingerprint(self, minimal_compiler_artifacts, test_config):
        r1 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert r1.artifact.fingerprint() == r2.artifact.fingerprint()

    def test_same_input_same_unit_count(self, minimal_compiler_artifacts, test_config):
        r1 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        n1 = len(r1.artifact.teaching_units)
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        n2 = len(r2.artifact.teaching_units)
        assert n1 == n2

    def test_same_input_same_canonical_json(self, minimal_compiler_artifacts, test_config):
        r1 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        # Compare fingerprints (volatile fields stripped)
        assert r1.artifact.fingerprint() == r2.artifact.fingerprint()

    def test_different_source_id_different_artifact_id(self, minimal_compiler_artifacts):
        config1 = {"source_artifact_id": "src-001", "pipeline_version": "M6.1.0", "chapter_ids": ["ch1"]}
        config2 = {"source_artifact_id": "src-002", "pipeline_version": "M6.1.0", "chapter_ids": ["ch1"]}
        r1 = build_teacher_knowledge_base(config=config1, direct_artifacts=minimal_compiler_artifacts)
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(config=config2, direct_artifacts=minimal_compiler_artifacts)
        assert r1.artifact.get_artifact_id() != r2.artifact.get_artifact_id()


# ===========================================================================
# Artifact validation tests
# ===========================================================================

class TestArtifactValidation:
    def test_all_schema_sections_present(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        d = result.artifact.to_dict()
        required = [
            "metadata", "compiler_information",
            "enriched_document_structure_tree", "enriched_knowledge_graph",
            "enriched_dependency_graph", "concept_progression_templates",
            "curriculum_graph", "teaching_units", "navigation",
            "runtime_indexes", "statistics", "validation", "serialization_metadata",
        ]
        for field in required:
            assert field in d, f"Schema section missing: {field}"

    def test_validation_schema_check_passed(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        schema_val = result.artifact.validation.get("schema_validation", {})
        assert schema_val.get("passed") is True

    def test_validation_artifact_check_passed(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        art_val = result.artifact.validation.get("artifact_validation", {})
        assert art_val.get("passed") is True

    def test_no_duplicate_concept_ownership(self, minimal_compiler_artifacts, test_config):
        """Each concept_id should appear in at most one chapter in concept_by_chapter."""
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        ri = result.artifact.runtime_indexes
        cbc = ri.get("concept_by_chapter", {})
        seen = {}
        for chapter, cids in cbc.items():
            for cid in cids:
                assert cid not in seen, (
                    f"Concept {cid!r} in both {seen.get(cid)!r} and {chapter!r}"
                )
                seen[cid] = chapter

    def test_all_runtime_index_concepts_in_ekg(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        ekg_ids = set(
            str(n.get("id") or n.get("concept_id") or "")
            for n in result.artifact.enriched_knowledge_graph.get("nodes", [])
        )
        ri = result.artifact.runtime_indexes
        for cid in ri.get("concept_by_id", {}):
            assert cid in ekg_ids, f"runtime_indexes.concept_by_id has {cid!r} not in EKG"


# ===========================================================================
# Regression tests — backward compatibility
# ===========================================================================

class TestRegression:
    def test_canonicalization_import_unchanged(self):
        """canonicalization.py must still work after M6.1 (no modifications)."""
        from canonicalization import (
            VOLATILE_KEYS, strip_volatile, canonical_json, sha256_hexdigest,
        )
        assert "generated_at" in VOLATILE_KEYS
        test_data = {"generated_at": "2024-01-01", "content": "hello"}
        stripped = strip_volatile(test_data)
        assert "generated_at" not in stripped
        assert "content" in stripped
        fp = sha256_hexdigest(canonical_json(stripped))
        assert len(fp) == 64

    def test_artifact_manager_state_unchanged(self):
        """artifact_manager/state.py must still work (no modifications)."""
        from artifact_manager.state import (
            set_current_build, get_current_build, has_current_build, reset_current_build,
        )
        reset_current_build()
        assert not has_current_build()
        sentinel = object()
        set_current_build(sentinel)
        assert has_current_build()
        assert get_current_build() is sentinel
        reset_current_build()
        assert not has_current_build()

    def test_artifact_manager_exceptions_unchanged(self):
        """artifact_manager/exceptions.py must still work (no modifications)."""
        from artifact_manager.exceptions import (
            ArtifactManagerError, BuildError, ManifestError,
            PersistenceError, ArtifactError,
        )
        e = ArtifactError("build-001", "not found")
        assert "build-001" in str(e)

    def test_change_detection_state_unchanged(self):
        """change_detection/state.py must still work (no modifications)."""
        from change_detection.state import (
            set_current_change_detection_report,
            get_current_change_detection_report,
            has_current_change_detection_report,
            reset_change_detection_state,
        )
        reset_change_detection_state()
        assert not has_current_change_detection_report()
        reset_change_detection_state()

    def test_build_executor_state_unchanged(self):
        """build_executor/state.py must still work (no modifications)."""
        from build_executor.state import (
            set_current_execution_report,
            get_current_execution_report,
            has_current_execution_report,
            reset_current_execution_report,
        )
        reset_current_execution_report()
        assert not has_current_execution_report()


# ===========================================================================
# Multi-chapter tests
# ===========================================================================

class TestMultiChapter:
    def test_two_chapter_build(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        ekg = result.artifact.enriched_knowledge_graph
        chapters = set(n.get("chapter_id") or n.get("chapter", "") for n in ekg["nodes"])
        assert "ch1" in chapters
        assert "ch2" in chapters

    def test_units_span_both_chapters(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        chapters_in_units = set(u.get("chapter_reference", "") for u in result.artifact.teaching_units)
        assert "ch1" in chapters_in_units
        assert "ch2" in chapters_in_units

    def test_concept_count_correct(self, minimal_compiler_artifacts, test_config):
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        total = result.artifact.statistics["concept_statistics"]["total_concepts"]
        assert total == 12

    def test_prerequisite_edges_cross_chapters(self, minimal_compiler_artifacts, test_config):
        """c7 (ch2) requires c6 (ch1) — cross-chapter prereq should be in EDG."""
        result = build_teacher_knowledge_base(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        edg = result.artifact.enriched_dependency_graph
        edges = edg.get("edges") or []
        # c7 depends on c6 (cross-chapter)
        cross_chapter_edges = [
            e for e in edges
            if str(e.get("source") or e.get("from") or "") == "c6"
            and str(e.get("target") or e.get("to") or "") == "c7"
        ]
        assert len(cross_chapter_edges) >= 1
