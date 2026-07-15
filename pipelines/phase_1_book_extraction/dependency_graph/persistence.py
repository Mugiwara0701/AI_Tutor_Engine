"""
dependency_graph/persistence.py — Phase 1 Output Persistence
Enhancement: chapter-scoped persistence for the Build Dependency Graph
(Phase E2).

BACKGROUND: Phase E2 (`dependency_graph/`) builds one `DependencyGraph`
per chapter -- which compiler artifact was built from which other
artifact, this chapter (see PHASE1_ARCHITECTURE.md §6) -- via
`dependency_graph.build.generate_dependency_graph()`. That function
already returns `{"dependency_graph": graph.to_dict()}`, and
`DependencyGraph.to_dict()` (dependency_graph/schema.py) is already a
plain, fully JSON-serializable dict (metadata dict + nodes list of
dicts + edges list of dicts -- see that module's own docstring: "every
node and edge, already serialized"). Before this module existed, that
dict lived only in `dependency_graph/state.py`'s "current chapter" slot
and was never durably persisted. This module is purely additive: it
does not change what Phase E2 computes, only what happens to that
output afterward.

REUSE, DON'T INVENT: same `storage.upload_json()`/`download_json()`/
`exists()` surface every other persisted phase in this codebase already
uses. Path layout is
`modules.json_writer.artifact_output_path("dependency_graph", ...)`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

logger = logging.getLogger("dependency_graph.persistence")


class PersistenceError(Exception):
    """Raised when persisting or loading a Dependency Graph record
    fails for a reason other than "no such record exists yet" (that is
    DependencyGraphNotFoundError, below)."""


class DependencyGraphNotFoundError(PersistenceError):
    """Raised by load_dependency_graph() when no record was ever
    persisted for the given chapter."""


ARTIFACT_TYPE = "dependency_graph"


def dependency_graph_record_path(klass: str, subject: str, book_slug: str, chapter_number,
                                  chapter_title: str, output_root: Optional[str] = None) -> str:
    return json_writer.artifact_output_path(
        ARTIFACT_TYPE, klass, subject, book_slug, chapter_number, chapter_title,
        output_root=output_root,
    )


def persist_dependency_graph(storage: Any, dependency_graph: Dict[str, Any], klass: str, subject: str,
                              book_slug: str, chapter_number, chapter_title: str,
                              output_root: Optional[str] = None) -> str:
    """Persists this chapter's Dependency Graph. `dependency_graph`
    must be the already-computed dict
    `dependency_graph.build.generate_dependency_graph(...)["dependency_graph"]`
    produced -- never recomputed or reshaped here. Returns the
    OneDrive-relative path written to. Raises PersistenceError,
    chaining the original storage error, if the upload fails."""
    path = dependency_graph_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                         output_root=output_root)
    try:
        storage.upload_json(dependency_graph, path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_dependency_graph(): failed to persist dependency graph for "
            f"chapter {chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("dependency_graph.persistence: persisted dependency graph -> %s", path)
    return path


def load_dependency_graph(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                           chapter_title: str, output_root: Optional[str] = None) -> Dict[str, Any]:
    path = dependency_graph_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                         output_root=output_root)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise DependencyGraphNotFoundError(f"no dependency graph record found at {path!r}") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_dependency_graph(): failed to load dependency graph at {path!r} "
            f"via storage: {exc}"
        ) from exc


def dependency_graph_exists(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                             chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = dependency_graph_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                         output_root=output_root)
    return bool(storage.exists(path=path))