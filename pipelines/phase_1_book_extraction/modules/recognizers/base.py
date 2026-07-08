"""
modules/recognizers/base.py — the Educational-Object-Aware recognizer
framework Stage D dispatches through.

Design goal (per the Phase 1 continuation spec): Stage D must select
recognizers by BLOCK TYPE (what Stage B already determined), never by
subject name. A book called "Science" containing Physics + Chemistry +
Biology, or a different publisher's differently-named subjects, must not
require any `if subject == "..."` branching anywhere in this pipeline.
Subject metadata (chapter title, book title) may at most be passed to a
recognizer as an optional hint — no recognizer in this package uses it as
its primary trigger.

Every recognizer:
  1. Declares which Stage B `block_type`s it is a CANDIDATE for (via the
     registry in modules/recognizers/registry.py, not on the class itself
     — keeps "which types call this recognizer" configurable in one
     place, mirroring how stage_c_priority keeps its map data-driven).
  2. Implements `recognize(block) -> Optional[RecognitionResult]`: pure
     deterministic, cheap, no VLM. Returns None when this recognizer's
     pattern doesn't match the block at all (as opposed to matching with
     low confidence) — that distinction lets the dispatcher in
     stage_d_extraction tell "wrong recognizer for this block" apart from
     "right recognizer, but not confident."
  3. Optionally overrides `vlm_fallback(doc, block)` for a VLM escape
     hatch when every candidate's deterministic confidence is below
     `config.DETERMINISTIC_CONFIDENCE_FLOOR`. The two mixins below
     (`FormulaFamilyRecognizer`, `VisualFamilyRecognizer`) provide this by
     delegating to the exact same semantic_processor call sites the
     pre-modular Stage D already used — so splitting one big per-type
     branch into several small recognizers does not add a single new VLM
     call. `Recognizer.vlm_fallback` itself (the base, un-mixed-in
     version) returns None, i.e. "no VLM path for this recognizer" is the
     safe default (e.g. Definition, accounting-rule recognizers never
     called the VLM before and still don't).

Adding a brand-new educational object (a new subject-specific formula
type, a new visual sub-kind, ...) is meant to require ONLY:
  - a new Recognizer subclass in this package (or a new module here), and
  - one `register(...)` call in modules/recognizers/__init__.py.
Nothing in stage_d_extraction.py itself should need to change.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

import config
from modules.stage_a_geometry import Block
from modules.layout_detector import VisualRegion
from modules import semantic_processor

logger = logging.getLogger("ncert_pipeline.stage_d.recognizers")


@dataclass
class RecognitionResult:
    """What a recognizer's `recognize()` returns on a (partial-or-full)
    match. `data` is merged directly into the Educational Object dict —
    its keys are whatever that recognizer's `educational_object_type`
    shape expects (e.g. `reusable_formula` for formula_or_procedure,
    `term` for concept, `reusable_syntax` for programming_syntax, ...)."""
    confidence: float
    data: Dict[str, Any] = field(default_factory=dict)
    educational_object_type: str = "ambiguous"
    recognizer_name: str = "unknown"
    source: str = "deterministic"


def block_raw_texts(block: Block) -> List[str]:
    """Ported unchanged from the pre-modular stage_d_extraction — every
    recognizer that reads a block's raw line text uses this, rather than
    each reimplementing the children-vs-lines fallback."""
    if block.children:
        return [(c.grouping_meta or {}).get("raw_text") or " ".join(l.text for l in c.lines)
                for c in block.children]
    return [l.text for l in block.lines]


def region_for_block(block: Block, kind: str = "equation") -> VisualRegion:
    """Builds a lightweight VisualRegion so recognizers can reuse
    semantic_processor's existing VLM call signatures unchanged."""
    raw_text = " ".join(block_raw_texts(block))
    return VisualRegion(kind=kind, page=block.page, bbox=block.bbox,
                         caption="", extra={"raw_text": raw_text})


