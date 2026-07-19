"""
modules/subject_profile_framework/registry.py — M5.2B: registration,
duplicate detection, capability-based queries, and deterministic
ordering for `SubjectProfile` entries.

This is the concrete integration point with the frozen M5.2A taxonomy:
`SubjectProfileRegistry.register()` extends
`modules.educational_taxonomy.registry.TaxonomyRegistry` by calling its
own, unmodified `register()` method for every contribution's
`EducationalObjectType` — the "official extension mechanism" M5.2A
already ships (see that package's own extensibility test). This module
never reaches into `TaxonomyRegistry`'s internals, never subclasses
it, and never adds a method to it.

Capability-based queries (by category, by symbolic content, by
copyright sensitivity, by structural/semantic/relationship support)
live here, over the Subject Profile layer's own metadata — NOT on
`TaxonomyRegistry`, which has no concept of any of these. This is the
"capability-based registry query" mechanism the M5.2B brief asks for,
implemented without changing the frozen registry it queries.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.exceptions import EducationalTaxonomyError
from modules.educational_taxonomy.registry import TaxonomyRegistry
from modules.educational_taxonomy.registry import default_taxonomy as _default_taxonomy_registry

from modules.subject_profile_framework.enums import CopyrightSensitivity, SupportLevel, support_at_least
from modules.subject_profile_framework.exceptions import (
    SubjectProfileLookupError,
    SubjectProfileRegistrationError,
    TaxonomyExtensionError,
)
from modules.subject_profile_framework.models import SubjectContribution, SubjectProfile


class SubjectProfileRegistry:
    """Tracks every registered `SubjectProfile`, enforces uniqueness of
    `subject_key` and of every contribution's object identifier (key
    or alias) across the whole registry, and extends a
    `TaxonomyRegistry` on each profile's behalf. Iteration order
    (`all_profiles()`, `all_contributions()`) is always
    deterministic, mirroring `TaxonomyRegistry`'s own ordering
    contract, regardless of registration order.
    """

    def __init__(self, taxonomy_registry: Optional[TaxonomyRegistry] = None) -> None:
        #: The frozen taxonomy registry this Subject Profile Registry
        #: extends. Defaults to the shared, process-wide
        #: `default_taxonomy` — the same singleton M5.2A's own catalog
        #: seeds — but a caller (e.g. a test needing isolation) may
        #: supply its own `TaxonomyRegistry()` instance instead.
        self._taxonomy: TaxonomyRegistry = taxonomy_registry if taxonomy_registry is not None else _default_taxonomy_registry
        self._profiles: Dict[str, SubjectProfile] = {}
        #: object identifier (key or alias) -> owning subject_key,
        #: kept independently of `self._taxonomy` so a duplicate can be
        #: reported as a Subject Profile Framework-level error (naming
        #: which subject already owns the identifier) rather than only
        #: as an opaque `TaxonomyRegistrationError`.
        self._identifier_to_subject: Dict[str, str] = {}

    # -- registration --------------------------------------------------

    def register(self, profile: SubjectProfile) -> None:
        """Registers `profile`: checks `subject_key` uniqueness and
        every contribution's object-identifier uniqueness within this
        registry, then extends the frozen taxonomy by calling its own
        `register()` for each contribution's `EducationalObjectType`,
        in `profile.contributions` order. If any contribution fails to
        register into the taxonomy (e.g. it collides with a built-in
        taxonomy entry from outside this registry), every contribution
        from this same `profile` that was already registered into the
        taxonomy during this call is rolled back via `unregister()`,
        so a failed `register()` call never leaves the taxonomy or
        this registry partially mutated.
        """
        if not isinstance(profile, SubjectProfile):
            raise SubjectProfileRegistrationError(
                f"Object {profile!r} is not a SubjectProfile instance."
            )
        if profile.subject_key in self._profiles:
            raise SubjectProfileRegistrationError(
                f"A subject profile with subject_key '{profile.subject_key}' is already "
                "registered; call unregister() first to replace it."
            )

        for contribution in profile.contributions:
            for identifier in (contribution.object_type.key, *contribution.object_type.aliases):
                if identifier in self._identifier_to_subject:
                    raise SubjectProfileRegistrationError(
                        f"Object identifier '{identifier}' (from subject "
                        f"'{profile.subject_key}') collides with an identifier already "
                        f"registered by subject '{self._identifier_to_subject[identifier]}'."
                    )

        registered_so_far: List[str] = []
        try:
            for contribution in profile.contributions:
                try:
                    self._taxonomy.register(contribution.object_type)
                except EducationalTaxonomyError as exc:
                    raise TaxonomyExtensionError(
                        f"Subject '{profile.subject_key}' contribution "
                        f"'{contribution.object_type.key}' could not extend the taxonomy: {exc}"
                    ) from exc
                registered_so_far.append(contribution.object_type.key)
        except TaxonomyExtensionError:
            for key in registered_so_far:
                self._taxonomy.unregister(key)
            raise

        self._profiles[profile.subject_key] = profile
        for contribution in profile.contributions:
            for identifier in (contribution.object_type.key, *contribution.object_type.aliases):
                self._identifier_to_subject[identifier] = profile.subject_key

    def unregister(self, subject_key: str) -> None:
        """Removes a profile entirely: every one of its contributions'
        `EducationalObjectType` entries is unregistered from the
        taxonomy (via the taxonomy's own `unregister()`), and every
        identifier it owned is freed in this registry."""
        if subject_key not in self._profiles:
            raise SubjectProfileLookupError(f"No subject profile with subject_key '{subject_key}' is registered.")
        profile = self._profiles.pop(subject_key)
        for contribution in profile.contributions:
            self._taxonomy.unregister(contribution.object_type.key)
            for identifier in (contribution.object_type.key, *contribution.object_type.aliases):
                self._identifier_to_subject.pop(identifier, None)

    # -- lookup / ordering --------------------------------------------------

    def get(self, subject_key: str) -> SubjectProfile:
        if subject_key not in self._profiles:
            raise SubjectProfileLookupError(f"No subject profile with subject_key '{subject_key}' is registered.")
        return self._profiles[subject_key]

    def all_profiles(self) -> List[SubjectProfile]:
        """Every registered profile, in a stable, deterministic order:
        ascending `subject_key`."""
        return [self._profiles[key] for key in sorted(self._profiles)]

    def all_contributions(self) -> List[SubjectContribution]:
        """Every contribution across every registered profile, in a
        stable, deterministic order: ascending
        `(subject_key, object_type.category.value, object_type.key)`.
        This is the single ordering every capability query below
        relies on for reproducibility."""
        contributions = [c for profile in self.all_profiles() for c in profile.contributions]
        return sorted(
            contributions,
            key=lambda c: (c.subject_key, c.object_type.category.value, c.object_type.key),
        )

    def subject_keys(self) -> List[str]:
        return sorted(self._profiles)

    def __contains__(self, subject_key: str) -> bool:
        return subject_key in self._profiles

    def __len__(self) -> int:
        return len(self._profiles)

    # -- capability-based queries --------------------------------------------------
    #
    # These operate entirely over this registry's own contribution
    # metadata. None of them read or change anything on the frozen
    # `TaxonomyRegistry` beyond the `category` each contribution's
    # `object_type` already carries.

    def contributions_by_category(self, category: EducationalCategory) -> List[SubjectContribution]:
        """Same ordering as `all_contributions()`, filtered to
        contributions whose `object_type.category` is `category`."""
        return [c for c in self.all_contributions() if c.object_type.category == category]

    def contributions_with_symbolic_content(self) -> List[SubjectContribution]:
        return [c for c in self.all_contributions() if c.symbolic_content]

    def contributions_by_copyright_sensitivity(self, sensitivity: CopyrightSensitivity) -> List[SubjectContribution]:
        return [c for c in self.all_contributions() if c.copyright_sensitivity == sensitivity]

    def contributions_supporting(
        self, capability: str, minimum: SupportLevel = SupportLevel.PARTIAL
    ) -> List[SubjectContribution]:
        """Contributions whose declared support level for `capability`
        ("structural", "semantic", or "relationship") is at least
        `minimum` on the NONE < PARTIAL < FULL scale.
        """
        field_name = {
            "structural": "structural_support",
            "semantic": "semantic_support",
            "relationship": "relationship_support",
        }.get(capability)
        if field_name is None:
            raise ValueError(
                f"Unknown capability {capability!r}; expected one of "
                "'structural', 'semantic', 'relationship'."
            )
        return [
            c for c in self.all_contributions()
            if support_at_least(getattr(c, field_name), minimum)
        ]

    @property
    def taxonomy(self) -> TaxonomyRegistry:
        """The `TaxonomyRegistry` this Subject Profile Registry
        extends — exposed read-only so a caller can confirm a
        contribution actually landed in the taxonomy (e.g.
        `registry.taxonomy.get("coordinate_geometry_figure")`) without
        this registry needing to re-expose every `TaxonomyRegistry`
        method itself."""
        return self._taxonomy


# -- module-level default registry + convenience functions --------------------------------------------------
#
# Mirrors `educational_taxonomy.registry`'s / `educational_object_
# framework.registry`'s own plain-function ergonomics for the common
# case of "one Subject Profile Registry for the whole process":
# `default_subject_profiles` is constructed once, against the shared
# `default_taxonomy`, and every subject profile (Mathematics, Physics,
# History, ...) registers into this same instance. Code that needs an
# isolated registry (e.g. tests exercising registration/uniqueness in
# isolation) should construct its own `SubjectProfileRegistry()`
# instead of using these.

default_subject_profiles = SubjectProfileRegistry()


def register(profile: SubjectProfile) -> None:
    default_subject_profiles.register(profile)


def unregister(subject_key: str) -> None:
    default_subject_profiles.unregister(subject_key)


def get(subject_key: str) -> SubjectProfile:
    return default_subject_profiles.get(subject_key)


def all_profiles() -> List[SubjectProfile]:
    return default_subject_profiles.all_profiles()


def all_contributions() -> List[SubjectContribution]:
    return default_subject_profiles.all_contributions()


__all__ = [
    "SubjectProfileRegistry",
    "default_subject_profiles",
    "register",
    "unregister",
    "get",
    "all_profiles",
    "all_contributions",
]
