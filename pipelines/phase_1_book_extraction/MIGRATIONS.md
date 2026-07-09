# Schema Migrations

This file documents every change to the exported Chapter JSON's
`schema_version` (see `config.SCHEMA_VERSION` for the versioning policy:
MAJOR.MINOR.PATCH SemVer applied to field meaning/compatibility, not code
releases).

## 1.0.0 → 2.0.0 (Phase A)

**What changed:** `TopicNode.concepts` changed meaning.

| | Before (1.0.0) | After (2.0.0) |
|---|---|---|
| Contents | List of human-readable concept **names** (e.g. `"Photosynthesis"`) | List of canonical concept **IDs** (e.g. `"photosynthesis-chapter-1-a1b2c3"`) |
| Field name | `concepts` | `concepts` (unchanged) |
| JSON position / shape | `List[str]` on every `TopicNode` | `List[str]` on every `TopicNode` (unchanged) |

**Why this is a MAJOR bump, not MINOR/PATCH:** the field's name, position,
and type are all unchanged, so nothing about the JSON *shape* signals that
old code needs to change. A consumer written against 1.0.0 that reads
`topic["concepts"]` expecting display-ready names will now silently receive
opaque canonical ids instead of erroring — exactly the kind of
backward-incompatible, easy-to-miss change SemVer's MAJOR component exists
to flag.

**Why the change was made:** Phase A introduced a chapter-wide canonical
Concept Registry (one deduplicated record per distinct concept name, each
with a stable `id`/`urn`). Every other object type that references a concept
(figures/tables/definitions/etc., where already resolvable) links to it by
this canonical id, not by re-quoting its name. `TopicNode.concepts` moved to
the same canonical-reference convention for consistency — see
`modules/canonical.py::resolve_concept_ids` and
`schemas/chapter_schema.py::TopicNode.concepts`'s field docstring.

**How to migrate a downstream consumer:**

1. If you need the concept's **display name**, read the new
   `TopicNode.concept_names` field instead (added in Phase A, holds the same
   human-readable names `concepts` used to hold). It is positional/parallel
   in intent to `concepts` but not guaranteed to be index-aligned with it —
   look the id up in the top-level `concepts[]` array (each `Concept` record
   has both `id` and `name`) if you need the exact name for a specific id.
2. If you need to **cross-reference** a topic's concepts against the
   chapter's `concepts[]` array (e.g. to pull `importance`,
   `related_concepts`, or the concept's own canonical `id`/`urn`), match on
   `TopicNode.concepts[i] == Concept.id` — this now works directly, which it
   did not before (previously you had to match on name, case-insensitively,
   with no guaranteed uniqueness).
3. Check `schema_version` on ingest. Any exported chapter JSON with
   `schema_version` starting `1.` still has concept **names** in
   `TopicNode.concepts`; `2.` and above has canonical ids.

**Backward compatibility impact:** breaking for any consumer that reads
`TopicNode.concepts` as display names without checking `schema_version`
first. Non-breaking for every other field — no field was renamed, removed,
or reshaped, and the top-level `concepts[]`, `glossary[]`, and all other
sections are unaffected.
