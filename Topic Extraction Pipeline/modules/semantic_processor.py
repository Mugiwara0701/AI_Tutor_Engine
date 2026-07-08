"""
semantic_processor.py — the ONLY module that decides what semantic
information needs to be generated and how to interpret the answers.
Everything deterministic (headings, page numbers, bboxes, chapter
splitting) has already been decided by pdf_parser and layout_detector
before this module ever runs; the VLM is used strictly for semantic
understanding fields, per the task spec's "USE QWEN2.5-VL-3B FOR" list.

Reconnect milestone: every AI inference in this module now goes through
prompt_manager (prompt_manager -> qwen_adapter -> Qwen2.5-VL-3B ->
validated TaskResult) instead of calling modules.vlm_inference directly.
This module's own responsibility is UNCHANGED: it still decides WHAT to
ask for (which task, with which context) and how to turn the validated
answer back into the flat dict shape its callers (pipeline.py,
json_writer.py) have always received. prompt_manager owns prompt
rendering, the model call, response cleanup/parsing (delegated further to
qwen_adapter), and validation+retry. No business logic moved the other
direction: prompt_manager does not know what a "topic" or "figure" is,
and never reaches into this module.

Copyright guardrail: every prompt instructs the model to paraphrase,
never quote, and cap at MAX_SEMANTIC_DESCRIPTION_WORDS words;
`_enforce_word_cap` then hard-truncates as a second, code-level safety
net independent of whether the model followed instructions. This part is
unchanged by the reconnect and is explicitly out of scope for this
milestone (see AFTER IMPLEMENTATION note in the task).
"""
import logging
from typing import List, Dict, Any, Optional

import fitz  # PyMuPDF
from PIL import Image

from config import MAX_SEMANTIC_DESCRIPTION_WORDS
from modules.pdf_parser import TopicRecord
from modules.layout_detector import VisualRegion
from modules import language_detector
from prompt_manager import PromptManager, TaskContext
from prompt_manager.adapters import QwenAdapter

logger = logging.getLogger("ncert_pipeline.semantic")

# --------------------------------------------------------------------------
# Current chapter's language, set once per chapter by pipeline.py before
# any topic/figure/table/equation is processed. Every _run_task() call
# injects this into the task's variables so every prompt template can
# instruct the model to keep its answer in the source textbook's language
# instead of silently defaulting to English -- one choke point instead of
# threading a `language` argument through every process_* function's
# signature (which every one of this module's callers would have had to
# start passing).
# --------------------------------------------------------------------------
_CURRENT_LANGUAGE = {"code": "en", "name": "English"}

# --------------------------------------------------------------------------
# Equation-semantics cache (ISSUE 1 fix).
#
# Root cause of the "duplicate equation_analysis" symptom: the flat
# top-level `equations` list (pipeline.py) and Stage D's
# FormulaFamilyRecognizer.vlm_fallback (modules/recognizers/base.py) are two
# INDEPENDENT call sites that can both end up asking for semantics on the
# same physical equation region -- once while building the flat Master
# JSON `equations` section, and again while extracting an Educational
# Object for the equivalent Stage A/B/C block. Neither call site knew about
# the other, so the same equation could be sent to the VLM twice.
#
# Rather than thread a cache object through every caller's signature, this
# module-level dict (keyed on the same (page, bbox) identity both call
# sites already have) is reset once per chapter (reset_chapter_state(),
# called from the same place set_current_language() already is) and
# consulted by process_equation_semantics() below -- a genuine
# checkpoint/cache for the single most expensive repeated operation in the
# pipeline, not just a cosmetic dedup.
# --------------------------------------------------------------------------
_EQUATION_SEMANTICS_CACHE: Dict[Any, Dict[str, Any]] = {}


def _equation_cache_key(region: VisualRegion):
    bbox = tuple(round(float(c), 1) for c in region.bbox)
    return (region.page, bbox)


def reset_chapter_state() -> None:
    """Clears every per-chapter cache (currently just the equation-
    semantics cache). Call once per chapter, alongside set_current_language,
    before any Stage A-E/VLM work starts -- never share this cache across
    chapters, since two different chapters can legitimately have equations
    at the same (page, bbox) coordinates."""
    _EQUATION_SEMANTICS_CACHE.clear()


def set_current_language(language_code: str) -> None:
    """Called once per chapter (pipeline.py, right after parse_chapter_pdf)
    so every subsequent VLM task in this chapter preserves the detected
    source language instead of assuming English."""
    _CURRENT_LANGUAGE["code"] = language_code or "en"
    _CURRENT_LANGUAGE["name"] = language_detector.language_name(_CURRENT_LANGUAGE["code"])


def get_current_language() -> str:
    return _CURRENT_LANGUAGE["code"]


def _enforce_word_cap(text: str, max_words: int = MAX_SEMANTIC_DESCRIPTION_WORDS) -> str:
    words = text.split()
    return " ".join(words[:max_words])


