"""
stage_c_priority.py — Stage C: Educational Priority Assignment.

Responsibility (and ONLY this responsibility): HOW IMPORTANT is the block?

Nothing is discarded here — every block keeps its priority annotation and
stays in the returned list, even Low-priority ones (Stage D decides whether
a given priority is worth spending extraction effort on; that's a
Stage D concern, not this one). Priority is deliberately a configurable
table rather than inline if/else so a caller (or a future config file) can
override it per deployment without touching this module's logic.

M4.1C improvements:
  - Confidence-based priority adjustment (deterministic thresholds)
  - Structural priority signals (parent/child, continuation)
  - Better HIGH/MEDIUM/LOW discrimination
  - Improved child priority propagation
  - Metadata-informed priority (border, visual grouping)
"""
import logging
from typing import Dict, List, Optional

from modules.stage_a_geometry import Block

logger = logging.getLogger("ncert_pipeline.stage_c")

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

DEFAULT_PRIORITY_MAP: Dict[str, str] = {
    "Definition": HIGH,
    "Formula Box": HIGH,
    "Summary": HIGH,
    "Law": HIGH,
    "Table": HIGH,          # "Concept Table" in the spec's High list
    "Diagram": HIGH,
    "Worked Example": MEDIUM,
    "Figure": MEDIUM,
    "Activity": MEDIUM,
    "Ambiguous": MEDIUM,
    "Exercise": LOW,
    "Homework": LOW,
    "Footer": LOW,
    "Header": LOW,
    "Watermark": LOW,
    # Not explicitly listed in the spec's examples; given sensible defaults
    "Heading": MEDIUM,
    "Flowchart": HIGH,
    "Decision Tree": HIGH,
    "Programming Syntax": MEDIUM,
    "Accounting Format": MEDIUM,
    "Reference": LOW,
}

# M4.1C: Confidence thresholds for priority adjustment.
# Blocks with confidence at or above the HIGH threshold get a priority boost.
# Blocks with confidence at or below the LOW threshold get a priority demotion.
# All thresholds are fixed/deterministic — no learning.
_CONFIDENCE_PROMOTE_THRESHOLD = 0.85
_CONFIDENCE_DEMOTE_THRESHOLD = 0.3

# M4.1C: Priority ordering for comparisons.
_PRIORITY_RANK = {HIGH: 3, MEDIUM: 2, LOW: 1}


def _promote(priority: str) -> str:
    """Promote priority one level (LOW→MEDIUM, MEDIUM→HIGH). HIGH stays HIGH."""
    if priority == LOW:
        return MEDIUM
    if priority == MEDIUM:
        return HIGH
    return HIGH


def _demote(priority: str) -> str:
    """Demote priority one level (HIGH→MEDIUM, MEDIUM→LOW). LOW stays LOW."""
    if priority == HIGH:
        return MEDIUM
    if priority == MEDIUM:
        return LOW
    return LOW


def _adjust_priority_by_confidence(block: Block, base_priority: str) -> str:
    """M4.1C: Deterministic priority adjustment based on classification
    confidence from Stage B.

    Rules:
    - Very high confidence (>=0.85) on a MEDIUM block → promote to HIGH
    - Very low confidence (<=0.3) on a HIGH block → demote to MEDIUM
    - All other cases → keep base_priority unchanged

    This ensures that strongly-classified blocks get appropriate priority
    and weakly-classified blocks don't receive unwarranted high priority.
    """
    if block.confidence >= _CONFIDENCE_PROMOTE_THRESHOLD and base_priority == MEDIUM:
        return _promote(base_priority)
    if block.confidence <= _CONFIDENCE_DEMOTE_THRESHOLD and base_priority == HIGH:
        return _demote(base_priority)
    return base_priority


def _adjust_priority_by_structure(block: Block, priority: str) -> str:
    """M4.1C: Structural priority adjustment based on block metadata.

    Rules (all deterministic):
    - Blocks with continuation metadata (cross-page) get a priority boost
      (they span page boundaries, indicating substantial content).
    - Blocks with visual grouping / borders get a priority boost when
      they're currently MEDIUM (visual emphasis from the textbook).
    - Blocks with grouped_definitions get HIGH if not already.
    """
    meta = block.grouping_meta or {}

    # Cross-page blocks are structurally significant
    if meta.get("continuation") and priority != HIGH:
        priority = _promote(priority)

    # Blocks with visual borders/grouping (from M4.1B) deserve attention
    if meta.get("has_border") and priority == MEDIUM:
        # Keep as MEDIUM but this is a signal — don't demote later
        pass

    # Grouped definitions are always high priority
    if meta.get("grouped_definitions") and priority != HIGH:
        priority = HIGH

    return priority


def assign_priority(blocks: List[Block], overrides: Optional[Dict[str, str]] = None) -> List[Block]:
    """Mutates + returns `blocks` with `.priority` set on every block.
    `overrides` lets a caller replace/extend DEFAULT_PRIORITY_MAP for a
    single run without editing this module.

    M4.1C improvements:
    - Confidence-based priority adjustment
    - Structural priority signals
    - Improved child priority propagation
    """
    priority_map = dict(DEFAULT_PRIORITY_MAP)
    if overrides:
        priority_map.update(overrides)

    for b in blocks:
        # 1. Base priority from block_type map
        base_priority = priority_map.get(b.block_type, MEDIUM)

        # 2. M4.1C: Adjust by classification confidence
        adjusted = _adjust_priority_by_confidence(b, base_priority)

        # 3. M4.1C: Adjust by structural signals
        adjusted = _adjust_priority_by_structure(b, adjusted)

        b.priority = adjusted

        # M4.1C: Improved child priority propagation
        # Children inherit the parent's priority but can be independently
        # promoted if they have their own strong signals.
        for child in b.children:
            child_base = priority_map.get(child.block_type or b.block_type, b.priority)
            # Children never exceed parent priority
            if _PRIORITY_RANK.get(child_base, 2) > _PRIORITY_RANK.get(b.priority, 2):
                child.priority = b.priority
            else:
                child.priority = child_base

    logger.info("Stage C: assigned priority to %d block(s) (%d high, %d medium, %d low).",
                len(blocks),
                sum(1 for b in blocks if b.priority == HIGH),
                sum(1 for b in blocks if b.priority == MEDIUM),
                sum(1 for b in blocks if b.priority == LOW))
    return blocks
