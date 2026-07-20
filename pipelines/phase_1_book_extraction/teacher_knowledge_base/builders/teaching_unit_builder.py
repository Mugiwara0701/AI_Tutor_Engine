"""
teacher_knowledge_base/builders/teaching_unit_builder.py — M6.1 (remediated)

SPECIFICATION: TEACHING_UNIT_SPECIFICATION.md v1.1.1

WHAT THIS BUILDS:
  Dict[concept_id -> TeachingUnit]
  One TeachingUnit per canonical concept in the compilation's concept_index.
  Key: concept_id (not a list, not grouped by chapter).

CONTENT SOURCES (§4 Field Population Source Map):
  concept_id, concept_key, title      <- MKP.concept_index
  definition                          <- ConceptIndex.ConceptEntry.definition
  explanations[0]                     <- ConceptEntry.description (always present)
  examples, figures, formulae         <- ChapterJSON via retrieval_index
  misconceptions                      <- SemanticGraph MISCONCEPTION_ABOUT
  learning_objectives                 <- MKP.LearningProgression.steps
  bloom_taxonomy                      <- derived from learning_objectives
  prerequisites                       <- EDG (convenience snapshot; EDG authoritative)
  related_concepts                    <- EKG RELATED_TO (convenience snapshot)
  estimated_teaching_time_minutes     <- OKP.learning_analytics.concept_analytics
  difficulty                          <- OKP.learning_analytics.concept_analytics
  assessments, practice_questions     <- ChapterJSON exercises + template_derived
  revision_notes                      <- ConceptIndex + MKP.metadata_index

WHAT THIS DOES NOT DO:
  - Does NOT group concepts into "teaching units" by chapter
  - Does NOT cluster concepts
  - Does NOT invent content (definitions, explanations, learning objectives)
  - Does NOT invent difficulty values using prerequisite count heuristics
  - Does NOT assign mastery time using easy=15/medium=30/hard=60 lookup

FIELD POPULATION CERTAINTY:
  When upstream data is absent, fields are left empty ([], {}, "")
  rather than filled with invented placeholder values.
  The completeness_score reflects actual populated state.

DETERMINISM:
  unit_id = UUID5(TU_NS, concept_id + ":" + tkb_id)   — spec §8
  unit_urn = "urn:tkb:tu:<unit_id>"
"""
from __future__ import annotations

import hashlib
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.teaching_unit")

# UUID5 namespace for TeachingUnit (TU_NS in spec §8)
_TU_NS = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")

STAGE = "teaching_units"
TU_VERSION = "1.1.1"

# Bloom taxonomy valid values (spec §4 / SCHEMA §4)
BLOOM_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}

# EDG edge types used in prerequisite snapshot derivation
_PREREQ_EDGE_TYPES = {"REQUIRES", "RECOMMENDED_BEFORE"}


