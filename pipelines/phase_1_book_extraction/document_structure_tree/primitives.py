"""
document_structure_tree/primitives.py — Milestone 1: primitive/reusable
value types (schema §2.1).

SCOPE: every "Supporting / Reusable Type" from
`DST_Schema_Design_v1.1.md` §2.1 is implemented here as a small, frozen
(immutable) dataclass wrapping the underlying scalar, with construction-
time validation and a `to_json`/`from_json` pair satisfying
`serialization.JsonSerializable`. Nothing in this module builds a
`HeadingNode`, a `SequenceEntry`, or any other composite artifact model
-- those are later milestones (roadmap M2+).

WHY WRAPPER DATACLASSES, NOT PLAIN `str`/`int`: schema §2.1 defines each
of these as a distinct type with its own constraints (non-empty,
non-negative, a specific string format, ...). A raw `str` parameter
gives no static or runtime signal that a `ChapterId` was passed where a
`NodeId` was expected, and provides nowhere for that type's own
validation to live. Frozen dataclasses give both: a real type boundary,
and one place per type to enforce schema §2.1's constraints -- at
essentially zero runtime cost, and consistent with this codebase's
existing convention of plain, storable dataclasses for schema-level
concerns (see knowledge_graph/schema.py).

`ObjectType` is deliberately declared here, alongside the identifier
types, rather than in enums.py, even though the roadmap's own M0/M1
"Enumerations" text lists it alongside `EntryType`/`ValidationStatus`/
etc. Schema §2.1 itself classifies `ObjectType` as "a String drawn from
the canonical registries' object-type vocabulary ... Open string set
owned by the canonical registries, not enumerated here" -- i.e. it is
explicitly NOT a closed set the DST schema may enumerate, unlike
`EntryType`/`ValidationStatus`/`HeadingDetectionMethod`/`InvariantId`
(see enums.py's own docstring for the corresponding note on that side).
Implementing `ObjectType` as a closed Python `Enum` would silently
narrow an open vocabulary the frozen schema deliberately leaves open
(§20: "new canonical object types never require a DST schema change").
This is a case of following the frozen schema's own classification over
the roadmap's illustrative (and here, imprecise) grouping, per this
milestone's instruction to point at the spec rather than invent.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .exceptions import DSTValueError
from .serialization import (
    OMIT,
    json_object,
    require_dict,
    require_iso8601_utc,
    require_key,
    require_non_empty_str,
    require_non_negative_int,
    require_semver,
    require_sha256_hex,
)

__all__ = [
    "ChapterId",
    "NodeId",
    "CanonicalObjectId",
    "ObjectType",
    "Level",
    "SchemaVersion",
    "CompilerVersion",
    "IdentitySchemeVersion",
    "Timestamp",
    "Fingerprint",
    "BlockIndex",
    "BlockRange",
    "PageLocator",
    "PageRange",
    "Span",
]


# --------------------------------------------------------------------------
# Opaque string identifiers
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ChapterId:
    """Opaque string identifier for a source chapter (schema §2.1).
    Owned upstream by Phase 1 extraction, not by this schema -- this
    type only enforces "non-empty", it never parses or derives meaning
    from the string's internal structure (schema §2.1, closing note)."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_non_empty_str(self.value, "ChapterId"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "ChapterId":
        return cls(data)


@dataclass(frozen=True)
class NodeId:
    """Opaque string identifier for a heading node, derived per
    architecture §14 / schema §4 (see identity.py). Unique only within
    a `ChapterId` scope (I3) -- carries no guaranteed cross-chapter or
    cross-edition meaning (schema §2.1)."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_non_empty_str(self.value, "NodeId"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "NodeId":
        return cls(data)


@dataclass(frozen=True)
class CanonicalObjectId:
    """Opaque string identifier for a canonical educational object,
    owned by the canonical registries, not this schema (schema §2.1).
    This type enforces only "non-empty"; resolvability against the
    canonical registries (R2) is a validation-engine concern, out of
    scope for this milestone."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_non_empty_str(self.value, "CanonicalObjectId"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "CanonicalObjectId":
        return cls(data)


