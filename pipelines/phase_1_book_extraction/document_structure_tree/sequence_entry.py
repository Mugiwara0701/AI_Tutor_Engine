"""
document_structure_tree/sequence_entry.py — Milestone 2.1: `SequenceEntry`
(schema §2.7) and Typed Canonical References (schema §2.8).

SCOPE: `SequenceEntry` is a closed value type -- the atomic unit of a
`HeadingNode`'s reading order. This module implements ONLY the type
itself: its shape, its own local constructor-time validation, and its
JSON round-trip. It does NOT implement:

  - Reference *resolution* (R1: a `heading`-type `ref` actually
    resolving to a node whose `parent_id` matches the containing node;
    R2/R3: a `content`-type `ref` resolving against the canonical
    registries and matching its authoritative `object_type` there) --
    these require external tree/registry state a single `SequenceEntry`
    does not have access to, and belong to the validation engine
    (roadmap M5), out of scope here.
  - Tree-wide completeness (R4: every canonical object appears in
    exactly one `sequence` entry across the whole tree) -- also a
    whole-tree, validation-engine concern (roadmap M5).

What IS in scope and enforced here, at construction time, is the one
check schema §6 calls out as a direct, *local*, "mechanical consequence
of §11's closed-type contract" and not a whole-tree invariant: that
`entry_type` and the shape of `ref`/`object_type` agree with each other
(architecture §11, schema §2.7, §6 -- "a conforming validator should
treat [a mismatched entry_type/object_type pairing] as a schema-
conformance failure (B1)"). This is exactly the kind of check a single
object can verify about itself, unlike R1-R4.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from .enums import EntryType
from .exceptions import DSTSerializationError, DSTValueError
from .primitives import CanonicalObjectId, NodeId, ObjectType
from .serialization import OMIT, json_object, require_dict, require_key

__all__ = ["SequenceEntry"]

# The reference a SequenceEntry carries is a NodeId when entry_type is
# `heading`, or a CanonicalObjectId (schema §2.8's Typed Canonical
# Reference) when entry_type is `content`. There is no third case --
# EntryType is a closed two-value discriminator (schema §2.1, §18.5).
_Ref = Union[NodeId, CanonicalObjectId]


@dataclass(frozen=True)
class SequenceEntry:
    """A single ordered element of `HeadingNode.sequence` (schema
    §2.7). Position in the containing list *is* the order -- there is
    no `order_index` field on this type, and none may ever be added
    without deprecating the type (§11, §18.3, §18.5); this is enforced
    structurally simply by this dataclass never declaring one.

    When `entry_type = content`, the `(ref, object_type)` pair together
    *is* the Typed Canonical Reference described in schema §2.8 -- not
    a separate wrapper object, exactly as §2.8 states ("This is not a
    separate JSON object -- it is the shape carried by content-type
    SequenceEntrys"). `object_type` is the *only* fact about the
    referenced object permitted to appear here (§2.8, closing
    statement); no other field may ever be added to this type for that
    purpose.
    """

    entry_type: EntryType
    ref: _Ref
    object_type: Optional[ObjectType] = None

    def __post_init__(self) -> None:
        if self.entry_type is EntryType.HEADING:
            if not isinstance(self.ref, NodeId):
                raise DSTValueError(
                    "SequenceEntry: entry_type='heading' requires `ref` to "
                    f"be a NodeId (schema §2.7); got {type(self.ref).__name__}."
                )
            if self.object_type is not None:
                raise DSTValueError(
                    "SequenceEntry: `object_type` must be absent when "
                    "entry_type='heading' (schema §2.7, §6 -- B1 shape rule); "
                    f"got object_type={self.object_type!r}."
                )
        elif self.entry_type is EntryType.CONTENT:
            if not isinstance(self.ref, CanonicalObjectId):
                raise DSTValueError(
                    "SequenceEntry: entry_type='content' requires `ref` to "
                    "be a CanonicalObjectId (schema §2.7, §2.8); got "
                    f"{type(self.ref).__name__}."
                )
            if self.object_type is None:
                raise DSTValueError(
                    "SequenceEntry: `object_type` is required when "
                    "entry_type='content' (schema §2.7, §2.8, §6 -- B1 shape "
                    "rule)."
                )
        else:  # pragma: no cover - EntryType is a closed 2-value enum
            raise DSTValueError(f"SequenceEntry: unrecognized entry_type {self.entry_type!r}.")

    # ----------------------------------------------------------------
    # Ergonomic constructors -- avoid callers having to remember which
    # combination of entry_type/object_type is legal for which ref kind.
    # ----------------------------------------------------------------

    @classmethod
    def heading(cls, ref: NodeId) -> "SequenceEntry":
        """Construct a `heading`-type entry pointing at a child node."""
        return cls(entry_type=EntryType.HEADING, ref=ref, object_type=None)

    @classmethod
    def content(cls, ref: CanonicalObjectId, object_type: ObjectType) -> "SequenceEntry":
        """Construct a `content`-type entry -- a Typed Canonical
        Reference (schema §2.8) -- pointing at a canonical object."""
        return cls(entry_type=EntryType.CONTENT, ref=ref, object_type=object_type)

    # ----------------------------------------------------------------
    # Serialization (schema §5)
    # ----------------------------------------------------------------

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("entry_type", self.entry_type.to_json()),
                ("ref", self.ref.to_json()),
                ("object_type", self.object_type.to_json() if self.object_type is not None else OMIT),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "SequenceEntry":
        data = require_dict(data, "SequenceEntry")
        entry_type = EntryType.from_json(require_key(data, "entry_type", "SequenceEntry"))
        raw_ref = require_key(data, "ref", "SequenceEntry")

        if entry_type is EntryType.HEADING:
            if "object_type" in data:
                raise DSTSerializationError(
                    "SequenceEntry.from_json: 'object_type' must not be "
                    "present when entry_type='heading' (schema §2.7, §5.3)."
                )
            ref: _Ref = NodeId.from_json(raw_ref)
            object_type: Optional[ObjectType] = None
        else:
            object_type = ObjectType.from_json(require_key(data, "object_type", "SequenceEntry"))
            ref = CanonicalObjectId.from_json(raw_ref)

        return cls(entry_type=entry_type, ref=ref, object_type=object_type)
