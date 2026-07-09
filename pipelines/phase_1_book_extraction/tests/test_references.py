"""
tests/test_references.py — unit tests for Phase B2's compiler.references
module (Deterministic Cross-Reference Resolution).

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import enrich_registries
from compiler.normalization import normalize_registries
from compiler.references import (
    REFERENCE_RESOLUTION_VERSION,
    REFERENCE_FIELDS,
    resolve_registries,
    resolve_topic_concept_ids,
    verify_topic_references,
    resolve_references,
    _build_concept_lookup,
)


# --------------------------------------------------------------------------
# Helpers -- minimal stand-ins for the canonical envelope, matching the
# style already used in tests/test_normalization.py /
# tests/test_registry_enrichment.py.
# --------------------------------------------------------------------------

def make_concept(id_="c1", name="Photosynthesis", aliases=None, **extra):
    d = {
        "id": id_, "urn": f"urn:concept:{id_}", "object_type": "concept",
        "name": name, "aliases": aliases if aliases is not None else [],
    }
    d.update(extra)
    return d


def make_definition(id_="d1", term="Inflation", **extra):
    d = {
        "id": id_, "urn": f"urn:definition:{id_}", "object_type": "definition",
        "term": term,
    }
    d.update(extra)
    return d


def make_glossary(id_="g1", term="Inflation", **extra):
    d = {
        "id": id_, "urn": f"urn:glossary:{id_}", "object_type": "glossary_entry",
        "term": term,
    }
    d.update(extra)
    return d


def make_figure(id_="f1", title="Fig 1", caption="", **extra):
    d = {
        "id": id_, "urn": f"urn:figure:{id_}", "object_type": "figure",
        "title": title, "caption": caption,
    }
    d.update(extra)
    return d


def make_diagram(id_="dg1", title="Diagram 1", **extra):
    d = {
        "id": id_, "urn": f"urn:diagram:{id_}", "object_type": "diagram",
        "title": title,
    }
    d.update(extra)
    return d


def make_table(id_="tb1", title="Table 1", **extra):
    d = {
        "id": id_, "urn": f"urn:table:{id_}", "object_type": "table",
        "title": title,
    }
    d.update(extra)
    return d


def make_equation(id_="e1", latex="a^2", **extra):
    d = {
        "id": id_, "urn": f"urn:equation:{id_}", "object_type": "equation",
        "latex": latex,
    }
    d.update(extra)
    return d


def make_example(id_="ex1", title="Example 1", **extra):
    d = {
        "id": id_, "urn": f"urn:example:{id_}", "object_type": "example",
        "title": title,
    }
    d.update(extra)
    return d


def make_activity(id_="a1", title="Activity 1", **extra):
    d = {
        "id": id_, "urn": f"urn:activity:{id_}", "object_type": "activity",
        "title": title,
    }
    d.update(extra)
    return d


def make_box(id_="bx1", title="Box 1", **extra):
    d = {
        "id": id_, "urn": f"urn:box:{id_}", "object_type": "box",
        "title": title,
    }
    d.update(extra)
    return d


def make_warning(id_="w1", **extra):
    d = {
        "id": id_, "urn": f"urn:warning:{id_}", "object_type": "warning",
    }
    d.update(extra)
    return d


def make_note(id_="n1", **extra):
    d = {
        "id": id_, "urn": f"urn:note:{id_}", "object_type": "note",
    }
    d.update(extra)
    return d


def build_manager(**populate_kwargs):
    """create_registry_manager() -> populate_registries() ->
    enrich_registries() -> normalize_registries(), the exact pipeline.py
    order this module's resolve_registries() expects to run after."""
    manager = create_registry_manager()
    populate_registries(manager, **populate_kwargs)
    enrich_registries(manager)
    normalize_registries(manager)
    return manager


# --------------------------------------------------------------------------
# Definition -> Concept resolution
# --------------------------------------------------------------------------

