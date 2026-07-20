"""
teacher_knowledge_base/statistics.py — M6.1: TKB statistics computation.

SCOPE (per M6.1 spec §8): computes all statistics blocks required by
TEACHER_KNOWLEDGE_BASE_SCHEMA.md:
  - concept_statistics
  - teaching_unit_statistics
  - graph_statistics
  - runtime_index_statistics
  - navigation_statistics
  - validation_statistics
  - memory_estimates
  - quality_statistics
  - build_statistics

REUSE, DON'T RECOMPUTE: every statistic is derived from the outputs already
produced by the builder pipeline stages — this module never re-scans the
original compiler artifacts or re-derives any enrichment. It reads from
TKBContext outputs only.

DETERMINISM: all statistics are deterministic functions of their inputs
(counts, sums, derived ratios). No random values, no timestamps used in
content (generated_at is volatile, stripped by canonicalization before
fingerprinting).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.statistics")

STATS_VERSION = "M6.1.0"
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


def _build_statistics(context: "TKBContext") -> None:
    outputs = context.outputs
    ekg = outputs.get("ekg") or {}
    edg = outputs.get("edg") or {}
    edst = outputs.get("edst") or {}
    teaching_units = outputs.get("teaching_units") or []
    cpt = outputs.get("concept_progression_templates") or []
    curriculum_graph = outputs.get("curriculum_graph") or {}
    navigation = outputs.get("navigation") or {}
    runtime_indexes = outputs.get("runtime_indexes") or {}
    diagnostics = context.diagnostics

    stats = {
        "version": STATS_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),  # volatile — stripped from fingerprint
        "concept_statistics": _concept_statistics(ekg),
        "teaching_unit_statistics": _teaching_unit_statistics(teaching_units, cpt),
        "graph_statistics": _graph_statistics(ekg, edg, edst, curriculum_graph),
        "runtime_index_statistics": _runtime_index_statistics(runtime_indexes),
        "navigation_statistics": _navigation_statistics(navigation),
        "validation_statistics": _validation_statistics(diagnostics),
        "memory_estimates": _memory_estimates(ekg, teaching_units, runtime_indexes),
        "quality_statistics": _quality_statistics(ekg, teaching_units, cpt),
        "build_statistics": _build_statistics_block(context),
    }
    context.set_output(STAGE, stats)
    logger.info("Statistics builder: computed all statistics blocks.")


def _concept_statistics(ekg: Dict[str, Any]) -> Dict[str, Any]:
    nodes = ekg.get("nodes") or []
    difficulty_dist = ekg.get("difficulty_distribution") or {}
    bloom_dist = (ekg.get("enrichment_metadata") or {}).get("bloom_distribution") or {}

    difficulties = [n.get("pedagogical_metadata", {}).get("difficulty_level", "medium") for n in nodes]
    bloom_levels = [n.get("pedagogical_metadata", {}).get("bloom_taxonomy_level", "understand") for n in nodes]

    concepts_with_prereqs = sum(
        1 for n in nodes
        if n.get("pedagogical_metadata", {}).get("prerequisite_concept_ids")
    )
    concepts_with_misconceptions = sum(
        1 for n in nodes
        if n.get("pedagogical_metadata", {}).get("misconception_flags")
    )
    avg_mastery_time = (
        sum(n.get("pedagogical_metadata", {}).get("estimated_mastery_time_minutes", 30) for n in nodes)
        / max(1, len(nodes))
    )

    return {
        "total_concepts": len(nodes),
        "concepts_with_prerequisites": concepts_with_prereqs,
        "concepts_with_misconceptions": concepts_with_misconceptions,
        "difficulty_distribution": difficulty_dist or _count_list(difficulties),
        "bloom_level_distribution": bloom_dist or _count_list(bloom_levels),
        "average_mastery_time_minutes": round(avg_mastery_time, 2),
        "total_estimated_learning_time_minutes": sum(
            n.get("pedagogical_metadata", {}).get("estimated_mastery_time_minutes", 30) for n in nodes
        ),
    }


def _teaching_unit_statistics(
    teaching_units: List[Dict[str, Any]],
    cpt: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not teaching_units:
        return {
            "total_units": 0, "total_progression_templates": len(cpt),
            "difficulty_distribution": {}, "average_concepts_per_unit": 0,
            "average_duration_minutes": 0, "total_estimated_duration_minutes": 0,
        }

    difficulties = [u.get("difficulty_level", "medium") for u in teaching_units]
    concept_counts = [len(u.get("concepts", [])) for u in teaching_units]
    durations = [u.get("estimated_duration_minutes", 30) for u in teaching_units]

    return {
        "total_units": len(teaching_units),
        "total_progression_templates": len(cpt),
        "difficulty_distribution": _count_list(difficulties),
        "average_concepts_per_unit": round(sum(concept_counts) / max(1, len(concept_counts)), 2),
        "min_concepts_per_unit": min(concept_counts) if concept_counts else 0,
        "max_concepts_per_unit": max(concept_counts) if concept_counts else 0,
        "average_duration_minutes": round(sum(durations) / max(1, len(durations)), 2),
        "total_estimated_duration_minutes": sum(durations),
        "units_with_prerequisites": sum(1 for u in teaching_units if u.get("prerequisite_unit_ids")),
    }


def _graph_statistics(
    ekg: Dict[str, Any],
    edg: Dict[str, Any],
    edst: Dict[str, Any],
    curriculum_graph: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ekg": {
            "node_count": len(ekg.get("nodes") or []),
            "edge_count": len(ekg.get("edges") or []),
            "cluster_count": len(ekg.get("concept_clusters") or []),
            "learning_path_count": len(ekg.get("learning_paths") or []),
        },
        "edg": {
            "node_count": len(edg.get("nodes") or []),
            "edge_count": len(edg.get("edges") or []),
            "cycle_count": len(edg.get("cycles_detected") or []),
            "has_cycles": bool(edg.get("cycles_detected")),
            "dependency_type_distribution": (edg.get("enrichment_metadata") or {}).get("dependency_type_distribution", {}),
        },
        "edst": {
            "node_count": len(edst.get("nodes") or []),
            "node_type_distribution": (edst.get("enrichment_metadata") or {}).get("node_types", {}),
        },
        "curriculum_graph": {
            "unit_node_count": len(curriculum_graph.get("nodes") or []),
            "edge_count": len(curriculum_graph.get("edges") or []),
            "chapter_count": len(curriculum_graph.get("chapters") or []),
        },
    }


def _runtime_index_statistics(runtime_indexes: Dict[str, Any]) -> Dict[str, Any]:
    ri_meta = runtime_indexes.get("metadata") or {}
    return {
        "total_concepts_indexed": ri_meta.get("total_concepts_indexed", len(runtime_indexes.get("concept_by_id") or {})),
        "total_units_indexed": ri_meta.get("total_units_indexed", len(runtime_indexes.get("teaching_unit_by_id") or {})),
        "total_chapters_indexed": ri_meta.get("total_chapters_indexed", len(runtime_indexes.get("concept_by_chapter") or {})),
        "total_prerequisite_entries": ri_meta.get("total_prerequisite_entries", 0),
        "total_learning_path_entries": ri_meta.get("total_learning_path_entries", 0),
        "index_count": len([k for k in runtime_indexes if k not in ("version", "metadata")]),
    }


def _navigation_statistics(navigation: Dict[str, Any]) -> Dict[str, Any]:
    nav_meta = navigation.get("metadata") or {}
    return {
        "total_concepts_indexed": nav_meta.get("total_concepts_indexed", len(navigation.get("concept_map") or {})),
        "total_units_indexed": nav_meta.get("total_units_indexed", len(navigation.get("teaching_unit_map") or {})),
        "total_chapters_indexed": nav_meta.get("total_chapters_indexed", len(navigation.get("chapter_map") or {})),
        "breadcrumb_index_size": len(navigation.get("breadcrumb_index") or {}),
    }


def _validation_statistics(diagnostics: "TKBDiagnostics") -> Dict[str, Any]:  # noqa: F821
    return {
        "total_errors": len(diagnostics.errors),
        "total_warnings": len(diagnostics.warnings),
        "total_ambiguities": len(diagnostics.ambiguities),
        "validation_passed": not diagnostics.has_errors,
    }


def _memory_estimates(
    ekg: Dict[str, Any],
    teaching_units: List[Dict[str, Any]],
    runtime_indexes: Dict[str, Any],
) -> Dict[str, Any]:
    """Rough memory estimates using sys.getsizeof on key structures.
    These are estimates for capacity planning — not precise measurements."""

    def _estimate_bytes(obj: Any) -> int:
        try:
            return sys.getsizeof(json.dumps(obj, default=str).encode("utf-8"))
        except Exception:
            return 0

    return {
        "ekg_estimate_bytes": _estimate_bytes(ekg),
        "teaching_units_estimate_bytes": _estimate_bytes(teaching_units),
        "runtime_indexes_estimate_bytes": _estimate_bytes(runtime_indexes),
        "total_estimate_bytes": (
            _estimate_bytes(ekg)
            + _estimate_bytes(teaching_units)
            + _estimate_bytes(runtime_indexes)
        ),
        "note": "Estimates based on JSON serialization size. Actual in-memory size will vary.",
    }


def _quality_statistics(
    ekg: Dict[str, Any],
    teaching_units: List[Dict[str, Any]],
    cpt: List[Dict[str, Any]],
) -> Dict[str, Any]:
    nodes = ekg.get("nodes") or []
    total = max(1, len(nodes))
    with_bloom = sum(1 for n in nodes if n.get("pedagogical_metadata", {}).get("bloom_taxonomy_level"))
    with_prereqs = sum(1 for n in nodes if n.get("pedagogical_metadata", {}).get("prerequisite_concept_ids"))
    with_hints = sum(1 for n in nodes if n.get("pedagogical_metadata", {}).get("teaching_hints"))

    return {
        "enrichment_coverage": {
            "concepts_with_bloom_level": with_bloom,
            "concepts_with_prerequisites": with_prereqs,
            "concepts_with_teaching_hints": with_hints,
            "bloom_coverage_pct": round(with_bloom / total * 100, 1),
            "prerequisite_coverage_pct": round(with_prereqs / total * 100, 1),
        },
        "teaching_unit_coverage": {
            "units_with_learning_objectives": sum(1 for u in teaching_units if u.get("learning_objectives")),
            "units_with_bloom_levels": sum(1 for u in teaching_units if u.get("bloom_levels")),
            "units_with_prerequisites": sum(1 for u in teaching_units if u.get("prerequisite_unit_ids")),
        },
        "progression_template_coverage": len(cpt),
    }


def _build_statistics_block(context: "TKBContext") -> Dict[str, Any]:  # noqa: F821
    return {
        "pipeline_stages_completed": context.completed_stages,
        "stage_timings_seconds": context.stage_timings,
        "total_build_time_seconds": round(sum(context.stage_timings.values()), 4),
        "artifact_id": context.artifact_id,
        "pipeline_version": context.metadata.pipeline_version,
    }


def _count_list(items: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts
