"""
storage/migration.py — first-run migration of pre-existing local JSON
output (config.JSON_OUTPUT_FOLDER, e.g. ./json_out/) up to OneDrive, so
OneDrive becomes the pipeline's single persistent-storage source of truth
going forward.

This module is the ONLY thing in the project that reads json_out/ as a
*migration source*. modules/json_writer.py never reads from or writes to
it directly (all of its persistent reads/writes already go through
storage.OneDriveStorage) -- this module is a one-time bridge for whatever
was already on disk before the OneDrive backend existed, not an ongoing
storage path. Local files are NEVER deleted or modified by this module;
they are left in place as a backup, per the migration's design goal.

Local layout expected (matches the OneDrive layout modules/json_writer.py
writes to, minus the `<root>/<board>/` prefix and the per-book `json_out/`
subfolder -- both of which were introduced only when the OneDrive backend
was added, so pre-existing local data predates them):

    <local_root>/Class_<klass>/<Subject>/<Book>/<file>.json

    e.g. ./json_out/Class_12/Chemistry/Chemistry/01_solutions.json
      -> AI_TUTOR/<board>/Class_12/Chemistry/Chemistry/json_out/01_solutions.json

Idempotency / resumability:
  - A completion marker (`<root>/<board>/_migration_state.json`) on
    OneDrive is checked first (is_migration_complete()); if present, this
    module does nothing further.
  - Within a single migration run, any file already present on OneDrive
    with byte-identical content is skipped rather than re-uploaded -- so
    a run that was interrupted partway (crash, network failure) resumes
    on the next startup instead of re-uploading everything from scratch.
  - The completion marker is written ONLY after every discovered file has
    been uploaded AND verified (re-downloaded and byte-compared against
    the local copy). If any file fails to upload or verify,
    MigrationError is raised and no marker is written, so the next
    startup retries the whole thing.

Entry point for callers (see book_orchestrator.py's startup gate):
    ensure_migration_complete(storage, local_root, board)
"""
import os
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from .onedrive_storage import OneDriveStorage
from .exceptions import StorageError, NotFoundError, MigrationError

logger = logging.getLogger("storage.migration")

_MARKER_FILENAME = "_migration_state.json"
_CLASS_DIR_RE = re.compile(r"^Class_(.+)$", re.IGNORECASE)

__all__ = [
    "LocalFile",
    "MigrationError",
    "discover_local_files",
    "is_migration_complete",
    "migrate_local_data_to_onedrive",
    "ensure_migration_complete",
]


@dataclass
class LocalFile:
    local_path: str
    klass: str
    subject: str
    book: str
    filename: str


def _marker_path(storage: OneDriveStorage, board: str) -> str:
    return f"{storage.root_folder}/{board}/{_MARKER_FILENAME}"


def is_migration_complete(storage: OneDriveStorage, board: str) -> bool:
    """Returns True only if a completion marker written by a previous,
    fully-verified migration run exists on OneDrive. Never raises --
    any error reading the marker (including it simply not existing yet)
    is treated as "not complete"."""
    try:
        marker = storage.download_json(path=_marker_path(storage, board))
    except NotFoundError:
        return False
    except StorageError as e:
        logger.warning("migration: could not read completion marker (%s); treating as incomplete", e)
        return False
    return bool(marker.get("completed"))


def discover_local_files(local_root: str) -> List[LocalFile]:
    """Walks `local_root` for the Class_<N>/<Subject>/<Book>/<file>.json
    layout described in the module docstring. Anything that doesn't fit
    that exact shape (unexpected nesting, non-.json files, stray files at
    the wrong depth) is logged and skipped rather than raising -- one
    unexpected leftover under json_out/ shouldn't block every other book
    from migrating."""
    found: List[LocalFile] = []
    if not os.path.isdir(local_root):
        logger.info("migration: local root '%s' does not exist -- nothing to migrate", local_root)
        return found

    for klass_name in sorted(os.listdir(local_root)):
        klass_dir = os.path.join(local_root, klass_name)
        if not os.path.isdir(klass_dir):
            logger.warning("migration: skipping unexpected file at top level: '%s'", klass_dir)
            continue
        m = _CLASS_DIR_RE.match(klass_name)
        if not m:
            logger.warning("migration: skipping '%s' -- not a Class_<N> directory", klass_dir)
            continue
        klass = m.group(1)

        for subject in sorted(os.listdir(klass_dir)):
            subject_dir = os.path.join(klass_dir, subject)
            if not os.path.isdir(subject_dir):
                logger.warning("migration: skipping unexpected file '%s'", subject_dir)
                continue

            for book in sorted(os.listdir(subject_dir)):
                book_dir = os.path.join(subject_dir, book)
                if not os.path.isdir(book_dir):
                    logger.warning("migration: skipping unexpected file '%s'", book_dir)
                    continue

                for filename in sorted(os.listdir(book_dir)):
                    file_path = os.path.join(book_dir, filename)
                    if not os.path.isfile(file_path) or not filename.lower().endswith(".json"):
                        logger.warning("migration: skipping unexpected entry '%s'", file_path)
                        continue
                    found.append(LocalFile(file_path, klass, subject, book, filename))

    return found


