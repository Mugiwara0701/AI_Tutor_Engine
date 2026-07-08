"""
modules/recognizers/registry.py — the block_type -> candidate recognizer
map Stage D dispatches through.

Deliberately a plain data-driven map (same pattern as
stage_c_priority.DEFAULT_PRIORITY_MAP), keyed by Stage B `block_type`
STRINGS only — never by subject name. This is the one place that decides
"which recognizers get a chance to look at a block of type X"; everything
about HOW a recognizer decides "yes, this is mine, with confidence C"
lives entirely inside that recognizer, not here.
"""
import logging
from typing import Dict, List

from modules.recognizers.base import Recognizer

logger = logging.getLogger("ncert_pipeline.stage_d.recognizers")

_REGISTRY: Dict[str, List[Recognizer]] = {}


def register(recognizer: Recognizer, block_types: List[str]) -> None:
    """Registers `recognizer` as a candidate for every block_type in
    `block_types`. Safe to call the same recognizer instance multiple
    times for different block_type lists (several modules in this package
    do exactly that, e.g. FormulaRecognizer is a candidate for both
    "Formula Box" and "Worked Example")."""
    for bt in block_types:
        _REGISTRY.setdefault(bt, []).append(recognizer)


def candidates_for(block_type: str) -> List[Recognizer]:
    """Returns the (possibly empty) list of candidate recognizers for a
    Stage B block_type. An empty list means "no recognizer registered for
    this type" — callers (stage_d_extraction) fall back to their own
    legacy/pass-through handling for those, unchanged."""
    return list(_REGISTRY.get(block_type, ()))


def registered_block_types() -> List[str]:
    return list(_REGISTRY.keys())
