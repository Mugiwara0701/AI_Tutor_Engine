# `modules.heading_canonicalization` — M4.3A: Heading Canonicalization Framework

Framework-only milestone. Establishes the architecture, models,
interfaces, registry, pipeline, and validation contracts for turning a
recognized heading (M4.2 output) into a stable internal
representation, ready for deterministic normalization in later M4.3
milestones. **No concrete canonicalization logic is implemented
here** — no Roman/Arabic/Devanagari numeral conversion, no title
normalization, no structural validation rules. See "Out of scope"
below.

This package is the direct architectural sibling of
`modules.heading_recognizers` (M4.2A-E), one stage downstream, and
deliberately mirrors its module layout, naming conventions, and
design philosophy module-for-module. Reading that package's own
docstrings first will make everything here immediately familiar.

## Why this exists

M4.2 answers: *"is this line of text a heading, and if so what kind
and what level?"* — producing a `RecognitionResult` per heading.

M4.3 answers the next question: *"given a recognized heading, what is
its stable, canonical internal shape — normalized numbering, resolved
type, validated structure — that the rest of the pipeline (Document
Structure Tree, Compiler, ...) can consume without caring how the
heading was originally recognized?"*

M4.3A builds only the **scaffolding** for that second question. The
actual normalization logic (M4.3B: Number System Canonicalization,
and whatever milestones follow it for title normalization and
structural validation) plugs into this scaffolding without changing
it.

## Architecture

```
modules/heading_canonicalization/
├── __init__.py       Public API surface (re-exports everything below)
├── enums.py           Shared vocabularies (CanonicalHeadingType,
│                       NumberingSystem, ValidationStatus,
│                       ValidationSeverity, CanonicalizerState,
│                       CanonicalizationOutcome)
├── exceptions.py       Exception hierarchy, rooted at
│                       HeadingCanonicalizationError
├── models.py           CanonicalHeading — the canonical heading model
├── validation.py       ValidationDiagnostic / ValidationResult —
│                       validation contracts (no rules)
├── base.py             CanonicalizationContext, CanonicalizationFailure,
│                       and the HeadingCanonicalizer extension interface
├── config.py           CanonicalizerSettings, HeadingCanonicalizationConfig
├── registry.py         CanonicalizerRegistry (+ default_registry)
└── pipeline.py         CanonicalizationPipeline, AttemptRecord,
                        CanonicalizationPipelineResult
```

Every module is a direct structural counterpart to a module in
`modules/heading_recognizers/`:

| heading_recognizers      | heading_canonicalization         | Role                                   |
|---------------------------|-----------------------------------|-----------------------------------------|
| `enums.py`                | `enums.py`                        | shared vocabularies                     |
| `exceptions.py`           | `exceptions.py`                   | exception hierarchy                     |
| `base.RecognitionContext` | `base.CanonicalizationContext`    | shared execution context                |
| `base.FailureResult`      | `base.CanonicalizationFailure`    | recorded step failure                   |
| `base.HeadingRecognizer`  | `base.HeadingCanonicalizer`       | extension interface                     |
| `base.RecognitionResult`  | `models.CanonicalHeading`         | the payload itself (see note below)     |
| `config.py`                | `config.py`                       | immutable, per-component settings       |
| `registry.py`              | `registry.py`                     | registration + lifecycle + ordering     |
| `pipeline.py`              | `pipeline.py`                     | deterministic orchestration             |
| —                          | `validation.py`                   | new: validation contracts (M4.3-only)   |

**Note on the one deliberate asymmetry:** in `heading_recognizers`,
`RecognitionResult` is a *transient output* — many recognizers each
produce their own candidate result against the *same* input, and the
pipeline picks a winner (recognizers **compete**). In
`heading_canonicalization`, `CanonicalHeading` is the *evolving
payload itself* — one heading flows through every enabled
canonicalizer in sequence, and each one may progressively enrich it
(canonicalizers **cooperate**). This is why `CanonicalizationPipeline`
threads a single heading through its loop and returns one
`output_heading`, rather than collecting `matches`/`winners` the way
`RecognitionPipeline` does.

## Pipeline flow

