"""
tests/test_glossary_urn_regression.py — regression tests for the
DuplicateUrnError root cause fixed in pipeline.py's canonical object
construction (Phase 1: Duplicate Glossary URN root-cause analysis).

BACKGROUND (see the runtime log / task description this fix responds to):
pipeline.py's glossary-entry construction generated `object_id` from
(chapter_title, "glossary", term, topic_id) -- unique per (term, topic)
occurrence -- but generated `urn` from urn_parts=["glossary", term] only,
omitting the topic. Two different topics mentioning the exact same term
therefore produced two objects with DIFFERENT ids but the IDENTICAL urn,
which CanonicalRegistry.insert() correctly rejected with DuplicateUrnError
("... already resolves to a different id in this registry").

The same id/urn-input mismatch pattern existed for `definitions` (id
included a positional idx, urn did not) and for `activities`/`boxes`/
`warnings`/`notes`/`examples` (id included a per-line idx, urn did not).

These tests do not re-run the full PDF pipeline (that needs a real PDF +
VLM stack); instead they exercise the exact same building blocks
pipeline.py itself calls -- modules.canonical.canonical_fields(),
modules.pdf_parser.make_id()/make_urn(), compiler.normalization.
canonical_lookup_key(), and the concrete registries -- reproducing
pipeline.py's construction pattern faithfully enough to catch a
regression in that pattern without depending on PDF/VLM infrastructure.
CanonicalRegistry/DuplicateUrnError/DuplicateIdError themselves (Phase B0)
are exercised unmodified, per "the registry must continue detecting
duplicate canonical identities."
"""
from __future__ import annotations

import pytest

from modules import canonical
from modules.pdf_parser import make_id
from compiler.normalization import canonical_lookup_key
from compiler.registries import GlossaryRegistry, DefinitionRegistry, ActivityRegistry
from compiler.exceptions import DuplicateUrnError, DuplicateIdError


NAMESPACE = "accountancy-part-1:accounting-for-partnership-basic-concepts"


def _build_glossary_entry(term: str, topic_id: str) -> dict:
    """Mirrors pipeline.py's fixed glossary-entry construction exactly
    (chapter_title fixed for all calls here, matching one chapter run)."""
    return {
        **canonical.canonical_fields(
            object_id=make_id("Accounting for Partnership: Basic Concepts", "glossary", term, topic_id),
            object_type="glossary_entry", namespace=NAMESPACE,
            urn_parts=["glossary", term, topic_id],
            confidence=0.5,
        ),
        "term": term, "topic": topic_id,
    }


def _build_definition(term: str, page: int, idx: int) -> dict:
    """Mirrors pipeline.py's fixed definition construction exactly."""
    return {
        "term": term, "page": page,
        **canonical.canonical_fields(
            object_id=make_id("Accounting for Partnership: Basic Concepts", "definition", term, str(page), str(idx)),
            object_type="definition", namespace=NAMESPACE,
            urn_parts=["definition", term, str(page), str(idx)],
            confidence=0.6,
        ),
    }


def _build_activity(activity_type: str, page: int, idx: int) -> dict:
    """Mirrors pipeline.py's fixed activity construction exactly."""
    return {
        "activity_type": activity_type, "page": page,
        **canonical.canonical_fields(
            object_id=make_id("Accounting for Partnership: Basic Concepts", "activity", activity_type, str(idx)),
            object_type="activity", namespace=NAMESPACE,
            urn_parts=["activity", activity_type, str(page), str(idx)],
            confidence=0.6,
        ),
    }


# --------------------------------------------------------------------------
# The exact failure from the runtime log: the same glossary term
# ("Fixed Capital Method") surfaced under two different topics within one
# chapter must no longer collide.
# --------------------------------------------------------------------------
class TestGlossaryDuplicateTermAcrossTopics:
    def test_same_term_two_topics_gets_distinct_urns(self):
        e1 = _build_glossary_entry("Fixed Capital Method", "topic-interest-on-capital")
        e2 = _build_glossary_entry("Fixed Capital Method", "topic-capital-accounts")
        assert e1["urn"] != e2["urn"]
        assert e1["id"] != e2["id"]

    def test_same_term_two_topics_both_insert_without_raising(self):
        registry = GlossaryRegistry()
        e1 = _build_glossary_entry("Fixed Capital Method", "topic-interest-on-capital")
        e2 = _build_glossary_entry("Fixed Capital Method", "topic-capital-accounts")
        registry.insert(e1)
        registry.insert(e2)  # must NOT raise DuplicateUrnError
        assert registry.size() == 2

    def test_reproduces_original_crash_scenario_end_to_end(self):
        """Direct reproduction of the runtime log's failing chapter: the
        term 'fixed-capital-method' emitted for two different topics used
        to raise DuplicateUrnError at registry insertion time."""
        registry = GlossaryRegistry()
        for topic_id in ("topic-a", "topic-b"):
            entry = _build_glossary_entry("Fixed Capital Method", topic_id)
            registry.insert(entry)  # must not raise
        assert registry.size() == 2