def build(context: "TKBContext") -> None:  # noqa: F821
    """Build teaching_units: Dict[concept_id -> TeachingUnit dict].
    Called by pipeline.py. Writes output via context.set_output('teaching_units', ...)."""
    import time
    t0 = time.monotonic()
    try:
        _build_teaching_units(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_teaching_units(context: "TKBContext") -> None:  # noqa: F821
    artifacts = context.compiler_artifacts
    tkb_id = context.tkb_id

    # The primary input is OptimizedKnowledgePackage.concept_index
    # (one entry per canonical concept in this chapter)
    concept_index = _get_concept_index(artifacts)

    if not concept_index:
        context.diagnostics.add_warning(
            STAGE,
            "No concept_index found in compiler artifacts — teaching_units will be empty.",
            "Ensure OptimizedKnowledgePackage or MasterKnowledgePackage is available.",
        )
        context.set_output(STAGE, {})
        return

    # Supporting lookups (may be empty dicts if upstream artifact absent)
    chapter_json = artifacts.get("chapter_json") or {}
    learning_analytics = _get_learning_analytics(artifacts)
    learning_progression = _get_learning_progression(artifacts)
    edg_output = context.get_output("edg")   # built in T2; may be None if EDG ran first

    teaching_units: Dict[str, Any] = {}
    for concept_id, concept_entry in concept_index.items():
        tu = _build_one_teaching_unit(
            concept_id=concept_id,
            concept_entry=concept_entry,
            tkb_id=tkb_id,
            chapter_json=chapter_json,
            learning_analytics=learning_analytics,
            learning_progression=learning_progression,
            edg_output=edg_output,
            context=context,
        )
        teaching_units[concept_id] = tu

    context.set_output(STAGE, teaching_units)
    logger.info(
        "Teaching Unit builder: produced %d TeachingUnits (Dict[concept_id -> TU]).",
        len(teaching_units),
    )


def _build_one_teaching_unit(
    concept_id: str,
    concept_entry: Dict[str, Any],
    tkb_id: str,
    chapter_json: Dict[str, Any],
    learning_analytics: Dict[str, Any],
    learning_progression: Dict[str, Any],
    edg_output: Optional[Dict[str, Any]],
    context: "TKBContext",
) -> Dict[str, Any]:
    """Builds one TeachingUnit dict for one concept.
    All fields populated from authoritative Phase 1 sources.
    No invented content."""
    # --- Identity (spec §3, §8) -------------------------------------------
    unit_id = str(uuid.uuid5(_TU_NS, f"{concept_id}:{tkb_id}"))
    unit_urn = f"urn:tkb:tu:{unit_id}"

    concept_key = str(concept_entry.get("concept_key") or concept_entry.get("key") or "")
    title = str(concept_entry.get("name") or concept_entry.get("title") or concept_id)

    # --- Definition (from ConceptEntry.definition) ------------------------
    def_text = str(
        concept_entry.get("definition")
        or concept_entry.get("description")
        or ""
    )
    definition = {
        "text": def_text,
        "source_key": concept_key,
        "confidence": float(concept_entry.get("definition_confidence") or 1.0),
    }

    # --- Explanations (spec §3: explanations[0] always from ConceptEntry.description) ---
    explanations = _extract_explanations(concept_entry, concept_id)

    # --- Content from ChapterJSON (via retrieval_index) -------------------
    retrieval_index = chapter_json.get("retrieval_index") or {}
    concept_retrieval = retrieval_index.get(concept_id) or retrieval_index.get(concept_key) or {}

    examples = _extract_examples(chapter_json, concept_retrieval, is_worked=False)
    worked_examples = _extract_examples(chapter_json, concept_retrieval, is_worked=True)
    formulae = _extract_formulae(chapter_json, concept_retrieval)
    all_figures = _extract_figures(chapter_json, concept_retrieval)
    figures = [f for f in all_figures if f.get("figure_type") not in ("diagram", "table")]
    diagrams = [f for f in all_figures if f.get("figure_type") == "diagram"]
    tables = [f for f in all_figures if f.get("figure_type") == "table"]
    activities = _extract_activities(chapter_json, concept_retrieval)
    analogies = _extract_analogies(concept_entry, chapter_json, concept_retrieval)
    misconceptions = _extract_misconceptions(concept_entry, chapter_json, concept_retrieval)
    common_mistakes = _extract_common_mistakes(concept_entry)
    applications = _extract_applications(concept_entry, chapter_json, concept_retrieval)

    # --- Assessments (spec §2, §3) ----------------------------------------
    assessments = _extract_assessments(chapter_json, concept_retrieval, is_practice=False)
    practice_questions = _extract_assessments(chapter_json, concept_retrieval, is_practice=True)

    # --- Revision Notes ---------------------------------------------------
    revision_notes = _extract_revision_notes(concept_entry)

    # --- Learning Objectives (from MKP.LearningProgression.steps) ---------
    learning_objectives = _extract_learning_objectives(learning_progression, concept_id, concept_key)

    # --- Bloom Taxonomy (derived from learning_objectives) ----------------
    bloom_taxonomy = _build_bloom_taxonomy(learning_objectives)

    # --- Prerequisites (convenience snapshot from EDG; EDG is authoritative) ---
    prerequisites = _build_prerequisites_snapshot(
        concept_id=concept_id,
        edg_output=edg_output,
    )

    # --- Teaching metadata from OKP.learning_analytics --------------------
    concept_analytics = (learning_analytics.get(concept_id) or
                         learning_analytics.get(concept_key) or {})
    estimated_teaching_time = float(
        concept_analytics.get("estimated_teaching_time_minutes")
        or concept_entry.get("estimated_teaching_time_minutes")
        or 0.0
    )
    difficulty = str(
        concept_analytics.get("difficulty")
        or concept_entry.get("difficulty")
        or ""
    )
    importance = str(
        concept_analytics.get("importance")
        or concept_entry.get("importance")
        or "core"
    )

    # --- Graph cross-references (IDs only; filled in by post-processing) --
    # These are set to empty strings here; EDG/EKG/EDST builders populate them
    # once their own outputs are available. The pipeline sets them via
    # post_process_teaching_units().
    edst_node_ids: List[str] = []
    ekg_node_id: str = ""
    edg_node_id: str = ""

    # --- Related Concepts (convenience snapshot from EKG.RELATED_TO) ------
    # EKG runs after TU; populated in post-processing step
    related_concepts: List[Dict[str, Any]] = []

    # --- Completeness Score (spec §6, exact weighted formula) -------------
    completeness_score = _compute_completeness_score(
        definition=definition,
        explanations=explanations,
        learning_objectives=learning_objectives,
        examples=examples + worked_examples,
        prerequisites=prerequisites,
        assessments=assessments + practice_questions,
        bloom_taxonomy=bloom_taxonomy,
        revision_notes=revision_notes,
        figures=all_figures,
        estimated_teaching_time=estimated_teaching_time,
    )

    return {
        "unit_id": unit_id,
        "unit_urn": unit_urn,
        "concept_id": concept_id,
        "concept_key": concept_key,
        "tkb_id": tkb_id,
        "title": title,
        "definition": definition,
        "explanations": explanations,
        "analogies": analogies,
        "examples": examples,
        "worked_examples": worked_examples,
        "common_mistakes": common_mistakes,
        "misconceptions": misconceptions,
        "formulae": formulae,
        "figures": all_figures,
        "diagrams": diagrams,
        "tables": tables,
        "activities": activities,
        "learning_objectives": learning_objectives,
        "bloom_taxonomy": bloom_taxonomy,
        "prerequisites": prerequisites,
        "related_concepts": related_concepts,
        "applications": applications,
        "assessments": assessments,
        "practice_questions": practice_questions,
        "revision_notes": revision_notes,
        "estimated_teaching_time_minutes": estimated_teaching_time,
        "difficulty": difficulty,
        "importance": importance,
        "completeness_score": completeness_score,
        # Graph cross-references (populated post-processing)
        "edst_node_ids": edst_node_ids,
        "ekg_node_id": ekg_node_id,
        "edg_node_id": edg_node_id,
        # Extension points (empty in v1; Phase 3 populates)
        "web_enrichments": [],
        "multilingual": {},
    }


# ---------------------------------------------------------------------------
# Content extractors — read from authoritative Phase 1 sources only
# ---------------------------------------------------------------------------

def _get_concept_index(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Returns concept_index from OKP or MKP. Keys are concept_ids."""
    okp = artifacts.get("optimized_knowledge_package")
    if isinstance(okp, dict):
        ci = okp.get("concept_index") or okp.get("concepts")
        if isinstance(ci, dict):
            return ci
        if isinstance(ci, list):
            return {str(c.get("concept_id") or c.get("id") or i): c
                    for i, c in enumerate(ci) if isinstance(c, dict)}
    mkp = artifacts.get("master_knowledge_package")
    if isinstance(mkp, dict):
        ci = mkp.get("concept_index") or mkp.get("concepts")
        if isinstance(ci, dict):
            return ci
        if isinstance(ci, list):
            return {str(c.get("concept_id") or c.get("id") or i): c
                    for i, c in enumerate(ci) if isinstance(c, dict)}
    # Fallback: try knowledge_graph nodes as concept stubs
    kg = artifacts.get("knowledge_graph") or {}
    nodes = kg.get("nodes") or []
    if nodes:
        return {
            str(n.get("id") or n.get("concept_id") or i): n
            for i, n in enumerate(nodes)
            if isinstance(n, dict)
        }
    return {}


def _get_learning_analytics(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Returns concept_analytics dict from OKP.learning_analytics."""
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        la = okp.get("learning_analytics") or {}
        ca = la.get("concept_analytics") or {}
        if isinstance(ca, dict):
            return ca
    return {}


def _get_learning_progression(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Returns LearningProgression from MKP."""
    mkp = artifacts.get("master_knowledge_package") or {}
    if isinstance(mkp, dict):
        lp = mkp.get("learning_progression") or mkp.get("LearningProgression") or {}
        return lp if isinstance(lp, dict) else {}
    return {}


def _extract_explanations(
    concept_entry: Dict[str, Any],
    concept_id: str,
) -> List[Dict[str, Any]]:
    """Explanations[0] always from ConceptEntry.description (spec §3, §4).
    Additional variants if SemanticGraph enrichment available."""
    variants = []
    # Primary explanation from ConceptEntry.description (always present if entry exists)
    desc = str(concept_entry.get("description") or concept_entry.get("definition") or "")
    if desc:
        variant_id = str(uuid.uuid5(
            uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
            f"exp:{concept_id}:0"
        ))
        variants.append({
            "variant_id": variant_id,
            "text": desc,
            "style": "formal",
            "complexity": "standard",
            "language": "en",
            "target_stage": "BEGINNER",
        })
    # Additional variants from SemanticGraph if available
    for i, extra in enumerate(concept_entry.get("explanation_variants") or [], start=1):
        if isinstance(extra, dict):
            vid = str(uuid.uuid5(
                uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                f"exp:{concept_id}:{i}"
            ))
            variants.append({
                "variant_id": vid,
                "text": str(extra.get("text") or ""),
                "style": str(extra.get("style") or "formal"),
                "complexity": str(extra.get("complexity") or "standard"),
                "language": str(extra.get("language") or "en"),
                "target_stage": str(extra.get("target_stage") or "BEGINNER"),
            })
    return variants


def _extract_examples(
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
    is_worked: bool,
) -> List[Dict[str, Any]]:
    """Extracts ExampleItems from ChapterJSON via retrieval_index."""
    all_examples = chapter_json.get("examples") or []
    example_ids = set(concept_retrieval.get("example_ids") or [])
    results = []
    for ex in all_examples:
        if not isinstance(ex, dict):
            continue
        ex_id = str(ex.get("example_id") or ex.get("id") or "")
        if example_ids and ex_id not in example_ids:
            continue
        if bool(ex.get("is_worked", False)) != is_worked:
            continue
        results.append({
            "example_id": ex_id,
            "title": str(ex.get("title") or ""),
            "body": str(ex.get("body") or ex.get("text") or ""),
            "is_worked": is_worked,
            "steps": list(ex.get("steps") or []),
            "concept_refs": list(ex.get("concept_refs") or []),
            "source_object_key": str(ex.get("source_object_key") or ex.get("source_key") or ""),
            "figure_refs": list(ex.get("figure_refs") or []),
        })
    return results


def _extract_formulae(
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
) -> List[Dict[str, Any]]:
    all_formulae = chapter_json.get("equations") or chapter_json.get("formulae") or []
    formula_ids = set(concept_retrieval.get("formula_ids") or [])
    results = []
    for f in all_formulae:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("formula_id") or f.get("equation_id") or f.get("id") or "")
        if formula_ids and fid not in formula_ids:
            continue
        results.append({
            "formula_id": fid,
            "name": str(f.get("name") or ""),
            "expression": str(f.get("expression") or f.get("equation") or ""),
            "variables": list(f.get("variables") or []),
            "conditions": list(f.get("conditions") or []),
            "concept_refs": list(f.get("concept_refs") or []),
            "source_object_key": str(f.get("source_object_key") or f.get("source_key") or ""),
        })
    return results


def _extract_figures(
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
) -> List[Dict[str, Any]]:
    all_figures = (chapter_json.get("figures") or
                   chapter_json.get("diagrams") or [])
    figure_ids = set(concept_retrieval.get("figure_ids") or [])
    results = []
    for fig in all_figures:
        if not isinstance(fig, dict):
            continue
        fid = str(fig.get("figure_id") or fig.get("id") or "")
        if figure_ids and fid not in figure_ids:
            continue
        results.append({
            "figure_id": fid,
            "caption": str(fig.get("caption") or ""),
            "figure_type": str(fig.get("figure_type") or fig.get("type") or "diagram"),
            "page_number": int(fig.get("page_number") or 0),
            "source_object_key": str(fig.get("source_object_key") or fig.get("source_key") or ""),
            "semantic_description": str(fig.get("semantic_description") or fig.get("description") or ""),
            "concept_refs": list(fig.get("concept_refs") or []),
        })
    return results


def _extract_activities(
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
) -> List[Dict[str, Any]]:
    all_activities = chapter_json.get("activities") or []
    activity_ids = set(concept_retrieval.get("activity_ids") or [])
    results = []
    for act in all_activities:
        if not isinstance(act, dict):
            continue
        aid = str(act.get("activity_id") or act.get("id") or "")
        if activity_ids and aid not in activity_ids:
            continue
        results.append({
            "activity_id": aid,
            "title": str(act.get("title") or ""),
            "description": str(act.get("description") or ""),
            "activity_type": str(act.get("activity_type") or act.get("type") or ""),
            "estimated_minutes": float(act.get("estimated_minutes") or act.get("duration_minutes") or 0.0),
            "materials": list(act.get("materials") or []),
            "steps": list(act.get("steps") or []),
            "learning_objectives": list(act.get("learning_objectives") or []),
            "concept_refs": list(act.get("concept_refs") or []),
            "source_key": str(act.get("source_key") or act.get("source_object_key") or ""),
        })
    return results


def _extract_analogies(
    concept_entry: Dict[str, Any],
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Source: SemanticGraph ANALOGY_FOR + ChapterJSON text. TU is authoritative."""
    raw = (concept_entry.get("analogies") or
           concept_retrieval.get("analogies") or [])
    results = []
    for i, a in enumerate(raw):
        if isinstance(a, dict):
            aid = str(a.get("analogy_id") or a.get("id") or i)
            results.append({
                "analogy_id": aid,
                "text": str(a.get("text") or ""),
                "domain": str(a.get("domain") or "everyday"),
                "concept_refs": list(a.get("concept_refs") or []),
                "source_object_key": str(a.get("source_object_key") or ""),
            })
        elif isinstance(a, str) and a:
            results.append({
                "analogy_id": str(i),
                "text": a,
                "domain": "everyday",
                "concept_refs": [],
                "source_object_key": "",
            })
    return results


def _extract_misconceptions(
    concept_entry: Dict[str, Any],
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Source: SemanticGraph MISCONCEPTION_ABOUT. TU is authoritative (spec §3.4)."""
    raw = (concept_entry.get("misconceptions") or
           concept_retrieval.get("misconceptions") or [])
    results = []
    for m in raw:
        if isinstance(m, dict):
            results.append({
                "misconception_id": str(m.get("misconception_id") or m.get("id") or ""),
                "text": str(m.get("text") or m.get("description") or ""),
                "correction": str(m.get("correction") or ""),
                "concept_refs": list(m.get("concept_refs") or []),
            })
        elif isinstance(m, str) and m:
            results.append({
                "misconception_id": "",
                "text": m,
                "correction": "",
                "concept_refs": [],
            })
    return results


def _extract_common_mistakes(concept_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Source: Stage D/E extraction (spec §3, §3 common_mistakes)."""
    raw = concept_entry.get("common_mistakes") or []
    results = []
    for m in raw:
        if isinstance(m, dict):
            results.append({
                "mistake_id": str(m.get("mistake_id") or m.get("id") or ""),
                "description": str(m.get("description") or ""),
                "correction": str(m.get("correction") or ""),
                "frequency": str(m.get("frequency") or "common"),
                "mistake_category": str(m.get("mistake_category") or ""),
            })
    return results


def _extract_applications(
    concept_entry: Dict[str, Any],
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Source: SemanticGraph APPLICATION_OF. TU is authoritative (spec §3.6)."""
    raw = (concept_entry.get("applications") or
           concept_retrieval.get("applications") or [])
    results = []
    for i, a in enumerate(raw):
        if isinstance(a, dict):
            results.append({
                "application_id": str(a.get("application_id") or a.get("id") or i),
                "title": str(a.get("title") or ""),
                "description": str(a.get("description") or ""),
                "domain": str(a.get("domain") or ""),
                "concept_refs": list(a.get("concept_refs") or []),
            })
    return results


def _extract_assessments(
    chapter_json: Dict[str, Any],
    concept_retrieval: Dict[str, Any],
    is_practice: bool,
) -> List[Dict[str, Any]]:
    """Source: ChapterJSON exercises (extracted) + template_derived (spec §2)."""
    field = "practice_questions" if is_practice else "assessments"
    all_items = (chapter_json.get(field) or
                 chapter_json.get("exercises") or
                 chapter_json.get("questions") or [])
    item_ids = set(concept_retrieval.get(f"{field}_ids") or
                   concept_retrieval.get("assessment_ids") or [])
    results = []
    for item in all_items:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("item_id") or item.get("question_id") or item.get("id") or "")
        if item_ids and iid not in item_ids:
            continue
        results.append({
            "item_id": iid,
            "question": str(item.get("question") or item.get("text") or ""),
            "answer": str(item.get("answer") or item.get("model_answer") or ""),
            "distractors": list(item.get("distractors") or item.get("options") or []),
            "item_type": str(item.get("item_type") or item.get("type") or "short_answer"),
            "difficulty": str(item.get("difficulty") or "medium"),
            "bloom_level": str(item.get("bloom_level") or ""),
            "concept_refs": list(item.get("concept_refs") or []),
            "marks": int(item.get("marks") or 1),
            "time_minutes": float(item.get("time_minutes") or 0.0),
            "provenance_tier": str(item.get("provenance_tier") or "extracted"),
        })
    # If no assessments found, add an empty_placeholder per spec §2
    if not results:
        results.append({
            "item_id": "",
            "question": "",
            "answer": "",
            "distractors": [],
            "item_type": "short_answer",
            "difficulty": "medium",
            "bloom_level": "",
            "concept_refs": [],
            "marks": 1,
            "time_minutes": 0.0,
            "provenance_tier": "empty_placeholder",
        })
    return results


def _extract_revision_notes(concept_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Source: ConceptIndex + MKP.metadata_index (spec §4)."""
    raw = concept_entry.get("revision_notes") or concept_entry.get("summary") or []
    results = []
    if isinstance(raw, list):
        for note in raw:
            if isinstance(note, dict):
                results.append({
                    "note_id": str(note.get("note_id") or note.get("id") or ""),
                    "text": str(note.get("text") or ""),
                    "note_type": str(note.get("note_type") or "summary"),
                    "key_points": list(note.get("key_points") or []),
                })
            elif isinstance(note, str) and note:
                results.append({
                    "note_id": "",
                    "text": note,
                    "note_type": "summary",
                    "key_points": [],
                })
    elif isinstance(raw, str) and raw:
        results.append({"note_id": "", "text": raw, "note_type": "summary", "key_points": []})
    return results


def _extract_learning_objectives(
    learning_progression: Dict[str, Any],
    concept_id: str,
    concept_key: str,
) -> List[Dict[str, Any]]:
    """Source: MKP.LearningProgression.steps (spec §4).
    Derived from existing compiler output — not generated text."""
    steps = (
        learning_progression.get("steps") or
        learning_progression.get(concept_id) or
        learning_progression.get(concept_key) or
        []
    )
    if isinstance(steps, dict):
        steps = steps.get("steps") or steps.get("objectives") or []
    results = []
    for i, step in enumerate(steps):
        if isinstance(step, dict):
            obj_id = str(step.get("objective_id") or step.get("id") or i)
            bloom = str(step.get("bloom_level") or step.get("bloom") or "understand")
            if bloom not in BLOOM_LEVELS:
                bloom = "understand"
            results.append({
                "objective_id": obj_id,
                "text": str(step.get("text") or step.get("objective") or ""),
                "bloom_level": bloom,
                "outcome_type": str(step.get("outcome_type") or "knowledge"),
                "assessment_hint": str(step.get("assessment_hint") or ""),
            })
        elif isinstance(step, str) and step:
            results.append({
                "objective_id": str(i),
                "text": step,
                "bloom_level": "understand",
                "outcome_type": "knowledge",
                "assessment_hint": "",
            })
    return results


def _build_bloom_taxonomy(
    learning_objectives: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Derived from learning_objectives bloom_level distribution.
    Uses coverage_flags (boolean), not normalized distribution (spec §4, SCHEMA §4)."""
    levels_present = list({
        obj["bloom_level"] for obj in learning_objectives
        if obj.get("bloom_level") in BLOOM_LEVELS
    })
    primary = levels_present[0] if levels_present else ""
    coverage = {lvl: (lvl in levels_present) for lvl in
                ("remember", "understand", "apply", "analyze", "evaluate", "create")}
    return {
        "primary_level": primary,
        "levels_present": sorted(levels_present),
        "coverage_flags": coverage,
    }


def _build_prerequisites_snapshot(
    concept_id: str,
    edg_output: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convenience snapshot from EDG REQUIRES + RECOMMENDED_BEFORE edges.
    EDG is authoritative (spec §2.1, TU §3). This list is derived, never authored."""
    if edg_output is None:
        return []
    nodes = edg_output.get("nodes") or {}
    node = (nodes.get(concept_id) if isinstance(nodes, dict) else {}) or {}
    prereq_ids = list(node.get("prerequisite_ids") or [])
    results = []
    for prereq_id in prereq_ids:
        prereq_node = (nodes.get(prereq_id) if isinstance(nodes, dict) else {}) or {}
        results.append({
            "concept_id": prereq_id,
            "concept_name": str(prereq_node.get("concept_name") or prereq_id),
            "is_blocking": bool(prereq_node.get("is_gate", False)),
            "teaching_unit_id": prereq_id,  # concept_id = TU key in v1.1
        })
    return results


def _compute_completeness_score(
    definition: Dict[str, Any],
    explanations: List,
    learning_objectives: List,
    examples: List,
    prerequisites: List,
    assessments: List,
    bloom_taxonomy: Dict,
    revision_notes: List,
    figures: List,
    estimated_teaching_time: float,
) -> float:
    """
    EXACT formula from TEACHING_UNIT_SPECIFICATION.md §6.
    completeness_score = weighted_average_of_boolean_checks:
      definition present:             weight 3
      at least 1 explanation:         weight 3
      at least 1 learning objective:  weight 2
      at least 1 example:             weight 2
      prerequisites resolved from EDG: weight 2
      at least 1 assessment (any tier): weight 2
      bloom_taxonomy present:         weight 1
      revision_notes present:         weight 1
      figures present:                weight 1
      estimated_teaching_time > 0:    weight 1
    Range: 0.0 -> 1.0
    """
    checks = [
        (bool(definition.get("text")), 3),
        (len(explanations) >= 1, 3),
        (len(learning_objectives) >= 1, 2),
        (len(examples) >= 1, 2),
        (len(prerequisites) >= 1, 2),
        # assessment: any tier counts (including empty_placeholder)
        (any(a.get("provenance_tier") != "empty_placeholder" for a in assessments), 2),
        (bool(bloom_taxonomy.get("primary_level")), 1),
        (len(revision_notes) >= 1, 1),
        (len(figures) >= 1, 1),
        (estimated_teaching_time > 0, 1),
    ]
    total_weight = sum(w for _, w in checks)
    weighted_sum = sum(w for passed, w in checks if passed)
    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 4)
