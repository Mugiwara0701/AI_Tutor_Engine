"""
compiler/discovery.py — Phase 1 Output Persistence Enhancement:
discovery for persisted Compiler IR records (compiler/persistence.py).

Reuses `storage.list_directory()` -- the exact listing surface
`artifact_manager/discovery.py` (Phase F2) already uses -- over
`modules.json_writer.artifact_output_dir()`, never a new indexing
mechanism. One bad record is skipped with a logged warning rather than
failing the whole listing, the same "one failure must never hide the
rest" convention `artifact_manager/discovery.py::build_history()`
already establishes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

from .persistence import (
    ARTIFACT_TYPE_COMPILER_METADATA,
    ARTIFACT_TYPE_REGISTRIES,
    PersistenceError,
)

logger = logging.getLogger("compiler.discovery")


def _list_records(storage: Any, artifact_type: str, klass: str, subject: str, book_slug: str,
                   output_root=None) -> List[str]:
    """Every persisted <NN>_<chapter-slug>.json filename under this
    book's `artifact_type` folder, sorted (chapter number prefix makes
    this chronological). Empty list if the folder doesn't exist yet --
    not an error, mirroring artifact_manager.discovery.list_builds()'s
    own "nothing yet is a normal state" convention."""
    out_dir = json_writer.artifact_output_dir(artifact_type, klass, subject, book_slug,
                                               output_root=output_root)
    try:
        entries = storage.list_directory(path=out_dir)
    except NotFoundError:
        return []
    except StorageError as exc:
        raise PersistenceError(f"failed to list {out_dir!r}: {exc}") from exc
    return sorted(
        entry["name"] for entry in entries
        if not entry.get("is_folder") and entry["name"].endswith(".json")
    )


def list_registries(storage: Any, klass: str, subject: str, book_slug: str, output_root=None) -> List[str]:
    """Every chapter filename with a persisted registries record for
    this book."""
    return _list_records(storage, ARTIFACT_TYPE_REGISTRIES, klass, subject, book_slug,
                          output_root=output_root)


def list_compiler_metadata(storage: Any, klass: str, subject: str, book_slug: str,
                            output_root=None) -> List[str]:
    """Every chapter filename with a persisted compiler_metadata record
    for this book."""
    return _list_records(storage, ARTIFACT_TYPE_COMPILER_METADATA, klass, subject, book_slug,
                          output_root=output_root)


def compiler_metadata_history(storage: Any, klass: str, subject: str, book_slug: str,
                               output_root=None) -> List[Dict[str, Any]]:
    """Every persisted chapter's compiler_metadata record for this
    book, in list_compiler_metadata()'s own filename order. A record
    that fails to load is skipped with a logged warning rather than
    failing the whole history call.

    Downloads by the exact listed path (out_dir/filename) rather than
    reconstructing a chapter_title from the filename and re-deriving a
    path through load_compiler_metadata()/artifact_output_path() --
    slugify() is not guaranteed invertible, so re-slugifying a filename
    fragment back through that path could silently miss on an unusual
    title even though the file is right there in the listing."""
    out_dir = json_writer.artifact_output_dir(ARTIFACT_TYPE_COMPILER_METADATA, klass, subject, book_slug,
                                               output_root=output_root)
    history: List[Dict[str, Any]] = []
    for filename in list_compiler_metadata(storage, klass, subject, book_slug, output_root=output_root):
        path = f"{out_dir}/{filename}"
        try:
            history.append(storage.download_json(path=path))
        except Exception:
            logger.warning(
                "compiler.discovery: skipping %s in compiler_metadata_history() -- "
                "its record could not be loaded.", filename, exc_info=True,
            )
    return history