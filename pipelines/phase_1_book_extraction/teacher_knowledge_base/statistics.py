"""
teacher_knowledge_base/statistics.py — M6.1 (remediated)

Implements TKBStatistics per TEACHER_KNOWLEDGE_BASE_SCHEMA.md §7.

EXACT FIELDS (spec §7):
  total_concepts, total_teaching_units (= total_concepts), total_learning_objectives,
  total_assessments, total_practice_questions, total_prerequisites, total_ekg_edges,
  total_edg_edges, total_curriculum_links, total_figures, total_examples, total_formulae,
  total_worked_examples, total_activities, coverage_score, avg_completeness_score,
  avg_prerequisites_per_concept, estimated_total_teaching_time_minutes, assessment_coverage_rate

All values computed from already-built stage outputs — no new derivation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.statistics")
STAGE = "statistics"


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_statistics(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_statistics(context: "TKBContext") -> None:  # noqa: F821
    outputs = context.outputs
    teaching_units: Dict[str, Any] = outputs.get("teaching_units") or {}
    edg: Dict[str, Any] = outputs.get("edg") or {}
    ekg: Dict[str, Any] = outputs.get("ekg") or {}
    curriculum_graph: Dict[str, Any] = outputs.get("curriculum_graph") or {}

    n_concepts = len(teaching_units)
    n_tu = n_concepts  # must equal total_concepts (spec §7 check #5)

    total_learning_objectives = sum(
        len(tu.get("learning_objectives") or []) for tu in teaching_units.values()
    )
    total_assessments = sum(
        len([a for a in (tu.get("assessments") or [])
             if a.get("provenance_tier") != "empty_placeholder"])
        for tu in teaching_units.values()
    )
    total_practice_questions = sum(
        len([a for a in (tu.get("practice_questions") or [])
             if a.get("provenance_tier") != "empty_placeholder"])
        for tu in teaching_units.values()
    )
    total_prerequisites = sum(
        len(tu.get("prerequisites") or []) for tu in teaching_units.values()
    )
    total_ekg_edges = len(ekg.get("edges") or {})
    total_edg_edges = len(edg.get("edges") or {})
    total_curriculum_links = (
        len(curriculum_graph.get("edges") or {}) +
        len(curriculum_graph.get("cross_chapter_links") or [])
    )
    total_figures = sum(len(tu.get("figures") or []) for tu in teaching_units.values())
    total_examples = sum(len(tu.get("examples") or []) for tu in teaching_units.values())
    total_formulae = sum(len(tu.get("formulae") or []) for tu in teaching_units.values())
    total_worked_examples = sum(len(tu.get("worked_examples") or []) for tu in teaching_units.values())
    total_activities = sum(len(tu.get("activities") or []) for tu in teaching_units.values())

    completeness_scores = [
        float(tu.get("completeness_score") or 0.0) for tu in teaching_units.values()
    ]
    avg_completeness = (
        sum(completeness_scores) / len(completeness_scores)
        if completeness_scores else 0.0
    )
    # coverage_score: fraction of TUs with completeness >= 0.6
    coverage_score = (
        sum(1 for s in completeness_scores if s >= 0.6) / len(completeness_scores)
        if completeness_scores else 0.0
    )
    avg_prereqs = total_prerequisites / max(1, n_concepts)
    est_total_minutes = sum(
        float(tu.get("estimated_teaching_time_minutes") or 0) for tu in teaching_units.values()
    )
    # assessment_coverage_rate: fraction of concepts with >= 1 real assessment item
    concepts_with_assessments = sum(
        1 for tu in teaching_units.values()
        if any(
            a.get("provenance_tier") != "empty_placeholder"
            for a in (tu.get("assessments") or []) + (tu.get("practice_questions") or [])
        )
    )
    assessment_coverage_rate = concepts_with_assessments / max(1, n_concepts)

    stats = {
        "total_concepts": n_concepts,
        "total_teaching_units": n_tu,
        "total_learning_objectives": total_learning_objectives,
        "total_assessments": total_assessments,
        "total_practice_questions": total_practice_questions,
        "total_prerequisites": total_prerequisites,
        "total_ekg_edges": total_ekg_edges,
        "total_edg_edges": total_edg_edges,
        "total_curriculum_links": total_curriculum_links,
        "total_figures": total_figures,
        "total_examples": total_examples,
        "total_formulae": total_formulae,
        "total_worked_examples": total_worked_examples,
        "total_activities": total_activities,
        "coverage_score": round(coverage_score, 4),
        "avg_completeness_score": round(avg_completeness, 4),
        "avg_prerequisites_per_concept": round(avg_prereqs, 4),
        "estimated_total_teaching_time_minutes": round(est_total_minutes, 2),
        "assessment_coverage_rate": round(assessment_coverage_rate, 4),
    }
    context.set_output(STAGE, stats)
    logger.info("Statistics: %d concepts, coverage=%.2f, avg_completeness=%.2f",
                n_concepts, coverage_score, avg_completeness)
