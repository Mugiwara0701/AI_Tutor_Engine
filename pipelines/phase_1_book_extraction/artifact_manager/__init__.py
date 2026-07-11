"""
artifact_manager/ — Phase F2: Artifact Manager.

SCOPE (F0 §7's F2 responsibility list, nothing more): this package owns
the Build object, the Build Manifest, artifact persistence, artifact
loading, artifact discovery, build history, runtime build metadata, and
the runtime artifact registry -- i.e. everything about *what a
CompilerRuntime run produced and where it lives*, once book_orchestrator.
run() (via pipeline.process_all_pdfs()/process_chapter()) has already
done every bit of actual compiler/knowledge-graph/validation/dependency-
graph/change-detection/incremental-* work.

Phase F2 NEVER creates Compiler IR, a Knowledge Graph, Validation,
Build Metadata, a Dependency Graph, Change Detection, an Incremental
Plan, Incremental Validation, or Incremental Finalization -- those are
Phases A-E1/E2/E3/E4/E5's own artifacts, already computed by
pipeline.process_chapter() by the time CompilerRuntime.run() returns.
This package only REFERENCES them (see build.py's own module docstring
for exactly what "reference" means given those artifacts are, by
existing and frozen design, chapter-scoped and not persisted anywhere
durable by Phases A-E1 themselves) and PERSISTS what Phase F2 itself
produces (the Build + Build Manifest), reusing the exact same
OneDriveStorage instance and upload_json()/download_json()/exists()/
list_directory() surface modules/json_writer.py already uses -- no new
serialization format, no new storage client, no new registry
implementation.

  * `exceptions.py` -- this package's own exception hierarchy
    (ArtifactManagerError and its BuildError/ManifestError/
    PersistenceError/ArtifactError subclasses), mirroring runtime/
    exceptions.py's/compiler/exceptions.py's shape one layer over.
  * `build.py` -- the immutable Build dataclass and create_build().
  * `manifest.py` -- deterministic Build Manifest generation.
  * `persistence.py` -- persist_build()/load_build(), reusing
    modules.json_writer's existing OneDriveStorage singleton and
    upload_json/download_json/exists.
  * `discovery.py` -- artifact discovery / build history: list_builds()
    over the same storage, via list_directory() (no new listing
    mechanism).
  * `state.py` -- set_current_build()/get_current_build()/
    has_current_build()/reset_current_build(), the exact set_current_*()/
    get_current_*()/has_current_*()/reset_*_state() idiom every other
    phase's own state.py in this codebase already uses.

WHAT THIS IS NOT (see this task's own "DO NOT IMPLEMENT" list): not
Input Manifest, not incremental execution, not build scheduling, not a
cache, not Compiler Build packaging, not a reuse engine -- those belong
to F3-F5. This package never decides whether a build *should* run
(F3), never optimizes or caches anything (F4), and never produces a
release/packaged Compiler Build (F5); it only records what a build that
already ran produced.
"""
