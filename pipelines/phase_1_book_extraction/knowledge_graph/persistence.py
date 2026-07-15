"""
knowledge_graph/persistence.py — Phase 1 Output Persistence Enhancement:
chapter-scoped persistence for the Knowledge Graph (Stage C).

BACKGROUND: Stage C (`knowledge_graph/`) builds one `KnowledgeGraph` per
chapter (metadata + a `GraphRegistryManager` populated with nodes and
edges, see PHASE1_ARCHITECTURE.md §4), plus the manifest/statistics/
validation report/fingerprints/readiness report/build summary/final
status that describe that build. Before this module existed, every one
of those artifacts lived only in `knowledge_graph/state.py`'s
module-level "current chapter" slots and was never durably persisted --
the Knowledge Graph is not part of the Chapter JSON at all (see
COMPILER_PIPELINE.md §3, step 4: "never touches chapter_dict"). This
module is purely additive: it does not change what Stage C computes,
only what happens to that output afterward.

REUSE, DON'T INVENT: same `storage.upload_json()`/`download_json()`/
`exists()` surface every other persisted phase in this codebase already
uses, via an already-authenticated `OneDriveStorage` instance the
caller supplies. Path layout is
`modules.json_writer.artifact_output_path("knowledge_graph", ...)`, the
same "<NN>_<chapter-slug>.json" filename convention the Chapter JSON
itself uses.

ONE RECORD, NOT SEVEN: unlike compiler/persistence.py's two-artifact
split (registries vs. metadata), this module persists the whole
Knowledge Graph -- metadata, nodes, edges, manifest, statistics,
validation report, fingerprints, readiness report, build summary, and
final status -- as one JSON record per chapter, mirroring the single
`knowledge_graph/` folder Phase 1's own output-structure design calls
for (one graph, one file, per chapter) rather than seven small files
that would all need to be loaded together to mean anything.

`KnowledgeGraph.nodes`/`.edges` (knowledge_graph/schema.py) are BOTH
set, by pipeline.py, to the same `GraphRegistryManager` instance (see
that module's own docstring) -- calling `KnowledgeGraph.to_dict()`
directly would therefore embed that live Python object twice, which
`storage.upload_json()`'s `json.dumps()` cannot serialize. This module
calls the registry manager's own `.serialize()` (the exact method
compiler/persistence.py already reuses for Compiler IR registries) once
and nests its result under "registries" instead, so the persisted
record is plain, JSON-serializable data throughout.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules import json_writer
from storage.exceptions import NotFoundError, StorageError

from .registries import GraphRegistryManager
from .schema import KnowledgeGraphMetadata

logger = logging.getLogger("knowledge_graph.persistence")


class PersistenceError(Exception):
    """Raised when persisting or loading a Knowledge Graph record fails
    for a reason other than "no such record exists yet" (that is
    KnowledgeGraphNotFoundError, below)."""


class KnowledgeGraphNotFoundError(PersistenceError):
    """Raised by load_knowledge_graph() when no record was ever
    persisted for the given chapter."""


ARTIFACT_TYPE = "knowledge_graph"


def knowledge_graph_record_path(klass: str, subject: str, book_slug: str, chapter_number,
                                 chapter_title: str, output_root: Optional[str] = None) -> str:
    return json_writer.artifact_output_path(
        ARTIFACT_TYPE, klass, subject, book_slug, chapter_number, chapter_title,
        output_root=output_root,
    )


def persist_knowledge_graph(
    storage: Any,
    klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
    *,
    metadata: KnowledgeGraphMetadata,
    registry_manager: GraphRegistryManager,
    manifest: Dict[str, Any],
    statistics: Dict[str, Any],
    validation_report: Dict[str, Any],
    registry_fingerprints: Dict[str, str],
    graph_fingerprint: str,
    readiness_report: Dict[str, Any],
    build_summary: Dict[str, Any],
    final_status: str,
    output_root: Optional[str] = None,
) -> str:
    """Persists this chapter's complete Knowledge Graph. Every argument
    is passed in verbatim (never recomputed here) from what pipeline.py's
    own Stage C call sequence already produced (knowledge_graph/
    build_nodes.py, build_edges.py, validation.py, build.py,
    fingerprints.py, finalize.py). Returns the OneDrive-relative path
    written to. Raises PersistenceError, chaining the original storage
    error, if the upload fails."""
    path = knowledge_graph_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                        output_root=output_root)
    record = {
        "metadata": metadata.to_dict(),
        "registries": registry_manager.serialize(),
        "manifest": manifest,
        "statistics": statistics,
        "validation_report": validation_report,
        "registry_fingerprints": registry_fingerprints,
        "graph_fingerprint": graph_fingerprint,
        "readiness_report": readiness_report,
        "build_summary": build_summary,
        "final_status": final_status,
    }
    try:
        storage.upload_json(record, path=path, indent=2)
    except StorageError as exc:
        raise PersistenceError(
            f"persist_knowledge_graph(): failed to persist Knowledge Graph for "
            f"chapter {chapter_title!r} via storage: {exc}"
        ) from exc
    logger.info("knowledge_graph.persistence: persisted Knowledge Graph -> %s", path)
    return path


def load_knowledge_graph(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                          chapter_title: str, output_root: Optional[str] = None) -> Dict[str, Any]:
    """Loads a previously persisted Knowledge Graph record (plain dict,
    the shape persist_knowledge_graph() wrote). `record["registries"]`
    can be passed straight to `GraphRegistryManager.deserialize()` to
    rebuild a real registry manager. Raises KnowledgeGraphNotFoundError
    if no such record was ever persisted, or PersistenceError if the
    storage read itself fails for any other reason."""
    path = knowledge_graph_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                        output_root=output_root)
    try:
        return storage.download_json(path=path)
    except NotFoundError as exc:
        raise KnowledgeGraphNotFoundError(f"no Knowledge Graph record found at {path!r}") from exc
    except StorageError as exc:
        raise PersistenceError(
            f"load_knowledge_graph(): failed to load Knowledge Graph at {path!r} "
            f"via storage: {exc}"
        ) from exc


def knowledge_graph_exists(storage: Any, klass: str, subject: str, book_slug: str, chapter_number,
                            chapter_title: str, output_root: Optional[str] = None) -> bool:
    path = knowledge_graph_record_path(klass, subject, book_slug, chapter_number, chapter_title,
                                        output_root=output_root)
    return bool(storage.exists(path=path))