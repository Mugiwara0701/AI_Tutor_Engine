"""
artifact_manager/persistence.py — Phase F2: artifact persistence for the
Build and its Build Manifest.

REUSE, DON'T INVENT: this module never constructs its own OneDriveStorage
client and never authenticates -- it always receives an already-
authenticated storage instance (the exact same one book_orchestrator.
run()'s own startup gate already constructed and handed to
modules.json_writer.set_storage(), retrieved here via the small public
modules.json_writer.get_storage() accessor). Persistence itself is
upload_json()/download_json()/exists()/list_directory() -- the identical
surface modules/json_writer.py already uses for every chapter JSON and
book manifest -- there is no second serialization format, no second
storage client, and no local-filesystem fallback introduced here.

LAYOUT: every Build this process ever persists lives under one fixed,
board/class/subject/book-independent root (a Build can span many books
across many classes/subjects, so it cannot live under any single one of
their folders):

    _runtime_builds/<build_id>/build.json
    _runtime_builds/<build_id>/manifest.json

`_runtime_builds/` deliberately sits alongside, not inside, any
Board/Class/Subject/Book tree PathResolver already owns -- this is a raw
AI_TUTOR-relative path (OneDriveStorage's `path=` surface), same
"already have a full path, no board/klass/subject/book to resolve"
usage json_writer.write_book_manifest() itself makes for its own
`_book_manifest.json`, one level up.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from storage.exceptions import NotFoundError, StorageError

from .exceptions import ArtifactError, PersistenceError

logger = logging.getLogger("artifact_manager.persistence")

_BUILDS_ROOT = "_runtime_builds"


def _build_dir(build_id: str) -> str:
    return f"{_BUILDS_ROOT}/{build_id}"


def build_record_path(build_id: str) -> str:
    return f"{_build_dir(build_id)}/build.json"


def manifest_record_path(build_id: str) -> str:
    return f"{_build_dir(build_id)}/manifest.json"


def persist_build(storage: Any, build_dict: Dict[str, Any], manifest_dict: Dict[str, Any]) -> Dict[str, str]:
    """Persists a Build's dict form (Build.to_dict(), with its manifest
    already attached via Build.with_manifest()) and that same Build
    Manifest, each as its own JSON record, via `storage.upload_json()` --
    the exact reused persistence utility, not a new one. Returns the two
    AI_TUTOR-relative paths written to.

    Raises PersistenceError, chaining the original storage.exceptions
    error, if either upload fails."""
    build_id = build_dict.get("build_id")
    if not build_id:
        raise PersistenceError(
            "persist_build(): build_dict is missing 'build_id' -- expected "
            "the shape produced by artifact_manager.build.Build.to_dict()."
        )

    b_path = build_record_path(build_id)
    m_path = manifest_record_path(build_id)

    try:
        storage.upload_json(build_dict, path=b_path, indent=2)
        storage.upload_json(manifest_dict, path=m_path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_build(): failed to persist build {build_id!r} via "
            f"storage: {exc}"
        ) from exc

    logger.info("artifact_manager: persisted build %s -> %s, %s", build_id, b_path, m_path)
    return {"build_record_path": b_path, "manifest_record_path": m_path}


def load_build(storage: Any, build_id: str) -> Dict[str, Any]:
    """Loads a previously persisted Build record (Build.to_dict() shape,
    manifest already attached) via `storage.download_json()`. Raises
    ArtifactError if no such build_id was ever persisted, or
    PersistenceError if the storage read itself fails for any other
    reason."""
    path = build_record_path(build_id)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise ArtifactError(build_id, "no build record found") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_build(): failed to load build {build_id!r} via storage: {exc}"
        ) from exc


def load_manifest(storage: Any, build_id: str) -> Dict[str, Any]:
    """Loads a previously persisted Build Manifest via
    `storage.download_json()`. Same error contract as load_build()."""
    path = manifest_record_path(build_id)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise ArtifactError(build_id, "no manifest record found") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_manifest(): failed to load manifest for build {build_id!r} "
            f"via storage: {exc}"
        ) from exc


def build_exists(storage: Any, build_id: str) -> bool:
    """True if a Build record was already persisted for `build_id`.
    Never raises -- mirrors storage.exists()'s own "existence is a
    plain bool, not a raise/don't-raise decision" contract."""
    return bool(storage.exists(path=build_record_path(build_id)))
