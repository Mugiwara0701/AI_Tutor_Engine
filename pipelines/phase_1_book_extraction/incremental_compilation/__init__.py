"""
incremental_compilation/ — Phase E4: Incremental Compilation.

SCOPE: this package answers exactly one question Phase E3 does not:
given Phase E3's own ChangeDetectionReport ("what changed?") and Phase
E2's own DependencyGraph ("what depends on what?"), which artifacts
must be rebuilt, in what order, and why -- and which artifacts can be
reused as-is, and why. It is NOT Change Detection (E3, already answers
"what changed" -- reused here, never rerun), NOT the Build Dependency
Graph (E2, already answers "what depends on what" -- reused here,
never rebuilt or modified), NOT Validation & Finalization (E5, which
will later verify this plan's own correctness), and NOT a compilation
executor, cache, or persistence layer of any kind: this package
produces a PLAN, and never executes, schedules, parallelizes, or
caches a single rebuild step itself.

  * `exceptions.py` -- this package's own exception hierarchy, mirrors
    change_detection/exceptions.py's shape and role one package over.
  * `traversal.py` -- `compute_rebuild_order()`: a deterministic
    topological ordering of the artifacts that require rebuilding,
    derived by walking Phase E2's own DependencyGraph edges (read-only,
    never rebuilt, never modified -- exactly change_detection/
    traversal.py's own "reuse the graph, only traverse it" rule, one
    phase up). This is Phase E4's own, new graph question -- "in what
    ORDER must these specific artifacts rebuild" -- which neither E2
    nor E3 ever computes (E3's own traversal.py answers a different
    question, "which artifacts are affected", as an unordered set; E4
    reuses that set rather than re-deriving it -- see planner.py).
  * `planner.py` -- `plan_rebuild()`: the Minimal Rebuild Planner.
    Classifies every artifact Phase E3's report already named into
    dirty / clean / affected / removed, reusing E3's own classification
    verbatim (never re-running compare.py's or E3's traversal.py's own
    logic a second time), unions dirty+affected into the rebuild set,
    calls traversal.py for that set's rebuild order, and attaches a
    human-readable reason to every dirty, affected, and clean artifact.
  * `plan.py` -- `IncrementalCompilationPlan`: the full Phase E4
    artifact, purely a data holder (matches every earlier phase's own
    "dataclass + to_dict(), all computation happens in the owning
    build.py/engine.py/planner.py" convention). Read-only reporting,
    exactly like change_detection.report.ChangeDetectionReport: this
    plan describes what must be rebuilt, it never rebuilds anything
    itself.
  * `engine.py` -- `plan_incremental_compilation()`, the one read-only
    orchestration pass and Phase E4's single pipeline.py integration
    point (mirrors change_detection.engine.detect_changes()'s own "one
    orchestration call" shape, one phase up): classify -> order ->
    reason -> report, in that order, and nothing else.
  * `state.py` -- the module-level "current chapter's
    IncrementalCompilationPlan" slot, following the exact idiom
    compiler/state.py, knowledge_graph/state.py, validation/state.py,
    build_metadata/state.py, dependency_graph/state.py, and
    change_detection/state.py already establish.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Phase E5, not a compilation executor, not a cache, not a persistence
layer, not distributed execution, not parallel scheduling, and not an
"actual rebuild" of anything -- this package computes a rebuild PLAN
and nothing else; no artifact is regenerated, no registry is touched,
and no Chapter JSON field is ever produced or modified here.

REUSE, DON'T RECOMPUTE: Phase E4 never reruns change_detection's own
compare_snapshots()/build_snapshot()/compute_affected_artifacts() --
every dirty/clean/affected/removed classification is read directly off
Phase E3's own ChangeDetectionReport, unchanged. Phase E4 never rebuilds
or mutates Phase E2's own DependencyGraph -- it is walked, read-only, to
answer Phase E4's own new question (rebuild ORDER + per-artifact
reasons), a question neither E2 nor E3 ever answers. Every fingerprint,
node, and edge is reused byte-for-byte from the artifact that already
computed it.
"""