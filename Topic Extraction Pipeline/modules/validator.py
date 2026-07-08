"""
validator.py — final gate before a Chapter JSON hits disk.

Two checks, both required per the task spec:
  1. Structural completeness: every top-level section from the spec's
     schema list must be present (missing sections are filled with []/{}
     rather than causing a hard failure — the spec says "If any section is
     empty return [] or {}", not "omit it").
  2. Type/shape validation via the Pydantic ChapterJSON model, so a field
     with the wrong type (e.g. a string where a list was expected) is
     caught here instead of silently corrupting Phase 2's input.
"""
import logging
from typing import Dict, Any, Tuple, List

from pydantic import ValidationError
from schemas.chapter_schema import ChapterJSON
from schemas.educational_objects_schema import EducationalObjectsDocument

logger = logging.getLogger("ncert_pipeline.validator")

REQUIRED_SECTIONS = list(ChapterJSON.model_fields.keys())

_LIST_SECTIONS = {
    "pages", "topic_tree", "topics", "concepts", "glossary", "definitions",
    "examples", "activities", "figures", "tables", "equations", "diagrams",
    "charts", "graphs", "maps", "timelines", "boxes", "notes", "warnings",
    "semantic_index",
}
_DICT_SECTIONS = {
    "extraction_metadata", "document", "chapter_metadata", "chapter_statistics",
    "learning_graph", "concept_graph", "ai_metadata", "generation_metadata",
    "quality", "extraction_logs",
}


def fill_missing_sections(chapter_dict: Dict[str, Any]) -> Dict[str, Any]:
    for section in REQUIRED_SECTIONS:
        if section not in chapter_dict:
            if section in _LIST_SECTIONS:
                chapter_dict[section] = []
            elif section in _DICT_SECTIONS:
                chapter_dict[section] = {}
            logger.info("Section '%s' missing — filled with empty default.", section)
    return chapter_dict


def validate_chapter(chapter_dict: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Validates the FULL Chapter JSON / Master JSON shape
    (schemas/chapter_schema.py, including learning_graph/concept_graph/
    semantic_index). This IS Phase 1's actual, currently-used validation
    entry point: modules/json_writer.write_chapter_json calls this
    function on every chapter before writing it to disk (a previous
    revision of this docstring claimed the opposite -- see
    graph_builder.py's docstring for the same correction). On failure,
    the caller still writes the file but records the errors in
    extraction_logs rather than dropping the chapter, so a schema issue
    is surfaced without silently losing extracted data.
    Returns (is_valid, error_messages, normalized_dict). Never raises."""
    chapter_dict = fill_missing_sections(chapter_dict)
    try:
        model = ChapterJSON.model_validate(chapter_dict)
        return True, [], model.model_dump(by_alias=True)
    except ValidationError as e:
        errors = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        logger.error("Chapter JSON failed schema validation: %s", errors)
        return False, errors, chapter_dict


def validate_educational_objects_document(doc_dict: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Validates the narrower Educational Objects Document shape
    (schemas/educational_objects_schema.py, Stage D/E output only, no
    learning_graph/concept_graph/semantic_index). NOTE: pipeline.py does
    NOT currently call this -- its actual output path is
    assemble_chapter_json/write_chapter_json/validate_chapter above. This
    function (and modules/json_writer.assemble_educational_objects_document/
    write_educational_objects_json) is orphaned code from an earlier,
    superseded architectural decision; kept for any external caller that
    still wants the narrower shape, but not part of the active pipeline.
    Returns (is_valid, error_messages, normalized_dict). Never raises."""
    try:
        model = EducationalObjectsDocument.model_validate(doc_dict)
        return True, [], model.model_dump(by_alias=True)
    except ValidationError as e:
        errors = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        logger.error("Educational Objects Document failed schema validation: %s", errors)
        return False, errors, doc_dict
