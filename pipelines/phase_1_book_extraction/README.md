# NCERT PDF Extraction Pipeline — Phase 1 (Upgraded)

Converts an NCERT PDF into **one structured JSON file per chapter**. No
master JSON, slides, quizzes, or teaching content — that's Phase 2.

## What changed from the original script

The original single-file script (font-based heading/TOC/chapter detection)
is preserved as the **deterministic layer** and now lives in
`modules/pdf_parser.py`, unchanged in approach. Everything new is additive:

| Module | Responsibility |
|---|---|
| `modules/pdf_parser.py` | Lines, fonts, TOC parsing, chapter/topic detection, page batching *(existing logic, refactored into a module)* |
| `modules/layout_detector.py` | Figure/table/equation/diagram bbox detection (PyMuPDF images, `find_tables()`, vector-drawing clustering, equation symbol heuristics) |
| `modules/ocr_engine.py` | Text-layer-first page text + Tesseract fallback for scanned pages, with confidence scores |
| `modules/content_blocks.py` | Deterministic pattern detection for Activities/Boxes/Notes/Warnings/Examples/Definition-terms |
| `modules/vlm_inference.py` | Loads **Qwen2.5-VL-3B-Instruct once** (4-bit if available, GPU→CPU fallback) and reuses it for the whole run |
| `modules/semantic_processor.py` | All VLM prompts + JSON-response parsing; enforces the 30-word/no-verbatim copyright rule at the code level, independent of model compliance |
| `modules/graph_builder.py` | `learning_graph`, `concept_graph`, `semantic_index` — derived from already-extracted records, no model calls |
| `modules/json_writer.py` | Assembles every stage's output into the exact schema shape and writes it to the required folder layout |
| `modules/validator.py` | Pydantic validation (`schemas/chapter_schema.py`) + guarantees no section is ever omitted |
| `pipeline.py` | Orchestrator: batching, resumable extraction, logging, progress bars, CLI |

## Division of labor (per spec)

- **Python**: PDF parsing, OCR, heading/topic/chapter/page detection, bounding
  boxes, reading order, figure/table/equation/diagram *detection*, JSON
  generation, validation, folder creation.
- **Qwen2.5-VL-3B**: semantic summaries, concept/glossary extraction, and
  figure/table/equation/diagram *understanding* only. It never decides
  headings, numbering, or page/chapter splits.

## Copyright guardrail

Every VLM prompt instructs paraphrase-only, ≤30 words, no verbatim text.
`semantic_processor._enforce_word_cap()` hard-truncates the response
afterward regardless of what the model actually returned, so the limit
holds even if the model doesn't follow instructions. Definitions store only
the **term**, never the copied definition text.

## Setup

```bash
pip install -r requirements.txt
# Tesseract binary (only needed if some pages are scanned images):
#   Ubuntu: sudo apt-get install tesseract-ocr
```

Put NCERT chapter PDFs in `pdf_in/` (optionally include the `*ps.pdf`
prelims file for authoritative book title/subject/class/TOC).

## Run

```bash
python pipeline.py                  # full run, loads Qwen2.5-VL-3B once
python pipeline.py --no-vlm         # deterministic-only dry run, no model load
python pipeline.py --force          # ignore resumable cache, re-extract everything
python pipeline.py --batch-size 8   # pages per VLM batch (4-8)
```

Re-running without `--force` skips chapters whose output JSON already
exists (resumable extraction).

## Output

```
json_out/
  class_12/
    economics/
      macroeconomics/
        _book_manifest.json
        01_introduction-to-macroeconomics.json
        02_national-income-accounting.json
        ...
```

Each chapter JSON contains exactly the sections listed in the task spec
(`schema_version` … `extraction_logs`); any empty section is written as
`[]`/`{}` rather than omitted, and it's validated against
`schemas/chapter_schema.py` before being written. No images, crops, or
page thumbnails are ever saved — only bbox + semantic metadata, per spec.

## Schema versioning

`schema_version` (in `config.SCHEMA_VERSION`) follows MAJOR.MINOR.PATCH,
applied to the exported JSON's field meaning/compatibility (not code
releases) — see the policy comment above `config.SCHEMA_VERSION` for exact
rules on what bumps which component. Every version bump is documented in
[`MIGRATIONS.md`](./MIGRATIONS.md), including how existing consumers should
adapt.

## Notes / known limitations of this pass

- Table detection relies on PyMuPDF's `find_tables()`; a caption-only
  fallback stub is emitted if no ruling-line table is detected for a page
  whose text says "Table N.N ...", so nothing is silently dropped.
- `content_blocks.py`'s Activity/Box/Note/Warning/Example detection is
  keyword+font based (matches the labels the spec lists); pages with
  unusual formatting may need a wider label pattern.
- `vlm_inference.generate_batch()` is currently sequential; true batched
  generation can be dropped in later without touching any other module.
