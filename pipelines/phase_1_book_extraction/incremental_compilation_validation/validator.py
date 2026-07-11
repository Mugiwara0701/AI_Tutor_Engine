"""
incremental_compilation_validation/validator.py — Phase E5.1:
Incremental Compilation Validation Engine.

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C, Phase D, Phase E1 (Build Metadata), Phase E2 (Build Dependency
Graph), Phase E3 (Change Detection), and Phase E4 (Incremental
Compilation) are all frozen -- this module does not redesign compiler/,
knowledge_graph/, validation/, build_metadata/, dependency_graph/,
change_detection/, or incremental_compilation/. It ONLY adds one more
read-only pass that VALIDATES the already-computed Phase E4
IncrementalCompilationPlan -- it never executes compilation, never
rebuilds anything, never modifies the plan, and never generates
readiness, final status, or a build summary (those belong to Phase
E5.2, out of this module's own scope).

REUSE, DON'T RECOMPUTE (task's own explicit requirement, "Reuse
existing outputs from: dependency_graph, change_detection,
incremental_compilation. Never recompute them."): every dirty/clean/
affected/removed/rebuild classification this module checks is read
directly off the `incremental_compilation_plan` argument, exactly as
Phase E4 already computed it -- this module never reruns
change_detection.compare.compare_snapshots(),
change_detection.traversal.compute_affected_artifacts(), or
incremental_compilation.planner.plan_rebuild() itself. The one
exception (module docstring's DETERMINISM CHECK below) calls Phase
E4's own already-existing, already-frozen
incremental_compilation.traversal.compute_rebuild_order() a second time
against the SAME inputs the plan itself already recorded, purely to
confirm reproducibility -- mirroring validation/determinism.py's own
"re-derive with the artifact's own existing generation function and
diff" precedent, one phase up. No new classification algorithm, no new
ordering algorithm, and no new rebuild logic of any kind is introduced
anywhere in this module.

READ-ONLY / DETERMINISTIC: like every validation pass in this codebase,
this module only ever reads its arguments -- nothing here mutates the
IncrementalCompilationPlan, the DependencyGraph, or the
ChangeDetectionReport it is handed (see `_validate_read_only_behaviour()`
below, which explicitly confirms this for every run). Given the same
inputs, `validate_incremental_compilation_plan()` always returns the
same report (modulo `generated_at`).

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Phase E5.2, not Phase F, not a compilation executor, not a cache, not a
persistence layer, not parallel execution, and not distributed
execution -- this module validates a plan that already exists and
reports what it finds, and nothing else.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from canonicalization import canonical_json
from change_detection.snapshot import (
    CONFIGURATION_ARTIFACT_KEY,
    DEPENDENCY_GRAPH_ARTIFACT_KEY,
)
from incremental_compilation.traversal import compute_rebuild_order

from .exceptions import InvalidIncrementalCompilationPlanError
from .report import INCREMENTAL_COMPILATION_VALIDATION_VERSION, IncrementalCompilationValidationReport

# The two synthetic artifact keys change_detection.snapshot.build_snapshot()
# (and therefore Phase E4's own dirty/affected/clean/removed/rebuild
# classifications, which are read straight off that snapshot's own
# keys) mints for the fingerprint families Phase E2 has no
# DependencyNode of its own for -- see change_detection/snapshot.py's
# own CONFIGURATION AND DEPENDENCY-GRAPH KEYS section and
# incremental_compilation/traversal.py's own ARTIFACT KEYS NOT MODELED
# AS A DEPENDENCYNODE section. Read here, never re-derived or
# hand-rolled a second time, so a synthetic key is never misreported as
# a "rebuild target that does not exist".
_SYNTHETIC_ARTIFACT_KEYS = frozenset({CONFIGURATION_ARTIFACT_KEY, DEPENDENCY_GRAPH_ARTIFACT_KEY})

_REQUIRED_PLAN_KEYS = (
    "namespace",
    "has_previous_build",
    "dirty_artifacts",
    "affected_artifacts",
    "rebuild_artifacts",
    "clean_artifacts",
    "removed_artifacts",
    "rebuild_order",
    "rebuild_reasons",
    "reuse_reasons",
    "dependency_traversal_summary",
)


# --------------------------------------------------------------------------
# Small issue-dict helpers -- same shape (`rule`, `message`, `severity`,
# optional `details`) every existing validator in this codebase already
# uses (compiler/validation.py's `_error()`/`_warning()`,
# knowledge_graph/validation.py's own same-named pair,
# validation/system_integrity.py's own same-named pair, reused
# unchanged one layer up).
# --------------------------------------------------------------------------

def _issue(severity: str, rule: str, message: str, **details: Any) -> Dict[str, Any]:
    issue: Dict[str, Any] = {"severity": severity, "rule": rule, "message": message}
    if details:
        issue["details"] = details
    return issue


def _error(rule: str, message: str, **details: Any) -> Dict[str, Any]:
    return _issue("error", rule, message, **details)


def _warning(rule: str, message: str, **details: Any) -> Dict[str, Any]:
    return _issue("warning", rule, message, **details)


def _record(passed: List[str], failed: List[str], name: str, ok: bool) -> None:
    (passed if ok else failed).append(name)


# --------------------------------------------------------------------------
# Plan presence / shape
# --------------------------------------------------------------------------

def _extract_plan(
    incremental_compilation_plan: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validates and returns `incremental_compilation_plan` unchanged
    (never mutated, never a copy substituted for a real field), plus
    any issue found while checking its shape.

    `incremental_compilation_plan=None` is the normal "Phase E4
    produced nothing this chapter" case (mirrors
    incremental_compilation.planner._extract_change_detection_lists()'s
    own `change_detection_report is None` handling one phase down) and
    produces an error (Phase E5.1 has nothing to validate without it),
    never a raised exception. A non-`None` value missing one of the
    fields this module reads is malformed input a caller passed by
    mistake -- surfaced as an error and treated as "nothing to
    validate", never raised (Phase E5.1 is a read-only validation pass,
    and a malformed plan should degrade to a `missing_plan`/
    `malformed_plan` finding, not abort the whole chapter's build)."""
    if incremental_compilation_plan is None:
        return None, [_error(
            "missing_plan",
            "incremental compilation validation: no IncrementalCompilationPlan "
            "was supplied (Phase E4 produced nothing this chapter) -- there is "
            "nothing for Phase E5.1 to validate",
        )]
    if not isinstance(incremental_compilation_plan, dict) or not all(
        key in incremental_compilation_plan for key in _REQUIRED_PLAN_KEYS
    ):
        try:
            raise InvalidIncrementalCompilationPlanError(
                "expected a dict shaped like incremental_compilation.plan."
                "IncrementalCompilationPlan.to_dict()'s own output (missing "
                f"one or more of {_REQUIRED_PLAN_KEYS!r})"
            )
        except InvalidIncrementalCompilationPlanError as exc:
            return None, [_error("malformed_plan", str(exc))]
    return incremental_compilation_plan, []


