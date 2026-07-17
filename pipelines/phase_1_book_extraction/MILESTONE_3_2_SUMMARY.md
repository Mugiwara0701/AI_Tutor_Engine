# Milestone 3.2 — Copyright-Safe Serialization Implementation Summary

Implements the approved recommendations from the Milestone 3.1 audit
(`M3.1_AUDIT.md`, provided as this milestone's blueprint — no re-audit
was performed). Scope, per this milestone's own instructions: implement
the **HIGH-risk findings** (M3.1 §2.1) plus the two explicit examples
that also cover a MEDIUM finding ("ensure raw OCR/text does not reach
the production Chapter JSON", "keep debugging information in debug/
extraction artifacts rather than production JSON").

## 1. What changed

A new serialization-time gate, `modules/copyright_sanitizer.py`, runs
once per chapter in `pipeline.py`, immediately after Stage E validation
and Knowledge-Graph-readiness enrichment finish (so every legitimate
deterministic reader of the raw content — Stage E's bare-arithmetic
filter — has already run) and before the Compiler IR registries or the
production Chapter JSON are built from `equations`/`educational_objects`.
It is the single, centrally-enforced checkpoint the audit's own
architectural concern #1 said did not exist.

| M3.1 finding | Risk | Action taken |
|---|---|---|
| `reusable_procedure` / `procedure_steps` (deterministic-sourced `formula_or_procedure` objects) | HIGH | Replaced with structural metadata: `procedure_step_count`, `procedure_step_marker_types` (per-step marker *shape* only — "step_n"/"numbered"/"first"/"then"/"next"/"finally"/"journal_keyword"/"algo_keyword"/"other" — never the step's own words) |
| `reusable_syntax` (deterministic-sourced `programming_syntax` objects) | HIGH, "REVIEW REQUIRED" | **Architectural decision** (no product/legal sign-off was given this milestone — see §2 below): defaults to the same treatment as every other HIGH-risk field, replaced with `code_line_count`/`has_code_content`. Gated by `config.PRESERVE_CODE_SNIPPETS_VERBATIM` (default `False`) for a future milestone to flip once that sign-off exists. |
| `Equation.raw_text` | HIGH | Removed; replaced with `has_raw_text_hint` (bool) |
| `Equation.vlm_raw_output` / `vlm_validation_errors` | MEDIUM (explicit example in this milestone's own instructions) | Moved to the new `extraction_debug/` artifact; production record keeps `vlm_analysis_skipped`/`educational_intent`/`block_type` |

`reusable_formula`, `semantic_meaning`, `latex`, `variables`, and every
canonical id/urn/provenance field are **untouched** — they were already
SAFE (M3.1 §2.4) or already going through the VLM paraphrase +
`_enforce_word_cap` two-net design (§2.3).

Stripped content is not discarded: it is written to a new,
chapter-scoped, debug-only artifact folder (`extraction_debug/`, a
sibling of `json_out/`), via `extraction_debug/persistence.py`, and
**only** for chapters that actually had something to strip (most
chapters produce no file there at all).

## 2. Architectural decision documented (per this milestone's own
   "if any recommendation requires an architectural decision, document
   your reasoning before making changes" instruction)

`reusable_syntax` was the one HIGH-risk finding the M3.1 audit did not
give a single recommended action for — it explicitly requires product/
legal sign-off on whether verbatim code snippets are an intentional
in-scope feature for a CS tutor. No such sign-off was provided as part
of this milestone. Rather than guess, this implementation:

- Defaults to the same conservative treatment as every other HIGH-risk
  field (redact to structural metadata), since that is the only
  decision this milestone can make safely without that sign-off.
- Exposes `config.PRESERVE_CODE_SNIPPETS_VERBATIM` (env var
  `NCERT_PRESERVE_CODE_SNIPPETS`, default off) as the single toggle a
  future milestone flips once product/legal has actually decided —
  `modules/copyright_sanitizer.py` already branches on it, so no further
  code change is needed to reverse this decision later, only the flag.

## 3. Design constraints satisfied

- **Deterministic:** `copyright_sanitizer.py` has no I/O, no VLM calls,
  and no randomness; same input always produces the same output (verified
  by unit tests re-running sanitization and comparing results).
- **Stable object IDs / urn / serialization ordering:** every id, urn,
  page, bbox, and list ordering is passed through untouched — the
  sanitizer only pops/adds keys on the *same* dict objects, in place,
  never reorders or re-keys a list.
- **Structurally complete:** every sanitized object still carries every
  field Phase 2 needs to know an item exists and where it came from
  (block/page/confidence/provenance) — only the copyright-risky prose
  itself is gone.
- **Backwards compatible where practical:** see `MIGRATIONS.md` for the
  full field-by-field mapping and the accompanying `SCHEMA_VERSION`
  bump (2.0.0 -> 3.0.0, MAJOR — these are real field removals, not
  silent no-ops).
- **Existing compiler architecture unchanged:** no recognizer, no Stage
  A-E logic, and no VLM prompt changed. The sanitizer is purely a
  post-processing gate over already-finished Stage D/E output.
- **M2 validation framework reused, not reinvented:** `modules/
  structural_validator.py`'s existing `banned_prose_field_present` check
  (Milestone 2) already flags `raw_text` as an ERROR when present — this
  milestone's fix is exactly what makes that check start passing cleanly
  instead of merely reporting the problem (see M3.1 §1 architectural
  note: M2 could detect the leak but had no removal step; M3.2 supplies
  that step).

## 4. Files changed / added

**New:**
- `modules/copyright_sanitizer.py` — the sanitizer itself.
- `extraction_debug/__init__.py`, `extraction_debug/persistence.py` — new
  debug-only artifact package, mirrors `validation/persistence.py`'s
  shape exactly.
- `tests/test_copyright_sanitizer.py` — unit tests.
- `MIGRATIONS.md` — schema version history (new file; previously only
  referenced by comments, never actually created in this checkout).
- `MILESTONE_3_2_SUMMARY.md` — this file.

**Modified:**
- `pipeline.py` — imports `copyright_sanitizer` and
  `extraction_debug.persistence.persist_extraction_debug`; calls
  `copyright_sanitizer.sanitize_chapter_records()` once, right after
  Knowledge-Graph-readiness enrichment; threads the resulting debug
  entries through `_persist_phase1_artifacts()` (new optional
  `copyright_debug_entries` parameter, defaults to `None`/`[]` so any
  other caller of that function is unaffected) to
  `persist_extraction_debug()`, wrapped in the same
  "never raises, logs and continues" pattern every other artifact
  persister in that function already uses.
- `modules/json_writer.py` — adds `"extraction_debug"` to
  `_ARTIFACT_SUBFOLDERS` (so `book_output_dir()`'s existing
  folder-provisioning loop creates it, and `artifact_output_path()`
  accepts it) — the same one-line addition pattern the
  `document_structure_tree` entry right above it already used.
- `config.py` — bumps `SCHEMA_VERSION` to `"3.0.0"` with a migration
  comment; adds `PRESERVE_CODE_SNIPPETS_VERBATIM` (see §2 above).

## 5. Testing

- `tests/test_copyright_sanitizer.py`: unit tests covering
  `sanitize_equations`, `sanitize_educational_objects`, and
  `sanitize_chapter_records` — raw-text/vlm-debug removal and hint
  generation, procedure-step structural-metadata generation (including
  every marker-shape category), the VLM-fallback-is-left-alone rule,
  code-snippet structural-metadata generation, the
  `PRESERVE_CODE_SNIPPETS_VERBATIM` toggle, non-mutation of inputs, and
  empty-input handling.
- **Regression test results:** this sandbox has no network access and
  neither `pytest` nor `pydantic` installed, so the test suite (and the
  existing `tests/test_structural_validator.py`, which imports
  `schemas.chapter_schema` and therefore `pydantic`) could not be
  executed here via `pytest`. Every assertion in
  `tests/test_copyright_sanitizer.py` was instead re-run manually as a
  plain Python script (no pytest/pydantic dependency) against the actual
  `modules/copyright_sanitizer.py` module and passed. A manual
  integration check (sanitized equation + educational-object output fed
  into `modules.structural_validator.validate_structural_completeness`'s
  `_check_source_text_leakage` logic) confirms the sanitized shape no
  longer contains any `_BANNED_PROSE_FIELD_NAMES` key — this could only
  be verified by source review, not execution, because that path
  requires `pydantic` (unavailable here). Whoever runs this in the
  project's real environment (where `pytest`/`pydantic` are installed,
  per the existing `tests/test_structural_validator.py`) should run
  `pytest tests/` as the first regression check.

## 6. Recommendations deferred to future milestones

Per this milestone's HIGH-risk-only scope, the following M3.1 findings
were **not** implemented here and remain open:

- **MEDIUM — `semantic_description`** (Activity/Box/Warning/Note/Example):
  route through `semantic_processor`'s paraphrase+cap path the same way
  Figures/Tables/Equations already do, instead of the current
  `_enforce_word_cap(body[:200])` raw-truncation in `pipeline.py`'s
  `_finalize_blocks()`.
- **MEDIUM — `rules`** (`accounting_format` objects): add a length/count
  cap, or replace with `matched_rule_types: List[str]`.
- **MEDIUM — table caption-only fallback**: add a length cap.
- **LOW — figure/table caption (normal path)**: add a defensive length
  cap.
- **LOW — `evidence_span`**: currently inert (never populated); flag for
  whoever eventually populates it.
- **Non-copyright, but noted by the audit:** `content_blocks.py`'s stale
  module docstring (claims the module is unused; `pipeline.py` calls it
  directly) was **not** corrected in this milestone — out of scope per
  this milestone's "Do NOT redesign the compiler" instruction, since
  fixing it touches no copyright-risk field.
