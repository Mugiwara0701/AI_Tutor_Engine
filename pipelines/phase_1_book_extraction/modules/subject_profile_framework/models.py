"""
modules/subject_profile_framework/models.py — M5.2B: `SubjectContribution`
and `SubjectProfile`, the immutable, strongly-typed value objects a
Subject Profile is built from.

Design note — augmentation, not a second ontology: a `SubjectContribution`
does not define a new kind of educational object identity. It *wraps*
one real `modules.educational_taxonomy.models.EducationalObjectType` —
the same frozen model M5.2A defines, registered into the same frozen
`TaxonomyRegistry` via the same `register()` call M5.2A already
provides — and attaches the M5.2B-owned metadata layer (symbolic
content, copyright sensitivity, structural/semantic/relationship
support, and free-form hint mappings) that M5.2A's spec once
envisioned living on `EducationalObjectType` itself but never actually
implemented. `EducationalObjectType` is used here exactly as it is;
nothing in this module subclasses or monkeypatches it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.models import DEFAULT_TYPE_VERSION, EducationalObjectType

from modules.subject_profile_framework.enums import CopyrightSensitivity, SupportLevel
from modules.subject_profile_framework.exceptions import SubjectContributionValidationError

#: Default version stamped on a contribution/profile that does not
#: specify its own — mirrors `modules.educational_taxonomy.models
#: .DEFAULT_TYPE_VERSION`'s own "MAJOR.MINOR.PATCH" convention rather
#: than inventing a new versioning scheme.
DEFAULT_CONTRIBUTION_VERSION: str = "1.0.0"
DEFAULT_PROFILE_VERSION: str = "1.0.0"

#: Reused by `registry.py` / `validation.py` for the subject_key form
#: check — the same canonical shape `EducationalObjectType.key` already
#: enforces, applied to subject identifiers instead of object-type
#: identifiers.
import re as _re

_SUBJECT_KEY_PATTERN = _re.compile(r"^[a-z][a-z0-9_]*$")


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Defensive-copy helper, matching
    `educational_object_framework.base._frozen_mapping` /
    `educational_object_framework.models._frozen_mapping`'s own
    per-module duplication convention."""
    return dict(value) if value else {}


