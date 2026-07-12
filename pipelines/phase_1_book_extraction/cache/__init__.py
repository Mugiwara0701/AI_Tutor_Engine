"""
cache/ — Phase F4.1: Cache Persistence & Validation.

SCOPE (frozen F4.1 architecture, nothing more): this package owns
exactly one thing neither Phase F2 nor Phase F3 owns -- making one
run's own already-computed fingerprints readable by a LATER run, and
reporting, read-only, how a fingerprint-based comparison of this run's
Execution Plan would have classified each chapter versus what Phase
F3's own (existence-based) Reuse Decision Engine actually decided.
Phase F2's own artifact_manager/discovery.py explicitly reserves this
role for Phase F4 ("no build database, no local index file -- that
would be a form of the 'Cache' F0 explicitly reserves for Phase F4"),
and Phase F3's own build_executor/__init__.py explicitly reserves it
too ("a persisted, cross-run artifact-fingerprint cache is explicitly
Phase F4's job").

Phase F4.1 NEVER creates Compiler IR, a Knowledge Graph, Validation,
Build Metadata, a Dependency Graph, Change Detection, an Incremental
Plan, Incremental Validation, or Incremental Finalization -- those
remain exactly where they already lived (Phases A-E5.2, all frozen,
untouched by this package). It never re-implements
change_detection.snapshot.build_snapshot()'s own fingerprint derivation
or compiler.fingerprints/knowledge_graph.fingerprints' own SHA-256
canonicalization -- every fingerprint this package persists is read
verbatim off Phase F2's own already-generated Build Manifest
(`build.build_manifest["fingerprints"]`, itself already surfaced,
never recomputed, from Phase B5.2/C4.2's own fingerprints -- see
artifact_manager/manifest.py's own `_collect_fingerprints()`).

  * `exceptions.py` -- this package's own exception hierarchy
    (CacheError and its CacheWriteError/CacheReadError/
    CacheValidationError subclasses), mirroring artifact_manager/
    exceptions.py's and build_executor/exceptions.py's shape one layer
    over.
  * `snapshot_store.py` -- persist_fingerprint_snapshot()/
    load_fingerprint_snapshot()/load_previous_fingerprint_snapshot(),
    reusing the exact same OneDriveStorage instance and
    upload_json()/download_json()/exists()/list_directory() surface
    artifact_manager/persistence.py already uses -- no new
    serialization format, no new storage client, no database.
  * `index.py` -- list_cache_entries()/cache_history(): cache
    discovery / cache history, over the same storage, via
    list_directory() (no new listing mechanism), mirroring
    artifact_manager/discovery.py's own list_builds()/build_history()
    one package over.
  * `validation.py` -- validate_execution_against_cache(): compares
    Phase F3's own already-made ExecutionPlan decisions against a
    fingerprint-based comparison of this run's snapshot against the
    previous one -- read-only, reports divergences, never re-decides
    reuse/rebuild and never feeds back into Phase F3's own decision
    this run.
  * `report.py` -- `CacheValidationReport`: the full Phase F4.1
    artifact, purely a data holder (matches every earlier phase's own
    "dataclass + to_dict(), all computation happens in the owning
    module" convention).
  * `state.py` -- set_current_cache_entry()/get_current_cache_entry()/
    has_current_cache_entry()/reset_current_cache_state() and the same
    idiom pair for the current CacheValidationReport, the exact
    set_current_*()/get_current_*()/has_current_*()/reset_*_state()
    idiom every other phase's own state.py in this codebase already
    uses -- run-scoped, like artifact_manager/state.py and
    build_executor/state.py, not chapter-scoped.

WHAT THIS IS NOT (see the frozen F4.1 architecture's own "F4 NEVER
OWNS" list): not execution gating (permanently Phase F3's), not a new
reuse decision engine (this package only VALIDATES Phase F3's own
already-made decisions, mirroring incremental_compilation_validation's
own "validate, don't re-plan" precedent one layer up), not an Input
Manifest (no such artifact is introduced -- cache validation works
entirely off fingerprints Phases B5.2/C4.2/F2 already computed), not a
database (OneDriveStorage only, same surface every other phase already
uses), not Compiler Build packaging or a release manifest (F5 -- out of
this package's own scope), and not Phase F4.2 (whatever future
refinement that may become is explicitly out of this freeze).
"""