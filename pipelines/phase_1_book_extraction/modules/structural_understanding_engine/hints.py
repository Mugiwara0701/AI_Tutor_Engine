"""
modules/structural_understanding_engine/hints.py — M5.2C: strongly
typed hint models.

These are the ONLY hint shapes the Structural Understanding Engine
operates on internally. `modules.subject_profile_framework.models
.SubjectContribution`'s raw `Mapping[str, Any]` hint fields
(`processing_hints`, `structural_hints`, `relationship_hints`,
`validation_hints`) are never read anywhere in this package except by
`hint_resolver.HintResolver` — the sole compatibility boundary where
the generic mapping is converted into these immutable, deterministic,
serializable, versioned models. Once resolved, nothing downstream in
M5.2C ever looks at a raw mapping again.

Deliberately absent: a `SemanticHints` model. `SubjectContribution
.semantic_hints` exists on the frozen M5.2B model, but semantic
enrichment is explicitly out of scope for M5.2C (see this package's
README.md) — resolving that field into a typed model belongs to
whichever milestone actually implements semantic enrichment.

Each model recognizes a small set of well-known keys relevant to
structural understanding and carries every other key, verbatim and
untouched, in its own `extra` mapping — so a subject-profile author's
forward-looking hint data is never silently dropped, only sorted into
"M5.2C understood this" vs. "M5.2C passed this through opaquely",
exactly the same "hint, never a trigger" convention
`ProcessingContext.metadata` (M5.1) already establishes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from modules.structural_understanding_engine.exceptions import HintResolutionError

#: Default version stamped on a typed hint model that does not specify
#: its own — mirrors `modules.educational_taxonomy.models
#: .DEFAULT_TYPE_VERSION`'s own "MAJOR.MINOR.PATCH" convention.
DEFAULT_HINT_VERSION: str = "1.0.0"


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Defensive-copy helper, matching every sibling framework's own
    per-module duplication convention (see e.g.
    `subject_profile_framework.models._frozen_mapping`)."""
    return dict(value) if value else {}


def _frozen_tuple(value: Optional[Tuple[str, ...]]) -> Tuple[str, ...]:
    return tuple(value) if value else ()


@dataclass(frozen=True)
class ProcessingHints:
    """Typed view over `SubjectContribution.processing_hints` relevant
    to structural understanding.

    Attributes:
        priority: Optional processing-order hint (lower runs first),
            same convention as `EducationalObjectProcessor
            .default_priority` (M5.1) — purely informational here;
            M5.2C performs no processor scheduling itself.
        enabled: Whether this contribution's structural understanding
            should run at all. Defaults to True.
        extra: Every other key from the raw mapping, untouched.
        version: "MAJOR.MINOR.PATCH"-style string for this hint
            model's own shape.
    """

    priority: Optional[int] = None
    enabled: bool = True
    extra: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_HINT_VERSION

    def __post_init__(self) -> None:
        if self.priority is not None and not isinstance(self.priority, int):
            raise HintResolutionError(
                f"ProcessingHints.priority must be an int or None, got {type(self.priority).__name__}."
            )
        if not isinstance(self.enabled, bool):
            raise HintResolutionError(
                f"ProcessingHints.enabled must be a bool, got {type(self.enabled).__name__}."
            )
        object.__setattr__(self, "extra", _frozen_mapping(self.extra))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "priority": self.priority,
            "enabled": self.enabled,
            "extra": dict(self.extra),
            "version": self.version,
        }


@dataclass(frozen=True)
class RecognitionHints:
    """Typed view over the `"recognition"` sub-mapping nested inside
    `SubjectContribution.processing_hints` (a subject-profile author's
    forward-looking hint for a future recognizer, e.g. M5.2C+'s own
    pattern matching or a later semantic recognizer) — kept as its own
    typed model, distinct from `ProcessingHints`, exactly because
    `SubjectContribution` has no separate `recognition_hints` field of
    its own; `HintResolver` is what draws this line (see its own
    docstring for the exact convention).

    Attributes:
        aliases: Additional free-form strings a recognizer should
            treat as equivalent to this contribution's object type,
            beyond `EducationalObjectType.aliases` itself (M5.2A) —
            purely a hint; M5.2C never registers these into the
            taxonomy.
        confidence_threshold: Optional minimum confidence a future
            recognizer should require before matching this
            contribution's object type.
        extra: Every other key from the nested `"recognition"`
            mapping, untouched.
    """

    aliases: Tuple[str, ...] = field(default_factory=tuple)
    confidence_threshold: Optional[float] = None
    extra: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_HINT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "aliases", _frozen_tuple(self.aliases))
        if self.confidence_threshold is not None and not isinstance(
            self.confidence_threshold, (int, float)
        ):
            raise HintResolutionError(
                "RecognitionHints.confidence_threshold must be a number or None, "
                f"got {type(self.confidence_threshold).__name__}."
            )
        object.__setattr__(self, "extra", _frozen_mapping(self.extra))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aliases": list(self.aliases),
            "confidence_threshold": self.confidence_threshold,
            "extra": dict(self.extra),
            "version": self.version,
        }


