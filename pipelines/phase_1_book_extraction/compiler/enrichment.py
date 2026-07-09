"""
compiler/enrichment.py — Phase B1b: canonical registry enrichment.

SCOPE (read this before touching anything else): Phase A, Phase B0, and
Phase B1 are frozen -- this module does not redesign
CanonicalRegistry/RegistryManager (compiler/registry.py,
compiler/registry_manager.py), does not add new registry types, and does
not touch Stage A-E extraction (modules/stage_a_geometry.py ...
modules/stage_e_validation.py) or pipeline.py's own object-assembly
logic. It ONLY adds additional, deterministically-derived educational
metadata fields onto items that already exist inside the twelve Phase B1
registries built by compiler/registries.py.

WHAT "DETERMINISTIC" MEANS HERE (see task spec's own Enrichment Rules):
every field below is computed from data the item itself already carries
(its own dict keys -- name/title/term, importance/difficulty,
semantic_description, *_type, provenance, extraction_confidence, ...),
using pure string/dict operations (strip, whitespace-collapse, casefold,
static lookup tables, numeric thresholding) -- never a model call, never
free-text generation, never a lookup against another registry entry or
another object. No cross-item relationship, dependency, prerequisite, or
graph edge is created anywhere in this module; see DO NOT IMPLEMENT in
the task notes for why that boundary is intentional. If an enrichment
field's value cannot be derived from information already present on the
item, that field is set to None (or an empty list, for list-shaped
fields) rather than fabricated -- never silently omitted, so downstream
consumers always see a stable field, just sometimes with no value yet.

WHERE THIS RUNS (see compiler/state.py's own ownership/lifecycle
docstring, which already anticipated this exact module and named it
"B1b enrichment"): pipeline.py calls enrich_registries() once per
chapter, immediately after populate_registries() finishes and before
compiler_state.set_current_registry_manager() hands the manager off as
this process's "current" one -- see pipeline.py's Phase B1 integration
point. Every registry item is a plain dict (the shape
modules/canonical.py::canonical_fields() + pipeline.py's
_attach_canonical() helper produce -- see compiler/registries.py's own
module docstring for why every one of the twelve registries is
dict-shaped today), so enrichment mutates each item's dict IN PLACE
(adds keys; never deletes or overwrites a key that already carries
real, non-placeholder extracted content) and then calls
CanonicalRegistry.update() to replace the registry's stored reference --
the explicit, intentional "replace an existing entry" operation B0's own
docstring describes, even though id/urn/name never change here. Because
registry items are the SAME dict objects pipeline.py's flat lists
(all_concepts, figures, tables, ...) hold -- populate_registries()
inserts a reference, never a copy -- enrichment fields become visible on
those objects too, and therefore flow into json_writer.assemble_chapter_json's
output. This is additive only (new keys on existing objects): every
existing key, value, id, and urn is left byte-for-byte unchanged, so
existing JSON output/consumers/schemas (which already use `extra="allow"`
throughout schemas/canonical_base.py and chapter_schema.py) remain fully
backward compatible.

FIELDS ADDED (documented individually below; also enumerated in this
module's ENRICHMENT_FIELDS constant for tests/tooling that want to
assert "did enrichment run" without hardcoding every field name):

  canonical_display_name  -- whitespace-normalized (but case-preserved)
                             version of whichever raw display field the
                             item has (name / title / term, checked in
                             that priority order). None if the item has
                             none of those keys, or the value is empty.

  normalized_name          -- casefolded + whitespace-normalized version
                             of the same raw display field. This is the
                             "deterministic normalization" the task
                             spec's Enrichment Rules explicitly allow
                             (distinct from "alias resolution", which is
                             explicitly out of scope). None under the
                             same conditions as canonical_display_name.

  aliases                  -- ONLY touched for items that already carry
                             an `aliases` list key (today: concept
                             records built in pipeline.py -- see
                             concept_registry's Single Owner Principle
                             loop, which already initializes
                             `"aliases": []`). If that list is empty,
                             this appends normalized_name to it, but
                             ONLY when normalized_name differs from the
                             raw name string (a case/whitespace variant
                             of the SAME string, not a new name) --
                             exactly "deterministic normalization",
                             never fuzzy/semantic alias resolution. If
                             aliases already has content (upstream
                             extraction populated it), or the item has
                             no `aliases` key at all, this is left
                             untouched.

  educational_role         -- a fixed, static category label looked up
                             from the item's own `object_type` (always
                             present -- every canonical object dict
                             already carries it via canonical_fields()/
                             _attach_canonical()) against
                             EDUCATIONAL_ROLE_BY_OBJECT_TYPE below. This
                             is categorical remapping of an already-known
                             field, not semantic inference over content:
                             the same object_type always maps to the
                             same role, for every chapter, forever.

  object_subtype            -- copies whichever of the item's own
                             existing "*_type" fields is present
                             (figure_type / table_type / activity_type /
                             box_type / warning_type -- see
                             modules/content_blocks.py and pipeline.py's
                             figure/diagram/table construction) into one
                             uniformly-named field, so a later phase can
                             read "this item's subtype" without knowing
                             which of five different key names a given
                             object_type happens to use. Pure aliasing of
                             already-extracted data; None if the item has
                             none of those keys.

  concept_type              -- always present, always None today. Concepts
                             (the one object_type this field is named
                             for) carry no deterministic sub-typing
                             signal anywhere in the data pipeline.py
                             already builds (they come from
                             semantic_processor.process_topic_semantics's
                             VLM output, not from any of
                             modules/recognizers/*, which is the only
                             place a comparable "*_type" signal exists
                             for other object types) -- so per the task
                             spec's "if a value cannot be determined
                             deterministically, leave it empty or null"
                             instruction, this stays null rather than
                             being guessed at. Reserved so a later phase
                             that DOES have a deterministic source for it
                             has a stable field to populate rather than
                             a schema migration.

  semantic_summary          -- RESERVED, always None as of B1b (see
                             REFINEMENT 2 below). This field is NOT a copy
                             of `semantic_description`: for figures/
                             diagrams/tables that key is currently always
                             ""  (populated only by a later, not-yet-built
                             semantic phase), but for activities/boxes/
                             warnings/notes/examples it already holds
                             real content -- raw extracted body text,
                             truncated to a fixed character count by
                             pipeline.py's `_finalize_blocks()`. Copying
                             that value verbatim into `semantic_summary`
                             would make the two fields byte-for-byte
                             identical whenever `semantic_description` is
                             non-empty, which is exactly the duplication
                             the task spec's Refinement 2 prohibits: a
                             "summary" field is supposed to be a distinct,
                             deliberately-produced abstraction, not an
                             alias for a raw-text field that already has
                             its own name and its own meaning. Producing
                             an actual abstraction (a shortened, reworded
                             restatement of the content) is not something
                             this module can do deterministically -- that
                             requires understanding meaning, i.e. semantic
                             inference or an AI/model call, both
                             explicitly out of scope for B1b (see
                             REFINEMENT 3 / this module's own "WHAT
                             DETERMINISTIC MEANS HERE" section above). So,
                             per the task spec's own instruction ("if a
                             deterministic compiler-generated abstraction
                             cannot yet be produced ... leave the field
                             empty ... or document that it is reserved
                             for a later milestone"), this field is left
                             None for every object type, unconditionally,
                             until a later phase can populate it with a
                             genuine abstraction rather than a raw-text
                             alias.

  visual_summary            -- for figure/diagram items only: a
                             deterministic, punctuation-joined
                             concatenation of the item's own `title` and
                             `caption` fields (both already extracted by
                             modules/layout_detector.py -- nothing new is
                             read or inferred), e.g. "Fig. 3 — Water
                             cycle diagram". None if both are empty, or
                             for any other object type.

  educational_importance    -- copies the item's own existing `importance`
                             field (concept/figure/diagram/table records
                             already carry one, currently a fixed
                             "medium" placeholder pending later semantic
                             work -- see pipeline.py) under this
                             standardized field name. None if the item has
                             no `importance` key.

  educational_difficulty    -- same as above, for the item's own existing
                             `difficulty` field (figure/diagram/table).

  extraction_quality         -- a small dict of deterministic, numeric/
                             boolean indicators computed purely from
                             fields the item already has -- never new
                             judgment about content quality:
                               confidence_band     : "high" | "medium" |
                                                      "low", by
                                                      thresholding the
                                                      item's own
                                                      extraction_confidence
                                                      (see
                                                      CONFIDENCE_BAND_THRESHOLDS)
                               is_vlm_extracted     : bool, from the
                                                      item's own
                                                      provenance.extraction_method
                               has_display_name     : bool(canonical_display_name)
                               has_semantic_summary : bool(semantic_summary)
                                                      -- always False as of
                                                      B1b.2, since
                                                      semantic_summary
                                                      itself is always None
                                                      (reserved; see that
                                                      field's own entry
                                                      above). Kept as a
                                                      real key (not
                                                      dropped) so a later
                                                      phase that DOES
                                                      populate
                                                      semantic_summary
                                                      doesn't also need a
                                                      schema migration for
                                                      this flag.
                               has_visual_summary   : bool(visual_summary)
                               has_source_page      : bool, from the
                                                      item's own
                                                      provenance.source_page

  registry_metadata          -- bookkeeping about the enrichment pass
                             itself, not about the educational object:
                               registry_name      : which CanonicalRegistry
                                                    this item lives in
                                                    (e.g. "concepts")
                               object_type        : copied from the item
                                                    for convenience
                               enrichment_version : ENRICHMENT_VERSION
                                                    (this module's own
                                                    version marker, bumped
                                                    if the enrichment
                                                    logic itself changes)
                               enriched_at        : ISO-8601 UTC
                                                    timestamp of this
                                                    enrichment pass --
                                                    the same
                                                    datetime.now(timezone.utc).isoformat()
                                                    idiom
                                                    modules/canonical.py's
                                                    canonical_fields()
                                                    already uses for
                                                    provenance.timestamp /
                                                    creation_metadata.created_at,
                                                    applied here to a new
                                                    place rather than a
                                                    new pattern.

NOT IN SCOPE HERE (see task's own DO NOT IMPLEMENT list -- enforced by
this module doing nothing but per-item, single-dict field derivation):
cross-link/reference resolution between different registry items,
Knowledge/Dependency/Prerequisite graphs, relationship generation,
concept/figure/equation linking, semantic inference, graph traversal,
registry validation/optimization, incremental compilation, caching. All
of those read or reason about MORE than one item (or about content
meaning) and belong to later, separate Phase B milestones.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .registry import CanonicalRegistry
from .registry_manager import RegistryManager

# --------------------------------------------------------------------------
# Static, deterministic lookup tables / constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of config.SCHEMA_VERSION,
# which versions the Chapter JSON schema, not this internal registry
# enrichment pass). Bump only if the enrichment logic in this file itself
# changes in a way a later phase might need to distinguish. Bumped to
# "B1b.2" for the Phase B1b final-refinement pass: `semantic_summary`
# no longer copies `semantic_description` verbatim (see _semantic_summary
# and REFINEMENT 2) -- items enriched under "B1b.1" may have a non-null
# semantic_summary that a "B1b.2" re-enrichment pass will now null out.
ENRICHMENT_VERSION = "B1b.2"

# object_type -> a fixed educational-role label. Every key here matches
# one of the twelve object_type strings pipeline.py's canonical_fields()/
# _attach_canonical() calls already use (see pipeline.py's
# object_type="..." call sites) -- this is a total, static mapping, never
# partial guesswork: an object_type not listed here (should never happen
# for the twelve current registries) maps to None rather than raising,
# so enrichment never crashes a chapter over an unrecognized type.
EDUCATIONAL_ROLE_BY_OBJECT_TYPE: Dict[str, str] = {
    "concept": "concept",
    "definition": "definition",
    "glossary_entry": "glossary_term",
    "figure": "visual_aid",
    "diagram": "visual_aid",
    "table": "data_reference",
    "equation": "formula",
    "activity": "practice_activity",
    "box": "callout",
    "warning": "caution",
    "note": "supplementary_note",
    "example": "worked_example",
}

# Object types for which `visual_summary` is meaningful (visual, on-page
# regions with a title/caption pair) -- deliberately excludes "table"
# even though tables also have a `title` key, since a table's content is
# its rows/columns, not a depicted image; table enrichment instead relies
# on semantic_summary/educational_* fields like every other type.
_VISUAL_SUMMARY_OBJECT_TYPES = frozenset({"figure", "diagram"})

# Raw display-name fields, checked in this fixed priority order. Concept
# records carry "name"; Figure/Diagram/Table/Activity/Box/Example carry
# "title"; Definition/Glossary carry "term". At most one of the three is
# ever present on a given item (see compiler/registries.py's own module
# docstring on why name_of is left at its dict.get("name") default), but
# checking all three keeps this helper correct even if that changes.
_DISPLAY_NAME_KEYS = ("name", "title", "term")

# Existing per-type "*_type" fields this module aliases into the single
# `object_subtype` field, checked in this fixed order. See
# modules/content_blocks.py (activity_type/box_type/warning_type) and
# pipeline.py's figure/diagram/table dict literals (figure_type/table_type).
_SUBTYPE_KEYS = ("figure_type", "table_type", "activity_type", "box_type", "warning_type")

# Numeric thresholds for extraction_quality's confidence_band. Purely a
# deterministic bucketing of the item's own extraction_confidence /
# provenance.confidence float -- never a judgment about the underlying
# content. >=0.75 -> high, >=0.4 -> medium, else low (matches the
# existing confidence values pipeline.py already assigns per stage: 0.5
# for most deterministic layout-detector extraction, 0.6 for
# content_blocks detections, so the default "medium" band is where most
# current Phase A/B0/B1 output already sits).
CONFIDENCE_BAND_THRESHOLDS = {"high": 0.75, "medium": 0.4}

# Public, ordered list of every top-level field name enrich_item() adds
# (or ensures exists) -- exposed so tests/tooling can iterate without
# hardcoding their own copy of this list.
ENRICHMENT_FIELDS: List[str] = [
    "canonical_display_name",
    "normalized_name",
    "aliases",
    "educational_role",
    "object_subtype",
    "concept_type",
    "semantic_summary",
    "visual_summary",
    "educational_importance",
    "educational_difficulty",
    "extraction_quality",
    "registry_metadata",
]


# --------------------------------------------------------------------------
# Pure helpers -- each reads only the single `item` dict passed in.
# --------------------------------------------------------------------------

def _normalize_whitespace(value: str) -> str:
    """Collapses any run of whitespace to a single space and strips the
    ends. Pure string mechanics -- no case change, no content judgment."""
    return " ".join(value.split())


def _raw_display_name(item: Dict[str, Any]) -> Optional[str]:
    """Returns the item's own name/title/term value (first non-empty
    match, in that fixed priority order), or None if it has none."""
    for key in _DISPLAY_NAME_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _canonical_display_name(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    normalized = _normalize_whitespace(raw)
    return normalized or None


def _normalized_name(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    normalized = _normalize_whitespace(raw).casefold()
    return normalized or None


def _object_subtype(item: Dict[str, Any]) -> Optional[str]:
    for key in _SUBTYPE_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _educational_role(item: Dict[str, Any]) -> Optional[str]:
    object_type = item.get("object_type")
    if not isinstance(object_type, str):
        return None
    return EDUCATIONAL_ROLE_BY_OBJECT_TYPE.get(object_type)


def _semantic_summary(item: Dict[str, Any]) -> Optional[str]:
    """RESERVED for a later milestone -- see module docstring's
    `semantic_summary` entry (REFINEMENT 2). Deliberately does NOT read
    `item["semantic_description"]`: doing so would make this field a
    byte-for-byte duplicate of that raw-text field for every object type
    that already populates it (activities/boxes/warnings/notes/examples),
    which is the exact duplication the task spec prohibits. No
    deterministic way to derive a genuine abstraction exists yet, so this
    always returns None rather than aliasing another field under a new
    name."""
    return None


def _visual_summary(item: Dict[str, Any]) -> Optional[str]:
    if item.get("object_type") not in _VISUAL_SUMMARY_OBJECT_TYPES:
        return None
    title = item.get("title")
    caption = item.get("caption")
    parts = [
        _normalize_whitespace(v)
        for v in (title, caption)
        if isinstance(v, str) and v.strip()
    ]
    if not parts:
        return None
    return " — ".join(parts)


def _educational_importance(item: Dict[str, Any]) -> Optional[str]:
    value = item.get("importance")
    return value if isinstance(value, str) and value else None


def _educational_difficulty(item: Dict[str, Any]) -> Optional[str]:
    value = item.get("difficulty")
    return value if isinstance(value, str) and value else None


def _confidence_band(confidence: Any) -> Optional[str]:
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return None
    if c >= CONFIDENCE_BAND_THRESHOLDS["high"]:
        return "high"
    if c >= CONFIDENCE_BAND_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _aliases(item: Dict[str, Any], normalized_name: Optional[str]) -> Optional[List[str]]:
    """Only touches items that already carry an `aliases` list (today:
    concept records -- see module docstring). Returns None (meaning
    "leave untouched") for items with no `aliases` key at all, so
    enrich_item() knows not to add a new key where none of the existing
    twelve object types has ever had one."""
    if "aliases" not in item:
        return None
    existing = item.get("aliases")
    if not isinstance(existing, list):
        existing = []
    if existing:
        # Upstream extraction already populated aliases -- deterministic
        # normalization only adds a variant when the field is still
        # empty; real extracted aliases are never touched or reordered.
        return list(existing)
    raw_name = item.get("name")
    if isinstance(raw_name, str) and normalized_name and normalized_name != raw_name:
        return [normalized_name]
    return list(existing)


# --------------------------------------------------------------------------
# Per-item enrichment
# --------------------------------------------------------------------------

def compute_enrichment(item: Dict[str, Any], *, registry_name: str) -> Dict[str, Any]:
    """Pure function: given one registry item dict, returns the dict of
    enrichment fields to merge into it (see module docstring for the
    full field list and derivation rules). Does not mutate `item`. Never
    raises on missing/odd-shaped fields -- every helper above degrades to
    None/[] rather than erroring, since a chapter's enrichment pass must
    never fail a whole compile over one malformed item.
    """
    raw_name = _raw_display_name(item)
    canonical_display_name = _canonical_display_name(raw_name)
    normalized_name = _normalized_name(raw_name)
    semantic_summary = _semantic_summary(item)
    visual_summary = _visual_summary(item)

    provenance = item.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    confidence = item.get("extraction_confidence", provenance.get("confidence"))

    enrichment: Dict[str, Any] = {
        "canonical_display_name": canonical_display_name,
        "normalized_name": normalized_name,
        "educational_role": _educational_role(item),
        "object_subtype": _object_subtype(item),
        # Reserved, always-null placeholder -- see module docstring for
        # why no deterministic source exists yet for this field.
        "concept_type": None,
        "semantic_summary": semantic_summary,
        "visual_summary": visual_summary,
        "educational_importance": _educational_importance(item),
        "educational_difficulty": _educational_difficulty(item),
        "extraction_quality": {
            "confidence_band": _confidence_band(confidence),
            "is_vlm_extracted": provenance.get("extraction_method") == "vlm",
            "has_display_name": bool(canonical_display_name),
            "has_semantic_summary": bool(semantic_summary),
            "has_visual_summary": bool(visual_summary),
            "has_source_page": provenance.get("source_page") is not None,
        },
        "registry_metadata": {
            "registry_name": registry_name,
            "object_type": item.get("object_type"),
            "enrichment_version": ENRICHMENT_VERSION,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    aliases = _aliases(item, normalized_name)
    if aliases is not None:
        enrichment["aliases"] = aliases

    return enrichment


def enrich_item(item: Dict[str, Any], *, registry_name: str) -> Dict[str, Any]:
    """Mutates `item` IN PLACE, adding every enrichment field
    compute_enrichment() derives for it, and returns the same `item`
    (for convenient chaining/inserting into a registry). Only ever adds
    or replaces the enrichment-owned keys listed in ENRICHMENT_FIELDS --
    every other existing key on `item` (id, urn, name/title/term,
    provenance, ...) is left completely untouched.

    Idempotent for every field except registry_metadata.enriched_at
    (a timestamp, by definition -- matches the same non-idempotent-
    timestamp behavior modules/canonical.py's canonical_fields() already
    has for provenance.timestamp / creation_metadata.created_at, so this
    isn't a new pattern). Running this twice on the same item leaves
    every other field byte-for-byte identical.
    """
    if not isinstance(item, dict):
        # Registries are dict-shaped for every current Phase B1 object
        # (see compiler/registries.py's module docstring) -- a non-dict
        # item is out of scope for this phase's enrichment and is left
        # alone rather than guessed at or raised on.
        return item
    item.update(compute_enrichment(item, registry_name=registry_name))
    return item


# --------------------------------------------------------------------------
# Registry-level / manager-level enrichment
# --------------------------------------------------------------------------

def enrich_registry(registry: CanonicalRegistry) -> int:
    """Enriches every item currently in `registry`, in the registry's own
    deterministic insertion order. Each enriched item is written back via
    CanonicalRegistry.update() -- the existing B0 "replace this id's
    entry" operation -- rather than mutating _items directly, so this
    module never reaches past CanonicalRegistry's own public API despite
    living in the same package. Returns the number of items enriched.

    Safe to call more than once (e.g. a re-run over an already-enriched
    registry): every field is recomputed fresh each time (see enrich_item's
    idempotency note), and update() accepts replacing an item with itself.
    """
    count = 0
    for item in registry.values():
        enrich_item(item, registry_name=registry.name)
        registry.update(item)
        count += 1
    return count


def enrich_registries(manager: RegistryManager) -> Dict[str, int]:
    """Enriches every registry `manager` owns, in registration order.
    Returns {registry_name: items_enriched}, primarily for logging/tests
    -- pipeline.py's own integration point (see this module's docstring)
    only needs the side effect, not the return value.
    """
    return {registry.name: enrich_registry(registry) for registry in manager}