"""
teacher_knowledge_base/builders/progression_builder.py — M6.1 (remediated)

SPECIFICATION: LEARNING_GRAPH_SPECIFICATION.md (CPT-SPEC-v1.1.1)

WHAT CHANGED FROM PREVIOUS IMPLEMENTATION:
  - CPT is a Dict[concept_id -> ConceptProgressionTemplate], NOT a list
  - One CPT per concept (not per cluster)
  - CPT contains stage_resources (ID pointers into TU), NOT bloom_arc/difficulty_arc
  - progression_type, anchor_concept_id, entry_concepts, exit_concepts are NOT spec fields
  - template_id = UUID5(concept_id + "cpt" + tkb_id)  (spec §3)

WHAT A ConceptProgressionTemplate CONTAINS (spec §3):
  template_id, template_urn, concept_id, concept_name, tkb_id
  stage_resources:
    BEGINNER:         {definition_present, figure_ids, simple_example_ids, learning_objective_ids}
    INTERMEDIATE:     {explanation_variant_ids, example_ids, learning_objective_ids}
    ADVANCED:         {worked_example_ids, formula_ids, application_ids, learning_objective_ids}
    MASTERY:          {assessment_item_ids, practice_question_ids, learning_objective_ids}
    ASSESSMENT_READY: {full_assessment_item_ids}
  revision_resources: {revision_note_ids, key_formula_ids, definition_present}
  suggested_thresholds: {advance_score, revisit_score}  -- advisory only
  estimated_stage_minutes: {BEGINNER, INTERMEDIATE, ADVANCED, MASTERY, ASSESSMENT_READY}
  prerequisite_concept_ids: List[str]  -- from EDG, not independently authored
  difficulty, importance  -- from OKP.learning_analytics

VALIDATION (spec §6):
  1. All IDs in stage_resources resolve within teaching_units[concept_id]
  2. revision_resources.revision_note_ids resolve within TU.revision_notes
  3. prerequisite_concept_ids matches EDG.nodes[concept_id].prerequisite_ids
  4. suggested_thresholds.advance_score in [0.0, 1.0]
  5. Every concept in teaching_units has exactly one CPT
"""
from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, List, Optional

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.progression")

_CPT_NS = uuid.UUID("fedcba98-0000-3210-fedc-ba9876543210")

STAGE = "concept_progression_templates"
CPT_VERSION = "1.1.1"

