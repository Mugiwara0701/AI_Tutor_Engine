"""
document_structure_tree/registry_snapshot.py — Milestone 5: Compiler
Integration, the `CanonicalRegistrySnapshot` seam.

WHAT THIS IS. Milestone 3 (`validation.py`) defined `CanonicalRegistrySnapshot`
as a narrow `Protocol` -- "given a `CanonicalObjectId` and a snapshot ref,
return existence + authoritative `object_type`, or 'not found'" -- and
noted that "a concrete registry client resolving
`canonical_registry_snapshot_ref` to *this* interface" was roadmap M5's
job, deliberately deferred (validation.py's own module docstring: "Its
real implementation is out of scope for Phase 1.1 (owned upstream)").
`artifact.py`'s own docstring says the same thing from the other side:
"callers resolving `canonical_registry_snapshot_ref` against the real
canonical registries do so entirely outside this package."

This module is that caller. It does not live inside the parts of this
package Milestones 1-4 already froze (builder/validation/serialization/
models) -- it is a NEW, additive file, exactly like `state.py` (this
same milestone) -- and it imports `compiler.registry_manager.
RegistryManager`, which is why it is kept in its own module rather than
folded into `state.py` or `persistence.py`: `document_structure_tree/`'s
other modules import nothing outside the package (see `artifact.py`'s
own "PACKAGE BOUNDARY" paragraph); this module is the one deliberate,
documented exception, and its entire job is to be that boundary-crossing
adapter and nothing else.

WHAT "THE CANONICAL REGISTRIES" MEANS IN *THIS* CODEBASE. Architecture
§6/§7 describes the DST and the Knowledge Graph as both being built from
"Chapter JSON and the canonical registries." In this codebase, "the
canonical registries" is exactly `compiler.registry_manager.RegistryManager`
-- the same, already-fully-populated-by-Phase-B manager Knowledge Graph
construction (Phase C1/C2, pipeline.py) already reads read-only. This
module wraps that same object; it does not introduce a second registry
implementation or duplicate any of Phase B's own population logic
(compiler/registries.py's `populate_registries()`).

WHICH REGISTRIES COUNT AS "CONTENT" FOR R2/R3/R4. Per architecture §5
(Non-Goals: "does not model semantic relationships between concepts...")
and schema §2.7 (a `content`-type `SequenceEntry.ref` is a
`CanonicalObjectId`), only the canonical object types the DST builder
itself can ever place into a node's `sequence` are in scope here --
exactly the fourteen types `builder.py`'s own
`_CONTENT_FIELD_TO_OBJECT_TYPE` enumerates (`definition`, `example`,
`activity`, `figure`, `table`, `equation`, `diagram`, `chart`, `graph`,
`map`, `timeline`, `box`, `note`, `warning`). `compiler.registries.
REGISTRY_NAMES` additionally includes `"topics"` (structural headings --
these become DST tree *nodes*, never `sequence` content, so counting
them here would make R4 flag every single one as "unowned content") and
`"concepts"` / `"glossary"` (architecture §5: concept modeling is the
Knowledge Graph's job, and -- consistent with that -- `builder.py` never
builds a `ContentRef` for either, so neither ever appears as a
`sequence` entry to validate a reference against). `EXCLUDED_REGISTRY_NAMES`
below names exactly those three, so this adapter's `objects_owned_by_chapter`
matches, precisely, the universe `builder.py` can actually reference --
never a broader or narrower one.

Every remaining registry's items are trusted for their own `object_type`
field (not the physical registry container they happen to live in):
`Chart`/`Graph`/`Map`/`Timeline` all subclass `Figure` in
`schemas/chapter_schema.py` and may be inserted into whichever registry
`populate_registries()` was given them under, but each item dict already
carries its own authoritative `"object_type"` string (compiler/
enrichment.py, compiler/validation.py both already read `item.get(
"object_type")` the same way) -- reading that field directly, rather
than inferring a type from the registry name, is what makes this
adapter correct regardless of exactly which named registry a given
object type happens to be inserted into.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, Optional

from .primitives import CanonicalObjectId, ChapterId, ObjectType

__all__ = ["EXCLUDED_REGISTRY_NAMES", "CompilerRegistrySnapshot"]

# See module docstring, "WHICH REGISTRIES COUNT AS 'CONTENT' FOR R2/R3/R4".
EXCLUDED_REGISTRY_NAMES = frozenset({"topics", "concepts", "glossary"})


@dataclass(frozen=True)
class CompilerRegistrySnapshot:
    """Adapts an already-populated `compiler.registry_manager.
    RegistryManager` (one chapter's Compiler IR -- the "canonical
    registries" architecture §6/§7 refers to, in this codebase) to
    `validation.CanonicalRegistrySnapshot`'s three-method Protocol.

    `registry_manager` is consumed strictly read-only: every method
    below only reads (`get`, iteration, `.get_by_id`-style dict access
    on each item); nothing here inserts, updates, or removes a single
    registry item. This mirrors the exact "read-only over
    `registry_manager`" treatment every Phase C (Knowledge Graph)
    integration point in `pipeline.py` already gives the same object.

    `chapter_id` is carried alongside `registry_manager` because
    `objects_owned_by_chapter()` (the Protocol's own method) takes a
    `ChapterId` parameter -- kept here, rather than trusted blindly, so
    a caller who (by a bug) passes this snapshot a `chapter_id` other
    than the one it was actually built for gets an intentionally empty
    result (see that method below) instead of silently attributing one
    chapter's registries to another's DST build.
    """

    registry_manager: "object"  # compiler.registry_manager.RegistryManager
    chapter_id: ChapterId

    def _content_items(self):
        """Yields every item dict from every non-excluded registry this
        manager owns (see module docstring). Registries are read via
        `RegistryManager.names()`/`.get()` rather than `__iter__` so a
        missing/absent registry (e.g. a chapter with no equations, whose
        `EquationRegistry` may simply not have been registered by a
        caller building a minimal manager for a test) is never an
        error -- `has(name)` is checked first, `RegistryManager.get()`
        would raise `ItemNotFoundError` for a truly-absent registry,
        which is not this adapter's concern to surface."""
        for name in self.registry_manager.names():
            if name in EXCLUDED_REGISTRY_NAMES:
                continue
            for item in self.registry_manager.get(name):
                yield item

    def object_exists(self, object_id: CanonicalObjectId) -> bool:
        target = object_id.value
        for item in self._content_items():
            if item.get("id") == target:
                return True
        return False

    def object_type_of(self, object_id: CanonicalObjectId) -> Optional[ObjectType]:
        target = object_id.value
        for item in self._content_items():
            if item.get("id") == target:
                object_type = item.get("object_type")
                return ObjectType(object_type) if object_type else None
        return None

    def objects_owned_by_chapter(self, chapter_id: ChapterId) -> AbstractSet[CanonicalObjectId]:
        # Intentionally empty for any chapter_id other than the one this
        # snapshot was constructed for -- see class docstring. A
        # RegistryManager, in this codebase, is always exactly one
        # chapter's worth of registries (compiler/state.py: "this
        # pipeline processes one chapter at a time"), so there is no
        # broader multi-chapter universe this method could honestly
        # answer for.
        if chapter_id != self.chapter_id:
            return frozenset()
        return frozenset(
            CanonicalObjectId(item["id"])
            for item in self._content_items()
            if item.get("id")
        )