# Phase 1 Architecture

This document describes the full system as implemented: what runs, in
what order, what each layer owns, and what each layer explicitly does
not own. It is derived from the packages' own module docstrings (which
in this codebase are unusually precise and were treated as authoritative)
and cross-checked against `pipeline.py` and `runtime/runtime.py`, the two
files that actually wire everything together.

**A naming note before anything else**, because it trips up new readers:
this codebase uses the letters **A–E twice, at two different scopes**:

1. **Compiler-level Stage A–E** (this document's own top-level
   structure): Stage A = the whole PDF-extraction layer, Stage B =
   `compiler/` (Symbol Table), Stage C = `knowledge_graph/`, Stage D =
   `validation/`, Stage E = the five incremental-build phases
   (`build_metadata/` … `incremental_compilation_finalization/`).
2. **Extraction-internal Stage A–E** (`modules/stage_a_geometry.py` …
   `modules/stage_e_validation.py`): a five-step *sub*-pipeline that
   lives entirely inside Compiler-level Stage A, turning raw
   text/layout into classified, prioritized, extracted, validated
   educational blocks.

Everywhere below, "Stage A" alone means the compiler-level stage;
extraction-internal stages are always written as "extraction Stage A"
etc.

## 1. The two runs of the system

There are two ways this code executes, and they nest:

