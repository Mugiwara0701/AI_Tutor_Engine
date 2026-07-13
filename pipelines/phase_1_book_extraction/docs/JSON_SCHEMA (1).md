# Chapter JSON Schema

Source of truth: `schemas/chapter_schema.py`. Enforced with `extra="forbid"`
at the top level (`ChapterJSON`) — no undocumented top-level key can ever
be written — while most nested sections use `extra="allow"` (`Loose`
base class) so they can grow without breaking old consumers. Every
section listed here is always present in the written JSON (`[]`/`{}`
rather than omitted), even when empty. Current `schema_version`:
`2.0.0` (`config.SCHEMA_VERSION`) — see `MIGRATIONS.md` for the version
history.

## Shared shapes

**`BBox`**: `x0`, `y0`, `x1`, `y1` (floats, default `0.0`), `page` (int,
default `0`).

**`Provenance`** (`extra="allow"`): `source_page`, `source_block_id`,
`source_heading`, `section`, `bounding_box: BBox`, `extraction_stage`,
`recognizer`, `evidence_span`, `extraction_method` (`"deterministic"` |
`"vlm"` | `"hybrid"`), `confidence`, `timestamp`. All optional.

**`CreationMetadata`** (`extra="allow"`): `created_at`,
`compiler_version` (default `"1.0.0"`), `generator`.

## `CanonicalObjectBase` — the common envelope

Every canonical educational object (Concept, Definition, Example,
Activity, Figure, Table, Equation, Diagram/Chart/Graph/Map/Timeline, Box,
NoteItem, WarningItem, GlossaryEntry) inherits this instead of
redeclaring identity/provenance/lineage fields per type:

| Field | Type | Notes |
|---|---|---|
| `id` | `str` (required) | Deterministic, derived from stable inputs (chapter title/slug, object kind, content-derived key or stable positional index) — **never random**. Recompiling identical content reproduces the identical id. See `modules/pdf_parser.py::make_id`. |
| `urn` | `Optional[str]` | Globally-unique, hierarchical reference (`modules/pdf_parser.py::make_urn`); stable across recompilations unless the content actually changes. |
| `object_type` | `str` | e.g. `"concept"`, `"figure"` — overridden per subclass. |
| `schema_version` | `str` | Set from `config.SCHEMA_VERSION` by `modules/canonical.py::canonical_fields()`. |
| `subject`, `chapter_reference` | `Optional[str]` | |
| `topic_ids`, `concept_ids` | `List[str]` | Canonical id references — see the concepts-as-ids note below. |
| `provenance` | `Provenance` | |
| `extraction_confidence` | `float` | |
| `validation_status` | `str` | default `"unvalidated"` |
| `duplicate_lineage` | `List[Dict]` | Populated by extraction-Stage-E dedup, recording what a surviving object absorbed. |
| `creation_metadata` | `CreationMetadata` | |

`extra="allow"` — a producer can attach extra fields without a schema
change.

## Top-level `ChapterJSON` sections

In the exact order the spec lists them (`extra="forbid"` at this level):

