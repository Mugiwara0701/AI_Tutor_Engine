"""
compiler/registries.py — Phase B1: concrete canonical registries.

This module is the thin, type-specific layer Phase B0's module docstring
(compiler/registry.py) already anticipated: one CanonicalRegistry
subclass per canonical educational object type that pipeline.py builds
today (see modules/canonical.py::canonical_fields() call sites), plus two
small pieces of glue --

  * `create_registry_manager()` -- builds one RegistryManager for a
    compiler run and registers one instance of every concrete registry
    below under a fixed, predictable name.
  * `populate_registries()` -- given the already-finalized per-chapter
    object lists pipeline.py builds (the same lists it passes into
    json_writer.assemble_chapter_json today), inserts every item into
    its matching registry.

SCOPE (Phase B1 only -- see task notes): this module only POPULATES
registries from data pipeline.py already produces. It does not add
aliases, semantic/visual summaries, Bloom or other educational metadata,
concept normalization, relationship/cross-link resolution, or any
Knowledge-Graph/prerequisite/dependency graph -- those are later Phase B
milestones. Nothing here changes what pipeline.py writes into a
chapter's JSON: registries are an internal compiler representation only
(see populate_registries()'s docstring and pipeline.py's integration
point for why).

WHY ONE SUBCLASS PER TYPE INSTEAD OF ONE SHARED FACTORY: a bare
`CanonicalRegistry(name="concepts")` would already work (CanonicalRegistry
is fully generic), but a named subclass per educational-object type (a)
gives Phase B2+ a stable, importable symbol (`ConceptRegistry`,
`FigureRegistry`, ...) to type-hint against and extend later (e.g. adding
alias resolution to ConceptRegistry specifically, in a later phase,
without touching the others), and (b) matches the task's explicit
"implement concrete registries for every existing canonical educational
object" instruction. Every subclass below adds nothing but its own fixed
`name=` -- no duplicated insert/lookup/serialize logic, per B0's own
"avoid duplicated registry code" design goal.

WHY DEFAULT id_of/urn_of/name_of EVERYWHERE (no per-type extractors):
every canonical object dict pipeline.py builds already has "id" and
"urn" keys, unconditionally, via canonical.canonical_fields() (merged in
directly for definitions/concepts/glossary, or via the
pipeline._attach_canonical() helper for every other type) -- so
CanonicalRegistry's default id_of/urn_of (dict.get("id") / dict.get(
"urn")) already work for all twelve types with no customization.

`name_of` is more subtle and is deliberately LEFT AT THE DEFAULT
(dict.get("name")) for every registry below, including the ones whose
objects have a human-readable label under a different key ("term" for
Definition/Glossary, "title" for Figure/Diagram/Table/Activity/Box/
Example). This is intentional, not an oversight:

  - Only the concept dicts pipeline.py builds actually carry a "name"
    key (concept_registry's Single-Owner-Principle loop in pipeline.py
    already deduplicates by case-insensitive name before a concept ever
    reaches this module), so ConceptRegistry's name-index is safe and
    matches existing pre-B1 dedup semantics exactly.
  - None of the other eleven object dicts has a "name" key, so their
    default name_of already returns None for every item -- CanonicalRegistry
    simply skips name-indexing for them (see registry.py's `if norm_name:`
    guards), with no code needed here to suppress it.
  - Explicitly wiring name_of to e.g. "term" for DefinitionRegistry or
    "title" for FigureRegistry would be actively wrong: the same
    definition term legitimately recurs on different pages within one
    chapter (each such occurrence is today a distinct, valid record --
    see content_blocks.detect_definition_terms), and two different
    figures/tables/diagrams can legitimately share an identical or empty
    caption/title. Indexing either by that key would make insert() raise
    DuplicateNameError on perfectly legitimate, pre-existing pipeline
    output -- a real behavior change and regression, not "additive"
    registry population. Concept is the one type where pipeline.py's own
    existing logic already guarantees name-uniqueness before insertion,
    which is exactly why it alone gets a meaningful name index for free.

Duplicate detection *by id/urn* -- via insert()'s existing B0 behavior --
still applies to every registry, and is exactly what "Duplicate
protection should use the B0 infrastructure" (task spec) means: it is
not skipped for any of the twelve types.

ARCHITECTURAL DECISION LOG (B1 refinement pass): reviewed whether these
twelve subclasses -- each of which currently does nothing but fix
`name=` in its constructor -- earn their keep versus one generic
`CanonicalRegistry(name=...)` call per type (which would work identically
today; CanonicalRegistry is fully generic and does not require a
subclass). Decision: KEEP them, for three reasons specific to this
project's own roadmap rather than abstraction for its own sake --

  1. Stable extension points, not speculative ones: the task's own
     later-phase names (B1b enrichment, B2 relationship generation, B3
     cross-link resolution, Phase C Knowledge Graph construction) are
     each documented elsewhere in this codebase as wanting type-specific
     behavior eventually -- e.g. only ConceptRegistry will ever need
     alias resolution, only FigureRegistry/DiagramRegistry/TableRegistry
     will ever need "visual objects on this page" lookups, only
     EquationRegistry will ever need LaTeX-normalized lookup. A plain
     dict of `{"concepts": CanonicalRegistry(...), ...}` would force that
     future behavior to live in free functions keyed by string name
     (`add_alias(registry_manager.get("concepts"), ...)`), reintroducing
     exactly the kind of stringly-typed, easy-to-typo indirection B0's
     own docstring says CanonicalRegistry was built to replace. A named
     class per type is where that future behavior will actually attach,
     with no migration needed when it arrives.
  2. isinstance()-checkable identity: create_registry_manager() (below)
     can and does assert `isinstance(manager.get("concepts"), ConceptRegistry)`
     in tests -- a plain factory-built CanonicalRegistry offers no such
     type-level guarantee that "the concepts slot really is a concepts
     registry," only that it happens to be named "concepts" today.
  3. Negligible cost today: each subclass is a two-line `__init__`
     override plus a docstring -- this is not "unnecessary abstraction"
     in the sense of added indirection, extra call layers, or
     configuration surface; it is the minimum unit (a class statement)
     needed to have twelve distinct, independently-extensible names at
     all. Collapsing them into one shared factory function would save
     those two lines per type at the cost of the three points above, for
     a project whose own roadmap already names five future phases likely
     to want exactly this kind of per-type extension point.

No code changed as a result of this review -- the twelve classes are
kept exactly as originally implemented; this entry exists so the
decision (and its reasoning) is recorded rather than re-litigated at the
next phase boundary.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .registry import CanonicalRegistry
from .registry_manager import RegistryManager

# --------------------------------------------------------------------------
# Concrete registries
#
# Each is a CanonicalRegistry, differing only in `name`. No overridden
# behavior, no duplicated insert/lookup/serialize code -- see module
# docstring for why id_of/urn_of/name_of are all left at their B0
# defaults.
# --------------------------------------------------------------------------


class ConceptRegistry(CanonicalRegistry):
    """One canonical record per distinct concept name (see A4/Single Owner
    Principle in pipeline.py -- concepts are already deduplicated by
    case-insensitive name before reaching this registry, so name-based
    lookup here, unlike the other eleven registries, is meaningful)."""

    def __init__(self) -> None:
        super().__init__(name="concepts")


class DefinitionRegistry(CanonicalRegistry):
    """One record per (term, page) definition occurrence -- see
    modules/content_blocks.py::detect_definition_terms. Not name-indexed:
    the same term legitimately recurs across pages within a chapter."""

    def __init__(self) -> None:
        super().__init__(name="definitions")


class GlossaryRegistry(CanonicalRegistry):
    """One record per (term, topic) glossary occurrence -- see
    semantic_processor.process_topic_semantics's glossary_terms output."""

    def __init__(self) -> None:
        super().__init__(name="glossary")