LEARNING_STAGES = ("BEGINNER", "INTERMEDIATE", "ADVANCED", "MASTERY", "ASSESSMENT_READY")


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_cpts(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_cpts(context: "TKBContext") -> None:  # noqa: F821
    teaching_units = context.require_output("teaching_units", STAGE)
    edg_output = context.get_output("edg")
    tkb_id = context.tkb_id
    artifacts = context.compiler_artifacts
    learning_analytics = _get_learning_analytics(artifacts)

    cpts: Dict[str, Any] = {}  # concept_id -> ConceptProgressionTemplate
    for concept_id, tu in teaching_units.items():
        cpt = _build_one_cpt(
            concept_id=concept_id,
            tu=tu,
            tkb_id=tkb_id,
            edg_output=edg_output,
            learning_analytics=learning_analytics,
        )
        cpts[concept_id] = cpt

    context.set_output(STAGE, cpts)
    logger.info(
        "Progression Template builder: produced %d ConceptProgressionTemplates (Dict[concept_id -> CPT]).",
        len(cpts),
    )


def _build_one_cpt(
    concept_id: str,
    tu: Dict[str, Any],
    tkb_id: str,
    edg_output: Optional[Dict[str, Any]],
    learning_analytics: Dict[str, Any],
) -> Dict[str, Any]:
    """Build one ConceptProgressionTemplate from TU content (spec §3).
    All values are ID pointers — no full content objects."""
    template_id = str(uuid.uuid5(_CPT_NS, f"{concept_id}:cpt:{tkb_id}"))
    template_urn = f"urn:tkb:cpt:{template_id}"
    concept_name = str(tu.get("title") or concept_id)

    # Extract ID lists from TU for each stage
    # All lists contain item_ids, figure_ids, etc. — never full objects
    figure_ids = [f.get("figure_id", "") for f in (tu.get("figures") or []) if f.get("figure_id")]
    simple_example_ids = [
        e.get("example_id", "") for e in (tu.get("examples") or [])
        if not e.get("is_worked") and e.get("example_id")
    ]
    all_example_ids = [
        e.get("example_id", "") for e in (tu.get("examples") or [])
        if e.get("example_id")
    ]
    worked_example_ids = [
        e.get("example_id", "") for e in (tu.get("worked_examples") or [])
        if e.get("example_id")
    ]
    formula_ids = [f.get("formula_id", "") for f in (tu.get("formulae") or []) if f.get("formula_id")]
    application_ids = [a.get("application_id", "") for a in (tu.get("applications") or []) if a.get("application_id")]
    explanation_variant_ids = [
        v.get("variant_id", "") for v in (tu.get("explanations") or [])
        if v.get("variant_id") and v.get("style") in ("conversational", "step_by_step")
    ]

    # Objectives sorted by Bloom level
    all_objectives = tu.get("learning_objectives") or []
    beginner_obj_ids = [o["objective_id"] for o in all_objectives
                        if o.get("bloom_level") in ("remember", "understand") and o.get("objective_id")]
    intermediate_obj_ids = [o["objective_id"] for o in all_objectives
                             if o.get("bloom_level") == "understand" and o.get("objective_id")]
    advanced_obj_ids = [o["objective_id"] for o in all_objectives
                        if o.get("bloom_level") in ("apply", "analyze") and o.get("objective_id")]
    mastery_obj_ids = [o["objective_id"] for o in all_objectives
                       if o.get("bloom_level") in ("evaluate", "create") and o.get("objective_id")]
    all_obj_ids = [o["objective_id"] for o in all_objectives if o.get("objective_id")]

    # Assessment IDs (from TU assessments + practice_questions)
    assessment_item_ids = [
        a["item_id"] for a in (tu.get("assessments") or [])
        if a.get("item_id") and a.get("provenance_tier") != "empty_placeholder"
    ]
    practice_question_ids = [
        a["item_id"] for a in (tu.get("practice_questions") or [])
        if a.get("item_id") and a.get("provenance_tier") != "empty_placeholder"
    ]
    # ASSESSMENT_READY: complete formal assessment set
    full_assessment_item_ids = assessment_item_ids[:]  # same items, full set

    # Revision resources
    revision_note_ids = [n["note_id"] for n in (tu.get("revision_notes") or []) if n.get("note_id")]
    key_formula_ids = formula_ids  # all formulae are key for revision
    definition_present = bool(tu.get("definition", {}).get("text"))

    # Prerequisite concept IDs from EDG (canonical source; EDG authoritative)
    prereq_ids = _get_prereq_ids_from_edg(concept_id, edg_output)

    # Difficulty and importance from OKP.learning_analytics (not from heuristics)
    analytics = learning_analytics.get(concept_id) or {}
    difficulty = str(analytics.get("difficulty") or tu.get("difficulty") or "")
    importance = str(analytics.get("importance") or tu.get("importance") or "core")

    # Estimated stage minutes (from learning_analytics if available; else 0)
    est_minutes = float(analytics.get("estimated_teaching_time_minutes") or tu.get("estimated_teaching_time_minutes") or 0.0)
    # Advisory breakdown by stage (proportional if total known; else equal split)
    stage_min = _split_stage_minutes(est_minutes)

    # Advisory thresholds (product policy advisory defaults — Phase 2 overrides)
    # These are fixed advisory values per spec — no heuristics
    suggested_thresholds = {
        "advance_score": 0.7,    # advisory: advance at 70%
        "revisit_score": 0.4,    # advisory: revisit below 40%
    }

    return {
        "template_id": template_id,
        "template_urn": template_urn,
        "concept_id": concept_id,
        "concept_name": concept_name,
        "tkb_id": tkb_id,
        "stage_resources": {
            "BEGINNER": {
                "definition_present": definition_present,
                "figure_ids": figure_ids[:3],  # simplest figures (first 3)
                "simple_example_ids": simple_example_ids,
                "learning_objective_ids": beginner_obj_ids or all_obj_ids[:1],
            },
            "INTERMEDIATE": {
                "explanation_variant_ids": explanation_variant_ids,
                "example_ids": all_example_ids,
                "learning_objective_ids": intermediate_obj_ids or all_obj_ids,
            },
            "ADVANCED": {
                "worked_example_ids": worked_example_ids,
                "formula_ids": formula_ids,
                "application_ids": application_ids,
                "learning_objective_ids": advanced_obj_ids or all_obj_ids,
            },
            "MASTERY": {
                "assessment_item_ids": assessment_item_ids,
                "practice_question_ids": practice_question_ids,
                "learning_objective_ids": mastery_obj_ids or all_obj_ids,
            },
            "ASSESSMENT_READY": {
                "full_assessment_item_ids": full_assessment_item_ids,
            },
        },
        "revision_resources": {
            "revision_note_ids": revision_note_ids,
            "key_formula_ids": key_formula_ids,
            "definition_present": definition_present,
        },
        "suggested_thresholds": suggested_thresholds,
        "estimated_stage_minutes": stage_min,
        "prerequisite_concept_ids": prereq_ids,
        "difficulty": difficulty,
        "importance": importance,
    }


def _get_prereq_ids_from_edg(
    concept_id: str,
    edg_output: Optional[Dict[str, Any]],
) -> List[str]:
    """Gets prerequisite_ids from EDG (canonical source). EDG is authoritative (spec §4)."""
    if not edg_output:
        return []
    edg_nodes = edg_output.get("nodes") or {}
    node = edg_nodes.get(concept_id) or {}
    return list(node.get("prerequisite_ids") or [])


def _split_stage_minutes(total: float) -> Dict[str, float]:
    """Advisory split of total estimated minutes across 5 stages.
    Simple proportional split — no heuristic formula."""
    if total <= 0:
        return {s: 0.0 for s in LEARNING_STAGES}
    proportions = {
        "BEGINNER": 0.15,
        "INTERMEDIATE": 0.25,
        "ADVANCED": 0.30,
        "MASTERY": 0.20,
        "ASSESSMENT_READY": 0.10,
    }
    return {s: round(total * p, 2) for s, p in proportions.items()}


def _get_learning_analytics(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        la = okp.get("learning_analytics") or {}
        ca = la.get("concept_analytics") or {}
        return ca if isinstance(ca, dict) else {}
    return {}
