"""
modules/educational_taxonomy/enums.py — M5.2A: the seven canonical
top-level categories of the Universal Educational Taxonomy.

Mirrors modules/educational_object_framework/enums.py's own
convention in this project: a str-backed Enum, JSON-serializable via
`.value`, directly comparable against the equivalent string.

Deliberately absent: any subject-specific category (Physics, Math,
History, ...) and any concrete object-type name (Concept, Figure,
MCQ, ...). Categories are the fixed, curriculum-independent top level
of the taxonomy; concrete object *types* (which belong to exactly one
category) live in `models.EducationalObjectType` / `catalog.py`, and
subject-specific profiles are explicitly out of scope for this
milestone (M5.2B).
"""
from __future__ import annotations

from enum import Enum


class EducationalCategory(str, Enum):
    """The seven canonical, curriculum-independent top-level
    categories every educational object type in the taxonomy belongs
    to exactly one of. Fixed for this milestone — a category is a
    structural classification of *kind of educational content*, not a
    subject or a curriculum, so this set is expected to stay closed
    even as `catalog.py`'s object types grow across future curricula
    (CBSE, ICSE, IB, undergraduate, ...) and future milestones
    (M5.2B+)."""

    KNOWLEDGE = "knowledge_objects"
    REASONING = "reasoning_objects"
    VISUAL = "visual_objects"
    STRUCTURED = "structured_objects"
    LEARNING = "learning_objects"
    ASSESSMENT = "assessment_objects"
    LANGUAGE = "language_objects"


__all__ = [
    "EducationalCategory",
]
