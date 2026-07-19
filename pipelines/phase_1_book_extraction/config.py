"""
config.py — central configuration for the NCERT Phase-1 extraction pipeline.

Nothing here talks to the model or the filesystem beyond reading env vars;
it just centralizes the knobs so every module agrees on the same paths and
limits instead of hardcoding them individually.
"""
import os

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PDF_INPUT_FOLDER = os.environ.get("NCERT_PDF_IN", "./pdf_in")
JSON_OUTPUT_FOLDER = os.environ.get("NCERT_JSON_OUT", "./json_out")
CACHE_FOLDER = os.environ.get("NCERT_CACHE", "./.cache")  # resumable-extraction checkpoints

# --------------------------------------------------------------------------
# Persistent storage backend (storage/ package -- OneDrive)
# --------------------------------------------------------------------------
# The "Board" segment of the OneDrive layout that modules/json_writer.py's
# OneDrive-backed output functions resolve every book's folder under, i.e.
# AI_TUTOR/<STORAGE_BOARD>/Class_<klass>/<Subject>/<Book>/. JSON_OUTPUT_FOLDER
# above is intentionally left in place (still read by chapter_output_path()'s
# `output_root` override path and by any caller that wants a raw-path
# escape hatch) -- it no longer names a local directory that gets written
# to directly.
STORAGE_BOARD = os.environ.get("NCERT_STORAGE_BOARD", "CBSE")

# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
VLM_MODEL_ID = os.environ.get("NCERT_VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
VLM_USE_4BIT = os.environ.get("NCERT_VLM_4BIT", "1") == "1"
VLM_MAX_NEW_TOKENS = int(os.environ.get("NCERT_VLM_MAX_NEW_TOKENS", "768"))
VLM_DEVICE = os.environ.get("NCERT_VLM_DEVICE", "auto")  # "auto" | "cuda" | "cpu"

# --------------------------------------------------------------------------
# Batching
# --------------------------------------------------------------------------
DEFAULT_PAGE_BATCH_SIZE = int(os.environ.get("NCERT_PAGE_BATCH_SIZE", "6"))  # 4-8 recommended
MIN_PAGE_BATCH_SIZE = 4
MAX_PAGE_BATCH_SIZE = 8

# --------------------------------------------------------------------------
# Copyright guardrail
# --------------------------------------------------------------------------
MAX_SEMANTIC_DESCRIPTION_WORDS = 30

# Milestone 3.3 (Copyright-Safe Serialization, cont'd): defensive word cap
# for Figure/Table/Diagram `caption`/`title` fields. These are sourced
# directly from nearby PDF/OCR line text (modules/layout_detector.py's
# `_nearby_caption` and the table caption-only fallback) with no upstream
# length limit -- almost always a short label ("Fig 3.2: ...") but nothing
# stops a mis-detected region from picking up a full sentence or more of
# body text as its "caption". Kept generous relative to
# MAX_SEMANTIC_DESCRIPTION_WORDS because a caption is expected to legitimately
# quote a short, factual label (a figure/table number and title), not
# prose -- this is a defensive ceiling, not a paraphrase cap.
MAX_CAPTION_WORDS = 20

# Milestone 3.2 (Copyright-Safe Serialization): whether `programming_syntax`
# Educational Objects built by the DETERMINISTIC recognizers
# (ProgrammingSyntaxRecognizer/PseudocodeRecognizer,
# modules/recognizers/programming_recognizers.py) keep their full verbatim
# `reusable_syntax` code/pseudocode text in the production Chapter JSON, or
# have it replaced with structural metadata (line count / has-content flag)
# like every other HIGH-risk field modules/copyright_sanitizer.py handles.
#
# Default False (redact): the M3.1 audit explicitly did NOT recommend a
# single action for this field -- it flagged it "REVIEW REQUIRED... if kept,
# needs explicit product/legal sign-off, not just a code fix" (a full code
# snippet from an NCERT CS textbook is a substantial, specific, copyrightable
# artifact, not a structural fact like a formula). Absent that sign-off,
# this defaults to the same conservative treatment as every other HIGH-risk
# finding. Flip only once a real product/legal decision has been made that
# verbatim code snippets are an intentional, in-scope feature.
PRESERVE_CODE_SNIPPETS_VERBATIM = os.environ.get("NCERT_PRESERVE_CODE_SNIPPETS", "0") == "1"

# --------------------------------------------------------------------------
# Stage D: deterministic-extraction / VLM-fallback tuning
# --------------------------------------------------------------------------
# Confidence floor below which Stage D's deterministic formula/procedure
# extraction (Worked Example / Formula Box) falls back to a single VLM call
# on the block instead of trusting the template match. Was previously
# hardcoded in modules/stage_d_extraction.py; centralized here so it can be
# tuned without touching pipeline code. No behavior change from the prior
# hardcoded 0.6 default.
DETERMINISTIC_CONFIDENCE_FLOOR = float(os.environ.get("NCERT_DET_CONFIDENCE_FLOOR", "0.6"))

# Tables, Figures, and Diagrams are extracted deterministically (caption +
# layout metadata only) and are NEVER sent to the VLM by default -- this
# matches the original pipeline's behavior, which intentionally never sent
# visual blocks to the VLM. This flag is deliberately separate from the
# general `use_vlm` runtime flag (which still gates the Stage D formula/
# procedure VLM fallback and script-mismatch title/heading recovery): a
# caller can run with use_vlm=True for those without also turning on VLM
# calls for every Table/Figure/Diagram in the chapter. Only flip this on
# once a real feature needs VLM-based visual analysis.
ENABLE_VISUAL_VLM = os.environ.get("NCERT_ENABLE_VISUAL_VLM", "0") == "1"

# --------------------------------------------------------------------------
# Educational Objects Document export (JSON size control)
# --------------------------------------------------------------------------
# The full Stage A/B/C block graph is always built and kept in memory for
# lineage, but is only written into the exported chapter JSON when one of
# these is explicitly enabled. Normal export contains `educational_objects`
# (+ validation_report/quality/extraction_logs) only, per the redesign goal
# of reducing JSON size -- see modules/json_writer.py.
# assemble_educational_objects_document.
EXPORT_BLOCKS = os.environ.get("NCERT_EXPORT_BLOCKS", "0") == "1"
DEBUG_MODE = os.environ.get("NCERT_DEBUG", "0") == "1"

# --------------------------------------------------------------------------
# Defaults used only when neither filename nor prelims TOC can tell us
# --------------------------------------------------------------------------
DEFAULT_SUBJECT = os.environ.get("NCERT_DEFAULT_SUBJECT")  # e.g. "economics"
DEFAULT_CLASS = os.environ.get("NCERT_DEFAULT_CLASS")      # e.g. "12"

# Explicit language override (ISO code, e.g. "en" | "hi" | "sa"). When unset,
# modules/language_detector.py determines the language automatically from
# book/chapter metadata, falling back to script analysis of the extracted
# text and finally to English. See modules/language_detector.py for the
# full list of supported codes.
DEFAULT_LANGUAGE = os.environ.get("NCERT_DEFAULT_LANGUAGE")

# Schema versioning policy: MAJOR.MINOR.PATCH (SemVer), applied to the
# *meaning/compatibility* of the exported Chapter JSON, not to code releases:
#   MAJOR — a field's meaning, type, or how a consumer must interpret it
#           changes even though its name/JSON position doesn't (a consumer
#           written against the old MAJOR version will silently misread the
#           new data rather than erroring) -- or a field is renamed/removed.
#   MINOR — purely additive, backward-compatible changes (new optional
#           field, new object type) that old consumers can safely ignore.
#   PATCH — non-schema fixes (bug fixes, doc/comment changes) that don't
#           change the exported JSON's shape or meaning at all.
#
# 1.0.0 -> 2.0.0 (Phase A): TopicNode.concepts changed meaning from a list of
# human-readable concept NAMES to a list of canonical concept IDs (same
# field name, same List[str] shape -- this is exactly the "silent
# misinterpretation" case MAJOR exists for, since old consumers reading
# `concepts` as display names would now get opaque ids instead). See
# MIGRATIONS.md for the full migration note and schemas/chapter_schema.py's
# TopicNode.concepts docstring for the field-level detail.
#
# 2.0.0 -> 3.0.0 (Milestone 3.2, Copyright-Safe Serialization): several
# fields that used to reach the production Chapter JSON are REMOVED
# outright (`Equation.raw_text`, `Equation.vlm_raw_output`,
# `Equation.vlm_validation_errors`, and, on deterministically-sourced
# `formula_or_procedure`/`programming_syntax` Educational Objects,
# `reusable_procedure`/`procedure_steps`/`reusable_syntax`), replaced with
# structural-metadata-only fields (`Equation.has_raw_text_hint`,
# `procedure_step_count`/`procedure_step_marker_types`,
# `code_line_count`/`has_code_content`). A consumer reading any of the
# removed fields today would silently start getting nothing instead of an
# error -- exactly the MAJOR case per this policy's own definition ("a
# field is renamed/removed"). See modules/copyright_sanitizer.py and
# MIGRATIONS.md for the full field-by-field mapping and reasoning.
#
# 3.0.0 -> 4.0.0 (Milestone 3.3, Copyright-Safe Serialization cont'd): the
# MEDIUM/LOW findings M3.2 deferred. `educational_objects[].rules` (on
# `accounting_format`/`accounting_rule` objects) is REMOVED outright,
# replaced with `matched_rule_count`/`matched_rule_types` -- the same
# MAJOR case as 2.0.0 -> 3.0.0 above, for the same reason. Two more
# fields change MEANING without being removed (still MAJOR, since a
# consumer relying on the old meaning silently gets different data, not
# an error): content-block (`activities`/`boxes`/`warnings`/`notes`/
# `examples`) `semantic_description` is now always `""` at Phase 1
# (paired with a new `has_semantic_description_hint` bool) instead of a
# raw-truncated source-text excerpt; Figure/Diagram/Table `caption`/
# `title` are now capped at MAX_CAPTION_WORDS instead of unbounded. See
# modules/copyright_sanitizer.py and MIGRATIONS.md for the full mapping.
SCHEMA_VERSION = "4.0.0"

# --------------------------------------------------------------------------
# Milestone T1: structural (keyword-independent) TOC page detection
# --------------------------------------------------------------------------
# Temporary runtime diagnostics for modules/pdf_parser.py's TOC-page
# detector (find_toc_lines / _classify_pages_for_toc): logs, per page in
# the prelims/TOC file, the confidence score, which structural signals
# fired, and why the page was accepted or rejected as part of the TOC.
# Meant to be easy to disable once cross-book validation (English, Hindi,
# Sanskrit, keyword-less layouts, ...) is complete -- flip to "0" or unset
# NCERT_TOC_DIAGNOSTICS to silence it without touching detector code.
TOC_DETECTION_DIAGNOSTICS = os.environ.get("NCERT_TOC_DIAGNOSTICS", "1") == "1"

# --------------------------------------------------------------------------
# Milestone M4.2C / M4.3C: heading recognition & canonicalization framework
# toggles
# --------------------------------------------------------------------------
# Whether modules/stage_b_classify.py's heading-topic branch runs the
# modules/heading_recognizers (M4.2A framework + M4.2B/D concrete
# recognizers) RecognitionPipeline at all. Restored here as the missing
# default this frozen M4.2C code has depended on since its own
# introduction (modules/stage_b_classify.py reads config.ENABLE_HEADING_
# RECOGNITION directly) -- not a new feature, just completing a config
# default the existing frozen code already requires to run at all.
# Default enabled -- disabling this only removes the additive
# `heading_recognition` diagnostic metadata from grouping_meta; Stage A's
# own "is this a Heading" block_type/confidence determination (unchanged
# since M4.1) is never affected.
ENABLE_HEADING_RECOGNITION = os.environ.get("NCERT_ENABLE_HEADING_RECOGNITION", "1") == "1"

# Milestone M4.3C: whether modules/stage_b_classify.py's heading-topic
# branch, after a successful M4.2 recognition, also runs the
# modules/heading_canonicalization (M4.3A framework + M4.3B number-system
# canonicalizers) CanonicalizationPipeline. Same established
# os.environ-backed toggle convention as every other flag in this file
# (e.g. ENABLE_VISUAL_VLM above) -- no second configuration mechanism
# introduced. Default enabled -- disabling this only removes the
# additive `heading_canonicalization` diagnostic metadata from
# grouping_meta; it never affects `heading_recognition` metadata,
# block_type, or confidence.
ENABLE_HEADING_CANONICALIZATION = os.environ.get("NCERT_ENABLE_HEADING_CANONICALIZATION", "1") == "1"

# Milestone M4.3D: whether the "structural_validator" canonicalizer
# (modules.heading_canonicalization.structural_validation.StructuralValidator)
# is enabled within the shared modules/heading_canonicalization registry.
# Same os.environ-backed toggle convention as every other flag in this file
# -- no second configuration mechanism introduced. Checked once at
# modules/stage_b_classify.py import time via the registry's own existing
# enable()/disable() lifecycle API. Default enabled -- disabling this only
# stops structural-validation diagnostics/validation_status from being
# produced; it never affects canonical_number, numbering_system,
# canonical_type, heading_recognition metadata, block_type, or confidence.
ENABLE_STRUCTURAL_VALIDATION = os.environ.get("NCERT_ENABLE_STRUCTURAL_VALIDATION", "1") == "1"
