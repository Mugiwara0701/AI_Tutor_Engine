# Milestone 3.3 — Copyright-Safe Serialization, MEDIUM/LOW Findings

Implements the M3.1 audit findings Milestone 3.2 deliberately left open
(`MILESTONE_3_2_SUMMARY.md` §6, "Recommendations deferred to future
milestones"). No re-audit was performed; scope is exactly that deferred
list, minus `evidence_span` (never populated anywhere in this checkout,
so there is nothing yet to sanitize).

## 1. What changed

Three additions to the M3.2 checkpoint (`copyright_sanitizer.sanitize_*`
calls in `pipeline.py`, right after the existing M3.2
`sanitize_chapter_records()` call — same place in the pipeline, same
"after every legitimate deterministic reader has run, before the
Compiler IR/production JSON is built" ordering guarantee):

| M3.1 finding | Risk | Action taken |
|---|---|---|
| `semantic_description` (Activity/Box/Warning/Note/Example) | MEDIUM | `pipeline.py`'s `_finalize_blocks()` raw-truncation (`_enforce_word_cap(body[:200])`) is still computed, but the new `copyright_sanitizer.sanitize_content_blocks()` strips it from the production record and sets `semantic_description = ""` + `has_semantic_description_hint` (bool) — the same interim state Figures/Tables/Equations already have at Phase 1 |
| `rules` (`accounting_format`/`accounting_rule` objects) | MEDIUM | Replaced with structural metadata: `matched_rule_count`, `matched_rule_types` (per-line golden-rule *category* — `debit_receiver`/`credit_giver`/`debit_comes_in`/`credit_goes_out`/`debit_expenses_losses`/`credit_incomes_gains`/`other` — never the line's own words) |
| Table caption-only fallback | MEDIUM | Covered by the same length cap as the normal path (see next row) — the fallback path (`modules/layout_detector.py`'s "Table 3.2 ..." stub) produces a `caption` field with no separate code path from the normal one, so one fix covers both |
| Figure/table caption (normal path) | LOW | `copyright_sanitizer.sanitize_visual_captions()` caps `caption`/`title` on Figure/Diagram/Table records at `config.MAX_CAPTION_WORDS` (20), truncating in place |
| `evidence_span` | LOW | **Not implemented** — still never populated anywhere in this checkout; nothing to sanitize. Left flagged in this module's docstring for whoever populates it |

`_ALLOWED_PROSE_FIELDS` in `modules/structural_validator.py` (the
read-only second-gate WARNING check) now also tracks `caption`/`title`
against `MAX_CAPTION_WORDS`, so an overlong caption that somehow slips
past the sanitizer is still flagged, exactly like every other
AI-paraphrase-only field already is.

## 2. Design constraints satisfied (same as M3.2)

- **Deterministic:** every new function is a pure function of its input;
  no I/O, no VLM calls, no randomness. `sanitize_visual_captions()`
  deliberately reimplements `semantic_processor._enforce_word_cap`'s
  trivial "split, keep first N words, rejoin" logic locally rather than
  importing it, specifically to avoid pulling in `semantic_processor.py`'s
  unconditional `fitz`/`PIL` import chain into an otherwise
  dependency-free module.
- **Not silently discarded:** every stripped `rules`/`semantic_description`
  value, and every truncated `caption`/`title`'s original text, is moved
  to the same `extraction_debug/` artifact M3.2 introduced — via the same
  `SanitizeReport.debug_entries` shape, merged into the single
  `_copyright_debug_entries` list `pipeline.py` already threads through
  to `persist_extraction_debug()`. Nothing new was added to
  `extraction_debug/persistence.py` itself; it already accepted an
  arbitrary list of `{record_type, record_key, ...}` dicts.
- **Backwards compatible where practical:** `rules` was already outside
  the frozen Pydantic contract (`EducationalObject` is `extra="allow"`),
  same as every M3.2-removed field. `semantic_description` and
  `caption`/`title` are not removed, only narrowed — see MIGRATIONS.md
  for why that is still MAJOR, not silent. `SCHEMA_VERSION` bumped
  3.0.0 -> 4.0.0.
- **Existing compiler architecture unchanged:** no recognizer, no
  Stage A-E logic changed. `AccountingRuleRecognizer`,
  `content_blocks.py`'s detectors, and `layout_detector.py`'s caption
  logic are untouched — this milestone only adds a later sanitization
  step over their already-finished output, same as M3.2.
- **Same checkpoint, same object-identity guarantee:** `figures`/
  `diagrams`/`tables`/`activities`/`boxes`/`warnings_list`/`notes`/
  `examples` are reassigned to their sanitized versions at the M3.2
  checkpoint in `pipeline.py`, before `populate_registries()` and
  `assemble_chapter_json()` both read them — so, exactly like M3.2's
  `equations`/`educational_objects` reassignment, there is no second,
  unsanitized copy of any of these lists anywhere later in the function.

## 3. Files changed / added

**New:**
- `MILESTONE_3_3_SUMMARY.md` — this file.

**Modified:**
- `modules/copyright_sanitizer.py` — adds `sanitize_content_blocks()`,
  `sanitize_visual_captions()`, `_accounting_rule_type()` /
  `_accounting_rules_structural_metadata()`, `_enforce_word_cap_local()`;
  extends `sanitize_educational_objects()` to also handle
  `accounting_format`/`accounting_rule` objects' `rules` field.
- `pipeline.py` — extends the existing M3.2 checkpoint (right after the
  `sanitize_chapter_records()` call) with calls to the three new
  sanitizer functions over `activities`/`boxes`/`warnings_list`/`notes`/
  `examples`/`figures`/`diagrams`/`tables`, merging their debug entries
  into the same `_copyright_debug_entries` list already passed to
  `_persist_phase1_artifacts()`. `_finalize_blocks()` itself is
  unchanged (still computes the capped excerpt) — the sanitizer strips
  it back out downstream, same "read then sanitize" ordering as Stage E
  reading `reusable_procedure` before M3.2 strips it.
- `modules/structural_validator.py` — adds `caption`/`title` to
  `_ALLOWED_PROSE_FIELDS` (capped at `MAX_CAPTION_WORDS`).
- `config.py` — adds `MAX_CAPTION_WORDS = 20`; bumps `SCHEMA_VERSION` to
  `"4.0.0"` with a migration comment.
- `MIGRATIONS.md` — new 3.0.0 -> 4.0.0 entry.
- `tests/test_copyright_sanitizer.py` — adds
  `TestSanitizeAccountingRuleObjects`, `TestSanitizeContentBlocks`,
  `TestSanitizeVisualCaptions` (41 tests total in the file now, up from
  22).

## 4. Testing

Unlike M3.2's writeup, this sandbox had network access to PyPI, so
`pytest` and `pydantic` were installed and the real suite was run (not a
manual plain-Python re-run):

```
pytest tests/test_copyright_sanitizer.py -q   # 41 passed
pytest tests/test_structural_validator.py -q  # 91 passed
python -m py_compile pipeline.py modules/copyright_sanitizer.py \
    modules/structural_validator.py config.py  # OK
```

A manual integration check (an overlong figure `caption` fed through
`copyright_sanitizer.sanitize_visual_captions()` then through
`modules.structural_validator.validate_structural_completeness()`)
confirms the second gate's `prose_field_exceeds_word_cap` WARNING no
longer fires on the sanitizer's own output (only would fire if the
sanitizer's cap and the validator's cap ever drifted apart, since both
now read `config.MAX_CAPTION_WORDS`).

## 5. Recommendations still open

- **`evidence_span`** (LOW) — remains unpopulated and therefore
  unsanitized. Add it to `copyright_sanitizer.py` (or
  `structural_validator._BANNED_PROSE_FIELD_NAMES`/
  `_ALLOWED_PROSE_FIELDS`, depending on the shape whoever populates it
  chooses) at the point it's actually wired up, not before.
- **`reusable_syntax` product/legal sign-off** (M3.2 §2, still open) —
  `config.PRESERVE_CODE_SNIPPETS_VERBATIM` still defaults to `False`
  pending that decision; unrelated to this milestone's scope but noted
  here since it's the one remaining "decision needed, not just a code
  fix" item from the original audit.
- **Fuzzy/n-gram matching against source PDF text** — still explicitly
  out of scope for `structural_validator.py` (a read-only module that
  only ever sees `chapter_dict`, never the source PDF text) and still
  not attempted anywhere in `copyright_sanitizer.py` either (which only
  ever removes/caps by field
  name and length, never compares against the original page text). If
  ever built, belongs in Stage D/E where the source text is still in
  scope — noted again here since M3.3 does not change that boundary.
