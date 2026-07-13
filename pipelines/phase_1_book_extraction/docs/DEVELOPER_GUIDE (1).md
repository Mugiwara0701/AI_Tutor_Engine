# Developer Guide

## Setup

```bash
pip install -r requirements.txt
```

Notable dependencies (`requirements.txt`): `pymupdf` (PDF parsing),
`pydantic>=2.6` (schema validation), `torch`/`transformers`/`accelerate`/
`bitsandbytes` (Qwen2.5-VL inference), `pytesseract`/`pillow` (OCR
fallback), `msal`/`requests`/`PyYAML` (OneDrive storage backend — see
`storage/requirements-storage.txt` for a standalone-storage-only subset).

Tesseract binary (only needed if any page has no extractable text layer):

```bash
sudo apt-get install tesseract-ocr   # Ubuntu
```

## Configuration

Everything lives in `config.py`, read from environment variables with
sane defaults (`NCERT_PDF_IN`, `NCERT_JSON_OUT`, `NCERT_STORAGE_BOARD`,
`NCERT_VLM_MODEL`, `NCERT_VLM_4BIT`, `NCERT_PAGE_BATCH_SIZE`,
`NCERT_DET_CONFIDENCE_FLOOR`, `NCERT_ENABLE_VISUAL_VLM`,
`NCERT_EXPORT_BLOCKS`, `NCERT_DEBUG`, `NCERT_DEFAULT_SUBJECT`,
`NCERT_DEFAULT_CLASS`, `NCERT_DEFAULT_LANGUAGE`). Storage-backend
configuration is separate: `config/storage.yaml`.

## Input layout

```
pdf_in/
├── Class_11_Economics/      # a "book" folder: subfolder + *.pdf inside
│   ├── lhat1ps.pdf          # prelims/TOC file — filename ends in "ps"
│   └── lhat101.pdf          # chapter file
├── Class_10_Science/
│   └── leec101.pdf
└── lhat1ps.pdf              # loose PDFs directly in pdf_in/ — legacy,
                              # backward-compatible: treated as ONE
                              # extra book with no name override
```

`book_orchestrator.discover_books()` auto-detects both layouts
simultaneously; a subfolder with no PDFs in it is skipped (logged, not
an error).

## Running

**Via the runtime layer** (recommended — gives you resumability, the
fingerprint cache, and a release manifest):

```python
from runtime.runtime import CompilerRuntime

rt = CompilerRuntime(use_vlm=True, page_batch_size=6, force=False)
stats = rt.run()          # raises on failure; RuntimeStatus tracked internally
# or, after a prior failed/cancelled run:
stats = rt.resume()       # always runs with force=False regardless of constructor's force

rt.status()                        # {"status", "context", "progress", "error"}
rt.cache_status()                  # this run's cache summary
rt.cache_history()                 # every persisted CacheEntry, oldest first
rt.previous_cache_entry()          # most recent CacheEntry strictly before this run
rt.cache_optimization_report()     # cross-run reuse-streak analysis
rt.release_manifest()              # this run's CompilerReleaseManifest, or None
rt.release_history()               # every persisted CompilerReleaseManifest, oldest first
rt.release_optimization_context()  # pass-through to cache_optimization_report()

rt.cancel()      # cooperative — honored between chapters, not mid-chapter
rt.shutdown()     # blocks further run()/resume()/cancel() calls; idempotent
```

`CompilerRuntime` is single-run-at-a-time: calling `run()`/`resume()`
while already running raises (`RuntimeAlreadyRunningError`), and it is
explicitly documented as not thread-safe.

**Directly**, bypassing Phase F bookkeeping entirely:

```bash
python pipeline.py                  # single-book, legacy entry point (PDFs directly in pdf_in/)
python pipeline.py --no-vlm         # deterministic-only, no model load
python pipeline.py --force          # ignore resumable skip, re-extract everything
python pipeline.py --batch-size 8   # pages per VLM batch (4-8)
```

```python
import book_orchestrator
book_orchestrator.run(use_vlm=True, page_batch_size=6, force=False)   # multi-book discovery
```

## Running tests

```bash
pytest tests/                # 59 test files as of this snapshot, organized roughly
                              # one file per phase/stage (test_f1_compiler_runtime.py,
                              # test_c3_graph_validation.py, test_e4_incremental_compilation.py, ...)
```

`conftest.py` at the repo root only ensures the project root is on
`sys.path` — no fixtures, no test doubles live there. Each phase's own
test file defines its own fakes (a `FakeStorage`/fake `OneDriveStorage`
stand-in exposing only `upload_json`/`download_json`/`exists`/
`list_directory`, and a `_FakeBookOrchestrator` for runtime-layer
integration tests) rather than sharing one global mock, so a test file
can be read in isolation.

Some tests require optional heavy dependencies (`fitz`/PyMuPDF,
`pydantic`, `msal`) to import cleanly — install the full
`requirements.txt`, not a trimmed subset, before running the suite.

## Module/package conventions (read this before adding a phase)

Every phase from Compiler IR (`compiler/`) onward in this codebase
follows the same shape, and new code should too:

- **`exceptions.py`** — one base exception per package
  (`XError(Exception)`), plus small, specific subclasses, so a caller
  can catch precisely what it cares about instead of parsing free-text
  messages. An error raised by an *earlier* phase is never re-wrapped by
  a later phase's own exception class.