class TestDefinitionResolution:
    def test_exact_term_match_resolves(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "Photosynthesis")],
        )
        resolve_registries(manager)
        definition = manager.get("definitions").get_by_id("d1")
        assert definition["concept_id"] == "c1"
        assert definition["reference_resolution"]["status"] == "resolved"

    def test_case_insensitive_match_resolves(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "PHOTOSYNTHESIS")],
        )
        resolve_registries(manager)
        assert manager.get("definitions").get_by_id("d1")["concept_id"] == "c1"

    def test_whitespace_and_punctuation_normalized_match_resolves(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Newton's Third Law")],
            definitions=[make_definition("d1", "  newton\u2019s   third law  ")],
        )
        resolve_registries(manager)
        assert manager.get("definitions").get_by_id("d1")["concept_id"] == "c1"

    def test_no_matching_concept_stays_unresolved(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "Something Else Entirely")],
        )
        resolve_registries(manager)
        definition = manager.get("definitions").get_by_id("d1")
        assert definition["concept_id"] is None
        assert definition["reference_resolution"]["status"] == "unresolved"

    def test_empty_concept_registry_leaves_every_definition_unresolved(self):
        manager = build_manager(
            definitions=[make_definition("d1", "Inflation"), make_definition("d2", "Deflation")],
        )
        resolve_registries(manager)
        for definition in manager.get("definitions").values():
            assert definition["concept_id"] is None

    def test_multiple_definitions_same_term_all_resolve_to_same_concept(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[
                make_definition("d1", "Inflation", page=1),
                make_definition("d2", "Inflation", page=7),
            ],
        )
        resolve_registries(manager)
        defs = manager.get("definitions")
        assert defs.get_by_id("d1")["concept_id"] == "c1"
        assert defs.get_by_id("d2")["concept_id"] == "c1"


# --------------------------------------------------------------------------
# Glossary -> Concept resolution
# --------------------------------------------------------------------------

class TestGlossaryResolution:
    def test_exact_term_match_resolves(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            glossary=[make_glossary("g1", "Inflation")],
        )
        resolve_registries(manager)
        assert manager.get("glossary").get_by_id("g1")["concept_id"] == "c1"

    def test_alias_match_resolves(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis", aliases=["Photosynthetic process"])],
            glossary=[make_glossary("g1", "Photosynthetic process")],
        )
        resolve_registries(manager)
        assert manager.get("glossary").get_by_id("g1")["concept_id"] == "c1"

    def test_unmatched_term_stays_unresolved(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            glossary=[make_glossary("g1", "Deflation")],
        )
        resolve_registries(manager)
        entry = manager.get("glossary").get_by_id("g1")
        assert entry["concept_id"] is None
        assert entry["reference_resolution"]["status"] == "unresolved"


# --------------------------------------------------------------------------
# Equation / Figure / Diagram / Table / Example / Activity / Box / Warning /
# Note -> Concept resolution: no deterministic source field exists today
# (see compiler/references.py's module docstring) -- every item in these
# nine registries must always resolve to concept_ids == [] rather than
# guessing from title/caption text.
# --------------------------------------------------------------------------

class TestNoDeterministicSourceRegistriesStayEmpty:
    def test_equation_concept_ids_always_empty(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Ohm's Law")],
            equations=[make_equation("e1", latex="V = IR")],
        )
        resolve_registries(manager)
        equation = manager.get("equations").get_by_id("e1")
        assert equation["concept_ids"] == []

    def test_figure_title_matching_concept_name_does_not_resolve(self):
        """A Figure whose own `title` happens to equal a Concept's name
        must NOT resolve -- title/caption matching was already reviewed
        and rejected as a non-deterministic heuristic by pipeline.py's
        own Fix 3 review (see compiler/references.py's module
        docstring); this module must not reintroduce it."""
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            figures=[make_figure("f1", title="Photosynthesis")],
        )
        resolve_registries(manager)
        figure = manager.get("figures").get_by_id("f1")
        assert figure["concept_ids"] == []
        assert "concept_id" not in figure or figure.get("concept_id") is None

    def test_diagram_table_activity_example_box_warning_note_all_empty(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            diagrams=[make_diagram("dg1", title="Photosynthesis")],
            tables=[make_table("tb1", title="Photosynthesis")],
            activities=[make_activity("a1", title="Photosynthesis")],
            examples=[make_example("ex1", title="Photosynthesis")],
            boxes=[make_box("bx1", title="Photosynthesis")],
            warnings=[make_warning("w1")],
            notes=[make_note("n1")],
        )
        resolve_registries(manager)
        for registry_name in ("diagrams", "tables", "activities", "examples", "boxes", "warnings", "notes"):
            for item in manager.get(registry_name).values():
                assert item["concept_ids"] == [], registry_name


