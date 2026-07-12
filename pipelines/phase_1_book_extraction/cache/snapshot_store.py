"""
cache/snapshot_store.py — Phase F4.1: fingerprint snapshot persistence.

REUSE, DON'T INVENT (same rule artifact_manager/persistence.py already
states for Phase F2, one package over): this module never constructs
its own OneDriveStorage client and never authenticates -- every
function here receives an already-authenticated storage instance (the
exact same one modules.json_writer.get_storage() already returns).
Persistence itself is upload_json()/download_json()/exists()/
list_directory() -- the identical surface artifact_manager/
persistence.py already uses for the Build and Build Manifest -- there
is no second serialization format, no second storage client, and no
local-filesystem or database fallback introduced here.

WHAT A CacheEntry ACTUALLY CONTAINS -- AN HONEST LIMITATION, NOT A NEW
ONE: `build_cache_entry()` below reads `build.build_manifest[
"fingerprints"]` verbatim -- the exact `{compiler_fingerprint,
graph_fingerprint, configuration_fingerprint}` dict Phase F2's own
manifest.py already computed (see artifact_manager/manifest.py's own
`_collect_fingerprints()`). That dict is already, by Phase F2's own
frozen design, a snapshot of whichever chapter was most recently
processed when the run finished (see artifact_manager/build.py's own
module docstring for why: Phases A-E1's own compiler/knowledge-graph
state is chapter-scoped and reset every chapter, so a Build spanning a
whole run has no single "the" per-chapter fingerprint set to persist,
only the last one). This module does not widen that scope, invent a
per-chapter fingerprint index of its own, or introduce a new
fingerprinting algorithm -- it persists exactly what Phase F2 already
computed, so a LATER run can finally read what a PREVIOUS run's own
last-processed-chapter fingerprints were, which today nothing in this
codebase can do (see change_detection/snapshot.py's own "NO
PERSISTENCE" section and pipeline.py's own `previous_build=None` call
site -- this module is what finally supplies a non-None value for a
FUTURE run, not this run's own change_detection.detect_changes() call,
which has already completed by the time Phase F4.1 runs).

LAYOUT: mirrors artifact_manager/persistence.py's own `_runtime_builds/`
layout exactly, one sibling root over -- deliberately NOT nested inside
`_runtime_builds/<build_id>/`, so Phase F2's own build record folder
never needs to know Phase F4.1 exists (F0 §13: "Phase F MUST NOT
redesign previous phases"):

    _runtime_cache/<build_id>/fingerprint_snapshot.json
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from storage.exceptions import NotFoundError, StorageError

from .exceptions import CacheReadError, CacheWriteError

logger = logging.getLogger("cache.snapshot_store")

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase, bumped only if the CacheEntry
# SHAPE this module produces itself changes in a way a consumer should
# be able to detect.
CACHE_ENTRY_VERSION = "F4.1"

_CACHE_ROOT = "_runtime_cache"


def cache_root() -> str:
    """Public accessor for this module's cache-history root path --
    mirrors artifact_manager.persistence.builds_root()'s own role, one
    package over, so index.py never reaches into a private constant
    here directly."""
    return _CACHE_ROOT


def _cache_dir(build_id: str) -> str:
    return f"{_CACHE_ROOT}/{build_id}"


def snapshot_record_path(build_id: str) -> str:
    return f"{_cache_dir(build_id)}/fingerprint_snapshot.json"


def build_cache_entry(build: Any) -> Dict[str, Any]:
    """Assembles this run's own CacheEntry directly from an
    already-constructed, already-manifested Build (Phase F2) -- reads
    `build.build_manifest["fingerprints"]` verbatim (see module
    docstring). Never recomputes a fingerprint, never re-derives
    `build_status`/`generated_at` (both are read straight off the same
    manifest Phase F2 already generated).

    Raises CacheWriteError if `build` is None or has no
    `build_manifest` attached yet (Phase F2's own `_record_build()`
    always attaches one via `Build.with_manifest()` before this run's
    Build is ever recorded -- this only fires for a hand-constructed
    Build missing it, or a run where Phase F2's own bookkeeping itself
    already failed and logged -- see runtime/runtime.py's own
    `_record_cache()` docstring for how that case is handled)."""
    if build is None or not getattr(build, "build_manifest", None):
        raise CacheWriteError(
            "build_cache_entry(): build.build_manifest is required to "
            "assemble a CacheEntry (Phase F2's own _record_build() always "
            "attaches one via Build.with_manifest() before a successful "
            "run is recorded)."
        )
    manifest = build.build_manifest
    return {
        "cache_entry_version": CACHE_ENTRY_VERSION,
        "build_id": build.build_id,
        "generated_at": manifest.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "build_status": manifest.get("build_status"),
        # Verbatim -- see module docstring's "WHAT A CacheEntry ACTUALLY
        # CONTAINS" section. Never recomputed here.
        "fingerprint_snapshot": dict(manifest.get("fingerprints") or {}),
    }


def persist_fingerprint_snapshot(storage: Any, cache_entry: Dict[str, Any]) -> Dict[str, str]:
    """Persists a CacheEntry (build_cache_entry()'s own return shape)
    as its own JSON record, via `storage.upload_json()` -- the exact
    reused persistence utility, not a new one. Returns the
    AI_TUTOR-relative path written to.

    Raises CacheWriteError, chaining the original storage.exceptions
    error, if `cache_entry` is missing `build_id` or the upload
    itself fails."""
    build_id = cache_entry.get("build_id")
    if not build_id:
        raise CacheWriteError(
            "persist_fingerprint_snapshot(): cache_entry is missing "
            "'build_id' -- expected the shape produced by "
            "build_cache_entry()."
        )

    path = snapshot_record_path(build_id)
    try:
        storage.upload_json(cache_entry, path=path, indent=2)
    except StorageError as exc:
        raise CacheWriteError(
            f"persist_fingerprint_snapshot(): failed to persist fingerprint "
            f"snapshot for build {build_id!r} via storage: {exc}"
        ) from exc

    logger.info("cache: persisted fingerprint snapshot %s -> %s", build_id, path)
    return {"snapshot_path": path}


def load_fingerprint_snapshot(storage: Any, build_id: str) -> Dict[str, Any]:
    """Loads a previously persisted CacheEntry (build_cache_entry()'s
    own shape) via `storage.download_json()`. Raises CacheReadError if
    no such build_id was ever cached, or if the storage read itself
    fails for any other reason."""
    path = snapshot_record_path(build_id)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise CacheReadError(build_id, "no cached fingerprint snapshot found") from exc
    except StorageError as exc:
        raise CacheReadError(
            build_id, f"storage read failed: {exc}"
        ) from exc


def snapshot_exists(storage: Any, build_id: str) -> bool:
    """True if a fingerprint snapshot was already persisted for
    `build_id`. Never raises -- mirrors storage.exists()'s own
    "existence is a plain bool, not a raise/don't-raise decision"
    contract, same as artifact_manager.persistence.build_exists()."""
    return bool(storage.exists(path=snapshot_record_path(build_id)))


def load_previous_cache_entry(
    storage: Any, *, before_build_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Returns the most recently persisted CacheEntry in full
    (build_cache_entry()'s own shape: `build_id`/`generated_at`/
    `build_status`/`fingerprint_snapshot`) -- the most recent cached
    build strictly before `before_build_id` (build ids sort
    chronologically by construction, see artifact_manager.build.
    _generate_build_id()), or the most recent cached build overall if
    `before_build_id` is None.

    Returns None if no cache entry exists yet (first run ever, or
    first run after this codebase's cache root was introduced) --
    not an error, mirroring every other "nothing yet is a normal
    state" convention in this codebase (e.g.
    artifact_manager.discovery.list_builds()'s own empty-list case).
    Also returns None (rather than raising) if the most recent entry's
    own record cannot be loaded -- one unreadable cache record must not
    fail an otherwise-successful run, same "a broken observer must
    never abort the run" principle every other Phase F integration
    point already applies."""
    from .index import list_cache_entries  # local import: avoids a
    # circular import at module-load time (index.py itself does not
    # import snapshot_store at its own top level either, but this
    # mirrors this codebase's own established "local import for
    # cross-module-in-same-package calls where helpful" convention --
    # see e.g. build_executor/executor.py's own module docstring).

    entries = list_cache_entries(storage)
    if before_build_id is not None:
        entries = [build_id for build_id in entries if build_id < before_build_id]
    if not entries:
        return None

    latest_build_id = entries[-1]
    try:
        return load_fingerprint_snapshot(storage, latest_build_id)
    except CacheReadError:
        logger.warning(
            "cache: most recent cache entry %s could not be loaded; "
            "treating this run as having no previous fingerprint "
            "snapshot.", latest_build_id, exc_info=True,
        )
        return None


def load_previous_fingerprint_snapshot(
    storage: Any, *, before_build_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Returns just the most recently persisted CacheEntry's own
    `fingerprint_snapshot` sub-field -- a thin convenience wrapper
    around load_previous_cache_entry() for a caller that only wants
    the fingerprint map itself (e.g. a future, out-of-scope caller
    wiring this into change_detection.engine.detect_changes()'s own
    `previous_build` argument, which expects a bare fingerprint map,
    not a full CacheEntry). Returns None under the exact same
    conditions load_previous_cache_entry() does.

    This is the one function that finally gives a caller a real,
    non-None fingerprint value computed by a PREVIOUS run -- see
    module docstring's own "WHAT A CacheEntry ACTUALLY CONTAINS"
    section for exactly what shape that is (and is not)."""
    cache_entry = load_previous_cache_entry(storage, before_build_id=before_build_id)
    if cache_entry is None:
        return None
    return cache_entry.get("fingerprint_snapshot")