- **`state.py`** — module-level "current chapter's" or "current run's"
  slot(s), each with a `set_current_*()`/`get_current_*()`/
  `has_current_*()`/`reset_current_*_state()` quartet. **Chapter-scoped**
  packages (`compiler/` through `incremental_compilation_finalization/`)
  reset at the *start* of the next `pipeline.process_chapter()` call.
  **Run-scoped** packages (`runtime/`, `artifact_manager/`,
  `build_executor/`, `cache/`, `compiler_release/`) reset at the start
  of the next `CompilerRuntime._execute()` call instead — see
  `runtime/runtime.py`'s own reset block for the exact five independent
  `try/except` calls, one per run-scoped package. None of these slots
  are thread-safe or concurrency-safe by design; every `state.py` says
  so explicitly.
- **A pure computation module** (named after what it computes:
  `build.py`, `finalize.py`, `validation.py`, `engine.py`, ...) — no
  I/O, no state-module calls itself; it receives already-computed
  arguments and returns a plain dict or dataclass. The *caller*
  (`pipeline.py` or `runtime.py`) is the only thing that calls a
  package's own `state.py`.
- **A dataclass artifact + `to_dict()`** — every phase's final output is
  a dataclass with a `to_dict()` method, never a hand-built dict
  literal duplicated at each call site.
- **Persisted phases only** (`artifact_manager/`, `cache/`,
  `compiler_release/`) additionally have `persistence.py`
  (`persist_*()`/`load_*()`/`*_exists()`, over the one shared
  `storage.OneDriveStorage` instance — never a new storage client or
  serialization format) and `discovery.py` (`list_*()`/`*_history()`,
  over `storage.list_directory()` — never a new indexing mechanism, one
  bad record must never hide the rest of the history).
- **Reuse, never re-derive.** Every phase's own module docstring
  includes an explicit list of what it reuses verbatim from an earlier
  phase and what it is careful never to recompute. Follow that pattern:
  before adding a new fingerprint, canonicalization routine, or status
  vocabulary, check `canonicalization.py` and `compiler/finalize.py`'s
  `STATUS_READY`/`STATUS_READY_WITH_WARNINGS`/`STATUS_FAILED` constants
  first — they are meant to be imported, not re-declared.
- **"Never raises" integration points.** Every `CompilerRuntime._record_*()`
  call (F2–F5) is independently wrapped in `try/except Exception`,
  logged, and swallowed, so one phase's bookkeeping failure can never
  mask or replace the real run outcome. Follow this pattern for any new
  run-scoped Phase F integration point.

## Storage backend (`storage/`)

`storage.OneDriveStorage` is the one persistence surface every phase
that writes anything durable uses (`modules/json_writer.py` obtains and
owns the singleton via `get_storage()`/`set_storage()`; every later
phase reuses that same instance rather than constructing its own).
Layout under one OneDrive root (`AI_TUTOR/` by default):

```
AI_TUTOR/<Board>/Class_<Class>/<Subject>/<Book>/{json_out,logs,cache,assets}/
_runtime_builds/<build_id>/     # Phase F2
_runtime_cache/<build_id>/      # Phase F4
_runtime_release/<build_id>/    # Phase F5
```

`storage/migration.py::ensure_migration_complete()` runs once at
`book_orchestrator.run()` startup, before any PDF is discovered: it
uploads any pre-existing local `json_out/` data to OneDrive, verifies
every upload, and writes a completion marker — a migration failure
aborts the whole run rather than being logged and skipped (unlike every
per-book/per-chapter failure elsewhere in the system).

## Where to look for X

| Question | Look at |
|---|---|
| "Why does this concept have two ids?" | `id` (short, hash-suffixed) vs. `urn` (hierarchical, globally unique) — both from `modules/pdf_parser.py::make_id`/`make_urn`, deterministic. |
| "What decides reuse vs. rebuild for a chapter?" | `build_executor/executor.py::execute_chapter()` — existence-based (`modules.json_writer.is_already_extracted()` + `force`), not fingerprint-based. |
| "What decides if a whole *run* is a good release?" | `compiler_release/finalize.py::determine_final_release_status()` — pure function of `RuntimeStatus` + this run's `chapters_failed` count + the cache's `overall_status`. |
| "Where does a new relationship type get added?" | `compiler/relationships.py::RELATIONSHIP_TYPES` (Compiler IR) — then, if it should also appear in the graph, `knowledge_graph/edge.py::FUTURE_EDGE_TYPES` already reserves `prerequisite`/`depends_on`/`related_to` for exactly this. |
| "What's chapter-scoped vs. run-scoped?" | Everything from `compiler/` through `incremental_compilation_finalization/` is chapter-scoped; everything under `runtime/`, `artifact_manager/`, `build_executor/`, `cache/`, `compiler_release/` is run-scoped. See `PHASE1_ARCHITECTURE.md` §1. |
| "How do I add a Word/PDF export of a chapter?" | Not implemented anywhere in this repository — out of scope for everything currently present (see `PHASE1_ARCHITECTURE.md` §8). |

## Known limitations (carried over from the original README, still accurate)

- Table detection relies on PyMuPDF's `find_tables()`; a caption-only
  fallback stub is emitted if no ruling-line table is detected for a
  page whose text says "Table N.N …", so nothing is silently dropped.
- `content_blocks.py`'s Activity/Box/Note/Warning/Example detection is
  keyword+font based; pages with unusual formatting may need a wider
  label pattern.
- `vlm_inference.generate_batch()` is sequential, not truly batched.