def block_deterministic_visual(block: Block) -> Dict[str, Any]:
    """Deterministic Table/Figure/Diagram baseline: caption + whatever
    layout metadata Stage A/the layout detector already attached to the
    block (rows/columns, region_extra, etc.) — no VLM call. Ported
    unchanged from the pre-modular `_extract_visual_deterministic`; visual
    recognizers use this as their data payload and layer a more specific
    `visual_subtype` / extra fields on top of it."""
    meta = block.grouping_meta or {}
    caption = meta.get("caption", "")
    region_extra = meta.get("region_extra", {}) or {}
    result = {"caption": caption, "semantic_description": ""}
    if region_extra:
        result["metadata"] = region_extra
    return result


class Recognizer:
    """Base class every concrete recognizer inherits from (usually via one
    of the two family mixins below, for the shared VLM fallback)."""
    name: str = "base"
    educational_object_type: str = "ambiguous"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        raise NotImplementedError

    def safe_recognize(self, block: Block) -> Optional[RecognitionResult]:
        """Wraps `recognize()` so one misbehaving recognizer (a bad regex,
        an unexpected grouping_meta shape) can't take the whole Stage D
        run down — logs and treats it as "no match", exactly like a
        deliberate `return None`."""
        try:
            return self.recognize(block)
        except Exception:
            logger.exception("Recognizer '%s' raised on block %s — treating as no match.",
                              self.name, block.block_id)
            return None

    def vlm_fallback(self, doc: fitz.Document, block: Block) -> Optional[Dict[str, Any]]:
        """Default: no VLM path. Returning None here means "this
        recognizer has nothing better to offer than its own (possibly
        low-confidence) deterministic result" — the dispatcher then keeps
        that deterministic result rather than dropping the block."""
        return None


class FormulaFamilyRecognizer(Recognizer):
    """Shared VLM fallback for the formula/procedure family (Formula
    Recognizer, Math Identity, Chemical Reaction, Economic Identity,
    Procedure, Algorithm, Journal Procedure, ...). Delegates to the exact
    same `semantic_processor.process_equation_semantics` call the
    pre-modular `_extract_formula_or_procedure` used — same call site,
    same gating (`use_vlm` only, decided by the dispatcher before calling
    this), so no new VLM call is introduced by splitting one recognizer
    into several."""
    educational_object_type = "formula_or_procedure"

    def vlm_fallback(self, doc: fitz.Document, block: Block) -> Optional[Dict[str, Any]]:
        region = region_for_block(block, kind="equation")
        sem = semantic_processor.process_equation_semantics(doc, region)
        return {
            "reusable_formula": sem.get("latex", ""),
            "reusable_procedure": sem.get("semantic_meaning", ""),
            "variables": sem.get("variables", []) or [],
            "confidence": float(sem.get("confidence", 0.5) or 0.5),
            "source": "vlm_fallback",
            "recognizer": self.name,
            "educational_object_type": self.educational_object_type,
        }


class VisualFamilyRecognizer(Recognizer):
    """Shared VLM fallback for visual-family recognizers (Flowchart,
    Graph, Circuit Diagram, Concept Table, Programming Syntax, Accounting
    Format, ...). Delegates to the exact same
    `semantic_processor.process_figure_semantics` /
    `process_table_semantics` call the pre-modular `_extract_visual` used,
    gated by BOTH `use_vlm` (checked by the dispatcher before calling
    this) AND `config.ENABLE_VISUAL_VLM` — identical, deliberately
    separate opt-in to before, so enabling the VLM for formula/procedure
    fallback elsewhere never silently starts sending every visual block
    to the model too."""
    educational_object_type = "visual"
    use_table_semantics: bool = False

    def vlm_fallback(self, doc: fitz.Document, block: Block) -> Optional[Dict[str, Any]]:
        if not config.ENABLE_VISUAL_VLM:
            return None
        caption = (block.grouping_meta or {}).get("caption", "")
        region = VisualRegion(kind="figure", page=block.page, bbox=block.bbox, caption=caption,
                               extra=(block.grouping_meta or {}).get("region_extra", {}))
        if self.use_table_semantics:
            sem = semantic_processor.process_table_semantics(doc, region)
        else:
            sem = semantic_processor.process_figure_semantics(doc, region)
        sem.setdefault("confidence", 0.5)
        sem["source"] = "vlm"
        sem["recognizer"] = self.name
        sem["educational_object_type"] = self.educational_object_type
        return sem
