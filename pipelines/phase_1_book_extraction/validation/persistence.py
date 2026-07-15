"""
validation/persistence.py — Phase 1 Output Persistence Enhancement:
chapter-scoped persistence for Stage D validation (`validation/`).

BACKGROUND: Stage D runs three chapter-scoped passes -- D1 System
Integrity (`system_integrity.py`), D2 Determinism
(`determinism.py`), D3 Release Readiness (`release.py`) -- each
aggregating what earlier phases already computed (see
PHASE1_ARCHITECTURE.md §5). Before this module existed, every one of
those reports lived only in its own state module
(`validation/state.py`, `validation/determinism_state.py`,
`validation/release_state.py`) and was never durably persisted --
`chapter_dict["validation_report"]` in the Chapter JSON is a *different*
artifact (extraction-internal Stage E's dedupe report, see
PHASE1_ARCHITECTURE.md §2's naming note), not any of these three. This
module is purely additive: it does not change what Stage D computes,
only what happens to that output afterward.

ONE RECORD, NOT THREE: D1/D2/D3 are three passes over the *same*
chapter build, each aggregating the one before it (D3 quotes D1 and D2
verdicts directly) -- persisting them as one "validation" record per
chapter (system_integrity_report + determinism_report +
release_readiness_report + release_status) mirrors the single
`validation/` folder Phase 1's own output-structure design calls for,
and keeps a chapter's three-pass validation story in one place instead
of three files a reader would otherwise have to open together anyway.

REUSE, DON'T INVENT: same `storage.upload_json()`/`download_json()`/
`exists()` surface every other persisted phase in this codebase already
uses. Path layout is
`modules.json_writer.artifact_output_path("validation", ...)`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

logger = logging.getLogger("validation.persistence")


class PersistenceError(Exception):
    """Raised when persisting or loading a validation record fails for
    a reason other than "no such record exists yet" (that is
    ValidationRecordNotFoundError, below)."""


class ValidationRecordNotFoundError(PersistenceError):
    """Raised by load_validation_record() when no record was ever
    persisted for the given chapter."""


ARTIFACT_TYPE = "validation"


def validation_record_path(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                            output_root: Optional[str] = None) -> str:
    return json_writer.artifact_output_path(
        ARTIFACT_TYPE, klass, subject, book_slug, chapter_number, chapter_title,
        output_root=output_root,
    )


def persist_validation_record(
    storage: Any,
    klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
    *,
    system_integrity_report: Dict[str, Any],
    determinism_report: Dict[str, Any],
    release_readiness_report: Dict[str, Any],
    release_status: str,
    output_root: Optional[str] = None,
) -> str:
    """Persists this chapter's Stage D validation story (D1 + D2 + D3).
    Every argument is passed in verbatim (never recomputed here) from
    what pipeline.py's own Stage D call sequence already produced
    (validation/system_integrity.py, validation/determinism.py,
    validation/release.py). Returns the OneDrive-relative path written
    to. Raises PersistenceError, chaining the original storage error,
    if the upload fails."""
    path = validation_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                   output_root=output_root)
    record = {
        "system_integrity_report": system_integrity_report,
        "determinism_report": determinism_report,
        "release_readiness_report": release_readiness_report,
        "release_status": release_status,
    }
    try:
        storage.upload_json(record, path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_validation_record(): failed to persist validation record for "
            f"chapter {chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("validation.persistence: persisted validation record -> %s", path)
    return path


def load_validation_record(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                            chapter_title: str, output_root: Optional[str] = None) -> Dict[str, Any]:
    path = validation_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                   output_root=output_root)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise ValidationRecordNotFoundError(f"no validation record found at {path!r}") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_validation_record(): failed to load validation record at {path!r} "
            f"via storage: {exc}"
        ) from exc


def validation_record_exists(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                              chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = validation_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                   output_root=output_root)
    return bool(storage.exists(path=path))