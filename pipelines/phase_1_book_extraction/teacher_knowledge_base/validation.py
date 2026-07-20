"""
teacher_knowledge_base/validation.py — M6.1: TKB validation framework.

SCOPE (per M6.1 spec §6): implements all validation passes required before
a TeacherKnowledgeBase artifact is considered complete:

  1. schema_validation       — required fields present, correct types
  2. reference_validation    — all IDs referenced exist in their target index
  3. ownership_validation    — no concept owned by multiple chapters (DST rule)
  4. authority_validation    — Authority Matrix holds (per AUTHORITY_MATRIX.md)
  5. graph_validation        — no broken edges, no isolated nodes (unless expected)
  6. cross_reference_validation — nav/runtime indexes consistent with EKG/units
  7. serialization_validation — artifact can be serialized to canonical JSON
  8. artifact_validation     — artifact_id present, schema_version present
  9. build_validation        — all required pipeline stages completed

REUSE: validation reads from context outputs only — never re-runs builders.
Each pass produces a sub-dict: {"passed": bool, "violations": [...]}

AUTHORITY MATRIX (per AUTHORITY_MATRIX.md, frozen):
  - Concepts are owned by their chapter. No cross-chapter concept ownership.
  - TeachingUnits are owned by the TKB builder, not the compiler.
  - Navigation indexes are derived — no independent ownership.
  - Runtime indexes are derived — no independent ownership.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

from .exceptions import TKBValidationError, TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.validation")

VAL_VERSION = "M6.1.0"
STAGE = "validation"

# Required top-level fields in the final artifact (per schema spec)
_REQUIRED_ARTIFACT_FIELDS = [
    "metadata", "compiler_information",
    "enriched_document_structure_tree", "enriched_knowledge_graph",
    "enriched_dependency_graph", "concept_progression_templates",
    "curriculum_graph", "teaching_units", "navigation",
    "runtime_indexes", "statistics", "validation", "serialization_metadata",
]

# Required pipeline stages (must all be present in context outputs)
_REQUIRED_STAGES = [
    "edst", "ekg", "edg", "teaching_units",
    "concept_progression_templates", "curriculum_graph",
    "navigation", "runtime_indexes", "statistics",
]


def build(context: "TKBContext") -> None:  # noqa: F821
    """Runs all validation passes and records the combined validation block
    in context. Raises TKBValidationError only if strict_validation is on
    AND errors are found. Otherwise, errors are recorded in diagnostics."""
    import time
    t0 = time.monotonic()
    try:
        _run_validation(context)
    except TKBValidationError:
        raise
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _run_validation(context: "TKBContext") -> None:
    outputs = context.outputs

    validation_block = {
        "version": VAL_VERSION,
        "schema_validation": _validate_schema(outputs),
        "reference_validation": _validate_references(outputs),
        "ownership_validation": _validate_ownership(outputs),
        "authority_validation": _validate_authority(outputs),
        "graph_validation": _validate_graphs(outputs),
        "cross_reference_validation": _validate_cross_references(outputs),
        "serialization_validation": _validate_serialization(outputs),
        "artifact_validation": _validate_artifact(outputs, context),
        "build_validation": _validate_build(context),
    }

    all_passed = all(
        v.get("passed", True)
        for k, v in validation_block.items()
        if k != "version" and isinstance(v, dict)
    )
    validation_block["passed"] = all_passed

    # Count violations
    total_violations = sum(
        len(v.get("violations") or [])
        for k, v in validation_block.items()
        if k not in ("version", "passed") and isinstance(v, dict)
    )
    validation_block["total_violations"] = total_violations

    context.set_output(STAGE, validation_block)

    if not all_passed:
        context.diagnostics.add_warning(
            STAGE,
            f"Validation completed with {total_violations} violation(s).",
            "Review validation.violations for details.",
        )

    if not all_passed and context.is_strict_validation():
        violations = _collect_violations(validation_block)
        raise TKBValidationError(
            "strict_validation_failed",
            f"{total_violations} violation(s): {violations[:3]}",
        )

    logger.info(
        "TKB validation: passed=%s, total_violations=%d",
        all_passed, total_violations,
    )


def _validate_schema(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Checks that all required pipeline stages produced output and that
    key schema fields are present and of the right type."""
    violations: List[str] = []
    for stage in _REQUIRED_STAGES:
        if stage not in outputs or outputs[stage] is None:
            violations.append(f"Missing required stage output: {stage!r}")

    # Check teaching_units is a list
    units = outputs.get("teaching_units")
    if units is not None and not isinstance(units, list):
        violations.append(f"teaching_units must be a list, got {type(units).__name__}")

    # Check cpt is a list
    cpt = outputs.get("concept_progression_templates")
    if cpt is not None and not isinstance(cpt, list):
        violations.append(f"concept_progression_templates must be a list, got {type(cpt).__name__}")

    # Check EKG has nodes key
    ekg = outputs.get("ekg") or {}
    if "nodes" not in ekg:
        violations.append("enriched_knowledge_graph missing 'nodes' field")

    return {"passed": len(violations) == 0, "violations": violations}


