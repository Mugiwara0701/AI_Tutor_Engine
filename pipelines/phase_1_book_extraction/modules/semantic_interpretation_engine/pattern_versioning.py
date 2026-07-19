"""
modules/semantic_interpretation_engine/pattern_versioning.py — M5.2D
Deliverable #4: Versioned Structural Pattern Interpretation.

Wraps M5.2C's StructuralPattern with a semantic evolution layer.
StructuralPattern itself is NOT modified; PatternVersionRegistry holds
PatternVersion entries that attach semantic metadata and version history
above M5.2C's frozen structural layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from modules.structural_understanding_engine.patterns import StructuralPattern

from modules.semantic_interpretation_engine.exceptions import PatternVersionError

__all__ = [
    "PatternVersion",
    "PatternMetadata",
    "PatternCompatibility",
    "PatternSelection",
    "PatternVersionRegistry",
    "DEFAULT_PATTERN_SEMANTIC_VERSION",
]

DEFAULT_PATTERN_SEMANTIC_VERSION = "1.0.0"

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_version(v: str, *, field_name: str) -> Tuple[int, int, int]:
    if not _VERSION_RE.match(v):
        raise PatternVersionError(
            f"{field_name} must be 'MAJOR.MINOR.PATCH'; got {v!r}."
        )
    major, minor, patch = v.split(".")
    return int(major), int(minor), int(patch)


@dataclass(frozen=True)
class PatternMetadata:
    """
    Semantic metadata attached to a specific version of a StructuralPattern.

    Attributes:
        description:         Human-readable description of the pattern's
                             educational purpose.
        typical_object_types:
                             EducationalObjectType keys this pattern is
                             commonly used with.
        change_notes:        What changed relative to the previous version.
        deprecated:          If True, prefer a newer version of this pattern.
        deprecation_reason:  Explanation if deprecated is True.
    """

    description: str = ""
    typical_object_types: Tuple[str, ...] = field(default_factory=tuple)
    change_notes: str = ""
    deprecated: bool = False
    deprecation_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "typical_object_types", tuple(self.typical_object_types))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "typical_object_types": list(self.typical_object_types),
            "change_notes": self.change_notes,
            "deprecated": self.deprecated,
            "deprecation_reason": self.deprecation_reason,
        }


@dataclass(frozen=True)
class PatternCompatibility:
    """
    Version-range compatibility declaration for a PatternVersion.

    Attributes:
        minimum_engine_version:  Minimum M5.2D engine version required.
        maximum_engine_version:  Maximum M5.2D engine version supported
                                 (inclusive; "" means no upper bound).
    """

    minimum_engine_version: str = "1.0.0"
    maximum_engine_version: str = ""

    def __post_init__(self) -> None:
        _parse_version(self.minimum_engine_version, field_name="minimum_engine_version")
        if self.maximum_engine_version:
            _parse_version(self.maximum_engine_version, field_name="maximum_engine_version")
            min_t = _parse_version(self.minimum_engine_version, field_name="minimum_engine_version")
            max_t = _parse_version(self.maximum_engine_version, field_name="maximum_engine_version")
            if min_t > max_t:
                raise PatternVersionError(
                    f"minimum_engine_version {self.minimum_engine_version!r} "
                    f"exceeds maximum_engine_version {self.maximum_engine_version!r}."
                )

    def accepts(self, engine_version: str) -> bool:
        """Return True if *engine_version* falls within this compatibility range."""
        try:
            ev = _parse_version(engine_version, field_name="engine_version")
        except PatternVersionError:
            return False
        min_t = _parse_version(self.minimum_engine_version, field_name="minimum_engine_version")
        if ev < min_t:
            return False
        if self.maximum_engine_version:
            max_t = _parse_version(self.maximum_engine_version, field_name="maximum_engine_version")
            if ev > max_t:
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "minimum_engine_version": self.minimum_engine_version,
            "maximum_engine_version": self.maximum_engine_version,
        }


@dataclass(frozen=True)
class PatternVersion:
    """
    A versioned semantic interpretation entry for a StructuralPattern.

    Attributes:
        pattern_key:     Matches StructuralPattern.pattern_key (M5.2C).
        semantic_version:
                         Semantic version of THIS interpretation layer
                         (independent of StructuralPattern.version).
        metadata:        PatternMetadata for this version.
        compatibility:   Engine version range where this entry is valid.
    """

    pattern_key: str
    semantic_version: str
    metadata: PatternMetadata = field(default_factory=PatternMetadata)
    compatibility: PatternCompatibility = field(default_factory=PatternCompatibility)

    def __post_init__(self) -> None:
        if not self.pattern_key:
            raise PatternVersionError("PatternVersion.pattern_key must not be empty.")
        _parse_version(self.semantic_version, field_name="semantic_version")

    def is_compatible_with_engine(self, engine_version: str) -> bool:
        return self.compatibility.accepts(engine_version)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_key": self.pattern_key,
            "semantic_version": self.semantic_version,
            "metadata": self.metadata.to_dict(),
            "compatibility": self.compatibility.to_dict(),
        }


@dataclass(frozen=True)
class PatternSelection:
    """
    The result of selecting the best PatternVersion for a given object
    and engine version.

    Attributes:
        pattern_key:      The selected StructuralPattern key.
        pattern_version:  The selected PatternVersion entry.
        engine_version:   The engine version used for selection.
        fallback_used:    True if no versioned entry matched and a fallback
                          was applied.
    """

    pattern_key: str
    pattern_version: PatternVersion
    engine_version: str
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_key": self.pattern_key,
            "pattern_version": self.pattern_version.to_dict(),
            "engine_version": self.engine_version,
            "fallback_used": self.fallback_used,
        }


class PatternVersionRegistry:
    """
    Registry of PatternVersion entries keyed by (pattern_key, semantic_version).

    Does NOT modify StructuralPatternRegistry or StructuralPattern.
    It provides a semantic interpretation layer ABOVE M5.2C's structural
    layer.
    """

    def __init__(self) -> None:
        # (pattern_key, semantic_version) → PatternVersion
        self._entries: Dict[Tuple[str, str], PatternVersion] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, entry: PatternVersion) -> None:
        """Register a PatternVersion.  Duplicate (key, version) raises."""
        k = (entry.pattern_key, entry.semantic_version)
        if k in self._entries:
            raise PatternVersionError(
                f"PatternVersion ({entry.pattern_key!r}, {entry.semantic_version!r}) "
                f"is already registered."
            )
        self._entries[k] = entry

    def unregister(self, pattern_key: str, semantic_version: str) -> None:
        k = (pattern_key, semantic_version)
        if k not in self._entries:
            raise PatternVersionError(
                f"PatternVersion ({pattern_key!r}, {semantic_version!r}) is not registered."
            )
        del self._entries[k]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, pattern_key: str, semantic_version: str) -> PatternVersion:
        k = (pattern_key, semantic_version)
        if k not in self._entries:
            raise PatternVersionError(
                f"PatternVersion ({pattern_key!r}, {semantic_version!r}) not found."
            )
        return self._entries[k]

    def versions_for(self, pattern_key: str) -> List[PatternVersion]:
        """Return all registered versions for *pattern_key*, newest first."""
        matches = [v for (pk, _), v in self._entries.items() if pk == pattern_key]
        return sorted(
            matches,
            key=lambda pv: _parse_version(pv.semantic_version, field_name="semantic_version"),
            reverse=True,
        )

    def select(self, pattern_key: str, engine_version: str) -> PatternSelection:
        """
        Select the best (newest compatible, non-deprecated) PatternVersion
        for *pattern_key* and *engine_version*.

        Falls back to the newest version if none is strictly compatible.
        """
        candidates = self.versions_for(pattern_key)
        if not candidates:
            raise PatternVersionError(
                f"No PatternVersion entries registered for pattern_key={pattern_key!r}."
            )

        # Prefer newest compatible, non-deprecated
        for pv in candidates:
            if pv.is_compatible_with_engine(engine_version) and not pv.metadata.deprecated:
                return PatternSelection(
                    pattern_key=pattern_key,
                    pattern_version=pv,
                    engine_version=engine_version,
                    fallback_used=False,
                )

        # Fallback: newest version regardless
        return PatternSelection(
            pattern_key=pattern_key,
            pattern_version=candidates[0],
            engine_version=engine_version,
            fallback_used=True,
        )

    def all_entries(self) -> List[PatternVersion]:
        return list(self._entries.values())

    def __contains__(self, item: Tuple[str, str]) -> bool:
        return item in self._entries

    def __len__(self) -> int:
        return len(self._entries)


#: Module-level singleton — callers can register entries here or
#: create their own isolated registry for testing.
default_pattern_version_registry = PatternVersionRegistry()
