# `modules.educational_object_framework` — M5.1: Educational Object Framework

Framework-only milestone. Establishes the architecture, models,
interfaces, registry, pipeline, and validation contracts for
processing recognized educational objects (equations, figures,
tables, diagrams, examples, activities, definitions, glossary
entries, ...). **No object-specific processor is implemented here** —
no equation extraction, no figure/table/diagram handling, no example/
activity/definition/glossary processing, no cross-object validation.
See "Out of scope" below.

This package mirrors the module layout, naming conventions, and
design philosophy of `modules.heading_recognizers` (M4.2) and
`modules.heading_canonicalization` (M4.3) — both frozen, both
read-only references for this milestone. Reading either package's own
docstrings first will make everything here immediately familiar. This
package does not import from or depend on either of them; the mirror
is architectural style only.

## Why this exists

M4 (frozen) answers *"what heading is this, and what is its canonical
form?"* for a document's structural skeleton (chapters, sections,
subsections).

M5 answers a different question for the **content** that skeleton
organizes: *"given a recognized educational object, how should it be
processed?"* M5.1 builds only the **scaffolding** for that question —
the same "framework first, concrete logic later" shape M4.2A and
M4.3A each followed for the heading subsystem. The actual
object-specific processing logic (M5.2: an EquationProcessor,
FigureProcessor, TableProcessor, DiagramProcessor, ExampleProcessor,
ActivityProcessor, DefinitionProcessor, GlossaryProcessor, and
whatever cross-object validation follows) plugs into this scaffolding
without changing it.

## Architecture

```
modules/educational_object_framework/
├── __init__.py       Public API surface (re-exports everything below)
├── enums.py           Shared vocabularies (ProcessorState,
│                       ProcessingOutcome, DiagnosticSeverity) — no
│                       enum names any specific educational object kind
├── exceptions.py       Exception hierarchy, rooted at
│                       EducationalObjectFrameworkError
├── models.py            ProcessingResult — the immutable result a
│                       processor reports
├── validation.py        ValidationDiagnostic / ValidationResult —
│                       validation contracts (no rules)
├── base.py              ProcessingContext, ProcessingFailure, and the
│                       EducationalObjectProcessor extension interface
├── config.py             ProcessorSettings, EducationalObjectFrameworkConfig
├── registry.py           ProcessorRegistry (+ default_registry)
└── pipeline.py           ProcessingPipeline, AttemptRecord,
                         ProcessingPipelineResult
```

Every module is a direct structural counterpart to a module in
`modules/heading_canonicalization/` (itself a counterpart to
`modules/heading_recognizers/`):

| heading_canonicalization           | educational_object_framework      | Role                                   |
|-------------------------------------|-------------------------------------|-----------------------------------------|
| `enums.py`                          | `enums.py`                          | shared vocabularies                     |
| `exceptions.py`                     | `exceptions.py`                     | exception hierarchy                     |
| `base.CanonicalizationContext`      | `base.ProcessingContext`            | shared execution context                |
| `base.CanonicalizationFailure`      | `base.ProcessingFailure`            | recorded step failure                   |
| `base.HeadingCanonicalizer`         | `base.EducationalObjectProcessor`   | extension interface                     |
| `models.CanonicalHeading`           | `models.ProcessingResult`           | the payload (see note below — asymmetric) |
| `config.py`                         | `config.py`                         | immutable, per-component settings       |
| `registry.py`                       | `registry.py`                       | registration + lifecycle + ordering     |
| `pipeline.py`                       | `pipeline.py`                       | deterministic orchestration             |
| `validation.py`                     | `validation.py`                     | validation contracts (no rules)         |

**Note on the one deliberate asymmetry:** in `heading_canonicalization`,
`CanonicalHeading` is the *evolving payload itself* — one heading
flows through every enabled canonicalizer in sequence, and each one
may progressively enrich it (canonicalizers **cooperate** on a shared,
mutating payload). This framework cannot do that: M5.1 has no
concrete educational object type to progressively enrich (the spec is
explicit that `ProcessingContext` "should not assume any specific
object", and object-specific processors are M5.2's job). So here,
`ProcessingContext.current_object` stays whatever an upstream stage
put there — generic, opaque, never mutated by this framework — and
each processor instead produces its own `ProcessingResult`, a
*report* about that object rather than a replacement for it.
`ProcessingPipeline` therefore **aggregates** every processor's report
against the same context, rather than threading a mutated payload
through the chain — processors **coexist**, each reporting
independently, closer in shape to how `RecognitionPipeline` runs every
recognizer against the same input, but collecting every result instead
of picking one winner. See `pipeline.py`'s own docstring for the full
rationale.

## Pipeline flow

```
ProcessingContext(current_object=..., object_type=..., ...)
        │
        ▼
ProcessingPipeline.run(context)
        │
        ├─ for each enabled processor, in priority order:
        │     supports(context)?
        │       ├─ raises            → AttemptRecord(FAILED)
        │       ├─ False              → AttemptRecord(SKIPPED)
        │       └─ True  → safe_process(context)
        │                    ├─ raises (wrapped)  → AttemptRecord(FAILED)
        │                    ├─ returns None        → AttemptRecord(NO_RESULT)
        │                    └─ returns ProcessingResult → AttemptRecord(EXECUTED, result=...)
        │
        ▼
ProcessingPipelineResult(context, attempts=(...))
    .results               — every ProcessingResult produced
    .successful_results    — the subset also reporting success=True
    .failures               — every ProcessingFailure recorded
```

One processor raising, or failing its `supports()` check, never stops
the run — every other enabled processor still gets a chance to run
against the same context (M5.1 spec: "the pipeline must never stop
because one processor fails").

## Extension mechanism (for M5.2)

Adding a concrete processor requires no change to this package:

```python
from modules.educational_object_framework import (
    EducationalObjectProcessor, ProcessingContext, ProcessingResult, register,
)

class EquationProcessor(EducationalObjectProcessor):
    name = "equation_processor"
    default_priority = 100

    def supports(self, context: ProcessingContext) -> bool:
        return context.object_type == "equation"

    def process(self, context: ProcessingContext) -> ProcessingResult | None:
        # M5.2's own extraction/normalization logic goes here.
        ...

register(EquationProcessor())
```

`ProcessorRegistry` validates the processor at registration time,
assigns it its configured (or default) priority, and
`ProcessingPipeline` picks it up automatically on the next `run()` —
no registry, pipeline, or context change required.

## Configuration

Reuses this repository's existing per-package configuration approach
(the same one `heading_recognizers/config.py` and
`heading_canonicalization/config.py` each already use) rather than
introducing a second configuration mechanism: an immutable,
dataclass-based `EducationalObjectFrameworkConfig` carrying
per-processor `ProcessorSettings` (enabled / priority / extra), looked
up by processor name, with a sensible zero-configuration default for
any processor that has none set explicitly.

## Out of scope

Per the M5.1 spec, none of the following is implemented in this
package — all belong to M5.2 or later:

- Equation, Figure, Table, Diagram, Example, Activity, Definition, or
  Glossary processing logic
- Cross-object validation rules
- Production integration (wiring this framework into
  `modules/stage_b_classify.py` or the wider pipeline)
- Document Structure Tree / Knowledge Graph integration

## Testing

See `tests/test_m51a_educational_object_framework.py` for framework
unit tests (models, context, registry, pipeline, public API) and
confirmation that the M4 heading-subsystem tests (`test_m42*`,
`test_m43*`) continue to pass unmodified.
