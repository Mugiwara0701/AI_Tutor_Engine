"""
tests/test_tkb_builders.py — M6.1: Builder-level tests.

Tests each builder stage independently using the fixture context.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from teacher_knowledge_base.context import TKBContext
from teacher_knowledge_base.metadata import build_tkb_metadata, build_tkb_compiler_information


def make_context(compiler_artifacts: dict, chapter_ids=None, config=None) -> TKBContext:
    meta = build_tkb_metadata(
        source_artifact_id="test-src",
        pipeline_version="M6.1.0",
        chapter_ids=chapter_ids or ["ch1", "ch2"],
    )
    ci = build_tkb_compiler_information(compiler_artifacts, 2, 12)
    return TKBContext(
        compiler_artifacts=compiler_artifacts,
        metadata=meta,
        compiler_information=ci,
        config=config or {},
    )


# ===========================================================================
# EDST Builder
# ===========================================================================

class TestEDSTBuilder:
    def test_builds_from_dst(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edst_builder
        ctx = make_context(minimal_compiler_artifacts)
        edst_builder.build(ctx)
        edst = ctx.get_output("edst")
        assert edst is not None
        assert "nodes" in edst
        assert edst["enrichment_applied"] is True

    def test_enriches_concept_density(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edst_builder
        ctx = make_context(minimal_compiler_artifacts)
        edst_builder.build(ctx)
        edst = ctx.get_output("edst")
        for node in edst["nodes"]:
            assert "teaching_metadata" in node
            assert "concept_density" in node["teaching_metadata"]

    def test_nodes_stable_sorted(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edst_builder
        ctx = make_context(minimal_compiler_artifacts)
        edst_builder.build(ctx)
        nodes = ctx.get_output("edst")["nodes"]
        # Check nodes are sorted by chapter_number then position_index
        keys = [(n.get("chapter_number", 0), n.get("position_index", 0)) for n in nodes]
        assert keys == sorted(keys)

    def test_fallback_to_concepts_without_dst(self, two_chapter_concepts):
        from teacher_knowledge_base.builders import edst_builder
        # No DST in artifacts — should fall back to synthetic
        artifacts = {"optimized_knowledge_package": {"concepts": two_chapter_concepts}}
        ctx = make_context(artifacts)
        edst_builder.build(ctx)
        edst = ctx.get_output("edst")
        assert edst is not None
        assert not ctx.diagnostics.has_errors  # warning only, not error

    def test_teaching_time_estimate_positive(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edst_builder
        ctx = make_context(minimal_compiler_artifacts)
        edst_builder.build(ctx)
        nodes = ctx.get_output("edst")["nodes"]
        for node in nodes:
            assert node["teaching_metadata"]["teaching_time_estimate_minutes"] > 0


# ===========================================================================
# EKG Builder
# ===========================================================================

class TestEKGBuilder:
    def test_builds_from_knowledge_graph(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder
        ctx = make_context(minimal_compiler_artifacts)
        ekg_builder.build(ctx)
        ekg = ctx.get_output("ekg")
        assert ekg is not None
        assert "nodes" in ekg and "edges" in ekg
        assert ekg["enrichment_applied"] is True

    def test_enriches_bloom_level(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder
        ctx = make_context(minimal_compiler_artifacts)
        ekg_builder.build(ctx)
        nodes = ctx.get_output("ekg")["nodes"]
        valid_blooms = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
        for node in nodes:
            bl = node["pedagogical_metadata"]["bloom_taxonomy_level"]
            assert bl in valid_blooms, f"Invalid bloom level: {bl}"

    def test_enriches_difficulty(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder
        ctx = make_context(minimal_compiler_artifacts)
        ekg_builder.build(ctx)
        nodes = ctx.get_output("ekg")["nodes"]
        valid = {"easy", "medium", "hard"}
        for node in nodes:
            d = node["pedagogical_metadata"]["difficulty_level"]
            assert d in valid

    def test_nodes_sorted(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder
        ctx = make_context(minimal_compiler_artifacts)
        ekg_builder.build(ctx)
        nodes = ctx.get_output("ekg")["nodes"]
        ids = [str(n.get("id") or n.get("concept_id") or "") for n in nodes]
        assert ids == sorted(ids)

    def test_learning_paths_produced(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder
        ctx = make_context(minimal_compiler_artifacts)
        ekg_builder.build(ctx)
        ekg = ctx.get_output("ekg")
        assert "learning_paths" in ekg
        assert isinstance(ekg["learning_paths"], list)

    def test_clusters_produced(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder
        ctx = make_context(minimal_compiler_artifacts)
        ekg_builder.build(ctx)
        clusters = ctx.get_output("ekg").get("concept_clusters", [])
        assert len(clusters) >= 1

    def test_fallback_without_kg(self, two_chapter_concepts):
        from teacher_knowledge_base.builders import ekg_builder
        # No KG in artifacts — should synthesize
        artifacts = {"optimized_knowledge_package": {"concepts": two_chapter_concepts}}
        ctx = make_context(artifacts)
        ekg_builder.build(ctx)
        assert ctx.get_output("ekg") is not None

    def test_enriched_id_deterministic(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder
        ctx1 = make_context(minimal_compiler_artifacts, chapter_ids=["ch1", "ch2"])
        ctx2 = make_context(minimal_compiler_artifacts, chapter_ids=["ch1", "ch2"])
        # Same source artifact ID → same artifact_id → same enriched_ids
        # Note: artifact_id is deterministic for same inputs
        ekg_builder.build(ctx1)
        ekg_builder.build(ctx2)
        ids1 = sorted(n["enriched_id"] for n in ctx1.get_output("ekg")["nodes"])
        ids2 = sorted(n["enriched_id"] for n in ctx2.get_output("ekg")["nodes"])
        assert ids1 == ids2


# ===========================================================================
# EDG Builder
# ===========================================================================

class TestEDGBuilder:
    def test_builds_from_kg(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        edg = ctx.get_output("edg")
        assert edg is not None
        assert "nodes" in edg and "edges" in edg

    def test_dependency_types(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        edges = ctx.get_output("edg")["edges"]
        valid_types = {"hard", "soft", "optional"}
        for e in edges:
            assert e["dependency_type"] in valid_types

    def test_readiness_order_is_list(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        order = ctx.get_output("edg")["concept_readiness_ordering"]
        assert isinstance(order, list)

    def test_cycles_detected_is_list(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        cycles = ctx.get_output("edg")["cycles_detected"]
        assert isinstance(cycles, list)


# ===========================================================================
# Teaching Unit Builder
# ===========================================================================

class TestTeachingUnitBuilder:
    def _run_prereqs(self, ctx, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import ekg_builder, edg_builder
        edg_builder.build(ctx)
        ekg_builder.build(ctx)

    def test_builds_teaching_units(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import teaching_unit_builder, ekg_builder, edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        ekg_builder.build(ctx)
        teaching_unit_builder.build(ctx)
        units = ctx.get_output("teaching_units")
        assert isinstance(units, list)
        assert len(units) >= 1

    def test_units_have_required_fields(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import teaching_unit_builder, ekg_builder, edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        ekg_builder.build(ctx)
        teaching_unit_builder.build(ctx)
        units = ctx.get_output("teaching_units")
        required = ["unit_id", "title", "concepts", "teaching_sequence",
                    "learning_objectives", "bloom_levels", "difficulty_level",
                    "estimated_duration_minutes", "chapter_reference"]
        for unit in units:
            for field in required:
                assert field in unit, f"Unit missing field {field!r}: {unit.get('unit_id')}"

    def test_unit_ids_unique(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import teaching_unit_builder, ekg_builder, edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        ekg_builder.build(ctx)
        teaching_unit_builder.build(ctx)
        units = ctx.get_output("teaching_units")
        unit_ids = [u["unit_id"] for u in units]
        assert len(unit_ids) == len(set(unit_ids))

    def test_unit_concepts_subset_of_ekg(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import teaching_unit_builder, ekg_builder, edg_builder
        ctx = make_context(minimal_compiler_artifacts)
        edg_builder.build(ctx)
        ekg_builder.build(ctx)
        teaching_unit_builder.build(ctx)
        ekg_ids = {str(n.get("id") or n.get("concept_id") or "") for n in ctx.get_output("ekg")["nodes"]}
        for unit in ctx.get_output("teaching_units"):
            for cid in unit["concepts"]:
                assert str(cid) in ekg_ids, f"Unit concept {cid!r} not in EKG"


# ===========================================================================
# Curriculum Graph Builder
# ===========================================================================

class TestCurriculumBuilder:
    def _run_prereqs(self, ctx):
        from teacher_knowledge_base.builders import ekg_builder, edg_builder, teaching_unit_builder
        edg_builder.build(ctx)
        ekg_builder.build(ctx)
        teaching_unit_builder.build(ctx)

    def test_builds_curriculum_graph(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import curriculum_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        curriculum_builder.build(ctx)
        cg = ctx.get_output("curriculum_graph")
        assert "nodes" in cg
        assert "edges" in cg
        assert "chapters" in cg
        assert "global_teaching_sequence" in cg

    def test_node_count_matches_units(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import curriculum_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        curriculum_builder.build(ctx)
        units = ctx.get_output("teaching_units")
        cg_nodes = ctx.get_output("curriculum_graph")["nodes"]
        assert len(cg_nodes) == len(units)

    def test_global_sequence_contains_all_units(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import curriculum_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        curriculum_builder.build(ctx)
        units = ctx.get_output("teaching_units")
        seq = ctx.get_output("curriculum_graph")["global_teaching_sequence"]
        unit_ids = {u["unit_id"] for u in units}
        seq_set = set(seq)
        assert unit_ids == seq_set


# ===========================================================================
# Navigation Builder
# ===========================================================================

class TestNavigationBuilder:
    def _run_prereqs(self, ctx):
        from teacher_knowledge_base.builders import ekg_builder, edg_builder, teaching_unit_builder, curriculum_builder
        edg_builder.build(ctx)
        ekg_builder.build(ctx)
        teaching_unit_builder.build(ctx)
        curriculum_builder.build(ctx)

    def test_builds_navigation(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import navigation_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        navigation_builder.build(ctx)
        nav = ctx.get_output("navigation")
        assert "concept_map" in nav
        assert "teaching_unit_map" in nav
        assert "chapter_map" in nav
        assert "breadcrumb_index" in nav

    def test_concept_map_covers_all_ekg_nodes(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import navigation_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        navigation_builder.build(ctx)
        ekg_ids = {str(n.get("id") or n.get("concept_id") or "") for n in ctx.get_output("ekg")["nodes"] if n.get("id") or n.get("concept_id")}
        nav_ids = set(ctx.get_output("navigation")["concept_map"].keys())
        assert ekg_ids == nav_ids

    def test_breadcrumbs_are_strings(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import navigation_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        navigation_builder.build(ctx)
        for cid, bc in ctx.get_output("navigation")["breadcrumb_index"].items():
            assert isinstance(bc, str)
            assert len(bc) > 0


# ===========================================================================
# Runtime Index Builder
# ===========================================================================

class TestRuntimeIndexBuilder:
    def _run_prereqs(self, ctx):
        from teacher_knowledge_base.builders import (
            ekg_builder, edg_builder, teaching_unit_builder,
            curriculum_builder, navigation_builder, progression_builder,
        )
        edg_builder.build(ctx)
        ekg_builder.build(ctx)
        teaching_unit_builder.build(ctx)
        progression_builder.build(ctx)
        curriculum_builder.build(ctx)
        navigation_builder.build(ctx)

    def test_builds_runtime_indexes(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import runtime_index_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        runtime_index_builder.build(ctx)
        ri = ctx.get_output("runtime_indexes")
        required = [
            "concept_by_id", "teaching_unit_by_id", "concept_by_chapter",
            "prerequisite_index", "dependent_index", "learning_path_index",
            "teaching_unit_by_chapter",
        ]
        for key in required:
            assert key in ri, f"Missing index: {key}"

    def test_concept_by_id_covers_all_concepts(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import runtime_index_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        runtime_index_builder.build(ctx)
        ekg_ids = {str(n.get("id") or n.get("concept_id") or "") for n in ctx.get_output("ekg")["nodes"] if n.get("id") or n.get("concept_id")}
        ri_ids = set(ctx.get_output("runtime_indexes")["concept_by_id"].keys())
        assert ekg_ids == ri_ids

    def test_dependent_index_is_inverse_of_prerequisite(self, minimal_compiler_artifacts):
        from teacher_knowledge_base.builders import runtime_index_builder
        ctx = make_context(minimal_compiler_artifacts)
        self._run_prereqs(ctx)
        runtime_index_builder.build(ctx)
        ri = ctx.get_output("runtime_indexes")
        prereq_index = ri["prerequisite_index"]
        dep_index = ri["dependent_index"]
        # For every A -> [B, C] in prereq_index, A should appear in dep_index[B] and dep_index[C]
        for concept_id, prereqs in prereq_index.items():
            for prereq in prereqs:
                if prereq in dep_index:
                    assert concept_id in dep_index[prereq], (
                        f"concept {concept_id!r} should be in dep_index[{prereq!r}]"
                    )
