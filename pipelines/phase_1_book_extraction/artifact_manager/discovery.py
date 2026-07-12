"""
artifact_manager/discovery.py — Phase F2: artifact discovery / build
history.

Reuses `storage.list_directory()` -- the exact same listing surface
already exposed by OneDriveStorage, no new discovery/indexing mechanism
of its own. Build history is simply "what's under persistence.py's own
builds root", read via persistence.builds_root() (a public accessor --
this module never reaches into persistence.py's private _BUILDS_ROOT
constant directly) on demand; nothing here is cached or indexed
anywhere new (no build database, no local index file -- that would be
a form of the "Cache" F0 explicitly reserves for Phase F4).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from storage.exceptions import NotFoundError, StorageError

from .exceptions import PersistenceError
from .persistence import builds_root, load_manifest

logger = logging.getLogger("artifact_manager.discovery")


def list_builds(storage: Any) -> List[str]:
    """Every build_id with a persisted record, oldest-looking-id first
    (build ids sort chronologically by construction -- see build.py's
    _generate_build_id()). Returns an empty list if
    _runtime_builds/ itself doesn't exist yet (no build has ever been
    persisted in this OneDrive account) -- not an error, mirroring
    every other "nothing yet is a normal state" convention in this
    codebase.

    Raises PersistenceError if the listing call fails for any other
    reason."""
    try:
        entries = storage.list_directory(path=builds_root())
    except NotFoundError:
        return []
    except StorageError as exc:
        raise PersistenceError(
            f"list_builds(): failed to list {builds_root()!r}: {exc}"
        ) from exc

    build_ids = sorted(
        entry["name"] for entry in entries if entry.get("is_folder")
    )
    return build_ids


def build_history(storage: Any) -> List[Dict[str, Any]]:
    """Every persisted build's own Build Manifest (the lightweight
    record -- build_status/execution_summary/fingerprints/errors/
    warnings -- rather than the heavier Build record with its full
    references), in the same build_id order list_builds() returns. A
    manifest that fails to load (e.g. a partially-written build whose
    manifest.json upload didn't complete) is skipped with a logged
    warning rather than failing the whole history call -- one bad
    record must not hide every other build's history, same "one
    failure must never stop the rest" principle book_orchestrator.py's
    own per-book error handling already applies one layer down."""
    history: List[Dict[str, Any]] = []
    for build_id in list_builds(storage):
        try:
            history.append(load_manifest(storage, build_id))
        except Exception:
            logger.warning(
                "artifact_manager: skipping build %s in build_history() -- "
                "its manifest record could not be loaded.", build_id,
                exc_info=True,
            )
    return history