"""
compiler/references.py — Phase B2: Deterministic Cross-Reference Resolution.

SCOPE (read this before touching anything else): Phase A, Phase B0,
Phase B1, Phase B1b, and Phase B1c are frozen -- this module does not
redesign CanonicalRegistry/RegistryManager (compiler/registry.py,
compiler/registry_manager.py), does not add new registry types
(compiler/registries.py's twelve registries are untouched), does not
touch Stage A-E extraction, and does not touch compiler/enrichment.py's
or compiler/normalization.py's own fields. It ONLY adds a third,
additive layer of metadata on top of what B1c's normalization pass
already put on each item: resolved references BETWEEN registry items,
expressed purely as canonical ids.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
Knowledge Graph, Dependency Graph, Prerequisite Graph, or any other
graph. Nothing here creates an edge/relationship object, computes a
weight, orders concepts by prerequisite, or infers that two differently
-spelled strings name the same thing. Every reference this module
produces is a plain id (or list of ids) copied from one existing
registry item onto another existing registry item's own dict -- never a
new object, never a score, never a guess.

RESOLUTION STRATEGY (deterministic only -- see task's RESOLUTION RULES):
this module resolves exactly one kind of link -- "does this item name an
existing Concept?" -- using ONLY:

  * ConceptRegistry's own canonical_lookup_key (B1c) and canonical_aliases
    (B1c) / aliases (B1) fields -- i.e. data another phase already
    computed and put ON the concept, never re-derived from scratch here
    (see _concept_lookup_key below, which calls
    compiler.normalization.canonical_lookup_key -- the same function
    B1c itself uses -- rather than inventing a second normalization
    algorithm).
  * The candidate item's OWN canonical_lookup_key (B1c), which is
    itself always derived from the item's own name/title/term field
    (compiler.enrichment._raw_display_name's fixed priority order) --
    never from free text such as a caption, description, or summary.

WHY ONLY DEFINITION AND GLOSSARY ACTUALLY RESOLVE TODAY: every one of
the twelve Phase B1 registries is put through this same resolver (see
_RESOLVABLE_NAME_FIELD / resolve_registries below), so the mechanism
itself has no per-type special case. But whether a given type's items
carry a name/title/term field that DETERMINISTICALLY denotes "the
concept this record is about" is a fact about that type's own schema,
not a policy choice made in this file:

  - Definition.term and GlossaryEntry.term are, by schema definition
    (schemas/chapter_schema.py), literally the word/phrase being
    defined/glossed -- resolving that term against ConceptRegistry is
    exactly what "Definition -> Concept ID" / "Glossary Entry ->
    Concept ID" in the task spec describes.
  - Equation, NoteItem, and WarningItem have no name/title/term field
    at all (schemas/chapter_schema.py) -- _raw_display_name already
    returns None for them, so canonical_lookup_key is None, so there is
    nothing to look up. This is not a gap in this module; there is no
    deterministic source data yet.
  - Figure/Diagram/Table/Example/Activity/Box DO carry a `title` field,
    but pipeline.py's own Phase A finalization review (see pipeline.py,
    "A4 review (Fix 3, Phase A finalization)" comment, just above the
    figures/diagrams/tables construction loop) already examined and
    explicitly REJECTED resolving concept links from a region's own
    title/caption text as a non-deterministic heuristic guess ("The
    only way to populate concept_ids today would be to guess from
    region.caption/region.title text ... both are heuristics, not
    existing deterministic information"). This module honors that same
    already-established project decision rather than quietly
    reintroducing the exact heuristic that review ruled out: a Figure's
    own `title` is a label for the figure, not a claim that the text it
    contains is a Concept's canonical name, so it is not treated as a
    resolvable name field here. Their `concept_ids` field is therefore
    always populated as `[]` -- correctly resolved to "nothing", not
    silently omitted (see RESOLUTION RULES: "leave the reference
    unresolved. Never guess.").

If a future phase adds genuinely deterministic source data for these
nine types (e.g. an explicit, VLM-free "this equation was extracted
from beneath heading X" back-reference), only _RESOLVABLE_NAME_FIELD
below needs a new entry -- the resolution/aggregation mechanism itself
already generalizes to any registry.

AMBIGUITY (see RESOLUTION RULES: "If multiple valid candidates exist,
leave the reference unresolved. Never guess."): the concept lookup index
this module builds (_build_concept_lookup) is keyed by normalized
lookup key -> concept id. If two DIFFERENT concepts ever normalize to
the same key (e.g. two distinct concepts whose names differ only in
case/punctuation the normalizer folds away, or a name colliding with
another concept's alias), that key is dropped from the index entirely
rather than arbitrarily picking one -- every item that would have
matched that key resolves to "unresolved" instead of a guess.

OUTPUT FIELDS (additive only -- see task's OUTPUT FIELDS section):

  concept_id       -- Definition / GlossaryEntry items only. The single
                      resolved Concept id, or None if unresolved.
  concept_ids      -- every other of the twelve Phase B1 registries.
                      Always a list (today: always [], per the "WHY ONLY
                      DEFINITION AND GLOSSARY" note above -- present and
                      empty, not omitted).
  definition_ids    \\
  glossary_ids       |  Concept items only. The reverse of concept_id
  equation_ids        > above: every OTHER registry's item id that
  figure_ids          |  resolved (via concept_id/concept_ids) to this
  diagram_ids          | concept, grouped by registry. Always present,
  table_ids             | always a list (empty unless something actually
  activity_ids           | resolved to this concept).
  example_ids            |
  warning_ids            |
  note_ids               |
  box_ids            ___/
  reference_resolution -- bookkeeping about this pass itself (mirrors
                      enrichment's/normalization's own per-item
                      bookkeeping field):
                        version      : REFERENCE_RESOLUTION_VERSION
                        status       : "resolved" | "unresolved" (for
                                       concept_id-bearing items) or
                                       "not_applicable" (every other
                                       item, including every Concept --
                                       Concept items are never
                                       themselves the SOURCE of a
                                       concept_id/concept_ids
                                       resolution, only the TARGET)
                        resolved_at  : ISO-8601 UTC timestamp

TOPIC -> CONCEPT RESOLUTION (see task's "Topic -> Contained Concept
IDs" example): a topic's own concept-linking was already implemented,
correctly and deterministically, in Phase A (pipeline.py's
topic-construction loop: each topic's `concept_names` list, gathered
from semantic_processor's per-topic output, is resolved against a
chapter-wide `concept_name_to_id` map into the topic's own `concepts`
field -- see pipeline.py around the `concept_registry`/
`this_topic_concept_ids` code). That is frozen, correct, working code
this task explicitly says not to redesign -- this module's
verify_topic_references()/resolve_topic_concept_ids() below remain the
authoritative, read-only parity check for it, unchanged.

(Phase C0.1 audit-findings refinement: `topics` is now also a
RegistryManager-owned registry -- see compiler/registries.py's own
"TOPIC REGISTRY" docstring section -- but it holds a canonical-enveloped
SNAPSHOT COPY of each topic, not pipeline.py's own `topics_out` dicts.
resolve_registries() below still iterates it generically like every
other registry [it's just one more name in `manager.names()`], but that
is orthogonal to, and does not replace or duplicate, the Phase-A
resolution / this module's read-only verification described above.)
`resolve_topic_concept_ids` / `verify_topic_references` below exist so
Topic -> Concept resolution goes through this SAME centralized lookup
index as every other reference type (the task's own "avoid duplicated
lookup logic. Centralize all resolution logic." instruction) and so it
has direct test coverage here -- but they are deliberately READ-ONLY:
they never mutate a topic dict. Two independent reasons:

  1. `schemas.chapter_schema.TopicNode` is a plain `BaseModel` with no
     `extra="allow"` (unlike every CanonicalObjectBase subclass this
     module DOES write additive fields onto), and
     modules/validator.validate_chapter round-trips the whole Chapter
     JSON through `ChapterJSON.model_validate(...).model_dump()` before
     it is written to disk. A new key added to a topic dict would
     therefore be silently dropped at that step -- writing it would be
     dead weight that looks like it worked (present on the in-memory
     dict / in RegistryManager-adjacent bookkeeping) but never survives
     to the actual Chapter JSON file, which is worse than not writing
     it at all.
  2. Topic.concepts already IS the correctly-resolved reference (Phase
     A, frozen) -- there is nothing to fix, and mutating it would risk
     exactly the kind of "redesign a frozen phase" the task explicitly
     rules out.

WHERE THIS RUNS: pipeline.py calls resolve_references() once per
chapter, immediately after normalize_registries() finishes and before
compiler_state.set_current_registry_manager() hands the manager off --
the same integration pattern B1b's enrich_registries() and B1c's
normalize_registries() already established. Every registry item is the
SAME dict object pipeline.py's flat lists hold (see compiler/
enrichment.py's and compiler/normalization.py's own documentation of
this), so reference fields become visible on those objects too and flow
into json_writer.assemble_chapter_json's output -- additive only, so
existing JSON output/consumers/schemas (extra="allow" on every
CanonicalObjectBase subclass) remain fully backward compatible. ids/
urns/normalized lookup keys/aliases are never read from anywhere except
each item's own already-computed fields; none are ever changed.

NOT IN SCOPE HERE (see task's own DO NOT IMPLEMENT list): Knowledge
Graph, Dependency Graph, Prerequisite Graph, relationship generation,
semantic graph, concept hierarchy, learning graph, reasoning graph,
graph traversal, concept merging, alias inference, semantic inference,
graph validation, compiler optimization. This module resolves REFERENCES
(ids copied between two already-existing items when a deterministic
match exists) -- it never builds a graph structure, never invents an
edge type/weight/direction beyond "this id points at that id", and never
decides two differently-spelled things are "the same concept" (that
would be alias inference, explicitly out of scope -- concept identity
itself is still decided entirely by Phase A's own case-insensitive-name
Single Owner Principle, untouched here).

COPYRIGHT: this module reads and copies existing ids/keys only -- it
never reads, generates, or copies any educational content (definition
text, descriptions, summaries) and never invents new text of any kind.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .registry_manager import RegistryManager
from .normalization import canonical_lookup_key
from .enrichment import _raw_display_name

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of ENRICHMENT_VERSION and
# NORMALIZATION_VERSION, which version those separate, earlier passes).
# Bump only if the resolution logic in this file itself changes in a way
# a consumer of `reference_resolution.version` should be able to detect.
REFERENCE_RESOLUTION_VERSION = "1.0.0"

# Every additive field this module can add to a registry item, for
# tests/tooling that want to enumerate them without hardcoding a second
# copy of this list (mirrors NORMALIZATION_FIELDS' / ENRICHMENT_FIELDS'
# own role in normalization.py / enrichment.py).
REFERENCE_FIELDS = [
    "concept_id",
    "concept_ids",
    "definition_ids",
    "glossary_ids",
    "equation_ids",
    "figure_ids",
    "diagram_ids",
    "table_ids",
    "activity_ids",
    "example_ids",
    "warning_ids",
    "note_ids",
    "box_ids",
    "reference_resolution",
]

# Registry name -> the one field on that registry's own items whose
# value DETERMINISTICALLY denotes "the concept this record is about" --
# see module docstring's "WHY ONLY DEFINITION AND GLOSSARY ACTUALLY
# RESOLVE TODAY" section for why the other ten registries are absent
# from this mapping (either no such field exists at all -- Equation/
# NoteItem/WarningItem -- or the only candidate field, `title`, was
# already reviewed and rejected as a non-deterministic heuristic by
# pipeline.py's own Fix 3 review -- Figure/Diagram/Table/Example/
# Activity/Box). Every registry not listed here still gets a `concept_ids
# = []` stamp (see resolve_registries) -- deterministically resolved to
# "nothing available", not silently skipped.
#
# Both registries below use "term" -- not because this module special-
# cases the string "term", but because that IS the field
# schemas.chapter_schema.Definition / GlossaryEntry declare for exactly
# this purpose (see their own docstrings/field definitions).
_RESOLVABLE_NAME_FIELD: Dict[str, str] = {
    "definitions": "term",
    "glossary": "term",
}

# Registry name -> the reverse-aggregation field name written onto the
# MATCHING Concept record (see module docstring's OUTPUT FIELDS list).
# Every one of the twelve Phase B1 registries has an entry here so every
# Concept record always carries a complete, stable field set (empty
# list where nothing resolved -- the same "always present, sometimes
# empty" convention compiler/enrichment.py already established for its
# own fields).
_REVERSE_ID_FIELD: Dict[str, str] = {
    "definitions": "definition_ids",
    "glossary": "glossary_ids",
    "equations": "equation_ids",
    "figures": "figure_ids",
    "diagrams": "diagram_ids",
    "tables": "table_ids",
    "activities": "activity_ids",
    "examples": "example_ids",
    "warnings": "warning_ids",
    "notes": "note_ids",
    "boxes": "box_ids",
}


# --------------------------------------------------------------------------
# Pure lookup-key helpers -- reuse B1c's normalization utilities only,
# never a second normalization algorithm (task's own "Reuse normalization
# utilities... Avoid duplicated lookup logic" instruction).
# --------------------------------------------------------------------------

def _item_lookup_key(item: Dict[str, Any]) -> Optional[str]:
    """The normalized lookup key that identifies `item` by its own name/
    title/term, preferring the value B1c's normalize_item() already
    computed and stored (`canonical_lookup_key`) so this module never
    redoes work another frozen phase already did. Falls back to deriving
    it fresh -- via the exact same two reused functions B1c itself uses
    (compiler.enrichment._raw_display_name + compiler.normalization.
    canonical_lookup_key) -- only for an item that has not been through
    normalize_item() yet (e.g. a hand-built test fixture), so this
    module works correctly even when called out of the usual pipeline
    order."""
    if not isinstance(item, dict):
        return None
    existing = item.get("canonical_lookup_key")
    if existing:
        return existing
    return canonical_lookup_key(_raw_display_name(item))


def _item_alias_keys(item: Dict[str, Any]) -> List[str]:
    """Normalized lookup keys for every alias already present on `item`
    (today: only Concept records carry `aliases`/`canonical_aliases` --
    see compiler/enrichment.py's/compiler/normalization.py's own
    `_aliases`/`_canonical_aliases`). Prefers B1c's already-normalize_text
    -ed `canonical_aliases` when present (still needs canonical_lookup_key
    applied -- canonical_aliases is NFKC/whitespace-normalized text for
    DISPLAY, not yet casefolded/punctuation-stripped into a lookup key),
    falling back to the raw `aliases` list otherwise. No alias is
    invented, dropped, or resolved against anything here -- purely a
    key-normalization step over data another phase already put on the
    item."""
    if not isinstance(item, dict):
        return []
    aliases = item.get("canonical_aliases")
    if aliases is None:
        aliases = item.get("aliases")
    if not isinstance(aliases, list):
        return []
    keys: List[str] = []
    for alias in aliases:
        if not isinstance(alias, str):
            continue
        key = canonical_lookup_key(alias)
        if key:
            keys.append(key)
    return keys


# --------------------------------------------------------------------------
# Concept lookup index
# --------------------------------------------------------------------------

def _build_concept_lookup(concept_registry: Any) -> Dict[str, str]:
    """Builds a normalized-lookup-key -> concept-id index from every item
    currently in `concept_registry`, using ONLY each concept's own
    canonical_lookup_key (B1c) / canonical_aliases (B1c) or aliases (B1)
    fields -- see module docstring's RESOLUTION STRATEGY. A key that
    would resolve to more than one DIFFERENT concept id is dropped from
    the index entirely (see module docstring's AMBIGUITY section) rather
    than arbitrarily kept as the first/last one seen -- every candidate
    item whose own key collides with such a dropped key resolves to
    "unresolved", never a guess.

    Deterministic: iterates concept_registry.values() in the registry's
    own insertion order, so two runs over the same concepts always build
    byte-identical indexes.
    """
    index: Dict[str, str] = {}
    ambiguous: set = set()

    def _record(key: Optional[str], concept_id: str) -> None:
        if not key:
            return
        if key in ambiguous:
            return
        existing = index.get(key)
        if existing is None:
            index[key] = concept_id
        elif existing != concept_id:
            # Two different concepts share this normalized key -- never
            # guess which one a future candidate meant.
            del index[key]
            ambiguous.add(key)

    for concept in concept_registry.values():
        concept_id = concept.get("id") if isinstance(concept, dict) else None
        if not concept_id:
            continue
        _record(_item_lookup_key(concept), concept_id)
        for alias_key in _item_alias_keys(concept):
            _record(alias_key, concept_id)

    return index


def _resolve_concept_id(item: Dict[str, Any], concept_lookup: Dict[str, str]) -> Optional[str]:
    """Resolves a single candidate item (e.g. a Definition or Glossary
    Entry) to a Concept id via `concept_lookup`, or None if the item has
    no lookup key, or its key is not (unambiguously) in the index. Never
    raises; never guesses (see module docstring's AMBIGUITY section --
    an ambiguous key was already removed from `concept_lookup` by
    _build_concept_lookup, so a simple dict lookup here is already
    "leave unresolved on ambiguity")."""
    key = _item_lookup_key(item)
    if not key:
        return None
    return concept_lookup.get(key)


# --------------------------------------------------------------------------
# Per-item / per-registry resolution
# --------------------------------------------------------------------------

def _stamp_resolution(item: Dict[str, Any], *, status: str) -> None:
    item["reference_resolution"] = {
        "version": REFERENCE_RESOLUTION_VERSION,
        "status": status,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


def resolve_registries(manager: RegistryManager) -> Dict[str, Any]:
    """Resolves every candidate registry's items against ConceptRegistry,
    and writes the reverse aggregation back onto every Concept record.
    Mutates registry items IN PLACE (additive keys only -- see module
    docstring's OUTPUT FIELDS list) and calls CanonicalRegistry.update()
    to replace each registry's stored reference, exactly like B1b's
    enrich_registry() / B1c's normalize_registry() do. Returns a
    dict of resolution statistics (registry name -> counts), primarily
    for logging/tests.

    Safe to call more than once: every field is recomputed fresh each
    time from each item's own current state, and update() accepts
    replacing an item with itself.
    """
    concept_registry = manager.get("concepts")
    concept_lookup = _build_concept_lookup(concept_registry)

    # concept_id -> registry_name -> [item ids] (deterministic: built by
    # iterating each registry in RegistryManager's own registration
    # order, and each registry's own items in its own insertion order).
    reverse_links: Dict[str, Dict[str, List[str]]] = {}

    stats: Dict[str, Any] = {"registries": {}}

    for registry_name in manager.names():
        if registry_name == "concepts":
            continue
        registry = manager.get(registry_name)
        name_field = _RESOLVABLE_NAME_FIELD.get(registry_name)
        resolved_count = 0
        total_count = 0

        for item in registry.values():
            if not isinstance(item, dict):
                continue
            total_count += 1

            if name_field is not None:
                # concept_id (singular) types: Definition, GlossaryEntry.
                concept_id = _resolve_concept_id(item, concept_lookup)
                item["concept_id"] = concept_id
                _stamp_resolution(item, status="resolved" if concept_id else "unresolved")
                if concept_id:
                    resolved_count += 1
                    reverse_links.setdefault(concept_id, {}) \
                        .setdefault(registry_name, []).append(item.get("id"))
            else:
                # concept_ids (plural) types: every other of the eleven
                # non-concept registries. No deterministic source field
                # exists today (see module docstring) -- correctly
                # resolved to "nothing available", not skipped.
                if "concept_ids" not in item:
                    item["concept_ids"] = []
                if "reference_resolution" not in item:
                    _stamp_resolution(item, status="not_applicable")

            registry.update(item)

        stats["registries"][registry_name] = {
            "total": total_count,
            "resolved": resolved_count,
        }

    # Write the reverse aggregation onto every Concept record.
    concept_resolved = 0
    for concept in concept_registry.values():
        if not isinstance(concept, dict):
            continue
        concept_id = concept.get("id")
        links = reverse_links.get(concept_id, {})
        for registry_name, field_name in _REVERSE_ID_FIELD.items():
            concept[field_name] = list(links.get(registry_name, []))
        if any(links.values()):
            concept_resolved += 1
        _stamp_resolution(concept, status="not_applicable")
        concept_registry.update(concept)

    stats["registries"]["concepts"] = {
        "total": concept_registry.size(),
        "resolved": concept_resolved,
    }
    stats["concept_lookup_keys"] = len(concept_lookup)
    return stats


# --------------------------------------------------------------------------
# Topic -> Concept resolution (read-only -- see module docstring)
# --------------------------------------------------------------------------

def resolve_topic_concept_ids(
    topic: Dict[str, Any], concept_lookup: Dict[str, str]
) -> List[str]:
    """Pure function: resolves one topic dict's own `concept_names` list
    (built by pipeline.py's Phase A topic-construction loop -- see
    module docstring's "TOPIC -> CONCEPT RESOLUTION" section) against
    `concept_lookup`, via the exact same normalized-key lookup every
    other registry in this module resolves through. Returns the list of
    resolved concept ids, in `concept_names`' own order, with duplicates
    removed (a topic mentioning the same concept name twice should not
    produce the same id twice) and any unresolved name simply omitted
    (never a guess, never a placeholder). Does NOT mutate `topic` -- see
    module docstring for why (TopicNode has no extra="allow", and
    Topic.concepts already holds this Phase-A-resolved reference)."""
    names = topic.get("concept_names") if isinstance(topic, dict) else None
    if not names:
        return []
    resolved: List[str] = []
    seen: set = set()
    for name in names:
        if not isinstance(name, str):
            continue
        key = canonical_lookup_key(name)
        concept_id = concept_lookup.get(key) if key else None
        if concept_id and concept_id not in seen:
            resolved.append(concept_id)
            seen.add(concept_id)
    return resolved


def verify_topic_references(
    topics: Iterable[Dict[str, Any]], manager: RegistryManager
) -> Dict[str, Any]:
    """Read-only diagnostic: for every topic in `topics`, resolves its
    `concept_names` via this module's own centralized concept lookup
    index (resolve_topic_concept_ids) and reports whether that agrees
    with the topic's own, already-Phase-A-resolved `concepts` field (as
    an unordered set comparison -- Phase A's simpler map and this
    module's ambiguity-aware index are expected to agree whenever no
    ambiguous concept name exists in the chapter). Returns per-topic and
    aggregate counts; never mutates a topic or raises on disagreement
    (a disagreement is a diagnostic to log/inspect, e.g. surfaced via
    pipeline.py's existing DEBUG-gated registry-statistics logging point,
    not a pipeline failure -- see pipeline.py's own guarded
    logger.debug() pattern right after registry population).
    """
    concept_registry = manager.get("concepts")
    concept_lookup = _build_concept_lookup(concept_registry)

    topics = list(topics)
    per_topic: List[Dict[str, Any]] = []
    agree_count = 0
    for topic in topics:
        resolved = resolve_topic_concept_ids(topic, concept_lookup)
        existing = topic.get("concepts") or [] if isinstance(topic, dict) else []
        agrees = set(resolved) == set(existing)
        if agrees:
            agree_count += 1
        per_topic.append({
            "id": topic.get("id") if isinstance(topic, dict) else None,
            "resolved_concept_ids": resolved,
            "existing_concept_ids": list(existing),
            "agrees": agrees,
        })

    return {
        "version": REFERENCE_RESOLUTION_VERSION,
        "topics_checked": len(topics),
        "topics_agree": agree_count,
        "topics": per_topic,
    }


# --------------------------------------------------------------------------
# Top-level entry point
# --------------------------------------------------------------------------

def resolve_references(
    manager: RegistryManager,
    *,
    topics: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Phase B2's single pipeline.py integration point. Runs
    resolve_registries(manager) (mutating, additive -- see its own
    docstring) and, if `topics` is given, also runs
    verify_topic_references(topics, manager) (read-only -- see its own
    docstring) for diagnostic parity with Topic -> Concept resolution.
    Returns the combined statistics dict; pipeline.py's own integration
    point only needs the side effect on `manager`, not this return
    value (mirrors normalize_registries()'s own "primarily for
    logging/tests" return-value note).
    """
    stats = resolve_registries(manager)
    if topics is not None:
        stats["topics"] = verify_topic_references(topics, manager)
    return stats