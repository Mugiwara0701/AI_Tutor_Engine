"""
extraction_debug/ — Milestone 3.2: Copyright-Safe Serialization, debug-only
artifact.

Holds exactly the content `modules/copyright_sanitizer.py` stripped out of
the production Chapter JSON (raw OCR/PDF-line text behind `raw_text`/
`reusable_procedure`/`procedure_steps`/`reusable_syntax`, plus any
`vlm_raw_output`/`vlm_validation_errors` from a failed VLM call) — never
written to `json_out/`, so it never reaches Phase 2 or any consumer of the
production document. Exists purely so that content isn't silently lost:
a developer debugging a specific extraction (e.g. "why did this equation's
`has_raw_text_hint` come back False?") can still inspect the original
source-derived text here, under a folder that is explicitly documented and
understood to be a debug/audit-only artifact, exactly like `validation/`,
`compiler_metadata/`, and every other sibling under
`modules.json_writer._ARTIFACT_SUBFOLDERS`.

Mirrors `validation/persistence.py`'s own "one record per chapter" shape
and `storage.upload_json()`/`download_json()`/`exists()` surface — see
`persistence.py` in this package.
"""
