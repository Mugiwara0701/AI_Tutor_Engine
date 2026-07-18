# modules/heading_recognizers

Deterministic heading recognition subsystem. Answers one narrow
question — _"is this line of source text a heading, and if so what
kind, at what level, with what confidence"_ — independent of PDF
parsing, layout detection, or VLM inference.

Status: **production, frozen** (as of M4.2E). See [Frozen interfaces](#frozen-interfaces).

## Milestone history

| Milestone | What it added                                                                                                                                                                                               |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M4.2A     | Framework: `HeadingRecognizer` base class, `RecognitionContext`/`RecognitionResult`, config, registry, factory, pipeline, enums, exceptions, utils. No concrete recognizer.                                 |
| M4.2B     | Generic, language-independent recognizers (§ [Recognizer catalog](#recognizer-catalog), first six).                                                                                                         |
| M4.2C     | Production integration into `modules/stage_b_classify.py` via the frozen public API only (`RecognitionPipeline`, `default_registry`, `RecognitionContext`, `RecognitionResult`, `HeadingRecognitionError`). |
| M4.2D     | Hindi and Sanskrit keyword recognizers (§ catalog, last two), plus Devanagari-numeral utilities in `utils.py`.                                                                                              |
| M4.2E     | Validation, edge-case hardening (see below), documentation, interface freeze. No new recognizers, no framework redesign.                                                                                    |

## Recognizer catalog

Registered on `default_registry` (via `default_factory`) in this order:

| Priority | `name`                  | Classification(s)                    | Matches                                    | Module                          |
| -------- | ----------------------- | ------------------------------------ | ------------------------------------------ | ------------------------------- |
| 5        | `chapter_number`        | `CHAPTER_NUMBER`                     | `Chapter 1`, `Unit 3`, `Lesson IV`         | `generic_recognizers.py`        |
| 10       | `hierarchical_heading`  | `HIERARCHICAL`                       | `1.1`, `2.3`, `4.5.2` (ASCII digits only)  | `generic_recognizers.py`        |
| 15       | `hindi_heading`         | `CHAPTER_NUMBER` / `SECTION_KEYWORD` | `अध्याय १`, `पाठ 5`, bare `सारांश`, ...    | `hindi_sanskrit_recognizers.py` |
| 16       | `sanskrit_heading`      | `CHAPTER_NUMBER` / `SECTION_KEYWORD` | `अध्यायः ३`, bare `उदाहरणम्`, ...          | `hindi_sanskrit_recognizers.py` |
| 20       | `numbered_heading`      | `NUMBERED`                           | bare `1`, `12`, `3)`                       | `generic_recognizers.py`        |
| 30       | `roman_numeral_heading` | `ROMAN_NUMERAL`                      | `I`, `IV`, `XIV`                           | `generic_recognizers.py`        |
| 40       | `alphabetic_heading`    | `ALPHABETIC`                         | `A`, `b)`, `(c)`                           | `generic_recognizers.py`        |
| 90       | `chapter_title`         | `CHAPTER_TITLE`                      | `The Living World` (structural heuristics) | `generic_recognizers.py`        |

Lower `priority` number = runs first / wins ties (see
[Priority & conflict resolution](#priority--conflict-resolution)).
`default_factory.registered_names()` / `default_registry.all_recognizers()`
are the source of truth if this table ever drifts from the code.

## Registration

A recognizer becomes part of the shared `default_registry` with exactly
one call in `modules/heading_recognizers/__init__.py`:

```python
default_factory.register_class(MyRecognizer.name, MyRecognizer)
```

`default_factory.build_registry(default_registry)` (called once, at
import time) then instantiates and registers every recognizer
registered with the factory. No other file needs to change — not
`base.py`, `config.py`, `registry.py`, `factory.py`, or `pipeline.py`.

## Priority & conflict resolution

`RecognizerRegistry.all_recognizers()` orders recognizers by
`(RecognizerSettings.priority ascending, registration order)` — this
is the single ordering the pipeline relies on, and it is deterministic
for a given registration sequence.

When more than one recognizer matches the same `RecognitionContext`
above its own confidence threshold, `RecognitionPipeline` resolves the
conflict per `HeadingRecognitionConfig.conflict_resolution`
(`HIGHEST_CONFIDENCE` by default — see `enums.ConflictResolutionStrategy`
for the other three strategies). Ties within a strategy fall back to
priority, then registration order — never non-deterministic.

## Confidence model

Every recognizer computes confidence via `utils.combine_confidence`
(multiplies independent [0,1] sub-scores, so any single weak signal
pulls the overall score down) and clamps via `utils.clamp_confidence`.
`RecognitionPipeline` compares the result against
`RecognizerSettings.confidence_threshold` (global default `0.5`,
overridable per recognizer via `HeadingRecognitionConfig`) — below
threshold is recorded as `NO_MATCH`, not a low-confidence win.

Rough calibration across the catalog (see each recognizer's own
`recognize()` for exact values):

- **~0.9–0.95** — unambiguous structural matches: `Chapter 1`,
  multi-letter Roman numerals, a numbered heading with its trailing
  marker, a Hindi/Sanskrit keyword _with_ a numeral.
- **~0.7–0.85** — plausible but weaker signals: chapter titles
  (structural heuristics only), a bare Hindi/Sanskrit keyword with no
  numeral.
- **~0.55–0.6** — genuinely ambiguous: a bare single Roman-numeral
  letter or bare single Latin letter (`"I"`, `"A"`) is intrinsically
  ambiguous with ordinary text.

Do not invent a new scoring algorithm for a new recognizer — reuse
`combine_confidence`/`clamp_confidence` so scores stay comparable
across the whole catalog.

## Extension mechanism (adding a recognizer)

1. Subclass `HeadingRecognizer` (`base.py`) in a new or existing
   module inside this package. Set `name`, `classification`,
   `default_priority`; implement `recognize()`; override `supports()`
   only as a cheap pre-filter if useful.
2. Reuse `utils.py` helpers (numeral parsing, whitespace/punctuation
   normalization, confidence combination) rather than reimplementing
   them.
3. Register with exactly one
   `default_factory.register_class(MyRecognizer.name, MyRecognizer)`
   call in `__init__.py`, and add the class to that module's imports
   and `__all__`.
4. Add unit tests following the existing per-recognizer suites
   (`tests/test_m42b_generic_recognizers.py`,
   `tests/test_m42d_hindi_sanskrit_recognizers.py`) as a template.

No change to `base.py`, `config.py`, `registry.py`, `factory.py`, or
`pipeline.py` should ever be required just to add a recognizer.
`enums.HeadingClassification` may gain a new member (additive only —
see that enum's own docstring) if a genuinely new heading _kind_ is
introduced; this is the one framework file a new recognizer family
may reasonably touch, and only ever additively.

## Expected metadata

A `RecognitionResult` (see `base.py`) always carries:

- `recognizer_name`, `classification`, `confidence` (required)
- `level` — 1-based (1 = chapter, 2 = section, ...), or `None` if the
  recognizer only classifies without ranking
- `number` — the canonical numbering token as a string (ASCII digits
  for any recognizer that resolves a numeral, regardless of which
  digit system the source text used), or `None`
- `title` — the recognizer's best display text, or `None`
- `metadata` — recognizer-specific extras (e.g. `{"keyword": ...}`,
  `{"integer_value": ...}`); consumers must treat unknown keys as
  opaque
- `diagnostics` — human-readable strings explaining the match; for
  logging/debugging only, never parsed by a caller

Stage B's own integration (`modules/stage_b_classify.py`,
`_recognize_heading`) is unchanged by M4.2D/M4.2E and continues to
consume only this shape.

## Supported heading formats & numeral systems

- English: `Chapter N` / `Unit N` / `Lesson N`, bare/hierarchical
  Arabic numbering, Roman numerals, single-letter markers, structural
  chapter titles.
- Hindi: अध्याय, पाठ, परिचय, अभ्यास, गतिविधि, उदाहरण, प्रश्न,
  प्रश्नावली, परियोजना, सारांश, निष्कर्ष, टिप्पणी — numbered or bare.
- Sanskrit: अध्यायः, पाठः, अभ्यासः, उदाहरणम्, प्रश्नाः, गतिविधिः,
  सारांशः — numbered or bare.
- Numeral systems: Arabic (0-9) and Devanagari (०-९), resolved to a
  canonical ASCII-digit `RecognitionResult.number` via
  `utils.normalize_numeral`. `hierarchical_heading` (`1.2.3`-style)
  and `chapter_number`'s English keywords are ASCII-digit only by
  design — see `hindi_sanskrit_recognizers.py`'s module docstring for
  the one explicitly out-of-scope combination (`"Chapter ५"`).

## M4.2E validation & hardening notes

Full edge-case sweep (empty/whitespace-only text, malformed numbering,
duplicate numbering, OCR-style spacing/punctuation variation, mixed
languages/numeral systems within one token, unexpected symbols,
non-string `RecognitionContext.text`) — see
`tests/test_m42e_validation_hardening.py`. Two real bugs were found
and fixed as part of this milestone (both are narrow, behavior-only
fixes — no interface changed):

1. **`hierarchical_heading`'s segment regex accepted Devanagari
   digits.** Python's bare `\d` in a compiled `str` pattern is
   Unicode-aware, so a purely-Devanagari token like `"१.२.३"` was
   incorrectly matched as a _generic_ hierarchical heading (which is
   explicitly documented as ASCII-only / language-independent),
   producing a `number` field that was never converted to a canonical
   digit form. Fixed by restricting the segment pattern to `[0-9]`.
2. **`RecognitionPipeline.run()` did not guard `supports()`.**
   `recognize()` calls were already protected by
   `HeadingRecognizer.safe_recognize()`, but an exception raised by
   `supports()` (e.g. from a malformed/non-`str` `RecognitionContext.text`)
   propagated out of `run()` and aborted the _entire_ pipeline run for
   every recognizer — silently breaking the framework's own documented
   "one misbehaving recognizer can't take a run down" guarantee. Fixed
   by wrapping the `supports()` call the same way, recording a
   `FAILED` `AttemptRecord` for that recognizer only.

Also tightened (performance only, no behavior change for any valid
input): `roman_numeral_heading`'s `supports()` pre-filter now checks
ASCII-alphabetic text specifically, instead of Unicode-aware
`.isalpha()`, avoiding a wasted `recognize()` call on non-Latin
alphabetic text that could never be a Roman numeral anyway.

## Frozen interfaces

As of M4.2E, the following are considered **frozen** — future
milestones build on them rather than change them:

- `HeadingRecognizer` (abstract interface: `name`, `classification`,
  `default_priority`, `recognize()`, `supports()`, `safe_recognize()`)
- `RecognitionContext`, `RecognitionResult`, `FailureResult`,
  `ConfidenceInfo` (shapes and field semantics)
- `RecognizerRegistry` / `RecognizerFactory` public methods
- `RecognitionPipeline.run()` and `PipelineResult`/`AttemptRecord`
  shapes
- `HeadingRecognitionConfig` / `RecognizerSettings` shapes and
  `settings_for()` defaulting behavior
- `HeadingClassification`, `ConflictResolutionStrategy`,
  `RecognizerState`, `RecognitionOutcome` — existing members are
  frozen; `HeadingClassification` may still gain new members
  additively (see [Extension mechanism](#extension-mechanism-adding-a-recognizer))
- The exception hierarchy in `exceptions.py`

Internal, non-public implementation details (private regexes, helper
functions prefixed `_`, a recognizer's internal normalization order)
are not frozen and may still be hardened/optimized without notice, as
long as observable behavior (match/no-match, confidence, metadata) for
any currently-passing test input does not change.
