# Milestone 1 — Core Foundation: Conformance Review

Reviewed against `DST_Architecture_v1.1.md` (Version 1.0, frozen) and
`DST_Schema_Design_v1.1.md` (Schema Version 1.0, frozen). Scope of this
review matches the roadmap's stated review posture: conformance only,
no design discussion.

## What was built

New package `document_structure_tree/`, placed alongside the existing
`knowledge_graph/` package (same repository convention: plain, storable
dataclasses; a `SCOPE:`-first module docstring; a small, specific
exception hierarchy):

| File | Contents |
|---|---|
| `primitives.py` | Every schema §2.1 supporting/reusable type: `ChapterId`, `NodeId`, `CanonicalObjectId`, `ObjectType`, `Level`, `SchemaVersion`, `CompilerVersion`, `IdentitySchemeVersion`, `Timestamp`, `Fingerprint`, `BlockIndex`, `BlockRange`, `PageLocator`, `PageRange`, `Span` |
| `enums.py` | `EntryType`, `ValidationStatus`, `HeadingDetectionMethod`, `InvariantId` |
| `serialization.py` | `OMIT` sentinel, `json_object`, `round_trip` harness, shared `require_*` validators |
| `identity.py` | `compute_node_id` (architecture §14, schema §4), `IDENTITY_SCHEME_VERSION` |
| `exceptions.py` | `DocumentStructureTreeError`, `DSTValueError`, `DSTSerializationError`, `DSTIdentityError` |
| `tests/test_dst_primitives.py`, `test_dst_enums.py`, `test_dst_serialization.py`, `test_dst_identity.py` | Unit tests, run and passing (138 pytest-parametrized invocations verified in-sandbox via a minimal local pytest-compatible shim, real network access to install pytest being unavailable here — spot-checked separately for the two stacked-`@parametrize` cases the shim doesn't expand) |

## Acceptance criteria (user's stated criteria)

- **Every primitive model from the frozen schema exists.** All fifteen
  §2.1 types are present; none invented beyond that table.
- **Every enum exists.** `EntryType`, `ValidationStatus`,
  `HeadingDetectionMethod`, `InvariantId` are implemented. See the
  one deliberate deviation from the roadmap's own illustrative list,
  below.
- **Serialization utilities are functional.** `to_json`/`from_json` on
  every primitive and enum; `round_trip` harness exercised by every
  test file; omission-vs-null handling (schema §5.3) implemented once
  in `json_object` and reused everywhere rather than per-type.
- **Identity utilities are implemented.** `compute_node_id` per
  architecture §14 / schema §4, as a pure function whose signature
  structurally excludes `title`/`span`/`sequence` (not just "ignores"
  them — no such parameters exist to pass).
- **All unit tests pass.** See table above.
- **No TODO placeholders for future milestones.** None present;
  every docstring that references a later milestone does so to
  explain a scope boundary, not to mark unfinished work.
- **No later-milestone implementation introduced.** No `HeadingNode`,
  `SequenceEntry`, `DocumentStructureTree`, tree builder, validation
  engine, artifact assembly, or pipeline wiring exists anywhere in the
  package. Confirmed by grep: neither name appears outside docstring
  prose explaining why it's absent.

## One deliberate spec-fidelity decision worth flagging explicitly

The roadmap (`DST_Implementation_Roadmap_v1.0.md`, M0/M1) lists
`ObjectType` alongside `EntryType`, `ValidationStatus`,
`HeadingDetectionMethod`, and `InvariantId` as illustrative examples of
"enums" to implement. The frozen schema itself
(`DST_Schema_Design_v1.1.md` §2.1) classifies `ObjectType` differently
from those four: "String drawn from the canonical registries'
object-type vocabulary ... **Open string set** owned by the canonical
registries, **not enumerated here**" — versus `EntryType`'s "Closed
set — this is a discriminator, not extensible."

Per the ground rule for this discussion ("if you believe something is
ambiguous, point to the relevant section of the frozen specification
rather than inventing a new design"), `ObjectType` is implemented in
`primitives.py` as an opaque, validated string type (non-empty only),
*not* as a closed Python `Enum` in `enums.py`. Implementing it as a
closed enum would have silently narrowed a vocabulary the architecture
explicitly keeps open for the canonical registries to extend without a
DST schema change (architecture §20). `enums.py`'s and `primitives.py`'s
own docstrings both cite this reasoning inline. This is a resolution of
an inconsistency between the roadmap's illustrative grouping and the
schema's own field-level classification — not a schema or architecture
change — and is flagged here per the review-posture instructions rather
than left implicit.

`HeadingDetectionMethod` is a related but different case: schema §2.1
calls it "a compiler-internal vocabulary" with a trailing "…" after its
examples (open-ended), but the roadmap does list it as an enum, and
no §15 invariant or §17 Phase 2 guarantee depends on its values (schema
§2.4). It is implemented as an `Enum` covering exactly the values the
schema document names, with an explicit docstring note that — unlike
the other three enums — extending it later is a compiler-internal,
non-breaking change, not a `schema_version`-relevant one.

## Spec conformance notes

- **§5.1 (naming/enum-value conventions):** all field names mirror the
  frozen documents exactly; enum values serialize as their declared
  lowercase (or, for `InvariantId`, as-specified `S1`/`R4`/etc.)
  strings via `.value`.
- **§5.3 (omission vs. null):** implemented once, generically, in
  `serialization.json_object` / the `OMIT` sentinel, rather than
  per-field-per-type. `Span` is the only composite type this milestone
  builds, and it already exercises the rule correctly: `block_range`/
  `page_range` independently omitted when absent, never `null`
  (verified by `test_span_block_range_only_omits_page_range_key`,
  `test_span_empty_case_both_fields_absent`).
- **§2.1 bound conventions:** `BlockRange` half-open (`start <= end`,
  zero-width permitted), `PageRange` inclusive-inclusive with no
  enforced ordering (locators are opaque, possibly non-numeric
  strings) — both implemented and tested against the schema document's
  own adjacency example (`BlockRange{0,5}`/`BlockRange{5,10}` adjacent,
  non-overlapping).
- **§2.9's one asymmetric `Span` constraint** (`page_range` present
  requires `block_range` present) is enforced in `Span.__post_init__`
  and tested both ways.
- **Architecture §14 / schema §4 identity derivation:** implemented as
  specified — reads only `chapter_id`, `level`, parent identity, and a
  caller-supplied disambiguator (`number` when present, else
  `unnumbered_ordinal`); the concrete encoding (SHA-256 over a
  delimited payload, chapter-id-prefixed) is flagged in the module
  docstring as the implementation-level choice schema §4 explicitly
  leaves open, versioned via `IDENTITY_SCHEME_VERSION`.
- **Tier 2's documented limitation** (an inserted earlier unnumbered
  sibling shifts every later sibling's `node_id`) is reproduced as a
  named regression test, not treated as a defect, per architecture §14
  and roadmap M1's own acceptance criteria.
- **Isolation from later-milestone concerns:** `Fingerprint.of()` is a
  generic "SHA-256 of arbitrary bytes" convenience — it does not
  implement the chapter-fingerprint hashing *policy* (which fields go
  in, schema §2.3/B3), which stays correctly owned by roadmap M8.
  Similarly, `BlockRange.contains()` is pure range arithmetic, not an
  S3 validator — no `Violation`/`ValidationResult` shape exists
  anywhere in this milestone.

## Nothing found requiring escalation

No genuine architectural or schema flaw was uncovered while
implementing this milestone. The one point requiring a judgment call
(`ObjectType`'s classification) was resolved by deferring to the
frozen schema's own explicit text over the roadmap's illustrative
grouping, consistent with the instruction to point at the spec rather
than propose a change.
