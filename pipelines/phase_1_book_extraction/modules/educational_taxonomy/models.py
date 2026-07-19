"""
modules/educational_taxonomy/models.py — M5.2A: `EducationalObjectType`,
the immutable, strongly-typed entry every canonical educational object
kind in the Universal Educational Taxonomy is represented as.

Design note — data catalog entry, not a processing payload: unlike
`educational_object_framework.models.ProcessingResult` (a report
produced by running a processor), an `EducationalObjectType` is a
static, versioned catalog entry — it describes *a kind of educational
object that can exist* ("Concept", "Theorem", "MCQ", ...), not any
particular instance of one. Nothing in this module processes,
recognizes, or extracts anything; that is explicitly out of scope for
this milestone (see this package's README.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.exceptions import TaxonomyValidationError

#: Canonical key form: lowercase snake_case, starting with a letter.
#: Enforced so every `EducationalObjectType.key` is stable, predictable,
#: and safe to use as a dict key / URN segment / JSON field name
#: without further sanitization.
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

#: Default version stamped on a taxonomy entry that does not specify
#: its own — mirrors this repository's existing `schema_version`
#: convention (see `schemas/canonical_base.py`,
#: `schemas/chapter_schema.py`: a plain "MAJOR.MINOR.PATCH" string,
#: not a framework-specific versioning scheme).
DEFAULT_TYPE_VERSION: str = "1.0.0"


def _frozen_aliases(value: Optional[Tuple[str, ...]]) -> Tuple[str, ...]:
    return tuple(value) if value else ()


@dataclass(frozen=True)
class EducationalObjectType:
    """One canonical entry in the Universal Educational Taxonomy.

    Attributes:
        key: Canonical, stable, machine-readable identifier —
            lowercase snake_case (e.g. "concept", "worked_example",
            "assertion_reason"). This is the identity of the type:
            uniqueness is enforced on `key` alone by
            `registry.TaxonomyRegistry`, never on `display_name`.
        category: Which of the seven `EducationalCategory` values this
            type belongs to. Exactly one — the taxonomy is a strict
            partition, not a multi-category tagging scheme.
        display_name: Human-readable label (e.g. "Concept", "Worked
            Example"). Purely presentational; never used for identity
            or lookup.
        description: A short, curriculum-independent description of
            what this object type represents.
        aliases: Optional additional machine-readable strings that
            should resolve to this same type (e.g. a future
            recognizer emitting "worked_problem" instead of
            "worked_example"). Purely a lookup convenience — never
            used to establish identity or uniqueness by itself.
        version: "MAJOR.MINOR.PATCH"-style string marking when this
            entry was introduced or last structurally changed —
            mirrors this repository's existing `schema_version`
            convention rather than inventing a new one. Defaults to
            `DEFAULT_TYPE_VERSION`.
    """

    key: str
    category: EducationalCategory
    display_name: str
    description: str
    aliases: Tuple[str, ...] = field(default_factory=tuple)
    version: str = DEFAULT_TYPE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise TaxonomyValidationError("EducationalObjectType.key must be a non-empty string.")
        if not _KEY_PATTERN.match(self.key):
            raise TaxonomyValidationError(
                f"EducationalObjectType.key {self.key!r} must be lowercase snake_case "
                "(e.g. 'concept', 'worked_example')."
            )
        if not isinstance(self.category, EducationalCategory):
            raise TaxonomyValidationError(
                "EducationalObjectType.category must be an EducationalCategory, "
                f"got {type(self.category).__name__}."
            )
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise TaxonomyValidationError("EducationalObjectType.display_name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise TaxonomyValidationError("EducationalObjectType.description must be a non-empty string.")
        if not isinstance(self.version, str) or not self.version:
            raise TaxonomyValidationError("EducationalObjectType.version must be a non-empty string.")

        object.__setattr__(self, "aliases", _frozen_aliases(self.aliases))
        for alias in self.aliases:
            if not isinstance(alias, str) or not _KEY_PATTERN.match(alias):
                raise TaxonomyValidationError(
                    f"EducationalObjectType({self.key}).aliases entry {alias!r} must be "
                    "lowercase snake_case, same as `key`."
                )
        if self.key in self.aliases:
            raise TaxonomyValidationError(
                f"EducationalObjectType({self.key}).aliases must not repeat `key` itself."
            )

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic, JSON-safe representation — field order is
        fixed (declaration order) and every value is already a plain
        `str`/`tuple`/`list`, so two calls for the same entry always
        produce identical output, and `json.dumps(..., sort_keys=True)`
        on the result is stable across runs and interpreters."""
        return {
            "key": self.key,
            "category": self.category.value,
            "display_name": self.display_name,
            "description": self.description,
            "aliases": list(self.aliases),
            "version": self.version,
        }


__all__ = [
    "EducationalObjectType",
    "DEFAULT_TYPE_VERSION",
]
