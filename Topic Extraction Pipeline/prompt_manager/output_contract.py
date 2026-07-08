"""
output_contract.py — per-task validation of the model's PARSED response.

This checks one task's response envelope only — not the fully assembled
Chapter JSON (that's schema_validator's job downstream, not built yet).

Two structural rules from the v1.2 addendum are enforced generically here,
not per-task-copy-pasted:
  - Every AI-inferred field must carry the {value, confidence, evidence_basis}
    triple shape (addendum #5, "no exception list").
  - key_visual_elements must be a non-empty list or explicit null — never []
    (addendum #2).
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional


@dataclass(frozen=True)
class FieldSpec:
    name: str
    required: bool = True
    is_evidence_triple: bool = True     # AI-inferred fields carry {value, confidence, evidence_basis}
    is_list: bool = False
    list_item_is_triple: bool = False   # e.g. key_visual_elements: list of triples, not a triple of a list
    mandatory_non_empty: bool = False   # addendum #2 style: [] is invalid, must be non-empty or null


@dataclass(frozen=True)
class OutputContract:
    task_name: str
    fields: List[FieldSpec]

    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]


def _is_valid_triple(value: Any) -> Tuple[bool, str]:
    if not isinstance(value, dict):
        return False, "expected an evidence-triple object {value, confidence, evidence_basis}"
    missing = [k for k in ("value", "confidence", "evidence_basis") if k not in value]
    if missing:
        return False, f"evidence-triple missing key(s): {missing}"
    conf = value.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        return False, "confidence must be a number between 0 and 1"
    return True, ""


def normalize_single_field_response(contract: OutputContract, parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Repairs one observed small-model quirk: for a task whose contract has
    exactly one (required, evidence-triple) field, the model sometimes
    "collapses" the nesting and returns the flat {value, confidence,
    evidence_basis} triple directly at the top level instead of wrapping it
    under the field's name — e.g. recover_chapter_title asking for a single
    `chapter_title` key coming back as just {"value": ..., "confidence": ...,
    "evidence_basis": ...} with no "chapter_title" wrapper at all. This is
    plausibly a side effect of there being nothing else in the schema to
    anchor the wrapping convention — a same-shaped two-field contract
    (recover_heading) doesn't show the same failure in practice.

    Only fires when ALL of the following hold, so it can't misfire on a
    genuinely different kind of bad response or on multi-field contracts:
      - the contract declares exactly one field, and it's required +
        an evidence triple
      - that field's name is NOT already a top-level key in `parsed`
        (nothing to repair if the model got the wrapper right)
      - `parsed` itself is already a syntactically valid evidence triple
        (has value/confidence/evidence_basis) — so this never invents
        content, it only relocates a triple the model already produced
        correctly under the wrong key.
    Returns a new dict with the field wrapped, or `parsed` unchanged if the
    pattern doesn't match."""
    if len(contract.fields) != 1:
        return parsed
    field = contract.fields[0]
    if not (field.required and field.is_evidence_triple):
        return parsed
    if field.name in parsed:
        return parsed  # already correctly wrapped, nothing to do
    is_triple, _ = _is_valid_triple(parsed)
    if not is_triple:
        return parsed
    return {field.name: parsed}


