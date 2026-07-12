"""
compiler_release/discovery.py — Phase F5: release discovery / release
history.

Mirrors cache/index.py's own list_cache_entries()/cache_history()
exactly, one package over: reuses `storage.list_directory()` -- the
exact same listing surface already exposed by OneDriveStorage, no new
discovery/indexing mechanism, no database, no local index file. Release
history is simply "what's under persistence.py's own release root",
read via persistence.release_root() (a public accessor -- this module
never reaches into persistence.py's private `_RELEASE_ROOT` constant
directly) on demand.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from storage.exceptions import NotFoundError, StorageError

from .exceptions import ReleaseManifestError
from .persistence import load_release_manifest, release_root

logger = logging.getLogger("compiler_release.discovery")


def list_release_manifests(storage: Any) -> List[str]:
    """Every build_id with a persisted CompilerReleaseManifest,
    oldest-looking-id first (build ids sort chronologically by
    construction -- see artifact_manager.build._generate_build_id()).
    Returns an empty list if `_runtime_release/` itself doesn't exist
    yet (no release manifest has ever been persisted in this OneDrive
    account) -- not an error, mirroring
    artifact_manager.discovery.list_builds()'s and
    cache.index.list_cache_entries()'s own "nothing yet is a normal
    state" convention.

    Raises ReleaseManifestError if the listing call fails for any other
    reason."""
    try:
        entries = storage.list_directory(path=release_root())
    except NotFoundError:
        return []
    except StorageError as exc:
        raise ReleaseManifestError(
            f"list_release_manifests(): failed to list {release_root()!r}: {exc}"
        ) from exc

    build_ids = sorted(
        entry["name"] for entry in entries if entry.get("is_folder")
    )
    return build_ids


def release_history(storage: Any) -> List[Dict[str, Any]]:
    """Every persisted build's own CompilerReleaseManifest, in the same
    build_id order list_release_manifests() returns. A manifest that
    fails to load (e.g. a partially-written release record whose upload
    didn't complete) is skipped with a logged warning rather than
    failing the whole history call -- one bad record must not hide
    every other build's release history, same "one failure must never
    stop the rest" principle artifact_manager.discovery.build_history()
    and cache.index.cache_history() already apply, one and two packages
    over."""
    history: List[Dict[str, Any]] = []
    for build_id in list_release_manifests(storage):
        try:
            history.append(load_release_manifest(storage, build_id))
        except ReleaseManifestError:
            logger.warning(
                "compiler_release: skipping build %s in release_history() "
                "-- its release manifest record could not be loaded.",
                build_id, exc_info=True,
            )
    return history