class EquationRegistry(CanonicalRegistry):
    """One record per detected equation region."""

    def __init__(self) -> None:
        super().__init__(name="equations")


class FigureRegistry(CanonicalRegistry):
    """One record per detected figure region."""

    def __init__(self) -> None:
        super().__init__(name="figures")


class DiagramRegistry(CanonicalRegistry):
    """One record per detected diagram region."""

    def __init__(self) -> None:
        super().__init__(name="diagrams")


class TableRegistry(CanonicalRegistry):
    """One record per detected table region."""

    def __init__(self) -> None:
        super().__init__(name="tables")


class ExampleRegistry(CanonicalRegistry):
    """One record per detected worked example."""

    def __init__(self) -> None:
        super().__init__(name="examples")


class ActivityRegistry(CanonicalRegistry):
    """One record per detected activity block."""

    def __init__(self) -> None:
        super().__init__(name="activities")


class BoxRegistry(CanonicalRegistry):
    """One record per detected box/callout block."""

    def __init__(self) -> None:
        super().__init__(name="boxes")


class NoteRegistry(CanonicalRegistry):
    """One record per detected note block."""

    def __init__(self) -> None:
        super().__init__(name="notes")


class WarningRegistry(CanonicalRegistry):
    """One record per detected warning block."""

    def __init__(self) -> None:
        super().__init__(name="warnings")


