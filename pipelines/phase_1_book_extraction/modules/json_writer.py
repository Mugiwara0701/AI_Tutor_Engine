"""
json_writer.py — assembles Phase 1's Stage A-E output into ONE schema-shaped
dict per chapter, validates it, and writes it to:

    AI_TUTOR/<board>/Class_<klass>/<Subject>/<Book_Name>/json_out/<NN>_<chapter-slug>.json

plus a single .../json_out/_book_manifest.json per book (written once by
pipeline.py after all chapters in a book are done), via the OneDrive storage
SDK (storage/onedrive_storage.py) -- see book_output_dir() below, which is
the single place that talks to storage.OneDriveStorage.

This module does no PDF/model work itself — it is purely a shape-assembler +
file writer, so it's the one place that has to know the full schema layout.

Two output shapes live here:
  - assemble_chapter_json() / write_chapter_json() -- the full Master JSON
    shape (schemas/chapter_schema.py: topics/concepts/glossary/figures/
    tables/equations/.../learning_graph/concept_graph/semantic_index/
    ai_metadata/generation_metadata), extended (see REGRESSION_AUDIT.md) to
    also accept the Stage A-E `blocks`/`educational_objects`/
    `validation_report` output as additive fields. This is what
    pipeline.py calls.
  - assemble_educational_objects_document() / write_educational_objects_json()
    -- the narrower Phase-1-only shape (schemas/educational_objects_schema.py).
    Kept for any caller that wants just that document; pipeline.py no
    longer uses this as its primary output.
"""
import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from config import SCHEMA_VERSION, STORAGE_BOARD
from modules.pdf_parser import slugify, ChapterStructure, make_id
from modules.validator import validate_chapter, validate_educational_objects_document
from modules.stage_a_geometry import Block
from storage import OneDriveStorage

logger = logging.getLogger("ncert_pipeline.writer")

# Per-book subfolders provisioned automatically (alongside json_out/, which
# is where every write below actually lands) so a book's OneDrive folder is
# ready for logs/cache/asset writers that land in a future phase without
# needing another round of folder-creation code.
#
# Phase 1 Output Persistence Enhancement: _ARTIFACT_SUBFOLDERS below are
# additive siblings of json_out/ for the chapter-scoped Phase 1 artifacts
# that previously existed only in memory (Compiler IR registries, the
# Knowledge Graph, the Build Dependency Graph, Stage D validation
# reports, and Build Metadata) -- see artifact_output_dir()/
# artifact_output_path() further down. Folded into _BOOK_SUBFOLDERS so
# they are provisioned by the exact same book_output_dir() loop that
# already provisions logs/cache/assets, rather than a second
# folder-creation code path.
_ARTIFACT_SUBFOLDERS = (
    "registries",         # compiler/persistence.py       -- Compiler IR (Stage B) canonical registries
    "knowledge_graph",     # knowledge_graph/persistence.py -- Stage C Knowledge Graph
    "dependency_graph",    # dependency_graph/persistence.py -- Phase E2 Build Dependency Graph
    "validation",          # validation/persistence.py     -- Stage D1/D2/D3 validation reports
    "compiler_metadata",   # compiler/persistence.py       -- Compiler IR manifest/statistics/fingerprints/etc.
    "build_metadata",      # build_metadata/persistence.py -- Phase E1 Build Metadata
    "document_structure_tree",  # document_structure_tree/persistence.py -- Milestone 5/M6 Document
                                 # Structure Tree artifact. document_structure_tree/persistence.py's
                                 # ARTIFACT_TYPE == "document_structure_tree" already assumed this
                                 # folder existed via artifact_output_path()/artifact_output_dir() --
                                 # added here, mirroring every sibling artifact type above, so that
                                 # assumption actually holds (previously artifact_output_dir() raised
                                 # ValueError for this artifact_type, silently breaking DST persistence).
    "extraction_debug",    # extraction_debug/persistence.py -- Milestone 3.2 (Copyright-Safe
                            # Serialization) debug-only record of whatever
                            # modules.copyright_sanitizer stripped out of the production Chapter
                            # JSON (raw_text / reusable_procedure / procedure_steps /
                            # reusable_syntax / vlm_raw_output / vlm_validation_errors). Never
                            # written to json_out/ -- see extraction_debug/__init__.py.
)

