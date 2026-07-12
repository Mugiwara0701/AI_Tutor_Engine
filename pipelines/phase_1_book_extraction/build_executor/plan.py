"""
build_executor/plan.py — Phase F3: deterministic Execution Plan
generation.

SCOPE: `ExecutionPlan` describes, for one book (generate_execution_plan()
-- called once per book by pipeline.process_all_pdfs(), immediately
after that book's chapters have each been decided/executed by
executor.execute_chapter()) or for one whole CompilerRuntime run
(aggregate_execution_plan() -- called once per run by
executor.aggregate_run_execution_report(), from every book's own plan),
exactly which chapter artifacts were reused, which were rebuilt, in
what deterministic order they were considered, and why.

REUSE, DON'T RECOMPUTE (same rule every other phase's own build/
manifest module already states one layer down): every field below is
assembled directly from the `chapter_decisions` executor.py already
made (each one the result of a single, already-made reuse/rebuild
decision -- see executor.execute_chapter()) -- this module performs no
new reuse/rebuild decision of its own, no new fingerprinting, and no
new dependency-graph traversal. Where a chapter's own
IncrementalCompilationPlan is available (build.py's own
incremental_plan_reference, when this is being assembled at the
Phase F2 Build level), this module surfaces that plan's own
already-computed `rebuild_order` verbatim as `dependency_rebuild_order`
-- it never recomputes incremental_compilation.traversal.
compute_rebuild_order() itself.

DETERMINISM: `execution_order` is exactly the order `chapter_decisions`
were made in -- pipeline.process_all_pdfs()'s own chapter loop, which
iterates `sorted(glob.glob(...))` and resolves each chapter's real
chapter number from its filename (see that function's own docstring),
never dict/set iteration order or any other non-reproducible ordering.
This module never re-sorts or re-orders that sequence itself; it is
already deterministic by construction before it reaches this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .exceptions import ExecutionPlanError

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase. Bump only if the PLAN SHAPE this
# module produces itself changes in a way a consumer should be able to
# detect.
EXECUTION_PLAN_VERSION = "F3.1"


@dataclass
class ExecutionPlan:
    """The full Phase F3 Execution Plan for one book or one whole run.

    FIELD NOTES:
    - `namespace`: the book title (one-book plan) or "<run>" (the
      run-level aggregate -- see aggregate_execution_plan() below).
    - `execution_order`: every chapter this plan considered, in the
      exact deterministic order pipeline.process_all_pdfs() iterated
      them -- never re-sorted here (module docstring's DETERMINISM
      section).
    - `reused_artifacts` / `rebuilt_artifacts`: `execution_order`,
      partitioned by executor.execute_chapter()'s own already-made
      decision -- never a second, independently computed
      classification.
    - `execution_reasons`: `{chapter_key: reason string}` for every
      entry in `execution_order` -- executor.execute_chapter()'s own
      explanation for why that chapter was reused or rebuilt.
    - `dependency_rebuild_order`: Phase E4's own `rebuild_order` for
      the last chapter processed this run, when available (see module
      docstring) -- purely informational context alongside this
      plan's own chapter-level `execution_order`; never a second
      source of truth for this plan's own ordering, and never
      recomputed.
    - `summary`: small, denormalized counts of the lists above, never
      a second source of truth (every count is `len()` of one of this
      same plan's own fields).
    - `warnings` / `errors`: plain strings, mirroring every earlier
      phase's own report convention.
    """

    generated_at: str
    execution_plan_version: str
    namespace: str
    execution_order: List[str] = field(default_factory=list)
    reused_artifacts: List[str] = field(default_factory=list)
    rebuilt_artifacts: List[str] = field(default_factory=list)
    execution_reasons: Dict[str, str] = field(default_factory=dict)
    dependency_rebuild_order: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_summary(
    *, reused_artifacts: List[str], rebuilt_artifacts: List[str]
) -> Dict[str, Any]:
    """Small, denormalized summary block -- every count is a direct
    `len()` of one of ExecutionPlan's own list fields, never
    independently computed or re-derived. Mirrors incremental_
    compilation.plan.build_summary()'s own precedent exactly, one
    phase up."""
    return {
        "reused_count": len(reused_artifacts),
        "rebuilt_count": len(rebuilt_artifacts),
        "total_considered": len(reused_artifacts) + len(rebuilt_artifacts),
        "requires_execution": bool(rebuilt_artifacts),
        "is_full_reuse": bool(reused_artifacts) and not rebuilt_artifacts,
    }


def generate_execution_plan(
    chapter_decisions: List[Dict[str, Any]],
    *,
    namespace: str,
    dependency_rebuild_order: Optional[List[str]] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Assembles one book's (or, via aggregate_execution_plan(), one
    run's) ExecutionPlan directly from `chapter_decisions` -- the exact
    list executor.execute_chapter() already returned, one dict per
    chapter, each already carrying its own `chapter_key`/`decision`/
    `reason` (see executor.py). Never re-decides reuse/rebuild itself.

    Raises ExecutionPlanError if any entry in `chapter_decisions` is
    missing `chapter_key` or `decision`, or carries a `decision` value
    other than "reuse"/"rebuild" (a caller/programming error --
    executor.execute_chapter() always returns one of exactly those
    two)."""
    execution_order: List[str] = []
    reused_artifacts: List[str] = []
    rebuilt_artifacts: List[str] = []
    execution_reasons: Dict[str, str] = {}
    errors: List[str] = []

    for entry in chapter_decisions:
        chapter_key = entry.get("chapter_key")
        decision = entry.get("decision")
        if not chapter_key or decision not in ("reuse", "rebuild"):
            raise ExecutionPlanError(
                "generate_execution_plan(): every chapter_decisions entry "
                "must carry a 'chapter_key' and a 'decision' of 'reuse' or "
                f"'rebuild' (executor.execute_chapter()'s own return shape), "
                f"got {entry!r}."
            )
        execution_order.append(chapter_key)
        execution_reasons[chapter_key] = entry.get("reason", "")
        if decision == "reuse":
            reused_artifacts.append(chapter_key)
        else:
            rebuilt_artifacts.append(chapter_key)
        if entry.get("error"):
            errors.append(str(entry["error"]))

    plan = ExecutionPlan(
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        execution_plan_version=EXECUTION_PLAN_VERSION,
        namespace=namespace,
        execution_order=execution_order,
        reused_artifacts=reused_artifacts,
        rebuilt_artifacts=rebuilt_artifacts,
        execution_reasons=execution_reasons,
        dependency_rebuild_order=list(dependency_rebuild_order or []),
        summary=build_summary(
            reused_artifacts=reused_artifacts, rebuilt_artifacts=rebuilt_artifacts
        ),
        warnings=[],
        errors=errors,
    )
    return plan.to_dict()


def aggregate_execution_plan(
    book_plans: List[Dict[str, Any]],
    *,
    namespace: str = "<run>",
    dependency_rebuild_order: Optional[List[str]] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Combines every book's own ExecutionPlan (this run's own
    `all_stats[*]["execution_plan"]`, one per book -- see executor.
    aggregate_run_execution_report()) into one run-level ExecutionPlan.
    Concatenates each book plan's own already-computed
    execution_order/reused_artifacts/rebuilt_artifacts/
    execution_reasons/errors verbatim, in book-processing order (itself
    deterministic -- book_orchestrator.discover_books() sorts book
    folder names) -- never re-derives or re-orders any individual
    book's own decisions."""
    execution_order: List[str] = []
    reused_artifacts: List[str] = []
    rebuilt_artifacts: List[str] = []
    execution_reasons: Dict[str, str] = {}
    errors: List[str] = []
    # Phase F3 audit refinement: preserve each book plan's own
    # `dependency_rebuild_order` (Phase E4's already-computed
    # `rebuild_order`, surfaced verbatim by generate_execution_plan()
    # above -- see that function's own docstring) into the run-level
    # plan, in book-processing order -- same concatenation convention
    # every other list field on this plan already uses above. Never
    # re-derived, re-ordered, or recomputed: purely what each book's own
    # plan already carried.
    aggregated_dependency_rebuild_order: List[str] = []

    for book_plan in book_plans:
        execution_order.extend(book_plan.get("execution_order") or [])
        reused_artifacts.extend(book_plan.get("reused_artifacts") or [])
        rebuilt_artifacts.extend(book_plan.get("rebuilt_artifacts") or [])
        execution_reasons.update(book_plan.get("execution_reasons") or {})
        errors.extend(book_plan.get("errors") or [])
        aggregated_dependency_rebuild_order.extend(
            book_plan.get("dependency_rebuild_order") or []
        )

    # An explicit `dependency_rebuild_order` argument (if the caller
    # passed one) takes precedence over what was aggregated from
    # `book_plans` -- mirrors generate_execution_plan()'s own "explicit
    # argument wins" contract for this same field, one function up.
    plan = ExecutionPlan(
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        execution_plan_version=EXECUTION_PLAN_VERSION,
        namespace=namespace,
        execution_order=execution_order,
        reused_artifacts=reused_artifacts,
        rebuilt_artifacts=rebuilt_artifacts,
        execution_reasons=execution_reasons,
        dependency_rebuild_order=(
            list(dependency_rebuild_order)
            if dependency_rebuild_order
            else aggregated_dependency_rebuild_order
        ),
        summary=build_summary(
            reused_artifacts=reused_artifacts, rebuilt_artifacts=rebuilt_artifacts
        ),
        warnings=[],
        errors=errors,
    )
    return plan.to_dict()