def validate(contract: OutputContract, parsed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    for f in contract.fields:
        present = f.name in parsed and parsed[f.name] is not None
        if not present:
            if f.required and not f.mandatory_non_empty:
                errors.append(f"'{f.name}' is required but missing")
            elif f.required and f.mandatory_non_empty:
                # explicit null is allowed for mandatory_non_empty fields (addendum #2:
                # "never a silent empty list" — null-with-logged-reason is the escape valve)
                pass
            continue

        value = parsed[f.name]

        if f.mandatory_non_empty:
            if isinstance(value, list) and len(value) == 0:
                errors.append(f"'{f.name}' must be a non-empty list or explicit null — got [] (empty list)")
                continue

        if f.is_list:
            if not isinstance(value, list):
                errors.append(f"'{f.name}' must be a list")
                continue
            if f.list_item_is_triple:
                for i, item in enumerate(value):
                    ok, msg = _is_valid_triple(item)
                    if not ok:
                        errors.append(f"'{f.name}[{i}]': {msg}")
            continue

        if f.is_evidence_triple:
            ok, msg = _is_valid_triple(value)
            if not ok:
                errors.append(f"'{f.name}': {msg}")

    return (len(errors) == 0), errors


# ---------------------------------------------------------------------------
# Per-task contracts
#
# NOTE: I only have the two amendment documents (prompt_manager redesign +
# v1.2 addendum), not the full frozen Chapter Schema v1.1 text. Field lists
# below are inferred from what those two documents explicitly describe;
# please correct any task's field list before step 2 if it doesn't match
# schema v1.1.
# ---------------------------------------------------------------------------
CONTRACTS: Dict[str, OutputContract] = {

    "recover_chapter_title": OutputContract("recover_chapter_title", [
        FieldSpec("chapter_title", required=True, is_evidence_triple=True),
    ]),

    "recover_heading": OutputContract("recover_heading", [
        FieldSpec("heading_title", required=True, is_evidence_triple=True),
        FieldSpec("numbering", required=False, is_evidence_triple=True),
    ]),

    "concept_extraction": OutputContract("concept_extraction", [
        FieldSpec("concepts", required=True, is_evidence_triple=False, is_list=True,
                   list_item_is_triple=False),
    ]),

    # Addendum #1/#2: structured visual metadata replaces long free-text.
    "figure_analysis": OutputContract("figure_analysis", [
        FieldSpec("figure_type", required=True),
        FieldSpec("semantic_description", required=True),
        FieldSpec("key_visual_elements", required=True, is_evidence_triple=False,
                   is_list=True, list_item_is_triple=True, mandatory_non_empty=True),
        FieldSpec("visual_relationships", required=False, is_evidence_triple=False,
                   is_list=True, list_item_is_triple=False),
        FieldSpec("layout", required=False),
        FieldSpec("educational_purpose", required=True),
        FieldSpec("concepts", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("related_topics", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("importance", required=True),
        FieldSpec("difficulty", required=True),
        FieldSpec("animation_candidate", required=True),
    ]),

    "table_analysis": OutputContract("table_analysis", [
        FieldSpec("table_type", required=True),
        FieldSpec("semantic_description", required=True),
        FieldSpec("educational_purpose", required=True),
        FieldSpec("concepts", required=False, is_evidence_triple=False, is_list=True),
    ]),

    "equation_analysis": OutputContract("equation_analysis", [
        FieldSpec("latex", required=True),
        FieldSpec("spoken_form", required=True),
        FieldSpec("variables", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("semantic_meaning", required=True),
    ]),

    "relationship_extraction": OutputContract("relationship_extraction", [
        FieldSpec("visual_relationships", required=True, is_evidence_triple=False,
                   is_list=True, list_item_is_triple=False),
    ]),

    "entity_description": OutputContract("entity_description", [
        FieldSpec("semantic_description", required=True),
        FieldSpec("key_visual_elements", required=True, is_evidence_triple=False,
                   is_list=True, list_item_is_triple=True, mandatory_non_empty=True),
        FieldSpec("visual_relationships", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("layout", required=False),
    ]),

    "visual_structure": OutputContract("visual_structure", [
        FieldSpec("layout", required=False),
        FieldSpec("key_visual_elements", required=True, is_evidence_triple=False,
                   is_list=True, list_item_is_triple=True, mandatory_non_empty=True),
        FieldSpec("visual_relationships", required=False, is_evidence_triple=False, is_list=True),
    ]),

    # Addendum #5: visual_dependency restored at concept level, same triple shape as difficulty/importance.
    "semantic_metadata": OutputContract("semantic_metadata", [
        FieldSpec("difficulty", required=True),
        FieldSpec("importance", required=True),
        FieldSpec("visual_dependency", required=True),
    ]),

    # Added during the pipeline-reconnect milestone (see task_registry.py
    # comment) -- same evidence-triple-for-scalars / plain-list-for-lists
    # convention as every contract above, no new shape introduced.
    "topic_semantics": OutputContract("topic_semantics", [
        FieldSpec("semantic_summary", required=True),
        FieldSpec("visual_summary", required=True),
        FieldSpec("concepts", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("glossary_terms", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("detected_entities", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("prerequisites", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("related_topics", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("educational_purpose", required=True),
    ]),

    "chapter_ai_metadata": OutputContract("chapter_ai_metadata", [
        FieldSpec("chapter_type", required=True),
        FieldSpec("knowledge_density", required=True),
        FieldSpec("overall_complexity", required=True),
        FieldSpec("visual_dependency", required=True),
        FieldSpec("formula_dependency", required=True),
        FieldSpec("memory_dependency", required=True),
        FieldSpec("calculation_dependency", required=True),
        FieldSpec("real_world_relevance", required=True),
        FieldSpec("important_concepts", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("likely_confusing_concepts", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("visual_priority_topics", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("concept_progression", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("interdisciplinary_links", required=False, is_evidence_triple=False, is_list=True),
    ]),

    "generation_metadata": OutputContract("generation_metadata", [
        FieldSpec("preferred_visual_types", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("visual_priority", required=False, is_evidence_triple=False, is_list=True),
        FieldSpec("real_world_domains", required=False, is_evidence_triple=False, is_list=True),
    ]),
}


def get_contract(task_name: str) -> OutputContract:
    if task_name not in CONTRACTS:
        raise KeyError(f"No output contract registered for task '{task_name}'.")
    return CONTRACTS[task_name]
