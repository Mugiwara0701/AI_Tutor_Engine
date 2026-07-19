"""
modules/subject_profile_framework/enums.py — M5.2B: closed vocabularies
for Subject Profile metadata.

M5.2A's `EducationalObjectType` was originally envisioned to carry
richer metadata directly (symbolic content, copyright sensitivity,
structural/semantic/relationship support) — see M5.2A's frozen
`models.py`. That metadata was never actually implemented before
M5.2A was frozen, so it is defined here instead, as an M5.2B-owned
layer that sits *beside* the frozen taxonomy rather than inside it.
`modules.educational_taxonomy.models.EducationalObjectType` is not
modified, imported into, or subclassed here.

Mirrors this repository's existing convention (see
`modules.educational_taxonomy.enums`,
`modules.educational_object_framework.enums`): str-backed `Enum`s,
JSON-serializable via `.value`, directly comparable against the
equivalent string.
"""
from __future__ import annotations

from enum import Enum


class CopyrightSensitivity(str, Enum):
    """How likely a contributed educational object type is to carry
    third-party copyrighted material verbatim (e.g. a reproduced poem,
    a quoted primary source, a licensed diagram) — a hint for later
    copyright-safe-normalization milestones (M5.2C+, out of scope
    here), not an enforcement mechanism in this package."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class SupportLevel(str, Enum):
    """How much a contributed educational object type is expected to
    participate in a later structural/semantic/relationship engine
    (M5.2C–E, out of scope here) — purely a forward-looking hint a
    subject profile author attaches now, not a guarantee anything
    downstream currently reads it."""

    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


#: Ordering used by `registry.contributions_supporting()` to compare a
#: contribution's declared SupportLevel against a queried minimum,
#: since a plain str-Enum has no inherent ordering of its own.
_SUPPORT_LEVEL_ORDER = {
    SupportLevel.NONE: 0,
    SupportLevel.PARTIAL: 1,
    SupportLevel.FULL: 2,
}


def support_at_least(level: "SupportLevel", minimum: "SupportLevel") -> bool:
    """True if `level` meets or exceeds `minimum` on the fixed
    NONE < PARTIAL < FULL scale."""
    return _SUPPORT_LEVEL_ORDER[level] >= _SUPPORT_LEVEL_ORDER[minimum]


__all__ = [
    "CopyrightSensitivity",
    "SupportLevel",
    "support_at_least",
]
