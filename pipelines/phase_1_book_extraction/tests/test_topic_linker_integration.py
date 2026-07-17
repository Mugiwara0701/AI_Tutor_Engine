"""
tests/test_topic_linker_integration.py — integration tests for
Milestone 1 (Universal Object Linking).

Unlike tests/test_topic_linker.py (pure unit tests against hand-built
minimal dicts), this module builds fixtures shaped exactly like what
pipeline.py actually produces -- full canonical envelopes (id/urn/
object_type/topic_ids/concept_ids/provenance/...), a realistic
multi-topic `topics_out`-shaped list (with every TopicNode
reverse-reference field pre-seeded to `[]`, matching pipeline.py's own
topics_out.append({...}) literal), and objects spanning pages that fall
inside topics, on topic boundaries, and outside any topic's range --
then runs the whole `link_universal_objects` pass exactly the way
pipeline.py's own Milestone-1 integration point calls it, and asserts
on the end-to-end result across every supported object type at once.

No PyMuPDF/pydantic dependency: these fixtures are plain dicts built to
match the *shape* pipeline.py's canonical.canonical_fields() /
_attach_canonical() produce, not actual pipeline.py execution (pipeline.py
itself needs a real PDF + PyMuPDF + pydantic environment this test suite
does not depend on -- see tests/test_topic_linker.py's own module
docstring convention).
"""
from __future__ import annotations

import copy

from modules.topic_linker import link_universal_objects, UNIVERSAL_LINKING_OBJECT_TYPES


def _canonical_envelope(object_id, object_type, page):
    """Mirrors the shape canonical.canonical_fields() actually produces
    (subset of fields relevant to linking)."""
    return {
        "id": object_id,
        "urn": f"urn:test:{object_type}:{object_id}",
        "object_type": object_type,
        "schema_version": "1.0.0",
        "subject": "Biology",
        "chapter_reference": "test-book:chapter-1",
        "topic_ids": [],
        "concept_ids": [],
        "page": page,
        "provenance": {
            "source_page": page,
            "extraction_stage": "test-fixture",
            "extraction_method": "deterministic",
            "confidence": 0.5,
        },
        "extraction_confidence": 0.5,
        "validation_status": "unvalidated",
    }


def _topics_out_fixture():
    """Three topics with non-overlapping page ranges, and every
    TopicNode reverse-reference field pre-seeded exactly like
    pipeline.py's own topics_out.append({...}) literal (schemas/
    chapter_schema.py::TopicNode's declared list fields)."""
    def topic(id_, title, page_start, page_end, parent=None):
        return {
            "id": id_, "title": title, "numbering": None, "level": 1,
            "parent": parent, "children": [],
            "page_start": page_start, "page_end": page_end,
            "concepts": [], "concept_names": [],
            "definitions": [], "examples": [], "activities": [],
            "figures": [], "tables": [], "equations": [], "diagrams": [],
            "charts": [], "graphs": [], "maps": [], "timelines": [],
            "boxes": [], "notes": [], "warnings": [],
            "semantic_summary": "", "visual_summary": "",
            "detected_entities": [], "prerequisites": [],
            "related_topics": [], "next_topics": [], "confidence": 0.5,
        }

    return [
        topic("t-cells", "Cell Structure", 1, 4),
        topic("t-photo", "Photosynthesis", 5, 9),
        topic("t-resp", "Respiration", 10, 14),
    ]


