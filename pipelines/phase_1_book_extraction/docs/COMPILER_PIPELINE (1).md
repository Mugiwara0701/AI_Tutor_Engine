# Compiler Pipeline — Pass by Pass

This document walks the actual call sequence, in order, with real
function names, at both scopes the system runs at: per-chapter
(`pipeline.process_chapter()`) and per-run (`CompilerRuntime._execute()`).
Read `PHASE1_ARCHITECTURE.md` first for what each phase *owns*; this
document is about *order and wiring*.

## 1. Book discovery (`book_orchestrator.py`)

```
book_orchestrator.run(use_vlm, page_batch_size, force, pdf_input_folder,
                       cancel_check=None, progress_callback=None)
  -> _ensure_storage_ready()                # OneDriveStorage init -> authenticate -> migration gate
  -> discover_books(pdf_input_folder)       # one Book per pdf_in/ subfolder with *.pdf, plus
                                             # one legacy Book if loose *.pdf sit in pdf_in/ itself
  -> for each Book:
       process_book(book, ...)
         -> pipeline.process_all_pdfs(pdf_folder=book.pdf_folder,
                                       output_root=None,
                                       book_title_override=book.name,
                                       cancel_check=...)
```

`_ensure_storage_ready()` is a hard gate: authentication and first-run
migration (`storage/migration.py`) must both succeed *before* any PDF is
discovered. A migration failure aborts startup entirely rather than
being logged and skipped, unlike every per-book/per-chapter failure
below.

`discover_books()` never infers a book's name from PDF content — the
folder name is authoritative and flows through as `book_title_override`
into every chapter that book produces (see `pdf_parser.BookContext`'s
own docstring on why this is deliberate).

## 2. Per-book chapter loop (`pipeline.process_all_pdfs()`)

For one book folder: finds the prelims PDF (if any, via
`pdf_parser.find_prelims_pdf()`), loads `BookContext` (title/subject/
class/TOC), applies a subject/class fallback chain (prelims → folder
name → chapter filename → `NCERT_DEFAULT_SUBJECT`/`NCERT_DEFAULT_CLASS`
env vars), pre-loads the VLM once for the whole call if `use_vlm=True`,
then loops chapter PDFs in sorted filename order, calling
`process_chapter()` once each. A `cancel_check()` returning `True` is
checked once per chapter boundary (not mid-chapter) and stops the
remaining chapters in this book, setting `"cancelled": True` in the
returned stats.

Per chapter, `process_all_pdfs()` also collects a Phase F3 reuse/rebuild
decision (via `build_executor.executor.execute_chapter()`, see §4) into
`chapter_decisions`, which becomes this book's own `ExecutionPlan`
(`build_executor.plan.generate_execution_plan()`) once the loop ends.

## 3. Per-chapter compilation (`pipeline.process_chapter()`)

This is the single largest function in the codebase and the one place
every phase from Stage A through Stage E is actually called, in this
order:

1. **Extraction-internal Stage A–E** (see `PHASE1_ARCHITECTURE.md` §2):
   text/OCR/layout extraction → `stage_a_geometry` (WHERE) →
   `stage_b_classify` (WHAT) → `stage_c_priority` (HOW IMPORTANT) →
   VLM semantic extraction gated by `equation_intent
   .introduces_reusable_knowledge()` → `stage_d_extraction` (extract) →
   `stage_e_validation` (dedupe).
2. **Canonical object assembly**: every educational object dict is
   merged with `modules.canonical.canonical_fields()`'s shared
   id/urn/provenance envelope as it is built.
3. **Compiler IR (Stage B)**, strictly in this order (`pipeline.py`'s own
   call sequence):
   ```
   create_registry_manager() -> populate_registries()
   -> enrich_registries()
   -> normalize_registries()
   -> resolve_references()
   -> resolve_relationships()
   -> validate_compiler_state()
   -> generate_compiler_manifest() / generate_compiler_statistics()
   -> generate_compiler_fingerprints()
   -> finalize_compiler_build()
   -> compiler_state.set_current_registry_manager(manager)
   ```
