"""
runtime/ — Phase F1: Compiler Runtime.

SCOPE: this package is the single execution entry point F0 §11 mandates
(`CompilerRuntime.run()/resume()/cancel()/status()/shutdown()`) around
the orchestration that already exists in this codebase --
book_orchestrator.run() -> pipeline.process_all_pdfs() ->
pipeline.process_chapter() -> every compiler/knowledge_graph/validation/
build_metadata/dependency_graph/change_detection/incremental_* phase in
sequence. It owns runtime lifecycle, runtime orchestration (as a thin
wrapper, not a re-implementation), execution context, runtime state,
progress reporting, logging, runtime status, cancellation, and resume --
exactly F0 §7's F1 responsibility list, nothing more.

  * `context.py` -- `RuntimeStatus` (the closed set of lifecycle states)
    and `ExecutionContext` (an immutable snapshot of one run's own
    use_vlm/page_batch_size/force/pdf_input_folder configuration).
  * `exceptions.py` -- this package's own exception hierarchy
    (`CompilerRuntimeError` and its lifecycle-misuse subclasses),
    mirroring compiler/exceptions.py's and change_detection/
    exceptions.py's shape one layer up. An error raised by an
    orchestrated phase (RegistryError, ChangeDetectionError, ...) is
    never wrapped in one of these -- see runtime.py's own module
    docstring for the full error-propagation contract.
  * `state.py` -- the module-level "current run's" status/context/
    progress/error slots, following the exact set_current_*()/
    get_current_*()/has_current_*()/reset_*_state() idiom compiler/
    state.py established and every later phase's own state.py has
    mirrored since -- run-scoped rather than chapter-scoped (see that
    module's own docstring for why).
  * `runtime.py` -- `CompilerRuntime`, the class itself.

WHAT THIS IS NOT (see this task's own "PHASE F1 DOES NOT OWN" list,
mirroring F0 §4/§7's F2-F5 split): this is not the Input Manifest, not
artifact persistence, not artifact discovery/loading/saving, not a build
history (all F2 -- Artifact Manager); not build gating, not incremental
execution, not build scheduling (all F3 -- Build Executor); not a cache
of any kind (F4 -- Cache & Build Optimization); and not Compiler Build
packaging, manifest generation, or a release artifact (F5 -- Compiler
Build Finalization). Phase F1 only starts, stops, and reports on a build
that pipeline.py's own existing code still does all the actual work
of -- it never persists anything, never decides whether a build can be
skipped, never caches anything, and never packages a Compiler Build.
"""