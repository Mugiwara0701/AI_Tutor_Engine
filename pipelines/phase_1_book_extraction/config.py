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
SCHEMA_VERSION = "2.0.0"