# Registry-name -> constructor, in the fixed, deterministic order every
# RegistryManager built by create_registry_manager() registers them in.
# This order (not alphabetical) mirrors the order these object types are
# first built in pipeline.py, purely so RegistryManager.names() /
# serialize() output is stable and easy to eyeball against pipeline.py.
_REGISTRY_CLASSES: "Dict[str, type]" = {
    "definitions": DefinitionRegistry,
    "concepts": ConceptRegistry,
    "glossary": GlossaryRegistry,
    "figures": FigureRegistry,
    "diagrams": DiagramRegistry,
    "tables": TableRegistry,
    "equations": EquationRegistry,
    "activities": ActivityRegistry,
    "boxes": BoxRegistry,
    "warnings": WarningRegistry,
    "notes": NoteRegistry,
    "examples": ExampleRegistry,
}

# Public, ordered list of every registry name create_registry_manager()
# registers -- exposed so callers/tests can iterate without hardcoding
# their own copy of _REGISTRY_CLASSES's keys.
REGISTRY_NAMES: List[str] = list(_REGISTRY_CLASSES.keys())


def create_registry_manager() -> RegistryManager:
    """Builds one RegistryManager for a single compiler run (one chapter,
    matching pipeline.py's per-chapter processing granularity) and
    registers one fresh instance of every concrete registry above under
    its fixed name. Every registry starts empty -- use populate_registries()
    to fill them from a chapter's already-built object lists."""
    manager = RegistryManager()
    for name, registry_cls in _REGISTRY_CLASSES.items():
        manager.register(registry_cls())
    return manager


def populate_registries(
    manager: RegistryManager,
    *,
    concepts: Optional[Iterable[Dict[str, Any]]] = None,
    definitions: Optional[Iterable[Dict[str, Any]]] = None,
    glossary: Optional[Iterable[Dict[str, Any]]] = None,
    figures: Optional[Iterable[Dict[str, Any]]] = None,
    diagrams: Optional[Iterable[Dict[str, Any]]] = None,
    tables: Optional[Iterable[Dict[str, Any]]] = None,
    equations: Optional[Iterable[Dict[str, Any]]] = None,
    activities: Optional[Iterable[Dict[str, Any]]] = None,
    boxes: Optional[Iterable[Dict[str, Any]]] = None,
    warnings: Optional[Iterable[Dict[str, Any]]] = None,
    notes: Optional[Iterable[Dict[str, Any]]] = None,
    examples: Optional[Iterable[Dict[str, Any]]] = None,
) -> RegistryManager:
    """Inserts every already-built canonical object into its matching
    registry on `manager`, in the exact order each list is given in --
    the same deterministic order pipeline.py already builds and passes
    these lists to json_writer.assemble_chapter_json in. Registry
    insertion order therefore always matches a given chapter's Chapter
    JSON list order, run after run.

    Every argument is optional and defaults to inserting nothing for
    that type, so partial population (e.g. in a focused unit test, or a
    --no-vlm dry run that produces empty glossary/concepts lists) is
    just as valid as populating all twelve at once.

    This is purely additive bookkeeping: it reads each object dict,
    inserts a reference to it into a registry, and returns the same
    `manager` it was given (never mutates any input list/dict, never
    computes or attaches anything to an object that later gets written
    into the Chapter JSON). The registries this populates are an
    internal compiler representation -- see this module's and
    pipeline.py's docstrings for why they are not serialized into the
    Chapter JSON in Phase B1.

    Duplicate ids/urns within one type still raise (DuplicateIdError /
    DuplicateUrnError, via CanonicalRegistry.insert() -- see B0), exactly
    per "Duplicate protection should use the B0 infrastructure." This
    should never trigger on correct pipeline.py output (ids/urns are
    already unique per object, by construction -- see modules/canonical.py),
    so a raise here surfaces a genuine upstream id/urn collision rather
    than a registry-layer false positive (see module docstring for why
    name-collisions specifically are not a concern for eleven of the
    twelve types).
    """
    _insert_all(manager, "concepts", concepts)
    _insert_all(manager, "definitions", definitions)
    _insert_all(manager, "glossary", glossary)
    _insert_all(manager, "figures", figures)
    _insert_all(manager, "diagrams", diagrams)
    _insert_all(manager, "tables", tables)
    _insert_all(manager, "equations", equations)
    _insert_all(manager, "activities", activities)
    _insert_all(manager, "boxes", boxes)
    _insert_all(manager, "warnings", warnings)
    _insert_all(manager, "notes", notes)
    _insert_all(manager, "examples", examples)
    return manager


def _insert_all(
    manager: RegistryManager, registry_name: str, items: Optional[Iterable[Dict[str, Any]]]
) -> None:
    """Inserts every item in `items` (if any) into manager's registry
    named `registry_name`, preserving iteration order. Private: the only
    reason this is a separate function is so populate_registries()'s body
    reads as a flat, deterministic list of "this list -> this registry"
    statements matching pipeline.py's own object-list order."""
    if not items:
        return
    registry = manager.get(registry_name)
    for item in items:
        registry.insert(item)
