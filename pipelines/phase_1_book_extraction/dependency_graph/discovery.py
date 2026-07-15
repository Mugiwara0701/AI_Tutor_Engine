"""
dependency_graph/discovery.py — Phase 1 Output Persistence Enhancement:
discovery for persisted Dependency Graph records
(dependency_graph/persistence.py). Mirrors
knowledge_graph/discovery.py's own convention one package over.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

from .persistence import ARTIFACT_TYPE, PersistenceError

logger = logging.getLogger("dependency_graph.discovery")


def list_dependency_graphs(storage: Any, klass: str, subject: str, book_slug: str,
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


def dependency_graph_history(storage: Any, klass: str, subject: str, book_slug: str,
                              output_root=None) -> List[Dict[str, Any]]:
    """Every persisted chapter's Dependency Graph record for this book,
    in list_dependency_graphs()'s own filename order. A record that
    fails to load is skipped with a logged warning."""
    out_dir = json_writer.artifact_output_dir(ARTIFACT_TYPE, klass, subject, book_slug,
                                               output_root=output_root)
    history: List[Dict[str, Any]] = []
    for filename in list_dependency_graphs(storage, klass, subject, book_slug, output_root=output_root):
        path = f"{out_dir}/{filename}"
        try:
            history.append(storage.download_json(path=path))
        except Exception:
            logger.warning(
                "dependency_graph.discovery: skipping %s in dependency_graph_history() -- "
                "its record could not be loaded.", filename, exc_info=True,
            )
    return history