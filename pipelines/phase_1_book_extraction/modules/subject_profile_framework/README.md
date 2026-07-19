# `modules.subject_profile_framework` — M5.2B: Subject Profile Extension Framework

Extends the frozen M5.2A Universal Educational Taxonomy
(`modules.educational_taxonomy`) with subject-specific educational
object types, metadata, validation, and capability-based queries —
without modifying, subclassing, or redesigning any part of that frozen
package.

## Why this package exists, and why it looks the way it does

The M5.2B spec, as originally written, assumed M5.2A had already
shipped richer `EducationalObjectType` metadata (symbolic content,
copyright sensitivity, structural/semantic/relationship support) and a
capability-based query API on `TaxonomyRegistry`. Inspection of the
actual, frozen M5.2A implementation
(`modules/educational_taxonomy/models.py`,
`modules/educational_taxonomy/registry.py`) confirmed neither exists:
`EducationalObjectType` has exactly six fields (`key`, `category`,
`display_name`, `description`, `aliases`, `version`), and
`TaxonomyRegistry` has no capability-query methods. Those were
architectural improvements identified after M5.2A shipped, but never
actually implemented before it was frozen.

This package does **not** retrofit them into M5.2A. Per the governing
rule for this milestone ("do not modify the M5.2A ontology"),
`modules/educational_taxonomy/` is untouched — no field was added, no
method was added, nothing was subclassed or monkeypatched. Instead,
everything M5.2B needs beyond what M5.2A actually provides is defined
here, as a new, additive layer that sits *beside* the taxonomy.

## Architecture

```
modules/subject_profile_framework/
├── __init__.py    Public API surface (re-exports everything below)
├── enums.py         CopyrightSensitivity, SupportLevel — the M5.2B-
│                     owned metadata vocabulary M5.2A's spec once
│                     envisioned but never implemented
├── exceptions.py     Exception hierarchy, rooted at
│                     SubjectProfileFrameworkError — separate from
│                     EducationalTaxonomyError; includes
│                     TaxonomyExtensionError, which wraps a failure
│                     from the frozen TaxonomyRegistry.register()
├── models.py          SubjectContribution (wraps a real
│                     EducationalObjectType + the M5.2B metadata
│                     layer) and SubjectProfile (a named, versioned
│                     bundle of contributions for one subject)
├── registry.py         SubjectProfileRegistry (+
│                     default_subject_profiles) — registration,
│                     duplicate detection, atomic rollback,
│                     deterministic ordering, and every
│                     capability-based query
└── validation.py        validate_subject_profile_registry() —
                        registry-wide integrity checks, returning
                        M5.1's own ValidationResult
```

## How M5.2B leverages M5.2A — exactly as it exists

- **Ontology-level metadata, not a second ontology.** A
  `SubjectContribution` does not invent a parallel classification
  system. It wraps one real `EducationalObjectType`, whose `category`
  is the *only* source of that contribution's place in the seven-way
  partition M5.2A defines. Nothing here re-derives or overrides
  category membership.
- **`EducationalObjectType` reused exactly as-is.** Every subject
  profile author constructs a real `EducationalObjectType` — same
  six fields, same validation, same `to_dict()` contract — for each
  contribution. `models.py` imports it directly; it is never
  subclassed.
- **`TaxonomyRegistry` reused exactly as-is.**
  `SubjectProfileRegistry.register()` calls `TaxonomyRegistry.register()`
  — M5.2A's own, unmodified method — once per contribution. This
  package never reaches into `TaxonomyRegistry`'s private state and
  never adds a method to the class itself.
- **The formal extension mechanism used as intended.**
  `register()` — confirmed by M5.2A's own test suite as "the sole
  extension mechanism" — is the only way this package extends the
  taxonomy. Recognition aliases use the same mechanism: they are set
  on the `EducationalObjectType.aliases` field at construction, so
  M5.2A's existing alias-uniqueness enforcement covers them for free.
- **Capability-based queries, implemented over the new layer.**
  `SubjectProfileRegistry.contributions_by_category()`,
  `.contributions_with_symbolic_content()`,
  `.contributions_by_copyright_sensitivity()`, and
  `.contributions_supporting("structural" | "semantic" | "relationship",
  minimum=...)` all read `SubjectContribution` metadata that
  `TaxonomyRegistry` has no concept of — so these queries could not
  live on the frozen registry without modifying it, and don't.
- **The frozen serialization contract.**
  `SubjectContribution.to_dict()` embeds `EducationalObjectType.to_dict()`
  verbatim rather than re-serializing it by hand; `SubjectProfile.to_dict()`
  always orders its contributions by `(category.value, key)` —
  the same deterministic-ordering convention `TaxonomyRegistry.all_types()`
  already establishes.

## Extension lifecycle

1. A subject profile author builds one or more `EducationalObjectType`
   instances (with `aliases` for recognition strings), wraps each in a
   `SubjectContribution` (adding the M5.2B metadata layer as needed),
   and bundles them into a `SubjectProfile`.
2. `SubjectProfileRegistry.register(profile)` — or the module-level
   `register()` against the shared `default_subject_profiles` /
   `default_taxonomy` singletons — validates uniqueness, then calls
   the real `TaxonomyRegistry.register()` for each contribution's
   object type, in order. If any contribution fails (e.g. it collides
   with a built-in taxonomy entry or another subject's contribution),
   every contribution from this same call that was already registered
   is rolled back via `unregister()`, so a failed registration never
   leaves the taxonomy or this registry partially mutated.
3. Once registered, the object type is a first-class taxonomy entry —
   resolvable via `modules.educational_taxonomy.get()` like any
   built-in type — and its M5.2B metadata is queryable via
   `SubjectProfileRegistry`'s capability methods.
4. `SubjectProfileRegistry.unregister(subject_key)` reverses step 2
   entirely: every contribution's taxonomy entry is removed via the
   taxonomy's own `unregister()`, and every identifier it owned is
   freed for reuse.

## Validation

`validate_subject_profile_registry()` reuses M5.1's `ValidationResult`
/ `ValidationDiagnostic` / `DiagnosticSeverity` contracts (the same
integration point M5.2A's own `validate_taxonomy()` establishes) to
check: subject-key uniqueness, cross-profile object-identifier
uniqueness (belt-and-suspenders re-checks of what `register()` already
enforces at registration time), `MAJOR.MINOR.PATCH` version-format
compliance (warning-level), deterministic serialization, and taxonomy
consistency (that every registered contribution still resolves in the
taxonomy registry it was registered into — guarding against external
drift if something else unregisters an entry directly).

## Out of scope (per the M5.2B spec)

Not implemented here — all belong to M5.2C or later: Structural
Understanding, Semantic Enrichment, Relationship Discovery,
Educational Object Processors, Copyright Normalization, Knowledge
Graph integration, DST integration, LLM integration. This package only
lets a subject profile *declare* forward-looking hints
(`structural_support`, `semantic_support`, `relationship_support`,
`processing_hints`, etc.) for those future milestones to consume —
nothing here acts on them.

## Testing

See `tests/test_m52b_subject_profile_extension_framework.py` for unit
tests covering: profile/contribution model validation and
immutability, `to_dict()`/`from_dict()` round-tripping, deterministic
serialization, registration (including atomic rollback on partial
failure), duplicate detection (within a profile and across profiles,
and against the base taxonomy's own built-in entries), unregistration,
deterministic ordering independent of registration/authoring order,
every capability-based query, validation, and confirmation that
`modules.educational_taxonomy` (M5.2A) and
`modules.educational_object_framework` (M5.1) remain importable,
untouched, and structurally identical to their frozen shape.
