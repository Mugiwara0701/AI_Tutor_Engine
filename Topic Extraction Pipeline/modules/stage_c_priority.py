"""
stage_c_priority.py — Stage C: Educational Priority Assignment.

Responsibility (and ONLY this responsibility): HOW IMPORTANT is the block?

Nothing is discarded here — every block keeps its priority annotation and
stays in the returned list, even Low-priority ones (Stage D decides whether
a given priority is worth spending extraction effort on; that's a
Stage D concern, not this one). Priority is deliberately a configurable
table rather than inline if/else so a caller (or a future config file) can
override it per deployment without touching this module's logic.
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
    # rather than left unhandled so every possible Stage B output always
    # gets an explicit, auditable priority instead of silently falling
    # through to a generic default deep inside assign_priority().
    "Heading": MEDIUM,
    "Flowchart": HIGH,
    "Decision Tree": HIGH,
    "Programming Syntax": MEDIUM,
    "Accounting Format": MEDIUM,
    "Reference": LOW,
}


def assign_priority(blocks: List[Block], overrides: Optional[Dict[str, str]] = None) -> List[Block]:
    """Mutates + returns `blocks` with `.priority` set on every block.
    `overrides` lets a caller replace/extend DEFAULT_PRIORITY_MAP for a
    single run without editing this module (e.g. a subject that wants
    Exercises promoted to Medium for quiz-generation reuse in a later
    phase)."""
    priority_map = dict(DEFAULT_PRIORITY_MAP)
    if overrides:
        priority_map.update(overrides)

    for b in blocks:
        b.priority = priority_map.get(b.block_type, MEDIUM)
        for child in b.children:
            child.priority = b.priority  # children inherit the parent's priority; never independently discarded

    logger.info("Stage C: assigned priority to %d block(s) (%d high, %d medium, %d low).",
                len(blocks),
                sum(1 for b in blocks if b.priority == HIGH),
                sum(1 for b in blocks if b.priority == MEDIUM),
                sum(1 for b in blocks if b.priority == LOW))
    return blocks