# --------------------------------------------------------------------------
# Unresolved references / duplicate (ambiguous) candidates
# --------------------------------------------------------------------------

class TestUnresolvedAndAmbiguous:
    def test_ambiguous_normalized_key_across_two_concepts_leaves_both_unresolved(self):
        """Two different concepts that normalize to the same lookup key
        (here: one concept's alias collides with another concept's own
        name) must never be guessed between -- every candidate matching
        that key resolves to unresolved."""
        manager = build_manager(
            concepts=[
                make_concept("c1", "Bank", aliases=["Financial Institution"]),
                make_concept("c2", "Financial Institution"),
            ],
            definitions=[make_definition("d1", "Financial Institution")],
        )
        resolve_registries(manager)
        definition = manager.get("definitions").get_by_id("d1")
        assert definition["concept_id"] is None
        assert definition["reference_resolution"]["status"] == "unresolved"

    def test_ambiguous_key_removed_from_lookup_index(self):
        manager = build_manager(
            concepts=[
                make_concept("c1", "Bank", aliases=["Financial Institution"]),
                make_concept("c2", "Financial Institution"),
            ],
        )
        lookup = _build_concept_lookup(manager.get("concepts"))
        assert "financial institution" not in lookup

    def test_definition_with_no_term_like_field_has_no_lookup_key(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[{"id": "d1", "urn": "urn:definition:d1", "object_type": "definition", "term": ""}],
        )
        resolve_registries(manager)
        assert manager.get("definitions").get_by_id("d1")["concept_id"] is None


# --------------------------------------------------------------------------
# Deterministic resolution: repeatable, order-independent of dict
# construction, and idempotent across repeated resolve_registries() calls.
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_resolution_is_repeatable_across_independent_managers(self):
        def build():
            return build_manager(
                concepts=[make_concept("c1", "Photosynthesis"), make_concept("c2", "Inflation")],
                definitions=[make_definition("d1", "Photosynthesis"), make_definition("d2", "Inflation")],
                glossary=[make_glossary("g1", "Inflation")],
            )

        manager_a = build()
        manager_b = build()
        resolve_registries(manager_a)
        resolve_registries(manager_b)

        for registry_name in ("definitions", "glossary", "concepts"):
            items_a = {item["id"]: item for item in manager_a.get(registry_name).values()}
            items_b = {item["id"]: item for item in manager_b.get(registry_name).values()}
            assert items_a.keys() == items_b.keys()
            for item_id in items_a:
                for field in REFERENCE_FIELDS:
                    if field == "reference_resolution":
                        continue  # timestamp differs run to run, by design
                    assert items_a[item_id].get(field) == items_b[item_id].get(field), (registry_name, item_id, field)

    def test_calling_resolve_registries_twice_is_idempotent(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "Photosynthesis")],
        )
        resolve_registries(manager)
        first = copy.deepcopy(manager.get("definitions").get_by_id("d1"))
        resolve_registries(manager)
        second = manager.get("definitions").get_by_id("d1")
        assert first["concept_id"] == second["concept_id"]
        assert first["reference_resolution"]["status"] == second["reference_resolution"]["status"]


# --------------------------------------------------------------------------
# Reverse aggregation onto Concept records
# --------------------------------------------------------------------------

