"""
tests/test_topic_linker.py — unit tests for Milestone 1's
modules/topic_linker.py (Universal Object Linking).

Covers, per requirement:
  - resolve_object_page: top-level `page`, provenance.source_page
    fallback, and "no deterministic page -> None" (never guess).
  - make_page_topic_lookup: containment, no-match, boundary pages,
    overlap tie-break (last topic in input order wins, matching
    pipeline.py's own _topic_lookup_factory), and malformed topic
    ranges are never candidates.
  - link_object_to_topic: linking a single object, never overwriting
    an already-linked object, never guessing when unresolvable.
  - link_objects_to_topics: reusable across every supported object
    type, populates topic_ids + reverse TopicNode lists, is
    idempotent, skips malformed entries, never writes concept_ids.
  - resolve_deterministic_concept_ids: opt-in only, `None` name_field
    never inspects the object, exact case-insensitive match only.
  - link_universal_objects: the pipeline.py integration point --
    end-to-end across all nine supported types plus an unsupported
    type, unresolved objects, reverse-ref population, idempotency,
    and that concepts/glossary/definitions are left alone (not passed
    through this entry point at all).
"""
from __future__ import annotations

import copy

import pytest

from modules import topic_linker
from modules.topic_linker import (
    TOPIC_REVERSE_FIELDS,
    UNIVERSAL_LINKING_OBJECT_TYPES,
    link_object_to_topic,
    link_objects_to_topics,
    link_universal_objects,
    make_page_topic_lookup,
    resolve_deterministic_concept_ids,
    resolve_object_page,
)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

def make_topic(id_, page_start, page_end, **extra):
    d = {"id": id_, "page_start": page_start, "page_end": page_end}
    d.update(extra)
    return d


def make_obj(id_="o1", page=None, topic_ids=None, provenance=None, **extra):
    d = {"id": id_}
    if page is not None:
        d["page"] = page
    if topic_ids is not None:
        d["topic_ids"] = topic_ids
    if provenance is not None:
        d["provenance"] = provenance
    d.update(extra)
    return d


TWO_TOPICS = [
    make_topic("t1", 1, 5),
    make_topic("t2", 6, 10),
]


# --------------------------------------------------------------------------
# resolve_object_page
# --------------------------------------------------------------------------

class TestResolveObjectPage:
    def test_top_level_page(self):
        assert resolve_object_page({"page": 3}) == 3

    def test_falls_back_to_provenance_source_page(self):
        assert resolve_object_page({"provenance": {"source_page": 7}}) == 7

    def test_top_level_page_takes_priority_over_provenance(self):
        obj = {"page": 3, "provenance": {"source_page": 7}}
        assert resolve_object_page(obj) == 3

    def test_missing_page_returns_none(self):
        assert resolve_object_page({}) is None

    def test_non_int_page_returns_none(self):
        assert resolve_object_page({"page": "3"}) is None

    def test_bool_page_is_rejected(self):
        # bool is a subclass of int in Python -- must not be treated as
        # a real page number.
        assert resolve_object_page({"page": True}) is None

    def test_provenance_not_a_dict_is_ignored(self):
        assert resolve_object_page({"provenance": "nope"}) is None

    def test_provenance_source_page_non_int_returns_none(self):
        assert resolve_object_page({"provenance": {"source_page": None}}) is None


# --------------------------------------------------------------------------
# make_page_topic_lookup
# --------------------------------------------------------------------------

class TestMakePageTopicLookup:
    def test_page_inside_first_topic(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        assert lookup(3) == "t1"

    def test_page_inside_second_topic(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        assert lookup(8) == "t2"

    def test_boundary_pages(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        assert lookup(1) == "t1"
        assert lookup(5) == "t1"
        assert lookup(6) == "t2"
        assert lookup(10) == "t2"

    def test_page_outside_any_range_returns_none(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        assert lookup(11) is None
        assert lookup(0) is None

    def test_none_page_returns_none(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        assert lookup(None) is None

    def test_overlapping_ranges_last_topic_wins(self):
        # Mirrors pipeline.py's own _topic_lookup_factory tie-break: the
        # LAST candidate (in input order) whose range contains the page.
        topics = [make_topic("a", 1, 10), make_topic("b", 5, 8)]
        lookup = make_page_topic_lookup(topics)
        assert lookup(6) == "b"

    def test_topic_missing_page_range_never_a_candidate(self):
        topics = [make_topic("a", None, None), make_topic("b", 1, 5)]
        lookup = make_page_topic_lookup(topics)
        assert lookup(3) == "b"

    def test_topic_with_non_int_page_range_never_a_candidate(self):
        topics = [{"id": "a", "page_start": "1", "page_end": "5"}]
        lookup = make_page_topic_lookup(topics)
        assert lookup(3) is None

    def test_topic_without_id_never_a_candidate(self):
        topics = [{"page_start": 1, "page_end": 5}]
        lookup = make_page_topic_lookup(topics)
        assert lookup(3) is None

    def test_empty_topics_list(self):
        lookup = make_page_topic_lookup([])
        assert lookup(3) is None


# --------------------------------------------------------------------------
# link_object_to_topic
# --------------------------------------------------------------------------

class TestLinkObjectToTopic:
    def test_links_resolvable_object(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        obj = make_obj(page=3)
        result = link_object_to_topic(obj, topic_lookup=lookup)
        assert result == "t1"
        assert obj["topic_ids"] == ["t1"]

    def test_never_overwrites_existing_topic_ids(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        obj = make_obj(page=8, topic_ids=["already-linked"])
        result = link_object_to_topic(obj, topic_lookup=lookup)
        assert result == "already-linked"
        assert obj["topic_ids"] == ["already-linked"]

    def test_unresolvable_page_leaves_topic_ids_untouched(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        obj = make_obj(page=None)
        result = link_object_to_topic(obj, topic_lookup=lookup)
        assert result is None
        assert "topic_ids" not in obj

    def test_page_outside_any_topic_range_leaves_topic_ids_empty(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        obj = make_obj(page=99, topic_ids=[])
        result = link_object_to_topic(obj, topic_lookup=lookup)
        assert result is None
        assert obj["topic_ids"] == []

    def test_never_writes_concept_ids(self):
        lookup = make_page_topic_lookup(TWO_TOPICS)
        obj = make_obj(page=3)
        link_object_to_topic(obj, topic_lookup=lookup)
        assert "concept_ids" not in obj


# --------------------------------------------------------------------------
# link_objects_to_topics — the reusable primitive
# --------------------------------------------------------------------------

class TestLinkObjectsToTopics:
    @pytest.mark.parametrize("object_type", UNIVERSAL_LINKING_OBJECT_TYPES)
    def test_reusable_across_every_supported_type(self, object_type):
        """Same function, same behavior, for every one of the nine
        supported object types -- no per-type branching."""
        topics = [make_topic("t1", 1, 5, **{TOPIC_REVERSE_FIELDS[object_type]: []})]
        topics_by_id = {"t1": topics[0]}
        obj = make_obj(id_="obj-1", page=3)

        stats = link_objects_to_topics(
            [obj], object_type=object_type,
            topic_lookup=make_page_topic_lookup(topics),
            topics_by_id=topics_by_id,
        )

        assert obj["topic_ids"] == ["t1"]
        assert stats == {"object_type": object_type, "total": 1, "linked": 1, "unlinked": 0}
        reverse_field = TOPIC_REVERSE_FIELDS[object_type]
        assert topics_by_id["t1"][reverse_field] == ["obj-1"]

    def test_glossary_entry_has_no_reverse_field_but_still_links(self):
        topics = [make_topic("t1", 1, 5)]
        topics_by_id = {"t1": topics[0]}
        obj = make_obj(id_="g1", page=3)

        stats = link_objects_to_topics(
            [obj], object_type="glossary_entry",
            topic_lookup=make_page_topic_lookup(topics),
            topics_by_id=topics_by_id,
        )
        assert obj["topic_ids"] == ["t1"]
        assert stats["linked"] == 1
        # No reverse field defined for glossary_entry -> topic dict
        # unchanged aside from what it already had.
        assert topics_by_id["t1"] == {"id": "t1", "page_start": 1, "page_end": 5}

    def test_unresolvable_objects_counted_as_unlinked(self):
        topics = [make_topic("t1", 1, 5)]
        objs = [make_obj(id_="a", page=None), make_obj(id_="b", page=99)]
        stats = link_objects_to_topics(
            objs, object_type="example",
            topic_lookup=make_page_topic_lookup(topics),
        )
        assert stats == {"object_type": "example", "total": 2, "linked": 0, "unlinked": 2}
        assert "topic_ids" not in objs[0]
        assert objs[1].get("topic_ids", []) == []

    def test_skips_non_dict_and_idless_entries(self):
        topics = [make_topic("t1", 1, 5)]
        objs = [None, "not-a-dict", {"page": 3}, make_obj(id_="ok", page=3)]
        stats = link_objects_to_topics(
            objs, object_type="figure",
            topic_lookup=make_page_topic_lookup(topics),
        )
        assert stats["total"] == 1
        assert stats["linked"] == 1

    def test_no_topics_by_id_still_links_object_topic_ids(self):
        topics = [make_topic("t1", 1, 5)]
        obj = make_obj(id_="a", page=3)
        stats = link_objects_to_topics(
            [obj], object_type="table",
            topic_lookup=make_page_topic_lookup(topics),
            topics_by_id=None,
        )
        assert obj["topic_ids"] == ["t1"]
        assert stats["linked"] == 1

    def test_idempotent_no_duplicate_reverse_entries(self):
        topics = [make_topic("t1", 1, 5, examples=[])]
        topics_by_id = {"t1": topics[0]}
        obj = make_obj(id_="ex-1", page=3)
        lookup = make_page_topic_lookup(topics)

        link_objects_to_topics([obj], object_type="example", topic_lookup=lookup,
                                topics_by_id=topics_by_id)
        link_objects_to_topics([obj], object_type="example", topic_lookup=lookup,
                                topics_by_id=topics_by_id)

        assert topics_by_id["t1"]["examples"] == ["ex-1"]

    def test_never_writes_concept_ids_on_any_type(self):
        topics = [make_topic("t1", 1, 5)]
        obj = make_obj(id_="a", page=3)
        link_objects_to_topics([obj], object_type="warning",
                                topic_lookup=make_page_topic_lookup(topics))
        assert "concept_ids" not in obj

    def test_multiple_objects_same_topic_all_appended(self):
        topics = [make_topic("t1", 1, 5, boxes=[])]
        topics_by_id = {"t1": topics[0]}
        objs = [make_obj(id_="b1", page=2), make_obj(id_="b2", page=4)]
        link_objects_to_topics(objs, object_type="box",
                                topic_lookup=make_page_topic_lookup(topics),
                                topics_by_id=topics_by_id)
        assert topics_by_id["t1"]["boxes"] == ["b1", "b2"]


# --------------------------------------------------------------------------
# resolve_deterministic_concept_ids — opt-in helper, unused by default
# --------------------------------------------------------------------------

class TestResolveDeterministicConceptIds:
    def test_none_name_field_never_inspects_object_returns_empty(self):
        obj = {"term": "Photosynthesis"}
        result = resolve_deterministic_concept_ids(
            obj, name_field=None, concept_name_to_id={"photosynthesis": "c1"})
        assert result == []

    def test_exact_case_insensitive_match(self):
        obj = {"term": "Photosynthesis"}
        result = resolve_deterministic_concept_ids(
            obj, name_field="term", concept_name_to_id={"photosynthesis": "c1"})
        assert result == ["c1"]

    def test_no_match_returns_empty(self):
        obj = {"term": "Osmosis"}
        result = resolve_deterministic_concept_ids(
            obj, name_field="term", concept_name_to_id={"photosynthesis": "c1"})
        assert result == []

    def test_missing_name_field_returns_empty(self):
        obj = {}
        result = resolve_deterministic_concept_ids(
            obj, name_field="term", concept_name_to_id={"photosynthesis": "c1"})
        assert result == []

    def test_blank_name_returns_empty(self):
        obj = {"term": "   "}
        result = resolve_deterministic_concept_ids(
            obj, name_field="term", concept_name_to_id={"photosynthesis": "c1"})
        assert result == []

    def test_never_mutates_object(self):
        obj = {"term": "Photosynthesis"}
        before = copy.deepcopy(obj)
        resolve_deterministic_concept_ids(
            obj, name_field="term", concept_name_to_id={"photosynthesis": "c1"})
        assert obj == before


# --------------------------------------------------------------------------
# link_universal_objects — the pipeline.py integration point
# --------------------------------------------------------------------------

class TestLinkUniversalObjects:
    def _topics(self):
        return [
            {
                "id": "t1", "page_start": 1, "page_end": 5,
                "examples": [], "activities": [], "figures": [], "tables": [],
                "equations": [], "diagrams": [], "boxes": [], "notes": [], "warnings": [],
                "definitions": ["already-here"],
            },
            {
                "id": "t2", "page_start": 6, "page_end": 10,
                "examples": [], "activities": [], "figures": [], "tables": [],
                "equations": [], "diagrams": [], "boxes": [], "notes": [], "warnings": [],
                "definitions": [],
            },
        ]

    def test_links_every_supported_type_end_to_end(self):
        topics = self._topics()
        examples = [make_obj(id_="ex1", page=2)]
        tables = [make_obj(id_="tb1", page=8)]
        figures = [make_obj(id_="fg1", page=3)]
        diagrams = [make_obj(id_="dg1", page=7)]
        equations = [make_obj(id_="eq1", page=1)]
        notes = [make_obj(id_="nt1", page=9)]
        boxes = [make_obj(id_="bx1", page=4)]
        activities = [make_obj(id_="ac1", page=6)]
        warnings = [make_obj(id_="wn1", page=10)]

        stats = link_universal_objects(
            topics=topics, examples=examples, tables=tables, figures=figures,
            diagrams=diagrams, equations=equations, notes=notes, boxes=boxes,
            activities=activities, warnings=warnings,
        )

        assert examples[0]["topic_ids"] == ["t1"]
        assert tables[0]["topic_ids"] == ["t2"]
        assert figures[0]["topic_ids"] == ["t1"]
        assert diagrams[0]["topic_ids"] == ["t2"]
        assert equations[0]["topic_ids"] == ["t1"]
        assert notes[0]["topic_ids"] == ["t2"]
        assert boxes[0]["topic_ids"] == ["t1"]
        assert activities[0]["topic_ids"] == ["t2"]
        assert warnings[0]["topic_ids"] == ["t2"]

        t1, t2 = topics
        assert t1["examples"] == ["ex1"]
        assert t1["figures"] == ["fg1"]
        assert t1["equations"] == ["eq1"]
        assert t1["boxes"] == ["bx1"]
        assert t2["tables"] == ["tb1"]
        assert t2["diagrams"] == ["dg1"]
        assert t2["notes"] == ["nt1"]
        assert t2["activities"] == ["ac1"]
        assert t2["warnings"] == ["wn1"]

        # Pre-existing definitions reverse list is untouched (definitions
        # aren't routed through this entry point at all).
        assert t1["definitions"] == ["already-here"]

        assert stats["total_linked"] == 9
        assert stats["total_unlinked"] == 0
        assert set(stats["types"].keys()) == set(UNIVERSAL_LINKING_OBJECT_TYPES)

    def test_unresolvable_object_is_never_guessed(self):
        topics = self._topics()
        # Page 99 is outside both topics' ranges.
        figures = [make_obj(id_="fg-orphan", page=99)]
        stats = link_universal_objects(topics=topics, figures=figures)
        assert figures[0].get("topic_ids", []) == []
        assert topics[0]["figures"] == []
        assert topics[1]["figures"] == []
        assert stats["types"]["figure"]["unlinked"] == 1
        assert stats["total_linked"] == 0

    def test_object_with_no_page_at_all_is_never_guessed(self):
        topics = self._topics()
        notes = [{"id": "nt-nopage"}]
        link_universal_objects(topics=topics, notes=notes)
        assert notes[0].get("topic_ids", []) == []
        assert topics[0]["notes"] == []
        assert topics[1]["notes"] == []

    def test_omitted_object_types_are_simply_skipped(self):
        topics = self._topics()
        stats = link_universal_objects(topics=topics, examples=[make_obj(page=2)])
        assert "table" not in stats["types"]
        assert "example" in stats["types"]

    def test_no_object_lists_at_all_is_a_no_op(self):
        topics = self._topics()
        before = copy.deepcopy(topics)
        stats = link_universal_objects(topics=topics)
        assert topics == before
        assert stats["types"] == {}
        assert stats["total_linked"] == 0
        assert stats["total_unlinked"] == 0

    def test_idempotent_across_repeated_calls(self):
        topics = self._topics()
        examples = [make_obj(id_="ex1", page=2)]
        link_universal_objects(topics=topics, examples=examples)
        link_universal_objects(topics=topics, examples=examples)
        assert topics[0]["examples"] == ["ex1"]
        assert examples[0]["topic_ids"] == ["t1"]

    def test_already_linked_object_is_not_overwritten_or_duplicated(self):
        topics = self._topics()
        boxes = [make_obj(id_="bx1", page=8, topic_ids=["some-other-topic"])]
        link_universal_objects(topics=topics, boxes=boxes)
        assert boxes[0]["topic_ids"] == ["some-other-topic"]
        # Never added to t2's reverse list either, since it was never
        # actually (re-)resolved against these topics.
        assert topics[1]["boxes"] == []

    def test_multiple_objects_same_type_different_topics(self):
        topics = self._topics()
        activities = [make_obj(id_="a1", page=2), make_obj(id_="a2", page=9)]
        link_universal_objects(topics=topics, activities=activities)
        assert topics[0]["activities"] == ["a1"]
        assert topics[1]["activities"] == ["a2"]

    def test_never_touches_concept_ids_on_any_object(self):
        topics = self._topics()
        equations = [make_obj(id_="eq1", page=2, concept_ids=[])]
        link_universal_objects(topics=topics, equations=equations)
        assert equations[0]["concept_ids"] == []