_BOOK_SUBFOLDERS = ("json_out", "logs", "cache", "assets") + _ARTIFACT_SUBFOLDERS

_storage_singleton: Optional[OneDriveStorage] = None


def _get_storage() -> OneDriveStorage:
    """Lazily constructs (and reuses) the single OneDriveStorage client for
    this process. Lazy on purpose: importing this module (e.g. for
    schema-only tests) must not require config/storage.yaml to be filled in
    or trigger any auth. The first real read/write is what pays that cost.

    In the normal `python pipeline.py` / book_orchestrator.run() startup
    path, set_storage() below is called first (after the startup gate's
    Initialize Storage -> Authenticate -> migration steps have already
    run), so this lazy path only actually constructs a fresh client when
    json_writer is used standalone (e.g. a test or script that never goes
    through that startup gate)."""
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = OneDriveStorage()
    return _storage_singleton


def set_storage(storage: OneDriveStorage) -> None:
    """Lets a caller that already constructed (and authenticated) an
    OneDriveStorage instance -- book_orchestrator.py's startup gate, after
    first-run migration -- hand it to this module instead of _get_storage()
    lazily constructing (and re-authenticating) a second one."""
    global _storage_singleton
    _storage_singleton = storage


def get_storage() -> OneDriveStorage:
    """Public accessor for this module's own storage singleton -- lets
    another package (e.g. artifact_manager/, Phase F2) reuse the exact
    same already-authenticated OneDriveStorage instance book_orchestrator.
    run()'s startup gate handed to set_storage() above, instead of
    constructing (and re-authenticating) a second client. Thin wrapper
    around _get_storage(); exists purely so callers outside this module
    have a non-underscore-prefixed name to import."""
    return _get_storage()


def book_output_dir(klass: str, subject: str, book_slug: str, output_root: Optional[str] = None) -> str:
    """Returns the OneDrive-relative .../json_out/ path for this book (e.g.
    "AI_TUTOR/CBSE/Class_12/Chemistry/Solutions/json_out"), creating the
    book's full folder tree on OneDrive -- json_out/, logs/, cache/,
    assets/ -- if any of it doesn't already exist yet. This is the single
    source of truth for the output hierarchy -- chapter_output_path() and
    write_book_manifest() both call it, so the layout can't drift between
    the two.

    Class/Subject/Book -> folder-name formatting (Title_Case_With_Underscores)
    and the AI_TUTOR/<board>/ root are entirely owned by storage.PathResolver
    (see storage/path_resolver.py) -- this function no longer duplicates
    that formatting logic locally.

    `output_root`, when given, is a raw AI_TUTOR-relative *book* folder path
    used IN PLACE OF the Board/Class/Subject/Book resolution below (e.g. for
    a caller/test that wants to redirect one book's output under a
    different prefix); it is NOT a place to inject the book name again (the
    book_orchestrator used to do that locally, which produced a
    duplicated/misordered path -- output_root should name the *book's*
    folder directly, not a books-in-general root).
    """
    storage = _get_storage()
    book_dir = _resolve_book_dir(klass, subject, book_slug, output_root=output_root)

    for sub in _BOOK_SUBFOLDERS:
        storage.create_directory(path=f"{book_dir}/{sub}")

    return f"{book_dir}/json_out"


def _resolve_book_dir(klass: str, subject: str, book_slug: str, output_root: Optional[str] = None) -> str:
    """The book-folder-only half of book_output_dir()'s own path
    resolution (no `/json_out` suffix, no folder creation) -- extracted
    so book_output_dir() and artifact_output_dir() (Phase 1 Output
    Persistence Enhancement, below) resolve the exact same book root
    from the exact same logic instead of two copies drifting apart.
    Behavior is unchanged: book_output_dir() calls this and appends
    `/json_out` exactly as it always inlined this itself."""
    storage = _get_storage()
    return output_root.strip("/") if output_root is not None else \
        storage.resolve_path(STORAGE_BOARD, klass, subject, book_slug)


