"""
document_structure_tree/heading_node.py — Milestone 2.1: `HeadingNode`
(schema §2.6).

SCOPE: this module implements ONLY the `HeadingNode` value type -- its
shape, the *local* constructor-time validation a single node can verify
about itself, and its JSON round-trip. Deliberately NOT implemented
here (all belong to later milestones per the roadmap, and are named
explicitly out of scope for this milestone):

  - Tree construction, parent resolution, or hierarchy generation --
    this type stores `parent_id` as an opaque `NodeId` reference; it
    never resolves it against a tree (roadmap M2's tree-assembly
    concerns, and roadmap M4's structural validators).
  - Depth consistency (`level == parent.level + 1`, schema §2.6) --
    this requires resolving `parent_id` against the rest of a tree,
    which a single `HeadingNode` cannot do about itself; this is a
    build-integrity check for a future validation engine (roadmap M4).
  - `chapter_id` matching `artifact_metadata.chapter_id` -- an
    artifact-level cross-check performed at the `DocumentStructureTree`
    level (see `document_structure_tree.py`), not by this type.
  - `node_id` derivation (architecture §14) -- performed by
    `identity.compute_node_id` (Milestone 1) *before* a `HeadingNode` is
    constructed; this type only stores the already-derived value, it
    never (re)computes it. This keeps `HeadingNode` a pure data holder,
    with no dependency on sibling context.
  - `span` computation (architecture §13) -- performed by a future
    milestone (roadmap M3) and passed in already-computed; this type
    only stores and carries the given `Span` value.
  - Referential/completeness validation of `sequence` entries (R1, R4)
    and reachability (S1, S2, S4) -- whole-tree validation-engine
    concerns (roadmap M4-M6).

What IS in scope and enforced at construction time: the one purely
local structural rule schema §2.6 states as a fact about a node in
isolation -- `parent_id` is `None` if and only if `level == 0`
(architecture §15 S2's local half; the "exactly one such node per
chapter" half of S2 needs the whole tree and is out of scope here).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .exceptions import DSTSerializationError, DSTValueError
from .primitives import ChapterId, Level, NodeId, Span
from .sequence_entry import SequenceEntry
from .enums import EntryType
from .serialization import OMIT, json_object, require_dict, require_key, require_non_empty_str

__all__ = ["HeadingNode"]


@dataclass(frozen=True)
class HeadingNode:
    """The sole structural node type in `tree` (schema §2.6) --
    every heading in a chapter, including the chapter root
    (`level = 0`), is one of these; there are no subtypes (architecture
    §10).

    Field order below groups every field the schema marks "Required"
    first, followed by the two schema-"Optional" fields (`number`,
    `title`) last -- a reordering forced by Python dataclass rules
    (fields with defaults must follow fields without), not a
    reordering of the schema's own Required/Optional classification.
    """

    node_id: NodeId
    chapter_id: ChapterId
    level: Level
    parent_id: Optional[NodeId]
    sequence: Tuple[SequenceEntry, ...]
    span: Span
    number: Optional[str] = None
    title: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", tuple(self.sequence))

        # parent_id is null iff level == 0 (schema §2.6; the local half
        # of S2 -- the "exactly one root per chapter" half needs the
        # whole tree and is a validation-engine concern, out of scope).
        if self.level.is_root() and self.parent_id is not None:
            raise DSTValueError(
                "HeadingNode: parent_id must be null when level=0 (schema "
                f"§2.6); got parent_id={self.parent_id.value!r} at level=0."
            )
        if not self.level.is_root() and self.parent_id is None:
            raise DSTValueError(
                "HeadingNode: parent_id is required (non-null) for every "
                f"non-root node (schema §2.6); got level={self.level.value} "
                "with parent_id=None."
            )

        if self.number is not None:
            object.__setattr__(
                self, "number", require_non_empty_str(self.number, "HeadingNode.number")
            )
        if self.title is not None:
            object.__setattr__(
                self, "title", require_non_empty_str(self.title, "HeadingNode.title")
            )

    # ----------------------------------------------------------------
    # Derived views (schema §2.7, "Derived views") -- never stored,
    # always recomputed by filtering `sequence`. Provided here as a
    # read-only convenience over *this node's own* sequence only; they
    # do not resolve `heading` refs into other HeadingNode objects
    # (that would be tree-level lookup, out of scope for this type).
    # ----------------------------------------------------------------

    @property
    def children(self) -> Tuple[NodeId, ...]:
        """The `NodeId`s of this node's child headings, in reading
        order -- the subsequence of `sequence` with `entry_type =
        'heading'` (schema §2.7). Not resolved against a tree."""
        return tuple(entry.ref for entry in self.sequence if entry.entry_type is EntryType.HEADING)  # type: ignore[misc]

    @property
    def content(self) -> Tuple[SequenceEntry, ...]:
        """The subsequence of `sequence` with `entry_type = 'content'`,
        order preserved (schema §2.7)."""
        return tuple(entry for entry in self.sequence if entry.entry_type is EntryType.CONTENT)

    # ----------------------------------------------------------------
    # Serialization (schema §5)
    # ----------------------------------------------------------------

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("node_id", self.node_id.to_json()),
                ("chapter_id", self.chapter_id.to_json()),
                ("level", self.level.to_json()),
                # parent_id: present and explicitly null for the root,
                # present as a string otherwise -- never omitted
                # (schema §5.3).
                ("parent_id", self.parent_id.to_json() if self.parent_id is not None else None),
                ("number", self.number if self.number is not None else OMIT),
                ("title", self.title if self.title is not None else OMIT),
                ("sequence", [entry.to_json() for entry in self.sequence]),
                ("span", self.span.to_json()),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "HeadingNode":
        data = require_dict(data, "HeadingNode")

        if "parent_id" not in data:
            raise DSTSerializationError(
                "HeadingNode.from_json: missing required key 'parent_id' "
                "(schema §5.3 -- present and possibly null, never omitted)."
            )
        raw_parent_id = data["parent_id"]
        parent_id = NodeId.from_json(raw_parent_id) if raw_parent_id is not None else None

        sequence = tuple(
            SequenceEntry.from_json(entry)
            for entry in require_key(data, "sequence", "HeadingNode")
        )

        return cls(
            node_id=NodeId.from_json(require_key(data, "node_id", "HeadingNode")),
            chapter_id=ChapterId.from_json(require_key(data, "chapter_id", "HeadingNode")),
            level=Level.from_json(require_key(data, "level", "HeadingNode")),
            parent_id=parent_id,
            sequence=sequence,
            span=Span.from_json(require_key(data, "span", "HeadingNode")),
            number=data.get("number"),
            title=data.get("title"),
        )
