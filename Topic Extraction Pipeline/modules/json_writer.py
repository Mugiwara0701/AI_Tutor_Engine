"""
json_writer.py — assembles Phase 1's Stage A-E output into ONE schema-shaped
dict per chapter, validates it, and writes it to:

    json_out/Class_<klass>/<Subject>/<Book_Name>/<NN>_<chapter-slug>.json

plus a single json_out/Class_<klass>/<Subject>/<Book_Name>/_book_manifest.json
per book (written once by pipeline.py after all chapters in a book are done).

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
import re
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from config import JSON_OUTPUT_FOLDER, SCHEMA_VERSION
from modules.pdf_parser import slugify, ChapterStructure, make_id
from modules.validator import validate_chapter, validate_educational_objects_document
from modules.stage_a_geometry import Block

logger = logging.getLogger("ncert_pipeline.writer")


def _dir_component(text: str) -> str:
    """Formats one Class/Subject/Book folder-name component as
    Title_Case_With_Underscores (e.g. "business studies" ->
    "Business_Studies", "introductory-macroeconomics" -> "Introductory_Macroeconomics"),
    per the required json_out/Class_Name/Subject_Name/Book_Name/ layout.

    Deliberately separate from slugify() (lowercase-hyphenated), which is
    left untouched and still used for chapter filenames / topic & figure
    IDs elsewhere -- this only changes how directory *names* are rendered.
    """
    words = [w for w in re.split(r"[\s_-]+", str(text).strip()) if w]
    return "_".join(w[:1].upper() + w[1:] for w in words) if words else "Untitled"


def book_output_dir(klass: str, subject: str, book_slug: str, output_root: Optional[str] = None) -> str:
    """Returns json_out/Class_<klass>/<Subject>/<Book_Name>/, creating it if
    needed. This is the single source of truth for the output hierarchy --
    chapter_output_path() and write_book_manifest() both call it, so the
    layout can't drift between the two.

    `output_root` overrides the base JSON_OUTPUT_FOLDER for this call only;
    it is NOT a place to inject the book name again (the book_orchestrator
    used to do that, which produced a duplicated/misordered path like
    json_out/<book>/class_<klass>/<subject>/<book>/... -- output_root should
    just be JSON_OUTPUT_FOLDER, or another books-in-general root).
    """
    base = output_root if output_root is not None else JSON_OUTPUT_FOLDER
    out_dir = os.path.join(base, f"Class_{_dir_component(str(klass))}",
                            _dir_component(subject), _dir_component(book_slug))
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def chapter_output_path(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                         output_root: Optional[str] = None) -> str:
    out_dir = book_output_dir(klass, subject, book_slug, output_root=output_root)
    chnum_str = str(chapter_number).zfill(2) if isinstance(chapter_number, int) else str(chapter_number)
    filename = f"{chnum_str}_{slugify(chapter_title)}.json"
    return os.path.join(out_dir, filename)


def is_already_extracted(klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
                          output_root: Optional[str] = None) -> bool:
    """Resumable extraction: if the chapter JSON already exists, skip it on
    re-run unless the caller explicitly forces re-processing."""
    return os.path.exists(chapter_output_path(klass, subject, book_slug, chapter_number, chapter_title,
                                               output_root=output_root))


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
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
    logger.info("Wrote chapter JSON -> %s", out_path)
    return out_path


def write_book_manifest(klass: str, subject: str, book_slug: str, book_title: str, toc: Dict[str, Any],
                         output_root: Optional[str] = None) -> str:
    out_dir = book_output_dir(klass, subject, book_slug, output_root=output_root)
    manifest_path = os.path.join(out_dir, "_book_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "schema_version": SCHEMA_VERSION,
            "book_title": book_title,
            "subject": subject,
            "class": klass,
            "table_of_contents": toc or {},
        }, f, indent=2, ensure_ascii=False)
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
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
    logger.info("Wrote educational objects JSON -> %s", out_path)
    return out_path