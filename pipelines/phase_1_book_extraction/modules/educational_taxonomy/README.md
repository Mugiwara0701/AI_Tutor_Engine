# `modules.educational_taxonomy` — M5.2A: Universal Educational Taxonomy

Taxonomy-only milestone. Defines the canonical, curriculum-independent
educational ontology every educational object in every subject belongs
to: seven top-level categories, and a built-in catalog of concrete
object types (Concept, Definition, Theorem, Proof, Figure, Table, MCQ,
Poem, ...). **No educational object is processed here** — no
extraction, no recognition, no classification logic, no subject-specific
types. See "Out of scope" below.

This package is a sibling to `modules.educational_object_framework`
(M5.1, frozen), `modules.heading_recognizers` (M4.2), and
`modules.heading_canonicalization` (M4.3) — it mirrors their module
layout and design philosophy (str-backed `Enum`s, frozen dataclasses,
a small stateful registry plus a module-level default instance,
`with_*` immutable-update helpers) without importing from or depending
on any of them.

## Why this exists

M5.1 answers *"how should a recognized educational object be
processed?"* — but deliberately leaves `ProcessingContext.object_type`
generic, an unconstrained free-form string. M5.2A answers the question
that leaves open: *"what are the valid kinds of educational object in
the first place, and what higher-level category does each belong to?"*
This is the fixed, universal vocabulary every later milestone —
subject profiles (M5.2B), structural/semantic/relationship engines
(M5.2C–E), and concrete M5.2 processors — classifies objects into,
instead of each independently inventing its own type strings.

## Architecture

```
modules/educational_taxonomy/
├── __init__.py    Public API surface (re-exports everything below)
├── enums.py         EducationalCategory — the 7 fixed top-level
│                     categories; no object-kind or subject name
├── exceptions.py     Exception hierarchy, rooted at
│                     EducationalTaxonomyError — separate from
│                     EducationalObjectFrameworkError (M5.1); a
│                     taxonomy lookup/registration problem is a
│                     different concern from a processing failure
├── models.py          EducationalObjectType — one immutable,
│                     versioned catalog entry (key, category,
│                     display_name, description, aliases, version)
├── registry.py         TaxonomyRegistry (+ default_taxonomy) —
│                     registration, uniqueness enforcement (key AND
│                     alias, across the whole registry), lookup,
│                     deterministic ordering
├── catalog.py           The built-in canonical object types from
│                     the M5.2A spec, grouped by category — pure
│                     data, registered into default_taxonomy at
│                     import time via seed()
└── validation.py        validate_taxonomy() — taxonomy integrity
                        checks, returning M5.1's own ValidationResult
                        rather than a parallel type
```

## The seven categories

`EducationalCategory` is a fixed, closed vocabulary — a structural
classification of *kind of educational content*, independent of
subject or curriculum:

| Category      | Example object types (built-in)                          |
|----------------|-----------------------------------------------------------|
| Knowledge      | Concept, Definition, Fact, Law, Theorem, Axiom, Corollary  |
| Reasoning      | Proof, Derivation, Explanation, Worked Example             |
| Visual         | Figure, Diagram, Graph, Timeline, Mind Map                 |
| Structured     | Table, Matrix, Comparison, Classification, List            |
| Learning       | Activity, Experiment, Exercise, Summary, Important Box      |
| Assessment     | MCQ, Assertion-Reason, Fill in the Blanks, HOTS, Case Study |
| Language       | Story, Poem, Dialogue, Grammar Rule, Verse, Stanza          |

Every `EducationalObjectType` belongs to **exactly one** category —
the taxonomy is a strict partition, not a multi-category tagging
scheme. Deliberately absent from `catalog.py`: any subject-specific
type (`PhysicsObject`, `MathObject`, `HistoryObject`, ...) — those
belong to M5.2B (Subject Profile Framework), which maps subject
concerns onto this same taxonomy rather than extending or subclassing
it.

## Identity, uniqueness, and aliases

An `EducationalObjectType`'s identity is its `key` — a canonical,
lowercase snake_case string (`"concept"`, `"worked_example"`,
`"assertion_reason"`) — never its `display_name`, which is purely
presentational. `TaxonomyRegistry` enforces uniqueness of every `key`
*and* every `alias` across the whole registry: an alias cannot collide
with another entry's key or alias, and `get()` resolves either form to
the same canonical entry. This lets a future recognizer that emits a
slightly different string for the same concept (e.g.
`"worked_problem"` instead of `"worked_example"`) register that string
as an alias without the taxonomy growing a second, ambiguous entry.

## Extensibility

Adding a new object type — whether a future built-in addition to this
package or a subject-specific one from M5.2B — requires no change to
`models.py`, `registry.py`, or any existing entry:

```python
from modules.educational_taxonomy import EducationalCategory, EducationalObjectType, register

register(EducationalObjectType(
    key="lemma",
    category=EducationalCategory.KNOWLEDGE,
    display_name="Lemma",
    description="A proposition established chiefly to support a larger theorem.",
))
```

`TaxonomyRegistry.register()` validates the entry and enforces
key/alias uniqueness at registration time; every read method
(`all_types()`, `types_by_category()`, `categories()`) picks it up on
the next call — no registry-internal change required.

## Versioning and serialization

Every `EducationalObjectType.version` is a plain `"MAJOR.MINOR.PATCH"`
string (default `"1.0.0"`), mirroring this repository's existing
`schema_version` convention (`schemas/canonical_base.py`,
`schemas/chapter_schema.py`) rather than inventing a new versioning
scheme. `EducationalObjectType.to_dict()` produces a fixed-field-order,
JSON-safe representation; `TaxonomyRegistry.all_types()` always orders
entries by `(category.value, key)` regardless of registration order —
so serializing the whole taxonomy is deterministic across runs,
processes, and import order.

## Integration with M5.1

This package does **not** duplicate M5.1's `ProcessingContext`,
`ProcessingPipeline`, `ProcessorRegistry`, or configuration mechanism —
it has no processing concern at all; a taxonomy entry has no lifecycle
state, no priority, and nothing to execute. The one concrete
integration point is `validation.py`, which imports and reuses M5.1's
own `ValidationResult` / `ValidationDiagnostic` / `DiagnosticSeverity`
contracts for the taxonomy's own integrity checks (duplicate keys,
categories with zero registered types, non-deterministic
serialization) instead of defining a parallel validation shape.

## Out of scope

Per the M5.2A spec, none of the following is implemented in this
package — all belong to M5.2B or later:

- Subject Profiles (`PhysicsObject`, `MathObject`, ... or any
  subject-specific mapping onto this taxonomy)
- Structural Understanding, Semantic Enrichment, Relationship
  Discovery, Copyright-Safe Normalization
- Any concrete educational object processor (equation extraction,
  figure/table/diagram handling, ...)
- Cross-object validation (validating a concrete extracted object
  instance against its declared type)
- Production integration (wiring this taxonomy into
  `modules/stage_b_classify.py`, `book_orchestrator.py`, or the wider
  pipeline)
- Master JSON / Teacher Brain generation, DST or Knowledge Graph
  integration, LLM integration

## Testing

See `tests/test_m52a_universal_educational_taxonomy.py` for taxonomy
unit tests (enums, exceptions, models, registry, built-in catalog,
validation, extensibility) and confirmation that
`modules.educational_object_framework` (M5.1) remains importable and
untouched by this package.