def render_page_crop(doc: fitz.Document, page: int, bbox, dpi: int = 150, pad: float = 6.0) -> Image.Image:
    p = doc[page]
    rect = fitz.Rect(bbox)
    rect = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad) & p.rect
    zoom = dpi / 72.0
    pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def render_full_page(doc: fitz.Document, page: int, dpi: int = 130) -> Image.Image:
    p = doc[page]
    zoom = dpi / 72.0
    pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


# --------------------------------------------------------------------------
# prompt_manager wiring — the single choke point every VLM call in this
# module now passes through. semantic_processor still decides WHICH task
# and WHAT context; prompt_manager owns everything downstream of that.
# --------------------------------------------------------------------------
_PROMPT_MANAGER: Optional[PromptManager] = None


def _get_prompt_manager() -> PromptManager:
    """Lazily builds a module-level PromptManager wired to QwenAdapter, the
    same "load once, reuse for the whole run" pattern vlm_inference.py
    already uses for the model itself. Tests can monkeypatch this function
    to inject a PromptManager backed by a fake adapter instead of Qwen."""
    global _PROMPT_MANAGER
    if _PROMPT_MANAGER is None:
        _PROMPT_MANAGER = PromptManager(QwenAdapter())
    return _PROMPT_MANAGER


def _unwrap(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """prompt_manager's output contracts wrap every AI-inferred scalar
    field in an evidence-triple {value, confidence, evidence_basis} (v1.2
    addendum #5). semantic_processor's callers (pipeline.py, json_writer)
    have always received flat plain values (str/float/bool/list), matching
    the frozen Chapter JSON schema (schemas/chapter_schema.py), and that
    public shape must not change. This is the one place that understands
    the triple envelope and flattens it back out.

    It also synthesizes a top-level 'confidence' as the average of every
    per-field confidence found, so callers that read sem.get('confidence',
    default) (pipeline.py does this for figures/tables/equations) keep
    working: before this refactor the model returned one overall
    confidence value directly; the new task contracts only carry
    per-field confidence, so an average is the closest faithful
    reconstruction of that same signal without inventing a new prompt
    convention outside prompt_manager's frozen per-field-triple design.
    """
    flat: Dict[str, Any] = {}
    confidences: List[float] = []

    def _unwrap_value(v):
        if isinstance(v, dict) and "value" in v and "confidence" in v:
            c = v.get("confidence")
            if isinstance(c, (int, float)):
                confidences.append(float(c))
            return v.get("value")
        return v

    for key, value in (parsed or {}).items():
        if isinstance(value, list):
            flat[key] = [_unwrap_value(item) for item in value]
        else:
            flat[key] = _unwrap_value(value)

    if confidences:
        flat.setdefault("confidence", round(sum(confidences) / len(confidences), 3))
    return flat


def _run_task(task_name: str, variables: Dict[str, Any], images: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Builds a TaskContext, runs it through prompt_manager, and flattens
    the result. On failure (invalid JSON even after prompt_manager's
    internal retry, or an adapter-reported infrastructure error) returns
    {} — exactly the same fallback the old _safe_json() produced on a
    parse failure — so every caller's `sem.get(key, default)` pattern
    keeps working unchanged. MissingContextError/KeyError are NOT caught
    here: those indicate this module built the wrong context for a task,
    which is a programming error that should fail loudly, same as before
    when a missing attribute would raise."""
    variables = dict(variables)
    variables.setdefault("target_language_code", _CURRENT_LANGUAGE["code"])
    variables.setdefault("target_language_name", _CURRENT_LANGUAGE["name"])
    context = TaskContext(variables=variables, images=images or [])
    result = _get_prompt_manager().run(task_name, context)
    if not result.success or result.parsed_output is None:
        logger.warning(
            "Task '%s' did not produce a validated result after %d retr%s: %s",
            task_name, result.retry_count, "y" if result.retry_count == 1 else "ies",
            result.validation_errors,
        )
        # ISSUE 2 fix: previously this returned {} unconditionally, which
        # silently discarded the model's raw text along with everything
        # else the moment JSON parsing/validation failed -- "invalid JSON"
        # became indistinguishable from "no information extracted at all".
        # Store what we have (raw text + why it failed) instead, so a
        # caller can still surface it in the Master JSON / extraction_logs
        # rather than the block's semantic fields simply vanishing.
        return {
            "_vlm_failed": True,
            "_vlm_raw_output": result.raw_model_output or "",
            "_vlm_validation_errors": list(result.validation_errors),
        }
    return _unwrap(result.parsed_output)


# --------------------------------------------------------------------------
# Runner functions — each takes deterministic input, decides what task and
# context to send to prompt_manager, and returns a schema-shaped flat dict.
# Public signatures and return shapes are unchanged from before the
# reconnect; only how the answer is obtained has changed.
# --------------------------------------------------------------------------
def process_topic_semantics(doc: fitz.Document, topic: TopicRecord) -> Dict[str, Any]:
    page_img = render_full_page(doc, min(topic.page_start, doc.page_count - 1))
    data = _run_task(
        "topic_semantics",
        {"topic_title": topic.title, "topic_body_preview": topic.body_text[:400]},
        images=[page_img],
    )
    data["semantic_summary"] = _enforce_word_cap(str(data.get("semantic_summary", "")))
    data["visual_summary"] = _enforce_word_cap(str(data.get("visual_summary", "")))
    return data


def process_figure_semantics(doc: fitz.Document, region: VisualRegion) -> Dict[str, Any]:
    crop = render_page_crop(doc, region.page, region.bbox)
    data = _run_task("figure_analysis", {"caption": region.caption}, images=[crop])
    data["semantic_description"] = _enforce_word_cap(str(data.get("semantic_description", "")))
    return data


def process_table_semantics(doc: fitz.Document, region: VisualRegion) -> Dict[str, Any]:
    extra = region.extra or {}
    crop = render_page_crop(doc, region.page, region.bbox)
    data = _run_task(
        "table_analysis",
        {"caption": region.caption, "rows": extra.get("rows", 0), "columns": extra.get("columns", 0)},
        images=[crop],
    )
    data["semantic_description"] = _enforce_word_cap(str(data.get("semantic_description", "")))
    return data


def process_equation_semantics(doc: fitz.Document, region: VisualRegion) -> Dict[str, Any]:
    """ISSUE 1 fix: cached per (page, bbox) for the lifetime of the current
    chapter (see reset_chapter_state()/_EQUATION_SEMANTICS_CACHE above), so
    if two independent call sites (the flat top-level `equations` builder
    and Stage D's FormulaFamilyRecognizer.vlm_fallback) both need semantics
    for the same physical equation, the VLM is invoked at most once."""
    cache_key = _equation_cache_key(region)
    cached = _EQUATION_SEMANTICS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    extra = region.extra or {}
    crop = render_page_crop(doc, region.page, region.bbox)
    data = _run_task("equation_analysis", {"raw_text_hint": extra.get("raw_text", "")}, images=[crop])
    data["semantic_meaning"] = _enforce_word_cap(str(data.get("semantic_meaning", "")))
    _EQUATION_SEMANTICS_CACHE[cache_key] = data
    return data


def process_recover_chapter_title(doc: fitz.Document, page_hint: int, candidate_title: str,
                                   book_title: str, subject: str, ocr_text_first_pages: str) -> Dict[str, Any]:
    """Recovers a chapter title that pdf_parser's deterministic (font-size
    based) detection pulled from a script-mismatched text layer -- the
    legacy-font symptom documented in modules/language_detector.py, where a
    Hindi/Sanskrit page's text layer decodes to Latin-looking gibberish
    instead of real Devanagari. Uses the page image + the OCR'd text (which
    ocr_engine already re-derives correctly via Tesseract for exactly this
    case) as evidence, so the model reads the real rendered glyphs rather
    than the lying text layer."""
    page_img = render_full_page(doc, min(max(page_hint, 0), doc.page_count - 1))
    return _run_task(
        "recover_chapter_title",
        {
            "candidate_titles": candidate_title,
            "ocr_text_first_pages": ocr_text_first_pages,
            "book_title": book_title,
            "subject": subject,
        },
        images=[page_img],
    )


def process_recover_heading(doc: fitz.Document, page: int, bbox, expected_level: int,
                             ocr_text_region: str, nearby_headings: List[str],
                             chapter_title: str) -> Dict[str, Any]:
    """Recovers a section heading (title + numbering) that pdf_parser's
    deterministic detection pulled from a script-mismatched text layer --
    same legacy-font symptom as process_recover_chapter_title, applied to
    an individual heading region instead of the chapter title."""
    crop = render_page_crop(doc, min(max(page, 0), doc.page_count - 1), bbox)
    return _run_task(
        "recover_heading",
        {
            "expected_level": expected_level,
            "ocr_text_region": ocr_text_region,
            "nearby_headings": nearby_headings,
            "chapter_title": chapter_title,
        },
        images=[crop],
    )


def process_chapter_ai_metadata(topic_titles: List[str], num_figures: int, num_tables: int,
                                 num_equations: int) -> Dict[str, Any]:
    return _run_task("chapter_ai_metadata", {
        "topic_titles": topic_titles[:40],
        "num_figures": num_figures,
        "num_tables": num_tables,
        "num_equations": num_equations,
    })


def process_generation_metadata(chapter_title: str, ai_metadata: Dict[str, Any]) -> Dict[str, Any]:
    return _run_task("generation_metadata", {
        "chapter_title": chapter_title,
        "chapter_type": ai_metadata.get("chapter_type"),
        "visual_dependency": ai_metadata.get("visual_dependency"),
        "formula_dependency": ai_metadata.get("formula_dependency"),
    })