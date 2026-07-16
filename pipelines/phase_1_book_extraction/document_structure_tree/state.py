"""
document_structure_tree/state.py — Milestone 5: Compiler Integration,
chapter-scoped DST state lifecycle.

WHY THIS FILE EXISTS / WHY IT LIVES HERE: Milestones 1-4 (see this
package's own `__init__.py`) deliberately never touched compiler
pipeline wiring or persistence -- `generate_artifact()` (artifact.py)
takes an already-built `tree` and already-resolved inputs as plain
arguments and hands back a `DocumentStructureTree` value; nothing in
this package remembers "the DST for the chapter currently being
compiled." Milestone 5 is exactly the milestone that needs that: a
compiler pipeline (`pipeline.py`) builds one DST per chapter and later,
in-process phases -- persistence (`persistence.py`, this same
milestone), artifact registration (`artifact_manager`) -- need to read
it back without pipeline.py threading it through every function
signature by hand.

This module reuses the EXACT "current compilation state" module-level-
slot idiom `compiler/state.py` established for Compiler IR and
`knowledge_graph/state.py` already reused, unmodified in shape, for the
Knowledge Graph one layer up (see that module's own docstring: "the
same established idiom ... a module-level slot, set once per chapter,
read by any later phase that needs it, and reset before the next
chapter starts"). It lives inside `document_structure_tree/` --
alongside the artifact type it tracks -- for the identical reason
`knowledge_graph/state.py` lives inside `knowledge_graph/` rather than
inside `compiler/`: each artifact package owns its own chapter-scoped
"current" slot; `pipeline.py` only ever calls `set_current_*()`/
`reset_*_state()`, never reimplements the slot itself.

PACKAGE BOUNDARY NOTE (see this milestone's own "Package Boundary"
instruction): this is a NEW, additive file. It imports nothing from,
and is imported by nothing in, `builder.py` / `validation.py` /
`serialization.py` / `artifact.py` / `document_structure_tree.py` /
`heading_node.py` / `sequence_entry.py` / `primitives.py` /
`identity.py` / `enums.py` / `exceptions.py` -- every one of those
modules, and the models/algorithms they implement, is completely
unmodified by this milestone. This file only adds a place for a
compiler pipeline to put the `DocumentStructureTree` those modules
already know how to build.

OWNERSHIP / LIFECYCLE (identical contract to knowledge_graph/state.py's
own, one artifact over):

  1. A pipeline step (pipeline.py's process_chapter(), this milestone)
     calls reset_document_structure_tree_state() at the start of DST
     construction for a chapter, so a failed or skipped DST build never
     leaves a stale artifact from the previous chapter visible as
     "current."
  2. That pipeline builds a fresh `DocumentStructureTree` (via
     `builder.build_tree_from_chapter_json()` + `artifact.
     generate_artifact()`, both unchanged, Milestones 2.2/4) and calls
     set_current_document_structure_tree() once it is complete --
     regardless of whether `validation_metadata.validation_status` is
     "pass" or "fail" (architecture §9.3: an artifact that fails
     validation is still a complete, representable artifact; it is Phase
     2 -- not this state slot -- that must refuse to treat it as safe to
     consume).
  3. get_current_document_structure_tree() returns that exact instance
     (not a copy) to any later, in-process consumer, until the next
     reset.

Not thread-safe / not concurrency-safe by design, same as
compiler/state.py's and knowledge_graph/state.py's own explicit design
note: this pipeline processes one chapter at a time, in one process.
"""
from __future__ import annotations

from typing import Optional

from .document_structure_tree import DocumentStructureTree

# --------------------------------------------------------------------------
# Current chapter's DST artifact. One slot -- unlike knowledge_graph/
# state.py's seven (KnowledgeGraph/manifest/statistics/validation report/
# readiness report/build summary/final status), the DST schema (§9) folds
# metadata, provenance, validation results, and the tree itself into ONE
# `DocumentStructureTree` value (schema §2.2) -- there is no separate
# manifest/statistics/build-summary/final-status object to track
# alongside it, so one slot is the complete, faithful mirror of that
# schema shape, not a simplification of it.
# --------------------------------------------------------------------------
_CURRENT_DOCUMENT_STRUCTURE_TREE: Optional[DocumentStructureTree] = None


def set_current_document_structure_tree(document_structure_tree: DocumentStructureTree) -> None:
    global _CURRENT_DOCUMENT_STRUCTURE_TREE
    _CURRENT_DOCUMENT_STRUCTURE_TREE = document_structure_tree


def get_current_document_structure_tree() -> Optional[DocumentStructureTree]:
    return _CURRENT_DOCUMENT_STRUCTURE_TREE


def has_current_document_structure_tree() -> bool:
    return _CURRENT_DOCUMENT_STRUCTURE_TREE is not None


def reset_document_structure_tree_state() -> None:
    """Clears the DST state slot -- the one function a compiler pipeline
    calls once per chapter, before that chapter's DST construction
    begins, mirroring knowledge_graph.state.reset_knowledge_graph_state()'s
    own role exactly. Safe to call even if the slot was never set
    (idempotent)."""
    global _CURRENT_DOCUMENT_STRUCTURE_TREE
    _CURRENT_DOCUMENT_STRUCTURE_TREE = None