- **Per-chapter compilation** — `pipeline.process_chapter()` — runs
  every one of Stage A through Stage E (compiler-level) for a single
  chapter PDF. This is the unit everything from `compiler/` through
  `incremental_compilation_finalization/` is scoped to: every state
  module in those packages holds exactly one chapter's data at a time
  and is reset at the start of the next chapter (see
  `DEVELOPER_GUIDE.md`'s state-lifecycle section).
- **A run** — `runtime.runtime.CompilerRuntime.run()`/`resume()` — calls
  `book_orchestrator.run()` (via `pipeline.process_all_pdfs()`) once per
  discovered book, which calls `process_chapter()` once per chapter, and
  then aggregates what happened *across every chapter and every book in
  that call* into run-scoped artifacts: a Build, an Execution Report, a
  Cache Entry/Validation Report, and finally a Compiler Release Manifest
  (Phases F1–F5). These are entirely separate from the chapter-scoped
  state above.

## 2. Stage A — Extraction (`modules/`, `pipeline.process_chapter()`)

Turns one chapter PDF into raw text, layout, and a first educational
JSON draft. Implemented across `modules/pdf_parser.py`,
`modules/ocr_engine.py`, `modules/layout_detector.py`,
`modules/content_blocks.py`, `modules/language_detector.py`,
`modules/ocr_cleanup.py`, `modules/semantic_processor.py`,
`modules/vlm_inference.py`, `modules/graph_builder.py`, and the
extraction-internal Stage A–E modules below.

| Step | Module | Does |
|---|---|---|
| Chapter split, TOC, heading detection | `pdf_parser.py` | Font/heading-based chapter and topic boundary detection (the original deterministic layer); `make_id`/`make_urn`/`slugify` — the canonical identity primitives every later phase reuses. |
| Text extraction | `ocr_engine.py` | Text-layer-first page text, Tesseract OCR fallback for scanned pages, per-page confidence. |
| Text normalization | `ocr_cleanup.py` | Ligature/whitespace/punctuation cleanup, language-agnostic. |
| Language detection | `language_detector.py` | Script-ratio + metadata-based language detection, defaults to English. |
| Layout detection | `layout_detector.py` | Figure/table/equation/diagram bounding boxes (PyMuPDF images, `find_tables()`, vector-drawing clustering, equation heuristics). |
| Deterministic block patterns | `content_blocks.py` | Activities/Boxes/Notes/Warnings/Examples/definition-term detection. |
| **extraction Stage A** | `stage_a_geometry.py` | WHERE are the blocks — geometry-only segmentation into hierarchical `Block` objects (e.g. a worked example's formula/calculation/answer lines become children of one block). No VLM. |
| **extraction Stage B** | `stage_b_classify.py` | WHAT is the block — pure deterministic classification into one of the frozen `BLOCK_TYPES` (Heading, Definition, Law, Formula Box, Worked Example, Exercise, Activity, Summary, Table, Figure, Diagram, Flowchart, Programming Syntax, Accounting Format, Reference, Footer, Header, Decision Tree, Ambiguous). No VLM; ambiguous stays ambiguous. |
| **extraction Stage C** | `stage_c_priority.py` | HOW IMPORTANT — attaches high/medium/low priority via a configurable table; nothing is discarded. |
| Semantic extraction | `semantic_processor.py` + `vlm_inference.py` | All Qwen2.5-VL prompts (topics, figures, tables, chapter metadata; equations only where `equation_intent.introduces_reusable_knowledge()` says so) and JSON-response parsing; enforces the ≤30-word / no-verbatim copyright rule at the code level (`config.MAX_SEMANTIC_DESCRIPTION_WORDS`), independent of model compliance. |
| **extraction Stage D** | `stage_d_extraction.py` | Extracts educational knowledge from priority-annotated blocks: cheap deterministic recognizers first, VLM fallback at most once per block only if confidence < `config.DETERMINISTIC_CONFIDENCE_FLOOR`, and only for block types with registered recognizers. |
| **extraction Stage E** | `stage_e_validation.py` | Deterministic-only validation: removes duplicate formulas/definitions/bare-arithmetic objects; normalizes only the dedupe key, never the object's own field values. |
| Canonical envelope | `modules/canonical.py` | `canonical_fields()` builds the shared id/urn/provenance/creation-metadata envelope every canonical object dict gets merged with; `resolve_concept_ids()` does best-effort name→id concept linkage. |
| Assembly | `modules/json_writer.py` | `assemble_chapter_json()` merges every section (topics/concepts/.../blocks/educational_objects/learning_graph/...) into one `ChapterJSON`-shaped dict; `write_chapter_json()` validates it against `schemas/chapter_schema.py` and persists it via `storage.OneDriveStorage`. |

Output: one Chapter JSON file per chapter (see `JSON_SCHEMA.md`). This is
the **only** artifact Stage A produces that is ever persisted to disk —
everything from Stage B onward operates on in-memory structures built
from the same in-process data, not by re-reading the JSON file back.

## 2.5. Phase 1.5 — Pre-compiler cleanup

`modules/ocr_cleanup.py` and `modules/language_detector.py` (listed
separately from Stage A in `compiler_release/report.py`'s own repository
audit) are the pre-compiler text/OCR cleanup and language-handling layer
Stage A calls into before classification. They produce no artifact of
their own; they are upstream inputs consumed inline by Stage A's text
pipeline.

## 3. Stage B — Compiler IR / Symbol Table (`compiler/`)

Once a chapter's canonical objects exist in memory, `compiler/` builds
one `RegistryManager` per chapter holding thirteen typed registries
(`topics`, `definitions`, `concepts`, `glossary`, `figures`, `diagrams`,
`tables`, `equations`, `activities`, `boxes`, `warnings`, `notes`,
`examples` — `compiler/registries.py::REGISTRY_NAMES`), plus a
fourteenth, `relationships`, added when `compiler/relationships.py`
first runs. Pipeline order within Stage B:

1. `create_registry_manager()` + `populate_registries()` — one registry
   per object type, deterministic ids/urns already attached.
2. `enrichment.enrich_registries()` — derived display names, roles,
   summaries; never changes an id/urn.
3. `normalization.normalize_registries()` — casefolded lookup keys for
   name matching.
4. `references.resolve_references()` — definitions/glossary entries
   resolve to concept ids by normalized name.
5. `relationships.resolve_relationships()` — generates the nine
   `RELATIONSHIP_TYPES` (`has_definition`, `explains`, `described_by`,
   `contains`, `appears_in`, `belongs_to`, `uses_concept`, `illustrates`,
   `teaches`) into the new `relationships` registry.
6. `validation.validate_compiler_state()` — registry/reference/
   relationship/state integrity + deterministic-id recomputation checks.
7. `build.generate_compiler_manifest()` / `generate_compiler_statistics()`
   — deterministic manifest + statistics, read off the already-built
   registries (never a re-scan).
8. `fingerprints.generate_compiler_fingerprints()` — one SHA-256 per
   registry plus one overall `compiler_fingerprint`, over canonicalized
   (volatile-timestamp-stripped) content.
9. `finalize.finalize_compiler_build()` — one closed-set
   `STATUS_READY` / `STATUS_READY_WITH_WARNINGS` / `STATUS_FAILED`
   verdict plus a `CompilerBuildSummary`.

Every one of these is chapter-scoped and held in `compiler/state.py`'s
module-level "current chapter" slots.

## 4. Stage C — Knowledge Graph (`knowledge_graph/`)

Reads the already-populated Compiler IR (Stage B's `RegistryManager` and
every Phase B artifact) and never writes back into it. Phases actually
implemented, in call order from `pipeline.py`:

- **C1 — Node construction** (`build_nodes.py`): one `GraphNodeBase`
  instance per canonical Compiler-IR object, inserted into a
  `GraphRegistryManager`'s `nodes` registry.
- **C2 — Edge construction** (`build_edges.py`): one graph edge per
  already-resolved Compiler-IR relationship (Stage B's `relationships`
  registry) — no new relationship logic, pure re-projection.
- **C3 — Validation & integrity** (`validation.validate_knowledge_graph()`,
  function-based, *not* the six ABC contracts described below).
- **C4.1 — Manifest & statistics** (`build.py`).
- **C4.2 — Fingerprints & readiness** (`fingerprints.py`).
- **C4.3 — Finalization** (`finalize.py`): closed-set final status +
  `KnowledgeGraphBuildSummary`, mirroring Stage B's own Phase B5.3.

See `KNOWLEDGE_GRAPH.md` for the full node/edge type list, the six
still-unimplemented ABC validation contracts reserved for a future C5,
and the deterministic identity scheme.

## 5. Stage D — Validation (`validation/`)

Three chapter-scoped passes, each aggregating what earlier phases
already computed — none re-derives a check another phase already made:

- **D1 — System Integrity** (`system_integrity.py`): cross-artifact
  consistency between Compiler IR and Knowledge Graph (dangling
  references, count/fingerprint agreement).
- **D2 — Determinism** (`determinism.py`): reproducibility, not
  correctness — does re-canonicalizing/re-fingerprinting the same
  already-built state reproduce byte-identical output.
- **D3 — Release Readiness** (`release.py`): the final chapter-level
  gate, aggregating Compiler + Knowledge Graph + D1 + D2 verdicts into
  one chapter Release Decision. **Not** to be confused with Phase F5's
  run-level `CompilerReleaseManifest` — D3 is explicitly chapter-scoped
  and explicitly disclaims packaging in its own docstring.

## 6. Stage E — Incremental-build bookkeeping (five phases)

Each phase below is chapter-scoped, reuses the previous phase's output
verbatim, and adds exactly one new question:

| Phase | Package | Question it answers |
|---|---|---|
| E1 | `build_metadata/` | What operational + configuration + version metadata describes this build? (`BuildMetadata`) |
| E2 | `dependency_graph/` | Which compiler artifact was built from which other artifact, this chapter? (`DependencyGraph` — a build-system DAG, unrelated to the Knowledge Graph) |
| E3 | `change_detection/` | What changed vs. a previous build's fingerprint snapshot? (`ChangeDetectionReport`) |
| E4 | `incremental_compilation/` | Given what changed, what must rebuild, in what order, and why? (`IncrementalCompilationPlan` — a plan only, never executed here) |
| E5.1 | `incremental_compilation_validation/` | Is that plan itself internally valid? (`IncrementalCompilationValidationReport`) |
| E5.2 | `incremental_compilation_finalization/` | Can the validated plan be finalized: final status, readiness report, build summary? |

None of Stage E executes a rebuild — that is Phase F3's job, one layer
up, at run scope rather than chapter scope.

## 7. Phase F — Runtime (`runtime/`, `artifact_manager/`, `build_executor/`, `cache/`, `compiler_release/`)

Run-scoped (not chapter-scoped): one instance of each Phase F artifact
per `CompilerRuntime.run()`/`resume()` call, covering every book/chapter
that run touches.

| Phase | Package | Owns |
|---|---|---|
| F1 | `runtime/` | `CompilerRuntime` itself: `run()`/`resume()`/`cancel()`/`status()`/`shutdown()`, `RuntimeStatus` lifecycle, `ExecutionContext`, cancellation, progress callbacks. Wraps `book_orchestrator.run()` — does not reimplement it. |
| F2 | `artifact_manager/` | The `Build` object + deterministic Build Manifest (fingerprints, per-book stats), persistence/discovery/history against `storage.OneDriveStorage`. |
| F3 | `build_executor/` | `ExecutionPlan` (reuse vs. rebuild per chapter, via the existing `is_already_extracted()`/`force` signal — not a second fingerprint check), `ExecutionReport`. |
| F4 | `cache/` | Cross-run fingerprint snapshot persistence + `CacheValidationReport` (this run's fingerprints vs. the previous run's) + cross-run reuse-streak analysis (`cache_optimization_report()`). |
| F5 | `compiler_release/` | `CompilerReleaseManifest` — the one final, run-scoped verdict (`READY`/`READY_WITH_WARNINGS`/`FAILED`) aggregating F1–F4's own already-computed outputs. Never recomputes a fingerprint or a validation verdict. |

See `COMPILER_PIPELINE.md` §4 for the exact call sequence inside
`CompilerRuntime._execute()`, and `DEVELOPER_GUIDE.md` for the
`CompilerRuntime` public API.

## 8. What is explicitly out of scope (verified via each package's own "WHAT THIS IS NOT" section)

- Master JSON assembly beyond the single Chapter JSON, slide/quiz/
  teaching-content generation — out of scope for every package in this
  repository (`README.md`, `pipeline.py`'s own header comment).
- A cross-book curriculum graph — the Knowledge Graph is per-chapter;
  nothing in this repository merges graphs across chapters or books.
- The six ABC validation contracts in `knowledge_graph/validation.py`
  (`NodeValidator`, `EdgeValidator`, ... ) — declared, documented,
  covered by a test asserting they remain unimplemented
  (`tests/test_c3_graph_validation.py::test_abc_contracts_are_still_unimplemented`),
  reserved for "a future C5 Validation phase" per that module's own
  docstring. **Inferred to be intentionally unfinished**, not a gap in
  this analysis.
- Any execution of an incremental rebuild plan inside Stage E itself —
  Stage E only plans; Phase F3 executes.
- A build database or second persistence format anywhere in Phase F —
  every phase from F2 through F5 explicitly reuses one
  `storage.OneDriveStorage` instance and its `upload_json`/
  `download_json`/`exists`/`list_directory` surface.