def _remote_path(storage: OneDriveStorage, board: str, lf: LocalFile) -> str:
    book_dir = storage.resolve_path(board, lf.klass, lf.subject, lf.book)
    return f"{book_dir}/{lf.filename}"


def _upload_and_verify(storage: OneDriveStorage, remote_path: str, data: bytes) -> bool:
    """Uploads `data` to `remote_path` and re-downloads it to confirm the
    bytes match. Returns True if an upload actually happened, False if an
    identical copy was already present and the upload was skipped. Raises
    MigrationError if upload or verification fails."""
    if storage.exists(path=remote_path):
        try:
            existing = storage.download_file(path=remote_path)
        except StorageError as e:
            raise MigrationError(f"Could not read existing remote file '{remote_path}' to compare: {e}") from e
        if existing == data:
            logger.info("migration: '%s' already on OneDrive and matches local copy -- skipping", remote_path)
            return False
        logger.warning("migration: remote '%s' exists but differs from local copy -- re-uploading", remote_path)

    try:
        storage.upload_file(data, path=remote_path)
    except StorageError as e:
        raise MigrationError(f"Upload failed for '{remote_path}': {e}") from e

    try:
        verify = storage.download_file(path=remote_path)
    except StorageError as e:
        raise MigrationError(f"Could not re-download '{remote_path}' to verify upload: {e}") from e

    if verify != data:
        raise MigrationError(
            f"Verification failed for '{remote_path}': downloaded content does not match what was uploaded"
        )
    return True


def migrate_local_data_to_onedrive(storage: OneDriveStorage, local_root: str, board: str) -> Dict[str, Any]:
    """Uploads every local file discovered under `local_root` to OneDrive
    and verifies each one. Never deletes or modifies local files. Raises
    MigrationError (without writing the completion marker) on the first
    file that can't be uploaded/verified -- callers must not proceed to
    extraction in that case."""
    files = discover_local_files(local_root)
    logger.info("migration: found %d local JSON file(s) under '%s' to migrate", len(files), local_root)

    migrated = 0
    already_present = 0
    for lf in files:
        remote_path = _remote_path(storage, board, lf)
        with open(lf.local_path, "rb") as fh:
            data = fh.read()
        uploaded = _upload_and_verify(storage, remote_path, data)
        if uploaded:
            migrated += 1
        else:
            already_present += 1

    return {"found": len(files), "migrated": migrated, "already_present": already_present}


def ensure_migration_complete(storage: OneDriveStorage, local_root: str, board: str) -> None:
    """Startup gate: if migration has not yet completed, run it now
    (idempotent/resumable -- safe even if a previous attempt partially
    uploaded some files), then write the completion marker. Raises
    MigrationError on failure. The caller (book_orchestrator.py) is
    responsible for treating that as fatal and NOT starting PDF
    extraction -- extraction must never begin before migration
    completes."""
    if is_migration_complete(storage, board):
        logger.info("migration: already completed for board '%s' -- skipping", board)
        return

    logger.info("migration: not yet completed for board '%s' -- migrating local data from '%s' to OneDrive",
                 board, local_root)
    stats = migrate_local_data_to_onedrive(storage, local_root, board)

    storage.upload_json(
        {
            "completed": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "local_root": os.path.abspath(local_root),
            "board": board,
            **stats,
        },
        path=_marker_path(storage, board),
        indent=2,
    )
    logger.info(
        "migration: complete for board '%s' (%d found, %d migrated, %d already present on OneDrive).",
        board, stats["found"], stats["migrated"], stats["already_present"],
    )
