"""
compiler/registry.py — Phase B0: generic Symbol Table infrastructure.

`CanonicalRegistry[T]` is a generic, type-parameterized registry with no
knowledge of Concepts, Figures, Equations, or any other educational
object. It is the same shape of thing a compiler's symbol table is: a
deterministic, deduplicated, lookup-friendly store of records, indexed by
id (primary key), and secondarily by urn and canonical name.

WHY THIS EXISTS (relationship to the pre-B0 pattern): pipeline.py already
builds several ad-hoc dict-keyed-by-lowercase-name registries by hand --
see `concept_registry` in pipeline.py's chapter-assembly loop, whose own
comment calls out the "Single Owner Principle" (one canonical record per
distinct name, deduplicated across the whole chapter, never silently
aliased). This module generalizes that exact pattern -- id/urn/name
indexing, deterministic insertion-order iteration, duplicate rejection --
into one reusable, tested base class, so Phase B1's concrete registries
(ConceptRegistry, FigureRegistry, EquationRegistry, ...) can each be a
thin, type-specific wrapper instead of a fifth copy-pasted dict-dedup
loop. No Phase B1 registry classes are introduced here -- see
compiler/README or the Phase B0 task notes for scope.

DESIGN NOTES
------------
- Generic over T: an item can be a plain dict (the shape
  modules/canonical.py::canonical_fields() already produces) or any
  object exposing attributes/methods for id/urn/name -- a Pydantic model
  such as schemas.chapter_schema.CanonicalObjectBase works out of the
  box. `id_of` / `urn_of` / `name_of` are overridable extractor
  callables so a concrete Phase B1 registry can adapt to whatever shape
  its item type actually has, without this base class special-casing
  any of them.
- Deterministic ordering: backed by a single `dict[id, item]`, whose
  insertion order Python (3.7+) guarantees to preserve. Iteration,
  values(), items(), and serialize() output all reflect insertion order,
  never a hash-derived one. Two independent runs that insert the same
  items in the same order always produce byte-identical serialize()
  output, matching the deterministic-id/urn identity strategy already
  established in modules/pdf_parser.py (A3).
- Duplicate protection: insert() raises rather than overwrites, on a
  duplicate id, a duplicate urn (resolving to a different id), or a
  duplicate canonical name (resolving to a different id, matched
  case-insensitively by default). update()/upsert() are the explicit,
  intentional ways to replace an existing entry. insert_or_report()
  offers a non-raising alternative for bulk-load callers that want to
  collect every conflict as a diagnostic instead of stopping at the
  first one.
- Single Owner Principle: `_items` (id -> item) is the one source of
  truth; `_urn_index` and `_name_index` are derived indexes that are
  always kept in lockstep with it (never allowed to drift into a second,
  disagreeing source of truth -- the exact failure mode the
  concept_registry comment in pipeline.py documents pre-B0).
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, asdict
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
)

from .exceptions import (
    RegistryError,
    DuplicateIdError,
    DuplicateUrnError,
    DuplicateNameError,
    ItemNotFoundError,
    RegistrySerializationError,
)

logger = logging.getLogger("compiler.registry")

T = TypeVar("T")

Extractor = Callable[[Any], Optional[str]]
Serializer = Callable[[Any], Dict[str, Any]]
Deserializer = Callable[[Dict[str, Any]], Any]


# --------------------------------------------------------------------------
# Default field extractors / (de)serializers
#
# These make CanonicalRegistry usable out of the box against either a
# plain dict item (the shape canonical_fields() produces today) or an
# object exposing id/urn/name as attributes (e.g. a Pydantic model) --
# without the registry itself ever branching on educational-object type.
# --------------------------------------------------------------------------

def _get(item: Any, key: str) -> Optional[Any]:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _default_id_of(item: Any) -> Optional[str]:
    return _get(item, "id")


def _default_urn_of(item: Any) -> Optional[str]:
    return _get(item, "urn")


def _default_name_of(item: Any) -> Optional[str]:
    return _get(item, "name")


def _default_serializer(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise RegistrySerializationError(
        f"cannot serialize item of type {type(item).__name__}: it is not "
        "a dict and exposes neither model_dump() nor to_dict(). Pass an "
        "explicit `serializer=` to CanonicalRegistry(...) for this item "
        "type."
    )


def _default_deserializer(data: Dict[str, Any]) -> Dict[str, Any]:
    # Identity by default: without knowing the concrete item type T, the
    # only universally safe reconstruction is "the dict itself". A
    # concrete Phase B1 registry that wants deserialize() to rebuild real
    # objects (e.g. a Pydantic model) supplies its own `deserializer=`.
    return dict(data)


# --------------------------------------------------------------------------
# Diagnostics / statistics
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RegistryDiagnostic:
    """One duplicate-conflict (or other reportable) event, as produced by
    insert_or_report(). Compiler-diagnostic-shaped on purpose: `kind`
    plays the role of an error code, `message` is human-readable, and the
    rest identify exactly which item/key collided."""

    ok: bool
    kind: str  # "duplicate_id" | "duplicate_urn" | "duplicate_name" | "ok"
    message: str
    id: Optional[str] = None
    urn: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegistryStatistics:
    """Compiler-friendly statistics for one CanonicalRegistry. `size` is a
    point-in-time snapshot (current item count); every other field is a
    lifetime counter that survives clear() -- clearing a registry's
    contents does not erase the historical record of what happened to
    it, mirroring how a compiler's diagnostic count isn't reset by
    discarding a symbol table's entries mid-run."""

    name: str
    size: int
    inserts: int
    updates: int
    removals: int
    duplicate_id_attempts: int
    duplicate_urn_attempts: int
    duplicate_name_attempts: int
    lookups: int
    lookup_hits: int
    lookup_misses: int
    approx_memory_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# CanonicalRegistry
