"""
modules/educational_taxonomy/registry.py — M5.2A: registration,
uniqueness enforcement, lookup, and deterministic ordering for
`EducationalObjectType` entries.

Mirrors modules/educational_object_framework/registry.py's own shape
in this project — a small stateful class plus a module-level default
instance (`default_taxonomy`) so most call sites can use the plain
function API below without constructing their own registry — applied
to taxonomy entries (a static data catalog) instead of processors (a
runtime execution concern). This is a deliberately separate registry
type from `educational_object_framework.registry.ProcessorRegistry`:
a taxonomy entry has no lifecycle state (no enabled/disabled/failed —
see `enums.py`'s docstring for why no such enum exists here), no
priority, and nothing to execute; it is a catalog lookup, not an
orchestration concern. Per the M5.1 spec, this package does not
introduce a second *processor* registry, pipeline, or processing
context — this is a new, narrower kind of registry the M5.1 framework
has no equivalent of.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.exceptions import (
    TaxonomyLookupError,
    TaxonomyRegistrationError,
)
from modules.educational_taxonomy.models import EducationalObjectType


class TaxonomyRegistry:
    """Tracks every registered `EducationalObjectType`, enforcing
    uniqueness of `key` (and of every `alias`, against every other
    entry's key and aliases) across the whole registry. Lookup by key
    or alias both resolve to the same entry. Iteration order
    (`all_types()`, `types_by_category()`) is always deterministic —
    sorted by `(category.value, key)` — regardless of registration
    order, so serializing the taxonomy never depends on import order
    or dict insertion order."""

    def __init__(self) -> None:
        self._by_key: Dict[str, EducationalObjectType] = {}
        self._alias_to_key: Dict[str, str] = {}

    # -- registration --------------------------------------------------

    def register(self, object_type: EducationalObjectType) -> None:
        """Registers `object_type`, keyed by its own `key`. Raises
        `TaxonomyRegistrationError` if `key` (or any of its
        `aliases`) collides with an already-registered entry's key or
        alias. This is the sole extension point: a future milestone
        (M5.2B+) adds new object types by calling `register()` with a
        new `EducationalObjectType` — nothing in this package needs
        to change."""
        if not isinstance(object_type, EducationalObjectType):
            raise TaxonomyRegistrationError(
                f"Object {object_type!r} is not an EducationalObjectType instance."
            )
        if object_type.key in self._by_key:
            raise TaxonomyRegistrationError(
                f"An educational object type with key '{object_type.key}' is already "
                "registered; call unregister() first to replace it."
            )
        if object_type.key in self._alias_to_key:
            raise TaxonomyRegistrationError(
                f"Key '{object_type.key}' collides with an existing alias of "
                f"'{self._alias_to_key[object_type.key]}'."
            )
        for alias in object_type.aliases:
            if alias in self._by_key or alias in self._alias_to_key:
                raise TaxonomyRegistrationError(
                    f"Alias '{alias}' of '{object_type.key}' collides with an "
                    "already-registered key or alias."
                )

        self._by_key[object_type.key] = object_type
        for alias in object_type.aliases:
            self._alias_to_key[alias] = object_type.key

    def unregister(self, key: str) -> None:
        """Removes an entry (and every one of its aliases) entirely."""
        if key not in self._by_key:
            raise TaxonomyLookupError(f"No educational object type with key '{key}' is registered.")
        object_type = self._by_key.pop(key)
        for alias in object_type.aliases:
            self._alias_to_key.pop(alias, None)

    # -- lookup / ordering --------------------------------------------------

    def get(self, key_or_alias: str) -> EducationalObjectType:
        """Resolves `key_or_alias` to its `EducationalObjectType`,
        whether it names an entry's canonical `key` or one of its
        `aliases`."""
        if key_or_alias in self._by_key:
            return self._by_key[key_or_alias]
        canonical_key = self._alias_to_key.get(key_or_alias)
        if canonical_key is not None:
            return self._by_key[canonical_key]
        raise TaxonomyLookupError(f"No educational object type with key or alias '{key_or_alias}' is registered.")

    def all_types(self) -> List[EducationalObjectType]:
        """Every registered type, in a stable, deterministic order:
        ascending `(category.value, key)`. This is the single
        ordering every other read method and `to_dict()`-style
        serialization relies on for reproducibility."""
        return sorted(self._by_key.values(), key=lambda t: (t.category.value, t.key))

    def types_by_category(self, category: EducationalCategory) -> List[EducationalObjectType]:
        """Same ordering as `all_types()`, filtered to one category."""
        return [t for t in self.all_types() if t.category == category]

    def categories(self) -> Tuple[EducationalCategory, ...]:
        """Every `EducationalCategory` that has at least one
        registered type, in `EducationalCategory` declaration order."""
        present = {t.category for t in self._by_key.values()}
        return tuple(c for c in EducationalCategory if c in present)

    def keys(self) -> List[str]:
        return [t.key for t in self.all_types()]

    def __contains__(self, key_or_alias: str) -> bool:
        return key_or_alias in self._by_key or key_or_alias in self._alias_to_key

    def __len__(self) -> int:
        return len(self._by_key)


# -- module-level default registry + convenience functions --------------------------------------------------
#
# Mirrors educational_object_framework.registry's plain-function
# ergonomics for the common case of "one taxonomy for the whole
# process": `default_taxonomy` is constructed once, seeded with the
# built-in canonical catalog by `catalog.py` (imported for its side
# effect below), and every later milestone (M5.2B+) registers new
# types into this same instance. Code that needs an isolated registry
# (e.g. tests exercising registration/uniqueness in isolation) should
# construct its own `TaxonomyRegistry()` instead of using these.

default_taxonomy = TaxonomyRegistry()


def register(object_type: EducationalObjectType) -> None:
    default_taxonomy.register(object_type)


def unregister(key: str) -> None:
    default_taxonomy.unregister(key)


def get(key_or_alias: str) -> EducationalObjectType:
    return default_taxonomy.get(key_or_alias)


def all_types() -> List[EducationalObjectType]:
    return default_taxonomy.all_types()


def types_by_category(category: EducationalCategory) -> List[EducationalObjectType]:
    return default_taxonomy.types_by_category(category)


__all__ = [
    "TaxonomyRegistry",
    "default_taxonomy",
    "register",
    "unregister",
    "get",
    "all_types",
    "types_by_category",
]


# Seed `default_taxonomy` with the built-in canonical catalog. Imported
# for its side effect (each type's own `register(...)` call) — see
# catalog.py's own docstring. Placed at the end of this module so
# `default_taxonomy` already exists by the time catalog.py's
# module-level registration code runs.
from modules.educational_taxonomy import catalog as _catalog  # noqa: E402  (see comment above)

_catalog.seed(default_taxonomy)
