# M5.2C — Structural Understanding Engine

## Philosophy

M5.2A gave every educational object type a place in a universal taxonomy.
M5.2B let a subject profile attach forward-looking metadata to a
taxonomy entry — including free-form `Mapping[str, Any]` hint fields
nobody had yet built a consumer for. M5.2C is the first consumer.

Structural understanding answers one narrow question: **given an
educational object that claims to be a "Worked Example" (or an
Experiment, a Proof, a Derivation, a Definition, a Figure, a Table),
does it actually have the parts a thing of that shape is supposed to
have?** It does not ask what those parts *mean* (semantic enrichment,
M5.2D), how they *relate* to other objects (relationship discovery,
M5.2E), whether their content is *copyright-safe*, or invoke an LLM to
find out. It is deliberately the most boring, most deterministic layer
in the stack — a shape-checker, not an understanding engine in the
colloquial sense.

## Engine architecture

```
SubjectContribution (M5.2B, frozen)
        │  raw Mapping[str, Any] hint fields
        ▼
   HintResolver  ──────────────────────────►  ResolvedHints
                                               (ProcessingHints, RecognitionHints,
                                                StructuralHints, ValidationHints,
                                                RelationshipHints)
        │
        │                     StructuralPatternRegistry
        │                     (worked_example, experiment, proof,
        │                      derivation, definition, figure, table)
        ▼                              │
StructuralObject  ───────────────►  StructuralUnderstandingEngine.analyze()
(caller-supplied content,                     │
 opaque to this package)                      ▼
                                    StructuralAnalysisResult
                                    (present/missing roles,
                                     M5.1 ValidationResult)

TaxonomyRegistry (M5.2A, frozen) ──► CompatibilityValidator ──► ProfileActivationManager
                                                                 (REGISTERED → VALIDATED
                                                                  → ACTIVE → INACTIVE →
                                                                  UNREGISTERED)
```

Every arrow above is a read, never a write, into a frozen package.

## The Typed Hint System

`SubjectContribution` carries five raw `Mapping[str, Any]` hint
fields. M5.2C never processes a raw mapping directly outside
`HintResolver` — everywhere else in this package, code operates on one
of five immutable, versioned, JSON-serializable dataclasses:

| Typed model         | Backed by                                             |
|----------------------|--------------------------------------------------------|
| `ProcessingHints`    | `processing_hints` (minus a nested `"recognition"` key) |
| `RecognitionHints`   | `processing_hints["recognition"]` (a nested sub-mapping) |
| `StructuralHints`    | `structural_hints`                                      |
| `ValidationHints`    | `validation_hints`                                       |
| `RelationshipHints`  | `relationship_hints`                                     |

`semantic_hints` is deliberately never resolved into a typed model —
semantic enrichment is out of scope for this milestone; whichever
milestone implements it can add a `SemanticHints` model of its own
without touching anything here.

Each typed model recognizes a small set of well-known keys as named,
typed fields, and preserves every other key verbatim in its own
`extra` mapping — nothing is ever silently dropped.

## HintResolver

`HintResolver.resolve(contribution) -> ResolvedHints` is a pure
function and the **only** place in M5.2C that reads a
`SubjectContribution`'s raw hint mappings. It never mutates its input
and never writes a resolved hint back onto `SubjectContribution` —
typed hints live only on `ResolvedHints` instances that M5.2C code
constructs fresh, on demand.

## Taxonomy Compatibility

`TaxonomyCompatibility` is an M5.2C-owned declaration of which
`EducationalObjectType.version` range (M5.2A) this engine deployment
supports (`supported_taxonomy_version`, `minimum_supported_version`,
`maximum_supported_version`). `CompatibilityValidator` wraps a
`TaxonomyRegistry` — resolving a key via its own, unmodified `get()` —
and reports an M5.1 `ValidationResult` for a single object type or an
entire `SubjectProfile`. `EducationalObjectType` and `TaxonomyRegistry`
are never subclassed, monkeypatched, or extended with new methods.

## Subject Profile Lifecycle

```
REGISTERED ──validate()──► VALIDATED ──activate()──► ACTIVE ──deactivate()──► INACTIVE
     ▲                          │                                                │
     └───(validation fails)─────┘                                    reactivate()│
                                                                                  ▼
                                                                              ACTIVE
                                                                                  │
                                                                          unregister()
                                                                                  ▼
                                                                           UNREGISTERED (terminal)
```

`ProfileActivationManager` tracks this lifecycle entirely outside
`SubjectProfile` / `SubjectProfileRegistry` (both frozen, M5.2B,
neither modified). `activate()` requires the profile's most recent
`validate()` call to have succeeded against a `CompatibilityValidator`;
`reactivate()` re-runs that check, since a profile may have drifted
while inactive.

## Relationship with M5.2A

M5.2C reads `EducationalObjectType` and `TaxonomyRegistry` exactly as
M5.2A defines them, exclusively through `compatibility.py`. No new
category, no new object type, no new registry method.

## Relationship with M5.2B

M5.2C reads `SubjectContribution` and `SubjectProfile` exactly as
M5.2B defines them. The one thing M5.2B left unimplemented — turning
its own free-form hint mappings into something usable — is what
`HintResolver` now does, entirely as an M5.2C-owned layer beside the
frozen models, never inside them.

## Preparation for M5.2D

M5.2D (Semantic Enrichment) can build directly on this milestone's
outputs without any change here:

- `StructuralAnalysisResult` already tells a semantic processor which
  components of an object are present, so it never needs to
  re-discover structure itself.
- `ResolvedHints.processing` / `.recognition` are already typed and
  ready to consume.
- The `semantic_hints` raw field is still there, untouched, waiting
  for M5.2D's own `SemanticHints` model and resolver — this package
  does not claim that territory.

## Out of Scope

Semantic enrichment, relationship discovery, knowledge graph
integration, DST integration, copyright normalization, Master JSON
generation, LLM integration.
