"""
stage_d_extraction.py — Stage D: Scoped Educational Extraction.

Responsibility (and ONLY this responsibility): extract educational
knowledge FROM educational blocks. This is the first expensive stage —
everything before it (A/B/C) is pure Python/deterministic and cheap; this
is the only stage that may call the VLM, and only for the blocks Stage C
marked worth the cost.

Input:  Priority-annotated Blocks (stage_c_priority output)
Output: Educational Objects — NOT Master JSON. Master JSON assembly belongs
        entirely to Phase 2.

Educational-Object-Aware, not subject-aware
--------------------------------------------
Stage B already tells us the block type (Formula Box, Worked Example,
Programming Syntax, Accounting Format, Table, Figure, Diagram, ...).
Stage D's job is then to pick the recognizer(s) suited to THAT block
type — never to a subject name. A book titled "Science" containing
Physics + Chemistry + Biology, or a differently-named-subject book from
another publisher, is handled identically: routing is 100% block-type
driven via modules/recognizers.

For every block type with registered candidates (see
modules/recognizers/__init__.py for the full map), Stage D:
    1. Runs every candidate recognizer's cheap deterministic `recognize()`.
    2. Picks the highest-confidence result.
    3. If that confidence is still below
       config.DETERMINISTIC_CONFIDENCE_FLOOR, calls the VLM AT MOST ONCE
       via that winning recognizer's own `vlm_fallback` (formula/procedure
       recognizers reuse the equation-semantics call; visual-family
       recognizers reuse the figure/table-semantics call gated by
       config.ENABLE_VISUAL_VLM) — exactly the same VLM call sites and
       gating the pre-modular implementation used, so re-organizing one
       big per-type branch into many small recognizers does not add any
       new VLM calls.
    4. Otherwise keeps the best deterministic result as-is.

Adding a new educational object (new formula family, new visual subtype,
...) only requires a new Recognizer + one registration line in
modules/recognizers/__init__.py — this file does not need to change.

Definition extraction (term + location, never the definition text itself)
and the Law/Summary/Activity/Ambiguous pass-through paths are unchanged in
behavior from before; Definition is now expressed as a recognizer too
(modules/recognizers/concept_recognizers.py) purely for dispatch
consistency, while Law/Summary/Activity/Ambiguous have no recognizer
because the frozen spec never defined an extraction shape for them.
"""
import logging
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

import config
from modules.stage_a_geometry import Block
from modules import recognizers

logger = logging.getLogger("ncert_pipeline.stage_d")

# Block types Stage D never spends extraction effort on, regardless of the
# priority Stage C assigned them (Stage C intentionally discards nothing;
# this is the one place that decides "worth extracting" vs "worth keeping
# around for lineage/debugging only").
_SKIP_TYPES = {"Exercise", "Homework", "Footer", "Header", "Watermark", "Reference", "Heading"}

# Below this deterministic confidence, fall back to a single VLM call
# (via the winning recognizer's own vlm_fallback) rather than trust the
# result. Configurable via config.DETERMINISTIC_CONFIDENCE_FLOOR
# (NCERT_DET_CONFIDENCE_FLOOR env var).
_DETERMINISTIC_CONFIDENCE_FLOOR = config.DETERMINISTIC_CONFIDENCE_FLOOR

# Block types with no registered recognizer that still get a lightweight,
# deterministic pass-through object (location + type only) instead of
# being silently dropped or given a made-up extraction shape — unchanged
# from the pre-modular implementation.
_UNCLASSIFIED_HIGH_VALUE_TYPES = {"Law", "Summary", "Activity"}


def _result_to_object_fields(result_data: Dict[str, Any], educational_object_type: str,
                              confidence: float, source: str, recognizer_name: str) -> Dict[str, Any]:
    out = dict(result_data)
    out["educational_object_type"] = educational_object_type
    out["confidence"] = confidence
    out["source"] = source
    out["recognizer"] = recognizer_name
    return out


def _recognize_via_registry(block: Block, doc: fitz.Document, use_vlm: bool) -> Optional[Dict[str, Any]]:
    """Runs every recognizer registered for `block.block_type`, picks the
    highest-confidence deterministic match, and escalates to that
    recognizer's own VLM fallback only when needed. Returns None when no
    recognizer at all is registered for this block_type — callers keep
    their own legacy pass-through handling for those."""
    candidates = recognizers.candidates_for(block.block_type)
    if not candidates:
        return None

    scored = []
    for rec in candidates:
        result = rec.safe_recognize(block)
        if result is not None:
            scored.append((rec, result))

    if not scored:
        # No candidate recognizer matched this block's text/caption at
        # all. Try each candidate's VLM fallback in turn (still at most
        # one VLM call, since we stop at the first one that returns
        # something) before giving up on an honestly-low-confidence
        # placeholder.
        if use_vlm:
            for rec in candidates:
                data = rec.vlm_fallback(doc, block)
                if data:
                    return data
        return {
            "educational_object_type": candidates[0].educational_object_type,
            "confidence": 0.0,
            "source": "deterministic_low_confidence",
        }

    scored.sort(key=lambda pair: pair[1].confidence, reverse=True)
    best_rec, best_result = scored[0]

    if best_result.confidence >= _DETERMINISTIC_CONFIDENCE_FLOOR:
        return _result_to_object_fields(
            best_result.data, best_result.educational_object_type,
            best_result.confidence, best_result.source, best_result.recognizer_name)

    if use_vlm:
        data = best_rec.vlm_fallback(doc, block)
        if data:
            return data

    # No VLM available/no fallback offered — still return the best
    # deterministic guess rather than silently dropping the block;
    # extraction_logs should reflect low confidence downstream.
    return _result_to_object_fields(
        best_result.data, best_result.educational_object_type,
        best_result.confidence, best_result.source, best_result.recognizer_name)


def extract_educational_objects(blocks: List[Block], doc: fitz.Document, use_vlm: bool = True,
                                 chapter_title: str = "") -> List[Dict[str, Any]]:
    """Returns a flat list of Educational Objects, one per extracted block.
    Skipped blocks (Low priority, or an explicitly-skipped type) are simply
    absent from this list — they are not discarded from the block list
    Stage C produced, only from this stage's extraction output, per the
    "Nothing is discarded [at Stage C]" / "Exercise: Skip [at Stage D]"
    split in the frozen spec."""
    objects: List[Dict[str, Any]] = []
    skipped = 0

    for block in blocks:
        if block.priority == "low" or block.block_type in _SKIP_TYPES:
            skipped += 1
            continue

        base = {
            "id": f"{block.block_id}-eo",
            "block_id": block.block_id,
            "block_type": block.block_type,
            "priority": block.priority,
            "page": block.page,
            "page_end": block.page_end,
            "bbox": {"x0": block.bbox[0], "y0": block.bbox[1], "x1": block.bbox[2], "y1": block.bbox[3]},
        }

        registry_result = _recognize_via_registry(block, doc, use_vlm)
        if registry_result is not None:
            base.update(registry_result)
        elif block.block_type in _UNCLASSIFIED_HIGH_VALUE_TYPES:
            base["educational_object_type"] = "unclassified_high_value"
            base["confidence"] = block.confidence
            base["source"] = "deterministic"
        else:  # Ambiguous, or anything else that reached here
            base["educational_object_type"] = "ambiguous"
            base["confidence"] = block.confidence
            base["source"] = "deterministic"

        objects.append(base)

    logger.info("Stage D: extracted %d educational object(s), skipped %d low-value block(s).",
                len(objects), skipped)
    return objects
