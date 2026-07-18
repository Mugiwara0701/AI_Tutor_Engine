# Chapter JSON schema migrations

## 4.0.0 -> 4.1.0 — Milestone 3.4, Code-Structural Metadata

**Type:** MINOR (purely additive optional fields; no field removed, no
existing field's meaning changed).

**What changed:** two new optional fields are now emitted on
`educational_objects[]` entries whose `educational_object_type` is
`"programming_syntax"` and whose `source` is `"deterministic"`:

| New field | Type | Derivation |
|---|---|---|
| `code_language` | `string \| null` | Single best-fit syntax family detected by keyword/regex over `reusable_syntax` before it is discarded.  Closed vocabulary: `python`, `c_cpp`, `java`, `javascript`, `sql`, `pseudocode`, `other`. |
| `code_construct_types` | `List[string]` | All structural construct labels detected in the same pass.  Closed vocabulary: `assignment`, `class_def`, `comment`, `conditional`, `exception_handling`, `function_def`, `import_statement`, `loop`, `print_statement`, `return_statement`. |

Both fields are `None` / `[]` when the object has no code content or is
not a `programming_syntax` object, so all non-code objects are completely
unaffected.

**Why MINOR, not MAJOR:** purely additive.  No existing field is removed,
renamed, or changes meaning.  A consumer that does not read these fields
receives the same data as before; `EducationalObject` is already
`extra="allow"` so new keys never cause schema-validation failures.

**Structural validator:** rule 13 (`code_vocab_membership`) is added in
this milestone (`STRUCTURAL_VALIDATION_VERSION` bumped from `1.0.0` to
`1.1.0`).  It raises an ERROR for an unknown `code_language` value and a
WARNING for an unknown `code_construct_types` entry.

**No new pipeline stage:** both fields are derived inside the existing
`copyright_sanitizer._code_structural_metadata()` helper, which is
already called from `sanitize_educational_objects()` at the same
checkpoint that already computes `code_line_count`/`has_code_content`
from the same `reusable_syntax` string.  No new VLM call, no new OCR
pass, no PDF re-read.

**Rejected fields (permanently out of scope for M3.4 and Phase 1):**
`related_object_ids`, `equation_role`, `pedagogical_pattern`,
`account_category`, `visual_subtype`, `step_dependency_order`.  See
`M3.4_AUDIT.md` for the per-field rejection rationale.



Tracks `config.SCHEMA_VERSION` (MAJOR.MINOR.PATCH, per config.py's own
policy comment) history for the exported Chapter JSON
(`schemas/chapter_schema.py: ChapterJSON`).

## 3.0.0 -> 4.0.0 — Milestone 3.3, Copyright-Safe Serialization cont'd

**Type:** MAJOR (a field removed, plus two fields whose meaning changes
without being removed — see below).

**What changed:** the MEDIUM/LOW M3.1 audit findings M3.2 deferred (see
"What did NOT change in this milestone" at the bottom of the 3.0.0 entry
below) are now implemented, at the same `copyright_sanitizer.py`
checkpoint in `pipeline.py` as M3.2's findings:

| Field | Was on | Change |
|---|---|---|
| `educational_objects[].rules` | `EducationalObject` (`accounting_format`, `format_type == "accounting_rule"`) † | **Removed.** Replaced by `.matched_rule_count`, `.matched_rule_types` |
| `activities[].semantic_description`, `boxes[]`, `warnings[]`, `notes[]`, `examples[]` (same field) | those five block kinds | **Meaning changed, not removed.** Always `""` now (previously a raw, word-capped-but-still-copied excerpt of the block's own source text); paired with a new `.has_semantic_description_hint` (bool) |
| `figures[].caption` / `.title`, `diagrams[]`, `tables[]` (same two fields) | those three region kinds | **Meaning changed, not removed.** Capped at `config.MAX_CAPTION_WORDS` (20) instead of unbounded PDF/OCR-sourced text |

† Only for objects whose `source == "deterministic"`, same convention as
every other M3.2/M3.3 finding.

**Why MAJOR:** `rules` removal is the same "consumer silently gets
nothing instead of an error" MAJOR case 2.0.0 -> 3.0.0 defines. The two
meaning-changed fields are also MAJOR, not MINOR/PATCH, because a
consumer that was reading `semantic_description` for its (copied) prose,
or reading an overlong `caption`/`title` in full, now silently gets a
truncated or empty value instead — same silent-behavior-change concern
the policy's MAJOR case exists for, even though the field itself still
exists and still type-checks.

**Backward compatibility:** every id/urn/page/bbox/confidence/provenance
field, and every field not listed above, is unchanged. `procedure_type`,
`format_type`, `columns` (on `journal_entry`-type `accounting_format`
objects) are untouched — only `accounting_rule`-type objects' `rules`
field is affected. A consumer that only reads full, short captions or
already treats `semantic_description` as advisory needs no changes.

**Where the removed/truncated content went:** same `extraction_debug/`
artifact as every M3.2 finding — `modules/copyright_sanitizer.py`'s new
`sanitize_content_blocks()` and `sanitize_visual_captions()` functions
follow the identical "strip in production, stash in debug, only for
records that actually had something removed" pattern as
`sanitize_equations()`/`sanitize_educational_objects()`.

**What remains open:** `evidence_span` (M3.1 §2.1 LOW) — still never
populated anywhere in this checkout, so there is nothing to sanitize yet.
Flagged for whoever wires it up to add it to `copyright_sanitizer.py` (or
`structural_validator._BANNED_PROSE_FIELD_NAMES`/`_ALLOWED_PROSE_FIELDS`)
at that time.

## 2.0.0 -> 3.0.0 — Milestone 3.2, Copyright-Safe Serialization

**Type:** MAJOR (fields removed — see below).

**What changed:** `modules/copyright_sanitizer.py` now runs as a
serialization-time gate in `pipeline.py` (right after Stage E validation
and Knowledge-Graph readiness enrichment, before the Compiler IR
registries and the production Chapter JSON are built). It implements the
HIGH-risk findings from the Milestone 3.1 audit. The following fields no
longer appear in the production Chapter JSON:

| Removed field | Was on | Replaced by |
|---|---|---|
| `equations[].raw_text` | `Equation` | `equations[].has_raw_text_hint` (bool) |
| `equations[].vlm_raw_output` | `Equation` | *(moved to `extraction_debug/` artifact; not replaced in production)* |
| `equations[].vlm_validation_errors` | `Equation` | *(moved to `extraction_debug/` artifact; not replaced in production)* |
| `educational_objects[].reusable_procedure` † | `EducationalObject` (`formula_or_procedure`) | `educational_objects[].procedure_step_count`, `.procedure_step_marker_types` |
| `educational_objects[].procedure_steps` † | `EducationalObject` (`formula_or_procedure`) | `educational_objects[].procedure_step_count`, `.procedure_step_marker_types` |
| `educational_objects[].reusable_syntax` † | `EducationalObject` (`programming_syntax`) | `educational_objects[].code_line_count`, `.has_code_content` |

† Only for objects whose `source == "deterministic"` (built by a
Recognizer's own `recognize()`). Objects whose `source == "vlm_fallback"`
already carry an already-paraphrased, word-capped `reusable_procedure`
(see `semantic_processor._enforce_word_cap`) and are **not** affected —
`reusable_procedure` can still legitimately appear in the Chapter JSON
for those objects.

**Why MAJOR, not MINOR:** per config.py's own SemVer policy, a field
rename/removal is MAJOR because a consumer written against the old
schema silently gets nothing back for that field instead of an error.
None of these fields were ever part of the frozen Pydantic contract
(`Equation`/`EducationalObject` are both `extra="allow"` — see
`schemas/canonical_base.py`), so no schema *class* changed, but the
*data* a consumer could previously read did.

**Backward compatibility:** every id/urn/page/bbox/confidence/provenance
field, and every field the M3.1 audit marked SAFE (§2.4) or LOW risk with
existing guardrails (§2.3), is completely unchanged. A Phase 2 consumer
that only reads those fields needs no changes. A consumer that was
specifically reading one of the removed fields will need to switch to
the new structural-metadata replacement, or (for `vlm_raw_output`/
`vlm_validation_errors`, which have no in-band replacement) read the
new `extraction_debug/` artifact instead — see
`extraction_debug/persistence.py`.

**Where the removed content went:** not deleted — every removed value is
still available, chapter-scoped, in the new `extraction_debug/` OneDrive
artifact folder (a sibling of `json_out/`, added to
`modules.json_writer._ARTIFACT_SUBFOLDERS`), written only for chapters
that actually had something to strip. See
`extraction_debug/persistence.py`'s module docstring. This is a
debug/audit-only artifact — never distribute or serve it the way the
Chapter JSON itself is served, since its entire purpose is to hold the
content the sanitizer determined was copyright-risky.

**What did NOT change in this milestone** (deferred, MEDIUM/LOW risk —
see `MILESTONE_3_2_SUMMARY.md`): `semantic_description` on
Activity/Box/Warning/Note/Example objects, `rules` on
`accounting_format` objects, table caption length, and `evidence_span`.

## 1.0.0 -> 2.0.0 — Phase A

`TopicNode.concepts` changed meaning from a list of human-readable
concept NAMES to a list of canonical concept IDs (same field name, same
`List[str]` shape — the "silent misinterpretation" case MAJOR exists
for). See `schemas/chapter_schema.py`'s `TopicNode.concepts` docstring
for the field-level detail.
