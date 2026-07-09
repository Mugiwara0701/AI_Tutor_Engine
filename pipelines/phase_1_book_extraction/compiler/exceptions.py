"""
compiler/exceptions.py — exception hierarchy for the compiler's Symbol
Table layer (compiler/registry.py, compiler/registry_manager.py).

Kept deliberately small and specific, mirroring storage/exceptions.py's
convention in this project: callers can catch precisely what they care
about (e.g. catch DuplicateIdError to report a conflict without crashing
a bulk-load loop) without parsing free-text messages.
"""


class RegistryError(Exception):
    """Base class for every error raised by compiler.registry /
    compiler.registry_manager."""


class DuplicateIdError(RegistryError):
    """Raised by CanonicalRegistry.insert() when an item's id already
    exists in the registry. Registries never silently overwrite an
    existing entry -- use update() (same id, replaces the value) or
    upsert() (insert-or-update) if that's actually what's wanted."""

    def __init__(self, id_: str, registry_name: str = "registry"):
        super().__init__(
            f"{registry_name}: duplicate id {id_!r} -- an item with this "
            "id already exists. Use update()/upsert() to replace it "
            "intentionally, or insert_or_report() to collect this as a "
            "diagnostic instead of raising."
        )
        self.id = id_
        self.registry_name = registry_name


class DuplicateUrnError(RegistryError):
    """Raised when an item's urn already resolves to a *different* id
    already in the registry. Two distinct ids are never allowed to share
    one urn -- that would make get_by_urn() ambiguous."""

    def __init__(self, urn: str, registry_name: str = "registry"):
        super().__init__(
            f"{registry_name}: duplicate urn {urn!r} -- already resolves "
            "to a different id in this registry."
        )
        self.urn = urn
        self.registry_name = registry_name


class DuplicateNameError(RegistryError):
    """Raised when an item's canonical name (case-insensitively, by
    default) already resolves to a *different* id already in the
    registry."""

    def __init__(self, name: str, registry_name: str = "registry"):
        super().__init__(
            f"{registry_name}: duplicate canonical name {name!r} -- "
            "already resolves to a different id in this registry."
        )
        self.name = name
        self.registry_name = registry_name


class ItemNotFoundError(RegistryError):
    """Raised by update()/remove()/RegistryManager.get() etc. when the
    requested key does not exist."""

    def __init__(self, key: str, by: str = "id", registry_name: str = "registry"):
        super().__init__(f"{registry_name}: no item found with {by}={key!r}")
        self.key = key
        self.by = by
        self.registry_name = registry_name


class RegistrySerializationError(RegistryError):
    """Raised when serialize()/deserialize() cannot round-trip an item --
    e.g. the item is neither a dict nor an object exposing model_dump()/
    to_dict(), and no explicit serializer was supplied."""
