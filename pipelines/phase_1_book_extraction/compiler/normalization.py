"""
compiler/normalization.py — Phase B1c: Canonical Normalization Layer.

SCOPE (read this before touching anything else): Phase A, Phase B0,
Phase B1, and Phase B1b are frozen -- this module does not redesign
CanonicalRegistry/RegistryManager (compiler/registry.py,
compiler/registry_manager.py), does not add new registry types, does not
touch Stage A-E extraction, and does not touch compiler/enrichment.py's
own fields (canonical_display_name, normalized_name, educational_role,
...). It ONLY adds a second, additive layer of deterministic normalization
metadata on top of what B1b's enrichment pass already put on each item.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
linking phase and not a graph phase. The `canonical_lookup_key` this
module computes is internal compiler metadata for a later phase's
deterministic dict-key lookups -- it is not a reference, an edge, or a
resolved relationship to any other registry item. No two items are ever
compared, merged, or linked to each other anywhere in this module; every
function here reads exactly one item and returns data derived only from
that item's own existing fields.

WHY THIS IS A SEPARATE LAYER FROM B1b's ENRICHMENT (not an extension of
it): B1b's `_canonical_display_name`/`_normalized_name` (compiler/
enrichment.py) already do "deterministic normalization" in the sense the
B1b task spec meant -- whitespace collapse + casefold, nothing more. This
phase's task spec asks for a strictly deeper kind of normalization (full
Unicode normalization, smart-quote/dash canonicalization, invisible-
character stripping) whose entire purpose is producing a stable *lookup
key*, not a *display* string -- display strings must stay human-
readable (a curly apostrophe in "Newton's Third Law" should still look
like a curly apostrophe when shown to a person), so folding it into an
ASCII straight quote belongs only in the lookup-key layer, never in
canonical_display_name. Keeping these as two distinct fields, produced by
two distinct passes, means B1b's frozen behavior is untouched (its tests
keep passing unmodified) while B1c adds exactly the new capability its
own task spec describes.

WHERE THIS RUNS (mirrors compiler/enrichment.py's own integration
pattern): pipeline.py calls normalize_registries() once per chapter,
immediately after enrich_registries() finishes and before
compiler_state.set_current_registry_manager() hands the manager off as
this process's "current" one. Every registry item is a plain dict (see
compiler/enrichment.py's module docstring for why), so normalization
mutates each item's dict IN PLACE (adds keys; never deletes or overwrites
a key that already carries real content -- including every key B1b's
enrichment pass already added) and then calls
CanonicalRegistry.update() to replace the registry's stored reference,
exactly like B1b's own enrich_registry() does. Because registry items are
the SAME dict objects pipeline.py's flat lists hold (see
compiler/enrichment.py's and pipeline.py's own documentation of this,
verified safe/deterministic during the B1b final-refinement pass),
normalization fields become visible on those objects too, and therefore
flow into json_writer.assemble_chapter_json's output -- additive only,
so existing JSON output/consumers/schemas (extra="allow" throughout)
remain fully backward compatible.

FIELDS ADDED (also enumerated in NORMALIZATION_FIELDS for tests/tooling):

  canonical_lookup_key   -- a deterministic, deeply-normalized string
                            derived from the item's own raw display name
                            (name/title/term -- the same
                            compiler.enrichment._raw_display_name this
                            module reuses rather than re-deriving, per
                            the task's own "avoid duplicated
                            normalization logic" instruction), suitable
                            for a later phase's exact-match dict lookups.
                            Pipeline: normalize_text() (Unicode NFKC,
                            quote/dash canonicalization, invisible-
                            character stripping, whitespace collapse) ->
                            casefold() -> strip trailing/leading ASCII
                            punctuation. None if the item has no raw
                            display name (mirrors
                            canonical_display_name's own None case).
                            THIS IS INTERNAL COMPILER METADATA, NOT A
                            GRAPH LINK: it is not resolved against any
                            other item, registry, or index anywhere in
                            this module.

  canonical_aliases      -- ONLY added for items that already carry an
                            `aliases` list key (today: concept records --
                            same condition compiler.enrichment._aliases
                            already checks). Each existing alias string
                            is passed through normalize_text() ALONE
                            (list length and order are always preserved
                            1:1 with the source `aliases` list) -- no
                            alias is invented, dropped, deduplicated, or
                            resolved against another concept's aliases.
                            None if the item has no `aliases` key.

  normalization           -- bookkeeping about this normalization pass
                            itself (mirrors enrichment's own
                            registry_metadata field):
                              version          : NORMALIZATION_VERSION
                              status           : "normalized" if a
                                                 canonical_lookup_key was
                                                 produced, else
                                                 "skipped_no_display_name"
                              normalized_fields: which of
                                                 canonical_lookup_key /
                                                 canonical_aliases this
                                                 pass actually populated
                                                 for this item (a subset
                                                 of NORMALIZATION_FIELDS)
                              normalized_at    : ISO-8601 UTC timestamp,
                                                 the same
                                                 datetime.now(timezone.utc).isoformat()
                                                 idiom compiler/enrichment.py
                                                 and modules/canonical.py
                                                 already use elsewhere

NOT IN SCOPE HERE (see task's own DO NOT IMPLEMENT list): concept
merging, alias resolution (deciding two different strings name the same
concept), cross-linking, reference resolution, Knowledge/Dependency/
Prerequisite graphs, relationship generation, semantic inference, graph
traversal, registry validation, compiler optimization, incremental
compilation. All of those read or reason about MORE than one item (or
about content meaning/identity across items) and belong to later,
separate milestones. This module's canonical_lookup_key makes such a
future phase POSSIBLE (a stable key to look items up by) without itself
performing any lookup, comparison, or resolution.

REGISTRY CONSISTENCY / ORDERING (task's Refinement 5 -- "normalize
ordering of deterministic collections"): CanonicalRegistry and
RegistryManager already guarantee deterministic (insertion-order)
iteration everywhere (see compiler/registry.py's and
compiler/registry_manager.py's own design-notes docstrings, reverified
during the B1b final-refinement pass) -- there is no hash-derived or
otherwise nondeterministic ordering anywhere in this compiler for this
module to fix. This module does not reorder any existing list-shaped
field (e.g. `aliases`, `concepts`): canonical_aliases is a 1:1,
order-preserving transform of the existing `aliases` list, and reordering
it would be indistinguishable from silently renaming which alias is
"first" -- exactly the kind of invented structure the task's DO NOT
IMPLEMENT list rules out. "Normalizing" ordering here means verifying
determinism already holds, not introducing a new sort.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .registry import CanonicalRegistry
from .registry_manager import RegistryManager
from .enrichment import _raw_display_name

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of ENRICHMENT_VERSION,
# which versions B1b's separate enrichment pass, and of
# config.SCHEMA_VERSION, which versions the Chapter JSON schema). Bump
# only if the normalization logic in this file itself changes in a way a
# later phase might need to distinguish.
NORMALIZATION_VERSION = "B1c.1"

# Public, ordered list of every top-level field name normalize_item() adds
# (or ensures exists) -- exposed so tests/tooling can iterate without
# hardcoding their own copy of this list.
NORMALIZATION_FIELDS: List[str] = [
    "canonical_lookup_key",
    "canonical_aliases",
    "normalization",
]

# Deterministic, static translation table: "smart"/typographic
# punctuation -> its plain-ASCII equivalent. Purely a fixed character
# mapping -- never a judgment about content, never locale-dependent.
# Covers the quote/dash variants a PDF text layer or OCR pass commonly
# produces (see modules/pdf_parser.py / modules/ocr_engine.py) that
# Unicode NFKC normalization alone does not fold away.
_PUNCTUATION_TRANSLATION = str.maketrans({
    "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK (includes typographic apostrophe)
    "\u201a": "'",  # SINGLE LOW-9 QUOTATION MARK
    "\u201b": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
    "\u201e": '"',  # DOUBLE LOW-9 QUOTATION MARK
    "\u201f": '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    "\u2013": "-",  # EN DASH
    "\u2014": "-",  # EM DASH
    "\u2212": "-",  # MINUS SIGN
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NON-BREAKING HYPHEN
    "\u2012": "-",  # FIGURE DASH
})

# Invisible / zero-width characters a PDF/OCR text layer can leave behind
# (soft hyphen, zero-width space/joiner/non-joiner, BOM, word joiner) --
# stripped entirely rather than translated to anything, since they carry
# no visible or semantic content of their own.
_INVISIBLE_CHARS = (
    "\u00ad"  # SOFT HYPHEN
    "\u200b"  # ZERO WIDTH SPACE
    "\u200c"  # ZERO WIDTH NON-JOINER
    "\u200d"  # ZERO WIDTH JOINER
    "\u2060"  # WORD JOINER
    "\ufeff"  # ZERO WIDTH NO-BREAK SPACE / BOM
)
_INVISIBLE_CHARS_TABLE = {ord(c): None for c in _INVISIBLE_CHARS}

# ASCII punctuation this module strips from the START/END of a lookup key
# only (never from the middle -- "co-operative" must not become
# "cooperative"). Deterministic, fixed set.
_EDGE_STRIP_CHARS = ".,;:!?'\"()[]{}<>"


# --------------------------------------------------------------------------
# Pure text-normalization primitives
# --------------------------------------------------------------------------

def normalize_text(value: str) -> str:
    """Deep, deterministic text normalization -- see module docstring's
    `canonical_lookup_key` entry for the full pipeline. Pure string/
    Unicode-table operations only; never a judgment about meaning.

    Order (fixed, always applied in this sequence):
      1. Unicode NFKC normalization (canonicalizes compatibility forms --
         e.g. full-width digits, ligatures -- to their standard form).
      2. Smart-quote/dash -> ASCII translation (_PUNCTUATION_TRANSLATION).
      3. Invisible/zero-width character removal (_INVISIBLE_CHARS_TABLE).
      4. Whitespace collapse (any run of whitespace -> single space) +
         strip.

    Returns "" for a non-str or already-empty input rather than raising
    -- callers that need "no value" semantics use None, not this
    function's return value, to represent that (see canonical_lookup_key
    below).
    """
    if not isinstance(value, str) or not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(_PUNCTUATION_TRANSLATION)
    normalized = normalized.translate(_INVISIBLE_CHARS_TABLE)
    normalized = " ".join(normalized.split())
    return normalized


def canonical_lookup_key(value: Optional[str]) -> Optional[str]:
    """Builds the deterministic lookup key described in the module
    docstring: normalize_text() -> casefold() -> strip a fixed set of
    ASCII punctuation from the edges only. Returns None for a missing/
    empty/whitespace-only input (never an empty string), so downstream
    code can use `if item.get("canonical_lookup_key"):` the same way it
    already does for canonical_display_name.
    """
    normalized = normalize_text(value) if isinstance(value, str) else ""
    if not normalized:
        return None
    key = normalized.casefold().strip(_EDGE_STRIP_CHARS)
    return key or None


# --------------------------------------------------------------------------
# Per-item normalization
# --------------------------------------------------------------------------

def _canonical_aliases(item: Dict[str, Any]) -> Optional[List[str]]:
    """Only touches items that already carry an `aliases` list (today:
    concept records -- same condition compiler.enrichment._aliases
    checks). Returns None (meaning "leave untouched, no field added") for
    items with no `aliases` key at all. Every existing alias string is
    passed through normalize_text() alone -- length and order are always
    preserved 1:1 with the source list; nothing is invented, dropped, or
    deduplicated."""
    if "aliases" not in item:
        return None
    existing = item.get("aliases")
    if not isinstance(existing, list):
        return []
    return [
        normalize_text(alias) if isinstance(alias, str) else alias
        for alias in existing
    ]


def compute_normalization(item: Dict[str, Any]) -> Dict[str, Any]:
    """Pure function: given one registry item dict, returns the dict of
    normalization fields to merge into it (see module docstring for the
    full field list and derivation rules). Does not mutate `item`. Never
    raises on missing/odd-shaped fields -- degrades to None rather than
    erroring, since a chapter's normalization pass must never fail a
    whole compile over one malformed item.
    """
    raw_name = _raw_display_name(item)
    lookup_key = canonical_lookup_key(raw_name)
    canonical_aliases = _canonical_aliases(item)

    normalized_fields: List[str] = []
    if lookup_key is not None:
        normalized_fields.append("canonical_lookup_key")
    if canonical_aliases is not None:
        normalized_fields.append("canonical_aliases")

    result: Dict[str, Any] = {
        "canonical_lookup_key": lookup_key,
        "normalization": {
            "version": NORMALIZATION_VERSION,
            "status": "normalized" if lookup_key is not None else "skipped_no_display_name",
            "normalized_fields": normalized_fields,
            "normalized_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    if canonical_aliases is not None:
        result["canonical_aliases"] = canonical_aliases
    return result


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Mutates `item` IN PLACE, adding every normalization field
    compute_normalization() derives for it, and returns the same `item`
    (for convenient chaining/inserting into a registry). Only ever adds
    or replaces the normalization-owned keys in NORMALIZATION_FIELDS --
    every other existing key on `item` (id, urn, name/title/term,
    every B1b enrichment field, ...) is left completely untouched.

    Idempotent for every field except normalization.normalized_at (a
    timestamp, by definition -- matches enrich_item()'s and
    canonical_fields()'s same non-idempotent-timestamp behavior).
    """
    if not isinstance(item, dict):
        return item
    item.update(compute_normalization(item))
    return item


# --------------------------------------------------------------------------
# Registry-level / manager-level normalization
# --------------------------------------------------------------------------

def normalize_registry(registry: CanonicalRegistry) -> int:
    """Normalizes every item currently in `registry`, in the registry's
    own deterministic insertion order. Each normalized item is written
    back via CanonicalRegistry.update() -- mirrors
    compiler.enrichment.enrich_registry() exactly. Returns the number of
    items normalized.

    Safe to call more than once: every field is recomputed fresh each
    time (see normalize_item's idempotency note), and update() accepts
    replacing an item with itself.
    """
    count = 0
    for item in registry.values():
        normalize_item(item)
        registry.update(item)
        count += 1
    return count


def normalize_registries(manager: RegistryManager) -> Dict[str, int]:
    """Normalizes every registry `manager` owns, in registration order.
    Returns {registry_name: items_normalized}, primarily for
    logging/tests -- pipeline.py's own integration point only needs the
    side effect, not the return value.
    """
    return {registry.name: normalize_registry(registry) for registry in manager}