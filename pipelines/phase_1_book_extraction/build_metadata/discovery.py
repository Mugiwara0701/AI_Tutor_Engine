"""
build_metadata/discovery.py — Phase 1 Output Persistence Enhancement:
discovery for persisted Build Metadata records
(build_metadata/persistence.py). Mirrors knowledge_graph/discovery.py's
own convention.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

from .persistence import ARTIFACT_TYPE, PersistenceError

logger = logging.getLogger("build_metadata.discovery")


def list_build_metadata(storage: Any, klass: str, subject: str, book_slug: str,
                         output_root=None) -> List[str]:
    out_dir = json_writer.artifact_output_dir(ARTIFACT_TYPE, klass, subject, book_slug,
                                               output_root=output_root)
    try:
        entries = storage.list_directory(path=out_dir)
    except NotFoundError:
        return []
    except StorageError as exc:
        raise PersistenceError(f"failed to list {out_dir!r}: {exc}") from exc
    return sorted(
        entry["name"] for entry in entries
        if not entry.get("is_folder") and entry["name"].endswith(".json")
    )


def build_metadata_history(storage: Any, klass: str, subject: str, book_slug: str,
                            output_root=None) -> List[Dict[str, Any]]:
    """Every persisted chapter's Build Metadata record for this book,
    in list_build_metadata()'s own filename order. A record that fails
    to load is skipped with a logged warning."""
    out_dir = json_writer.artifact_output_dir(ARTIFACT_TYPE, klass, subject, book_slug,
                                               output_root=output_root)
    history: List[Dict[str, Any]] = []
    for filename in list_build_metadata(storage, klass, subject, book_slug, output_root=output_root):
        path = f"{out_dir}/{filename}"
        try:
            history.append(storage.download_json(path=path))
        except Exception:
            logger.warning(
                "build_metadata.discovery: skipping %s in build_metadata_history() -- "
                "its record could not be loaded.", filename, exc_info=True,
            )
    return history