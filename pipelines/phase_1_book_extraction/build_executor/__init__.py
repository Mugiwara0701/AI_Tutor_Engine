"""
build_executor/ — Phase F3: Build Executor.

SCOPE (F0/this task's own F3 responsibility list, nothing more): this
package owns the Build Executor, the Execution Planner, the Build
Scheduler, the Reuse Decision Engine, execution ordering, the Execution
Report, and the run-scoped "current execution report" state -- i.e.
everything about *deciding what this run actually needs to (re)build,
in what order, and reporting what happened*, once Phases A-E5.2 have
already computed the artifacts (Compiler IR, Knowledge Graph,
Validation, Build Metadata, Dependency Graph, Change Detection,
Incremental Compilation, Incremental Compilation Validation,
Incremental Compilation Finalization) this package's decisions are
*based on*.

Phase F3 NEVER creates Compiler IR, a Knowledge Graph, Validation, Build
Metadata, a Dependency Graph, Change Detection, an Incremental Plan,
Incremental Validation, or Incremental Finalization -- those remain
exactly where they already lived (Phases A-E5.2, all frozen, untouched
by this package). It NEVER re-implements
incremental_compilation.traversal.compute_rebuild_order()'s own
dependency-aware topological ordering -- see executor.py's own module
docstring for exactly which upstream artifact this package reuses for
what.

WHAT "REUSE" MEANS HERE, HONESTLY (read this before assuming F3 does
more than it does): Phases A-E1's own chapter-scoped artifacts
(Compiler IR, Knowledge Graph, ...) are only ever compared against a
*previous build's* fingerprints once they have already been computed
this run -- Phase E3 Change Detection is, by existing/frozen design, an
artifact-fingerprint comparison, not a pre-extraction file check (see
change_detection/engine.py). There is, today, no cheaper signal this
package could consult to decide "should OCR/VLM extraction even run for
this chapter" other than the one Phase A already used internally for
exactly that purpose: `modules.json_writer.is_already_extracted()`
(chapter-JSON-already-exists) plus `force`. Phase F3 does not invent a
second, fingerprint-based version of that decision -- a persisted,
cross-run artifact-fingerprint cache is explicitly Phase F4's job (F0's
"F3 DOES NOT OWN: Cache, Cache invalidation (F4)"), not this package's.
What Phase F3 *does* add on top of that one existing signal:

  * moves the decision to BEFORE the chapter's own extraction call
    (see pipeline.process_all_pdfs()'s integration point), so a
    "reuse" decision genuinely skips calling `pipeline.process_chapter()`
    at all this run, rather than merely being noticed by it after the
    fact,
  * makes the decision explicit, explainable, and centrally reported
    (one ExecutionPlan/ExecutionReport per run) rather than a private
    early-return buried in `process_chapter()`,
  * layers Phase E4's own already-computed, already-deterministic
    `rebuild_order` (incremental_compilation.traversal.
    compute_rebuild_order()) into this package's own execution-order
    reporting wherever a chapter's IncrementalCompilationPlan is
    available, without ever recomputing that ordering itself.

  * `exceptions.py` -- this package's own exception hierarchy.
  * `plan.py` -- the deterministic ExecutionPlan dataclass + its
    generator.
  * `report.py` -- the ExecutionReport dataclass + its generator.
  * `executor.py` -- `execute_chapter()` (the actual pre-execution
    reuse gate, called once per chapter PDF by
    pipeline.process_all_pdfs()) and `aggregate_run_execution_report()`
    (the run-scoped aggregation CompilerRuntime._execute() calls once
    per run, after Phase F2's own Build has been recorded).
  * `state.py` -- set_current_execution_report()/
    get_current_execution_report()/has_current_execution_report()/
    reset_current_execution_report(), the exact set_current_*()/
    get_current_*()/has_current_*()/reset_*_state() idiom every other
    phase's own state.py in this codebase already uses -- run-scoped,
    like runtime/state.py, not chapter-scoped.

WHAT THIS IS NOT (see this task's own "DO NOT IMPLEMENT" list): not
Input Manifest, not Build Manifest, not persistence (F2), not a cache
or cache invalidation (F4), not Compiler Build packaging (F5), not a
compiler phase, not extraction, not Knowledge Graph, not Dependency
Graph, not Change Detection, not Incremental Planning. This package
never computes a single one of those artifacts; it only decides,
schedules, and reports on top of what they already produced.
"""