"""
change_detection/ — Phase E3: Change Detection.

SCOPE: this package answers exactly one question -- "what changed?" --
by comparing this chapter's CURRENT build (Phase B-E2's own
already-computed fingerprints, reused unchanged) against a PREVIOUS
build's fingerprint snapshot (an `Optional` input this package accepts
but never sources itself -- see `snapshot.py`'s own module docstring
for why). It does NOT decide what should be rebuilt (that is Phase
E4's Incremental Compilation, not this package's concern) and does NOT
persist anything to disk (Persistence Store is explicitly out of scope
-- see the task's own DO NOT IMPLEMENT list).

  * `exceptions.py` -- this package's own exception hierarchy, mirrors
    dependency_graph/exceptions.py's shape and role one package over.
  * `snapshot.py` -- `build_snapshot()`: derives one
    `{artifact_key: fingerprint}` map for the CURRENT build from
    Phase E1's BuildMetadata and Phase E2's DependencyGraph, reusing
    every fingerprint that already exists (compiler_fingerprint,
    graph_fingerprint, configuration_fingerprint, per-registry
    fingerprints) as-is, and deriving one via the shared
    canonicalization.py primitives ONLY for artifacts that have no
    dedicated fingerprint of their own yet (manifests, statistics,
    readiness reports, build summaries, BuildMetadata itself, and the
    DependencyGraph's own shape) -- never a second, independently
    invented fingerprint algorithm.
  * `compare.py` -- `compare_snapshots()`: pure, deterministic
    Artifact Comparison + Fingerprint Comparison + Changed Artifact
    Detection -- added / removed / modified / unchanged-candidate
    artifact keys, from two snapshots and nothing else.
  * `traversal.py` -- `compute_affected_artifacts()`: Dependency Graph
    Traversal -- walks Phase E2's own DependencyGraph edges (read-only,
    never rebuilt, never modified) to find every artifact that
    transitively depends on a changed one.
  * `report.py` -- `ChangeDetectionReport`, the graph-level container
    this package ultimately produces: added/removed/modified/affected/
    unchanged artifacts, a summary, warnings, and errors.
  * `engine.py` -- `detect_changes()`, the one read-only pass that
    orchestrates snapshot -> compare -> traverse -> report. The one
    pipeline.py integration point.
  * `state.py` -- the module-level "current chapter's
    ChangeDetectionReport" slot, following the exact single-slot idiom
    dependency_graph/state.py already establishes one phase down.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Incremental Compilation (E4), not Validation & Finalization (E5), not
a dirty-rebuild executor, not an incremental planner, not a cache, not
a persistence layer, not minimal-rebuild execution, and not build
skipping. Phase E3 only detects and reports what changed -- it never
rebuilds, never skips a build step, and never decides what a future
phase should do about a detected change.

READ-ONLY OVER EVERYTHING IT COMPARES: no Compiler IR, Knowledge
Graph, Validation report, Build Metadata, Dependency Graph, Chapter
JSON, or registry is ever inserted into, updated, or removed from by
this package. `detect_changes()` only ever reads already-computed
dicts and returns a brand new report -- see engine.py's own module
docstring.
"""