4. **Knowledge Graph (Stage C)**, immediately after, reusing the same
   `RegistryManager` read-only:
   ```
   build_knowledge_graph_nodes(manager)
   -> build_knowledge_graph_edges(...)          # from the `relationships` registry
   -> validate_knowledge_graph(...)
   -> generate_knowledge_graph_manifest() / generate_knowledge_graph_statistics()
   -> generate_graph_fingerprints()
   -> finalize_knowledge_graph()
   -> kg_state.set_current_knowledge_graph(...)
   ```
5. **Validation (Stage D)**:
   ```
   validate_system_integrity(...)      # D1 -- system_integrity_state
   -> validate_determinism(...)        # D2 -- determinism_state
   -> finalize_release(...)            # D3 -- release_state (chapter-scoped;
                                        #        NOT compiler_release/'s F5 artifact)
   ```
6. **Incremental-build bookkeeping (Stage E)**, one call per phase,
   each phase's result stored via its own `state.py` before the next
   phase runs:
   ```
   finalize_build_metadata(...)                        # E1 -> build_metadata_state
   -> generate_dependency_graph(...)                    # E2 -> dependency_graph_state
   -> detect_changes(...)                                # E3 -> change_detection_state
   -> plan_incremental_compilation(...)                  # E4 -> incremental_compilation_state
   -> validate_incremental_compilation(...)              # E5.1 -> incremental_compilation_validation_state
   -> finalize_incremental_compilation(...)              # E5.2 -> incremental_compilation_finalization_state
   ```
7. **Phase F3 reuse/rebuild execution** for this one chapter
   (`build_executor.executor.execute_chapter()`), which is what decides
   — via `modules.json_writer.is_already_extracted()` and `force` —
   whether steps 1–6 above even ran for this chapter, or whether the
   chapter was reused as-is from a previous run. See §4.
8. **JSON assembly**: `json_writer.assemble_chapter_json()` merges every
   section into one `ChapterJSON`-shaped dict (topics, concepts,
   glossary, definitions, examples, activities, figures, tables,
   equations, diagrams/charts/graphs/maps/timelines, boxes, notes,
   warnings, `blocks`, `educational_objects`, `validation_report`,
   `learning_graph`, `concept_graph`, `semantic_index`, `ai_metadata`,
   `generation_metadata`, `quality`, `extraction_logs`) —
   `write_chapter_json()` validates it against
   `schemas/chapter_schema.py::ChapterJSON` and persists it.

Every one of steps 3–6's `state.py` modules is reset at the *start* of
the next `process_chapter()` call (see `DEVELOPER_GUIDE.md`'s state
section) — nothing here is durable across chapters except what actually
lands on disk in the Chapter JSON, the Build Manifest, or the cache.

## 4. Reuse vs. rebuild (`build_executor/`, Phase F3)

`execute_chapter()` (`build_executor/executor.py`) is the one place
that decides, per chapter, whether steps 3–6 above run at all this call:

- If `force=False` and `modules.json_writer.is_already_extracted()`
  says this chapter's output JSON already exists → **reuse**: the
  chapter's own extraction function (`process_chapter`) is never called.
- Otherwise → **rebuild**: `process_chapter()` runs in full.

This is an *existence*-based decision, not a fingerprint-based one —
`build_executor/__init__.py`'s own docstring is explicit that a
persisted, fingerprint-based cache is Phase F4's job, not F3's. Every
chapter's decision (`reuse`/`rebuild` + reason) accumulates into
`chapter_decisions`, which `generate_execution_plan()` turns into this
book's `ExecutionPlan`; `process_all_pdfs()` attaches that plan to its
returned stats dict, and `CompilerRuntime._execute()` aggregates every
book's plan into one run-level `ExecutionReport`.

## 5. Run orchestration (`CompilerRuntime._execute()`, `runtime/runtime.py`)

