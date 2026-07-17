"""
tests/test_structural_validator.py — exhaustive tests for Milestone 2's
modules/structural_validator.py (Structural Validation).

No PyMuPDF dependency: fixtures here are plain dicts built to match the
*shape* `canonical.canonical_fields()` / `pipeline.py`'s `topics_out`
entries actually produce (same "no pipeline.py execution needed" pattern
`tests/test_topic_linker_integration.py` already established), never an
actual pipeline.py run.

Organized one test class per rule (`_check_*` function in
modules/structural_validator.py), plus a final class for the
`validate_structural_completeness()` entry point's own behavior
(report shape, crash resilience, invalid input). See
tests/test_validator_structural_integration.py for how this module is
wired into modules/validator.py's `validate_chapter()`.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import pytest

from modules import structural_validator as sv
from modules.structural_validator import (
    ERROR,
    INFO,
    WARNING,
    REQUIRED_SECTIONS,
    validate_structural_completeness,
)


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------

def canon(
    oid: str,
    otype: str,
    *,
    topic_ids: Optional[List[str]] = None,
    concept_ids: Optional[List[str]] = None,
    chapter_reference: str = "book:chap-1",
    provenance: Optional[Dict[str, Any]] = None,
    urn: Optional[str] = "SET",
) -> Dict[str, Any]:
    """Builds a dict shaped like `canonical.canonical_fields()`'s output
    merged with an object's own fields (subset relevant to this module).
    `urn="SET"` (the default) auto-derives a urn; pass `urn=None`
    explicitly to omit it (for missing_urn tests)."""
    d: Dict[str, Any] = {
        "id": oid,
        "object_type": otype,
        "topic_ids": topic_ids if topic_ids is not None else [],
        "concept_ids": concept_ids if concept_ids is not None else [],
        "chapter_reference": chapter_reference,
        "provenance": (
            provenance if provenance is not None
            else {"source_page": 1, "extraction_stage": "test", "timestamp": "2026-01-01T00:00:00Z"}
        ),
    }
    if urn == "SET":
        d["urn"] = f"urn:test:{otype}:{oid}"
    elif urn is not None:
        d["urn"] = urn
    return d


def topic(
    tid: str,
    *,
    parent: Optional[str] = None,
    children: Optional[List[str]] = None,
    concepts: Optional[List[str]] = None,
    level: int = 1,
    urn: Optional[str] = "SET",
    **reverse_lists: Any,
) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": tid, "title": tid, "parent": parent, "children": children or [],
        "concepts": concepts or [], "level": level,
        "definitions": [], "examples": [], "activities": [], "figures": [], "tables": [],
        "equations": [], "diagrams": [], "charts": [], "graphs": [], "maps": [], "timelines": [],
        "boxes": [], "notes": [], "warnings": [],
    }
    if urn == "SET":
        d["urn"] = f"urn:test:topic:{tid}"
    elif urn is not None:
        d["urn"] = urn
    d.update(reverse_lists)
    return d


def base_document(**overrides: Any) -> Dict[str, Any]:
    """A minimal, fully-present, internally-consistent Chapter JSON dict
    -- every REQUIRED_SECTIONS key present, no topics/concepts/objects at
    all. `validate_structural_completeness()` on this returns
    `status="pass"` with zero issues (asserted in
    TestEntryPoint::test_empty_but_complete_document_passes below). Tests
    build on top of this via `overrides` / by mutating a deep copy."""
    doc: Dict[str, Any] = {section: ([] if section in sv.CANONICAL_OBJECT_SECTIONS
                                      or section in ("pages", "topic_tree", "topics",
                                                      "blocks", "educational_objects", "semantic_index")
                                      else {})
                            for section in REQUIRED_SECTIONS}
    doc["schema_version"] = "2.0.0"
    doc.update(overrides)
    return doc


def with_topics_and_objects(topics: List[Dict[str, Any]], **sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    doc = base_document(topics=topics)
    doc.update(sections)
    return doc


def issues_for(report: Dict[str, Any], rule: str) -> List[Dict[str, Any]]:
    return [i for i in report["issues"] if i["rule"] == rule]


def has_issue(report: Dict[str, Any], rule: str, severity: Optional[str] = None) -> bool:
    return any(i["rule"] == rule and (severity is None or i["severity"] == severity) for i in report["issues"])


# --------------------------------------------------------------------------
# 0. base_document sanity
# --------------------------------------------------------------------------

class TestBaseDocumentFixture:
    def test_empty_but_complete_document_is_clean(self):
        report = validate_structural_completeness(base_document())
        assert report["status"] == "pass"
        assert report["issues"] == []


# --------------------------------------------------------------------------
# 1. Required sections
# --------------------------------------------------------------------------

class TestRequiredSections:
    def test_missing_section_is_error(self):
        doc = base_document()
        del doc["concepts"]
        report = validate_structural_completeness(doc)
        assert report["status"] == "fail"
        errs = issues_for(report, "missing_required_section")
        assert any(e["section"] == "concepts" for e in errs)
        assert all(e["severity"] == ERROR for e in errs)

    def test_all_sections_present_no_missing_section_issue(self):
        report = validate_structural_completeness(base_document())
        assert not has_issue(report, "missing_required_section")

    def test_every_required_section_individually_detected(self):
        for section in REQUIRED_SECTIONS:
            doc = base_document()
            del doc[section]
            report = validate_structural_completeness(doc)
            assert has_issue(report, "missing_required_section", ERROR), f"section={section}"


# --------------------------------------------------------------------------
# 2. Identity
# --------------------------------------------------------------------------

class TestIdentity:
    def test_missing_id_is_error(self):
        obj = canon("f1", "figure")
        del obj["id"]
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_identity", ERROR)

    def test_empty_string_id_is_error(self):
        obj = canon("", "figure")
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_identity", ERROR)

    def test_missing_urn_is_warning(self):
        obj = canon("f1", "figure", urn=None)
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_urn", WARNING)
        assert not has_issue(report, "missing_urn", ERROR)

    def test_urn_present_no_warning(self):
        obj = canon("f1", "figure")
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "missing_urn")

    def test_duplicate_id_across_sections_is_error(self):
        fig = canon("dup-1", "figure")
        tab = canon("dup-1", "table")
        doc = with_topics_and_objects([], figures=[fig], tables=[tab])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "duplicate_object_id")
        assert len(errs) == 1
        assert errs[0]["severity"] == ERROR
        assert set(errs[0]["details"]["locations"]) == {"figures[0]", "tables[0]"}

    def test_duplicate_urn_across_sections_is_error(self):
        fig = canon("f1", "figure", urn="urn:same")
        tab = canon("t1", "table", urn="urn:same")
        doc = with_topics_and_objects([], figures=[fig], tables=[tab])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "duplicate_urn", ERROR)

    def test_unique_ids_no_duplicate_issue(self):
        doc = with_topics_and_objects([], figures=[canon("f1", "figure")], tables=[canon("t1", "table")])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "duplicate_object_id")
        assert not has_issue(report, "duplicate_urn")

    def test_malformed_object_entry_is_error(self):
        doc = with_topics_and_objects([], figures=["not-a-dict"])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "malformed_object_entry", ERROR)

    def test_malformed_topic_entry_is_error(self):
        doc = base_document(topics=["not-a-dict"])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "malformed_object_entry", ERROR)

    def test_missing_object_type_is_warning(self):
        obj = canon("f1", "figure")
        del obj["object_type"]
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_object_type", WARNING)

    def test_duplicate_topic_ids_is_error(self):
        doc = base_document(topics=[topic("t1"), topic("t1")])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "duplicate_object_id", ERROR)

    def test_topic_and_canonical_object_sharing_id_is_error(self):
        # ids are a single global namespace in this document -- a topic
        # and an unrelated figure claiming the same id is exactly the
        # kind of identity collision #2 exists to catch.
        doc = with_topics_and_objects([topic("shared")], figures=[canon("shared", "figure")])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "duplicate_object_id", ERROR)


# --------------------------------------------------------------------------
# 3. Chapter membership
# --------------------------------------------------------------------------

class TestChapterMembership:
    def test_missing_chapter_reference_is_error(self):
        obj = canon("f1", "figure")
        del obj["chapter_reference"]
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_chapter_reference", ERROR)

    def test_blank_chapter_reference_is_error(self):
        obj = canon("f1", "figure", chapter_reference="   ")
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_chapter_reference", ERROR)

    def test_consistent_chapter_reference_no_issue(self):
        doc = with_topics_and_objects(
            [], figures=[canon("f1", "figure")], tables=[canon("t1", "table")],
        )
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "chapter_reference_mismatch")
        assert not has_issue(report, "missing_chapter_reference")

    def test_mismatched_chapter_reference_is_error(self):
        fig = canon("f1", "figure", chapter_reference="book:chap-1")
        tab = canon("t1", "table", chapter_reference="book:chap-1")
        rogue = canon("r1", "equation", chapter_reference="OTHER-BOOK:chap-9")
        doc = with_topics_and_objects([], figures=[fig], tables=[tab], equations=[rogue])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "chapter_reference_mismatch")
        assert len(errs) == 1
        assert errs[0]["object_id"] == "r1"
        assert errs[0]["details"]["expected"] == "book:chap-1"


# --------------------------------------------------------------------------
# 4. topic_ids -> topics[].id
# --------------------------------------------------------------------------

class TestTopicIdReferences:
    def test_valid_topic_reference_no_issue(self):
        doc = with_topics_and_objects([topic("t1")], figures=[canon("f1", "figure", topic_ids=["t1"])])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "broken_topic_reference")

    def test_broken_topic_reference_is_error(self):
        doc = with_topics_and_objects([topic("t1")], figures=[canon("f1", "figure", topic_ids=["ghost"])])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "broken_topic_reference")
        assert len(errs) == 1
        assert errs[0]["severity"] == ERROR
        assert errs[0]["details"]["topic_id"] == "ghost"

    def test_non_string_topic_id_entry_is_error(self):
        obj = canon("f1", "figure")
        obj["topic_ids"] = [123]
        doc = with_topics_and_objects([topic("t1")], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "invalid_topic_reference", ERROR)

    def test_empty_topic_ids_no_broken_reference(self):
        doc = with_topics_and_objects([topic("t1")], figures=[canon("f1", "figure", topic_ids=[])])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "broken_topic_reference")

    def test_checked_across_every_canonical_section(self):
        for section, otype in sv._SECTION_TO_OBJECT_TYPE.items():
            doc = with_topics_and_objects([], **{section: [canon("x1", otype, topic_ids=["ghost"])]})
            report = validate_structural_completeness(doc)
            assert has_issue(report, "broken_topic_reference", ERROR), f"section={section}"


# --------------------------------------------------------------------------
# 5. concept_ids -> concepts[].id  (+ TopicNode.concepts)
# --------------------------------------------------------------------------

class TestConceptIdReferences:
    def test_valid_concept_reference_no_issue(self):
        doc = with_topics_and_objects(
            [], concepts=[canon("c1", "concept")], figures=[canon("f1", "figure", concept_ids=["c1"])],
        )
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "broken_concept_reference")

    def test_broken_concept_reference_on_object_is_error(self):
        doc = with_topics_and_objects([], figures=[canon("f1", "figure", concept_ids=["ghost"])])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "broken_concept_reference")
        assert any(e["object_id"] == "f1" for e in errs)
        assert all(e["severity"] == ERROR for e in errs)

    def test_broken_concept_reference_on_topic_concepts_is_error(self):
        doc = with_topics_and_objects([topic("t1", concepts=["ghost"])])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "broken_concept_reference")
        assert any(e["object_id"] == "t1" for e in errs)

    def test_topic_concept_names_field_not_checked(self):
        t = topic("t1")
        t["concept_names"] = ["Not A Real Id On Purpose"]
        doc = with_topics_and_objects([t])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "broken_concept_reference")

    def test_non_string_concept_id_entry_is_error(self):
        obj = canon("f1", "figure")
        obj["concept_ids"] = [None]
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "invalid_concept_reference", ERROR)


# --------------------------------------------------------------------------
# 6. Reverse-reference consistency
# --------------------------------------------------------------------------

class TestReverseReferenceConsistency:
    def test_fully_consistent_forward_and_reverse_no_issue(self):
        t1 = topic("t1", figures=["f1"])
        f1 = canon("f1", "figure", topic_ids=["t1"])
        doc = with_topics_and_objects([t1], figures=[f1])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "reverse_reference_missing")
        assert not has_issue(report, "broken_reverse_reference")

    def test_forward_without_reverse_is_warning(self):
        t1 = topic("t1")  # figures=[] (default) -- doesn't list f1 back
        f1 = canon("f1", "figure", topic_ids=["t1"])
        doc = with_topics_and_objects([t1], figures=[f1])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "reverse_reference_missing")
        assert any(e["object_id"] == "f1" and e["severity"] == WARNING for e in errs)

    def test_reverse_pointing_at_nonexistent_object_is_error(self):
        t1 = topic("t1", figures=["ghost"])
        doc = with_topics_and_objects([t1], figures=[])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "broken_reverse_reference")
        assert any(e["details"]["figures"] == "ghost" for e in errs)
        assert all(e["severity"] == ERROR for e in errs)

    def test_reverse_pointing_at_real_object_missing_forward_link_is_warning(self):
        t1 = topic("t1", figures=["f1"])
        f1 = canon("f1", "figure", topic_ids=[])  # never links back to t1
        doc = with_topics_and_objects([t1], figures=[f1])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "reverse_reference_missing")
        assert any(e["object_id"] == "f1" for e in errs)

    def test_known_pipeline_quirk_topic_definitions_holds_terms_not_ids(self):
        """Regression-style test: pipeline.py's own topics_out['definitions']
        is populated with TERM STRINGS (`[d["term"] for d in definitions ...]`),
        not Definition object ids, even though modules.topic_linker.
        TOPIC_REVERSE_FIELDS declares 'definition' -> 'definitions' as an
        id-holding reverse field. This is a real, pre-existing structural
        inconsistency in the pipeline's own output shape -- the validator
        is *supposed* to catch it (that's the whole point of this rule),
        not paper over it."""
        d1 = canon("def-1", "definition", topic_ids=["t1"])
        t1 = topic("t1", definitions=["the actual term text"])  # NOT d1's id
        doc = with_topics_and_objects([t1], definitions=[d1])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "broken_reverse_reference", ERROR)

    def test_object_type_with_no_reverse_field_is_skipped(self):
        # 'chart' has no TopicNode reverse-list slot (see
        # modules.topic_linker.TOPIC_REVERSE_FIELDS) -- inconsistency here
        # must never be flagged, there's nothing to be consistent with.
        assert sv.TOPIC_REVERSE_FIELDS.get("chart") is None
        t1 = topic("t1")
        c1 = canon("ch1", "chart", topic_ids=["t1"])
        doc = with_topics_and_objects([t1], charts=[c1])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "reverse_reference_missing")
        assert not has_issue(report, "broken_reverse_reference")

    def test_non_string_entry_in_reverse_list_is_error(self):
        t1 = topic("t1", figures=[42])
        doc = with_topics_and_objects([t1], figures=[])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "invalid_reverse_reference", WARNING)

    def test_concept_topic_reciprocity(self):
        t1 = topic("t1", concepts=["c1"])
        c1 = canon("c1", "concept", topic_ids=["t1"])
        doc = with_topics_and_objects([t1], concepts=[c1])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "reverse_reference_missing")
        assert not has_issue(report, "broken_reverse_reference")


# --------------------------------------------------------------------------
# 7. Orphan objects
# --------------------------------------------------------------------------

class TestOrphanObjects:
    def test_object_with_no_topic_ids_is_warning(self):
        doc = with_topics_and_objects([], figures=[canon("f1", "figure", topic_ids=[])])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "orphan_object", WARNING)

    def test_object_with_topic_ids_not_orphan(self):
        doc = with_topics_and_objects([topic("t1")], figures=[canon("f1", "figure", topic_ids=["t1"])])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "orphan_object")

    def test_isolated_topic_no_parent_no_children_no_content_is_info(self):
        doc = base_document(topics=[topic("t1")])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "orphan_topic", INFO)

    def test_topic_with_content_not_orphan(self):
        doc = base_document(topics=[topic("t1", figures=["f1"])])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "orphan_topic")

    def test_topic_that_is_a_child_not_orphan_even_without_content(self):
        parent = topic("p1", children=["c1"])
        child = topic("c1", parent="p1")
        doc = base_document(topics=[parent, child])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "orphan_topic")

    def test_root_topic_with_children_not_orphan(self):
        parent = topic("p1", children=["c1"])
        child = topic("c1", parent="p1", figures=["f1"])
        doc = base_document(topics=[parent, child])
        report = validate_structural_completeness(doc)
        # p1 has children -> not orphan (is_child_of_someone/has_content
        # aren't the only escape -- children make it a real hierarchy root)
        assert not any(i["rule"] == "orphan_topic" and i["object_id"] == "p1" for i in report["issues"])


# --------------------------------------------------------------------------
# 8. Duplicate references
# --------------------------------------------------------------------------

class TestDuplicateReferences:
    def test_duplicate_topic_ids_entry_is_warning(self):
        obj = canon("f1", "figure", topic_ids=["t1", "t1"])
        doc = with_topics_and_objects([topic("t1")], figures=[obj])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "duplicate_reference_in_list")
        assert any(e["details"]["field"] == "topic_ids" and e["details"]["value"] == "t1" for e in errs)

    def test_duplicate_concept_ids_entry_is_warning(self):
        obj = canon("f1", "figure", concept_ids=["c1", "c1", "c1"])
        doc = with_topics_and_objects([], concepts=[canon("c1", "concept")], figures=[obj])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "duplicate_reference_in_list")
        assert any(e["details"]["field"] == "concept_ids" and e["details"]["count"] == 3 for e in errs)

    def test_duplicate_children_entry_is_warning(self):
        doc = base_document(topics=[topic("t1", children=["c1", "c1"]), topic("c1", parent="t1")])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "duplicate_reference_in_list")
        assert any(e["details"]["field"] == "children" for e in errs)

    def test_duplicate_graph_node_is_warning(self):
        doc = base_document(topics=[topic("t1")],
                             learning_graph={"nodes": ["t1", "t1"], "edges": []})
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "duplicate_reference_in_list")
        assert any(e["section"] == "learning_graph" for e in errs)

    def test_duplicate_graph_edge_is_warning(self):
        edge = {"source": "t1", "target": "t2", "relationship_type": "precedes"}
        doc = base_document(
            topics=[topic("t1"), topic("t2")],
            learning_graph={"nodes": ["t1", "t2"], "edges": [dict(edge), dict(edge)]},
        )
        report = validate_structural_completeness(doc)
        assert has_issue(report, "duplicate_graph_edge", WARNING)

    def test_no_duplicates_no_issue(self):
        obj = canon("f1", "figure", topic_ids=["t1"])
        doc = with_topics_and_objects([topic("t1")], figures=[obj])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "duplicate_reference_in_list")
        assert not has_issue(report, "duplicate_graph_edge")


# --------------------------------------------------------------------------
# 9. Broken graph edges
# --------------------------------------------------------------------------

class TestBrokenGraphEdges:
    def test_valid_learning_graph_no_issue(self):
        doc = base_document(
            topics=[topic("t1"), topic("t2")],
            learning_graph={"nodes": ["t1", "t2"], "edges": [
                {"source": "t1", "target": "t2", "relationship_type": "precedes"},
            ]},
        )
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "broken_graph_edge")
        assert not has_issue(report, "dangling_graph_node")
        assert not has_issue(report, "graph_node_coverage_incomplete")

    def test_edge_target_not_in_nodes_is_error(self):
        doc = base_document(
            topics=[topic("t1")],
            learning_graph={"nodes": ["t1"], "edges": [
                {"source": "t1", "target": "ghost", "relationship_type": "precedes"},
            ]},
        )
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "broken_graph_edge")
        assert any(e["object_id"] == "ghost" and e["details"]["role"] == "target" for e in errs)
        assert all(e["severity"] == ERROR for e in errs)

    def test_node_not_a_real_topic_id_is_warning(self):
        doc = base_document(topics=[topic("t1")], learning_graph={"nodes": ["t1", "ghost"], "edges": []})
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "dangling_graph_node")
        assert any(e["object_id"] == "ghost" and e["severity"] == WARNING for e in errs)

    def test_real_topic_missing_from_nodes_is_warning(self):
        doc = base_document(topics=[topic("t1"), topic("t2")], learning_graph={"nodes": ["t1"], "edges": []})
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "graph_node_coverage_incomplete")
        assert any("t2" in e["details"]["missing"] for e in errs)

    def test_concept_graph_checked_against_concepts(self):
        doc = with_topics_and_objects(
            [], concepts=[canon("c1", "concept")],
            concept_graph={"nodes": ["c1", "c2"], "edges": [
                {"source": "c1", "target": "c2", "relationship_type": "related_to"},
            ]},
        )
        report = validate_structural_completeness(doc)
        assert has_issue(report, "dangling_graph_node", WARNING)

    def test_malformed_edge_missing_source_is_error(self):
        doc = base_document(topics=[topic("t1")],
                             learning_graph={"nodes": ["t1"], "edges": [{"target": "t1"}]})
        report = validate_structural_completeness(doc)
        assert has_issue(report, "malformed_graph_edge", ERROR)

    def test_non_dict_edge_is_error(self):
        doc = base_document(topics=[topic("t1")],
                             learning_graph={"nodes": ["t1"], "edges": ["not-a-dict"]})
        report = validate_structural_completeness(doc)
        assert has_issue(report, "malformed_graph_edge", ERROR)

    def test_non_string_node_is_error(self):
        doc = base_document(topics=[topic("t1")], learning_graph={"nodes": ["t1", 42], "edges": []})
        report = validate_structural_completeness(doc)
        assert has_issue(report, "invalid_graph_node", ERROR)


# --------------------------------------------------------------------------
# 10. Missing provenance
# --------------------------------------------------------------------------

class TestMissingProvenance:
    def test_no_provenance_key_is_warning(self):
        obj = canon("f1", "figure")
        del obj["provenance"]
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_provenance", WARNING)

    def test_empty_provenance_dict_is_warning(self):
        obj = canon("f1", "figure", provenance={})
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_provenance", WARNING)

    def test_all_falsy_provenance_fields_is_warning(self):
        obj = canon("f1", "figure", provenance={
            "source_page": None, "source_block_id": None, "extraction_stage": "",
            "recognizer": None, "evidence_span": None,
        })
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_provenance", WARNING)

    def test_provenance_with_source_page_no_warning(self):
        obj = canon("f1", "figure", provenance={"source_page": 3})
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "missing_provenance")

    def test_missing_timestamp_is_info_not_warning(self):
        obj = canon("f1", "figure", provenance={"source_page": 3})  # no timestamp
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "missing_provenance_timestamp", INFO)

    def test_full_provenance_no_issues(self):
        obj = canon("f1", "figure", provenance={
            "source_page": 3, "extraction_stage": "stage_d", "timestamp": "2026-01-01T00:00:00Z",
        })
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "missing_provenance")
        assert not has_issue(report, "missing_provenance_timestamp")


# --------------------------------------------------------------------------
# 11. Parent-child hierarchy
# --------------------------------------------------------------------------

class TestParentChildHierarchy:
    def test_clean_two_level_hierarchy_no_issues(self):
        doc = base_document(
            topics=[topic("t1", children=["t1a"]), topic("t1a", parent="t1", level=2)],
            topic_tree=[{"id": "t1", "title": "t1", "children": [{"id": "t1a", "title": "t1a", "children": []}]}],
        )
        report = validate_structural_completeness(doc)
        for rule in (
            "broken_parent_reference", "broken_child_reference", "parent_child_mismatch",
            "hierarchy_cycle_detected", "unexpected_level_jump", "topic_missing_from_tree",
            "topic_tree_dangling_node", "duplicate_topic_tree_node",
        ):
            assert not has_issue(report, rule), rule

    def test_broken_parent_reference_is_error(self):
        doc = base_document(topics=[topic("t1", parent="ghost")])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "broken_parent_reference", ERROR)

    def test_invalid_parent_type_is_error(self):
        t = topic("t1")
        t["parent"] = 42
        doc = base_document(topics=[t])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "invalid_parent_reference", ERROR)

    def test_parent_missing_child_backref_is_warning(self):
        doc = base_document(topics=[topic("p1", children=[]), topic("c1", parent="p1")])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "parent_child_mismatch", WARNING)

    def test_broken_child_reference_is_error(self):
        doc = base_document(topics=[topic("p1", children=["ghost"])])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "broken_child_reference", ERROR)

    def test_invalid_child_type_is_error(self):
        t = topic("p1", children=[None])
        doc = base_document(topics=[t])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "invalid_child_reference", ERROR)

    def test_child_disagreeing_parent_is_warning(self):
        doc = base_document(topics=[
            topic("p1", children=["c1"]), topic("other"), topic("c1", parent="other"),
        ])
        report = validate_structural_completeness(doc)
        errs = issues_for(report, "parent_child_mismatch")
        assert any(e["object_id"] == "c1" for e in errs)

    def test_two_node_cycle_is_error(self):
        doc = base_document(topics=[topic("a", parent="b"), topic("b", parent="a")])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "hierarchy_cycle_detected", ERROR)

    def test_self_referencing_parent_is_cycle(self):
        doc = base_document(topics=[topic("a", parent="a")])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "hierarchy_cycle_detected", ERROR)

    def test_level_jump_is_warning(self):
        doc = base_document(topics=[topic("p1", children=["c1"], level=1), topic("c1", parent="p1", level=5)])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "unexpected_level_jump", WARNING)

    def test_correct_level_increment_no_warning(self):
        doc = base_document(topics=[topic("p1", children=["c1"], level=1), topic("c1", parent="p1", level=2)])
        report = validate_structural_completeness(doc)
        assert not has_issue(report, "unexpected_level_jump")

    def test_topic_missing_from_tree_is_error(self):
        doc = base_document(topics=[topic("t1")], topic_tree=[])
        report = validate_structural_completeness(doc)
        assert has_issue(report, "topic_missing_from_tree", ERROR)

    def test_topic_tree_dangling_node_is_error(self):
        doc = base_document(
            topics=[topic("t1")],
            topic_tree=[{"id": "t1", "title": "t1", "children": []},
                        {"id": "ghost", "title": "ghost", "children": []}],
        )
        report = validate_structural_completeness(doc)
        assert has_issue(report, "topic_tree_dangling_node", ERROR)

    def test_duplicate_topic_tree_node_is_error(self):
        doc = base_document(
            topics=[topic("t1")],
            topic_tree=[{"id": "t1", "title": "t1", "children": []},
                        {"id": "t1", "title": "t1", "children": []}],
        )
        report = validate_structural_completeness(doc)
        assert has_issue(report, "duplicate_topic_tree_node", ERROR)

    def test_no_topics_no_topic_tree_checks_run(self):
        # topic_tree comparison is skipped entirely when there are no
        # topics at all -- nothing to be inconsistent with, and an empty
        # `topic_tree: []` alongside an empty `topics: []` is valid.
        doc = base_document(topics=[], topic_tree=[])
        report = validate_structural_completeness(doc)
        assert report["status"] == "pass"


# --------------------------------------------------------------------------
# Entry point: report shape, robustness, severity classification
# --------------------------------------------------------------------------

class TestEntryPoint:
    def test_empty_but_complete_document_passes(self):
        report = validate_structural_completeness(base_document())
        assert report["status"] == "pass"
        assert report["errors"] == []

    def test_report_shape(self):
        report = validate_structural_completeness(base_document())
        for key in (
            "validator", "validator_version", "generated_at", "status",
            "rules_run", "rules_crashed", "issues", "errors", "warnings",
            "info", "summary",
        ):
            assert key in report
        assert report["validator"] == "structural_validator"
        summary = report["summary"]
        for key in ("total_issues", "error_count", "warning_count", "info_count", "issues_by_rule"):
            assert key in summary

    def test_every_rule_runs_on_clean_document(self):
        report = validate_structural_completeness(base_document())
        expected_rules = {name for name, _ in sv._RULES}
        assert set(report["rules_run"]) == expected_rules
        assert report["rules_crashed"] == []

    def test_non_dict_input_is_error_and_fail(self):
        report = validate_structural_completeness("not-a-dict")
        assert report["status"] == "fail"
        assert has_issue(report, "invalid_input", ERROR)
        assert report["rules_run"] == []

    def test_none_input_is_error_and_fail(self):
        report = validate_structural_completeness(None)
        assert report["status"] == "fail"
        assert has_issue(report, "invalid_input", ERROR)

    def test_crashing_rule_is_recorded_not_silently_skipped(self, monkeypatch):
        def _boom(chapter_dict):
            raise RuntimeError("simulated rule failure")

        monkeypatch.setattr(sv, "_RULES", [("identity", _boom)])
        report = validate_structural_completeness(base_document())
        assert report["status"] == "fail"
        assert report["rules_crashed"] == ["identity"]
        assert has_issue(report, "identity_check_crashed", ERROR)

    def test_partial_crash_still_runs_other_rules(self, monkeypatch):
        def _boom(chapter_dict):
            raise RuntimeError("simulated rule failure")

        real_rules = list(sv._RULES)
        patched = [(name, _boom if name == "identity" else fn) for name, fn in real_rules]
        monkeypatch.setattr(sv, "_RULES", patched)

        doc = base_document()
        report = validate_structural_completeness(doc)
        assert "identity" in report["rules_crashed"]
        assert "required_sections" in report["rules_run"]
        assert report["status"] == "fail"

    def test_warnings_and_info_never_flip_status_to_fail(self):
        # object with no provenance/no urn/no topic_ids -> several
        # WARNING/INFO issues, zero ERROR issues -> still "pass".
        obj = canon("f1", "figure", urn=None, provenance={})
        del obj["provenance"]
        doc = with_topics_and_objects([], figures=[obj])
        report = validate_structural_completeness(doc)
        assert report["summary"]["warning_count"] > 0
        assert report["summary"]["error_count"] == 0
        assert report["status"] == "pass"

    def test_any_error_flips_status_to_fail(self):
        doc = with_topics_and_objects([], figures=[canon("f1", "figure", topic_ids=["ghost"])])
        report = validate_structural_completeness(doc)
        assert report["summary"]["error_count"] > 0
        assert report["status"] == "fail"

    def test_issues_by_rule_counts_match_issue_list(self):
        obj1 = canon("f1", "figure", topic_ids=["ghost1"])
        obj2 = canon("f2", "figure", topic_ids=["ghost2"])
        doc = with_topics_and_objects([], figures=[obj1, obj2])
        report = validate_structural_completeness(doc)
        assert report["summary"]["issues_by_rule"]["broken_topic_reference"] == 2

    def test_does_not_mutate_input(self):
        doc = with_topics_and_objects([topic("t1")], figures=[canon("f1", "figure", topic_ids=["t1"])])
        before = copy.deepcopy(doc)
        validate_structural_completeness(doc)
        assert doc == before

    def test_severity_values_are_exactly_the_three_classes(self):
        # every possible issue's severity must be one of the task's own
        # three classes -- never a fourth, never lowercase.
        doc = base_document()
        del doc["concepts"]  # -> ERROR
        obj = canon("f1", "figure", urn=None)  # -> WARNING (missing_urn)
        doc["figures"] = [obj]
        report = validate_structural_completeness(doc)
        assert {i["severity"] for i in report["issues"]} <= {ERROR, WARNING, INFO}
        assert ERROR in {i["severity"] for i in report["issues"]}
        assert WARNING in {i["severity"] for i in report["issues"]}


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))