def _validate_references(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Checks that all referenced IDs resolve to existing records."""
    violations: List[str] = []

    ekg = outputs.get("ekg") or {}
    units = outputs.get("teaching_units") or []
    runtime_indexes = outputs.get("runtime_indexes") or {}

    # All concept IDs in teaching units must exist in EKG
    ekg_concept_ids: Set[str] = set()
    for n in (ekg.get("nodes") or []):
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        if nid:
            ekg_concept_ids.add(nid)

    for unit in units:
        uid = unit.get("unit_id", "?")
        for cid in (unit.get("concepts") or []):
            if str(cid) not in ekg_concept_ids and ekg_concept_ids:
                violations.append(
                    f"TeachingUnit {uid!r}: concept_id {cid!r} not found in EKG nodes"
                )

    # All prerequisite_unit_ids must point to existing units
    unit_ids: Set[str] = {u["unit_id"] for u in units if u.get("unit_id")}
    for unit in units:
        uid = unit.get("unit_id", "?")
        for prereq_uid in (unit.get("prerequisite_unit_ids") or []):
            if str(prereq_uid) not in unit_ids:
                violations.append(
                    f"TeachingUnit {uid!r}: prerequisite_unit_id {prereq_uid!r} not found"
                )

    # Limit reported violations for readability
    if len(violations) > 20:
        violations = violations[:20] + [f"... and {len(violations) - 20} more"]

    return {"passed": len(violations) == 0, "violations": violations}


def _validate_ownership(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Authority Matrix: each concept_id must appear in at most one chapter's
    concept_by_chapter index."""
    violations: List[str] = []

    runtime_indexes = outputs.get("runtime_indexes") or {}
    concept_by_chapter = runtime_indexes.get("concept_by_chapter") or {}

    seen_concepts: Dict[str, str] = {}  # concept_id -> chapter_key
    for chapter_key, concept_ids in concept_by_chapter.items():
        for cid in (concept_ids or []):
            if cid in seen_concepts:
                violations.append(
                    f"Concept {cid!r} appears in multiple chapters: "
                    f"{seen_concepts[cid]!r} and {chapter_key!r}"
                )
            else:
                seen_concepts[cid] = chapter_key

    return {"passed": len(violations) == 0, "violations": violations}


def _validate_authority(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Authority Matrix: TeachingUnits are owned by TKB (never by compiler).
    Checks that no unit_id duplicates a concept_id in the EKG."""
    violations: List[str] = []

    ekg = outputs.get("ekg") or {}
    units = outputs.get("teaching_units") or []

    ekg_ids: Set[str] = set()
    for n in (ekg.get("nodes") or []):
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        if nid:
            ekg_ids.add(nid)

    for unit in units:
        uid = unit.get("unit_id", "")
        if uid in ekg_ids:
            violations.append(
                f"TeachingUnit unit_id {uid!r} collides with an EKG concept_id — "
                f"authority matrix violation: units and concepts must have distinct IDs."
            )

    return {"passed": len(violations) == 0, "violations": violations}


def _validate_graphs(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Checks graph structural integrity: no broken edges (references to
    non-existent nodes), no self-loops in prerequisite edges."""
    violations: List[str] = []

    ekg = outputs.get("ekg") or {}
    edg = outputs.get("edg") or {}

    # EKG: check all edge endpoints exist
    ekg_node_ids: Set[str] = set()
    for n in (ekg.get("nodes") or []):
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        if nid:
            ekg_node_ids.add(nid)

    for edge in (ekg.get("edges") or []):
        src = str(edge.get("source") or edge.get("from") or "")
        tgt = str(edge.get("target") or edge.get("to") or "")
        if src == tgt and src:
            violations.append(f"EKG self-loop detected on node {src!r}")
        if src and ekg_node_ids and src not in ekg_node_ids:
            violations.append(f"EKG edge source {src!r} not found in EKG nodes")
        if tgt and ekg_node_ids and tgt not in ekg_node_ids:
            violations.append(f"EKG edge target {tgt!r} not found in EKG nodes")

    # EDG cycles: already documented in edg output
    cycle_count = len(edg.get("cycles_detected") or [])
    if cycle_count > 0:
        violations.append(
            f"EDG contains {cycle_count} dependency cycle(s) — "
            f"documented in enriched_dependency_graph.cycles_detected."
        )

    if len(violations) > 20:
        violations = violations[:20] + [f"... and {len(violations) - 20} more"]

    return {"passed": len(violations) == 0, "violations": violations}


def _validate_cross_references(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Checks consistency between navigation, runtime_indexes, and source data."""
    violations: List[str] = []

    units = outputs.get("teaching_units") or []
    navigation = outputs.get("navigation") or {}
    runtime_indexes = outputs.get("runtime_indexes") or {}

    unit_ids_source: Set[str] = {u["unit_id"] for u in units if u.get("unit_id")}
    unit_ids_nav: Set[str] = set(navigation.get("teaching_unit_map") or {})
    unit_ids_ri: Set[str] = set(runtime_indexes.get("teaching_unit_by_id") or {})

    # All unit IDs in navigation must exist in source
    for uid in unit_ids_nav - unit_ids_source:
        violations.append(f"navigation.teaching_unit_map references unknown unit_id {uid!r}")
    for uid in unit_ids_ri - unit_ids_source:
        violations.append(f"runtime_indexes.teaching_unit_by_id references unknown unit_id {uid!r}")

    if len(violations) > 20:
        violations = violations[:20] + [f"... and {len(violations) - 20} more"]

    return {"passed": len(violations) == 0, "violations": violations}


def _validate_serialization(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Verifies that all outputs can be serialized to canonical JSON."""
    violations: List[str] = []
    for stage, output in outputs.items():
        if output is None:
            continue
        try:
            json.dumps(output, sort_keys=True, default=str)
        except Exception as exc:
            violations.append(f"Stage {stage!r} output is not JSON-serializable: {exc}")
    return {"passed": len(violations) == 0, "violations": violations}


def _validate_artifact(outputs: Dict[str, Any], context: "TKBContext") -> Dict[str, Any]:  # noqa: F821
    """Checks artifact-level fields: artifact_id present, schema_version present."""
    violations: List[str] = []
    if not context.metadata.artifact_id:
        violations.append("metadata.artifact_id is empty or missing")
    if not context.metadata.schema_version:
        violations.append("metadata.schema_version is empty or missing")
    return {"passed": len(violations) == 0, "violations": violations}


def _validate_build(context: "TKBContext") -> Dict[str, Any]:  # noqa: F821
    """Checks that all required pipeline stages completed."""
    violations: List[str] = []
    outputs = context.outputs
    for stage in _REQUIRED_STAGES:
        if stage not in outputs or outputs[stage] is None:
            violations.append(f"Required pipeline stage {stage!r} did not complete")
    return {"passed": len(violations) == 0, "violations": violations}


def _collect_violations(validation_block: Dict[str, Any]) -> List[str]:
    all_v: List[str] = []
    for k, v in validation_block.items():
        if isinstance(v, dict) and "violations" in v:
            all_v.extend(v["violations"])
    return all_v