class TestFullChapterLinking:
    """Simulates one whole chapter's worth of previously-unlinked
    canonical objects, spanning all three topics plus a couple of
    deliberately unresolvable ones, and checks the entire pass end to
    end -- forward topic_ids, reverse TopicNode lists, and that nothing
    outside this milestone's scope (concept_ids, ids/urns, unrelated
    topic fields) was touched."""

    def _build_objects(self):
        return {
            "examples": [
                _canonical_envelope("ex-1", "example", page=2),
                _canonical_envelope("ex-2", "example", page=7),
            ],
            "tables": [_canonical_envelope("tb-1", "table", page=6)],
            "figures": [
                _canonical_envelope("fg-1", "figure", page=1),
                _canonical_envelope("fg-2", "figure", page=14),
            ],
            "diagrams": [_canonical_envelope("dg-1", "diagram", page=9)],
            "equations": [_canonical_envelope("eq-1", "equation", page=12)],
            "notes": [_canonical_envelope("nt-1", "note", page=4)],
            "boxes": [_canonical_envelope("bx-1", "box", page=5)],
            "activities": [_canonical_envelope("ac-1", "activity", page=13)],
            "warnings": [_canonical_envelope("wn-1", "warning", page=10)],
            # Deliberately outside every topic's page range (before
            # page 1 is impossible here, so use a page past the last
            # topic's range instead) -- must stay unlinked.
            "_orphan_figure": _canonical_envelope("fg-orphan", "figure", page=99),
        }

    def test_end_to_end_chapter(self):
        topics = _topics_out_fixture()
        objs = self._build_objects()
        objs["figures"].append(objs.pop("_orphan_figure"))

        before_ids_urns = {
            (o["id"], o["urn"])
            for group in objs.values() for o in group
        }

        stats = link_universal_objects(
            topics=topics,
            examples=objs["examples"], tables=objs["tables"],
            figures=objs["figures"], diagrams=objs["diagrams"],
            equations=objs["equations"], notes=objs["notes"],
            boxes=objs["boxes"], activities=objs["activities"],
            warnings=objs["warnings"],
        )

        by_id = {t["id"]: t for t in topics}

        # Forward links, boundary-page correctness.
        assert objs["examples"][0]["topic_ids"] == ["t-cells"]   # page 2
        assert objs["examples"][1]["topic_ids"] == ["t-photo"]   # page 7
        assert objs["tables"][0]["topic_ids"] == ["t-photo"]     # page 6 (boundary)
        assert objs["figures"][0]["topic_ids"] == ["t-cells"]    # page 1 (boundary)
        assert objs["diagrams"][0]["topic_ids"] == ["t-photo"]   # page 9 (boundary)
        assert objs["equations"][0]["topic_ids"] == ["t-resp"]   # page 12
        assert objs["notes"][0]["topic_ids"] == ["t-cells"]      # page 4 (boundary)
        assert objs["boxes"][0]["topic_ids"] == ["t-photo"]      # page 5 (boundary)
        assert objs["activities"][0]["topic_ids"] == ["t-resp"]  # page 13
        assert objs["warnings"][0]["topic_ids"] == ["t-resp"]    # page 10 (boundary)

        # The orphan (page 99) stays unlinked -- never guessed.
        orphan = [f for f in objs["figures"] if f["id"] == "fg-orphan"][0]
        assert orphan["topic_ids"] == []
        second_figure = [f for f in objs["figures"] if f["id"] == "fg-2"][0]
        assert second_figure["topic_ids"] == ["t-resp"]  # page 14

        # Reverse references, populated onto the correct topic only.
        assert by_id["t-cells"]["examples"] == ["ex-1"]
        assert by_id["t-photo"]["examples"] == ["ex-2"]
        assert by_id["t-photo"]["tables"] == ["tb-1"]
        assert by_id["t-cells"]["figures"] == ["fg-1"]
        assert by_id["t-resp"]["figures"] == ["fg-2"]
        assert by_id["t-photo"]["diagrams"] == ["dg-1"]
        assert by_id["t-resp"]["equations"] == ["eq-1"]
        assert by_id["t-cells"]["notes"] == ["nt-1"]
        assert by_id["t-photo"]["boxes"] == ["bx-1"]
        assert by_id["t-resp"]["activities"] == ["ac-1"]
        assert by_id["t-resp"]["warnings"] == ["wn-1"]
        # Orphan never appears in any topic's reverse list.
        assert "fg-orphan" not in by_id["t-cells"]["figures"]
        assert "fg-orphan" not in by_id["t-photo"]["figures"]
        assert "fg-orphan" not in by_id["t-resp"]["figures"]

        # concept_ids untouched everywhere.
        for group in objs.values():
            for o in group:
                assert o["concept_ids"] == []

        # ids/urns never mutated.
        after_ids_urns = {
            (o["id"], o["urn"])
            for group in objs.values() for o in group
        }
        assert before_ids_urns == after_ids_urns

        assert stats["total_linked"] == 11  # every object except the orphan
        assert stats["total_unlinked"] == 1
        assert set(stats["types"].keys()) == set(UNIVERSAL_LINKING_OBJECT_TYPES)

    def test_re_running_over_already_linked_chapter_is_a_no_op(self):
        """Running the pass twice (e.g. a re-compile) must not change
        anything the second time -- no duplicate reverse-reference
        entries, no re-resolution."""
        topics = _topics_out_fixture()
        objs = self._build_objects()
        objs["figures"].append(objs.pop("_orphan_figure"))

        kwargs = dict(
            topics=topics,
            examples=objs["examples"], tables=objs["tables"],
            figures=objs["figures"], diagrams=objs["diagrams"],
            equations=objs["equations"], notes=objs["notes"],
            boxes=objs["boxes"], activities=objs["activities"],
            warnings=objs["warnings"],
        )
        link_universal_objects(**kwargs)
        after_first = copy.deepcopy(topics)
        link_universal_objects(**kwargs)

        assert topics == after_first

    def test_topics_with_no_objects_get_empty_reverse_lists(self):
        topics = _topics_out_fixture()
        link_universal_objects(topics=topics, examples=[_canonical_envelope("ex-1", "example", page=2)])
        by_id = {t["id"]: t for t in topics}
        assert by_id["t-photo"]["examples"] == []
        assert by_id["t-resp"]["examples"] == []
        # Untouched TopicNode fields stay exactly as seeded.
        assert by_id["t-cells"]["concepts"] == []
        assert by_id["t-cells"]["semantic_summary"] == ""
