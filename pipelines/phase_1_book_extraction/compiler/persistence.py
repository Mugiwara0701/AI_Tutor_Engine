"""
compiler/persistence.py — Phase 1 Output Persistence Enhancement:
chapter-scoped persistence for Compiler IR (Stage B).

BACKGROUND: Stage B (`compiler/`) builds one `RegistryManager` per
chapter holding the fourteen typed canonical registries (topics,
definitions, concepts, glossary, figures, diagrams, tables, equations,
activities, boxes, warnings, notes, examples, relationships), plus the
compiler manifest/statistics/fingerprints/validation report/readiness
report/build summary/final status that describe that build -- see
PHASE1_ARCHITECTURE.md §3. Before this module existed, every one of
those artifacts lived only in `compiler/state.py`'s module-level
"current chapter" slots, reset at the start of the next chapter, and
was never durably persisted; only the final Chapter JSON (topics/
concepts/.../equations lists, already flattened and re-shaped by
`modules/json_writer.py`) survived past one chapter's compilation. This
module is purely additive: it does not change what Stage B computes,
only what happens to that output afterward.

REUSE, DON'T INVENT: persistence itself is `storage.upload_json()`/
`download_json()`/`exists()` -- the exact surface `artifact_manager/
persistence.py` (Phase F2) and `modules/json_writer.py` already use --
via an already-authenticated `OneDriveStorage` instance the caller
supplies (never a new client, mirroring artifact_manager/persistence.
py's own "never constructs its own OneDriveStorage client" rule). Path
layout is `modules.json_writer.artifact_output_path()`, the same
"<NN>_<chapter-slug>.json" filename convention as the Chapter JSON
itself, so a chapter's Compiler IR records and its Chapter JSON are
trivially correlatable.

TWO RECORDS, MIRRORING compiler/build.py's OWN MANIFEST-VS-REGISTRIES
SPLIT:
  * "registries" -- `RegistryManager.serialize()`'s own output (every
    owned registry's serialize() output, keyed by name) -- the actual
    canonical objects (definitions, concepts, equations, ...), not a
    summary of them.
  * "compiler_metadata" -- the small, already-computed identity/
    verdict records Stage B produces alongside the registries
    (manifest, statistics, registry_fingerprints, compiler_fingerprint,
    validation_report, readiness_report, build_summary, final_status),
    each already a plain dict by the time Stage B is done (see
    compiler/build.py, compiler/fingerprints.py, compiler/finalize.py).

Nothing here re-derives, re-validates, or mutates a single field --
every value persisted is read verbatim from what pipeline.py's own
Stage B call sequence already computed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

from .registry_manager import RegistryManager

logger = logging.getLogger("compiler.persistence")


class PersistenceError(Exception):
    """Raised when persisting or loading a Compiler IR record fails for
    a reason other than "no such record exists yet" (that is
    RegistryNotFoundError, below)."""


class RegistryNotFoundError(PersistenceError):
    """Raised by load_registries()/load_compiler_metadata() when no
    record was ever persisted for the given chapter."""


ARTIFACT_TYPE_REGISTRIES = "registries"
ARTIFACT_TYPE_COMPILER_METADATA = "compiler_metadata"


def _chapter_path(artifact_type: str, klass: str, subject: str, book_slug: str, chapter_number,
                   chapter_title: str, output_root: Optional[str] = None) -> str:
    return json_writer.artifact_output_path(
        artifact_type, klass, subject, book_slug, chapter_number, chapter_title,
        output_root=output_root,
    )


def registries_record_path(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                            output_root: Optional[str] = None) -> str:
    return _chapter_path(ARTIFACT_TYPE_REGISTRIES, klass, subject, book_slug, chapter_number,
                          chapter_title, output_root=output_root)


def compiler_metadata_record_path(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                                   output_root: Optional[str] = None) -> str:
    return _chapter_path(ARTIFACT_TYPE_COMPILER_METADATA, klass, subject, book_slug, chapter_number,
                          chapter_title, output_root=output_root)


def persist_registries(storage: Any, registry_manager: RegistryManager, klass: str, subject: str,
                        book_slug: str, chapter_number, chapter_title: str,
                        output_root: Optional[str] = None) -> str:
    """Persists this chapter's Compiler IR registries via
    `registry_manager.serialize()` -- the RegistryManager's own,
    already-established serialization (compiler/registry_manager.py),
    never a second, hand-rolled shape. Returns the OneDrive-relative
    path written to. Raises PersistenceError, chaining the original
    storage error, if the upload fails."""
    path = registries_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                   output_root=output_root)
    try:
        storage.upload_json(registry_manager.serialize(), path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_registries(): failed to persist registries for chapter "
            f"{chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("compiler.persistence: persisted registries -> %s", path)
    return path


def load_registries(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                     chapter_title: str, output_root: Optional[str] = None) -> Dict[str, Any]:
    """Loads a previously persisted registries record (plain dict, the
    exact shape RegistryManager.serialize() produced) via
    `storage.download_json()`. A caller that wants a real
    RegistryManager back can pass this straight to
    `RegistryManager.deserialize()`. Raises RegistryNotFoundError if
    no such record was ever persisted, or PersistenceError if the
    storage read itself fails for any other reason."""
    path = registries_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                   output_root=output_root)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise RegistryNotFoundError(f"no registries record found at {path!r}") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_registries(): failed to load registries at {path!r} via storage: {exc}"
        ) from exc


def registries_exist(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                      chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = registries_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                   output_root=output_root)
    return bool(storage.exists(path=path))


def persist_compiler_metadata(
    storage: Any,
    klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
    *,
    manifest: Dict[str, Any],
    statistics: Dict[str, Any],
    registry_fingerprints: Dict[str, str],
    compiler_fingerprint: str,
    validation_report: Dict[str, Any],
    readiness_report: Dict[str, Any],
    build_summary: Dict[str, Any],
    final_status: str,
    output_root: Optional[str] = None,
) -> str:
    """Persists the small, already-computed Compiler IR
    identity/verdict records that accompany the registries above --
    every argument is passed in verbatim (never recomputed here) from
    what pipeline.py's own Stage B call sequence already produced
    (compiler/build.py, compiler/fingerprints.py, compiler/
    validation.py, compiler/finalize.py). Returns the OneDrive-relative
    path written to."""
    path = compiler_metadata_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                          output_root=output_root)
    record = {
        "manifest": manifest,
        "statistics": statistics,
        "registry_fingerprints": registry_fingerprints,
        "compiler_fingerprint": compiler_fingerprint,
        "validation_report": validation_report,
        "readiness_report": readiness_report,
        "build_summary": build_summary,
        "final_status": final_status,
    }
    try:
        storage.upload_json(record, path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_compiler_metadata(): failed to persist compiler metadata for "
            f"chapter {chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("compiler.persistence: persisted compiler metadata -> %s", path)
    return path


def load_compiler_metadata(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                            chapter_title: str, output_root: Optional[str] = None) -> Dict[str, Any]:
    path = compiler_metadata_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                          output_root=output_root)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise RegistryNotFoundError(f"no compiler metadata record found at {path!r}") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_compiler_metadata(): failed to load compiler metadata at {path!r} "
            f"via storage: {exc}"
        ) from exc


def compiler_metadata_exist(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                             chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = compiler_metadata_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                          output_root=output_root)
    return bool(storage.exists(path=path))