The call sequence a `CompilerRuntime.run()`/`resume()` actually performs,
after acquiring the single-run-at-a-time lock:

```
_execute(context):
  reset_current_build() / reset_current_execution_report()
  / reset_current_cache_state() / reset_current_release_manifest_state()   # 4 independent try/except blocks

  book_orchestrator.run(use_vlm=context.use_vlm,
                         page_batch_size=context.page_batch_size,
                         force=context.force,
                         pdf_input_folder=context.pdf_input_folder,
                         cancel_check=self._check_cancel,
                         progress_callback=self._on_book_progress)
  -> all_stats   # list of per-book stats dicts, each carrying that book's ExecutionPlan

  # -- on success/cancelled --
  _record_build(context, runtime_state.get_current_status(), all_stats, None, started_at)   # F2
  _record_execution(all_stats)                                                              # F3
  _record_cache()                                                                           # F4
  _record_release()                                                                         # F5
  return all_stats

  # -- on any exception raised anywhere above --
  _record_build(context, RuntimeStatus.FAILED, [], str(exc), started_at)                    # F2
  _record_execution([])                                                                      # F3
  _record_cache()                                                                            # F4
  _record_release()                                                                          # F5
  raise    # the original exception, unmodified
```

Every `_record_*()` call follows the same "never raises" contract: each
is independently wrapped in `try/except Exception`, logged, and
swallowed, so a Phase F bookkeeping failure can never mask (or replace)
the actual success/failure of the underlying extraction run. Each
`_record_*()` also short-circuits cleanly (not an error) if the artifact
it depends on wasn't produced — e.g. `_record_release()` is a no-op if
`_record_build()` itself never produced a manifested `Build`.

What each `_record_*()` produces:

| Call | Package | Produces |
|---|---|---|
| `_record_build()` | `artifact_manager/` | `Build` + deterministic Build Manifest (fingerprints, per-book stats), persisted under `_runtime_builds/<build_id>/`. |
| `_record_execution()` | `build_executor/` | Run-level `ExecutionReport` aggregated from every book's own `ExecutionPlan`. |
| `_record_cache()` | `cache/` | Persists this run's fingerprint snapshot under `_runtime_cache/<build_id>/`, and a `CacheValidationReport` comparing this run's Execution Plan against the previous run's snapshot. |
| `_record_release()` | `compiler_release/` | One `CompilerReleaseManifest`, aggregating the three rows above plus `RuntimeStatus`, persisted under `_runtime_release/<build_id>/release_manifest.json`. |

`CompilerRuntime`'s own public introspection methods
(`status()`, `cache_status()`, `cache_history()`, `previous_cache_entry()`,
`cache_optimization_report()`, `release_manifest()`, `release_history()`,
`release_optimization_context()`) are all thin, read-only pass-throughs
over this already-recorded state — none of them re-runs any computation.
See `DEVELOPER_GUIDE.md` for the full public API with signatures.

## 6. Where persistence actually happens

Every persisted artifact in this system goes through exactly one storage
surface: `storage.OneDriveStorage`, first obtained by
`modules.json_writer.get_storage()` and reused (never re-instantiated)
by every later phase that persists something:

| Root | Written by | Contents |
|---|---|---|
| `json_out/Class_<k>/<Subject>/<Book>/` (via OneDrive) | `modules/json_writer.py` | Chapter JSON files + `_book_manifest.json` |
| `_runtime_builds/<build_id>/` | `artifact_manager/persistence.py` | Build + Build Manifest |
| `_runtime_cache/<build_id>/` | `cache/snapshot_store.py` | Fingerprint snapshot |
| `_runtime_release/<build_id>/` | `compiler_release/persistence.py` | `release_manifest.json` |

Each root is a sibling of the others by deliberate design (see each
package's own docstring) — no phase nests its records inside another
phase's folder, and no phase introduces a second serialization format,
storage client, or database.