def artifact_output_dir(artifact_type: str, klass: str, subject: str, book_slug: str,
                         output_root: Optional[str] = None) -> str:
    """Phase 1 Output Persistence Enhancement: OneDrive-relative
    directory for one chapter-scoped Phase 1 artifact type (e.g.
    "knowledge_graph"), a sibling of json_out/ under the same book
    folder book_output_dir() already provisions. `artifact_type` must
    be one of _ARTIFACT_SUBFOLDERS -- every one of those folders is
    already created eagerly by book_output_dir()'s own loop over
    _BOOK_SUBFOLDERS (which now includes _ARTIFACT_SUBFOLDERS), and
    storage.upload_file()/upload_json() themselves ensure the
    destination folder exists on every write regardless -- so this
    function only resolves and returns the path, it does not need to
    create_directory() again.

    Callers that persist a chapter-scoped Phase 1 artifact before any
    chapter JSON has been written this run (e.g. a standalone script or
    test) still get a valid path -- the folder is created lazily by the
    first upload_json() call, same as every other OneDrive write in
    this codebase.
    """
    if artifact_type not in _ARTIFACT_SUBFOLDERS:
        raise ValueError(
            f"artifact_output_dir(): unknown artifact_type {artifact_type!r} -- "
            f"expected one of {_ARTIFACT_SUBFOLDERS!r}."
        )
    book_dir = _resolve_book_dir(klass, subject, book_slug, output_root=output_root)
    return f"{book_dir}/{artifact_type}"


def artifact_output_path(artifact_type: str, klass: str, subject: str, book_slug: str, chapter_number,
                          chapter_title: str, output_root: Optional[str] = None) -> str:
    """Phase 1 Output Persistence Enhancement: the artifact_output_dir()
    analogue of chapter_output_path() -- same "<NN>_<chapter-slug>.json"
    filename convention chapter_output_path() already uses (so a
    chapter's Chapter JSON and its Knowledge Graph/Dependency
    Graph/etc. records are trivially correlatable by filename), under
    the requested artifact_type's own folder instead of json_out/."""
    out_dir = artifact_output_dir(artifact_type, klass, subject, book_slug, output_root=output_root)
    chnum_str = str(chapter_number).zfill(2) if isinstance(chapter_number, int) else str(chapter_number)
    filename = f"{chnum_str}_{slugify(chapter_title)}.json"
    return f"{out_dir}/{filename}"


def chapter_output_path(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                         output_root: Optional[str] = None) -> str:
    out_dir = book_output_dir(klass, subject, book_slug, output_root=output_root)
    chnum_str = str(chapter_number).zfill(2) if isinstance(chapter_number, int) else str(chapter_number)
    filename = f"{chnum_str}_{slugify(chapter_title)}.json"
    return f"{out_dir}/{filename}"


def artifact_types() -> tuple:
    """Public accessor for _ARTIFACT_SUBFOLDERS -- the closed set of
    valid `artifact_type` values for artifact_output_dir()/
    artifact_output_path() -- so each artifact package's own
    persistence.py/discovery.py (compiler/, knowledge_graph/,
    dependency_graph/, validation/, build_metadata/) doesn't reach into
    this module's private constant directly. Mirrors artifact_manager.
    persistence.builds_root()'s own "public accessor for a private
    module constant" convention."""
    return _ARTIFACT_SUBFOLDERS


def is_already_extracted(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                          output_root: Optional[str] = None) -> bool:
    """Resumable extraction: if the chapter JSON already exists on
    OneDrive, skip it on re-run unless the caller explicitly forces
    re-processing."""
    file_path = chapter_output_path(klass, subject, book_slug, chapter_number, chapter_title,
                                     output_root=output_root)
    return _get_storage().exists(path=file_path)




def _flatten_blocks_to_dicts(blocks: Optional[List["Block"]]) -> List[Dict[str, Any]]:
    """Flattens the Stage A/B/C block tree (with children) into a flat list
    of block dicts, shared by both assemble_chapter_json (Master JSON,
    restored path) and assemble_educational_objects_document (Phase-1-only
    path, kept for compatibility). `blocks` may be None/empty (e.g.
    --no-vlm or a caller that never ran Stage A) -- returns [] in that case."""
    if not blocks:
        return []
    all_blocks_flat: List["Block"] = []

    def _flatten(b):
        all_blocks_flat.append(b)
        for c in b.children:
            _flatten(c)

    for b in blocks:
        _flatten(b)

    return [_block_to_dict(b) for b in all_blocks_flat]