# --------------------------------------------------------------------------

class CanonicalRegistry(Generic[T]):
    """Generic, deterministic, type-safe registry -- the compiler's Symbol
    Table layer. See module docstring for the full design rationale.

    Every method that mutates the registry (insert/update/remove/clear)
    and every method that reads it (get_by_*, lookup, values, items,
    size, statistics) is intentionally generic: nothing here knows what
    kind of educational object T is.
    """

    def __init__(
        self,
        name: str = "registry",
        *,
        id_of: Extractor = _default_id_of,
        urn_of: Extractor = _default_urn_of,
        name_of: Extractor = _default_name_of,
        serializer: Serializer = _default_serializer,
        deserializer: Deserializer = _default_deserializer,
        case_insensitive_names: bool = True,
    ) -> None:
        self._name = name
        self._id_of = id_of
        self._urn_of = urn_of
        self._name_of = name_of
        self._serializer = serializer
        self._deserializer = deserializer
        self._case_insensitive_names = case_insensitive_names

        # Single Owner Principle: `_items` is the one source of truth;
        # `_urn_index` / `_name_index` are derived indexes maintained in
        # lockstep, never a second, independently-updated store.
        self._items: Dict[str, T] = {}
        self._urn_index: Dict[str, str] = {}
        self._name_index: Dict[str, str] = {}

        self._duplicate_log: List[RegistryDiagnostic] = []

        self._stat_inserts = 0
        self._stat_updates = 0
        self._stat_removals = 0
        self._stat_dup_id = 0
        self._stat_dup_urn = 0
        self._stat_dup_name = 0
        self._stat_lookups = 0
        self._stat_lookup_hits = 0
        self._stat_lookup_misses = 0

    # -- identity ------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"CanonicalRegistry(name={self._name!r}, size={self.size()})"

    # -- internal helpers ------------------------------------------------

    def _normalize_name(self, name: str) -> str:
        cleaned = name.strip()
        return cleaned.lower() if self._case_insensitive_names else cleaned

    def _require_id(self, item: T) -> str:
        id_ = self._id_of(item)
        if not id_:
            raise RegistryError(
                f"{self._name}: item has no id (id_of(item) returned "
                "empty/None) -- every registry item must have a stable, "
                "non-empty id"
            )
        return id_

    # -- mutation: insert / update / upsert / remove / clear -------------

    def insert(self, item: T) -> str:
        """Adds a new item. Raises DuplicateIdError / DuplicateUrnError /
        DuplicateNameError rather than overwriting an existing entry --
        use update() or upsert() to replace one intentionally."""
        diagnostic = self._try_insert(item)
        if not diagnostic.ok:
            if diagnostic.kind == "duplicate_id":
                raise DuplicateIdError(diagnostic.id or "", self._name)
            if diagnostic.kind == "duplicate_urn":
                raise DuplicateUrnError(diagnostic.urn or "", self._name)
            raise DuplicateNameError(diagnostic.name or "", self._name)
        return diagnostic.id  # type: ignore[return-value]

    def insert_or_report(self, item: T) -> RegistryDiagnostic:
        """Non-raising alternative to insert(), for bulk-load callers
        that want to keep going past the first conflict and collect every
        duplicate as a diagnostic instead. Every conflict (raised or not)
        is also appended to duplicate_report()."""
        return self._try_insert(item)

    def _try_insert(self, item: T) -> RegistryDiagnostic:
        id_ = self._require_id(item)
        urn = self._urn_of(item)
        name = self._name_of(item)

        if id_ in self._items:
            self._stat_dup_id += 1
            diag = RegistryDiagnostic(
                ok=False, kind="duplicate_id",
                message=f"{self._name}: duplicate id {id_!r}",
                id=id_, urn=urn, name=name,
            )
            self._duplicate_log.append(diag)
            return diag

        if urn and urn in self._urn_index:
            self._stat_dup_urn += 1
            diag = RegistryDiagnostic(
                ok=False, kind="duplicate_urn",
                message=f"{self._name}: duplicate urn {urn!r}",
                id=id_, urn=urn, name=name,
            )
            self._duplicate_log.append(diag)
            return diag

        norm_name = self._normalize_name(name) if name else None
        if norm_name and norm_name in self._name_index:
            self._stat_dup_name += 1
            diag = RegistryDiagnostic(
                ok=False, kind="duplicate_name",
                message=f"{self._name}: duplicate canonical name {name!r}",
                id=id_, urn=urn, name=name,
            )
            self._duplicate_log.append(diag)
            return diag

        self._items[id_] = item
        if urn:
            self._urn_index[urn] = id_
        if norm_name:
            self._name_index[norm_name] = id_
        self._stat_inserts += 1
        return RegistryDiagnostic(
            ok=True, kind="ok", message="inserted", id=id_, urn=urn, name=name,
        )

    def update(self, item: T) -> str:
        """Replaces the existing item with this same id. Raises
        ItemNotFoundError if no item with that id exists yet (use
        insert() or upsert() for that case). Still rejects a urn/name
        change that would collide with a *different* existing id."""
        id_ = self._require_id(item)
        if id_ not in self._items:
            raise ItemNotFoundError(id_, by="id", registry_name=self._name)

        old = self._items[id_]
        old_urn = self._urn_of(old)
        old_name = self._name_of(old)
        new_urn = self._urn_of(item)
        new_name = self._name_of(item)
        new_norm_name = self._normalize_name(new_name) if new_name else None
        old_norm_name = self._normalize_name(old_name) if old_name else None

        if new_urn and new_urn != old_urn and new_urn in self._urn_index \
                and self._urn_index[new_urn] != id_:
            self._stat_dup_urn += 1
            raise DuplicateUrnError(new_urn, self._name)

        if new_norm_name and new_norm_name != old_norm_name \
                and new_norm_name in self._name_index \
                and self._name_index[new_norm_name] != id_:
            self._stat_dup_name += 1
            raise DuplicateNameError(new_name or "", self._name)

        if old_urn and old_urn in self._urn_index:
            del self._urn_index[old_urn]
        if old_norm_name:
            self._name_index.pop(old_norm_name, None)

        self._items[id_] = item
        if new_urn:
            self._urn_index[new_urn] = id_
        if new_norm_name:
            self._name_index[new_norm_name] = id_

        self._stat_updates += 1
        return id_

    def upsert(self, item: T) -> str:
        """insert() if this id is new, update() if it already exists."""
        id_ = self._id_of(item)
        if id_ and id_ in self._items:
            return self.update(item)
        return self.insert(item)

    def remove(self, id_: str) -> T:
        """Removes and returns the item with this id. Raises
        ItemNotFoundError if it doesn't exist."""
        if id_ not in self._items:
            raise ItemNotFoundError(id_, by="id", registry_name=self._name)
        item = self._items.pop(id_)
        urn = self._urn_of(item)
        name = self._name_of(item)
        if urn:
            self._urn_index.pop(urn, None)
        if name:
            self._name_index.pop(self._normalize_name(name), None)
        self._stat_removals += 1
        return item

    def clear(self) -> None:
        """Empties the registry's contents. Lifetime statistics counters
        (inserts/updates/duplicate attempts/lookups/...) are NOT reset --
        see RegistryStatistics docstring."""
        self._items.clear()
        self._urn_index.clear()
        self._name_index.clear()

    # -- reads: contains / get_by_* / lookup ------------------------------

    def contains(self, id_: str) -> bool:
        return id_ in self._items

    def __contains__(self, id_: str) -> bool:
        return self.contains(id_)

    def get_by_id(self, id_: str) -> Optional[T]:
        self._stat_lookups += 1
        item = self._items.get(id_)
        self._stat_lookup_hits += 1 if item is not None else 0
        self._stat_lookup_misses += 0 if item is not None else 1
        return item

    def get_by_urn(self, urn: str) -> Optional[T]:
        self._stat_lookups += 1
        id_ = self._urn_index.get(urn)
        item = self._items.get(id_) if id_ is not None else None
        self._stat_lookup_hits += 1 if item is not None else 0
        self._stat_lookup_misses += 0 if item is not None else 1
        return item

    def get_by_name(self, name: str) -> Optional[T]:
        self._stat_lookups += 1
        id_ = self._name_index.get(self._normalize_name(name))
        item = self._items.get(id_) if id_ is not None else None
        self._stat_lookup_hits += 1 if item is not None else 0
        self._stat_lookup_misses += 0 if item is not None else 1
        return item

    def lookup(
        self,
        *,
        id: Optional[str] = None,  # noqa: A002 - matches task-spec API name
        urn: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[T]:
        """Single dispatching lookup: exactly one of id=/urn=/name= should
        be given. Convenience wrapper over get_by_id/get_by_urn/
        get_by_name for callers that select the key type dynamically."""
        provided = [k for k, v in (("id", id), ("urn", urn), ("name", name)) if v is not None]
        if len(provided) != 1:
            raise ValueError(
                "lookup() requires exactly one of id=, urn=, or name= "
                f"(got: {provided or 'none'})"
            )
        if id is not None:
            return self.get_by_id(id)
        if urn is not None:
            return self.get_by_urn(urn)
        return self.get_by_name(name)  # type: ignore[arg-type]

    # -- iteration ---------------------------------------------------------

    def values(self) -> List[T]:
        """All items, in deterministic insertion order."""
        return list(self._items.values())

    def items(self) -> List[Tuple[str, T]]:
        """(id, item) pairs, in deterministic insertion order."""
        return list(self._items.items())

    def ids(self) -> List[str]:
        """All ids, in deterministic insertion order."""
        return list(self._items.keys())

    def __iter__(self) -> Iterator[T]:
        return iter(self.values())

    def __len__(self) -> int:
        return self.size()

    def size(self) -> int:
        return len(self._items)

    # -- duplicate reporting -----------------------------------------------

    def duplicate_report(self) -> List[RegistryDiagnostic]:
        """Every duplicate conflict recorded so far (from insert() and
        insert_or_report() alike), in the order encountered."""
        return list(self._duplicate_log)

    # -- statistics ----------------------------------------------------------

    def statistics(self) -> RegistryStatistics:
        approx_bytes = self._estimate_memory_bytes()
        return RegistryStatistics(
            name=self._name,
            size=self.size(),
            inserts=self._stat_inserts,
            updates=self._stat_updates,
            removals=self._stat_removals,
            duplicate_id_attempts=self._stat_dup_id,
            duplicate_urn_attempts=self._stat_dup_urn,
            duplicate_name_attempts=self._stat_dup_name,
            lookups=self._stat_lookups,
            lookup_hits=self._stat_lookup_hits,
            lookup_misses=self._stat_lookup_misses,
            approx_memory_bytes=approx_bytes,
        )

    def _estimate_memory_bytes(self) -> int:
        """Best-effort, shallow sys.getsizeof() total over the three
        internal dicts and their direct contents. Deliberately NOT a deep
        recursive size (that's expensive and this is a diagnostic nicety,
        not a precise memory profiler) -- good enough to spot "this
        registry is suspiciously huge", not to budget bytes exactly."""
        total = sys.getsizeof(self._items) + sys.getsizeof(self._urn_index) \
            + sys.getsizeof(self._name_index)
        for k, v in self._items.items():
            total += sys.getsizeof(k) + sys.getsizeof(v)
        return total

    # -- serialization ----------------------------------------------------

    def serialize(self) -> Dict[str, Any]:
        """Returns a JSON-compatible dict: registry name + items in
        deterministic (insertion) order. Round-trips via deserialize()."""
        return {
            "registry": self._name,
            "version": 1,
            "items": [self._serializer(item) for item in self.values()],
        }

    def to_json(self, **json_kwargs: Any) -> str:
        return json.dumps(self.serialize(), **json_kwargs)

    @classmethod
    def deserialize(
        cls,
        data: Dict[str, Any],
        *,
        id_of: Extractor = _default_id_of,
        urn_of: Extractor = _default_urn_of,
        name_of: Extractor = _default_name_of,
        serializer: Serializer = _default_serializer,
        deserializer: Deserializer = _default_deserializer,
        case_insensitive_names: bool = True,
    ) -> "CanonicalRegistry[Any]":
        """Rebuilds a registry from serialize()'s output (or an
        equivalent dict). Items are re-inserted in the exact order they
        appear in `data["items"]`, so deterministic ordering survives the
        round trip. `deserializer` should reconstruct whatever item type
        T actually is (defaults to leaving each item as a plain dict)."""
        if "items" not in data:
            raise RegistrySerializationError(
                "cannot deserialize: input is missing the required "
                "'items' key (expected the shape produced by "
                "CanonicalRegistry.serialize())"
            )
        registry: "CanonicalRegistry[Any]" = cls(
            name=data.get("registry", "registry"),
            id_of=id_of, urn_of=urn_of, name_of=name_of,
            serializer=serializer, deserializer=deserializer,
            case_insensitive_names=case_insensitive_names,
        )
        for raw in data["items"]:
            item = registry._deserializer(raw)
            registry.insert(item)
        return registry

    @classmethod
    def from_json(cls, text: str, **kwargs: Any) -> "CanonicalRegistry[Any]":
        return cls.deserialize(json.loads(text), **kwargs)
