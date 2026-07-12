"""
build_executor/executor.py — Phase F3: the Build Executor.

TWO INTEGRATION POINTS, TWO GRANULARITIES:

  1. `execute_chapter()` -- called once per chapter PDF, from INSIDE
     pipeline.process_all_pdfs()'s own chapter loop, BEFORE that
     chapter's extraction would otherwise run. This is Phase F3's own
     Reuse Decision Engine, and the actual pre-execution gate: a
     "reuse" decision means `process_chapter_fn` (pipeline.
     process_chapter, injected by the caller -- see DEPENDENCY
     INJECTION below) is never even called this run, so no OCR/VLM/
     compiler/knowledge-graph/... work happens for that chapter at
     all. A "rebuild" decision calls `process_chapter_fn` exactly as
     pipeline.process_all_pdfs() always has.

  2. `aggregate_run_execution_report()` -- called once per
     CompilerRuntime run/resume, from runtime/runtime.py, AFTER Phase
     F2's own Build has already been recorded (same integration point
     F2 itself uses, one step later) -- aggregates every book's own
     ExecutionPlan (each book's stats dict, additively, carries its
     own `"execution_plan"` -- see pipeline.process_all_pdfs()'s own
     integration of `execute_chapter()`) into one run-level
     ExecutionPlan + ExecutionReport and hands both to
     build_executor.state.

DEPENDENCY INJECTION, NOT A CIRCULAR IMPORT: `execute_chapter()` never
imports pipeline.py itself -- pipeline.process_all_pdfs() passes its
own `process_chapter` function in as `process_chapter_fn`. This keeps
build_executor a leaf package (it only imports modules.pdf_parser/
modules.json_writer, exactly the same "phase 0" infra pipeline.py
itself already imports), with no import-order dependency on pipeline.py
at build_executor's own module-load time -- mirroring this codebase's
existing local-import convention for cross-package calls (see e.g.
book_orchestrator.py's own local `import pipeline`).

REUSE DECISION -- WHAT SIGNAL THIS ACTUALLY USES (see this package's
own __init__.py "WHAT REUSE MEANS HERE, HONESTLY" section for the full
explanation): exactly the same `modules.json_writer.
is_already_extracted()` existence check (plus `force`) Phase A already
used internally for this same purpose, before this refinement, inside
`process_chapter()`'s own early-return. Phase F3 does not add a new,
finer-grained (e.g. content-fingerprint-based) reuse signal of its own
-- that is explicitly Phase F4's Cache to own, not this package's. What
changes here is WHEN and WHERE that decision is made and acted on (see
module docstring's point 1 above), not WHAT decides it.

NEVER RAISES AT THE COMPILERRUNTIME INTEGRATION POINT:
`aggregate_run_execution_report()` itself may raise (e.g.
ExecutionPlanError/ExecutionReportError for malformed input) --
runtime/runtime.py's own call site wraps it in the exact same
try/except-log-and-swallow contract artifact_manager's own
`_record_build()` already uses, so a failure in Phase F3's own
bookkeeping can never turn a successful (or already-recorded) run into
a second, different failure for run()'s caller. `execute_chapter()`
itself does NOT swallow exceptions raised by `process_chapter_fn` --
those propagate exactly as they always have (pipeline.
process_all_pdfs()'s own per-chapter try/except, unchanged, still
catches them one layer up), since a chapter that genuinely fails to
extract must still count as a chapter failure, not be silently treated
as "reused".
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from modules import json_writer, pdf_parser
from modules.pdf_parser import slugify

from .plan import aggregate_execution_plan, generate_execution_plan
from .report import generate_execution_report


def execute_chapter(
    *,
    pdf_path: str,
    book_ctx: Any,
    chapter_order_fallback: int,
    use_vlm: bool,
    page_batch_size: int,
    force: bool,
    output_root: Optional[str],
    process_chapter_fn: Callable[..., Optional[str]],
) -> Dict[str, Any]:
    """Phase F3's own pre-execution reuse gate for exactly one chapter
    PDF. Called by pipeline.process_all_pdfs() in place of calling
    `process_chapter_fn` (pipeline.process_chapter) directly -- see
    module docstring's integration point 1.

    Parses the chapter's own structure once (pdf_parser.
    parse_chapter_pdf() -- the same cheap, deterministic, no-OCR/no-VLM
    parse `process_chapter_fn` would perform at its own top regardless;
    calling it here first, before the reuse decision, does mean a
    "rebuild" decision causes it to be parsed a second time inside
    `process_chapter_fn` -- an accepted, documented inefficiency, not a
    correctness issue: parse_chapter_pdf() is a pure, side-effect-free
    reader, never OCR/VLM/compiler work) to obtain the klass/subject/
    chapter_number/chapter_title `is_already_extracted()` needs -- the
    exact same information `process_chapter_fn` already derives at its
    own top before making this same check internally.

    Returns:
        {
            "chapter_title": str,
            "chapter_key": str,      # this chapter's own deterministic
                                      # output path (json_writer.
                                      # chapter_output_path()) -- stable
                                      # whether reused or rebuilt
            "output_path": Optional[str],  # None for "reuse" (mirrors
                                      # process_chapter_fn's own "already
                                      # extracted" return value exactly)
                                      # or this chapter's real written
                                      # path for "rebuild"
            "decision": "reuse" | "rebuild",
            "reason": str,
        }

    Does not itself catch exceptions `process_chapter_fn` raises (see
    module docstring's NEVER RAISES section) -- those propagate to
    pipeline.process_all_pdfs()'s own existing per-chapter try/except,
    unchanged.
    """
    structure = pdf_parser.parse_chapter_pdf(pdf_path, book_ctx, chapter_order_fallback)
    # Must match pipeline.process_chapter()'s own book_slug source exactly
    # (book_ctx.slug_source, i.e. the discovered folder name when one
    # exists) -- this is the SAME reuse/output-path key process_chapter_fn
    # will compute, and any divergence here silently breaks the reuse gate
    # (is_already_extracted() would check the wrong directory).
    book_slug = slugify(pdf_parser.book_slug_source(book_ctx))
    chapter_key = json_writer.chapter_output_path(
        structure.klass, structure.subject, book_slug,
        structure.chapter_number, structure.chapter_title,
        output_root=output_root,
    )

    already_extracted = json_writer.is_already_extracted(
        structure.klass, structure.subject, book_slug,
        structure.chapter_number, structure.chapter_title,
        output_root=output_root,
    )

    if not force and already_extracted:
        return {
            "chapter_title": structure.chapter_title,
            "chapter_key": chapter_key,
            "output_path": None,
            "decision": "reuse",
            "reason": (
                "chapter JSON already exists at this path and force=False "
                "-- Phase F3 reused it without calling process_chapter() "
                "(no OCR/VLM/compiler/knowledge-graph work performed this "
                "run for this chapter)."
            ),
        }

    out_path = process_chapter_fn(
        pdf_path, book_ctx, chapter_order_fallback=chapter_order_fallback,
        use_vlm=use_vlm, page_batch_size=page_batch_size, force=force,
        output_root=output_root,
    )
    return {
        "chapter_title": structure.chapter_title,
        "chapter_key": chapter_key,
        "output_path": out_path,
        "decision": "rebuild",
        "reason": (
            "no existing chapter JSON found for this path (or force=True) "
            "-- full extraction was required and process_chapter() was "
            "called."
        ),
    }


def aggregate_run_execution_report(
    all_stats: List[Dict[str, Any]],
    *,
    execution_duration_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Called once per CompilerRuntime run/resume (runtime/runtime.py),
    after Phase F2's own Build has been recorded -- aggregates every
    book's own ExecutionPlan (`all_stats[*]["execution_plan"]`, additive
    key set by pipeline.process_all_pdfs() -- absent/empty for a book
    whose stats dict predates this integration, e.g. a book that failed
    before process_all_pdfs() could attach it, or a test double built
    against the pre-F3 stats shape) into one run-level ExecutionPlan,
    then generates this run's own ExecutionReport from it.

    Never itself re-decides reuse/rebuild, never re-orders anything --
    purely combines what execute_chapter() already decided, book by
    book, in book-processing order (see plan.aggregate_execution_plan()).

    Returns:
        {"execution_plan": <dict>, "execution_report": <dict>}

    May raise ExecutionPlanError/ExecutionReportError for malformed
    input -- see module docstring's NEVER RAISES section for why the
    one call site (runtime/runtime.py) always wraps this in a
    try/except."""
    book_plans = [
        book_stats["execution_plan"]
        for book_stats in all_stats
        if book_stats.get("execution_plan")
    ]
    execution_plan = aggregate_execution_plan(book_plans, namespace="<run>")
    execution_report = generate_execution_report(
        execution_plan, execution_duration_seconds=execution_duration_seconds
    )
    return {"execution_plan": execution_plan, "execution_report": execution_report}