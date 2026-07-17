# Milestone 1 — Universal Object Linking

## Summary

Before this milestone, only three canonical object types were reliably
linked to the topic that contains them: **concepts**, **glossary
entries**, and **definitions**. Every other canonical object type built
by `pipeline.py` — **examples, tables, figures, diagrams, equations,
notes, boxes, activities, warnings** — was assembled through
`_attach_canonical()` / `canonical.canonical_fields()` with no
`topic_ids=` argument at all, so `topic_ids` silently defaulted to `[]`
and stayed empty for the rest of the pipeline. `TopicNode`'s own reverse
-reference list fields (`examples`, `figures`, `tables`, `equations`,
`diagrams`, `boxes`, `notes`, `warnings`, `activities`) were declared in
`schemas/chapter_schema.py` but never populated — every `topics_out`
entry hard-coded them to `[]` and nothing downstream ever filled them
in.

This milestone adds **one reusable, object-type-agnostic linking
stage** (`modules/topic_linker.py`) that closes both gaps for all nine
previously-unlinked types, and wires it into `pipeline.py` as a single
integration point.

## What changed

| File | Change |
|---|---|
| `modules/topic_linker.py` | **New.** The reusable linker itself. |
| `pipeline.py` | Imports `topic_linker` and calls `topic_linker.link_universal_objects(...)` once, right after every previously-unlinked object type is fully built and `topics_out`'s own page ranges/ids are final. Adds one `logger.debug(...)` line alongside the existing compiler-pass stats logging. |
| `tests/test_topic_linker.py` | **New.** Unit tests for every function in the module. |
| `tests/test_topic_linker_integration.py` | **New.** Integration tests exercising the linker against a realistic, multi-topic, whole-chapter fixture shaped like `pipeline.py`'s real output. |

No existing file's behavior changes for concepts, glossary entries, or
definitions — they are not routed through this new pass at all (see
"Why concepts/glossary/definitions are untouched" below). No schema
changes, no new fields, no new registries, and no changes to
`compiler/references.py`, `compiler/relationships.py`, `compiler/validation.py`,
or anything downstream of Phase A. Validation and semantic-summary work
are explicitly out of scope for this milestone and are not touched.

## Design

### One reusable linker, not nine object-specific call sites

The entire mechanism is two small, generic functions:

- `link_object_to_topic(obj, *, topic_lookup)` — links a single object.
- `link_objects_to_topics(objects, *, object_type, topic_lookup, topics_by_id)`
  — links a homogeneous list of one object type, and (if a reverse slot
  exists for that type) appends into the matching topic's reverse list.

`object_type` is used **only** as a label to look up the correct
`TopicNode` reverse-list name in a small table
(`TOPIC_REVERSE_FIELDS`). Neither function contains any per-type
branching on how to read or link the object itself — adding a tenth
supported type is a one-line addition to that table, never a new
function.

`link_universal_objects(...)` is the single `pipeline.py` integration
point: it builds one page→topic lookup, then runs
`link_objects_to_topics` once per supplied object list.

### Resolution strategy — deterministic page containment, never a guess

The only structural fact this module relies on is **page containment**:
every canonical object built by `pipeline.py` carries a `page` (copied
from the region/content-block it was extracted from, and mirrored onto
`provenance.source_page` by `canonical.canonical_fields()`), and every
topic carries a `page_start`/`page_end` range computed deterministically
by `pdf_parser`'s heading detection. "This object's page falls inside
this topic's range" is exactly the same geometric fact `pipeline.py`'s
own `_topic_lookup_factory` already used for definitions — this module
generalizes that one already-accepted mechanism to the other nine
types, rather than introducing a new one.

