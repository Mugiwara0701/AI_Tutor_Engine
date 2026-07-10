"""
compiler/relationships.py — Phase B3: Canonical Semantic Relationship
Resolution.

SCOPE (read this before touching anything else): Phase A, Phase B0,
Phase B1, Phase B1b, Phase B1c, and Phase B2 are frozen -- this module
does not redesign CanonicalRegistry/RegistryManager (compiler/registry.py,
compiler/registry_manager.py), does not add new Phase B1 registry types
(compiler/registries.py's twelve registries are untouched), does not
touch Stage A-E extraction, does not touch compiler/enrichment.py's,
compiler/normalization.py's, or compiler/references.py's own fields, and
does not touch json_writer.py / schemas/chapter_schema.py / ChapterJSON.
It ONLY adds a fourth, additive compiler pass that reads references
Phase B2 (compiler/references.py) and Phase A (topic_ids/topic
concept-lists) already resolved, and turns each already-resolved
reference into an explicit, typed Relationship record -- never a new
kind of reference, never a new id/urn, never a guess.

MOST IMPORTANT REQUIREMENT (see task spec): relationships are part of
the compiler's Intermediate Representation ONLY. They are NEVER
serialized into Chapter JSON, never attached to json_writer.py's output,
and never written onto an existing educational object's own dict (that
would risk exactly the kind of accidental Chapter-JSON leakage the task
spec prohibits, since every CanonicalObjectBase subclass has
extra="allow" and would happily carry -- and later serialize -- any new
key added to it). Every Relationship this module produces lives ONLY
inside its own dedicated compiler registry (RelationshipRegistry,
below), owned by the same RegistryManager Phase B1 already built and
Phase B2 already populated -- see resolve_relationships()'s own
docstring for exactly how it is wired in.

WHAT THIS IS NOT (see task's own scope notes, mirroring
compiler/references.py's): this is not a Knowledge Graph. It computes no
weight, does no traversal, builds no adjacency structure beyond "one
flat registry of (type, source, target) records", and never decides two
differently-spelled things are "the same concept" (that is concept
identity / alias resolution, already decided by earlier, frozen phases).
Phase C is what will consume this registry to build an actual Knowledge
Graph; this module's only job is to resolve WHAT the semantic
relationship between two already-existing, already-referenced items IS.

RESOLUTION STRATEGY (deterministic only -- mirrors compiler/references.py's
own "Never infer. Never guess." rule): every relationship generated here
is read directly off a field an earlier, frozen phase already computed
deterministically:

  * concept_id / definition_ids / glossary_ids  (Phase B2 --
    compiler/references.py) -> has_definition / explains / described_by
  * concept_ids  (Phase B2 -- compiler/references.py; always [] today
    for equations/figures/diagrams/tables/activities per that module's
    own documented reason -- no deterministic source field for those ten
    types exists yet) -> uses_concept / illustrates / teaches
  * topic_ids  (Phase A -- modules/canonical.py::canonical_fields(),
    frozen, already present on every canonical object) and each topic's
    own already-Phase-A-resolved `concepts` list -> contains / appears_in
    / belongs_to

No semantic matching, caption/title matching, heuristics, embeddings,
LLM calls, fuzzy matching, or relationship scoring happens anywhere in
this file. If the deterministic source field a relationship type needs
is absent or empty on a given item, that relationship is simply not
generated for that item -- never guessed, never backfilled.

RELATIONSHIP REGISTRY: RelationshipRegistry (below) is one more
CanonicalRegistry, built and registered as "relationships" on the SAME
RegistryManager Phase B1's create_registry_manager() already builds
(via ensure_relationship_registry(), below -- create-if-absent, never a
second, parallel storage mechanism). Its items are plain
relationship dicts: {id, type, source_type, source_id, target_type,
target_id, relationship_resolution}. `id` is a deterministic id
(_relationship_id, below, over the relationship's own type/source/
target -- the same slugify-then-sha1 A3 identity strategy
modules.pdf_parser.make_id already uses for every other canonical id in
this project, reimplemented locally here rather than imported -- see
_relationship_id's own note for why), so re-running the compiler over
unchanged input always reproduces byte-identical relationship ids, and
CanonicalRegistry's own insert()-time duplicate-id rejection is what
gives this pass its "duplicate prevention" guarantee for free -- no
second dedup mechanism is invented here (see _insert_unique, which
checks contains() first specifically so a legitimately-repeated
relationship is silently skipped rather than raising DuplicateIdError).

PIPELINE INTEGRATION: resolve_relationships(manager, topics=...) is the
one pipeline.py integration point, mirroring resolve_references()'s own
shape exactly. It must run AFTER compiler.references.resolve_references()
(so concept_id/concept_ids/definition_ids/glossary_ids are already
present to read) and BEFORE compiler_state.set_current_registry_manager()
(so the manager any later phase reads via
compiler.state.get_current_registry_manager() already carries the fully
populated "relationships" registry as part of this chapter's compiler
IR) -- see pipeline.py's own integration comment for exactly where this
call was added.

BACKWARD COMPATIBILITY: ids/urns/reference fields already on every
registry item are only ever READ here, never changed. No existing
registry, field, or Chapter JSON output changes as a result of this
module existing. The only new compiler artifact is the "relationships"
registry itself.

COPYRIGHT: this module reads and copies existing ids only -- it never
reads, generates, or copies any educational content (definition text,
descriptions, summaries, captions) and never invents new text of any
kind.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .registry import CanonicalRegistry
from .registry_manager import RegistryManager

# NOTE on modules.pdf_parser.make_id: that function already implements
# the exact "slugify -> sha1, truncated, no random/UUID/timestamp
# component" strategy (A3 identity strategy) this module wants for
# relationship ids. It is intentionally NOT imported here, though: no
# other module under compiler/ imports anything from modules/ (the
# dependency edge in this project runs modules -> compiler, never the
# reverse -- see compiler/references.py, compiler/normalization.py,
# compiler/enrichment.py, none of which import from modules/), and
# modules.pdf_parser specifically requires PyMuPDF (fitz) just to import
# at all -- a heavy, otherwise-irrelevant dependency for computing an id
# from three already-in-memory strings. _relationship_id below reuses
# the SAME algorithm (not a different one), just without adding a new,
# one-directional compiler -> modules import edge that does not exist
# anywhere else in this codebase.

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of ENRICHMENT_VERSION,
# NORMALIZATION_VERSION, and REFERENCE_RESOLUTION_VERSION, which version
# those separate, earlier passes). Bump only if the relationship
# generation logic in this file itself changes in a way a consumer of
# `relationship_resolution.version` should be able to detect.
RELATIONSHIP_RESOLUTION_VERSION = "1.0.0"

# Name this pass's dedicated registry is always registered under on a
# RegistryManager -- a fixed, importable constant so callers never
# hardcode the string "relationships" in more than one place.
RELATIONSHIP_REGISTRY_NAME = "relationships"

# Every relationship `type` this module can ever produce, in the fixed
# order the task spec lists them -- exposed so tests/tooling can
# enumerate them without hardcoding a second copy of this list (mirrors
# REFERENCE_FIELDS' own role in compiler/references.py).
RELATIONSHIP_TYPES: List[str] = [
    "has_definition",     # Concept -> Definition
    "explains",           # Glossary Entry -> Concept
    "described_by",       # Concept -> Glossary Entry
    "contains",           # Topic -> Concept
    "appears_in",         # Concept -> Topic
    "belongs_to",         # Definition -> Topic, Glossary Entry -> Topic
    "uses_concept",       # Equation -> Concept
    "illustrates",        # Figure / Diagram / Table -> Concept
    "teaches",            # Activity -> Concept
]


class RelationshipRegistry(CanonicalRegistry):
    """The one dedicated compiler registry Phase B3 introduces -- see
    module docstring's RELATIONSHIP REGISTRY section. A relationship item
    is a plain dict (see resolve_relationships()'s docstring for its
    exact shape); default id_of/urn_of/name_of all work unmodified
    because every relationship dict carries an "id" key (its own
    deterministic make_id(...) result) and no "urn"/"name" key (so those
    two indexes are simply never populated for this registry -- exactly
    the same "default extractors, no per-type customization needed"
    reasoning compiler/registries.py's own twelve subclasses document).
    """

    def __init__(self) -> None:
        super().__init__(name=RELATIONSHIP_REGISTRY_NAME)


def ensure_relationship_registry(manager: RegistryManager) -> RelationshipRegistry:
    """Returns the RelationshipRegistry already registered on `manager`
    under RELATIONSHIP_REGISTRY_NAME, registering a fresh, empty one
    first if none exists yet. Safe to call repeatedly (e.g. once from
    pipeline.py's integration point and again from a test that wants a
    handle on the same registry) -- never replaces an existing registry,
    never raises on a second call for the same manager."""
    if manager.has(RELATIONSHIP_REGISTRY_NAME):
        registry = manager.get(RELATIONSHIP_REGISTRY_NAME)
        if not isinstance(registry, RelationshipRegistry):
            # A registry named "relationships" already exists but isn't
            # ours -- surface this loudly rather than silently treating
            # someone else's registry as this module's own. Should never
            # happen in the real pipeline (only this module ever
            # registers this name); guards against a misconfigured test
            # or future caller.
            raise TypeError(
                "RegistryManager already has a registry named "
                f"{RELATIONSHIP_REGISTRY_NAME!r} that is not a "
                "RelationshipRegistry."
            )
        return registry
    registry = RelationshipRegistry()
    manager.register(registry)
    return registry


# --------------------------------------------------------------------------
# Relationship construction helpers
# --------------------------------------------------------------------------

def _relationship_id(*parts: str) -> str:
    """Deterministic relationship id: same slugify -> sha1(truncated)
    strategy as modules.pdf_parser.make_id (see the import-site NOTE
    above for why that function itself isn't imported/called here).
    Purely a function of `parts` -- no random/UUID/timestamp component --
    so the same (type, source_id, target_id) triple always yields the
    same id, on this run and every future one."""
    raw = "_".join(p.lower().strip() for p in parts if p)
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or "relationship"
    digest = hashlib.sha1(slug.encode()).hexdigest()[:6]
    return f"{slug[:60]}-{digest}"


def _stamp_resolution() -> Dict[str, Any]:
    return {
        "version": RELATIONSHIP_RESOLUTION_VERSION,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_relationship(
    *,
    rel_type: str,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
) -> Dict[str, Any]:
    """Builds one deterministic relationship dict. `id` is derived only
    from the relationship's own type/source/target -- via
    _relationship_id's A3-style identity strategy (slugify -> sha1, no
    random/UUID/timestamp component) -- so the SAME (type, source,
    target) triple always yields the SAME relationship id, run after
    run, matching the task's "deterministic IDs" test requirement
    exactly."""
    rel_id = _relationship_id("relationship", rel_type, source_id, target_id)
    return {
        "id": rel_id,
        "object_type": "relationship",
        "type": rel_type,
        "source_type": source_type,
        "source_id": source_id,
        "target_type": target_type,
        "target_id": target_id,
        "relationship_resolution": _stamp_resolution(),
    }


def _insert_unique(registry: RelationshipRegistry, relationship: Dict[str, Any]) -> bool:
    """Inserts `relationship` into `registry` unless its id is already
    present (duplicate prevention -- see module docstring). Returns True
    if it was actually inserted, False if it was already there. This is
    the ONE place duplicate suppression happens: two upstream references
    that would deterministically produce the identical (type, source,
    target) triple (and therefore the identical id) collapse into a
    single stored relationship rather than raising DuplicateIdError,
    which would otherwise be an implementation-detail failure mode for
    what is really "this relationship was already recorded"."""
    if registry.contains(relationship["id"]):
        return False
    registry.insert(relationship)
    return True


# --------------------------------------------------------------------------
# Per-relationship-type generators
#
# Each generator is a pure function: given the manager (read-only access
# to already-resolved registry items) and the target RelationshipRegistry
# to insert into, it walks exactly the deterministic source field its
# relationship type depends on (see module docstring's RESOLUTION
# STRATEGY) and inserts one relationship per resolved reference found.
# Never inspects any field outside that one deterministic source.
# --------------------------------------------------------------------------

def _generate_definition_concept_relationships(
    manager: RegistryManager, registry: RelationshipRegistry
) -> int:
    """Concept --has_definition--> Definition, from each Definition
    item's own Phase-B2-resolved `concept_id` (compiler/references.py).
    Never generated if concept_id is unresolved (None)."""
    count = 0
    for definition in manager.get("definitions").values():
        if not isinstance(definition, dict):
            continue
        def_id = definition.get("id")
        concept_id = definition.get("concept_id")
        if not def_id or not concept_id:
            continue
        rel = _make_relationship(
            rel_type="has_definition",
            source_type="concept", source_id=concept_id,
            target_type="definition", target_id=def_id,
        )
        if _insert_unique(registry, rel):
            count += 1
    return count


def _generate_glossary_concept_relationships(
    manager: RegistryManager, registry: RelationshipRegistry
) -> int:
    """Glossary Entry --explains--> Concept, and (the other direction of
    the same already-resolved reference) Concept --described_by-->
    Glossary Entry, from each Glossary Entry's own Phase-B2-resolved
    `concept_id`. Never generated if concept_id is unresolved (None)."""
    count = 0
    for entry in manager.get("glossary").values():
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        concept_id = entry.get("concept_id")
        if not entry_id or not concept_id:
            continue
        explains = _make_relationship(
            rel_type="explains",
            source_type="glossary_entry", source_id=entry_id,
            target_type="concept", target_id=concept_id,
        )
        if _insert_unique(registry, explains):
            count += 1
        described_by = _make_relationship(
            rel_type="described_by",
            source_type="concept", source_id=concept_id,
            target_type="glossary_entry", target_id=entry_id,
        )
        if _insert_unique(registry, described_by):
            count += 1
    return count


# Registry name -> (source_type label, relationship type) for the four
# "uses_concept / illustrates / teaches" object types whose Phase-B2
# `concept_ids` field is the ONLY deterministic source of this
# relationship, per module docstring's RESOLUTION STRATEGY. Every one of
# these is empty ([]) today (see compiler/references.py's own
# documentation of why), so these generators correctly produce zero
# relationships today -- not a bug, a deterministic "no source data yet"
# outcome that will start producing relationships automatically, with no
# code change here, the moment a future phase gives one of these types a
# genuinely deterministic concept_ids source.
_CONCEPT_IDS_RELATIONSHIP_TYPES: Dict[str, Dict[str, str]] = {
    "equations": {"source_type": "equation", "rel_type": "uses_concept"},
    "figures": {"source_type": "figure", "rel_type": "illustrates"},
    "diagrams": {"source_type": "diagram", "rel_type": "illustrates"},
    "tables": {"source_type": "table", "rel_type": "illustrates"},
    "activities": {"source_type": "activity", "rel_type": "teaches"},
}


def _generate_concept_ids_relationships(
    manager: RegistryManager, registry: RelationshipRegistry
) -> int:
    """Equation --uses_concept--> Concept, Figure/Diagram/Table
    --illustrates--> Concept, Activity --teaches--> Concept -- each from
    that item's own Phase-B2-resolved `concept_ids` list (compiler/
    references.py), and ONLY if that list is non-empty (i.e. only if
    deterministic concept_ids already exist -- see task spec). No
    generator here reads a title/caption/summary field; each reads
    exactly the one field compiler/references.py already deterministically
    resolved (or correctly left empty)."""
    count = 0
    for registry_name, spec in _CONCEPT_IDS_RELATIONSHIP_TYPES.items():
        source_type = spec["source_type"]
        rel_type = spec["rel_type"]
        for item in manager.get(registry_name).values():
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            concept_ids = item.get("concept_ids") or []
            if not item_id or not isinstance(concept_ids, list):
                continue
            for concept_id in concept_ids:
                if not concept_id:
                    continue
                rel = _make_relationship(
                    rel_type=rel_type,
                    source_type=source_type, source_id=item_id,
                    target_type="concept", target_id=concept_id,
                )
                if _insert_unique(registry, rel):
                    count += 1
    return count


def _generate_topic_concept_relationships(
    manager: RegistryManager,
    registry: RelationshipRegistry,
    topics: Iterable[Dict[str, Any]],
) -> int:
    """Topic --contains--> Concept, from each topic's own already-Phase-A
    -resolved `concepts` list (pipeline.py's topic-construction loop --
    frozen, see compiler/references.py's own "TOPIC -> CONCEPT
    RESOLUTION" note for why this is read directly rather than
    re-derived). Read-only over `topics`: never mutates a topic dict,
    exactly like compiler/references.py's own verify_topic_references()."""
    count = 0
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        topic_id = topic.get("id")
        concept_ids = topic.get("concepts") or []
        if not topic_id or not isinstance(concept_ids, list):
            continue
        for concept_id in concept_ids:
            if not concept_id:
                continue
            rel = _make_relationship(
                rel_type="contains",
                source_type="topic", source_id=topic_id,
                target_type="concept", target_id=concept_id,
            )
            if _insert_unique(registry, rel):
                count += 1
    return count


