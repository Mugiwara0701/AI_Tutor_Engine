# Chapter JSON schema migrations

Tracks `config.SCHEMA_VERSION` (MAJOR.MINOR.PATCH, per config.py's own
policy comment) history for the exported Chapter JSON
(`schemas/chapter_schema.py: ChapterJSON`).

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