This is deliberately **not** the same kind of thing as matching a
figure's caption or title text against a concept name. That heuristic
was already reviewed and explicitly rejected elsewhere in this codebase
(`pipeline.py`'s own "A4 review (Fix 3, Phase A finalization)" comment)
as non-deterministic guessing. Page-range containment carries no such
ambiguity — a page is either inside a topic's `[page_start, page_end]`
span or it is not.

**If an object's page cannot be determined, or no topic's range
contains it**, nothing is linked: `topic_ids` is left exactly as it
already was (normally `[]`), and the object is never added to any
topic's reverse list. Overlapping topic ranges resolve to the **last**
matching topic in input order, matching `_topic_lookup_factory`'s own
tie-break rule exactly.

An object that already carries a non-empty `topic_ids` (i.e., was
linked by an earlier, more specific pass) is **never overwritten or
re-resolved**.

### `concept_ids` is intentionally left alone

None of the nine object types this milestone links get `concept_ids`
populated by this module, and that is by design, not an oversight.
Figures/tables/diagrams/equations/notes/boxes/activities/warnings have
no deterministic name/term field to resolve against the concept
registry (`pipeline.py`'s own existing "A4 review" comment already
established this — the only routes would be caption/title-text guessing
or borrowing the enclosing topic's own concept list, both explicitly
rejected as heuristics). `resolve_deterministic_concept_ids()` exists
in the module purely as an **opt-in** helper for a future object type
that does carry such a field; nothing in `link_universal_objects()`
calls it today.

### Reverse references on `Topic` objects

`schemas/chapter_schema.py::TopicNode` already declares
`examples`/`activities`/`figures`/`tables`/`equations`/`diagrams`/
`boxes`/`notes`/`warnings`/`definitions`/`concepts` as list fields — no
schema change was needed. This milestone simply populates the nine that
were previously always `[]`. Population is idempotent (running the pass
twice never duplicates an id in a reverse list) and additive-only
(pre-existing entries — e.g. `definitions`, already populated inline at
construction time — are never touched by this module).

### Why concepts/glossary/definitions are untouched

They are already linked correctly, inline, at construction time in
`pipeline.py`'s own topic-construction loop (concepts/glossary via the
loop's own `t.id`) and via the `topic_lookup` callback already passed
into `content_blocks.detect_definition_terms`. Re-routing already
-correct, already-tested logic through the new module was out of scope
("DO NOT change the architecture") and unnecessary — `link_objects_to_topics`
would handle them identically if a future caller chose to (see
`tests/test_topic_linker.py::TestLinkObjectsToTopics` for a
`glossary_entry` case demonstrating this).

## Where it runs

`topic_linker.link_universal_objects(...)` is called once in
`pipeline.py`, immediately after every one of the nine object lists
(`examples`, `tables`, `figures`, `diagrams`, `equations`, `notes`,
`boxes`, `activities`, `warnings_list`) is fully built (so every
object's `page` is already set) and after `topics_out`'s own
`page_start`/`page_end`/`id` fields are final — the same point in the
pipeline where `_topic_lookup_factory` itself is already trusted for
definitions. It runs before `graph_builder`, before registry population
(`populate_registries`), and well before `compiler/references.py`'s
Phase B2 pass, so every downstream phase that reads `topic_ids` off a
registry item sees the fully-linked value.

## Testing

- `tests/test_topic_linker.py` — 40+ unit tests covering
  `resolve_object_page`, `make_page_topic_lookup` (containment,
  boundaries, overlap tie-break, malformed ranges), `link_object_to_topic`
  (linking, never-overwrite, never-guess), `link_objects_to_topics`
  (parametrized across all nine supported types plus a
  `glossary_entry` reuse case, idempotency, malformed-entry skipping),
  `resolve_deterministic_concept_ids` (opt-in only), and
  `link_universal_objects` end to end.
- `tests/test_topic_linker_integration.py` — a realistic, whole-chapter,
  multi-topic fixture (three topics, objects on boundary pages, one
  deliberately out-of-range "orphan" object) exercising the full pass
  the way `pipeline.py` actually calls it, including a re-run-is-a-no-op
  idempotency check.

All 57 tests pass against the module directly (no PyMuPDF/pydantic
dependency — the linker itself operates on plain dicts).