@dataclass(frozen=True)
class ObjectType:
    """String drawn from the canonical registries' open object-type
    vocabulary (`paragraph_group`, `definition`, `figure`, `example`,
    ...) -- schema §2.1. Deliberately NOT a closed enum; see this
    module's own docstring for why. This type enforces only
    "non-empty"; matching the referenced object's authoritative type
    (R3) is a validation-engine concern, out of scope for this
    milestone."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_non_empty_str(self.value, "ObjectType"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "ObjectType":
        return cls(data)


# --------------------------------------------------------------------------
# Depth
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Level:
    """Non-negative integer depth, unbounded (schema §2.1). `0` is
    reserved for the chapter root (S2); depth is otherwise open-ended
    by design, so no new heading level ever requires a schema change
    (architecture §20)."""

    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_non_negative_int(self.value, "Level"))

    def is_root(self) -> bool:
        """True iff this is the chapter-root depth (schema §2.1: `0`
        reserved for the root, S2)."""
        return self.value == 0

    def child(self) -> "Level":
        """The depth immediately below this one -- a pure arithmetic
        convenience (`level + 1`), not a tree-assembly operation. Used
        by schema §2.6's depth-consistency check
        (`level = parent.level + 1`), which a later milestone's
        validator applies against real nodes; this method only
        expresses the arithmetic itself."""
        return Level(self.value + 1)

    def __int__(self) -> int:
        return self.value

    def to_json(self) -> int:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "Level":
        return cls(data)


# --------------------------------------------------------------------------
# Version fields (architecture §16)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SchemaVersion:
    """Semantic-version string (`MAJOR.MINOR.PATCH`) answering "what
    shape is this artifact?" (architecture §16). Consumers gate parsing
    on `major` (schema §2.1)."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_semver(self.value, "SchemaVersion"))

    @property
    def major(self) -> int:
        return int(self.value.split(".", 1)[0])

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "SchemaVersion":
        return cls(data)


