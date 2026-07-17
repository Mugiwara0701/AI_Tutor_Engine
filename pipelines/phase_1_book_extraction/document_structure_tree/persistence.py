"""
document_structure_tree/persistence.py — Milestone 5: Compiler
Integration, chapter-scoped persistence for the Document Structure Tree.

BACKGROUND: Milestones 1-4 build one `DocumentStructureTree` per chapter
(the full four-layer artifact -- `artifact_metadata`, `build_provenance`,
`validation_metadata`, `tree`, plus optional `derived_summary` -- schema
§2.2) entirely in memory; `artifact.generate_artifact()`/`serialize()`/
`deserialize()` (Milestone 4) already cover assembly and text-level
round-tripping, but nothing before this milestone ever wrote a DST to
durable storage. This module is purely additive, exactly like
`knowledge_graph/persistence.py` was for the Knowledge Graph: it does
not change what Milestones 1-4 compute, only what happens to that output
afterward.

REUSE, DON'T INVENT (this milestone's own "Reuse the existing builder,
validator, serializer, and models" instruction, applied to persistence):
same `storage.upload_json()`/`download_json()`/`exists()` surface every
other persisted phase in this codebase already uses (compiler/
persistence.py, knowledge_graph/persistence.py, dependency_graph/
persistence.py, ...), via an already-authenticated storage instance the
caller supplies -- this module does not open a new storage connection or
define a new upload/download primitive. Path layout is
`modules.json_writer.artifact_output_path("document_structure_tree",
...)`, the exact same "<NN>_<chapter-slug>.json"-style convention every
other artifact type already uses, under its own artifact-type folder.

WHY `to_canonical_json()`, NOT A NEW SERIALIZATION: the record this
module writes is exactly `artifact.to_canonical_json(document_structure_tree)`
(Milestone 4, unchanged) -- the same deterministic, `tree`-array-sorted
JSON shape `artifact.serialize()` already produces text for. This module
never re-derives that shape or re-implements schema §5's rules; it only
decides that shape should also be written to durable storage, via
`storage.upload_json()` (which accepts a plain dict, the exact shape
`to_canonical_json()` already returns) rather than `artifact.serialize()`'s
own text form -- mirroring every other artifact-type persistence module
in this codebase (e.g. knowledge_graph/persistence.py: "calls the
registry manager's own `.serialize()` ... and nests its result", never
a bespoke text write).

ONE RECORD, ONE FILE: like knowledge_graph/persistence.py (and unlike
compiler/persistence.py's two-artifact split), this module persists the
whole `DocumentStructureTree` as one JSON record per chapter --
`artifact_metadata`, `build_provenance`, `validation_metadata`, `tree`,
and `derived_summary` together -- mirroring the DST schema's own single-
artifact design (schema §2.2: "the single persisted artifact
representing a chapter's structural map").

PACKAGE BOUNDARY NOTE: this is a NEW, additive file, exactly like
`state.py` and `registry_snapshot.py` (this same milestone). It imports
`artifact.to_canonical_json`/`DocumentStructureTree.from_json` (both
Milestone 4/2.1, unchanged) plus, like `registry_snapshot.py`, the two
external modules every other persistence module in this codebase already
depends on (`modules.json_writer`, `storage.exceptions`) -- it does not
duplicate either.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

from .artifact import to_canonical_json
from .document_structure_tree import DocumentStructureTree

logger = logging.getLogger("document_structure_tree.persistence")

__all__ = [
    "PersistenceError",
    "DocumentStructureTreeNotFoundError",
    "ARTIFACT_TYPE",
    "document_structure_tree_record_path",
    "persist_document_structure_tree",
    "load_document_structure_tree",
    "document_structure_tree_exists",
]


class PersistenceError(Exception):
    """Raised when persisting or loading a Document Structure Tree
    record fails for a reason other than "no such record exists yet"
    (that is `DocumentStructureTreeNotFoundError`, below) -- mirrors
    `knowledge_graph.persistence.PersistenceError`'s own role exactly,
    one artifact type over."""


class DocumentStructureTreeNotFoundError(PersistenceError):
    """Raised by `load_document_structure_tree()` when no record was
    ever persisted for the given chapter."""


ARTIFACT_TYPE = "document_structure_tree"


def document_structure_tree_record_path(klass: str, subject: str, book_slug: str, chapter_number,
                                         chapter_title: str, output_root: Optional[str] = None) -> str:
    return json_writer.artifact_output_path(
        ARTIFACT_TYPE, klass, subject, book_slug, chapter_number, chapter_title,
        output_root=output_root,
    )


def persist_document_structure_tree(
    storage: Any,
    klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
    *,
    document_structure_tree: DocumentStructureTree,
    output_root: Optional[str] = None,
) -> str:
    """Persists this chapter's complete Document Structure Tree. The
    only argument that isn't plain routing (`klass`/`subject`/
    `book_slug`/`chapter_number`/`chapter_title`/`output_root`, the same
    six every other artifact-type persistence function in this codebase
    already takes) is `document_structure_tree` itself -- the already-
    fully-assembled artifact `artifact.generate_artifact()` (Milestone 4)
    produced; never recomputed or revalidated here. Returns the
    storage-relative path written to. Raises `PersistenceError`,
    chaining the original storage error, if the upload fails -- never
    lets a raw storage exception escape this module's boundary,
    mirroring every sibling persistence module."""
    path = document_structure_tree_record_path(
        klass, subject, book_slug, chapter_number, chapter_title, output_root=output_root,
    )
    record = to_canonical_json(document_structure_tree)
    try:
        storage.upload_json(record, path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_document_structure_tree(): failed to persist the Document "
            f"Structure Tree for chapter {chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("document_structure_tree.persistence: persisted DST -> %s", path)
    return path


def load_document_structure_tree(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                                  chapter_title: str, output_root: Optional[str] = None) -> DocumentStructureTree:
    """Loads a previously persisted Document Structure Tree record and
    reconstructs it via `DocumentStructureTree.from_json()` (Milestone
    2.1, unchanged) -- the exact inverse of `persist_document_structure_tree()`
    above. Raises `DocumentStructureTreeNotFoundError` if no such record
    was ever persisted, or `PersistenceError` if the storage read itself
    fails for any other reason."""
    path = document_structure_tree_record_path(
        klass, subject, book_slug, chapter_number, chapter_title, output_root=output_root,
    )
    try:
        record: Dict[str, Any] = storage.download_json(path=path)
    except NotFoundError as exc:
        raise DocumentStructureTreeNotFoundError(
            f"no Document Structure Tree record found at {path!r}"
        ) from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_document_structure_tree(): failed to load the Document "
            f"Structure Tree at {path!r} via storage: {exc}"
        ) from exc
    return DocumentStructureTree.from_json(record)


def document_structure_tree_exists(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                                    chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = document_structure_tree_record_path(
        klass, subject, book_slug, chapter_number, chapter_title, output_root=output_root,
    )
    return bool(storage.exists(path=path))