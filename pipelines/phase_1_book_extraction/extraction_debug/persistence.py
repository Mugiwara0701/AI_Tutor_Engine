"""
extraction_debug/persistence.py — Milestone 3.2: Copyright-Safe
Serialization, debug-artifact persistence.

Persists whatever `modules.copyright_sanitizer` stripped out of a
chapter's production Chapter JSON (see that module's own docstring for
the full list of fields) to its own artifact folder
(`extraction_debug/`, an OneDrive sibling of `json_out/` — see
`modules/json_writer.py`'s `_ARTIFACT_SUBFOLDERS`), NEVER to `json_out/`
itself. Mirrors `validation/persistence.py`'s own shape and error
handling exactly (`PersistenceError`/`*NotFoundError`, one record per
chapter, `storage.upload_json()`/`download_json()`/`exists()`).

Written ONLY when there is something to write: a chapter with no
stripped fields (no equation had a raw-text hint, no deterministic
procedure/programming-syntax object was found) never creates an empty
`extraction_debug/<chapter>.json` file — see `persist_extraction_debug`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

logger = logging.getLogger("extraction_debug.persistence")


class PersistenceError(Exception):
    """Raised when persisting or loading an extraction-debug record fails
    for a reason other than "no such record exists yet" (that is
    ExtractionDebugRecordNotFoundError, below)."""


class ExtractionDebugRecordNotFoundError(PersistenceError):
    """Raised by load_extraction_debug_record() when no record was ever
    persisted for the given chapter (the common case — most chapters
    have nothing to sanitize away)."""


ARTIFACT_TYPE = "extraction_debug"


def extraction_debug_record_path(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                                  output_root: Optional[str] = None) -> str:
    return json_writer.artifact_output_path(
        ARTIFACT_TYPE, klass, subject, book_slug, chapter_number, chapter_title,
        output_root=output_root,
    )


def persist_extraction_debug(
    storage: Any,
    klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
    *,
    debug_entries: List[Dict[str, Any]],
    output_root: Optional[str] = None,
) -> Optional[str]:
    """Persists this chapter's copyright-sanitization debug entries.
    `debug_entries` is passed in verbatim (never recomputed here) from
    `modules.copyright_sanitizer.sanitize_chapter_records()`'s own
    return value.

    Returns the OneDrive-relative path written to, or None (writes
    nothing) when `debug_entries` is empty — the common case, and the
    reason this is a distinct code path from persist_validation_record's
    "always write" behavior. Raises PersistenceError, chaining the
    original storage error, if the upload fails."""
    if not debug_entries:
        return None

    path = extraction_debug_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                         output_root=output_root)
    record = {
        "note": (
            "Debug-only artifact (Milestone 3.2, Copyright-Safe Serialization). "
            "Contains source-derived text stripped from the production Chapter "
            "JSON by modules.copyright_sanitizer. Never distribute or serve this "
            "file the way the Chapter JSON itself is served."
        ),
        "entries": debug_entries,
    }
    try:
        storage.upload_json(record, path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_extraction_debug(): failed to persist extraction-debug record for "
            f"chapter {chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("extraction_debug.persistence: persisted %d debug entr%s -> %s",
                len(debug_entries), "y" if len(debug_entries) == 1 else "ies", path)
    return path


def load_extraction_debug_record(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                                  chapter_title: str, output_root: Optional[str] = None) -> Dict[str, Any]:
    path = extraction_debug_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                         output_root=output_root)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise ExtractionDebugRecordNotFoundError(f"no extraction-debug record found at {path!r}") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_extraction_debug_record(): failed to load extraction-debug record at {path!r} "
            f"via storage: {exc}"
        ) from exc


def extraction_debug_record_exists(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                                    chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = extraction_debug_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                         output_root=output_root)
    return bool(storage.exists(path=path))
