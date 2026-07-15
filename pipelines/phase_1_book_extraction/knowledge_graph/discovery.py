"""
knowledge_graph/discovery.py — Phase 1 Output Persistence Enhancement:
discovery for persisted Knowledge Graph records
(knowledge_graph/persistence.py).

Reuses `storage.list_directory()` over
`modules.json_writer.artifact_output_dir()`, mirroring
`compiler/discovery.py`'s own convention one package over. One bad
record is skipped with a logged warning rather than failing the whole
listing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

from .persistence import ARTIFACT_TYPE, PersistenceError

logger = logging.getLogger("knowledge_graph.discovery")


def list_knowledge_graphs(storage: Any, klass: str, subject: str, book_slug: str,
                           output_root=None) -> List[str]:
    """Every persisted <NN>_<chapter-slug>.json filename under this
    book's knowledge_graph/ folder, sorted. Empty list if the folder
    doesn't exist yet -- not an error."""
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


def knowledge_graph_history(storage: Any, klass: str, subject: str, book_slug: str,
                             output_root=None) -> List[Dict[str, Any]]:
    """Every persisted chapter's Knowledge Graph record for this book,
    in list_knowledge_graphs()'s own filename order. Downloads by the
    exact listed path rather than reconstructing a chapter_title from
    the filename (slugify() is not guaranteed invertible). A record
    that fails to load is skipped with a logged warning rather than
    failing the whole history call."""
    out_dir = json_writer.artifact_output_dir(ARTIFACT_TYPE, klass, subject, book_slug,
                                               output_root=output_root)
    history: List[Dict[str, Any]] = []
    for filename in list_knowledge_graphs(storage, klass, subject, book_slug, output_root=output_root):
        path = f"{out_dir}/{filename}"
        try:
            history.append(storage.download_json(path=path))
        except Exception:
            logger.warning(
                "knowledge_graph.discovery: skipping %s in knowledge_graph_history() -- "
                "its record could not be loaded.", filename, exc_info=True,
            )
    return history