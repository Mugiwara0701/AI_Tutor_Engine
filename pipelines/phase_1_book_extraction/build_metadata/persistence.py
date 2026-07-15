"""
build_metadata/persistence.py — Phase 1 Output Persistence Enhancement:
chapter-scoped persistence for Build Metadata (Phase E1).

BACKGROUND: Phase E1 (`build_metadata/`) aggregates every
already-computed Phase B-D3 artifact, plus this chapter's own
operational (CompilationMetadata) and deterministic-configuration
(ConfigurationMetadata/VersionMetadata) details, into one
`BuildMetadata` record (see PHASE1_ARCHITECTURE.md §6, E1).
`build_metadata.build.finalize_build_metadata()` already returns
`{"build_metadata": ...}` with `BuildMetadata.to_dict()` already
applied (pipeline.py accesses it as a plain dict, e.g.
`build_metadata_result["build_metadata"]["configuration_metadata"]`) --
so, like dependency_graph/persistence.py, there is no live Python
object to `.serialize()` here, only an already-JSON-serializable dict
to write out. Before this module existed, that dict lived only in
`build_metadata/state.py`'s "current chapter" slot and was never
durably persisted. This module is purely additive: it does not change
what Phase E1 computes, only what happens to that output afterward.

REUSE, DON'T INVENT: same `storage.upload_json()`/`download_json()`/
`exists()` surface every other persisted phase in this codebase already
uses. Path layout is
`modules.json_writer.artifact_output_path("build_metadata", ...)`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

logger = logging.getLogger("build_metadata.persistence")


class PersistenceError(Exception):
    """Raised when persisting or loading a Build Metadata record fails
    for a reason other than "no such record exists yet" (that is
    BuildMetadataNotFoundError, below)."""


class BuildMetadataNotFoundError(PersistenceError):
    """Raised by load_build_metadata() when no record was ever
    persisted for the given chapter."""


ARTIFACT_TYPE = "build_metadata"


def build_metadata_record_path(klass: str, subject: str, book_slug: str, chapter_number,
                                chapter_title: str, output_root: Optional[str] = None) -> str:
    return json_writer.artifact_output_path(
        ARTIFACT_TYPE, klass, subject, book_slug, chapter_number, chapter_title,
        output_root=output_root,
    )


def persist_build_metadata(storage: Any, build_metadata: Dict[str, Any], klass: str, subject: str,
                            book_slug: str, chapter_number, chapter_title: str,
                            output_root: Optional[str] = None) -> str:
    """Persists this chapter's Build Metadata. `build_metadata` must be
    the already-computed dict
    `build_metadata.build.finalize_build_metadata(...)["build_metadata"]`
    produced -- never recomputed or reshaped here. Returns the
    OneDrive-relative path written to. Raises PersistenceError,
    chaining the original storage error, if the upload fails."""
    path = build_metadata_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                       output_root=output_root)
    try:
        storage.upload_json(build_metadata, path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_build_metadata(): failed to persist build metadata for "
            f"chapter {chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("build_metadata.persistence: persisted build metadata -> %s", path)
    return path


def load_build_metadata(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                         chapter_title: str, output_root: Optional[str] = None) -> Dict[str, Any]:
    path = build_metadata_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                       output_root=output_root)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise BuildMetadataNotFoundError(f"no build metadata record found at {path!r}") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_build_metadata(): failed to load build metadata at {path!r} "
            f"via storage: {exc}"
        ) from exc


def build_metadata_exists(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                           chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = build_metadata_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                       output_root=output_root)
    return bool(storage.exists(path=path))