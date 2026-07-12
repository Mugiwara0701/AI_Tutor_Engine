"""
compiler_release/persistence.py — Phase F5: CompilerReleaseManifest
persistence.

REUSE, DON'T INVENT (same rule artifact_manager/persistence.py and
cache/snapshot_store.py already state one and two packages down): this
module never constructs its own OneDriveStorage client and never
authenticates -- every function here receives an already-authenticated
storage instance (the exact same one modules.json_writer.get_storage()
already returns). Persistence itself is upload_json()/download_json()/
exists()/list_directory() -- the identical surface artifact_manager/
persistence.py and cache/snapshot_store.py already use for the Build,
Build Manifest, and fingerprint snapshot -- there is no second
serialization format, no second storage client, and no local-filesystem
or database fallback introduced here.

LAYOUT: mirrors cache/snapshot_store.py's own "deliberately NOT nested
inside _runtime_builds/<build_id>/" rule exactly, one sibling root
further -- so neither Phase F2's nor Phase F4's own record folders ever
need to know Phase F5 exists (F0 §13: "Phase F MUST NOT redesign
previous phases"):

    _runtime_release/<build_id>/release_manifest.json
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from storage.exceptions import NotFoundError, StorageError

from .exceptions import ReleaseManifestError

logger = logging.getLogger("compiler_release.persistence")

_RELEASE_ROOT = "_runtime_release"


def release_root() -> str:
    """Public accessor for this module's release-history root path --
    mirrors artifact_manager.persistence.builds_root()'s and
    cache.snapshot_store.cache_root()'s own role, one package further
    over, so discovery.py never reaches into a private constant here
    directly."""
    return _RELEASE_ROOT


def _release_dir(build_id: str) -> str:
    return f"{_RELEASE_ROOT}/{build_id}"


def release_manifest_record_path(build_id: str) -> str:
    return f"{_release_dir(build_id)}/release_manifest.json"


def persist_release_manifest(storage: Any, manifest: Dict[str, Any]) -> Dict[str, str]:
    """Persists a CompilerReleaseManifest (generate_compiler_release_
    manifest()'s own return shape) as its own JSON record, via
    `storage.upload_json()` -- the exact reused persistence utility, not
    a new one. Returns the AI_TUTOR-relative path written to.

    Raises ReleaseManifestError, chaining the original storage.exceptions
    error, if `manifest` is missing `build_id` or the upload itself
    fails."""
    build_id = manifest.get("build_id")
    if not build_id:
        raise ReleaseManifestError(
            "persist_release_manifest(): manifest is missing 'build_id' "
            "-- expected the shape produced by "
            "generate_compiler_release_manifest()."
        )

    path = release_manifest_record_path(build_id)
    try:
        storage.upload_json(manifest, path=path, indent=2)
    except StorageError as exc:
        raise ReleaseManifestError(
            f"persist_release_manifest(): failed to persist release "
            f"manifest for build {build_id!r} via storage: {exc}"
        ) from exc

    logger.info("compiler_release: persisted release manifest %s -> %s", build_id, path)
    return {"release_manifest_path": path}


def load_release_manifest(storage: Any, build_id: str) -> Dict[str, Any]:
    """Loads a previously persisted CompilerReleaseManifest via
    `storage.download_json()`. Raises ReleaseManifestError if no such
    build_id was ever persisted, or if the storage read itself fails
    for any other reason."""
    path = release_manifest_record_path(build_id)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise ReleaseManifestError(
            f"load_release_manifest(): no release manifest found for build "
            f"{build_id!r}."
        ) from exc
    except StorageError as exc:
        raise ReleaseManifestError(
            f"load_release_manifest(): failed to load release manifest for "
            f"build {build_id!r} via storage: {exc}"
        ) from exc


def release_manifest_exists(storage: Any, build_id: str) -> bool:
    """True if a CompilerReleaseManifest was already persisted for
    `build_id`. Never raises -- mirrors storage.exists()'s own
    "existence is a plain bool, not a raise/don't-raise decision"
    contract, same as artifact_manager.persistence.build_exists() and
    cache.snapshot_store.snapshot_exists()."""
    return bool(storage.exists(path=release_manifest_record_path(build_id)))
