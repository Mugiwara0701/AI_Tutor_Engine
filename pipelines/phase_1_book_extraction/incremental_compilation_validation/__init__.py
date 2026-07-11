"""
incremental_compilation_validation/ — Phase E5.1: Incremental
Compilation Validation.

SCOPE: this package answers exactly one question no earlier phase
answers -- given Phase E4's own IncrementalCompilationPlan (already
computed and frozen), IS THAT PLAN ITSELF VALID: does it exist, is it
internally self-consistent (no duplicate or overlapping classification,
rebuild_artifacts really is dirty union affected, rebuild_order really
is the same set), does every artifact key and dependency edge endpoint
it names actually resolve against Phase E2's own DependencyGraph, does
its own rebuild_order actually respect every dependency edge among the
rebuild set with no circular ordering, does every rebuild artifact
carry a rebuild reason and every clean artifact a reuse reason, is the
rebuild order it recorded reproducible, and did validating all of the
above leave the plan (and the Phase E2/E3 artifacts it was built from)
completely unmutated. It is NOT Incremental Compilation (E4, already
answers "what must rebuild, in what order, and why" -- reused here,
never re-planned), NOT Incremental Compilation Finalization (E5.2,
which will generate readiness / final status / a build summary from
this report -- out of this package's own scope), and NOT a compilation
executor, cache, or persistence layer of any kind: this package
produces a VALIDATION REPORT and never executes, rebuilds, reschedules,
or caches a single rebuild step itself.

  * `exceptions.py` -- this package's own exception hierarchy, mirrors
    incremental_compilation/exceptions.py's shape and role one package
    over.
  * `report.py` -- `IncrementalCompilationValidationReport`: the full
    Phase E5.1 artifact, purely a data holder (matches every earlier
    phase's own "dataclass + to_dict(), all computation happens in the
    owning validator.py/engine.py" convention). Unlike
    incremental_compilation.plan.IncrementalCompilationPlan (read-only
    reporting, no verdict), this report DOES carry one verdict
    (`overall_status`), mirroring validation.system_integrity.
    SystemIntegrityReport's own precedent one layer up.
  * `validator.py` -- `validate_incremental_compilation_plan()`: the
    Incremental Compilation Validation Engine. Six check groups
    (classification consistency, reference consistency, ordering
    consistency, reason consistency, determinism, read-only behaviour),
    each reading already-computed state and never recomputing a Phase
    E2/E3/E4 classification, node, edge, or ordering from scratch (the
    one narrow exception -- a determinism re-check that calls Phase
    E4's own already-existing compute_rebuild_order() a second time --
    is documented in that function's own docstring).
  * `engine.py` -- `validate_incremental_compilation()`, the one
    read-only orchestration pass and Phase E5.1's single pipeline.py
    integration point (mirrors incremental_compilation.engine.
    plan_incremental_compilation()'s own "one orchestration call"
    shape, one phase up).
  * `state.py` -- the module-level "current chapter's
    IncrementalCompilationValidationReport (+ its own overall_status)"
    slot pair, following the exact idiom compiler/state.py,
    knowledge_graph/state.py, validation/state.py,
    validation/release_state.py, build_metadata/state.py,
    dependency_graph/state.py, change_detection/state.py, and
    incremental_compilation/state.py already establish.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Phase E5.2, not Phase F, not a compilation executor, not a cache, not a
persistence layer, not parallel execution, and not distributed
execution -- this package validates a plan that already exists, and
nothing else; no artifact is regenerated, no registry is touched, and
no Chapter JSON field is ever produced or modified here.

REUSE, DON'T RECOMPUTE: Phase E5.1 never reruns
change_detection.compare.compare_snapshots(),
change_detection.traversal.compute_affected_artifacts(), or
incremental_compilation.planner.plan_rebuild() -- every dirty/clean/
affected/removed/rebuild classification is read directly off Phase
E4's own IncrementalCompilationPlan, unchanged. Phase E5.1 never
rebuilds or mutates Phase E2's own DependencyGraph or Phase E3's own
ChangeDetectionReport -- both are read-only inputs, and this package's
own read-only-behaviour check confirms as much for every run.
"""