def _generate_appears_in_and_belongs_to_relationships(
    manager: RegistryManager, registry: RelationshipRegistry
) -> int:
    """Concept --appears_in--> Topic, Definition --belongs_to--> Topic,
    Glossary Entry --belongs_to--> Topic -- each from that item's own
    Phase-A-populated `topic_ids` list (modules/canonical.py::
    canonical_fields(), frozen, already present on every canonical object
    -- see pipeline.py's topic_ids= call sites for concepts/definitions/
    glossary). One relationship per (item, topic_id) pair in `topic_ids`,
    in that list's own order; an empty/missing topic_ids produces none."""
    count = 0
    specs = [
        ("concepts", "concept", "appears_in"),
        ("definitions", "definition", "belongs_to"),
        ("glossary", "glossary_entry", "belongs_to"),
    ]
    for registry_name, source_type, rel_type in specs:
        for item in manager.get(registry_name).values():
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            topic_ids = item.get("topic_ids") or []
            if not item_id or not isinstance(topic_ids, list):
                continue
            for topic_id in topic_ids:
                if not topic_id:
                    continue
                rel = _make_relationship(
                    rel_type=rel_type,
                    source_type=source_type, source_id=item_id,
                    target_type="topic", target_id=topic_id,
                )
                if _insert_unique(registry, rel):
                    count += 1
    return count