# --------------------------------------------------------------------------
# 1. Classification Consistency -- dirty / affected / clean / removed /
#    rebuild_artifacts / rebuild_order, read straight off the plan
# --------------------------------------------------------------------------

def _validate_classification_consistency(
    plan: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Checks the plan's own five classification lists (dirty/affected/
    clean/removed/rebuild_artifacts) and its own rebuild_order for
    internal, self-consistency -- every check here compares the plan's
    OWN already-recorded fields against each other (a `set()`/`len()`
    comparison), never against a freshly re-derived classification (see
    module docstring's REUSE, DON'T RECOMPUTE)."""
    issues: List[Dict[str, Any]] = []

    dirty = list(plan.get("dirty_artifacts") or [])
    affected = list(plan.get("affected_artifacts") or [])
    clean = list(plan.get("clean_artifacts") or [])
    removed = list(plan.get("removed_artifacts") or [])
    rebuild_artifacts = list(plan.get("rebuild_artifacts") or [])
    rebuild_order = list(plan.get("rebuild_order") or [])

    duplicate_lists: Dict[str, List[str]] = {}
    for name, values in (
        ("dirty_artifacts", dirty),
        ("affected_artifacts", affected),
        ("clean_artifacts", clean),
        ("removed_artifacts", removed),
        ("rebuild_artifacts", rebuild_artifacts),
        ("rebuild_order", rebuild_order),
    ):
        seen = set()
        dupes = sorted({v for v in values if v in seen or seen.add(v)})
        if dupes:
            duplicate_lists[name] = dupes
            issues.append(_error(
                f"duplicate_entries_in_{name}",
                f"incremental compilation validation: plan's own {name!r} "
                f"contains duplicate entrie(s): {dupes!r}",
            ))

    # -- pairwise disjoint: no artifact key is classified more than one
    # way by this same plan. --
    groups = {
        "dirty_artifacts": set(dirty),
        "affected_artifacts": set(affected),
        "clean_artifacts": set(clean),
        "removed_artifacts": set(removed),
    }
    overlaps: Dict[str, List[str]] = {}
    group_names = list(groups.keys())
    for i, left_name in enumerate(group_names):
        for right_name in group_names[i + 1:]:
            overlap = sorted(groups[left_name] & groups[right_name])
            if overlap:
                key = f"{left_name}&{right_name}"
                overlaps[key] = overlap
                issues.append(_error(
                    "overlapping_classification",
                    f"incremental compilation validation: {overlap!r} appear "
                    f"in both plan's own {left_name!r} and {right_name!r}",
                ))

    # -- rebuild_artifacts is exactly dirty union affected (the plan's
    # own stated union, never a second, independently re-derived
    # union). --
    expected_rebuild_set = set(dirty) | set(affected)
    rebuild_set_matches_union = set(rebuild_artifacts) == expected_rebuild_set
    if not rebuild_set_matches_union:
        issues.append(_error(
            "rebuild_artifacts_not_dirty_union_affected",
            "incremental compilation validation: plan's own rebuild_artifacts "
            "does not equal the union of its own dirty_artifacts and "
            "affected_artifacts",
            expected=sorted(expected_rebuild_set),
            actual=sorted(set(rebuild_artifacts)),
        ))

    # -- rebuild_order is exactly the same SET as rebuild_artifacts
    # (only the ORDER may differ -- see ordering_consistency below for
    # whether that order itself is dependency-safe). --
    rebuild_order_set_matches = set(rebuild_order) == set(rebuild_artifacts)
    rebuild_order_length_matches = len(rebuild_order) == len(rebuild_artifacts)
    if not rebuild_order_set_matches:
        issues.append(_error(
            "rebuild_order_set_mismatch",
            "incremental compilation validation: plan's own rebuild_order "
            "does not contain exactly the same artifacts as its own "
            "rebuild_artifacts",
            missing_from_order=sorted(set(rebuild_artifacts) - set(rebuild_order)),
            extra_in_order=sorted(set(rebuild_order) - set(rebuild_artifacts)),
        ))

    summary = {
        "dirty_count": len(dirty),
        "affected_count": len(affected),
        "clean_count": len(clean),
        "removed_count": len(removed),
        "rebuild_artifacts_count": len(rebuild_artifacts),
        "rebuild_order_count": len(rebuild_order),
        "duplicate_lists": duplicate_lists,
        "overlapping_classifications": overlaps,
        "rebuild_set_matches_dirty_union_affected": rebuild_set_matches_union,
        "rebuild_order_set_matches_rebuild_artifacts": rebuild_order_set_matches,
        "rebuild_order_length_matches_rebuild_artifacts": rebuild_order_length_matches,
        "no_duplicates": not duplicate_lists,
        "no_overlapping_classifications": not overlaps,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 2. Reference Consistency -- every artifact key / dependency edge
#    endpoint the plan names actually exists in Phase E2's own
#    DependencyGraph (or is one of the two synthetic keys)
# --------------------------------------------------------------------------

def _validate_reference_consistency(
    plan: Dict[str, Any],
    dependency_graph: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Cross-checks every artifact key this plan names (across all six
    of its own classification/order lists) against Phase E2's own
    DependencyGraph node_ids, plus the two synthetic keys neither
    Phase E2 nor any earlier phase's own validation pass ever checks
    (dependency_graph/ has no validation module of its own -- this is a
    genuinely new check, not a duplicate of one Phase E2 already makes,
    exactly like validation/system_integrity.py's own category-(b)
    checks, one layer up). Also confirms every DependencyGraph edge's
    own source_node_id/target_node_id resolves to a real node -- the
    "dependency references exist" / "artifact references exist" pair
    from the task's own VALIDATION list.

    Read-only over `dependency_graph`: only its own `nodes`/`edges`
    lists are read, never mutated, never rebuilt.

    When `dependency_graph` itself is unavailable, every check in this
    group is OMITTED (not failed) with a warning explaining why --
    mirrors validation/system_integrity.py's own Finding 3 precedent:
    a check that never actually ran must not be reported as passed OR
    failed."""
    issues: List[Dict[str, Any]] = []

    if dependency_graph is None:
        issues.append(_warning(
            "reference_consistency_not_verified",
            "incremental compilation validation: no DependencyGraph was "
            "supplied -- rebuild-target/dependency-reference existence was "
            "never verified for this plan",
        ))
        return issues, {
            "verified": False,
            "known_node_ids_count": 0,
            "unknown_artifact_keys": [],
            "dangling_edge_endpoints": [],
        }

    known_node_ids = {
        node.get("node_id")
        for node in (dependency_graph.get("nodes") or [])
        if node.get("node_id") is not None
    }
    known_keys = known_node_ids | _SYNTHETIC_ARTIFACT_KEYS

    all_named_artifacts: set = set()
    for list_name in (
        "dirty_artifacts", "affected_artifacts", "clean_artifacts",
        "removed_artifacts", "rebuild_artifacts", "rebuild_order",
    ):
        all_named_artifacts.update(plan.get(list_name) or [])

    unknown_artifact_keys = sorted(all_named_artifacts - known_keys)
    if unknown_artifact_keys:
        issues.append(_error(
            "unknown_artifact_reference",
            "incremental compilation validation: plan references "
            f"artifact key(s) with no matching DependencyGraph node (and not "
            f"one of the known synthetic keys): {unknown_artifact_keys!r}",
        ))

    dangling_edge_endpoints: List[Dict[str, Any]] = []
    for edge in dependency_graph.get("edges") or []:
        source = edge.get("source_node_id")
        target = edge.get("target_node_id")
        if source is not None and source not in known_node_ids:
            dangling_edge_endpoints.append({"edge_id": edge.get("edge_id"), "endpoint": "source_node_id", "node_id": source})
        if target is not None and target not in known_node_ids:
            dangling_edge_endpoints.append({"edge_id": edge.get("edge_id"), "endpoint": "target_node_id", "node_id": target})
    if dangling_edge_endpoints:
        issues.append(_error(
            "dangling_dependency_edge_endpoint",
            "incremental compilation validation: DependencyGraph contains "
            f"{len(dangling_edge_endpoints)} edge endpoint(s) with no "
            "matching node",
            endpoints=dangling_edge_endpoints,
        ))

    summary = {
        "verified": True,
        "known_node_ids_count": len(known_node_ids),
        "unknown_artifact_keys": unknown_artifact_keys,
        "dangling_edge_endpoints": dangling_edge_endpoints,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 3. Ordering Consistency -- rebuild_order respects every dependency
#    edge among the rebuild set, and carries no circular ordering
# --------------------------------------------------------------------------

def _validate_ordering_consistency(
    plan: Dict[str, Any],
    dependency_graph: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Two checks, neither a re-derivation of rebuild_order itself:

    (a) reads Phase E4's own already-computed
        `dependency_traversal_summary.cycle_detected` flag verbatim --
        the verdict incremental_compilation.traversal.
        compute_rebuild_order() already reached when this plan was
        first built (see that module's own CYCLES section) -- never
        re-derived here.

    (b) a genuinely NEW, whole-plan structural check neither Phase E2
        nor Phase E4 owns individually (mirrors validation/
        system_integrity.py's own category-(b) checks, one layer up):
        for every DependencyGraph edge whose both endpoints are in the
        rebuild set, does `target_node_id` actually appear at or before
        `source_node_id`'s own position in the plan's own recorded
        `rebuild_order`? This walks `rebuild_order` read-only (a single
        pass building an index map) -- it never reorders it, never
        rebuilds it, and never calls compute_rebuild_order() itself
        (that would be a determinism check, not an ordering-validity
        check -- see `_validate_determinism()` below for that one)."""
    issues: List[Dict[str, Any]] = []

    traversal_summary = plan.get("dependency_traversal_summary") or {}
    cycle_detected = bool(traversal_summary.get("cycle_detected"))
    cycle_node_ids = list(traversal_summary.get("cycle_node_ids") or [])
    if cycle_detected:
        issues.append(_error(
            "cycle_detected_in_rebuild_order",
            "incremental compilation validation: Phase E4's own "
            "dependency_traversal_summary reports a cycle among rebuild "
            f"artifact(s): {cycle_node_ids!r}",
        ))

    if dependency_graph is None:
        issues.append(_warning(
            "dependency_ordering_not_verified",
            "incremental compilation validation: no DependencyGraph was "
            "supplied -- rebuild_order's own dependency-safety was never "
            "independently verified for this plan",
        ))
        return issues, {
            "verified": False,
            "cycle_detected": cycle_detected,
            "cycle_node_ids": cycle_node_ids,
            "ordering_violations": [],
        }

    rebuild_order = list(plan.get("rebuild_order") or [])
    position = {node_id: index for index, node_id in enumerate(rebuild_order)}
    rebuild_set = set(rebuild_order)

    ordering_violations: List[Dict[str, Any]] = []
    for edge in dependency_graph.get("edges") or []:
        source = edge.get("source_node_id")
        target = edge.get("target_node_id")
        if source not in rebuild_set or target not in rebuild_set:
            continue
        # DIRECTION (incremental_compilation/traversal.py's own module
        # docstring, reused unchanged): source depends_on target, so
        # target must be ordered before source.
        if position.get(target, -1) > position.get(source, -1):
            ordering_violations.append({
                "edge_id": edge.get("edge_id"),
                "source_node_id": source,
                "target_node_id": target,
            })
    if ordering_violations:
        issues.append(_error(
            "dependency_ordering_violated",
            "incremental compilation validation: rebuild_order violates "
            f"{len(ordering_violations)} dependency edge(s) -- a dependency "
            "is ordered after the artifact that depends on it",
            violations=ordering_violations,
        ))

    summary = {
        "verified": True,
        "cycle_detected": cycle_detected,
        "cycle_node_ids": cycle_node_ids,
        "ordering_violations": ordering_violations,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 4. Reason Consistency -- every rebuild artifact has a rebuild reason,
#    every clean artifact has a reuse reason, and neither map carries a
#    stale entry for an artifact outside its own list
# --------------------------------------------------------------------------

def _validate_reason_consistency(
    plan: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Checks the plan's own rebuild_reasons/reuse_reasons maps against
    its own rebuild_artifacts/clean_artifacts lists -- a self-
    consistency comparison between two fields the SAME plan already
    carries, never a re-derivation of what either reason string should
    say (planner._rebuild_reason()'s own text is trusted verbatim)."""
    issues: List[Dict[str, Any]] = []

    rebuild_artifacts = set(plan.get("rebuild_artifacts") or [])
    clean_artifacts = set(plan.get("clean_artifacts") or [])
    rebuild_reasons = plan.get("rebuild_reasons") or {}
    reuse_reasons = plan.get("reuse_reasons") or {}

    missing_rebuild_reasons = sorted(rebuild_artifacts - set(rebuild_reasons.keys()))
    stale_rebuild_reasons = sorted(set(rebuild_reasons.keys()) - rebuild_artifacts)
    empty_rebuild_reasons = sorted(
        k for k, v in rebuild_reasons.items() if k in rebuild_artifacts and not (v or "").strip()
    )

    missing_reuse_reasons = sorted(clean_artifacts - set(reuse_reasons.keys()))
    stale_reuse_reasons = sorted(set(reuse_reasons.keys()) - clean_artifacts)
    empty_reuse_reasons = sorted(
        k for k, v in reuse_reasons.items() if k in clean_artifacts and not (v or "").strip()
    )

    if missing_rebuild_reasons:
        issues.append(_error(
            "missing_rebuild_reasons",
            "incremental compilation validation: no rebuild_reasons entry "
            f"for rebuild artifact(s): {missing_rebuild_reasons!r}",
        ))
    if stale_rebuild_reasons:
        issues.append(_warning(
            "stale_rebuild_reasons",
            "incremental compilation validation: rebuild_reasons carries "
            f"entrie(s) for artifact(s) not in rebuild_artifacts: "
            f"{stale_rebuild_reasons!r}",
        ))
    if empty_rebuild_reasons:
        issues.append(_error(
            "empty_rebuild_reasons",
            f"incremental compilation validation: empty rebuild_reasons "
            f"text for: {empty_rebuild_reasons!r}",
        ))
    if missing_reuse_reasons:
        issues.append(_error(
            "missing_reuse_reasons",
            "incremental compilation validation: no reuse_reasons entry "
            f"for clean artifact(s): {missing_reuse_reasons!r}",
        ))
    if stale_reuse_reasons:
        issues.append(_warning(
            "stale_reuse_reasons",
            "incremental compilation validation: reuse_reasons carries "
            f"entrie(s) for artifact(s) not in clean_artifacts: "
            f"{stale_reuse_reasons!r}",
        ))
    if empty_reuse_reasons:
        issues.append(_error(
            "empty_reuse_reasons",
            f"incremental compilation validation: empty reuse_reasons "
            f"text for: {empty_reuse_reasons!r}",
        ))

    summary = {
        "missing_rebuild_reasons": missing_rebuild_reasons,
        "stale_rebuild_reasons": stale_rebuild_reasons,
        "empty_rebuild_reasons": empty_rebuild_reasons,
        "missing_reuse_reasons": missing_reuse_reasons,
        "stale_reuse_reasons": stale_reuse_reasons,
        "empty_reuse_reasons": empty_reuse_reasons,
        "rebuild_reasons_complete": not (missing_rebuild_reasons or empty_rebuild_reasons),
        "reuse_reasons_complete": not (missing_reuse_reasons or empty_reuse_reasons),
    }
    return issues, summary


# --------------------------------------------------------------------------
# 5. Determinism -- given the SAME DependencyGraph + rebuild set this
#    plan already recorded, does Phase E4's own already-existing
#    compute_rebuild_order() reproduce a byte-identical rebuild_order?
# --------------------------------------------------------------------------

def _validate_determinism(
    plan: Dict[str, Any],
    dependency_graph: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Re-derives rebuild_order using Phase E4's own already-existing,
    frozen incremental_compilation.traversal.compute_rebuild_order() --
    the exact same pure function that produced this plan's own
    rebuild_order in the first place -- against the exact same
    DependencyGraph and the exact same rebuild set this plan already
    recorded, and confirms the result is byte-identical. Mirrors
    validation/determinism.py's own reproducibility-checking precedent,
    one phase up: this is not a second, independently-invented ordering
    algorithm, and it is not Phase E4's planner.plan_rebuild() rerun in
    full (dirty/affected/clean/removed classification is never touched
    here) -- it is Phase E4's own single existing ordering primitive,
    invoked a second time to confirm its own documented determinism
    guarantee (incremental_compilation/traversal.py's own DETERMINISM
    section) actually holds for this specific plan instance.

    OMITTED (not failed) when no DependencyGraph is available, for the
    same reason `_validate_reference_consistency()`/
    `_validate_ordering_consistency()` omit their own checks above."""
    if dependency_graph is None:
        return [_warning(
            "determinism_not_verified",
            "incremental compilation validation: no DependencyGraph was "
            "supplied -- rebuild_order's own determinism was never "
            "independently re-verified for this plan",
        )], {"verified": False, "reproduced_order_matches": False}

    rebuild_artifacts = list(plan.get("rebuild_artifacts") or [])
    recomputed = compute_rebuild_order(dependency_graph, set(rebuild_artifacts))

    recorded_order = list(plan.get("rebuild_order") or [])
    recorded_cycle_detected = bool((plan.get("dependency_traversal_summary") or {}).get("cycle_detected"))

    order_matches = recomputed["order"] == recorded_order
    cycle_flag_matches = recomputed["cycle_detected"] == recorded_cycle_detected

    issues: List[Dict[str, Any]] = []
    if not order_matches:
        issues.append(_error(
            "non_deterministic_rebuild_order",
            "incremental compilation validation: re-running "
            "incremental_compilation.traversal.compute_rebuild_order() "
            "against this plan's own DependencyGraph and rebuild set did "
            "not reproduce this plan's own recorded rebuild_order",
            recorded=recorded_order,
            recomputed=recomputed["order"],
        ))
    if not cycle_flag_matches:
        issues.append(_error(
            "non_deterministic_cycle_flag",
            "incremental compilation validation: re-running "
            "compute_rebuild_order() reported a different cycle_detected "
            "flag than this plan's own recorded "
            "dependency_traversal_summary.cycle_detected",
            recorded=recorded_cycle_detected,
            recomputed=recomputed["cycle_detected"],
        ))

    summary = {
        "verified": True,
        "reproduced_order_matches": order_matches,
        "reproduced_cycle_flag_matches": cycle_flag_matches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 6. Read-Only Behaviour -- confirms this module's own run mutated
#    neither the plan, the DependencyGraph, nor the ChangeDetectionReport
#    it was handed
# --------------------------------------------------------------------------

def _snapshot_for_read_only_check(value: Optional[Dict[str, Any]]) -> Optional[str]:
    """Canonical-JSON fingerprint of one argument, taken BEFORE any
    other check in this module runs -- reuses canonicalization.
    canonical_json(), the exact same shared primitive every fingerprint
    in this codebase already uses, rather than a second, hand-rolled
    equality strategy. `None` stays `None` (an absent argument has
    nothing to prove read-only)."""
    if value is None:
        return None
    return canonical_json(value)


def _validate_read_only_behaviour(
    *,
    plan_before: Optional[str],
    plan_after: Optional[Dict[str, Any]],
    dependency_graph_before: Optional[str],
    dependency_graph_after: Optional[Dict[str, Any]],
    change_detection_report_before: Optional[str],
    change_detection_report_after: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Re-fingerprints each of the three arguments AFTER every other
    check in this module has already run, and compares against the
    fingerprint taken before any check ran -- a mismatch means some
    check above mutated an input it was only supposed to read, a
    genuine regression against this module's own module-docstring
    guarantee, not a re-derivation of anything the plan itself
    describes."""
    issues: List[Dict[str, Any]] = []

    plan_matches = plan_before == _snapshot_for_read_only_check(plan_after)
    dependency_graph_matches = dependency_graph_before == _snapshot_for_read_only_check(dependency_graph_after)
    change_detection_report_matches = change_detection_report_before == _snapshot_for_read_only_check(change_detection_report_after)

    if not plan_matches:
        issues.append(_error(
            "plan_mutated",
            "incremental compilation validation: the IncrementalCompilationPlan "
            "was mutated during validation -- Phase E5.1 must be strictly "
            "read-only",
        ))
    if not dependency_graph_matches:
        issues.append(_error(
            "dependency_graph_mutated",
            "incremental compilation validation: the DependencyGraph was "
            "mutated during validation -- Phase E5.1 must be strictly "
            "read-only",
        ))
    if not change_detection_report_matches:
        issues.append(_error(
            "change_detection_report_mutated",
            "incremental compilation validation: the ChangeDetectionReport "
            "was mutated during validation -- Phase E5.1 must be strictly "
            "read-only",
        ))

    summary = {
        "plan_unmutated": plan_matches,
        "dependency_graph_unmutated": dependency_graph_matches,
        "change_detection_report_unmutated": change_detection_report_matches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Task 6/7: single pipeline.py integration point
# --------------------------------------------------------------------------

def validate_incremental_compilation_plan(
    *,
    namespace: str,
    # Phase E4 (Incremental Compilation), already in scope -- the one
    # artifact this module exists to validate.
    incremental_compilation_plan: Optional[Dict[str, Any]],
    # Phase E2 (Build Dependency Graph), already in scope -- reused
    # read-only for reference/ordering/determinism checks; never
    # rebuilt or modified.
    dependency_graph: Optional[Dict[str, Any]] = None,
    # Phase E3 (Change Detection), already in scope -- accepted purely
    # so `_validate_read_only_behaviour()` can also confirm THIS
    # argument was never mutated; no check above reads a classification
    # field off it directly (every classification this module checks
    # is read from `incremental_compilation_plan` itself, which already
    # carries Phase E3's own verdict, per Phase E4's own REUSE, DON'T
    # RECOMPUTE rule).
    change_detection_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase E5.1's single pipeline.py integration point (mirrors
    validation.system_integrity.validate_system_integrity()'s own
    shape, one layer over): classify presence -> validate -> render one
    overall_status verdict, in that order, and nothing else.

    Read-only over every argument (see module docstring and
    `_validate_read_only_behaviour()`); performs no rebuild, no
    replanning, and no mutation of the IncrementalCompilationPlan, the
    DependencyGraph, or the ChangeDetectionReport it is handed.

    Returns a plain dict (report.to_dict()), matching every earlier
    phase's own "plain, storable dict" convention, and so it can be
    handed directly to
    incremental_compilation_validation.state.set_current_incremental_compilation_validation_report()."""
    plan_before = _snapshot_for_read_only_check(incremental_compilation_plan)
    dependency_graph_before = _snapshot_for_read_only_check(dependency_graph)
    change_detection_report_before = _snapshot_for_read_only_check(change_detection_report)

    report = IncrementalCompilationValidationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        namespace=namespace,
    )

    passed: List[str] = []
    failed: List[str] = []
    all_issues: List[Dict[str, Any]] = []

    plan, presence_issues = _extract_plan(incremental_compilation_plan)
    all_issues.extend(presence_issues)
    report.plan_available = plan is not None
    _record(passed, failed, "plan_exists", report.plan_available)

    if plan is not None:
        classification_issues, classification_consistency = _validate_classification_consistency(plan)
        all_issues.extend(classification_issues)
        report.classification_consistency = classification_consistency
        _record(passed, failed, "no_duplicate_artifact_entries", classification_consistency["no_duplicates"])
        _record(passed, failed, "no_overlapping_classifications", classification_consistency["no_overlapping_classifications"])
        _record(passed, failed, "rebuild_artifacts_matches_dirty_union_affected", classification_consistency["rebuild_set_matches_dirty_union_affected"])
        _record(passed, failed, "rebuild_order_matches_rebuild_artifacts", (
            classification_consistency["rebuild_order_set_matches_rebuild_artifacts"]
            and classification_consistency["rebuild_order_length_matches_rebuild_artifacts"]
        ))

        reference_issues, reference_consistency = _validate_reference_consistency(plan, dependency_graph)
        all_issues.extend(reference_issues)
        report.reference_consistency = reference_consistency
        if reference_consistency["verified"]:
            _record(passed, failed, "rebuild_targets_exist", not reference_consistency["unknown_artifact_keys"])
            _record(passed, failed, "dependency_references_exist", not reference_consistency["dangling_edge_endpoints"])
        # else: no DependencyGraph supplied -- omitted from both
        # checks_passed and checks_failed (the
        # reference_consistency_not_verified warning above already
        # explains why), never defaulted to "passed".

        ordering_issues, ordering_consistency = _validate_ordering_consistency(plan, dependency_graph)
        all_issues.extend(ordering_issues)
        report.ordering_consistency = ordering_consistency
        _record(passed, failed, "no_circular_rebuild_ordering", not ordering_consistency["cycle_detected"])
        if ordering_consistency["verified"]:
            _record(passed, failed, "dependency_ordering_is_valid", not ordering_consistency["ordering_violations"])
        # else: no DependencyGraph supplied -- omitted, same rationale
        # as rebuild_targets_exist/dependency_references_exist above.

        reason_issues, reason_consistency = _validate_reason_consistency(plan)
        all_issues.extend(reason_issues)
        report.reason_consistency = reason_consistency
        _record(passed, failed, "rebuild_reasons_exist", reason_consistency["rebuild_reasons_complete"])
        _record(passed, failed, "reuse_reasons_exist", reason_consistency["reuse_reasons_complete"])

        determinism_issues, determinism_consistency = _validate_determinism(plan, dependency_graph)
        all_issues.extend(determinism_issues)
        report.determinism_consistency = determinism_consistency
        if determinism_consistency["verified"]:
            _record(passed, failed, "deterministic_plan", (
                determinism_consistency["reproduced_order_matches"]
                and determinism_consistency["reproduced_cycle_flag_matches"]
            ))
        # else: no DependencyGraph supplied -- omitted, same rationale
        # as above.

    read_only_issues, read_only_consistency = _validate_read_only_behaviour(
        plan_before=plan_before,
        plan_after=incremental_compilation_plan,
        dependency_graph_before=dependency_graph_before,
        dependency_graph_after=dependency_graph,
        change_detection_report_before=change_detection_report_before,
        change_detection_report_after=change_detection_report,
    )
    all_issues.extend(read_only_issues)
    report.read_only_consistency = read_only_consistency
    _record(passed, failed, "read_only_behaviour", (
        read_only_consistency["plan_unmutated"]
        and read_only_consistency["dependency_graph_unmutated"]
        and read_only_consistency["change_detection_report_unmutated"]
    ))

    report.errors = [i for i in all_issues if i["severity"] == "error"]
    report.warnings = [i for i in all_issues if i["severity"] == "warning"]
    report.checks_passed = passed
    report.checks_failed = failed
    report.overall_status = "fail" if (report.errors or failed) else "pass"

    total_checks = len(passed) + len(failed)
    report.summary = (
        f"Incremental compilation validation {report.overall_status}: "
        f"{total_checks} check{'s' if total_checks != 1 else ''} run "
        f"({len(passed)} passed, {len(failed)} failed); "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s) "
        "against the Phase E4 IncrementalCompilationPlan."
    )

    return report.to_dict()