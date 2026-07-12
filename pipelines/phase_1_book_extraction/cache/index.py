"""
cache/index.py — Phase F4.1: cache discovery / cache history.

Mirrors artifact_manager/discovery.py's own list_builds()/
build_history() exactly, one package over: reuses
`storage.list_directory()` -- the exact same listing surface already
exposed by OneDriveStorage, no new discovery/indexing mechanism, no
database, no local index file. Cache history is simply "what's under
snapshot_store.py's own cache root", read via
snapshot_store.cache_root() (a public accessor -- this module never
reaches into snapshot_store.py's private `_CACHE_ROOT` constant
directly) on demand.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from storage.exceptions import NotFoundError, StorageError

from .exceptions import CacheReadError
from .snapshot_store import cache_root, load_fingerprint_snapshot

logger = logging.getLogger("cache.index")


def list_cache_entries(storage: Any) -> List[str]:
    """Every build_id with a persisted fingerprint snapshot, oldest-
    looking-id first (build ids sort chronologically by construction --
    see artifact_manager.build._generate_build_id()). Returns an empty
    list if `_runtime_cache/` itself doesn't exist yet (no cache entry
    has ever been persisted in this OneDrive account) -- not an error,
    mirroring artifact_manager.discovery.list_builds()'s own "nothing
    yet is a normal state" convention.

    Raises CacheReadError if the listing call fails for any other
    reason."""
    try:
        entries = storage.list_directory(path=cache_root())
    except NotFoundError:
        return []
    except StorageError as exc:
        raise CacheReadError(
            "<all>", f"failed to list {cache_root()!r}: {exc}"
        ) from exc

    build_ids = sorted(
        entry["name"] for entry in entries if entry.get("is_folder")
    )
    return build_ids


def cache_history(storage: Any) -> List[Dict[str, Any]]:
    """Every persisted build's own CacheEntry (build_id/generated_at/
    build_status/fingerprint_snapshot), in the same build_id order
    list_cache_entries() returns. An entry that fails to load (e.g. a
    partially-written cache record whose upload didn't complete) is
    skipped with a logged warning rather than failing the whole history
    call -- one bad record must not hide every other build's cache
    history, same "one failure must never stop the rest" principle
    artifact_manager.discovery.build_history() already applies one
    package over."""
    history: List[Dict[str, Any]] = []
    for build_id in list_cache_entries(storage):
        try:
            history.append(load_fingerprint_snapshot(storage, build_id))
        except CacheReadError:
            logger.warning(
                "cache: skipping build %s in cache_history() -- its "
                "fingerprint snapshot record could not be loaded.",
                build_id, exc_info=True,
            )
    return history