@dataclass(frozen=True)
class CompilerVersion:
    """Semantic-version string identifying the compiler build that
    produced an artifact -- informational only, never a structural
    signal (architecture §16, schema §2.1)."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_semver(self.value, "CompilerVersion"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "CompilerVersion":
        return cls(data)


@dataclass(frozen=True)
class IdentitySchemeVersion:
    """Opaque version token (integer or string in source form, always
    serialized as a JSON string per schema §5.5) marking which rules a
    `node_id` was derived under. Any change is a critical signal
    requiring Phase 2 reconciliation (architecture §16/§17) -- this
    type itself only carries and compares the token; it does not
    interpret it."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value if isinstance(self.value, str) else str(self.value)
        object.__setattr__(self, "value", require_non_empty_str(normalized, "IdentitySchemeVersion"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "IdentitySchemeVersion":
        return cls(data)


# --------------------------------------------------------------------------
# Timestamp / Fingerprint
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Timestamp:
    """ISO-8601 UTC datetime string, e.g. `2026-07-15T09:00:00Z`
    (schema §2.1)."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_iso8601_utc(self.value, "Timestamp"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "Timestamp":
        return cls(data)


@dataclass(frozen=True)
class Fingerprint:
    """SHA-256 digest, lowercase hex string (schema §2.1). Computed per
    B3 over exactly a chapter's nodes' structural-identity fields --
    that specific hashing responsibility belongs to a later milestone
    (roadmap M8); this type only carries and validates the resulting
    digest shape."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_sha256_hex(self.value, "Fingerprint"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "Fingerprint":
        return cls(data)

    @classmethod
    def of(cls, payload: bytes) -> "Fingerprint":
        """Generic convenience constructor: the SHA-256 hex digest of
        arbitrary bytes. Deliberately generic (no DST-specific hashing
        policy, e.g. "which fields go into a chapter_fingerprint") --
        that policy is schema §2.3/§15 B3's concern, owned by roadmap
        M8, not this primitive type."""
        return cls(hashlib.sha256(payload).hexdigest())


# --------------------------------------------------------------------------
# Block-indexed ranges
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BlockIndex:
    """Non-negative integer indexing the compiler's internal block
    sequence for a chapter; defined by Chapter JSON, not this schema
    (schema §2.1)."""

    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_non_negative_int(self.value, "BlockIndex"))

    def __int__(self) -> int:
        return self.value

    def to_json(self) -> int:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "BlockIndex":
        return cls(data)


@dataclass(frozen=True)
class BlockRange:
    """`{ start: BlockIndex, end: BlockIndex }`, half-open `[start,
    end)` over block indices (schema §2.1, "Bound-convention note").
    `start <= end` is enforced here; authoritative for span
    monotonicity (S3, architecture §13) -- the monotonicity *check*
    itself belongs to a later milestone's validator (roadmap M4), this
    type only guarantees the range it carries is internally well-
    formed."""

    start: BlockIndex
    end: BlockIndex

    def __post_init__(self) -> None:
        if self.start.value > self.end.value:
            raise DSTValueError(
                f"BlockRange.start ({self.start.value}) must be <= "
                f"BlockRange.end ({self.end.value}) (schema §2.1)."
            )

    def is_empty(self) -> bool:
        """True for a zero-width range (`start == end`) -- valid under
        half-open semantics, distinct from `Span`'s own "both fields
        absent" empty-span case (architecture §13), which this method
        does not model."""
        return self.start.value == self.end.value

    def contains(self, other: "BlockRange") -> bool:
        """Half-open containment: is `other` fully inside `self`? Pure
        arithmetic on the two ranges' own bounds -- reusable wherever
        span containment needs to be asked as a yes/no question. This
        is NOT S3 itself: S3 (architecture §15) is a validator that
        walks a whole tree and reports a `Violation`, which is a
        later-milestone, validation-engine concern (roadmap M4) out of
        scope here. This method only answers the underlying arithmetic
        question a future S3 implementation (and any other caller)
        would need."""
        return self.start.value <= other.start.value and other.end.value <= self.end.value

    def is_adjacent_to(self, other: "BlockRange") -> bool:
        """True if `self` and `other` share a boundary with no gap and
        no overlap under half-open semantics (`self.end == other.start`
        or `other.end == self.start`) -- the property schema §2.1's own
        "Bound-convention note" example calls out (`BlockRange{0,5}`
        and `BlockRange{5,10}` are adjacent, non-overlapping)."""
        return self.end.value == other.start.value or other.end.value == self.start.value

    def to_json(self) -> Dict[str, Any]:
        return {"start": self.start.to_json(), "end": self.end.to_json()}

    @classmethod
    def from_json(cls, data: Any) -> "BlockRange":
        data = require_dict(data, "BlockRange")
        return cls(
            start=BlockIndex.from_json(require_key(data, "start", "BlockRange")),
            end=BlockIndex.from_json(require_key(data, "end", "BlockRange")),
        )


# --------------------------------------------------------------------------
# Page-locator ranges
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PageLocator:
    """String page locator supporting non-numeric pagination (e.g.
    front-matter roman numerals) -- best-effort, source-format-
    specific, and deliberately not format-validated here (schema
    §2.1). Only "non-empty" is enforced."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_non_empty_str(self.value, "PageLocator"))

    def __str__(self) -> str:
        return self.value

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "PageLocator":
        return cls(data)


@dataclass(frozen=True)
class PageRange:
    """`{ start: PageLocator, end: PageLocator }`, both endpoints
    **inclusive** (schema §2.1, §2.9's "Page inclusivity convention") --
    the opposite bound convention from `BlockRange`. Non-authoritative
    for validation (§13); this type deliberately does not enforce any
    `start <= end` ordering, since `PageLocator` values are opaque,
    source-format-specific strings (e.g. roman numerals) with no
    schema-defined total order."""

    start: PageLocator
    end: PageLocator

    def to_json(self) -> Dict[str, Any]:
        return {"start": self.start.to_json(), "end": self.end.to_json()}

    @classmethod
    def from_json(cls, data: Any) -> "PageRange":
        data = require_dict(data, "PageRange")
        return cls(
            start=PageLocator.from_json(require_key(data, "start", "PageRange")),
            end=PageLocator.from_json(require_key(data, "end", "PageRange")),
        )


# --------------------------------------------------------------------------
# Span
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Span:
    """`{ block_range?: BlockRange, page_range?: PageRange }` (schema
    §2.1/§2.9). Both fields independently optional; both absent
    together is the defined "empty span" case (architecture §13). The
    one asymmetric constraint schema §2.9 states -- `page_range`
    present requires `block_range` present -- is enforced here;
    `block_range` present with `page_range` absent is valid and
    expected for source formats lacking stable pagination.

    This type only carries a span's value; *computing* a node's span
    bottom-up from owned content and descendants (architecture §13) is
    a later milestone's concern (roadmap M3), out of scope here."""

    block_range: Optional[BlockRange] = None
    page_range: Optional[PageRange] = None

    def __post_init__(self) -> None:
        if self.page_range is not None and self.block_range is None:
            raise DSTValueError(
                "Span.page_range present requires Span.block_range to "
                "also be present (schema §2.9's asymmetric optionality rule)."
            )

    def is_empty(self) -> bool:
        """True for the defined "empty span" case (architecture §13):
        both `block_range` and `page_range` absent -- a heading with no
        directly-owned content and no descendants."""
        return self.block_range is None and self.page_range is None

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("block_range", self.block_range.to_json() if self.block_range is not None else OMIT),
                ("page_range", self.page_range.to_json() if self.page_range is not None else OMIT),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "Span":
        data = require_dict(data, "Span")
        block_range = BlockRange.from_json(data["block_range"]) if "block_range" in data else None
        page_range = PageRange.from_json(data["page_range"]) if "page_range" in data else None
        return cls(block_range=block_range, page_range=page_range)