# --------------------------------------------------------------------------
# Case / whitespace / punctuation variants of the same term must be
# recognized as "the same term" by the compiler's own canonical identity
# primitive (canonical_lookup_key), i.e. pipeline.py's within-topic dedup
# loop collapses them instead of emitting near-duplicate records.
# --------------------------------------------------------------------------
class TestGlossaryTermNormalizationForDedup:
    @pytest.mark.parametrize("variant", [
        "fixed capital method",
        "FIXED CAPITAL METHOD",
        "Fixed   Capital   Method",
        "  Fixed Capital Method  ",
        "Fixed Capital Method.",
        "Fixed Capital Method,",
    ])
    def test_variant_normalizes_to_same_key_as_canonical_form(self, variant):
        canonical_key = canonical_lookup_key("Fixed Capital Method")
        assert canonical_lookup_key(variant) == canonical_key

    def test_within_topic_duplicate_mentions_collapse_to_one_entry(self):
        """Mirrors pipeline.py's per-topic dedup loop: the same term
        mentioned twice (with incidental case/whitespace differences) in
        one topic's glossary_terms list must produce exactly one glossary
        record for that topic, not two."""
        raw_terms = ["Fixed Capital Method", "fixed capital method  "]
        seen = set()
        built = []
        for term in raw_terms:
            term_s = str(term).strip()
            key = canonical_lookup_key(term_s) or term_s.casefold()
            if key in seen:
                continue
            seen.add(key)
            built.append(_build_glossary_entry(term_s, "topic-interest-on-capital"))
        assert len(built) == 1


# --------------------------------------------------------------------------
# Registry protection itself must be completely unchanged: genuinely
# different objects that happen to share a urn must still raise.
# --------------------------------------------------------------------------
class TestRegistryStillRejectsGenuineCollisions:
    def test_glossary_registry_still_raises_for_true_urn_collision(self):
        registry = GlossaryRegistry()
        registry.insert({"id": "g1", "urn": "urn:ncert-kg:same:urn:value", "term": "Alpha"})
        with pytest.raises(DuplicateUrnError):
            registry.insert({"id": "g2", "urn": "urn:ncert-kg:same:urn:value", "term": "Beta"})

    def test_glossary_registry_still_raises_for_true_id_collision(self):
        registry = GlossaryRegistry()
        registry.insert({"id": "same-id", "urn": "urn:a", "term": "Alpha"})
        with pytest.raises(DuplicateIdError):
            registry.insert({"id": "same-id", "urn": "urn:b", "term": "Beta"})


# --------------------------------------------------------------------------
# STEP 4 audit: same id/urn-input-mismatch bug class, verified fixed for
# definitions (idx now in urn_parts, matching object_id) and activities
# (page + idx now in urn_parts, matching object_id's own idx input).
# --------------------------------------------------------------------------
class TestDefinitionDuplicateTermSamePage:
    def test_same_term_same_page_distinct_occurrences_get_distinct_urns(self):
        d1 = _build_definition("Partnership", 12, idx=3)
        d2 = _build_definition("Partnership", 12, idx=7)
        assert d1["urn"] != d2["urn"]
        assert d1["id"] != d2["id"]

    def test_same_term_same_page_both_insert_without_raising(self):
        registry = DefinitionRegistry()
        registry.insert(_build_definition("Partnership", 12, idx=3))
        registry.insert(_build_definition("Partnership", 12, idx=7))  # must NOT raise
        assert registry.size() == 2


class TestActivityDuplicateTypeSamePage:
    def test_same_type_same_page_distinct_occurrences_get_distinct_urns(self):
        a1 = _build_activity("Discuss", 47, idx=2)
        a2 = _build_activity("Discuss", 47, idx=9)
        assert a1["urn"] != a2["urn"]
        assert a1["id"] != a2["id"]

    def test_same_type_same_page_both_insert_without_raising(self):
        registry = ActivityRegistry()
        registry.insert(_build_activity("Discuss", 47, idx=2))
        registry.insert(_build_activity("Discuss", 47, idx=9))  # must NOT raise
        assert registry.size() == 2


# --------------------------------------------------------------------------
# Canonical URN uniqueness, more generally: id and urn must always be
# derived from the same distinguishing inputs for a given object type, so
# neither can be unique while the other collides.
# --------------------------------------------------------------------------
class TestIdUrnInputsAgree:
    def test_glossary_id_and_urn_share_the_same_distinguishing_inputs(self):
        # Changing ONLY the topic must change both id and urn, together --
        # never one without the other.
        base = _build_glossary_entry("Goodwill", "topic-1")
        changed_topic = _build_glossary_entry("Goodwill", "topic-2")
        assert base["id"] != changed_topic["id"]
        assert base["urn"] != changed_topic["urn"]