# --------------------------------------------------------------------------
# Top-level entry point -- pipeline.py's single integration point
# --------------------------------------------------------------------------

def resolve_relationships(
    manager: RegistryManager,
    *,
    topics: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Phase B3's single pipeline.py integration point (mirrors
    compiler.references.resolve_references()'s own shape). Must run
    AFTER resolve_references() (so concept_id/concept_ids/definition_ids/
    glossary_ids are already present to read) and BEFORE
    compiler_state.set_current_registry_manager() (see module docstring's
    PIPELINE INTEGRATION section and pipeline.py's own comment at the
    call site).

    Ensures `manager` owns a "relationships" RelationshipRegistry (create
    -if-absent, via ensure_relationship_registry() -- never replaces an
    existing one), then runs every deterministic relationship generator
    above against `manager`'s already-resolved registry items (and
    `topics`, if given, for the two Topic<->Concept relationship types --
    read-only, never mutated). Every relationship is inserted into that
    one registry; nothing is ever written onto an existing registry
    item's own dict, and nothing here is ever added to any Chapter JSON
    output (see module docstring's MOST IMPORTANT REQUIREMENT section).

    Returns a dict of generation statistics (by relationship type),
    primarily for logging/tests -- pipeline.py's own integration point
    only needs the side effect on `manager`, matching resolve_references()'s
    own "primarily for logging/tests" return-value note.

    Safe to call more than once: relationship ids are fully deterministic
    (see _make_relationship) and duplicate insertion is suppressed (see
    _insert_unique), so re-running this over an unchanged manager/topics
    never produces duplicate relationships or raises.
    """
    registry = ensure_relationship_registry(manager)

    stats: Dict[str, Any] = {"version": RELATIONSHIP_RESOLUTION_VERSION, "by_type": {}}

    _generate_definition_concept_relationships(manager, registry)
    _generate_glossary_concept_relationships(manager, registry)
    _generate_concept_ids_relationships(manager, registry)
    if topics is not None:
        _generate_topic_concept_relationships(manager, registry, topics)
    _generate_appears_in_and_belongs_to_relationships(manager, registry)

    # Recount straight off the final registry contents (rather than
    # threading per-generator counts through) so `stats["by_type"]`
    # always reflects exactly what is actually stored -- correct even if
    # a call collapsed some inserts as duplicates (see _insert_unique) or
    # this function is called more than once over the same manager.
    for rel_type in RELATIONSHIP_TYPES:
        stats["by_type"][rel_type] = sum(
            1 for item in registry.values() if item.get("type") == rel_type
        )

    stats["total"] = registry.size()
    return stats