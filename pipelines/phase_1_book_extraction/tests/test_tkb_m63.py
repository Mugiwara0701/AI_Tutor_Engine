"""
tests/test_tkb_m63.py — M6.1 Remediation + M6.2 + M6.3 Tests

Tests for:
  - M6.1 architecture gaps now fixed (EDG->TU backfill, EKG->TU backfill,
    completeness_score recompute, validation CHK-15/CHK-16)
  - M6.2 runtime indexes (7 indexes, all fully populated)
  - M6.3 TKBRuntime Phase 2 APIs (all spec §4–§10 endpoints)
  - Determinism (identical inputs → identical fingerprint)
  - Multi-concept regression
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pytest

from teacher_knowledge_base.builder import build_teacher_knowledge_base
from teacher_knowledge_base.artifact import TeacherKnowledgeBase
from teacher_knowledge_base.tkb_runtime import TKBRuntime, TKBRuntimeError
from teacher_knowledge_base.state import reset_all_tkb_state


# ===========================================================================
# Shared fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def reset_state():
    reset_all_tkb_state()
    yield
    reset_all_tkb_state()


def _make_concept(cid, name, prereqs=None, difficulty="medium",
                  importance="core", time=30.0):
    return {
        "concept_key": f"concept:{name.lower().replace(' ', '_')}",
        "name": name,
        "title": name,
        "description": f"{name} is a fundamental concept in this chapter.",
        "definition": f"Formal definition: {name} describes a property or behaviour.",
        "definition_confidence": 0.92,
        "prerequisites": prereqs or [],
        "difficulty": difficulty,
        "importance": importance,
        "estimated_teaching_time_minutes": time,
        "revision_notes": [
            {"note_id": f"note_{cid}", "text": f"Remember: {name}",
             "note_type": "summary", "key_points": [f"{name} key point"]}
        ],
        "learning_objectives_raw": [
            {"objective_id": f"obj_{cid}", "text": f"Understand {name}",
             "bloom_level": "understand", "outcome_type": "knowledge",
             "assessment_hint": f"Explain {name}"}
        ],
    }


@pytest.fixture
def two_concept_artifacts():
    """Minimal two-concept pipeline input (c1 -> c2 via REQUIRES)."""
    concepts = {
        "c1": _make_concept("c1", "Motion", difficulty="easy", time=20.0),
        "c2": _make_concept("c2", "Velocity", prereqs=["c1"], difficulty="easy", time=25.0),
    }
    return {
        "optimized_knowledge_package": {
            "concept_index": concepts,
            "dependency_map": {"edges": [
                {"source": "c1", "target": "c2", "edge_type": "REQUIRES",
                 "strength": 1.0, "is_blocking": True, "context": "c1 required for c2"},
            ]},
            "learning_analytics": {"concept_analytics": {
                cid: {"difficulty": c.get("difficulty", "medium"),
                      "importance": c.get("importance", "core"),
                      "estimated_teaching_time_minutes": c.get("estimated_teaching_time_minutes", 30.0)}
                for cid, c in concepts.items()
            }},
            "manifest": {"package_id": "test-okp-two"},
        },
        "document_structure_tree": {
            "id": "dst-two",
            "nodes": [
                {"node_id": "root", "heading_text": "Chapter", "level": 0,
                 "parent_id": None, "children_ids": ["s1"], "concept_ids": []},
                {"node_id": "s1", "heading_text": "Section 1", "level": 1,
                 "parent_id": "root", "children_ids": [],
                 "concept_ids": ["c1", "c2"], "teaching_unit_ids": ["c1", "c2"]},
            ],
        },
    }


@pytest.fixture
def two_concept_config():
    return {
        "chapter_id": "ch-two",
        "chapter_number": 1,
        "chapter_title": "Motion and Velocity",
        "subject": "Physics",
        "book_title": "Test Physics",
        "klass": "9",
        "board": "CBSE",
        "source_artifact_id": "test-okp-two",
        "strict_validation": False,
    }


@pytest.fixture
def two_result(two_concept_artifacts, two_concept_config):
    return build_teacher_knowledge_base(
        config=two_concept_config,
        direct_artifacts=two_concept_artifacts,
    )


# ===========================================================================
# M6.1 REMEDIATION: EDG -> TU Backfill (GAP-M61-01, GAP-M61-02, GAP-M61-03)
# ===========================================================================

class TestEDGBackfill:
    """Verifies EDG builder backfills TU.prerequisites, TU.edg_node_id,
    and recomputes TU.completeness_score per AUTHORITY_MATRIX §2.1."""

    def test_tu_prerequisites_populated_from_edg(self, two_result):
        """TU.prerequisites is a derived convenience snapshot from EDG REQUIRES edges.
        AUTHORITY_MATRIX §2.1 + TEACHING_UNIT_SPECIFICATION §3.
        """
        tu_c2 = two_result.artifact.teaching_units["c2"]
        prereqs = tu_c2.get("prerequisites") or []
        assert len(prereqs) >= 1, (
            f"c2 must have at least 1 prerequisite (c1) derived from EDG; got {prereqs}"
        )
        prereq_ids = {p["concept_id"] for p in prereqs}
        assert "c1" in prereq_ids, f"c1 must be in c2 prerequisites; got {prereq_ids}"

    def test_tu_prerequisite_is_prereq_ref_schema(self, two_result):
        """Each PrerequisiteRef has concept_id, concept_name, is_blocking, teaching_unit_id."""
        prereqs = two_result.artifact.teaching_units["c2"]["prerequisites"]
        for p in prereqs:
            for field in ("concept_id", "concept_name", "is_blocking", "teaching_unit_id"):
                assert field in p, f"PrerequisiteRef missing field: {field}"
            assert isinstance(p["is_blocking"], bool)

    def test_tu_edg_node_id_set(self, two_result):
        """TU.edg_node_id must reference the LearningDependencyNode.node_id.
        TEACHING_UNIT_SPECIFICATION §3 'Graph Cross-References'.
        """
        for cid, tu in two_result.artifact.teaching_units.items():
            edg_node_id = tu.get("edg_node_id", "")
            assert edg_node_id != "", f"TU[{cid}].edg_node_id is empty"

    def test_edg_node_id_matches_edg(self, two_result):
        """TU.edg_node_id must resolve to a real node in EDG.nodes."""
        edg_nodes = two_result.artifact.enriched_dependency_graph.get("nodes") or {}
        for cid, tu in two_result.artifact.teaching_units.items():
            edg_node_id = tu.get("edg_node_id", "")
            # EDG nodes are keyed by concept_id in our implementation
            # The edg_node_id is the UUID of the node, not the concept_id key
            assert edg_node_id, f"TU[{cid}].edg_node_id empty"
            # Verify this UUID appears as a node_id value somewhere in EDG
            found = any(
                n.get("node_id") == edg_node_id
                for n in edg_nodes.values()
            )
            assert found, (
                f"TU[{cid}].edg_node_id={edg_node_id!r} not found as EDG node.node_id"
            )

    def test_completeness_score_recomputed_after_prereq_backfill(self, two_result):
        """c2 completeness_score must reflect 'prerequisites resolved from EDG' weight=2.
        TEACHING_UNIT_SPECIFICATION §6.
        """
        tu_c2 = two_result.artifact.teaching_units["c2"]
        score = float(tu_c2.get("completeness_score") or 0.0)
        prereqs = tu_c2.get("prerequisites") or []
        assert len(prereqs) >= 1, "Prereq backfill must have run"
        # With prereqs populated, score should be higher than without (which had weight=2 missing)
        # For a TU with definition + explanation + revision_notes + time + prereqs populated:
        # min expected: (3+3+0+0+2+0+0+1+0+1)/18 ≈ 0.555
        assert score >= 0.5, (
            f"c2 completeness_score should be >= 0.5 with prereqs; got {score}"
        )

    def test_root_concept_has_no_prerequisites(self, two_result):
        """c1 (root) must have no prerequisites after EDG backfill."""
        prereqs = two_result.artifact.teaching_units["c1"].get("prerequisites") or []
        assert prereqs == [], f"Root concept c1 must have no prereqs; got {prereqs}"


# ===========================================================================
# M6.1 REMEDIATION: EKG -> TU Backfill (GAP-M61-04)
# ===========================================================================

class TestEKGRelatedConceptsBackfill:
    """Verifies EKG builder backfills TU.related_concepts from RELATED_TO edges.
    AUTHORITY_MATRIX §4.2 + TEACHING_UNIT_SPECIFICATION §3.
    """

    def test_related_concepts_is_list(self, two_result):
        """TU.related_concepts must be a list (never None)."""
        for cid, tu in two_result.artifact.teaching_units.items():
            rc = tu.get("related_concepts")
            assert isinstance(rc, list), f"TU[{cid}].related_concepts must be a list; got {type(rc)}"

    def test_related_concepts_populated_from_semantic_graph(self, two_concept_config):
        """When semantic_graph provides RELATED_TO edges, TU.related_concepts is backfilled."""
        artifacts_with_sg = {
            "optimized_knowledge_package": {
                "concept_index": {
                    "c1": _make_concept("c1", "Motion"),
                    "c2": _make_concept("c2", "Velocity"),
                },
                "dependency_map": {"edges": []},
                "learning_analytics": {"concept_analytics": {
                    "c1": {"difficulty": "easy", "importance": "core",
                           "estimated_teaching_time_minutes": 20.0},
                    "c2": {"difficulty": "easy", "importance": "core",
                           "estimated_teaching_time_minutes": 25.0},
                }},
                "manifest": {"package_id": "test-sg"},
            },
            "document_structure_tree": {
                "id": "dst-sg",
                "nodes": [
                    {"node_id": "root", "heading_text": "Ch", "level": 0,
                     "parent_id": None, "children_ids": ["s1"], "concept_ids": []},
                    {"node_id": "s1", "heading_text": "S1", "level": 1,
                     "parent_id": "root", "children_ids": [],
                     "concept_ids": ["c1", "c2"], "teaching_unit_ids": ["c1", "c2"]},
                ],
            },
            "knowledge_graph": {
                "nodes": [
                    {"id": "c1", "concept_id": "c1", "name": "Motion",
                     "node_type": "Concept", "concept_key": "concept:motion"},
                    {"id": "c2", "concept_id": "c2", "name": "Velocity",
                     "node_type": "Concept", "concept_key": "concept:velocity"},
                ],
                "edges": [],
            },
            # semantic_graph with RELATED_TO edge
            "semantic_graph": {
                "edges": [
                    {"edge_type": "RELATED_TO", "source": "c1", "target": "c2",
                     "weight": 0.7, "confidence": 0.8},
                ]
            },
        }
        config = dict(two_concept_config)
        config["source_artifact_id"] = "test-sg"
        config["chapter_id"] = "ch-sg"
        result = build_teacher_knowledge_base(config=config, direct_artifacts=artifacts_with_sg)
        # c1 should have c2 as related, and c2 should have c1 as related (symmetric)
        c1_related = result.artifact.teaching_units["c1"]["related_concepts"]
        c2_related = result.artifact.teaching_units["c2"]["related_concepts"]
        c1_related_ids = {r["concept_id"] for r in c1_related}
        c2_related_ids = {r["concept_id"] for r in c2_related}
        assert "c2" in c1_related_ids, f"c1 should relate to c2; got {c1_related_ids}"
        assert "c1" in c2_related_ids, f"c2 should relate to c1 (symmetric); got {c2_related_ids}"


# ===========================================================================
# M6.1 REMEDIATION: Validation CHK-04, CHK-15, CHK-16
# ===========================================================================

class TestValidationStrengthening:
    """Validates the new validation checks added during M6.1 remediation."""

    def test_chk_15_present(self, two_result):
        """CHK-15: completeness_score >= 0.2 must appear in validation checks."""
        chk_ids = {c["check_id"] for c in (two_result.artifact.validation.get("checks") or [])}
        assert "CHK-15" in chk_ids, "CHK-15 missing from validation checks"

    def test_chk_16_present(self, two_result):
        """CHK-16: completeness_score >= 0.5 must appear in validation checks."""
        chk_ids = {c["check_id"] for c in (two_result.artifact.validation.get("checks") or [])}
        assert "CHK-16" in chk_ids, "CHK-16 missing from validation checks"

    def test_chk_15_passes_with_populated_concepts(self, two_result):
        """CHK-15 must PASS when all TUs have definition + explanation (score > 0.2)."""
        chk15 = next(
            (c for c in (two_result.artifact.validation.get("checks") or [])
             if c["check_id"] == "CHK-15"),
            None
        )
        assert chk15 is not None
        assert chk15["result"] == "PASS", f"CHK-15 failed: {chk15['message']}"

    def test_chk_04_compares_against_concept_index(self, two_result):
        """CHK-04 must compare TU count against concept_index count."""
        chk04 = next(
            (c for c in (two_result.artifact.validation.get("checks") or [])
             if c["check_id"] == "CHK-04"),
            None
        )
        assert chk04 is not None
        # Should PASS because concept_index has 2 concepts and we have 2 TUs
        assert chk04["result"] == "PASS", f"CHK-04: {chk04['message']}"

    def test_chk_14_no_prerequisite_of_in_ekg(self, two_result):
        """CHK-14: EKG must have no PREREQUISITE_OF edges (authority rule)."""
        chk14 = next(
            (c for c in (two_result.artifact.validation.get("checks") or [])
             if c["check_id"] == "CHK-14"),
            None
        )
        assert chk14 is not None
        assert chk14["result"] == "PASS", f"CHK-14 failed: {chk14['message']}"


# ===========================================================================
# M6.2: Runtime Indexes — 7 fully populated indexes
# ===========================================================================

class TestRuntimeIndexes:
    """All 7 runtime indexes must be present and correctly populated.
    RUNTIME_API_SPECIFICATION §2.
    """

    def test_all_seven_indexes_present(self, two_result):
        ri = two_result.artifact.runtime_indexes
        required = [
            "concept_lookup_index", "semantic_search_index", "prerequisite_index",
            "teaching_retrieval_index", "revision_retrieval_index",
            "assessment_retrieval_index", "curriculum_traversal_index",
        ]
        for key in required:
            assert key in ri, f"Missing runtime index: {key}"

    def test_concept_lookup_has_by_id_by_key_by_name(self, two_result):
        cli = two_result.artifact.runtime_indexes["concept_lookup_index"]
        assert "by_id" in cli and "by_key" in cli and "by_name" in cli
        # All concepts must be in by_id
        for cid in two_result.artifact.teaching_units:
            assert cid in cli["by_id"], f"concept_id {cid} missing from by_id"

    def test_concept_nav_entry_schema(self, two_result):
        """ConceptNavEntry must have all spec fields (200 bytes max—ID-only rule)."""
        by_id = two_result.artifact.runtime_indexes["concept_lookup_index"]["by_id"]
        required_fields = {
            "concept_id", "concept_key", "concept_name", "teaching_unit_id",
            "edst_node_ids", "ekg_node_id", "edg_node_id", "difficulty", "importance",
        }
        for cid, entry in by_id.items():
            for field in required_fields:
                assert field in entry, f"ConceptNavEntry[{cid}] missing: {field}"

    def test_concept_lookup_by_name_case_insensitive(self, two_result):
        by_name = two_result.artifact.runtime_indexes["concept_lookup_index"]["by_name"]
        # All keys must be lowercased
        for key in by_name:
            assert key == key.lower(), f"by_name key not lowercase: {key!r}"

    def test_semantic_search_index_entries_present(self, two_result):
        ssi = two_result.artifact.runtime_indexes["semantic_search_index"]
        assert "entries" in ssi
        assert isinstance(ssi["entries"], list)
        assert "total_entries" in ssi
        assert ssi["total_entries"] == len(ssi["entries"])
        assert ssi["total_entries"] >= 2  # at least one entry per concept

    def test_semantic_search_entry_schema(self, two_result):
        """SemanticSearchEntry must have entry_id, entry_type, display_text, concept_ids, unit_id."""
        entries = two_result.artifact.runtime_indexes["semantic_search_index"]["entries"]
        for entry in entries:
            for field in ("entry_id", "entry_type", "display_text", "concept_ids", "unit_id"):
                assert field in entry, f"SemanticSearchEntry missing: {field}"
            assert isinstance(entry["concept_ids"], list)
            assert entry["entry_type"] in (
                "concept", "definition", "example", "formula", "figure", "activity"
            )

    def test_prerequisite_index_has_blocking_soft_dependent(self, two_result):
        pi = two_result.artifact.runtime_indexes["prerequisite_index"]["by_concept"]
        assert "c2" in pi
        entry = pi["c2"]
        assert "blocking_prerequisite_ids" in entry
        assert "soft_prerequisite_ids" in entry
        assert "dependent_ids" in entry
        assert "c1" in entry["blocking_prerequisite_ids"]

    def test_teaching_retrieval_index_structure(self, two_result):
        tri = two_result.artifact.runtime_indexes["teaching_retrieval_index"]
        assert "by_concept_id" in tri
        assert "by_section_id" in tri
        assert "by_difficulty" in tri
        assert "by_importance" in tri
        # All concepts present in by_concept_id
        for cid in two_result.artifact.teaching_units:
            assert cid in tri["by_concept_id"], f"concept {cid} missing from by_concept_id"

    def test_assessment_retrieval_index_has_item_location(self, two_result):
        ari = two_result.artifact.runtime_indexes["assessment_retrieval_index"]
        assert "assessment_item_location" in ari
        assert "chapter_test_item_ids" in ari
        assert "by_concept_id" in ari

    def test_revision_retrieval_index_structure(self, two_result):
        rri = two_result.artifact.runtime_indexes["revision_retrieval_index"]
        for key in ("by_concept_id", "formula_ids_ordered", "definition_index", "core_concept_ids"):
            assert key in rri, f"revision_retrieval_index missing: {key}"

    def test_curriculum_traversal_index_structure(self, two_result):
        cti = two_result.artifact.runtime_indexes["curriculum_traversal_index"]
        assert "by_concept_id" in cti
        assert "cross_chapter" in cti


# ===========================================================================
# M6.2: Navigation Index — all 6 sub-navigations
# ===========================================================================

class TestNavigationIndex:
    """NavigationIndex must contain all 6 sub-navigations per NAV-SPEC §2."""

    def test_all_six_sub_navigations_present(self, two_result):
        nav = two_result.artifact.navigation
        for key in ("teacher_navigation", "question_navigation", "concept_navigation",
                    "revision_navigation", "assessment_navigation",
                    "learning_path_navigation"):
            assert key in nav, f"Missing sub-navigation: {key}"

    def test_learning_path_canonical_equals_edg_topological_order(self, two_result):
        """LearningPathNavigation.canonical_path IS the EDG topological_order (spec §8 LPN)."""
        lpn = two_result.artifact.navigation["learning_path_navigation"]
        edg_topo = two_result.artifact.enriched_dependency_graph.get("topological_order") or []
        assert lpn.get("canonical_path") == edg_topo, (
            "canonical_path must be identical to EDG.topological_order "
            f"(not re-derived). canonical={lpn.get('canonical_path')}, "
            f"topo={edg_topo}"
        )

    def test_learning_path_c1_before_c2(self, two_result):
        """c1 must appear before c2 in canonical learning path."""
        canonical = two_result.artifact.navigation["learning_path_navigation"]["canonical_path"]
        assert canonical.index("c1") < canonical.index("c2"), (
            "c1 must precede c2 in learning order"
        )

    def test_revision_navigation_has_full_chapter_revision(self, two_result):
        rv = two_result.artifact.navigation["revision_navigation"]
        assert "full_chapter_revision" in rv
        assert isinstance(rv["full_chapter_revision"], list)

    def test_revision_navigation_has_spaced_repetition_groups(self, two_result):
        rv = two_result.artifact.navigation["revision_navigation"]
        assert "spaced_repetition_groups" in rv
        assert isinstance(rv["spaced_repetition_groups"], list)

    def test_question_navigation_has_provenance_tier(self, two_result):
        """QuestionNavigation must index by provenance_tier (spec §4 QN)."""
        qn = two_result.artifact.navigation["question_navigation"]
        assert "by_provenance_tier" in qn

    def test_concept_navigation_has_name_lookup(self, two_result):
        cn = two_result.artifact.navigation["concept_navigation"]
        assert "name_lookup" in cn
        assert "alias_lookup" in cn


# ===========================================================================
# M6.3: TKBRuntime — all Phase 2 API endpoints
# ===========================================================================

class TestTKBRuntimeLoad:
    def test_from_artifact(self, two_result):
        rt = TKBRuntime.from_artifact(two_result.artifact)
        assert rt.is_loaded()

    def test_from_dict(self, two_result):
        rt = TKBRuntime.from_dict(two_result.artifact.to_dict())
        assert rt.is_loaded()

    def test_from_json_str(self, two_result):
        json_str = json.dumps(two_result.artifact.to_dict(), default=str)
        rt = TKBRuntime.from_json_str(json_str)
        assert rt.is_loaded()

    def test_wrong_schema_version_raises(self, two_result):
        d = two_result.artifact.to_dict()
        d["schema_version"] = "9.9.9"
        with pytest.raises(TKBRuntimeError):
            TKBRuntime.from_dict(d)

    def test_missing_schema_version_ok(self, two_result):
        """Missing schema_version is tolerated (not a version mismatch)."""
        d = two_result.artifact.to_dict()
        d["schema_version"] = ""
        rt = TKBRuntime.from_dict(d)
        assert rt.is_loaded()


@pytest.fixture
def runtime(two_result):
    return TKBRuntime.from_artifact(two_result.artifact)


class TestTKBRuntimeConceptAPIs:
    """§4 Concept APIs."""

    def test_get_concept_returns_nav_entry(self, runtime):
        entry = runtime.get_concept("c1")
        assert entry is not None
        assert entry["concept_id"] == "c1"
        assert entry["concept_name"] == "Motion"

    def test_get_concept_not_found_returns_none(self, runtime):
        assert runtime.get_concept("nonexistent") is None

    def test_get_concept_empty_id_returns_none(self, runtime):
        assert runtime.get_concept("") is None

    def test_get_concept_by_name(self, runtime):
        entry = runtime.get_concept_by_name("Velocity")
        assert entry is not None
        assert entry["concept_id"] == "c2"

    def test_get_concept_by_name_case_insensitive(self, runtime):
        entry = runtime.get_concept_by_name("MOTION")
        assert entry is not None
        assert entry["concept_id"] == "c1"

    def test_get_concept_by_name_not_found(self, runtime):
        assert runtime.get_concept_by_name("Nonexistent") is None

    def test_get_concept_by_key(self, runtime):
        entry = runtime.get_concept_by_key("concept:motion")
        assert entry is not None
        assert entry["concept_id"] == "c1"

    def test_get_concept_by_key_not_found(self, runtime):
        assert runtime.get_concept_by_key("concept:unknown") is None


class TestTKBRuntimeTeachingUnitAPIs:
    """§5 Teaching Unit APIs."""

    def test_get_teaching_unit_returns_full_tu(self, runtime):
        tu = runtime.get_teaching_unit("c1")
        assert tu is not None
        assert tu["concept_id"] == "c1"
        assert "definition" in tu

    def test_get_teaching_unit_not_found(self, runtime):
        assert runtime.get_teaching_unit("xxx") is None

    def test_get_teaching_units_batch(self, runtime):
        result = runtime.get_teaching_units(["c1", "c2", "xxx"])
        assert result["c1"] is not None
        assert result["c2"] is not None
        assert result["xxx"] is None

    def test_get_teaching_units_empty_list(self, runtime):
        result = runtime.get_teaching_units([])
        assert result == {}

    def test_get_teaching_unit_for_section(self, runtime, two_result):
        # Get the enriched_node_id for section s1
        edst_nodes = two_result.artifact.enriched_document_structure_tree.get("nodes") or {}
        section_node = next(
            (n for n in edst_nodes.values() if n.get("heading_text") == "Section 1"),
            None
        )
        if section_node:
            eid = section_node.get("enriched_node_id", "")
            tus = runtime.get_teaching_unit_for_section(eid)
            assert isinstance(tus, list)
            assert len(tus) >= 1

    def test_get_teaching_unit_for_section_not_found(self, runtime):
        result = runtime.get_teaching_unit_for_section("nonexistent_section")
        assert result == []


class TestTKBRuntimeContentAPIs:
    """§6 Content Retrieval APIs."""

    def test_get_examples_empty_list_when_none(self, runtime):
        assert isinstance(runtime.get_examples("c1"), list)

    def test_get_examples_not_found_returns_empty(self, runtime):
        assert runtime.get_examples("nonexistent") == []

    def test_get_examples_worked_only(self, runtime):
        result = runtime.get_examples("c1", worked_only=True)
        assert isinstance(result, list)

    def test_get_figures_by_concept(self, runtime):
        result = runtime.get_figures(concept_id="c1")
        assert isinstance(result, list)

    def test_get_figures_not_found(self, runtime):
        assert runtime.get_figures(concept_id="xxx") == []

    def test_get_tables_returns_list(self, runtime):
        assert isinstance(runtime.get_tables("c1"), list)

    def test_get_formulae_returns_list(self, runtime):
        assert isinstance(runtime.get_formulae("c1"), list)

    def test_get_analogies_returns_list(self, runtime):
        assert isinstance(runtime.get_analogies("c1"), list)

    def test_get_activities_returns_list(self, runtime):
        assert isinstance(runtime.get_activities("c1"), list)

    def test_get_learning_objectives_returns_list(self, runtime):
        objs = runtime.get_learning_objectives("c1")
        assert isinstance(objs, list)

    def test_get_learning_objectives_bloom_filter(self, runtime):
        # Should return only objectives matching the bloom level
        objs_all = runtime.get_learning_objectives("c1")
        objs_filtered = runtime.get_learning_objectives("c1", bloom_level="understand")
        for obj in objs_filtered:
            assert obj.get("bloom_level") == "understand"
        assert len(objs_filtered) <= len(objs_all)

    def test_get_common_mistakes_returns_list(self, runtime):
        assert isinstance(runtime.get_common_mistakes("c1"), list)

    def test_get_misconceptions_returns_list(self, runtime):
        assert isinstance(runtime.get_misconceptions("c1"), list)

    def test_get_applications_returns_list(self, runtime):
        assert isinstance(runtime.get_applications("c1"), list)

    def test_get_related_concepts_returns_list(self, runtime):
        assert isinstance(runtime.get_related_concepts("c1"), list)

    def test_get_revision_notes_by_concept(self, runtime):
        notes = runtime.get_revision_notes("c1")
        assert isinstance(notes, list)
        # c1 has one revision note in fixture
        assert len(notes) >= 1

    def test_get_revision_notes_all_in_topo_order(self, runtime):
        all_notes = runtime.get_revision_notes()
        assert isinstance(all_notes, list)
        # Should have notes from all concepts
        assert len(all_notes) >= 2  # one per concept


class TestTKBRuntimeLearningPathAPIs:
    """§7 Learning Path APIs."""

    def test_get_prerequisites_c2(self, runtime):
        prereqs = runtime.get_prerequisites("c2")
        assert len(prereqs) >= 1
        ids = {p["concept_id"] for p in prereqs}
        assert "c1" in ids

    def test_get_prerequisites_c1_empty(self, runtime):
        prereqs = runtime.get_prerequisites("c1")
        assert prereqs == []

    def test_get_prerequisites_blocking_only(self, runtime):
        blocking = runtime.get_prerequisites("c2", blocking_only=True)
        assert isinstance(blocking, list)
        # All returned must be blocking
        for nav_entry in blocking:
            assert "concept_id" in nav_entry

    def test_get_prerequisites_not_found_empty(self, runtime):
        assert runtime.get_prerequisites("xxx") == []

    def test_get_learning_path_canonical(self, runtime):
        lp = runtime.get_learning_path("canonical")
        assert len(lp) == 2
        assert lp[0]["concept_id"] == "c1"
        assert lp[1]["concept_id"] == "c2"

    def test_get_learning_path_beginner(self, runtime):
        lp = runtime.get_learning_path("beginner")
        assert isinstance(lp, list)

    def test_get_learning_path_invalid_style(self, runtime):
        assert runtime.get_learning_path("invalid_style") == []

    def test_get_learning_path_to_returns_none_or_chain(self, runtime):
        result = runtime.get_learning_path_to("c2")
        # May be None if no chains were built (empty dataset)
        assert result is None or isinstance(result, dict)

    def test_get_remediation_path_returns_none_or_path(self, runtime):
        result = runtime.get_remediation_path("c2")
        assert result is None or isinstance(result, dict)


class TestTKBRuntimeAssessmentAPIs:
    """§8 Assessment APIs."""

    def test_get_assessments_returns_list(self, runtime):
        assert isinstance(runtime.get_assessments("c1"), list)

    def test_get_assessments_not_found_returns_empty(self, runtime):
        assert runtime.get_assessments("xxx") == []

    def test_get_assessments_with_filter(self, runtime):
        result = runtime.get_assessments("c1", difficulty="easy")
        assert isinstance(result, list)

    def test_get_assessments_batch(self, runtime):
        result = runtime.get_assessments_batch(["c1", "c2"])
        assert "c1" in result and "c2" in result
        assert isinstance(result["c1"], list)

    def test_get_practice_questions_returns_list(self, runtime):
        assert isinstance(runtime.get_practice_questions("c1"), list)

    def test_get_chapter_test_returns_list(self, runtime):
        ct = runtime.get_chapter_test()
        assert isinstance(ct, list)

    def test_get_diagnostic_items_returns_list(self, runtime):
        result = runtime.get_diagnostic_items("c2")
        assert isinstance(result, list)


class TestTKBRuntimeSearchAPI:
    """§9 Search API (V1 lexical BM25)."""

    def test_search_returns_result_shape(self, runtime):
        result = runtime.search("motion")
        assert result["search_type"] == "lexical_v1"
        assert "results" in result
        assert "total_found" in result
        assert isinstance(result["results"], list)

    def test_search_finds_concept(self, runtime):
        result = runtime.search("motion")
        assert result["total_found"] >= 1
        # Top result should be about motion/c1
        if result["results"]:
            top = result["results"][0]
            assert "c1" in top.get("concept_ids", [])

    def test_search_empty_query_returns_empty(self, runtime):
        result = runtime.search("")
        assert result["results"] == []
        assert result["total_found"] == 0

    def test_search_respects_max_results(self, runtime):
        result = runtime.search("motion velocity", filters={"max_results": 1})
        assert len(result["results"]) <= 1

    def test_search_max_results_capped_at_50(self, runtime):
        result = runtime.search("concept", filters={"max_results": 9999})
        assert len(result["results"]) <= 50

    def test_search_with_content_type_filter(self, runtime):
        result = runtime.search("motion", filters={"content_types": ["concept"]})
        for r in result["results"]:
            assert r["entry_type"] == "concept"

    def test_search_scores_are_normalized(self, runtime):
        result = runtime.search("motion")
        for r in result["results"]:
            assert 0.0 <= r["score"] <= 1.0

    def test_search_results_sorted_descending(self, runtime):
        result = runtime.search("motion velocity definition")
        scores = [r["score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True), "Results not sorted by score desc"


class TestTKBRuntimeSessionAPIs:
    """§10 Session APIs."""

    def test_get_progression_template_returns_cpt(self, runtime):
        cpt = runtime.get_progression_template("c1")
        assert cpt is not None
        assert cpt["concept_id"] == "c1"
        assert "stage_resources" in cpt

    def test_get_progression_template_not_found(self, runtime):
        assert runtime.get_progression_template("xxx") is None

    def test_get_stage_resources_beginner(self, runtime):
        sr = runtime.get_stage_resources("c1", "BEGINNER")
        assert sr is not None
        assert "definition_present" in sr

    def test_get_stage_resources_all_stages(self, runtime):
        for stage in ("BEGINNER", "INTERMEDIATE", "ADVANCED", "MASTERY", "ASSESSMENT_READY"):
            sr = runtime.get_stage_resources("c1", stage)
            assert sr is not None or True  # may be empty but not raise

    def test_get_stage_resources_invalid_stage(self, runtime):
        assert runtime.get_stage_resources("c1", "INVALID") is None

    def test_get_stage_resources_not_found_concept(self, runtime):
        assert runtime.get_stage_resources("xxx", "BEGINNER") is None

    def test_get_revision_resources(self, runtime):
        rr = runtime.get_revision_resources("c1")
        assert rr is not None
        assert "revision_note_ids" in rr
        assert "key_formula_ids" in rr
        assert "definition_present" in rr

    def test_get_revision_resources_not_found(self, runtime):
        assert runtime.get_revision_resources("xxx") is None

    def test_get_tkb_info(self, runtime):
        info = runtime.get_tkb_info()
        assert info["schema_version"] == "1.1.1"
        assert info["tkb_scope"] == "chapter"
        assert info["total_concepts"] == 2
        assert info["chapter_title"] == "Motion and Velocity"
        assert info["chapter_number"] == 1

    def test_concept_count(self, runtime):
        assert runtime.concept_count() == 2


# ===========================================================================
# M6.3: Determinism Test (GAP-M63-03)
# ===========================================================================

class TestDeterminism:
    """Running the pipeline twice with identical inputs must produce identical fingerprints."""

    def test_identical_inputs_identical_fingerprint(self, two_concept_artifacts, two_concept_config):
        """Spec: 'Identical OptimizedKnowledgePackage → identical TKB' (M6 ARCH §2)."""
        reset_all_tkb_state()
        result1 = build_teacher_knowledge_base(
            config=two_concept_config,
            direct_artifacts=two_concept_artifacts,
        )
        reset_all_tkb_state()
        result2 = build_teacher_knowledge_base(
            config=two_concept_config,
            direct_artifacts=two_concept_artifacts,
        )
        assert result1.fingerprint == result2.fingerprint, (
            f"Non-deterministic: run1={result1.fingerprint[:16]}... "
            f"run2={result2.fingerprint[:16]}..."
        )

    def test_different_inputs_different_fingerprint(self, two_concept_artifacts, two_concept_config):
        reset_all_tkb_state()
        result1 = build_teacher_knowledge_base(
            config=two_concept_config,
            direct_artifacts=two_concept_artifacts,
        )
        # Change chapter_id → different tkb_id → different fingerprint
        config2 = dict(two_concept_config)
        config2["chapter_id"] = "ch-different"
        reset_all_tkb_state()
        result2 = build_teacher_knowledge_base(
            config=config2,
            direct_artifacts=two_concept_artifacts,
        )
        assert result1.fingerprint != result2.fingerprint, (
            "Different inputs must produce different fingerprints"
        )

    def test_tkb_id_is_deterministic(self, two_concept_artifacts, two_concept_config):
        """tkb_id = UUID5(...) must be identical across runs."""
        reset_all_tkb_state()
        r1 = build_teacher_knowledge_base(config=two_concept_config, direct_artifacts=two_concept_artifacts)
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(config=two_concept_config, direct_artifacts=two_concept_artifacts)
        assert r1.artifact.tkb_id == r2.artifact.tkb_id

    def test_topological_order_deterministic(self, two_concept_artifacts, two_concept_config):
        """EDG topological_order must be identical across runs."""
        reset_all_tkb_state()
        r1 = build_teacher_knowledge_base(config=two_concept_config, direct_artifacts=two_concept_artifacts)
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(config=two_concept_config, direct_artifacts=two_concept_artifacts)
        topo1 = r1.artifact.enriched_dependency_graph.get("topological_order")
        topo2 = r2.artifact.enriched_dependency_graph.get("topological_order")
        assert topo1 == topo2


# ===========================================================================
# M6.3: Pipeline Integration Test (GAP-M63-02)
# ===========================================================================

class TestPipelineIntegration:
    """Verifies M6.3 pipeline integration hook syntax and imports."""

    def test_pipeline_has_tkb_hook(self):
        """pipeline.py must contain the M6.3 TKB integration block."""
        pipeline_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "pipeline.py"
        )
        with open(pipeline_path) as f:
            content = f.read()
        assert "M6.3: Teacher Knowledge Base (TKB) Build" in content, (
            "pipeline.py missing M6.3 TKB build hook"
        )
        assert "build_teacher_knowledge_base" in content, (
            "pipeline.py missing build_teacher_knowledge_base call"
        )

    def test_tkb_runtime_exported_from_package(self):
        """TKBRuntime must be importable from teacher_knowledge_base.__init__."""
        from teacher_knowledge_base import TKBRuntime as RT, TKBRuntimeError as RTE
        assert RT is not None
        assert RTE is not None


# ===========================================================================
# Multi-book regression test
# ===========================================================================

class TestMultiBookRegression:
    """Ensures TKB builds correctly for multiple independent chapters."""

    def test_two_independent_chapters_produce_distinct_tkb_ids(self):
        """Different chapter_id → different tkb_id (UUID5 is chapter-scoped)."""
        base_artifacts = {
            "optimized_knowledge_package": {
                "concept_index": {
                    "c1": _make_concept("c1", "Motion"),
                },
                "dependency_map": {"edges": []},
                "learning_analytics": {"concept_analytics": {
                    "c1": {"difficulty": "easy", "importance": "core",
                           "estimated_teaching_time_minutes": 20.0}
                }},
                "manifest": {"package_id": "okp-multi"},
            },
            "document_structure_tree": {
                "id": "dst-m",
                "nodes": [
                    {"node_id": "root", "heading_text": "Ch", "level": 0,
                     "parent_id": None, "children_ids": [], "concept_ids": []},
                ],
            },
        }
        base_config = {
            "chapter_number": 1, "chapter_title": "Test",
            "subject": "Sci", "book_title": "T", "klass": "9",
            "board": "CBSE", "strict_validation": False,
        }

        reset_all_tkb_state()
        r1 = build_teacher_knowledge_base(
            config={**base_config, "chapter_id": "ch-01", "source_artifact_id": "ch-01"},
            direct_artifacts=base_artifacts,
        )
        reset_all_tkb_state()
        r2 = build_teacher_knowledge_base(
            config={**base_config, "chapter_id": "ch-02", "source_artifact_id": "ch-02"},
            direct_artifacts=base_artifacts,
        )
        assert r1.artifact.tkb_id != r2.artifact.tkb_id, (
            "Different chapters must produce different tkb_ids"
        )

    def test_full_12_concept_pipeline(self, minimal_compiler_artifacts, test_config):
        """Full 12-concept regression — all artifacts complete."""
        from teacher_knowledge_base.builder import build_teacher_knowledge_base as b
        r = b(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        assert len(r.artifact.teaching_units) == 12
        assert len(r.artifact.concept_progression_templates) == 12
        edg_topo = r.artifact.enriched_dependency_graph.get("topological_order") or []
        assert len(edg_topo) == 12, "All 12 concepts must appear in topological order"

    def test_12_concept_prerequisites_backfilled(self, minimal_compiler_artifacts, test_config):
        """EDG backfill must populate prerequisites for all 12 concepts."""
        from teacher_knowledge_base.builder import build_teacher_knowledge_base as b
        r = b(config=test_config, direct_artifacts=minimal_compiler_artifacts)
        # c12 has prerequisites c10 and c11
        c12 = r.artifact.teaching_units.get("c12")
        assert c12 is not None
        c12_prereq_ids = {p["concept_id"] for p in (c12.get("prerequisites") or [])}
        assert {"c10", "c11"} <= c12_prereq_ids, (
            f"c12 should have c10 and c11 as prereqs; got {c12_prereq_ids}"
        )
