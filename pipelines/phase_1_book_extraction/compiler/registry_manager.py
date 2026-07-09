"""
compiler/registry_manager.py — Phase B0: RegistryManager.

Owns every CanonicalRegistry instance a compiler run needs, keyed by a
caller-chosen name (e.g. "concepts", "figures", "equations" once Phase B1
introduces those). RegistryManager itself stays exactly as generic as
CanonicalRegistry -- it does not know or hardcode any educational-object
registry name; Phase B1 is the layer that decides which named registries
actually exist and what they're populated with.

At Phase B0 nothing calls create()/register() with real data -- the
manager exists purely as reusable plumbing so Phase B1 has a single,
clean place to (a) create a new named registry, (b) fetch an existing
one by name, and (c) get aggregate statistics/serialization across every
registry it owns, without each Phase B1 module hand-rolling its own
`Dict[str, CanonicalRegistry]` bookkeeping.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Optional

from .exceptions import RegistryError, ItemNotFoundError
from .registry import CanonicalRegistry, RegistryStatistics, Extractor, Serializer, Deserializer
from .registry import _default_id_of, _default_urn_of, _default_name_of
from .registry import _default_serializer, _default_deserializer

logger = logging.getLogger("compiler.registry_manager")


class RegistryManager:
    """Owns every CanonicalRegistry for one compiler run, keyed by name.

    Usage (Phase B1 and later):

        manager = RegistryManager()
        concepts = manager.create("concepts")   # -> CanonicalRegistry
        concepts.insert(concept_dict)
        ...
        manager.get("concepts").get_by_name("Photosynthesis")
        manager.statistics()   # {"concepts": RegistryStatistics(...), ...}
    """

    def __init__(self) -> None:
        self._registries: Dict[str, CanonicalRegistry[Any]] = {}

    # -- registry lifecycle -------------------------------------------------

    def create(
        self,
        name: str,
        *,
        id_of: Extractor = _default_id_of,
        urn_of: Extractor = _default_urn_of,
        name_of: Extractor = _default_name_of,
        serializer: Serializer = _default_serializer,
        deserializer: Deserializer = _default_deserializer,
        case_insensitive_names: bool = True,
    ) -> CanonicalRegistry[Any]:
        """Creates a new, empty CanonicalRegistry under `name` and takes
        ownership of it. Raises RegistryError if `name` is already
        registered -- use get_or_create() if that's fine."""
        if name in self._registries:
            raise RegistryError(
                f"RegistryManager: a registry named {name!r} is already "
                "registered -- use get(), get_or_create(), or remove() "
                "it first."
            )
        registry: CanonicalRegistry[Any] = CanonicalRegistry(
            name=name, id_of=id_of, urn_of=urn_of, name_of=name_of,
            serializer=serializer, deserializer=deserializer,
            case_insensitive_names=case_insensitive_names,
        )
        self._registries[name] = registry
        return registry

    def register(self, registry: CanonicalRegistry[Any]) -> None:
        """Takes ownership of an already-constructed CanonicalRegistry
        (e.g. one a Phase B1 subclass built itself), keyed by its own
        `.name`. Raises RegistryError on a name collision."""
        if registry.name in self._registries:
            raise RegistryError(
                f"RegistryManager: a registry named {registry.name!r} is "
                "already registered."
            )
        self._registries[registry.name] = registry

    def get(self, name: str) -> CanonicalRegistry[Any]:
        """Returns the registry owned under `name`. Raises
        ItemNotFoundError if none exists."""
        try:
            return self._registries[name]
        except KeyError:
            raise ItemNotFoundError(name, by="registry name", registry_name="RegistryManager") from None

    def get_or_create(self, name: str, **create_kwargs: Any) -> CanonicalRegistry[Any]:
        """get(name) if it already exists, else create(name, **kwargs)."""
        existing = self._registries.get(name)
        if existing is not None:
            return existing
        return self.create(name, **create_kwargs)

    def has(self, name: str) -> bool:
        return name in self._registries

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def remove(self, name: str) -> CanonicalRegistry[Any]:
        """Un-registers and returns the registry owned under `name`.
        Raises ItemNotFoundError if none exists."""
        try:
            return self._registries.pop(name)
        except KeyError:
            raise ItemNotFoundError(name, by="registry name", registry_name="RegistryManager") from None

    def names(self) -> List[str]:
        """Every registered registry's name, in the order it was
        registered (deterministic, like CanonicalRegistry's own
        iteration order)."""
        return list(self._registries.keys())

    def __iter__(self) -> Iterator[CanonicalRegistry[Any]]:
        return iter(self._registries.values())

    def __len__(self) -> int:
        return len(self._registries)

    def clear(self, name: Optional[str] = None) -> None:
        """Empties one named registry's contents (if `name` given), or
        every registry this manager owns (if not). Does not un-register
        anything -- the registry objects themselves still exist, just
        empty. Mirrors CanonicalRegistry.clear()'s own contents-only
        semantics."""
        if name is not None:
            self.get(name).clear()
            return
        for registry in self._registries.values():
            registry.clear()

    # -- aggregate reads -----------------------------------------------------

    def total_size(self) -> int:
        """Sum of every owned registry's current item count."""
        return sum(registry.size() for registry in self._registries.values())

    def statistics(self) -> Dict[str, RegistryStatistics]:
        """Per-registry RegistryStatistics, keyed by registry name."""
        return {name: registry.statistics() for name, registry in self._registries.items()}

    # -- serialization ---------------------------------------------------------

    def serialize(self) -> Dict[str, Any]:
        """Every owned registry's serialize() output, keyed by name, in
        deterministic (registration) order."""
        return {
            "registries": {
                name: registry.serialize() for name, registry in self._registries.items()
            }
        }

    def to_json(self, **json_kwargs: Any) -> str:
        return json.dumps(self.serialize(), **json_kwargs)

    @classmethod
    def deserialize(
        cls,
        data: Dict[str, Any],
        *,
        registry_kwargs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> "RegistryManager":
        """Rebuilds a RegistryManager (and every registry it owns) from
        serialize()'s output. `registry_kwargs`, if given, maps a
        registry name to the id_of/urn_of/name_of/serializer/deserializer
        kwargs CanonicalRegistry.deserialize() needs to reconstruct real
        item objects for that specific registry (defaults to plain-dict
        items, like CanonicalRegistry.deserialize() itself, for any
        registry not listed)."""
        if "registries" not in data:
            raise RegistryError(
                "RegistryManager.deserialize(): input is missing the "
                "required 'registries' key (expected the shape produced "
                "by RegistryManager.serialize())."
            )
        registry_kwargs = registry_kwargs or {}
        manager = cls()
        for name, registry_data in data["registries"].items():
            kwargs = registry_kwargs.get(name, {})
            manager._registries[name] = CanonicalRegistry.deserialize(registry_data, **kwargs)
        return manager

    @classmethod
    def from_json(cls, text: str, **kwargs: Any) -> "RegistryManager":
        return cls.deserialize(json.loads(text), **kwargs)