@dataclass(frozen=True)
class StructuralHints:
    """Typed view over `SubjectContribution.structural_hints` — the
    hint field M5.2C consults most directly.

    Attributes:
        pattern_key: Optional override naming which `StructuralPattern`
            (see `patterns.py`) applies to this contribution's object
            type, instead of whatever `StructuralUnderstandingEngine`
            would otherwise infer.
        component_aliases: Maps a pattern's canonical component role
            (e.g. "solution_steps") to an alternate key a subject
            profile's own extracted content may use instead (e.g.
            "steps") — lets `StructuralObject.components` use whatever
            naming the subject's own pipeline already produces without
            forcing a rename upstream.
        extra: Every other key from the raw mapping, untouched.
    """

    pattern_key: Optional[str] = None
    component_aliases: Mapping[str, str] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_HINT_VERSION

    def __post_init__(self) -> None:
        if self.pattern_key is not None and not isinstance(self.pattern_key, str):
            raise HintResolutionError(
                f"StructuralHints.pattern_key must be a string or None, got {type(self.pattern_key).__name__}."
            )
        object.__setattr__(self, "component_aliases", _frozen_mapping(self.component_aliases))
        object.__setattr__(self, "extra", _frozen_mapping(self.extra))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_key": self.pattern_key,
            "component_aliases": dict(self.component_aliases),
            "extra": dict(self.extra),
            "version": self.version,
        }


@dataclass(frozen=True)
class ValidationHints:
    """Typed view over `SubjectContribution.validation_hints` relevant
    to structural understanding.

    Attributes:
        strict: Whether a missing required structural component
            should be reported as an ERROR (True) or a WARNING
            (False) diagnostic. `None` means "defer to the engine's
            own `StructuralUnderstandingEngineConfig
            .strict_structural_validation` default".
        required_roles: Additional component roles (beyond whatever
            the matched `StructuralPattern` itself marks required)
            this subject profile wants enforced as required for its
            own contribution.
        extra: Every other key from the raw mapping, untouched.
    """

    strict: Optional[bool] = None
    required_roles: Tuple[str, ...] = field(default_factory=tuple)
    extra: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_HINT_VERSION

    def __post_init__(self) -> None:
        if self.strict is not None and not isinstance(self.strict, bool):
            raise HintResolutionError(
                f"ValidationHints.strict must be a bool or None, got {type(self.strict).__name__}."
            )
        object.__setattr__(self, "required_roles", _frozen_tuple(self.required_roles))
        object.__setattr__(self, "extra", _frozen_mapping(self.extra))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strict": self.strict,
            "required_roles": list(self.required_roles),
            "extra": dict(self.extra),
            "version": self.version,
        }


@dataclass(frozen=True)
class RelationshipHints:
    """Typed view over `SubjectContribution.relationship_hints`.

    M5.2C resolves this hint into a typed model (per the M5.2C spec's
    explicit `HintResolver` example set) but performs no relationship
    discovery of its own — relationship discovery is M5.2E's job (see
    this package's README.md "Out of Scope"). This model exists so a
    later milestone can consume already-typed relationship hints
    without needing its own resolver.

    Attributes:
        related_keys: Object-type keys (or aliases) this contribution
            declares a forward-looking relationship to.
        extra: Every other key from the raw mapping, untouched.
    """

    related_keys: Tuple[str, ...] = field(default_factory=tuple)
    extra: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_HINT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "related_keys", _frozen_tuple(self.related_keys))
        object.__setattr__(self, "extra", _frozen_mapping(self.extra))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "related_keys": list(self.related_keys),
            "extra": dict(self.extra),
            "version": self.version,
        }


@dataclass(frozen=True)
class ResolvedHints:
    """The full bundle of typed hints `HintResolver.resolve()`
    produces for one `SubjectContribution` — what every other M5.2C
    component (engine, compatibility validator, lifecycle manager)
    actually consumes. Never constructed by hand from a raw mapping
    outside `hint_resolver.py`."""

    processing: ProcessingHints = field(default_factory=ProcessingHints)
    recognition: RecognitionHints = field(default_factory=RecognitionHints)
    structural: StructuralHints = field(default_factory=StructuralHints)
    validation: ValidationHints = field(default_factory=ValidationHints)
    relationship: RelationshipHints = field(default_factory=RelationshipHints)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processing": self.processing.to_dict(),
            "recognition": self.recognition.to_dict(),
            "structural": self.structural.to_dict(),
            "validation": self.validation.to_dict(),
            "relationship": self.relationship.to_dict(),
        }


__all__ = [
    "DEFAULT_HINT_VERSION",
    "ProcessingHints",
    "RecognitionHints",
    "StructuralHints",
    "ValidationHints",
    "RelationshipHints",
    "ResolvedHints",
]