def _validate_subject_key(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise SubjectContributionValidationError(f"{field_name} must be a non-empty string.")
    if not _SUBJECT_KEY_PATTERN.match(value):
        raise SubjectContributionValidationError(
            f"{field_name} {value!r} must be lowercase snake_case (e.g. 'mathematics', "
            "'computer_science')."
        )


@dataclass(frozen=True)
class SubjectContribution:
    """One subject-specific contribution to the Universal Educational
    Taxonomy: a real `EducationalObjectType` plus the M5.2B metadata
    layer describing how a subject profile expects it to be treated by
    later milestones.

    Attributes:
        subject_key: Which subject profile this contribution belongs
            to (e.g. "mathematics", "physics") — must match the
            owning `SubjectProfile.subject_key`; enforced by
            `SubjectProfile.__post_init__`, not here, since a bare
            `SubjectContribution` has no owning profile to check
            against yet.
        object_type: The canonical `EducationalObjectType` this
            contribution registers into the frozen taxonomy — used
            exactly as M5.2A defines it, including its own `aliases`
            for recognition-alias support. This is the sole source of
            the contribution's category and object identity; nothing
            in this class re-derives or overrides either.
        symbolic_content: Whether instances of this object type are
            expected to carry symbolic/notational content (e.g. a
            LaTeX equation, a chemical formula) that a later
            structural engine (M5.2C+) may need to treat specially.
        copyright_sensitivity: How likely instances are to reproduce
            third-party copyrighted material verbatim.
        structural_support / semantic_support / relationship_support:
            Forward-looking hints for the M5.2C (Structural
            Understanding), M5.2D (Semantic Enrichment), and M5.2E
            (Relationship Discovery) engines respectively — this
            milestone implements none of those engines; it only lets
            a subject profile author declare the hint now.
        processing_hints / structural_hints / semantic_hints /
        relationship_hints / validation_hints: Free-form,
            subject-profile-specific mappings, opaque to this
            framework — never inspected or parsed by anything in this
            package, same "hint, never a trigger" convention as
            `ProcessingContext.metadata` (M5.1).
        version: "MAJOR.MINOR.PATCH"-style string for this
            contribution's own metadata shape (independent of
            `object_type.version`, which versions the taxonomy entry
            itself).
    """

    subject_key: str
    object_type: EducationalObjectType
    symbolic_content: bool = False
    copyright_sensitivity: CopyrightSensitivity = CopyrightSensitivity.NONE
    structural_support: SupportLevel = SupportLevel.NONE
    semantic_support: SupportLevel = SupportLevel.NONE
    relationship_support: SupportLevel = SupportLevel.NONE
    processing_hints: Mapping[str, Any] = field(default_factory=dict)
    structural_hints: Mapping[str, Any] = field(default_factory=dict)
    semantic_hints: Mapping[str, Any] = field(default_factory=dict)
    relationship_hints: Mapping[str, Any] = field(default_factory=dict)
    validation_hints: Mapping[str, Any] = field(default_factory=dict)
    version: str = DEFAULT_CONTRIBUTION_VERSION

    def __post_init__(self) -> None:
        _validate_subject_key(self.subject_key, field_name="SubjectContribution.subject_key")
        if not isinstance(self.object_type, EducationalObjectType):
            raise SubjectContributionValidationError(
                "SubjectContribution.object_type must be an EducationalObjectType instance, "
                f"got {type(self.object_type).__name__}."
            )
        for enum_field, enum_type in (
            ("copyright_sensitivity", CopyrightSensitivity),
            ("structural_support", SupportLevel),
            ("semantic_support", SupportLevel),
            ("relationship_support", SupportLevel),
        ):
            value = getattr(self, enum_field)
            if not isinstance(value, enum_type):
                raise SubjectContributionValidationError(
                    f"SubjectContribution.{enum_field} must be a {enum_type.__name__}, "
                    f"got {type(value).__name__}."
                )
        if not isinstance(self.symbolic_content, bool):
            raise SubjectContributionValidationError(
                "SubjectContribution.symbolic_content must be a bool, "
                f"got {type(self.symbolic_content).__name__}."
            )
        if not isinstance(self.version, str) or not self.version:
            raise SubjectContributionValidationError(
                "SubjectContribution.version must be a non-empty string."
            )
        for hints_field in (
            "processing_hints", "structural_hints", "semantic_hints",
            "relationship_hints", "validation_hints",
        ):
            object.__setattr__(self, hints_field, _frozen_mapping(getattr(self, hints_field)))

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic, JSON-safe representation — fixed field
        order, mirroring `EducationalObjectType.to_dict()`'s own
        contract. `object_type` is embedded via its own `to_dict()`
        rather than duplicated by hand."""
        return {
            "subject_key": self.subject_key,
            "object_type": self.object_type.to_dict(),
            "symbolic_content": self.symbolic_content,
            "copyright_sensitivity": self.copyright_sensitivity.value,
            "structural_support": self.structural_support.value,
            "semantic_support": self.semantic_support.value,
            "relationship_support": self.relationship_support.value,
            "processing_hints": dict(self.processing_hints),
            "structural_hints": dict(self.structural_hints),
            "semantic_hints": dict(self.semantic_hints),
            "relationship_hints": dict(self.relationship_hints),
            "validation_hints": dict(self.validation_hints),
            "version": self.version,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "SubjectContribution":
        """Reconstructs a `SubjectContribution` from `to_dict()`'s own
        output shape. Raises `SubjectContributionValidationError` (via
        `__post_init__`) or the underlying taxonomy's own
        `TaxonomyValidationError` (via `EducationalObjectType`'s own
        construction) for malformed input, rather than a raw
        `KeyError`/`ValueError` — same "fail with a specific,
        catchable exception" convention as the rest of this
        framework."""
        try:
            object_type_data = data["object_type"]
            object_type = EducationalObjectType(
                key=object_type_data["key"],
                category=EducationalCategory(object_type_data["category"]),
                display_name=object_type_data["display_name"],
                description=object_type_data["description"],
                aliases=tuple(object_type_data.get("aliases", ())),
                version=object_type_data.get("version", DEFAULT_TYPE_VERSION),
            )
            return SubjectContribution(
                subject_key=data["subject_key"],
                object_type=object_type,
                symbolic_content=data.get("symbolic_content", False),
                copyright_sensitivity=CopyrightSensitivity(
                    data.get("copyright_sensitivity", CopyrightSensitivity.NONE.value)
                ),
                structural_support=SupportLevel(data.get("structural_support", SupportLevel.NONE.value)),
                semantic_support=SupportLevel(data.get("semantic_support", SupportLevel.NONE.value)),
                relationship_support=SupportLevel(data.get("relationship_support", SupportLevel.NONE.value)),
                processing_hints=data.get("processing_hints", {}),
                structural_hints=data.get("structural_hints", {}),
                semantic_hints=data.get("semantic_hints", {}),
                relationship_hints=data.get("relationship_hints", {}),
                validation_hints=data.get("validation_hints", {}),
                version=data.get("version", DEFAULT_CONTRIBUTION_VERSION),
            )
        except KeyError as exc:
            raise SubjectContributionValidationError(
                f"SubjectContribution.from_dict() input is missing required field: {exc}."
            ) from exc


@dataclass(frozen=True)
class SubjectProfile:
    """A named, versioned bundle of `SubjectContribution` entries for
    one subject (e.g. "mathematics", "history"). Registering a
    `SubjectProfile` (via `registry.SubjectProfileRegistry.register()`)
    is what actually extends the frozen taxonomy — a bare
    `SubjectProfile` instance is inert data until registered.

    Attributes:
        subject_key: Canonical, stable, machine-readable identifier
            for this subject (lowercase snake_case, e.g.
            "mathematics", "computer_science", "political_science").
            This is the profile's identity: uniqueness is enforced on
            `subject_key` by `SubjectProfileRegistry`, never on
            `display_name`.
        display_name: Human-readable label (e.g. "Mathematics").
            Purely presentational.
        description: A short description of the subject this profile
            covers.
        contributions: Every `SubjectContribution` this profile
            declares. Order here is authoring order, not a contract —
            `SubjectProfileRegistry` re-sorts deterministically on
            read (see `registry.py`).
        version: "MAJOR.MINOR.PATCH"-style string for this profile as
            a whole, independent of any individual contribution's own
            `version`.
    """

    subject_key: str
    display_name: str
    description: str
    contributions: Tuple[SubjectContribution, ...] = field(default_factory=tuple)
    version: str = DEFAULT_PROFILE_VERSION

    def __post_init__(self) -> None:
        _validate_subject_key(self.subject_key, field_name="SubjectProfile.subject_key")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise SubjectContributionValidationError("SubjectProfile.display_name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise SubjectContributionValidationError("SubjectProfile.description must be a non-empty string.")
        if not isinstance(self.version, str) or not self.version:
            raise SubjectContributionValidationError("SubjectProfile.version must be a non-empty string.")

        object.__setattr__(self, "contributions", tuple(self.contributions))
        for contribution in self.contributions:
            if not isinstance(contribution, SubjectContribution):
                raise SubjectContributionValidationError(
                    f"SubjectProfile({self.subject_key}).contributions entries must be "
                    f"SubjectContribution instances, got {type(contribution).__name__}."
                )
            if contribution.subject_key != self.subject_key:
                raise SubjectContributionValidationError(
                    f"SubjectProfile({self.subject_key}) contains a contribution declared "
                    f"for subject_key {contribution.subject_key!r} — every contribution's "
                    "subject_key must match its owning profile's subject_key."
                )

        # Duplicate object identifiers *within this profile* — the
        # cheapest possible check, independent of any registry, so a
        # malformed profile fails at construction time rather than
        # only surfacing once someone tries to register it. Duplicate
        # detection *across* profiles (or against the base taxonomy)
        # is a registration-time concern — see
        # `registry.SubjectProfileRegistry.register()`.
        seen: Dict[str, str] = {}
        for contribution in self.contributions:
            identifiers = (contribution.object_type.key, *contribution.object_type.aliases)
            for identifier in identifiers:
                if identifier in seen:
                    raise SubjectContributionValidationError(
                        f"SubjectProfile({self.subject_key}) declares duplicate object "
                        f"identifier {identifier!r} (key or alias) across more than one "
                        "contribution."
                    )
                seen[identifier] = contribution.object_type.key

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic, JSON-safe representation. `contributions` is
        always emitted in the same deterministic order
        `registry.SubjectProfileRegistry.all_contributions()` uses —
        ascending `(object_type.category.value, object_type.key)` —
        regardless of authoring order, so two profiles with the same
        contributions authored in a different order serialize
        identically."""
        ordered = sorted(
            self.contributions,
            key=lambda c: (c.object_type.category.value, c.object_type.key),
        )
        return {
            "subject_key": self.subject_key,
            "display_name": self.display_name,
            "description": self.description,
            "contributions": [c.to_dict() for c in ordered],
            "version": self.version,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "SubjectProfile":
        """Reconstructs a `SubjectProfile` from `to_dict()`'s own
        output shape."""
        try:
            return SubjectProfile(
                subject_key=data["subject_key"],
                display_name=data["display_name"],
                description=data["description"],
                contributions=tuple(
                    SubjectContribution.from_dict(c) for c in data.get("contributions", ())
                ),
                version=data.get("version", DEFAULT_PROFILE_VERSION),
            )
        except KeyError as exc:
            raise SubjectContributionValidationError(
                f"SubjectProfile.from_dict() input is missing required field: {exc}."
            ) from exc


__all__ = [
    "SubjectContribution",
    "SubjectProfile",
    "DEFAULT_CONTRIBUTION_VERSION",
    "DEFAULT_PROFILE_VERSION",
]
