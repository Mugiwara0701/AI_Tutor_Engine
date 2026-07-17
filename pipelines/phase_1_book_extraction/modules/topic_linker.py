"""
modules/topic_linker.py — Milestone 1: Universal Object Linking.

SCOPE: this milestone is structural linking ONLY. It does not touch
Phase 2 (Knowledge-Graph / dependency-graph construction, kg_readiness.py
-- see kg_readiness.py's own "that remains entirely Phase 2's job" note),
does not touch compiler/references.py's or compiler/relationships.py's
own (frozen) concept-id resolution or relationship generation, does not
add any validation or semantic-summary logic, and does not redesign
canonical.canonical_fields()/CanonicalObjectBase. It adds exactly one
thing: a reusable, object-type-agnostic pass that fills in `topic_ids`
(and, where a deterministic reverse slot already exists on TopicNode,
the matching reverse-reference list) for every canonical object type
that pipeline.py was not already linking.

BACKGROUND -- what was already working: concepts, glossary entries, and
definitions are linked to their enclosing topic INLINE, at construction
time, in pipeline.py's own topic-construction loop (concepts/glossary
via the loop's own `t.id`; definitions via the `topic_lookup` callback
`_topic_lookup_factory` builds and passes into
content_blocks.detect_definition_terms). Every OTHER canonical object
type built in pipeline.py -- examples, tables, figures, diagrams,
equations, notes, boxes, activities, warnings -- goes through
`_attach_canonical()` / `canonical.canonical_fields()` with no
`topic_ids=` argument at all, so `topic_ids` defaults to `[]` and stays
empty forever. `_topic_lookup_factory`'s own docstring already claims
this lookup is "used by definitions/examples/boxes to attach themselves
to the enclosing topic" -- examples and boxes were never actually wired
up to it. This module is what closes that gap, generically, for every
remaining canonical object type, rather than adding nine more one-off
call sites.

RESOLUTION STRATEGY (deterministic only -- "Never guess" per task spec):
the only structural fact this module relies on is PAGE CONTAINMENT.
Every canonical object built in pipeline.py carries a `page` (copied
from the region/content-block it was extracted from), and every topic
carries a `page_start`/`page_end` range computed deterministically by
pdf_parser's heading detection. "This object's page falls within this
topic's page range" is exactly the same geometric fact
`_topic_lookup_factory` already uses for definitions -- this module
generalizes that ONE already-accepted mechanism instead of inventing a
new one. It is explicitly NOT the same kind of thing as matching a
figure's caption/title text against a concept name -- that heuristic was
already reviewed and explicitly rejected elsewhere in this codebase (see
pipeline.py's "A4 review (Fix 3, Phase A finalization)" comment, just
above the figures/diagrams/tables construction loop) as non-deterministic
guessing. Page-range containment carries no such ambiguity: a page is
either inside a topic's [page_start, page_end] span or it is not.

If an object's page cannot be determined, or no topic's page range
contains it (e.g. a region on a chapter-cover page before the first
heading), NOTHING is linked for that object: `topic_ids` is left
exactly as it already was (normally `[]`), and it is never added to any
topic's reverse-reference list. This mirrors compiler/references.py's
own rule: "If the deterministic source field a relationship type needs
is absent or empty ... that relationship is simply not generated."

WHAT THIS MODULE NEVER DOES:
  * Never overwrites an already-populated `topic_ids` (an object linked
    by an earlier, more specific pass -- e.g. a Definition, already
    linked at construction time -- is left untouched).
  * Never writes `concept_ids`. Every one of the nine object types this
    module targets has its `concept_ids` left exactly as
    `canonical.canonical_fields()` already set it (`[]` today -- see the
    already-established "A4 review" reasoning in pipeline.py: there is
    no deterministic name/term field on these types to resolve against
    the concept registry, and borrowing the enclosing topic's own
    concept list would be exactly the kind of guess the roadmap already
    ruled out). `resolve_deterministic_concept_ids()` below exists only
    so a FUTURE object type that genuinely does carry a deterministic
    concept-name field can opt in explicitly -- it is not used by
    `link_universal_objects()` today because no such field exists yet on
    any of the nine supported types.
  * Never matches on caption, title, or any other free text.
  * Never mutates an object's `id`, `urn`, or any field other than
    `topic_ids` (and, on the topic side, the one matching reverse list).

REUSABILITY (requirement: "design a reusable linker rather than
object-specific code"): the entire linking mechanism is exactly two
generic functions -- `link_object_to_topic` (single object) and
`link_objects_to_topics` (a homogeneous list of one object type). Both
take `object_type` purely as a label used to look up the matching
TopicNode reverse-list name in `TOPIC_REVERSE_FIELDS`; neither contains
any per-type branching on how to read or link the object itself. Adding
a tenth or eleventh supported type is a one-line addition to
`TOPIC_REVERSE_FIELDS` (or a `None` entry, for a type with no reverse
slot), never a new function.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional

# A page -> topic_id lookup function. `None` means "no topic's page
# range deterministically contains this page" (or the page itself is
# unknown) -- never a guess, never a fallback to "the nearest topic".
PageLookup = Callable[[Optional[int]], Optional[str]]

# --------------------------------------------------------------------------
# object_type -> TopicNode reverse-reference field name.
#
# Every value here is a field schemas/chapter_schema.py::TopicNode already
# declares (examples/activities/figures/tables/equations/diagrams/boxes/
# notes/warnings/definitions/concepts) -- this module never invents a new
# TopicNode field. `concept`/`glossary_entry`/`definition` are listed for
# completeness/reuse (see module docstring's REUSABILITY note and
# tests/test_topic_linker.py) even though pipeline.py does not route
# those three through this module today (they are already linked inline
# at construction time -- see BACKGROUND above). `glossary_entry` maps to
# `None` because TopicNode has no reverse list for glossary entries
# today; forward `topic_ids` linking would still work for it, the
# reverse-list step is simply a no-op for that one type.
# --------------------------------------------------------------------------
TOPIC_REVERSE_FIELDS: Dict[str, Optional[str]] = {
    "example": "examples",
    "activity": "activities",
    "figure": "figures",
    "table": "tables",
    "equation": "equations",
    "diagram": "diagrams",
    "box": "boxes",
    "note": "notes",
    "warning": "warnings",
    "definition": "definitions",
    "concept": "concepts",
    "glossary_entry": None,
}

# The nine canonical object types this milestone's pipeline.py
# integration point (link_universal_objects) links. Concepts, glossary
# entries, and definitions are intentionally excluded here -- they are
# already correctly linked elsewhere (see BACKGROUND above) and are not
# re-processed by this module's top-level entry point (though the
# underlying per-object functions work identically for them, see
# REUSABILITY above and tests/test_topic_linker.py).
UNIVERSAL_LINKING_OBJECT_TYPES: List[str] = [
    "example", "table", "figure", "diagram", "equation",
    "note", "box", "activity", "warning",
]


def resolve_object_page(obj: Dict[str, Any]) -> Optional[int]:
    """Pure function: the single deterministic page number for a
    canonical object dict, if any.

    Prefers the object's own top-level `page` (set at construction by
    every region/content-block builder in pipeline.py) and falls back to
    `provenance.source_page` (the exact same value, mirrored there by
    `pipeline._attach_canonical`'s own
    `source_page if source_page is not None else obj.get("page")`
    fallback -- so the two fields never disagree for any object this
    pipeline builds; this function simply tolerates whichever one a
    caller-constructed test fixture happens to set). Never derives a
    page from a bbox, a page range, a caption, or any other inferred
    source -- if neither field holds a definite `int`, this returns
    `None` and the caller must leave the object unlinked."""
    page = obj.get("page")
    if isinstance(page, int) and not isinstance(page, bool):
        return page
    provenance = obj.get("provenance")
    if isinstance(provenance, dict):
        source_page = provenance.get("source_page")
        if isinstance(source_page, int) and not isinstance(source_page, bool):
            return source_page
    return None


def make_page_topic_lookup(topics: Iterable[Dict[str, Any]]) -> PageLookup:
    """Builds a `page -> topic_id` lookup function from a list of topic
    dicts (each needs `id`, `page_start`, `page_end`).

    Uses EXACTLY the same deterministic containment rule pipeline.py's
    own `_topic_lookup_factory` already uses for definitions: a page is
    linked to the LAST topic (in the input's own order -- for
    `topics_out`, document/reading order) whose `[page_start, page_end]`
    contains it. Reimplemented here (rather than imported from
    pipeline.py) so this module has no dependency on pipeline.py --
    pipeline.py imports this module, never the reverse.

    A topic with a missing or non-integer `page_start`/`page_end` is
    simply never a candidate; it is not skipped-with-a-warning, since
    that would be a validation concern, out of this milestone's scope.
    """
    topics = list(topics)

    def lookup(page: Optional[int]) -> Optional[str]:
        if not isinstance(page, int) or isinstance(page, bool):
            return None
        candidates = [
            t for t in topics
            if isinstance(t, dict) and t.get("id")
            and isinstance(t.get("page_start"), int) and not isinstance(t.get("page_start"), bool)
            and isinstance(t.get("page_end"), int) and not isinstance(t.get("page_end"), bool)
            and t["page_start"] <= page <= t["page_end"]
        ]
        return candidates[-1]["id"] if candidates else None

    return lookup


def link_object_to_topic(
    obj: Dict[str, Any],
    *,
    topic_lookup: PageLookup,
) -> Optional[str]:
    """Links ONE canonical object dict to its enclosing topic, in place.

    If `obj["topic_ids"]` is already non-empty, this is a no-op that
    returns the first existing id -- an object already linked by an
    earlier, more specific pass (e.g. a Definition or Glossary Entry,
    linked at construction time) is never overwritten or second-guessed.

    Otherwise, resolves the object's own page (`resolve_object_page`)
    and looks it up via `topic_lookup`. If a topic id is found, sets
    `obj["topic_ids"] = [topic_id]` and returns it. If no topic id can
    be determined (unresolvable page, or no topic's range contains it),
    `obj["topic_ids"]` is left exactly as it already was -- never forced
    to anything, never guessed -- and this function returns `None`.

    Never writes `concept_ids` or any other field.
    """
    existing = obj.get("topic_ids")
    if existing:
        return existing[0]

    topic_id = topic_lookup(resolve_object_page(obj))
    if topic_id:
        obj["topic_ids"] = [topic_id]
        return topic_id
    return None


def link_objects_to_topics(
    objects: Iterable[Dict[str, Any]],
    *,
    object_type: str,
    topic_lookup: PageLookup,
    topics_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """The reusable universal linking primitive. Works identically for
    every canonical object type -- `object_type` is used ONLY to look up
    which TopicNode reverse-list (if any) gets appended to
    (`TOPIC_REVERSE_FIELDS`); there is no other per-type branching
    anywhere in this function.

    For every dict in `objects`:
      1. `link_object_to_topic` resolves and writes its `topic_ids` in
         place (or leaves it untouched -- see that function's docstring).
      2. If a topic id was resolved, `topics_by_id` was given, and
         `object_type` has a reverse field, appends the object's own
         `id` onto `topics_by_id[topic_id][<field>]` -- but only if that
         id is not already present, so calling this function more than
         once over the same objects/topics is idempotent (never
         duplicates a reverse-reference entry).

    Non-dict entries, and dicts with no `id`, are skipped (nothing to
    link, nothing to key a reverse reference on).

    Returns per-call statistics (`object_type`, `total`, `linked`,
    `unlinked`) -- primarily for logging/tests, mirroring
    compiler/references.py's / compiler/relationships.py's own
    "returns stats, side effect is what matters" shape.
    """
    reverse_field = TOPIC_REVERSE_FIELDS.get(object_type)
    linked = 0
    unlinked = 0
    for obj in objects:
        if not isinstance(obj, dict) or not obj.get("id"):
            continue
        topic_id = link_object_to_topic(obj, topic_lookup=topic_lookup)
        if not topic_id:
            unlinked += 1
            continue
        linked += 1
        if topics_by_id is not None and reverse_field:
            topic = topics_by_id.get(topic_id)
            if isinstance(topic, dict):
                bucket = topic.setdefault(reverse_field, [])
                if obj["id"] not in bucket:
                    bucket.append(obj["id"])
    return {
        "object_type": object_type,
        "total": linked + unlinked,
        "linked": linked,
        "unlinked": unlinked,
    }


def resolve_deterministic_concept_ids(
    obj: Dict[str, Any],
    *,
    name_field: Optional[str],
    concept_name_to_id: Dict[str, str],
) -> List[str]:
    """Opt-in helper for a FUTURE object type that genuinely carries a
    deterministic concept-name field (see module docstring's "WHAT THIS
    MODULE NEVER DOES" section for why none of the nine object types
    this milestone links use this today). `name_field=None` (the correct
    value for every currently-supported type) always returns `[]`
    without inspecting `obj` at all -- this function never guesses a
    name field to read. Matching is exact, case-insensitive lookup
    against `concept_name_to_id` (the same map `canonical.
    resolve_concept_ids` already uses) -- no fuzzy or substring
    matching. Never mutates `obj`; the caller decides whether/how to
    write the result onto `concept_ids`."""
    if not name_field:
        return []
    name = obj.get(name_field)
    if not isinstance(name, str) or not name.strip():
        return []
    concept_id = concept_name_to_id.get(name.strip().lower())
    return [concept_id] if concept_id else []


def link_universal_objects(
    *,
    topics: List[Dict[str, Any]],
    examples: Optional[Iterable[Dict[str, Any]]] = None,
    tables: Optional[Iterable[Dict[str, Any]]] = None,
    figures: Optional[Iterable[Dict[str, Any]]] = None,
    diagrams: Optional[Iterable[Dict[str, Any]]] = None,
    equations: Optional[Iterable[Dict[str, Any]]] = None,
    notes: Optional[Iterable[Dict[str, Any]]] = None,
    boxes: Optional[Iterable[Dict[str, Any]]] = None,
    activities: Optional[Iterable[Dict[str, Any]]] = None,
    warnings: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Milestone 1's single pipeline.py integration point.

    Links every supported, previously-unlinked canonical object type
    (examples, tables, figures, diagrams, equations, notes, boxes,
    activities, warnings) to its enclosing topic via
    `link_objects_to_topics`, and populates the matching
    reverse-reference list on each topic dict in `topics`, in place.
    Concepts, glossary entries, and definitions are intentionally not
    passed through this entry point -- see module docstring's BACKGROUND
    section for why they are already linked elsewhere; `link_objects_to_topics`
    itself would handle them identically if a future caller chose to.

    Must be called AFTER every object list is fully built (so every
    object's `page` is already set) and AFTER `topics`' own
    `page_start`/`page_end`/`id` fields are final -- matching where
    pipeline.py's equivalent existing calls (`_topic_lookup_factory`,
    Phase A's topic-construction loop) already run relative to object
    construction. Safe to call more than once over the same
    objects/topics (see `link_objects_to_topics`'s own idempotency note).

    `topics` items are mutated in place: existing TopicNode
    reverse-reference fields (examples/activities/figures/tables/
    equations/diagrams/boxes/notes/warnings) are appended to, never
    replaced or cleared -- any pre-existing entries (e.g. `definitions`,
    already populated inline by pipeline.py) are left exactly as they
    were.

    Returns a dict of per-type statistics, keyed by object_type
    (mirrors compiler/references.py's / compiler/relationships.py's own
    stats shape) -- primarily for logging/tests.
    """
    topic_lookup = make_page_topic_lookup(topics)
    topics_by_id = {t["id"]: t for t in topics if isinstance(t, dict) and t.get("id")}

    supplied: Dict[str, Optional[Iterable[Dict[str, Any]]]] = {
        "example": examples, "table": tables, "figure": figures,
        "diagram": diagrams, "equation": equations, "note": notes,
        "box": boxes, "activity": activities, "warning": warnings,
    }

    stats: Dict[str, Any] = {"types": {}}
    for object_type in UNIVERSAL_LINKING_OBJECT_TYPES:
        objects = supplied.get(object_type)
        if objects is None:
            continue
        stats["types"][object_type] = link_objects_to_topics(
            objects, object_type=object_type, topic_lookup=topic_lookup,
            topics_by_id=topics_by_id,
        )

    stats["total_linked"] = sum(s["linked"] for s in stats["types"].values())
    stats["total_unlinked"] = sum(s["unlinked"] for s in stats["types"].values())
    return stats
