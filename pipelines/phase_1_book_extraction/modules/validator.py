"""
validator.py — final gate before a Chapter JSON hits disk.

Originally two checks, both required per the task spec:
  1. Structural completeness (section presence): every top-level section
     from the spec's schema list must be present (missing sections are
     filled with []/{} rather than causing a hard failure — the spec
     says "If any section is empty return [] or {}", not "omit it").
  2. Type/shape validation via the Pydantic ChapterJSON model, so a field
     with the wrong type (e.g. a string where a list was expected) is
     caught here instead of silently corrupting Phase 2's input.

MILESTONE 2 ADDITION (Structural Validation): (1)+(2) above only ever
checked EXTRACTION QUALITY -- does the dict have the right shape/types?
They say nothing about whether the document is internally coherent: a
`topic_ids` entry that points at a topic id nobody ever defined, two
objects that were assigned the same `id`, a `learning_graph` edge whose
source/target was never declared as a node, and so on all sail straight
through (1)+(2) untouched. `validate_chapter()` below now runs a THIRD,
independent check for exactly that class of problem --
`modules.structural_validator.validate_structural_completeness()` -- and
folds its findings into both the returned `errors` list and `is_valid`,
so a document that is schema-valid but structurally broken is no longer
reported as valid. See modules/structural_validator.py's own module
docstring for the full rule list and severity scheme (ERROR/WARNING/
INFO). This is additive: nothing about the existing two checks' own
behavior changed, and every previously-passing chapter that was ALSO
structurally sound still returns `is_valid=True` with an unchanged
`errors` list.
"""
import logging
from typing import Dict, Any, Tuple, List

from pydantic import ValidationError
from schemas.chapter_schema import ChapterJSON
from schemas.educational_objects_schema import EducationalObjectsDocument
from modules.structural_validator import validate_structural_completeness

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


def _merge_structural_report_into_logs(normalized: Dict[str, Any], structural_report: Dict[str, Any]) -> None:
    """Stashes the full structural report (issues/summary/etc.) into
    `extraction_logs.structural_validation`, and folds ERROR/WARNING
    issue messages into `extraction_logs.errors`/`.warnings` alongside
    whatever schema-validation messages are already there. `extraction_logs`
    is a `Loose` (extra="allow") model (schemas/chapter_schema.py), so an
    extra `structural_validation` key is always safe to add -- it never
    conflicts with ChapterJSON's `extra="forbid"` top-level contract since
    it lives one level down. Mutates `normalized` in place; never raises."""
    logs = normalized.get("extraction_logs")
    if not isinstance(logs, dict):
        logs = {}
        normalized["extraction_logs"] = logs

    logs["structural_validation"] = structural_report

    if structural_report["errors"]:
        logs.setdefault("errors", [])
        logs["errors"].extend(
            f"structural_validation[{i['rule']}]: {i['message']}" for i in structural_report["errors"]
        )
    if structural_report["warnings"]:
        logs.setdefault("warnings", [])
        logs["warnings"].extend(
            f"structural_validation[{i['rule']}]: {i['message']}" for i in structural_report["warnings"]
        )


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

    MILESTONE 2: after the schema check (unchanged above this point),
    also runs `modules.structural_validator.validate_structural_completeness()`
    over whichever dict resulted (the normalized model dump if schema
    validation passed, the raw filled-in dict otherwise -- structural
    completeness is checked either way, since a schema failure does not
    mean structural problems should go unreported). The returned
    `is_valid` is `True` only if BOTH the schema check AND the structural
    check pass (no ERROR-level structural issue and no rule crash) --
    this is the "must never silently pass structurally incomplete output"
    requirement. The full structural report (including WARNING/INFO
    issues, which do not affect `is_valid`) is always attached to the
    returned dict at `extraction_logs.structural_validation` so nothing
    found is ever dropped on the floor even when it isn't fatal.

    Returns (is_valid, error_messages, normalized_dict). Never raises."""
    chapter_dict = fill_missing_sections(chapter_dict)
    try:
        model = ChapterJSON.model_validate(chapter_dict)
        schema_valid = True
        schema_errors: List[str] = []
        normalized = model.model_dump(by_alias=True)
    except ValidationError as e:
        schema_valid = False
        schema_errors = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        logger.error("Chapter JSON failed schema validation: %s", schema_errors)
        normalized = chapter_dict

    structural_report = validate_structural_completeness(normalized)
    _merge_structural_report_into_logs(normalized, structural_report)

    structural_valid = structural_report["status"] == "pass"
    is_valid = schema_valid and structural_valid

    all_errors = list(schema_errors)
    all_errors.extend(
        f"structural_validation[{i['rule']}]: {i['message']}" for i in structural_report["errors"]
    )
    if not structural_valid:
        logger.error(
            "Chapter JSON failed structural validation: %d error(s) (%s)",
            structural_report["summary"]["error_count"],
            ", ".join(sorted(set(i["rule"] for i in structural_report["errors"]))) or "rule crash",
        )

    return is_valid, all_errors, normalized


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