class TestReverseAggregation:
    def test_concept_gains_definition_and_glossary_ids(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
            glossary=[make_glossary("g1", "Inflation")],
        )
        resolve_registries(manager)
        concept = manager.get("concepts").get_by_id("c1")
        assert concept["definition_ids"] == ["d1"]
        assert concept["glossary_ids"] == ["g1"]

    def test_concept_with_no_links_has_empty_lists_not_missing_keys(self):
        manager = build_manager(concepts=[make_concept("c1", "Unlinked Concept")])
        resolve_registries(manager)
        concept = manager.get("concepts").get_by_id("c1")
        for field in ("definition_ids", "glossary_ids", "equation_ids", "figure_ids",
                      "diagram_ids", "table_ids", "activity_ids", "example_ids",
                      "warning_ids", "note_ids", "box_ids"):
            assert concept[field] == []

    def test_multiple_definitions_aggregate_under_one_concept(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation"), make_definition("d2", "Inflation")],
        )
        resolve_registries(manager)
        concept = manager.get("concepts").get_by_id("c1")
        assert set(concept["definition_ids"]) == {"d1", "d2"}


# --------------------------------------------------------------------------
# Topic -> Concept resolution (read-only; see module docstring)
# --------------------------------------------------------------------------

class TestTopicResolution:
    def test_resolve_topic_concept_ids_matches_by_name(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis"), make_concept("c2", "Inflation")],
        )
        lookup = _build_concept_lookup(manager.get("concepts"))
        topic = {"id": "t1", "concept_names": ["Photosynthesis", "Inflation"]}
        resolved = resolve_topic_concept_ids(topic, lookup)
        assert resolved == ["c1", "c2"]

    def test_resolve_topic_concept_ids_skips_unmatched_names(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        lookup = _build_concept_lookup(manager.get("concepts"))
        topic = {"id": "t1", "concept_names": ["Photosynthesis", "Not A Real Concept"]}
        assert resolve_topic_concept_ids(topic, lookup) == ["c1"]

    def test_resolve_topic_concept_ids_deduplicates(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        lookup = _build_concept_lookup(manager.get("concepts"))
        topic = {"id": "t1", "concept_names": ["Photosynthesis", "photosynthesis"]}
        assert resolve_topic_concept_ids(topic, lookup) == ["c1"]

    def test_resolve_topic_concept_ids_never_mutates_topic(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        lookup = _build_concept_lookup(manager.get("concepts"))
        topic = {"id": "t1", "concept_names": ["Photosynthesis"]}
        before = copy.deepcopy(topic)
        resolve_topic_concept_ids(topic, lookup)
        assert topic == before

    def test_verify_topic_references_reports_agreement(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        topics = [{"id": "t1", "concept_names": ["Photosynthesis"], "concepts": ["c1"]}]
        report = verify_topic_references(topics, manager)
        assert report["topics_checked"] == 1
        assert report["topics_agree"] == 1
        assert report["topics"][0]["resolved_concept_ids"] == ["c1"]

    def test_verify_topic_references_reports_disagreement_without_raising(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        topics = [{"id": "t1", "concept_names": ["Photosynthesis"], "concepts": []}]
        report = verify_topic_references(topics, manager)
        assert report["topics_agree"] == 0
        assert report["topics"][0]["agrees"] is False

    def test_verify_topic_references_never_mutates_topics(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        topics = [{"id": "t1", "concept_names": ["Photosynthesis"], "concepts": ["c1"]}]
        before = copy.deepcopy(topics)
        verify_topic_references(topics, manager)
        assert topics == before


# --------------------------------------------------------------------------
# Pipeline integration (resolve_references top-level entry point)
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_resolve_references_runs_registry_resolution_and_topic_verification(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "Photosynthesis")],
        )
        topics = [{"id": "t1", "concept_names": ["Photosynthesis"], "concepts": ["c1"]}]
        stats = resolve_references(manager, topics=topics)
        assert stats["registries"]["definitions"]["resolved"] == 1
        assert "topics" in stats
        assert stats["topics"]["topics_agree"] == 1

    def test_resolve_references_without_topics_skips_topic_stats(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        stats = resolve_references(manager)
        assert "topics" not in stats

    def test_resolve_references_is_the_only_thing_needed_after_normalize(self):
        """Mirrors pipeline.py's actual integration order: create -> populate
        -> enrich -> normalize -> resolve. No extra setup should be
        required for a correct end-to-end resolution."""
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "Photosynthesis")],
            glossary=[make_glossary("g1", "Photosynthesis")],
        )
        enrich_registries(manager)
        normalize_registries(manager)
        resolve_references(manager)
        assert manager.get("definitions").get_by_id("d1")["concept_id"] == "c1"
        assert manager.get("glossary").get_by_id("g1")["concept_id"] == "c1"
        assert manager.get("concepts").get_by_id("c1")["definition_ids"] == ["d1"]


# --------------------------------------------------------------------------
# Backward compatibility: additive-only, no existing key/value is changed.
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_ids_urns_and_fields_are_never_changed(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis", importance="high")],
            definitions=[make_definition("d1", "Photosynthesis", page=4)],
        )
        before_concept = copy.deepcopy(manager.get("concepts").get_by_id("c1"))
        before_definition = copy.deepcopy(manager.get("definitions").get_by_id("d1"))
        resolve_registries(manager)
        after_concept = manager.get("concepts").get_by_id("c1")
        after_definition = manager.get("definitions").get_by_id("d1")

        for key, value in before_concept.items():
            assert after_concept[key] == value
        for key, value in before_definition.items():
            assert after_definition[key] == value

        # New keys are additive only.
        assert set(after_concept.keys()) - set(before_concept.keys()) <= set(REFERENCE_FIELDS)
        assert set(after_definition.keys()) - set(before_definition.keys()) <= set(REFERENCE_FIELDS)

    def test_registry_ids_and_urns_never_change_after_resolution(self):
        manager = build_manager(
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "Photosynthesis")],
        )
        before_ids = manager.get("definitions").ids()
        before_urn = manager.get("definitions").get_by_id("d1")["urn"]
        resolve_registries(manager)
        assert manager.get("definitions").ids() == before_ids
        assert manager.get("definitions").get_by_id("d1")["urn"] == before_urn

    def test_resolve_registries_returns_manager_unaffected_in_type(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        stats = resolve_registries(manager)
        assert isinstance(stats, dict)
        # resolve_registries mutates in place and returns statistics, not
        # the manager itself -- callers keep using their own reference.
        assert "registries" in stats


# --------------------------------------------------------------------------
# Registry-manager level: every non-concept registry gets a concept_ids
# stamp, `concepts` itself is never given a concept_ids field.
# --------------------------------------------------------------------------

class TestRegistryManagerLevel:
    def test_concepts_registry_itself_has_no_concept_ids_field(self):
        manager = build_manager(concepts=[make_concept("c1", "Photosynthesis")])
        resolve_registries(manager)
        concept = manager.get("concepts").get_by_id("c1")
        assert "concept_ids" not in concept

    def test_every_registered_registry_is_covered(self):
        manager = build_manager(
            concepts=[make_concept("c1", "X")],
            definitions=[make_definition("d1", "X")],
            glossary=[make_glossary("g1", "X")],
            figures=[make_figure("f1")],
            diagrams=[make_diagram("dg1")],
            tables=[make_table("tb1")],
            equations=[make_equation("e1")],
            activities=[make_activity("a1")],
            boxes=[make_box("bx1")],
            warnings=[make_warning("w1")],
            notes=[make_note("n1")],
            examples=[make_example("ex1")],
        )
        stats = resolve_registries(manager)
        assert set(stats["registries"].keys()) == set(manager.names())

    def test_empty_manager_resolves_without_error(self):
        manager = create_registry_manager()
        stats = resolve_registries(manager)
        assert stats["registries"]["concepts"]["total"] == 0


# --------------------------------------------------------------------------
# Module-level constants
# --------------------------------------------------------------------------

class TestModuleConstants:
    def test_reference_resolution_version_is_a_string(self):
        assert isinstance(REFERENCE_RESOLUTION_VERSION, str)

    def test_reference_fields_contains_expected_names(self):
        for field in ("concept_id", "concept_ids", "definition_ids", "glossary_ids",
                      "reference_resolution"):
            assert field in REFERENCE_FIELDS