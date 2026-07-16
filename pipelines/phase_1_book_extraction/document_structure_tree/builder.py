"""
document_structure_tree/builder.py — Milestone 2.2: the DST Builder
(roadmap M2, "Flat Tree Assembly", architecture §8, §10, §11).

SCOPE: this module builds the in-memory, flat, ID-indexed collection of
`HeadingNode`s (schema §2.6) from an already-completed Phase 1
representation of a chapter's heading structure and per-heading owned
content. It performs exactly the responsibilities Milestone 2.2 lists:

  - constructing `HeadingNode` instances (via `heading_node.HeadingNode`,
    Milestone 2.1 -- never redefined here),
  - assigning each node's `node_id` deterministically (via
    `identity.compute_node_id`, Milestone 1 -- never re-implemented
    here),
  - establishing `parent_id` by resolving each source heading's parent
    reference against the same input batch,
  - computing `level` structurally (root = 0, otherwise
    `parent.level + 1`) rather than trusting any level-like field a
    source record happens to carry,
  - creating the chapter-root node (`level = 0`, `parent_id = None`),
  - building the flat node collection plus the `node_id -> node` and
    `parent_id -> children` indices roadmap M2 calls out as "a
    consumer/implementation responsibility, not a stored field",
  - constructing each node's `sequence` (schema §11) in textbook
    reading order, interleaving child headings with directly-owned
    content,
  - creating Typed Canonical References (schema §12) -- `(ref,
    object_type)` pairs -- for every content id a heading owns.

NOT implemented here (out of scope for this milestone; see the
package's own `__init__.py` and each model module's docstring for the
fuller boundary):

  - OCR, layout analysis, heading detection, or any other Phase 1
    extraction work. The builder consumes an already-decided heading
    structure; it never decides *whether* something is a heading, only
    *how the given headings assemble into a tree*.
  - `span` computation (architecture §13, roadmap M3). Every
    constructed node's `span` is the empty `Span()` -- the correct,
    fully-defined value for "no material yet aggregated" (§13,
    Empty-node behavior) -- pending M3.
  - The validation engine (S1-S4, R1-R4, O1-O2, I1-I3, B1-B3; roadmap
    M4-M6). In particular, resolving a *content* reference against the
    canonical registries (R2) or checking its `object_type` matches
    the registry's authoritative type (R3) is explicitly deferred: the
    builder creates the `(ref, object_type)` pair the source data
    names and never checks whether `ref` actually resolves anywhere.
    A dangling content reference is not a builder error.
  - `ArtifactMetadata` / `BuildProvenance` / `ValidationMetadata`
    assembly, `chapter_fingerprint` computation, or constructing an
    actual `document_structure_tree.DocumentStructureTree` artifact
    instance (roadmap M7-M9) -- that type's constructor *requires*
    exactly the three pieces this milestone does not build. This
    builder's output is `tree` (schema §9.4's flat node collection,
    the one layer schema §9's "isolation principle" says must be fully
    interpretable on its own) plus the two lookup indices, not the
    four-layer artifact envelope.
  - Persistence, JSON artifact generation, or pipeline wiring (roadmap
    M9-M10).

TWO LAYERS, ONE REASON: `build_tree()` below is the actual tree-assembly
algorithm, expressed over small, generic, framework-agnostic source
records (`HeadingSource` / `ContentRef`) that carry nothing but the
structural-identity and ordering facts architecture §14/§11 care about.
`build_tree_from_chapter_json()` is a thin adapter from
`schemas.chapter_schema.ChapterJSON` (the attached Phase 1 model,
consumed here read-only, exactly as the milestone instructions require)
onto those same generic records. Keeping the algorithm itself
independent of `ChapterJSON`'s ~30-field `TopicNode` shape (and of
`pydantic`) means the tree-assembly logic can be exhaustively unit
tested against small, explicit, hand-built fixtures -- exactly roadmap
M2's own prescribed testing approach ("a test fixture at this stage") --
while the adapter is a separate, narrow, independently-reviewable seam
that does nothing but reshape data.

READING-ORDER POLICY (best-effort, documented, and bounded -- see
`_interleave` below): Phase 1's `TopicNode` records an explicit,
chapter-global `reading_order` for headings, but nothing analogous
tying a given content item's position to a specific point in that same
order relative to its owning heading's other content and child
headings. This module resolves that with the same kind of documented,
best-effort convention the frozen schema itself already uses elsewhere
(e.g. `PageLocator`, schema §2.1: "best-effort, source-format-specific,
deliberately not format-validated"): entries owned directly by one
heading are ordered by `(page, position)` where `position` is any
caller-supplied monotonic proxy for on-page vertical placement (e.g. a
bounding box's `y0`), falling back to the order the caller originally
listed same-page/no-page entries in when `(page, position)` ties. This
is a placement heuristic, not a validated fact -- it never contributes
to `node_id` (§14) and is superseded, node by node, the moment a real
positional source is available.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .exceptions import DSTBuildError
from .heading_node import HeadingNode
from .identity import compute_node_id
from .primitives import CanonicalObjectId, ChapterId, Level, NodeId, ObjectType, Span
from .sequence_entry import SequenceEntry

__all__ = [
    "HeadingSource",
    "ContentRef",
    "BuiltTree",
    "build_tree",
    "build_tree_from_chapter_json",
]

# Sentinel key `content_by_heading` uses for content owned directly by
# the chapter root (a heading has no such case -- `heading.id` is
# always a real string) -- see `HeadingSource`/`build_tree` docstrings.
ROOT_CONTENT_KEY: Optional[str] = None


# ==========================================================================
# Generic source records — the builder's own input contract
# ==========================================================================

@dataclass(frozen=True)
class HeadingSource:
    """One heading, as given to `build_tree()` -- carries exactly the
    structural-identity fields architecture §14 reads (`id`, `parent`,
    `number`) plus the two ordering facts needed to place it and its
    siblings (`reading_order`) and to interleave it against its
    parent's directly-owned content (`page`, `position`). Deliberately
    generic: shape-compatible with, but independent of,
    `schemas.chapter_schema.TopicNode` -- see module docstring.

    Never carries `title`: this milestone's builder does not read
    `title` at all (architecture §14 -- `title` never contributes to
    identity, and the builder does not need it for tree *shape*); the
    adapter still copies it straight onto the constructed `HeadingNode`
    from the source `TopicNode`, since `HeadingNode.title` is a
    plain structural-state field, not something the tree-assembly
    algorithm itself needs to reason about.
    """

    id: str
    parent_id: Optional[str]  # None => attaches directly under the chapter root
    number: Optional[str] = None
    title: Optional[str] = None
    reading_order: int = 0
    page: Optional[int] = None
    position: float = 0.0


@dataclass(frozen=True)
class ContentRef:
    """One content object owned directly by a heading (or the chapter
    root) -- the source-side shape of a Typed Canonical Reference
    (schema §12): an id + `object_type`, plus the same optional
    `(page, position)` ordering facts `HeadingSource` carries, used
    only to place this entry within `sequence` -- never stored on the
    resulting `SequenceEntry` (schema §11: no positional field on that
    closed type)."""

    object_id: str
    object_type: str
    page: Optional[int] = None
    position: float = 0.0


@dataclass(frozen=True)
class BuiltTree:
    """The builder's output: the flat node collection (schema §9.4's
    `tree`) plus the two lookup indices roadmap M2 calls for --
    `node_id -> node` and `parent_id -> children` -- built once here so
    callers never re-derive them. `root` is also `nodes_by_id`'s entry
    for the chapter's own `level = 0` node, included separately purely
    for caller convenience."""

    root: HeadingNode
    tree: Tuple[HeadingNode, ...]
    nodes_by_id: Dict[NodeId, HeadingNode] = field(repr=False)
    children_by_parent_id: Dict[NodeId, Tuple[NodeId, ...]] = field(repr=False)


# ==========================================================================
# build_tree — the tree-assembly algorithm
# ==========================================================================

def build_tree(
    chapter_id: ChapterId,
    headings: Sequence[HeadingSource],
    content_by_heading: Optional[Mapping[Optional[str], Sequence[ContentRef]]] = None,
) -> BuiltTree:
    """Build the complete flat `HeadingNode` collection for one chapter.

    Args:
        chapter_id: identity of the source chapter (schema §2.1);
            stamped onto every constructed node.
        headings: every heading in the chapter, in any order. Each
            `HeadingSource.parent_id` must be `None` (attaches directly
            under the chapter root) or must equal another
            `HeadingSource.id` in this same sequence -- see "Errors"
            below.
        content_by_heading: for each heading id (or `ROOT_CONTENT_KEY`
            / `None`, for content owned directly by the chapter root),
            the `ContentRef`s that heading directly owns. A heading
            with no entry here, or an empty entry, simply owns no
            content directly -- not an error (a node's `sequence` may
            legitimately consist only of child-heading entries, or be
            empty for a childless, contentless leaf).

    Returns:
        A `BuiltTree` with the chapter root (architecture §14 -- the
        one `level = 0` node) plus one `HeadingNode` per `HeadingSource`
        given, hierarchy fully established via `parent_id`, `level`
        computed structurally from that hierarchy (never read off a
        source field), and every node's `sequence` built in
        best-effort textbook reading order (see module docstring).
        Every node's `span` is the empty `Span()`, pending span
        computation (roadmap M3, out of scope here).

    Raises:
        DSTBuildError: if two `HeadingSource`s share the same `id`, if
            a `HeadingSource.parent_id` names no `id` among `headings`,
            or if the parent chain from any heading back toward the
            root contains a cycle (so no chain of `parent_id`s from
            that heading ever actually reaches the root). All three
            are preconditions for building anything at all -- a node's
            `node_id` is derived recursively from its parent's own
            identity (architecture §14), so an unresolvable or cyclic
            parent chain leaves no `node_id` computable in the first
            place. This is not §15's S1 (a *validation* invariant
            checked against an already-built tree's data) -- it is
            what makes building the tree possible at all.
    """
    content_by_heading = content_by_heading or {}

    # ---- 1. Validate heading ids are unique, and index by id --------
    by_id: Dict[str, HeadingSource] = {}
    for h in headings:
        if h.id in by_id:
            raise DSTBuildError(
                f"build_tree: duplicate heading id {h.id!r} -- every "
                "HeadingSource.id must be unique within one build "
                "(architecture §14 -- node_id derivation assumes a "
                "heading's source id is unambiguous)."
            )
        by_id[h.id] = h

    # ---- 2. Validate every non-root parent_id resolves ---------------
    for h in headings:
        if h.parent_id is not None and h.parent_id not in by_id:
            raise DSTBuildError(
                f"build_tree: heading {h.id!r} names parent_id "
                f"{h.parent_id!r}, which is not the id of any heading "
                "in this build (a heading's node_id is derived from "
                "its parent's own identity, so an unresolvable parent "
                "cannot be built)."
            )

    # ---- 3. Cycle detection: every parent chain must reach the root -
    for h in headings:
        seen = {h.id}
        current = h
        while current.parent_id is not None:
            nxt = by_id[current.parent_id]
            if nxt.id in seen:
                raise DSTBuildError(
                    f"build_tree: parent cycle detected involving "
                    f"heading {h.id!r} (chain revisits {nxt.id!r} "
                    "without ever reaching the chapter root)."
                )
            seen.add(nxt.id)
            current = nxt

    # ---- 4. Group siblings, in deterministic sibling order -----------
    # Sort key: (reading_order, id). `id` is only a tiebreaker for a
    # degenerate input that gives two siblings the same reading_order;
    # real Phase 1 output never does, since reading_order is itself a
    # chapter-global enumeration (see builder module docstring / the
    # ChapterJSON adapter below).
    children_source_by_parent: Dict[Optional[str], List[HeadingSource]] = defaultdict(list)
    for h in headings:
        children_source_by_parent[h.parent_id].append(h)
    for siblings in children_source_by_parent.values():
        siblings.sort(key=lambda s: (s.reading_order, s.id))

    # ---- 5. Chapter root -----------------------------------------------
    root_node_id = compute_node_id(chapter_id, Level(0), None)

    # ---- 6. Assign node_id/level top-down (parent before child) ------
    node_id_by_heading_id: Dict[str, NodeId] = {}
    level_by_heading_id: Dict[str, Level] = {}

    def _assign(heading: HeadingSource, parent_node_id: NodeId, parent_level: Level) -> None:
        level = parent_level.child()
        siblings = children_source_by_parent[heading.parent_id]
        number = heading.number if heading.number else None
        if number is None:
            unnumbered_siblings = [s for s in siblings if not s.number]
            unnumbered_ordinal: Optional[int] = unnumbered_siblings.index(heading)
        else:
            unnumbered_ordinal = None
        node_id = compute_node_id(
            chapter_id,
            level,
            parent_node_id,
            number=number,
            unnumbered_ordinal=unnumbered_ordinal,
        )
        node_id_by_heading_id[heading.id] = node_id
        level_by_heading_id[heading.id] = level
        for child in children_source_by_parent.get(heading.id, ()):
            _assign(child, node_id, level)

    for top_level_heading in children_source_by_parent.get(None, ()):
        _assign(top_level_heading, root_node_id, Level(0))

    # ---- 7. Build each node's `sequence`, then the HeadingNode itself
    def _sequence_for(
        own_id: Optional[str],
        child_headings: Sequence[HeadingSource],
    ) -> Tuple[SequenceEntry, ...]:
        heading_entries = [
            (child.page, child.position, SequenceEntry.heading(node_id_by_heading_id[child.id]))
            for child in child_headings
        ]
        content_entries = [
            (ref.page, ref.position, SequenceEntry.content(CanonicalObjectId(ref.object_id), ObjectType(ref.object_type)))
            for ref in content_by_heading.get(own_id, ())
        ]
        return tuple(_interleave(heading_entries + content_entries))

    root = HeadingNode(
        node_id=root_node_id,
        chapter_id=chapter_id,
        level=Level(0),
        parent_id=None,
        sequence=_sequence_for(ROOT_CONTENT_KEY, children_source_by_parent.get(None, ())),
        span=Span(),
    )

    nodes: List[HeadingNode] = [root]
    for h in headings:
        nodes.append(
            HeadingNode(
                node_id=node_id_by_heading_id[h.id],
                chapter_id=chapter_id,
                level=level_by_heading_id[h.id],
                parent_id=(
                    root_node_id if h.parent_id is None else node_id_by_heading_id[h.parent_id]
                ),
                number=h.number,
                title=h.title,
                sequence=_sequence_for(h.id, children_source_by_parent.get(h.id, ())),
                span=Span(),
            )
        )

    # ---- 8. Indices ----------------------------------------------------
    nodes_by_id: Dict[NodeId, HeadingNode] = {n.node_id: n for n in nodes}
    children_by_parent_id: Dict[NodeId, Tuple[NodeId, ...]] = {
        n.node_id: n.children for n in nodes
    }

    return BuiltTree(
        root=root,
        tree=tuple(nodes),
        nodes_by_id=nodes_by_id,
        children_by_parent_id=children_by_parent_id,
    )


def _interleave(
    entries: List[Tuple[Optional[int], float, SequenceEntry]]
) -> List[SequenceEntry]:
    """Best-effort reading-order sort for one node's own `sequence`
    (see module docstring's "READING-ORDER POLICY"). `entries` is a
    list of `(page, position, SequenceEntry)`; a missing `page` sorts
    after every known page (an entry the source data cannot place is
    placed last, deterministically, rather than guessed at the front).
    Python's `sorted()` is stable, so entries tied on `(page,
    position)` keep the relative order `entries` was already given in
    -- callers therefore control the tiebreak simply by the order they
    build `entries` in."""
    return [
        entry
        for _, _, entry in sorted(
            entries, key=lambda item: (item[0] if item[0] is not None else math.inf, item[1])
        )
    ]


# ==========================================================================
# build_tree_from_chapter_json — adapter over the attached Phase 1 model
# ==========================================================================

# TopicNode field name -> canonical `object_type` string (schema §12).
# Matches, one-for-one, the `object_type` default every corresponding
# canonical class in schemas/chapter_schema.py declares for itself
# (Definition.object_type == "definition", Figure.object_type ==
# "figure", ...) -- this dict does not invent a vocabulary, it simply
# names which of TopicNode's id-list fields corresponds to which
# already-frozen canonical object_type. `concepts` / `concept_names`
# are deliberately excluded: a topic's `concepts` list is a keyword/tag
# reference (A4, chapter_schema.py), not a content object directly
# owned and positioned in the chapter's reading order the way a
# Definition/Figure/Example/... is.
_CONTENT_FIELD_TO_OBJECT_TYPE: Tuple[Tuple[str, str], ...] = (
    ("definitions", "definition"),
    ("examples", "example"),
    ("activities", "activity"),
    ("figures", "figure"),
    ("tables", "table"),
    ("equations", "equation"),
    ("diagrams", "diagram"),
    ("charts", "chart"),
    ("graphs", "graph"),
    ("maps", "map"),
    ("timelines", "timeline"),
    ("boxes", "box"),
    ("notes", "note"),
    ("warnings", "warning"),
)

# ChapterJSON top-level list field name -> object_type, used only to
# build the id -> page lookup `_page_index` below (never to decide
# which ids a topic owns -- that is still TopicNode's own per-type id
# lists, per _CONTENT_FIELD_TO_OBJECT_TYPE above).
_TOP_LEVEL_FIELD_BY_OBJECT_TYPE: Dict[str, str] = {
    "definition": "definitions",
    "example": "examples",
    "activity": "activities",
    "figure": "figures",
    "table": "tables",
    "equation": "equations",
    "diagram": "diagrams",
    "chart": "charts",
    "graph": "graphs",
    "map": "maps",
    "timeline": "timelines",
    "box": "boxes",
    "note": "notes",
    "warning": "warnings",
}


def _page_index(chapter) -> Dict[str, Optional[int]]:
    """`canonical object id -> page`, built once by reading straight
    off each already-produced canonical object's own `page` field
    (falling back to `provenance.source_page` when `page` itself is
    absent) across every typed list `_TOP_LEVEL_FIELD_BY_OBJECT_TYPE`
    names on `chapter`. Pure data access over already-computed Phase 1
    output -- this performs no layout inference of its own; an id this
    index cannot resolve at all (e.g. a topic names a content id that
    is not actually present in any typed list) simply yields no
    ordering signal for that entry (see `_interleave`), never a
    builder error -- resolving that reference is R2's job (roadmap
    M5), not this adapter's."""
    index: Dict[str, Optional[int]] = {}
    for field_name in _TOP_LEVEL_FIELD_BY_OBJECT_TYPE.values():
        for obj in getattr(chapter, field_name, ()):
            page = getattr(obj, "page", None)
            if page is None:
                provenance = getattr(obj, "provenance", None)
                page = getattr(provenance, "source_page", None) if provenance is not None else None
            index[obj.id] = page
    return index


def build_tree_from_chapter_json(chapter_id: ChapterId, chapter) -> BuiltTree:
    """Adapter: build a `BuiltTree` from an already-completed
    `schemas.chapter_schema.ChapterJSON` (the attached Phase 1 model,
    consumed strictly read-only -- see module docstring). `chapter` is
    left untyped in this signature so this module never imports
    `schemas.chapter_schema` (and, transitively, `pydantic`) unless a
    caller actually reaches this function -- `build_tree` itself, and
    every other symbol in this module, has zero dependency on either.

    Maps `chapter.topics` (`List[TopicNode]`) onto `HeadingSource`
    records 1:1 (`TopicNode.id` -> `id`, `.parent` -> `parent_id`,
    `.numbering` -> `number`, `.title` -> `title`, `.reading_order` ->
    `reading_order`, `.page_start` -> `page`, and a topic's own bbox
    top edge -- `.bbox.y0`, when present -- as the generic `position`
    tiebreak), and each of `TopicNode`'s per-type owned-content id
    lists (`.definitions`, `.figures`, ...) onto `ContentRef`s via
    `_CONTENT_FIELD_TO_OBJECT_TYPE`, each looked up in `_page_index`
    for its own `(page, position)` placement.

    `ChapterJSON` has no notion of content owned directly by the
    chapter root independent of any topic (unlike this module's own,
    more general `content_by_heading[ROOT_CONTENT_KEY]` slot) -- so
    the root of a `ChapterJSON`-built tree always has only
    heading-type `sequence` entries (one per top-level topic) and never
    any content-type ones.
    """
    topics = list(getattr(chapter, "topics", ()))

    headings = [
        HeadingSource(
            id=t.id,
            parent_id=t.parent,
            number=t.numbering if t.numbering else None,
            title=t.title if t.title else None,
            reading_order=t.reading_order,
            page=t.page_start,
            position=(t.bbox.y0 if t.bbox is not None else 0.0),
        )
        for t in topics
    ]

    page_index = _page_index(chapter)
    content_by_heading: Dict[Optional[str], List[ContentRef]] = defaultdict(list)
    for t in topics:
        for field_name, object_type in _CONTENT_FIELD_TO_OBJECT_TYPE:
            for object_id in getattr(t, field_name, ()):
                content_by_heading[t.id].append(
                    ContentRef(
                        object_id=object_id,
                        object_type=object_type,
                        page=page_index.get(object_id),
                    )
                )

    return build_tree(chapter_id, headings, content_by_heading)