| Section | Type | Notes |
|---|---|---|
| `schema_version` | `str` | Fallback default; `json_writer.py` always sets it explicitly. |
| `extraction_metadata` | `ExtractionMetadata` | `pipeline_version`, `extracted_at`, `source_pdf`, `ocr_engine`, `vlm_model`, `processing_time_seconds`. |
| `document` | `DocumentInfo` | `book_title`, `subject`, `class` (aliased from `klass`), `board` (default `"NCERT"`), `language: List[str]`, plus optional cover metadata (`book_subtitle`, `book_part`, `book_volume`, `book_edition`, `educational_identity`, `storage_identity`). |
| `chapter_metadata` | `ChapterMetadata` | `chapter_number`, `chapter_title`, `page_start`, `page_end`, `toc_matched`. |
| `chapter_statistics` | `ChapterStatistics` | `total_pages`, `total_words`, `total_topics`, `total_figures`, `total_tables`, `total_equations`. |
| `pages` | `List[PageInfo]` | One entry per page: dimensions, word count, has_figures/tables/equations flags, `ocr_confidence`. |
| `topic_tree` | `List[Dict]` | Free-form hierarchical view (not schema-typed). |
| `topics` | `List[TopicNode]` | See below — the richest section. |
| `concepts` | `List[Concept]` | One per distinct concept name (deduped case-insensitively at build time). |
| `glossary` | `List[GlossaryEntry]` | Term only, never definition text (copyright guardrail). |
| `definitions` | `List[Definition]` | |
| `examples` | `List[Example]` | |
| `activities` | `List[Activity]` | |
| `figures`, `tables`, `equations` | `List[Figure\|Table\|Equation]` | |
| `diagrams`, `charts`, `graphs`, `maps`, `timelines` | `List[Diagram\|Chart\|Graph\|Map\|Timeline]` | All subclass `Figure` — same fields, distinct `object_type`, kept as separate top-level keys per spec. |
| `boxes`, `notes`, `warnings` | `List[Box\|NoteItem\|WarningItem]` | |
| `blocks` | `List[AnnotatedBlock]` | Extraction-internal Stage A/B/C output (geometry + classification + priority), kept for lineage/debugging alongside the semantic sections. |
| `educational_objects` | `List[EducationalObject]` | Extraction-internal Stage D/E output. |
| `validation_report` | `ValidationReport` | `input_count`, `output_count`, `removed_duplicate_formulas`, `removed_duplicate_definitions`, `removed_bare_arithmetic`, `warnings`. |
| `learning_graph`, `concept_graph` | `LearningGraph`/`ConceptGraph` | `nodes: List[str]` + `edges: List[GraphEdge]` (`source`, `target`, `relationship_type`, `weight`). Built by `modules/graph_builder.py` from already-extracted records — no model calls. |
| `semantic_index` | `List[SemanticIndexEntry]` | `concept` + cross-references into topics/definitions/figures/tables/equations. |
| `ai_metadata` | `AIMetadata` | Chapter-level descriptive metadata (complexity, dependency dimensions, important/confusing concepts) — knowledge facts, not pedagogy. |
| `generation_metadata` | `GenerationMetadata` | `preferred_visual_types`, `visual_priority`, `real_world_domains`. **Note**: `teacher_style` and `quiz_focus_topics` were deliberately removed (documented as "phase leakage" in the schema's own comment) — old JSON carrying them still validates via `extra="allow"`, but they are no longer produced. |
| `quality` | `QualityScores` | Per-dimension scores: `ocr`, `heading`, `layout`, `table`, `figure`, `equation`, `overall`. |
| `extraction_logs` | `ExtractionLogs` | `warnings`, `errors`, `missing_figures`, `ocr_failures`, `parser_messages`, `processing_time`. |

## `TopicNode` — the field with a documented breaking change

`TopicNode` is a standalone model (not a `CanonicalObjectBase` subclass).
Besides identity/hierarchy fields (`id`, `title`, `numbering`, `level`,
`parent`, `children`, `page_start`/`page_end`, `bbox`, `reading_order`,
`keywords`), it carries per-type id-reference lists (`definitions`,
`examples`, `activities`, `figures`, `tables`, `equations`, `diagrams`,
`charts`, `graphs`, `maps`, `timelines`, `boxes`, `notes`, `warnings`),
`semantic_summary`, `visual_summary`, `detected_entities`,
`prerequisites`, `related_topics`, `next_topics`, and `confidence`.

**`concepts: List[str]`** changed meaning at `schema_version` `1.0.0` →
`2.0.0`: it used to hold human-readable concept **names**; it now holds
canonical concept **ids**. The shape (`List[str]`) is unchanged, so an
old consumer reading it as names would silently misinterpret the new
data — this is exactly the MAJOR-version case `config.SCHEMA_VERSION`'s
own policy comment defines. The new `concept_names: List[str]` field is
the derived, human-readable counterpart for display purposes; it is
**not** a reference other objects should link against. See
`MIGRATIONS.md` for the full migration note.

## Per-object-type fields (beyond `CanonicalObjectBase`)

| Type | `object_type` | Own fields |
|---|---|---|
| `Concept` | `concept` | `name`, `aliases`, `importance`, `topic` (legacy singular, kept for back-compat), `topics` (canonical, complete list), `page`, `related_concepts`. |
| `Definition` | `definition` | `term`, `page`, `bbox`, `topic`. |
| `Example` | `example` | `title`, `page`, `bbox`, `example_type` (default `"worked_example"`), `semantic_description`. |
| `Activity` | `activity` | `activity_type` (Activity/Think/Observe/Try/Discuss/Experiment), `title`, `page`, `bbox`, `semantic_description`. |
| `Figure` | `figure` | `page`, `bbox`, `title`, `caption`, `figure_type`, `semantic_description`, `educational_purpose`, `concepts` (legacy human-readable list — `concept_ids` on the base class is now canonical), `related_topics`, `importance`, `difficulty`, `animation_candidate`, `confidence`. |
| `Table` | `table` | `title`, `page`, `bbox`, `rows`, `columns`, `table_type` (default `"data_table"`), `semantic_description`, `educational_purpose`, `concepts`, `confidence`. |
| `Equation` | `equation` | `page`, `bbox`, `latex`, `spoken_form`, `variables`, `semantic_meaning`, `confidence`. |
| `Diagram`/`Chart`/`Graph`/`Map`/`Timeline` | `diagram`/`chart`/`graph`/`map`/`timeline` | Subclass `Figure` directly — identical field set, distinct `object_type` only, so `json_writer` can emit them under their own top-level keys per spec. |
| `Box` | `box` | `box_type` (Did You Know/Important/Note/Remember/Case Study/Box), `title`, `page`, `bbox`, `semantic_description`. |
| `NoteItem` | `note` | `page`, `bbox`, `semantic_description`. |
| `WarningItem` | `warning` | `warning_type` (Warning/Caution/Remember/Important), `page`, `bbox`, `semantic_description`. |
| `GlossaryEntry` | `glossary_entry` | `term`, `topic`, `page`. Promoted from a free-form dict to a canonical, identity-bearing object; still stores the term only, never definition text. |

## `AnnotatedBlock` / `EducationalObject` — extraction-internal output

- **`AnnotatedBlock`** (`extra="allow"`): `block_id`, `parent`,
  `block_type` (one of extraction-Stage-B's `BLOCK_TYPES`), `priority`
  (extraction-Stage-C output), `confidence`, `page`, `page_end`, `bbox`,
  `child_block_ids`. This is the raw geometry+classification+priority
  record from extraction Stages A–C, kept for lineage/debugging.
- **`EducationalObject`** (`extra="allow"`): `id`, `block_id`,
  `block_type`, `priority`, `educational_object_type`, `page`,
  `page_end`, `bbox`, `confidence`, `source` (`"deterministic"` by
  default), `duplicate_lineage`. This is extraction Stage D/E output.

Both classes are declared once in `schemas/chapter_schema.py` and
re-imported (not redeclared) by `schemas/educational_objects_schema.py`,
so the two schema files cannot drift apart.

## Copyright guardrail, enforced at the schema/pipeline boundary

Every `semantic_description`/`semantic_meaning`/`semantic_summary` field
is produced under a ≤`config.MAX_SEMANTIC_DESCRIPTION_WORDS` (30-word)
cap enforced in code (`modules/semantic_processor.py`) independent of
model compliance — the schema itself does not enforce a word count
(these are plain `str` fields), so this constraint is a **pipeline**
guarantee, not a schema-level one. Glossary entries store only `term`,
never definition text, at both the pipeline and schema level.