def assemble_chapter_json(
    structure: ChapterStructure,
    pdf_path: str,
    topics_semantic: List[Dict[str, Any]],
    concepts: List[Dict[str, Any]],
    glossary: List[Dict[str, Any]],
    definitions: List[Dict[str, Any]],
    examples: List[Dict[str, Any]],
    activities: List[Dict[str, Any]],
    figures: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
    equations: List[Dict[str, Any]],
    diagrams: List[Dict[str, Any]],
    charts: List[Dict[str, Any]],
    graphs: List[Dict[str, Any]],
    maps: List[Dict[str, Any]],
    timelines: List[Dict[str, Any]],
    boxes: List[Dict[str, Any]],
    notes: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
    learning_graph: Dict[str, Any],
    concept_graph: Dict[str, Any],
    semantic_index: List[Dict[str, Any]],
    ai_metadata: Dict[str, Any],
    generation_metadata: Dict[str, Any],
    quality: Dict[str, float],
    extraction_logs: Dict[str, Any],
    ocr_engine_name: str,
    vlm_model_id: str,
    processing_time_seconds: float,
    blocks: Optional[List["Block"]] = None,
    educational_objects: Optional[List[Dict[str, Any]]] = None,
    validation_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """`blocks` / `educational_objects` / `validation_report` are additive,
    optional params (regression-fix restoration -- see REGRESSION_AUDIT.md):
    they let a caller fold the Stage A-E block/educational-object output
    into this same Master JSON instead of that output living in a separate
    document. Omitting them (the pre-existing call shape) still works and
    produces empty [] / {} sections, exactly like every other optional
    section here."""

    pages = []
    for pno in range(structure.num_pages):
        w, h = structure.page_sizes.get(pno, (0.0, 0.0))
        pages.append({
            "page_number": pno,
            "width": w,
            "height": h,
            "word_count": structure.page_word_counts.get(pno, 0),
            "has_figures": any(f["page"] == pno for f in figures),
            "has_tables": any(t["page"] == pno for t in tables),
            "has_equations": any(e["page"] == pno for e in equations),
            "ocr_confidence": None,  # filled by caller if OCR results are passed in via quality/extraction_logs
        })

    topic_tree = _build_topic_tree(topics_semantic)

    chapter_dict = {
        "schema_version": SCHEMA_VERSION,
        "extraction_metadata": {
            "pipeline_version": SCHEMA_VERSION,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "source_pdf": os.path.basename(pdf_path),
            "ocr_engine": ocr_engine_name,
            "vlm_model": vlm_model_id,
            "processing_time_seconds": processing_time_seconds,
        },
        "document": {
            "book_title": getattr(structure, "book_title", "untitled-book"),
            "subject": structure.subject,
            "class": structure.klass,
            "board": "NCERT",
            "language": [structure.language],
            # Phase 1 Final Metadata Architecture Refinement: canonical
            # cover metadata (never overwrites book_title above) + the two
            # derived identities. Additive/optional, same getattr()
            # pattern as book_title -- a bare ChapterStructure double that
            # predates this refinement still assembles a valid document.
            "book_subtitle": getattr(structure, "book_subtitle", None),
            "book_part": getattr(structure, "book_part", None),
            "book_volume": getattr(structure, "book_volume", None),
            "book_edition": getattr(structure, "book_edition", None),
            "educational_identity": getattr(structure, "educational_identity", None),
            "storage_identity": getattr(structure, "storage_identity", None),
        },
        "chapter_metadata": {
            "chapter_number": structure.chapter_number,
            "chapter_title": structure.chapter_title,
            "page_start": 0,
            "page_end": structure.num_pages - 1,
            "toc_matched": structure.toc_matched,
        },
        "chapter_statistics": {
            "total_pages": structure.num_pages,
            "total_words": sum(structure.page_word_counts.values()),
            "total_topics": len(topics_semantic),
            "total_figures": len(figures),
            "total_tables": len(tables),
            "total_equations": len(equations),
        },
        "pages": pages,
        "topic_tree": topic_tree,
        "topics": topics_semantic,
        "concepts": concepts,
        "glossary": glossary,
        "definitions": definitions,
        "examples": examples,
        "activities": activities,
        "figures": figures,
        "tables": tables,
        "equations": equations,
        "diagrams": diagrams,
        "charts": charts,
        "graphs": graphs,
        "maps": maps,
        "timelines": timelines,
        "boxes": boxes,
        "notes": notes,
        "warnings": warnings,
        "blocks": _flatten_blocks_to_dicts(blocks),
        "educational_objects": educational_objects or [],
        "validation_report": validation_report or {},
        "learning_graph": learning_graph,
        "concept_graph": concept_graph,
        "semantic_index": semantic_index,
        "ai_metadata": ai_metadata,
        "generation_metadata": generation_metadata,
        "quality": quality,
        "extraction_logs": extraction_logs,
    }
    return chapter_dict


def _build_topic_tree(topics_semantic: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Nested tree view (chapter -> topic -> sub-topic) derived from the
    flat `topics` list's parent/children links, for quick structural
    traversal without walking the flat list."""
    by_id = {t["id"]: {**t, "children_nodes": []} for t in topics_semantic}
    roots = []
    for t in topics_semantic:
        node = by_id[t["id"]]
        parent = t.get("parent")
        if parent and parent in by_id:
            by_id[parent]["children_nodes"].append(node)
        else:
            roots.append(node)

    def trim(node):
        return {
            "id": node["id"], "title": node["title"], "numbering": node.get("numbering"),
            "level": node.get("level"), "children": [trim(c) for c in node["children_nodes"]],
        }

    return [trim(r) for r in roots]


def write_chapter_json(chapter_dict: Dict[str, Any], klass: str, subject: str, book_slug: str,
                        chapter_number, chapter_title: str, output_root: Optional[str] = None) -> str:
    is_valid, errors, normalized = validate_chapter(chapter_dict)
    if not is_valid:
        normalized.setdefault("extraction_logs", {}).setdefault("errors", []).extend(
            [f"schema_validation: {e}" for e in errors])
        logger.warning("Writing chapter '%s' despite %d schema validation issue(s) (flagged in extraction_logs).",
                        chapter_title, len(errors))

    out_path = chapter_output_path(klass, subject, book_slug, chapter_number, chapter_title,
                                    output_root=output_root)
    _get_storage().upload_json(normalized, path=out_path, indent=2)
    logger.info("Wrote chapter JSON -> %s", out_path)
    return out_path


def write_book_manifest(klass: str, subject: str, book_slug: str, book_title: str, toc: Dict[str, Any],
                         output_root: Optional[str] = None, cover_subtitle: Optional[str] = None,
                         part: Optional[str] = None, volume: Optional[str] = None,
                         edition: Optional[str] = None, educational_identity: Optional[str] = None,
                         storage_identity: Optional[str] = None) -> str:
    """`cover_subtitle`/`part`/`volume`/`edition`/`educational_identity`/
    `storage_identity` are additive, optional params (Phase 1 Final
    Metadata Architecture Refinement) -- callers that omit them (the
    pre-refinement call shape) still produce a valid manifest with those
    keys simply set to None, same contract as every other optional field
    in this module."""
    out_dir = book_output_dir(klass, subject, book_slug, output_root=output_root)
    manifest_path = f"{out_dir}/_book_manifest.json"
    _get_storage().upload_json({
        "schema_version": SCHEMA_VERSION,
        "book_title": book_title,
        "book_subtitle": cover_subtitle,
        "book_part": part,
        "book_volume": volume,
        "book_edition": edition,
        "educational_identity": educational_identity,
        "storage_identity": storage_identity,
        "subject": subject,
        "class": klass,
        "table_of_contents": toc or {},
    }, path=manifest_path, indent=2)
    logger.info("Wrote book manifest -> %s", manifest_path)
    return manifest_path


# --------------------------------------------------------------------------
# Educational Objects Document (Stage A/B/C blocks + Stage D/E educational
# objects) -- kept for any caller that still wants the narrower Phase-1-only
# shape. As of the regression fix (see REGRESSION_AUDIT.md), pipeline.py no
# longer calls assemble_educational_objects_document/
# write_educational_objects_json below as its primary output -- it calls
# assemble_chapter_json/write_chapter_json above instead, passing blocks/
# educational_objects/validation_report into it so the Master JSON is a
# strict superset of both the old chapter JSON and this document's content.
# _block_to_dict is shared (via _flatten_blocks_to_dicts above) by both
# assembly functions so the two representations never drift apart.
# --------------------------------------------------------------------------
def _block_to_dict(block: Block) -> Dict[str, Any]:
    return {
        "block_id": block.block_id,
        "parent": block.parent,
        "block_type": block.block_type or "Ambiguous",
        "priority": block.priority or "medium",
        "confidence": block.confidence,
        "page": block.page,
        "page_end": block.page_end,
        "bbox": {"x0": block.bbox[0], "y0": block.bbox[1], "x1": block.bbox[2], "y1": block.bbox[3],
                 "page": block.page},
        "child_block_ids": [c.block_id for c in block.children],
    }


def assemble_educational_objects_document(
    structure: ChapterStructure,
    pdf_path: str,
    blocks: List[Block],
    educational_objects: List[Dict[str, Any]],
    validation_report: Dict[str, Any],
    quality: Dict[str, float],
    extraction_logs: Dict[str, Any],
    ocr_engine_name: str,
    vlm_model_id: str,
    processing_time_seconds: float,
    debug: bool = False,
    export_blocks: bool = False,
) -> Dict[str, Any]:
    """Assembles Phase 1's actual output shape: validated educational
    objects (Stage D/E) plus, ONLY when explicitly requested, the full
    Stage A/B/C annotated block graph for lineage/debugging.

    `blocks` is always received and always available to this function --
    the complete block hierarchy is never lost internally -- but it is only
    included in the returned/exported document when `debug` or
    `export_blocks` is True (mirroring config.DEBUG_MODE /
    config.EXPORT_BLOCKS, which is what pipeline.py passes by default).
    This keeps normal exports to `educational_objects` + minimal metadata,
    per the redesign goal of reducing JSON size; the schema itself
    (schemas/educational_objects_schema.py) is unchanged -- `blocks` simply
    defaults to `[]` when not populated here.

    Deliberately contains no learning_graph/concept_graph/semantic_index --
    those are Phase 2 work (see module docstring)."""
    include_blocks = debug or export_blocks

    blocks_out: List[Dict[str, Any]] = []
    if include_blocks:
        all_blocks_flat: List[Block] = []

        def _flatten(b: Block):
            all_blocks_flat.append(b)
            for c in b.children:
                _flatten(c)

        for b in blocks:
            _flatten(b)

        blocks_out = [_block_to_dict(b) for b in all_blocks_flat]

    return {
        "schema_version": SCHEMA_VERSION,
        "phase": "phase_1_educational_extraction",
        "extraction_metadata": {
            "pipeline_version": SCHEMA_VERSION,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "source_pdf": os.path.basename(pdf_path),
            "ocr_engine": ocr_engine_name,
            "vlm_model": vlm_model_id,
            "processing_time_seconds": processing_time_seconds,
        },
        "document": {
            "book_title": getattr(structure, "book_title", "untitled-book"),
            "subject": structure.subject,
            "class": structure.klass,
            "board": "NCERT",
            "language": [structure.language],
        },
        "chapter_metadata": {
            "chapter_number": structure.chapter_number,
            "chapter_title": structure.chapter_title,
            "page_start": 0,
            "page_end": structure.num_pages - 1,
            "toc_matched": structure.toc_matched,
        },
        "blocks": blocks_out,
        "educational_objects": educational_objects,
        "validation_report": validation_report,
        "quality": quality,
        "extraction_logs": extraction_logs,
    }


def write_educational_objects_json(doc_dict: Dict[str, Any], klass: str, subject: str, book_slug: str,
                                    chapter_number, chapter_title: str,
                                    output_root: Optional[str] = None) -> str:
    is_valid, errors, normalized = validate_educational_objects_document(doc_dict)
    if not is_valid:
        normalized.setdefault("extraction_logs", {}).setdefault("errors", []).extend(
            [f"schema_validation: {e}" for e in errors])
        logger.warning("Writing educational objects for '%s' despite %d schema validation issue(s) "
                        "(flagged in extraction_logs).", chapter_title, len(errors))

    out_path = chapter_output_path(klass, subject, book_slug, chapter_number, chapter_title,
                                    output_root=output_root)
    _get_storage().upload_json(normalized, path=out_path, indent=2)
    logger.info("Wrote educational objects JSON -> %s", out_path)
    return out_path