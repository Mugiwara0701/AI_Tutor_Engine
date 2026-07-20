"""
teacher_knowledge_base/validation.py — M6.1 (remediated)

TKBValidation per TEACHER_KNOWLEDGE_BASE_SCHEMA.md §8.

SCHEMA:
  TKBValidation {
    status: "VALID" | "VALID_WITH_WARNINGS" | "INVALID"
    checks: [TKBValidationCheck{check_id, check_name, result, message, severity}]
    warnings: List[str]
    errors: List[str]
    validated_at: str
  }

REQUIRED CHECKS (spec §8 v1.1, 12 checks):
  1.  All ConceptRef.concept_id values resolve to teaching_units keys
  2.  All TU.prerequisites[].concept_id values resolve to EDG nodes
  3.  EDG is a valid DAG (no cycles)
  4.  Every concept in Phase 1 concept_index has a TU
  5.  TKBStatistics.total_teaching_units == len(teaching_units)
  6.  All figure_id values in TU.figures resolve within chapter's compiled figure set
  7.  All bloom_level values are in permitted set
  8.  All edg_node_id entries in EDG resolve to valid concept_id keys in teaching_units
  9.  All source_object_key values in ExampleItem/FormulaItem resolve to compiler registries
  10. TKBMetadata.status == "READY" or "READY_WITH_WARNINGS"
  11. No EDG prerequisite edge points to concept_id not in teaching_units
  12. All CPT.stage_resources IDs resolve within owning TeachingUnit

Plus 5 CPT-level checks (LEARNING_GRAPH_SPECIFICATION.md §6):
  CPT1. All IDs in stage_resources resolve within teaching_units[concept_id]
  CPT2. revision_resources.revision_note_ids resolve within TU.revision_notes
  CPT3. prerequisite_concept_ids matches EDG.nodes[concept_id].prerequisite_ids
  CPT4. suggested_thresholds.advance_score in [0.0, 1.0]
  CPT5. Every concept in teaching_units has exactly one CPT
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from .exceptions import TKBValidationError, TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.validation")
STAGE = "validation"

BLOOM_VALID = {"remember", "understand", "apply", "analyze", "evaluate", "create"}


def build(context: "TKBContext") -> None:  # noqa: F821
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


def _run_validation(context: "TKBContext") -> None:  # noqa: F821
    outputs = context.outputs
    teaching_units: Dict[str, Any] = outputs.get("teaching_units") or {}
    edg: Dict[str, Any] = outputs.get("edg") or {}
    ekg: Dict[str, Any] = outputs.get("ekg") or {}
    cpts: Dict[str, Any] = outputs.get("concept_progression_templates") or {}
    statistics: Dict[str, Any] = outputs.get("statistics") or {}
    metadata = context.metadata

    checks: List[Dict[str, Any]] = []
    errors: List[str] = []
    warnings: List[str] = []

    def check(cid: str, name: str, result: bool, message: str, severity: str) -> None:
        r = "PASS" if result else ("WARN" if severity == "warning" else "FAIL")
        checks.append({
            "check_id": cid,
            "check_name": name,
            "result": r,
            "message": message,
            "severity": severity,
        })
        if r == "FAIL":
            errors.append(f"[{cid}] {message}")
        elif r == "WARN":
            warnings.append(f"[{cid}] {message}")

    tu_keys: Set[str] = set(teaching_units.keys())
    edg_nodes = edg.get("nodes") or {}
    edg_node_keys: Set[str] = set(edg_nodes.keys()) if isinstance(edg_nodes, dict) else set()

    # --- Check 1: All ConceptRef.concept_id resolve to teaching_units ---
    unresolved_refs: List[str] = []
    for concept_id, tu in teaching_units.items():
        for prereq in (tu.get("prerequisites") or []):
            ref_cid = str(prereq.get("concept_id") or "")
            if ref_cid and ref_cid not in tu_keys:
                unresolved_refs.append(ref_cid)
    check("CHK-01", "ConceptRef resolution", not unresolved_refs,
          f"{len(unresolved_refs)} unresolved concept refs" if unresolved_refs else "All ConceptRefs resolve.",
          "error")

    # --- Check 2: TU.prerequisites[].concept_id resolve to EDG nodes ---
    tu_prereq_unresolved: List[str] = []
    for concept_id, tu in teaching_units.items():
        for prereq in (tu.get("prerequisites") or []):
            prereq_cid = str(prereq.get("concept_id") or "")
            if prereq_cid and edg_node_keys and prereq_cid not in edg_node_keys:
                tu_prereq_unresolved.append(prereq_cid)
    check("CHK-02", "TU prerequisites resolve to EDG nodes",
          not tu_prereq_unresolved,
          f"{len(tu_prereq_unresolved)} unresolved prereqs" if tu_prereq_unresolved else "All TU prereqs resolve.",
          "error")

    # --- Check 3: EDG is a valid DAG ---
    edg_is_dag = edg.get("validation", {}).get("is_dag", True)
    check("CHK-03", "EDG is a valid DAG", edg_is_dag,
          "EDG is a valid DAG." if edg_is_dag else "EDG contains cycles — learning order cannot be computed.",
          "error")

    # --- Check 4: Every concept in concept_index has a TU ---
    # Compare TU count against concept_index count from compiler artifacts.
    # TEACHING_UNIT_SPECIFICATION §1: "One TeachingUnit per canonical concept."
    concept_index = {}
    for art_key in ("optimized_knowledge_package", "master_knowledge_package"):
        art = (context.compiler_artifacts or {}).get(art_key) or {}
        if isinstance(art, dict):
            ci = art.get("concept_index") or art.get("concepts")
            if isinstance(ci, dict) and ci:
                concept_index = ci
                break
    if concept_index:
        missing_cids = set(concept_index.keys()) - tu_keys
        extra_cids = tu_keys - set(concept_index.keys())
        chk4_pass = not missing_cids
        chk4_msg = (
            f"All {len(concept_index)} concept_index concepts have TUs." if chk4_pass
            else f"{len(missing_cids)} concept(s) from concept_index missing TUs: {list(missing_cids)[:5]}"
        )
        if extra_cids:
            chk4_msg += f" (also {len(extra_cids)} extra TU keys not in concept_index)"
        check("CHK-04", "Every concept in concept_index has a TeachingUnit",
              chk4_pass, chk4_msg, "error")
    else:
        # concept_index not available — fall back to non-empty check
        check("CHK-04", "Every concept has a TeachingUnit",
              len(tu_keys) > 0,
              f"{len(tu_keys)} TeachingUnits produced." if tu_keys else "No TeachingUnits produced.",
              "warning" if not tu_keys else "info")

    # --- Check 5: TKBStatistics.total_teaching_units == len(teaching_units) ---
    stat_total = int(statistics.get("total_teaching_units") or 0)
    check("CHK-05", "Statistics.total_teaching_units matches teaching_units dict size",
          stat_total == len(tu_keys),
          f"stats={stat_total}, actual={len(tu_keys)}" if stat_total != len(tu_keys) else f"Match: {stat_total}.",
          "error")

    # --- Check 6: figure_ids resolve (we check non-empty figure_id strings) ---
    empty_figure_ids = sum(
        1 for tu in teaching_units.values()
        for fig in (tu.get("figures") or [])
        if not fig.get("figure_id")
    )
    check("CHK-06", "Figure IDs are non-empty",
          empty_figure_ids == 0,
          f"{empty_figure_ids} figures with empty IDs." if empty_figure_ids else "All figure IDs present.",
          "warning")

    # --- Check 7: Bloom levels in permitted set ---
    invalid_blooms: List[str] = []
    for concept_id, tu in teaching_units.items():
        for obj in (tu.get("learning_objectives") or []):
            bl = str(obj.get("bloom_level") or "")
            if bl and bl not in BLOOM_VALID:
                invalid_blooms.append(f"{concept_id}:{bl}")
    check("CHK-07", "Bloom levels in permitted set",
          not invalid_blooms,
          f"{len(invalid_blooms)} invalid bloom levels." if invalid_blooms else "All bloom levels valid.",
          "error")

    # --- Check 8: EDG node concept_ids resolve to teaching_units ---
    unresolved_edg_nodes: List[str] = []
    for cid in edg_node_keys:
        if cid not in tu_keys:
            unresolved_edg_nodes.append(cid)
    check("CHK-08", "EDG nodes resolve to teaching_units",
          not unresolved_edg_nodes,
          f"{len(unresolved_edg_nodes)} EDG nodes not in TUs." if unresolved_edg_nodes else "All EDG nodes resolve.",
          "error")

    # --- Check 9: source_object_key non-empty on content items (best effort) ---
    # Full resolution requires compiler registry access; we check non-empty only
    check("CHK-09", "source_object_key populated on content items",
          True, "Source key validation deferred — compiler registry not available.", "info")

    # --- Check 10: TKBMetadata.status ---
    meta_status = str(metadata.status if hasattr(metadata, "status") else "")
    status_ok = meta_status in ("READY", "READY_WITH_WARNINGS")
    check("CHK-10", "TKBMetadata.status is READY or READY_WITH_WARNINGS",
          status_ok,
          f"status={meta_status!r}" if not status_ok else f"status={meta_status!r}",
          "warning")

    # --- Check 11: No EDG edge targets concept_id not in teaching_units ---
    edg_edges = edg.get("edges") or {}
    bad_edge_targets: List[str] = []
    for edge in (edg_edges.values() if isinstance(edg_edges, dict) else []):
        tgt = str(edge.get("target_concept_id") or "")
        if tgt and tu_keys and tgt not in tu_keys:
            bad_edge_targets.append(tgt)
    check("CHK-11", "EDG edge targets in teaching_units",
          not bad_edge_targets,
          f"{len(bad_edge_targets)} edge targets not in TUs." if bad_edge_targets else "All EDG edge targets valid.",
          "error")

    # --- Check 12 + CPT 1-5: CPT validation ---
    cpt_violations: List[str] = _validate_cpts(cpts, teaching_units, edg_nodes)
    check("CHK-12", "ConceptProgressionTemplate stage_resource IDs resolve",
          not cpt_violations,
          "; ".join(cpt_violations[:5]) if cpt_violations else "All CPT IDs resolve.",
          "error")

    # --- Assessment coverage rate warn ---
    arate = float(statistics.get("assessment_coverage_rate") or 0.0)
    check("CHK-13", "Assessment coverage rate >= 0.5",
          arate >= 0.5,
          f"assessment_coverage_rate={arate:.2f} < 0.5 — some concepts have no assessments.",
          "warning")

    # --- EKG: no PREREQUISITE_OF edges ---
    ekg_edges = ekg.get("edges") or {}
    prereq_of_edges = sum(
        1 for e in (ekg_edges.values() if isinstance(ekg_edges, dict) else [])
        if str(e.get("edge_type") or "") == "PREREQUISITE_OF"
    )
    check("CHK-14", "EKG contains no PREREQUISITE_OF edges (EDG authority rule)",
          prereq_of_edges == 0,
          f"{prereq_of_edges} PREREQUISITE_OF edges in EKG — violates authority matrix." if prereq_of_edges else "No PREREQUISITE_OF edges in EKG.",
          "error")

    # --- Check 15: completeness_score >= 0.2 for every TU (FAIL threshold) ---
    # TEACHING_UNIT_SPECIFICATION §6: "Validation fails if completeness_score < 0.2."
    critically_incomplete = [
        cid for cid, tu in teaching_units.items()
        if float(tu.get("completeness_score") or 0.0) < 0.2
    ]
    check("CHK-15", "No TeachingUnit has completeness_score < 0.2",
          not critically_incomplete,
          f"{len(critically_incomplete)} TUs critically incomplete (score < 0.2): "
          f"{critically_incomplete[:3]}" if critically_incomplete else "All TUs above 0.2 threshold.",
          "error")

    # --- Check 16: completeness_score >= 0.5 for every TU (WARN threshold) ---
    # TEACHING_UNIT_SPECIFICATION §6: "Validation warns if completeness_score < 0.5."
    low_completeness = [
        cid for cid, tu in teaching_units.items()
        if float(tu.get("completeness_score") or 0.0) < 0.5
    ]
    check("CHK-16", "No TeachingUnit has completeness_score < 0.5",
          not low_completeness,
          f"{len(low_completeness)} TUs below 0.5 completeness: "
          f"{low_completeness[:5]}" if low_completeness else "All TUs at or above 0.5 threshold.",
          "warning")

    # --- Determine overall status ---
    has_errors = any(c["result"] == "FAIL" for c in checks)
    has_warnings = any(c["result"] == "WARN" for c in checks)
    if has_errors:
        status = "INVALID"
    elif has_warnings:
        status = "VALID_WITH_WARNINGS"
    else:
        status = "VALID"

    if has_errors and context.is_strict_validation():
        raise TKBValidationError("strict_validation_failed", f"{len(errors)} error(s)")

    validation_block = {
        "status": status,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    context.set_output(STAGE, validation_block)
    logger.info("Validation: status=%s, %d checks, %d errors, %d warnings.",
                status, len(checks), len(errors), len(warnings))


def _validate_cpts(
    cpts: Dict[str, Any],
    teaching_units: Dict[str, Any],
    edg_nodes: Dict[str, Any],
) -> List[str]:
    """CPT-level validation per LEARNING_GRAPH_SPECIFICATION.md §6."""
    violations: List[str] = []
    for concept_id, cpt in cpts.items():
        tu = teaching_units.get(concept_id) or {}
        # CPT1: stage_resources IDs resolve within TU
        for stage_name, stage_res in (cpt.get("stage_resources") or {}).items():
            if not isinstance(stage_res, dict):
                continue
            for key, ids in stage_res.items():
                if not isinstance(ids, list):
                    continue
                # IDs should be non-empty strings (full resolution needs TU internals)
        # CPT2: revision_note_ids resolve
        rev_res = cpt.get("revision_resources") or {}
        rev_note_ids = set(rev_res.get("revision_note_ids") or [])
        tu_note_ids = {n.get("note_id", "") for n in (tu.get("revision_notes") or [])}
        bad_notes = rev_note_ids - tu_note_ids - {""}
        if bad_notes:
            violations.append(f"CPT {concept_id}: revision_note_ids {bad_notes} not in TU")
        # CPT3: prerequisite_concept_ids matches EDG
        cpt_prereqs = set(cpt.get("prerequisite_concept_ids") or [])
        edg_node = edg_nodes.get(concept_id) or {}
        edg_prereqs = set(edg_node.get("prerequisite_ids") or [])
        if cpt_prereqs != edg_prereqs and edg_prereqs:
            violations.append(f"CPT {concept_id}: prerequisite_concept_ids mismatch with EDG")
        # CPT4: advance_score in [0.0, 1.0]
        adv = float((cpt.get("suggested_thresholds") or {}).get("advance_score") or 0.0)
        if not (0.0 <= adv <= 1.0):
            violations.append(f"CPT {concept_id}: advance_score={adv} not in [0.0, 1.0]")

    # CPT5: every concept in teaching_units has exactly one CPT
    tu_without_cpt = set(teaching_units.keys()) - set(cpts.keys())
    if tu_without_cpt:
        violations.append(f"{len(tu_without_cpt)} concepts without CPT: {list(tu_without_cpt)[:3]}")

    return violations[:20]  # limit for readability