```
CanonicalHeading.from_recognition(context, result)
        │
        ▼
CanonicalizationPipeline.run(heading, context) ──▶ for each enabled
        │                                           canonicalizer, in
        │                                           priority order:
        │
        │   supports(heading, ctx)?  ──No──▶ record SKIPPED, continue
        │            │Yes
        │            ▼
        │   safe_canonicalize(heading, ctx)
        │            │
        │     raises?  ──Yes──▶ record FAILED, continue (heading unchanged)
        │            │No
        │            ▼
        │   returns None?  ──Yes──▶ record UNCHANGED, continue
        │            │No (returns an updated CanonicalHeading)
        │            ▼
        │   record APPLIED; heading := updated result
        ▼
CanonicalizationPipelineResult(input_heading, output_heading, attempts=[...])
```

A misbehaving canonicalizer never aborts the run — it is recorded as
a `FAILED` `AttemptRecord` and the heading carries forward unchanged
into the next canonicalizer, mirroring
`RecognitionPipeline`'s own resilience contract.

## Extension mechanism

A future canonicalizer needs to do exactly two things:

1. Implement `base.HeadingCanonicalizer`:

   ```python
   class RomanNumeralCanonicalizer(HeadingCanonicalizer):
       name = "roman_numeral_canonicalizer"

       def supports(self, heading, context) -> bool:
           return heading.canonical_number is None  # don't redo work

       def canonicalize(self, heading, context):
           if heading.recognized_classification != HeadingClassification.ROMAN_NUMERAL:
               return None  # not this canonicalizer's concern
           value = roman_to_int(heading.original_numbering)
           if value is None:
               return None
           return heading.with_updates(
               canonical_number=str(value),
               numbering_system=NumberingSystem.ROMAN,
           )
   ```

2. Register one instance into `default_registry` (typically from this
   package's `__init__.py`, one `register(...)` call per
   canonicalizer — the same convention `heading_recognizers/__init__.py`
   uses for its own recognizer family).

Nothing in `base.py`, `config.py`, `registry.py`, or `pipeline.py`
needs to change. This is exactly M4.3A's "extension without
modification" objective.

Expected future extension points (M4.3B and later):

- `RomanNumeralCanonicalizer`
- `ArabicNumeralCanonicalizer`
- `DevanagariNumeralCanonicalizer`
- a title normalizer (populates `CanonicalHeading.normalized_title`)
- a structural validator (produces a `validation.ValidationResult` and
  applies its `.status` to `CanonicalHeading.validation_status`)

## Expected inputs / outputs

**Input:** a `heading_recognizers.base.RecognitionContext` plus the
`RecognitionResult` it produced (e.g.
`RecognitionPipeline.run(context).winner`), adapted via
`CanonicalHeading.from_recognition(context, result)`.

**Output of M4.3A's own pipeline, today:** a `CanonicalHeading` with
every M4.2-sourced field populated (`original_text`,
`recognized_classification`, `recognized_confidence`, `level`,
`original_numbering`, `original_language`) and every canonicalization
placeholder still at its default (`canonical_type=None`,
`canonical_number=None`, `numbering_system=UNKNOWN`,
`normalized_title=None`, `validation_status=PENDING`) — because no
canonicalizer is registered yet. Once M4.3B (and later milestones)
register canonicalizers into `default_registry`, the exact same
pipeline call starts returning a `CanonicalHeading` with those
placeholders actually filled in. **No M4.3A code needs to change for
that to happen.**

## Lifecycle

1. Stage B (or a test) obtains a `RecognitionContext` +
   `RecognitionResult` from `heading_recognizers`.
2. `CanonicalHeading.from_recognition(...)` builds the initial,
   placeholder-only `CanonicalHeading`.
3. `CanonicalizationPipeline(default_registry).run(heading, context)`
   threads it through every enabled canonicalizer.
4. `CanonicalizationPipelineResult.output_heading` is the final,
   (eventually) canonicalized heading; `.attempts` is the full audit
   trail of what ran and what it did.

## Out of scope (M4.3A)

Per the milestone spec, none of the following are implemented in this
package yet:

- Roman / Arabic / Devanagari numeral conversion
- Title normalization, Unicode normalization, OCR cleanup
- Sequence validation, duplicate detection, hierarchy validation
- Stage B integration, Document Structure Tree integration,
  educational object extraction
- Any redesign of the M4.2 heading recognition framework (untouched —
  see the top-level deliverables list for confirmation)

These belong to M4.3B and later.
