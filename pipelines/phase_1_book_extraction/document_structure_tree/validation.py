"""
document_structure_tree/validation.py — Milestone 3: the Validation
Engine (architecture §15, schema §2.5/§6; roadmap M4-M7).

SCOPE: this module implements the complete validation framework that
checks an already-built, in-memory flat node collection (`tree`,
schema §9.4 -- a `Sequence[HeadingNode]`) against every invariant in
the frozen architecture's §15, plus the two schema-added checks folded
into `B1` (depth consistency, discriminator consistency -- schema §6),
and assembles the result into `ValidationMetadata` (schema §2.5).

"Operates on an already-built DocumentStructureTree" (this milestone's
own instructions) is read here as: the `tree` layer plus the
`ArtifactMetadata`/`BuildProvenance` that describe it -- NOT a fully
assembled `document_structure_tree.DocumentStructureTree` instance.
That type's own constructor *requires* a `validation_metadata` value
already (schema §2.2) -- which is exactly what this module produces --
so requiring one as this module's *input* would be circular. This
mirrors the roadmap's own dependency graph exactly: M7
(`ValidationMetadata` assembly) feeds M9 (JSON serialization / final
artifact assembly), it does not consume M9's output. `revalidate()`
below is the one place a full `DocumentStructureTree` is accepted, and
only to *re*-run this same suite against an already-assembled
artifact's own `tree`/`artifact_metadata`/`build_provenance` -- never
against its (possibly stale) stored `validation_metadata`.

WHAT IS IN SCOPE (per this milestone's own "Scope" list):
    - structural validation       -- S1-S4 (+ the depth-consistency
                                      half of B1)
    - referential integrity       -- R1-R4
    - ordering validation         -- O1-O2
    - identity validation         -- I1-I3
    - build validation            -- B1-B3
    - `ValidationResult` / `Violation` generation (one function per
      invariant, each returning a `ValidationResult`)
    - `ValidationMetadata` generation (`run_all_invariants`)

WHAT IS DELIBERATELY NOT IN SCOPE (this milestone's own "Out of
Scope" list, and each already-frozen model's own docstring):
    - DST Builder changes -- every check function below only *reads*
      an already-built `Sequence[HeadingNode]`; none of them
      construct, repair, or mutate a node. `builder.py` is untouched.
    - `ArtifactMetadata` *generation* -- `compute_chapter_fingerprint`
      below exists solely so `B3` has something authoritative to
      compare `artifact_metadata.chapter_fingerprint` against; it is a
      validation primitive, not artifact assembly (roadmap M8, which
      remains unimplemented). A future M8 should call this same
      function rather than re-deriving the formula, so the two
      milestones never quietly disagree about what a fingerprint
      means.
    - JSON serialization / JSON artifact generation / persistence /
      compiler pipeline integration -- nothing here touches
      `serialization.py`, disk, or a pipeline entry point.
    - `derived_summary` / statistics -- never read, never referenced
      by any check below (schema §9.5, §2.10 -- by design, nothing may
      depend on it).

PACKAGE BOUNDARY: this module imports nothing outside
`document_structure_tree`. The one genuine external dependency any
DST validator has -- the canonical registries, for R2/R3/R4/B2
(architecture §6: "does not consume ... the Knowledge Graph"; schema
§6: every invariant is checkable purely from this JSON shape "except
R2/R3 ... and B2") -- is modeled as the `CanonicalRegistrySnapshot`
Protocol below, a narrow interface this package defines and calls
against, never a dependency on the registries' own implementation
(architecture §6; roadmap M5: "do not let canonical-registry data
modeling leak into the DST's own types"). No other package needs to
change for this milestone.

A NOTE ON "NOT VALIDATED" (R2/R3/R4/B2 without a registry). Roadmap
M5's own acceptance criteria describe these as reporting "'not
validated' rather than crashing" when no registry is available. The
*frozen schema* (§2.5) gives `ValidationResult.status` a closed
`pass | fail` domain -- there is no third state to report, and
`ValidationMetadata`'s own closure property (already enforced by
`document_structure_tree.ValidationMetadata.__post_init__`) forbids
omitting an invariant's result entirely. Reconciling the two: this
module treats "could not be verified" as `fail` with an explicit,
actionable `Violation` message saying so -- never as `pass`, since a
validator claiming an unverified referential fact "passed" would be
false reassurance, and never as a missing/omitted result, since the
frozen schema doesn't allow that. This is the same kind of
frozen-spec-over-roadmap-wording resolution `enums.py` and
`primitives.py` already document for `ObjectType`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import (
    AbstractSet,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

from .document_structure_tree import (
    ArtifactMetadata,
    BuildProvenance,
    DocumentStructureTree,
    ValidationMetadata,
    ValidationResult,
    Violation,
)
from .enums import EntryType, InvariantId, ValidationStatus
from .heading_node import HeadingNode
from .identity import compute_node_id
from .primitives import CanonicalObjectId, ChapterId, Fingerprint, NodeId, ObjectType

__all__ = [
    "TreeIndex",
    "build_index",
    "CanonicalRegistrySnapshot",
    "InMemoryCanonicalRegistrySnapshot",
    "compute_chapter_fingerprint",
    "check_s1",
    "check_s2",
    "check_s3",
    "check_s4",
    "check_r1",
    "check_r2",
    "check_r3",
    "check_r4",
    "check_o1",
    "check_o2",
    "check_i1",
    "check_i2",
    "check_i3",
    "check_b1",
    "check_b2",
    "check_b3",
    "run_all_invariants",
    "revalidate",
]


# ==========================================================================
# TreeIndex — the "consumer/implementation responsibility" index (schema
# §5.2/§6): "any validator implementation must build its own node_id ->
# node and parent_id -> children indices before checking S1-S4/O1-O2".
# ==========================================================================

@dataclass(frozen=True)
class TreeIndex:
    """The two lookup indices schema §6 requires a validator to build
    once, up front, because `tree` is an unordered array (schema
    §5.2): `node_id -> node`, and `parent_id -> children` (the latter
    derived from `HeadingNode.parent_id` -- i.e. *actual*, structural
    parentage -- deliberately distinct from a node's own `.children`
    property, which is the *declared* children a node's own `sequence`
    lists (schema §2.7). O2's whole job is comparing those two, so
    this index must not conflate them.

    `duplicate_node_ids` records any `node_id` that appears on more
    than one node in the input `tree` -- a fact `nodes_by_id` alone
    would silently hide (a dict comprehension keyed by `node_id` keeps
    only the last write). Recorded here, once, so `check_i3` doesn't
    have to re-scan the raw tree itself.
    """

    nodes_by_id: Dict[NodeId, HeadingNode]
    children_by_parent_id: Dict[NodeId, Tuple[NodeId, ...]]
    duplicate_node_ids: Tuple[NodeId, ...]


def build_index(tree: Sequence[HeadingNode]) -> TreeIndex:
    """Build a `TreeIndex` from a flat node collection. Never raises
    on a malformed tree (a dangling `parent_id`, a duplicate
    `node_id`, ...) -- building the index is purely mechanical
    bookkeeping; every invariant check below is responsible for
    *reporting* such defects as `Violation`s, not this function for
    refusing to index them (roadmap M4 risk note: "each validator
    should be defensive enough to report a clean failure rather than
    throw when run against a malformed fixture")."""
    nodes_by_id: Dict[NodeId, HeadingNode] = {}
    duplicates: List[NodeId] = []
    for node in tree:
        if node.node_id in nodes_by_id:
            duplicates.append(node.node_id)
        nodes_by_id[node.node_id] = node

    children_by_parent_id: Dict[NodeId, List[NodeId]] = defaultdict(list)
    for node in tree:
        if node.parent_id is not None:
            children_by_parent_id[node.parent_id].append(node.node_id)

    return TreeIndex(
        nodes_by_id=nodes_by_id,
        children_by_parent_id={k: tuple(v) for k, v in children_by_parent_id.items()},
        duplicate_node_ids=tuple(duplicates),
    )


# ==========================================================================
# CanonicalRegistrySnapshot — the external seam R2/R3/R4/B2 call against
# (architecture §6, §12; schema §6; roadmap M5).
# ==========================================================================

@runtime_checkable
class CanonicalRegistrySnapshot(Protocol):
    """The minimal lookup interface DST validation needs against the
    canonical registries at `build_provenance.canonical_registry_snapshot_ref`
    (architecture §15 R2/R3/R4, B2). Deliberately narrow -- "given a
    `CanonicalObjectId` and a snapshot ref, return existence +
    authoritative `object_type`, or 'not found'" (roadmap M5) -- and
    deliberately a `Protocol`, not a base class, so this package never
    depends on the real canonical registries' own implementation
    (architecture §6; consistent with every other type in this package
    that models an external concern only as far as the frozen
    architecture requires, e.g. `ObjectType` in `primitives.py`).

    A concrete registry client resolving
    `canonical_registry_snapshot_ref` to *this* interface is what "B2:
    the ref resolves" means operationally here: a caller who could not
    resolve the ref passes `registry=None` to the check functions
    below, rather than this module attempting resolution itself (which
    would require a dependency this package must not take)."""

    def object_exists(self, object_id: CanonicalObjectId) -> bool:
        """True iff `object_id` exists in the canonical registries at
        this snapshot (R2's precondition)."""
        ...

    def object_type_of(self, object_id: CanonicalObjectId) -> Optional[ObjectType]:
        """The object's authoritative `object_type` at this snapshot,
        or `None` if the object does not exist here (R3's
        precondition; R2, not R3, is responsible for reporting
        nonexistence, so `check_r3` treats `None` as "not this
        check's concern", not as a type mismatch)."""
        ...

    def objects_owned_by_chapter(self, chapter_id: ChapterId) -> AbstractSet[CanonicalObjectId]:
        """Every canonical object the registries consider to belong
        to `chapter_id` (R4's "every canonical educational object
        belonging to the chapter" universe -- architecture §15 R4,
        §17 Ownership guarantees)."""
        ...


@dataclass(frozen=True)
class InMemoryCanonicalRegistrySnapshot:
    """A minimal, in-memory `CanonicalRegistrySnapshot` -- roadmap
    M5's "fixture-backed fake implementation for testing". A
    reference implementation only: the real canonical registries are
    owned and implemented elsewhere (architecture §6) and are
    explicitly out of this milestone's scope; this class exists so
    R2/R3/R4/B2 can be exercised against real data (in tests, or by
    any caller who already holds the relevant snapshot data in
    memory) without this package depending on the registries'
    implementation."""

    object_types: Mapping[CanonicalObjectId, ObjectType] = field(default_factory=dict)
    chapter_objects: Mapping[ChapterId, AbstractSet[CanonicalObjectId]] = field(default_factory=dict)

    def object_exists(self, object_id: CanonicalObjectId) -> bool:
        return object_id in self.object_types

    def object_type_of(self, object_id: CanonicalObjectId) -> Optional[ObjectType]:
        return self.object_types.get(object_id)

    def objects_owned_by_chapter(self, chapter_id: ChapterId) -> AbstractSet[CanonicalObjectId]:
        return frozenset(self.chapter_objects.get(chapter_id, ()))


# ==========================================================================
# Small shared helper
# ==========================================================================

def _outcome(invariant_id: InvariantId, violations: Sequence[Violation]) -> ValidationResult:
    """Build the `ValidationResult` for one invariant from whatever
    `Violation`s its check function collected -- the single canonical
    representation schema §2.5/§5.3 fixes: `violations` present and
    non-empty iff `status = fail`, omitted iff `status = pass`.
    `ValidationResult.__post_init__` already enforces this closure
    property; this helper just avoids repeating the pass/fail branch
    in every `check_*` function below."""
    if violations:
        return ValidationResult(
            invariant_id=invariant_id, status=ValidationStatus.FAIL, violations=tuple(violations)
        )
    return ValidationResult(invariant_id=invariant_id, status=ValidationStatus.PASS)


# ==========================================================================
# Structural — S1-S4 (architecture §15)
# ==========================================================================

def _has_cycle(node: HeadingNode, index: TreeIndex) -> bool:
    """Walk `node`'s `parent_id` chain toward the root; true iff a
    node is revisited before the chain terminates. Terminates cleanly
    (returns `False`) on a dangling `parent_id` too -- that defect is
    `check_s1`'s *other* half to report, not this helper's."""
    seen = set()
    current: Optional[HeadingNode] = node
    while current is not None:
        if current.node_id in seen:
            return True
        seen.add(current.node_id)
        if current.parent_id is None:
            return False
        current = index.nodes_by_id.get(current.parent_id)
    return False


def check_s1(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """S1 — Tree well-formedness: the structure is acyclic, and every
    non-root node's `parent_id` resolves to an existing node (the
    data model -- a single `parent_id` field -- makes "more than one
    parent" structurally unrepresentable, so the "exactly one parent"
    half of S1 holds by construction and needs no runtime check;
    see `heading_node.py`'s own docstring)."""
    violations: List[Violation] = []
    for node in tree:
        if node.level.is_root():
            continue
        if node.parent_id not in index.nodes_by_id:
            violations.append(
                Violation(
                    node_id=node.node_id,
                    message=(
                        f"S1: parent_id {node.parent_id.value!r} does not resolve to any "
                        "node in this tree (dangling parent reference)."
                    ),
                )
            )
    for node in tree:
        if _has_cycle(node, index):
            violations.append(
                Violation(
                    node_id=node.node_id,
                    message="S1: this node's parent_id chain contains a cycle and never reaches the chapter root.",
                )
            )
    return _outcome(InvariantId.S1, violations)


def check_s2(tree: Sequence[HeadingNode]) -> ValidationResult:
    """S2 — Single root: exactly one `level = 0` node exists per
    chapter. Scans the raw `tree`, not a `node_id`-deduplicated index
    -- two distinct root-level nodes are a violation regardless of
    whether they happen to carry the same or different `node_id`s."""
    roots = [n for n in tree if n.level.is_root()]
    violations: List[Violation] = []
    if not roots:
        violations.append(Violation(message="S2: no level=0 (chapter root) node exists; exactly one is required."))
    elif len(roots) > 1:
        for r in roots:
            violations.append(
                Violation(
                    node_id=r.node_id,
                    message=f"S2: {len(roots)} level=0 nodes exist in this chapter; exactly one chapter root is required.",
                )
            )
    return _outcome(InvariantId.S2, violations)


def check_s3(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """S3 — Span monotonicity: for every node, `span.block_range`
    fully contains the `block_range` of every descendant. Checked as
    direct parent/child pairs only (via `index.children_by_parent_id`,
    i.e. *actual* structural children from `parent_id` -- S3 is a
    tree-shape invariant, independent of what any node's own
    `sequence` declares): containment is transitive, so if every
    direct child's `block_range` is contained in its own parent's, the
    same holds for every deeper descendant by induction -- no need to
    materialize full descendant sets. A node with an empty `span`
    (§13) vacuously satisfies this for any child that is *also* empty;
    a non-empty child under an empty-spanned parent is a genuine
    violation (§13: an empty span is valid only "when the node owns no
    content and has no descendants" -- a non-empty child means it does
    have a descendant)."""
    violations: List[Violation] = []
    for node in tree:
        parent_range = node.span.block_range
        for child_id in index.children_by_parent_id.get(node.node_id, ()):
            child = index.nodes_by_id.get(child_id)
            if child is None:
                continue  # dangling; S1 already reports it
            child_range = child.span.block_range
            if child_range is None:
                continue  # empty child span vacuously satisfies S3 (§13)
            if parent_range is None:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"S3: this node's span is empty, but its child {child_id.value!r} "
                            f"has a non-empty block_range ({child_range.start.value}, "
                            f"{child_range.end.value}); a parent's span must contain every "
                            "descendant's span."
                        ),
                    )
                )
            elif not parent_range.contains(child_range):
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"S3: span.block_range [{parent_range.start.value}, "
                            f"{parent_range.end.value}) does not contain child "
                            f"{child_id.value!r}'s block_range [{child_range.start.value}, "
                            f"{child_range.end.value})."
                        ),
                    )
                )
    return _outcome(InvariantId.S3, violations)


def check_s4(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """S4 — Reachability: every non-root node is reachable from the
    chapter root via `parent_id` links. Computed as a forward
    traversal (root -> children -> grandchildren -> ...) using
    `index.children_by_parent_id`, starting from every `level = 0`
    node found (ordinarily exactly one; if S2 is already violated,
    this still runs defensively from whichever root-level nodes exist
    rather than crashing on the ambiguity)."""
    roots = [n for n in tree if n.level.is_root()]
    reachable: set = set()
    stack: List[NodeId] = [r.node_id for r in roots]
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        stack.extend(index.children_by_parent_id.get(node_id, ()))

    violations: List[Violation] = []
    for node in tree:
        if node.node_id not in reachable:
            violations.append(
                Violation(
                    node_id=node.node_id,
                    message="S4: this node is not reachable from the chapter root via parent_id links.",
                )
            )
    return _outcome(InvariantId.S4, violations)


# ==========================================================================
# Referential — R1-R4 (architecture §15)
# ==========================================================================

def check_r1(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """R1 — Referential integrity (headings): every `heading`-type
    `sequence` entry's `ref` resolves to an existing node whose own
    `parent_id` equals the containing node's `node_id`."""
    violations: List[Violation] = []
    for node in tree:
        for entry in node.sequence:
            if entry.entry_type is not EntryType.HEADING:
                continue
            target = index.nodes_by_id.get(entry.ref)  # type: ignore[arg-type]
            if target is None:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"R1: heading-type sequence entry references node_id "
                            f"{entry.ref.value!r}, which does not exist in this tree."
                        ),
                    )
                )
            elif target.parent_id != node.node_id:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"R1: heading-type sequence entry references "
                            f"{entry.ref.value!r}, but that node's own parent_id "
                            f"({target.parent_id.value if target.parent_id else None!r}) "
                            "does not equal this containing node's node_id."
                        ),
                    )
                )
    return _outcome(InvariantId.R1, violations)


def check_r2(
    tree: Sequence[HeadingNode],
    index: TreeIndex,
    registry: Optional[CanonicalRegistrySnapshot],
) -> ValidationResult:
    """R2 — Referential integrity (content): every `content`-type
    `sequence` entry's `ref` resolves to an existing object in the
    canonical registries at the recorded snapshot. Requires external
    registry state (schema §6); see module docstring's "not
    validated" note for what happens when `registry` is `None`."""
    del index  # unused; kept for a uniform check_* signature
    violations: List[Violation] = []
    if registry is None:
        violations.append(
            Violation(
                message=(
                    "R2: no canonical registry snapshot was supplied; referential "
                    "integrity of content-type sequence entries could not be verified "
                    "(architecture §6 — the DST is not self-contained with respect to "
                    "canonical object identity)."
                )
            )
        )
        return _outcome(InvariantId.R2, violations)

    for node in tree:
        for entry in node.sequence:
            if entry.entry_type is not EntryType.CONTENT:
                continue
            if not registry.object_exists(entry.ref):  # type: ignore[arg-type]
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"R2: content-type sequence entry references canonical object "
                            f"{entry.ref.value!r}, which does not exist in the canonical "
                            "registries at the recorded snapshot."
                        ),
                    )
                )
    return _outcome(InvariantId.R2, violations)


def check_r3(
    tree: Sequence[HeadingNode],
    index: TreeIndex,
    registry: Optional[CanonicalRegistrySnapshot],
) -> ValidationResult:
    """R3 — Reference type consistency: for every `content`-type
    entry, the stored `object_type` matches the referenced object's
    authoritative type in the canonical registries at the recorded
    snapshot. An object that doesn't exist at all is R2's concern, not
    R3's -- this check is silent (not a violation) on a `None`
    authoritative type, to avoid double-reporting the same underlying
    defect under two invariant ids."""
    del index
    violations: List[Violation] = []
    if registry is None:
        violations.append(
            Violation(
                message=(
                    "R3: no canonical registry snapshot was supplied; object_type "
                    "consistency of content-type sequence entries could not be verified."
                )
            )
        )
        return _outcome(InvariantId.R3, violations)

    for node in tree:
        for entry in node.sequence:
            if entry.entry_type is not EntryType.CONTENT:
                continue
            authoritative = registry.object_type_of(entry.ref)  # type: ignore[arg-type]
            if authoritative is None:
                continue  # nonexistence is R2's concern
            if entry.object_type != authoritative:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"R3: content-type entry for {entry.ref.value!r} carries "
                            f"object_type {entry.object_type.value!r}, which does not "
                            f"match the registry's authoritative type {authoritative.value!r}."
                        ),
                    )
                )
    return _outcome(InvariantId.R3, violations)


def check_r4(
    tree: Sequence[HeadingNode],
    index: TreeIndex,
    chapter_id: ChapterId,
    registry: Optional[CanonicalRegistrySnapshot],
) -> ValidationResult:
    """R4 — Completeness: every canonical educational object belonging
    to the chapter is referenced by exactly one `sequence` entry across
    the entire tree -- no unowned objects, no duplicate ownership.
    Checked tree-wide (schema/roadmap M5: "not node-by-node"): builds a
    single reference count across every node's `sequence` before
    comparing against the registry's `objects_owned_by_chapter`."""
    del index
    violations: List[Violation] = []
    if registry is None:
        violations.append(
            Violation(
                message=(
                    "R4: no canonical registry snapshot was supplied; tree-wide "
                    "completeness of content ownership could not be verified."
                )
            )
        )
        return _outcome(InvariantId.R4, violations)

    owned_by_chapter = registry.objects_owned_by_chapter(chapter_id)
    ref_counts: Dict[CanonicalObjectId, int] = {}
    owner_nodes: Dict[CanonicalObjectId, List[NodeId]] = defaultdict(list)
    for node in tree:
        for entry in node.sequence:
            if entry.entry_type is not EntryType.CONTENT:
                continue
            ref_counts[entry.ref] = ref_counts.get(entry.ref, 0) + 1  # type: ignore[index]
            owner_nodes[entry.ref].append(node.node_id)  # type: ignore[index]

    for object_id in owned_by_chapter:
        if ref_counts.get(object_id, 0) == 0:
            violations.append(
                Violation(
                    message=(
                        f"R4: canonical object {object_id.value!r} belongs to chapter "
                        f"{chapter_id.value!r} but is not referenced by any sequence entry."
                    )
                )
            )

    for object_id, count in ref_counts.items():
        if count > 1:
            owners = ", ".join(n.value for n in owner_nodes[object_id])
            violations.append(
                Violation(
                    message=(
                        f"R4: canonical object {object_id.value!r} is referenced by "
                        f"{count} sequence entries across nodes [{owners}]; it must be "
                        "referenced by exactly one."
                    )
                )
            )
    return _outcome(InvariantId.R4, violations)


# ==========================================================================
# Ordering — O1-O2 (architecture §15)
# ==========================================================================

def check_o1(tree: Sequence[HeadingNode]) -> ValidationResult:
    """O1 — Sequence integrity: within a single node's `sequence`,
    there are no gaps or duplicate entries.

    "No gaps" is structurally guaranteed by construction, not a
    runtime property to re-check: `sequence` is a plain, positionally-
    ordered list with no independent `order_index` field a value could
    ever be missing *for* (architecture §18.3: the unified `sequence`
    design "makes correct ordering true by construction"; §11:
    "position in the list *is* its order — there is no separate
    order-index field"). There is therefore no representable "gap" in
    this schema for a validator to detect; checking for one would be
    checking a property the schema doesn't allow to vary.

    "True document order, verified against source position data at
    build time" describes how the order was *established*, at
    construction time, against source data the persisted artifact does
    not retain (`SequenceEntry` carries no positional field at all —
    schema §2.7's closed-type contract). Schema §6 states every §15
    invariant except R2/R3/B2 is checkable purely from this JSON shape
    without external state; since no positional oracle survives into
    the persisted artifact for a validator to re-check order against,
    the one part of O1 checkable here, purely from the tree's own
    data, is duplication: no `(entry_type, ref)` pair may appear twice
    within one node's own `sequence`."""
    violations: List[Violation] = []
    for node in tree:
        seen = set()
        for entry in node.sequence:
            key = (entry.entry_type, entry.ref)
            if key in seen:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"O1: duplicate sequence entry (entry_type={entry.entry_type.value!r}, "
                            f"ref={entry.ref.value!r}) within this node's own sequence."
                        ),
                    )
                )
            seen.add(key)
    return _outcome(InvariantId.O1, violations)


def check_o2(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """O2 — Parent/child sequence consistency, checked in both
    directions independently (roadmap M5):

    1. For every `heading`-type entry in a node's `sequence`, the
       referenced child's `parent_id` equals the containing node's
       `node_id` (a *declared* child must also be an *actual* one).
    2. No child node exists whose actual parent (via `parent_id`)
       doesn't list it (an *actual* child must also be a *declared*
       one -- the reverse direction).

    Uses `HeadingNode.children` (schema §2.7's derived view over
    `sequence`) for "declared" and `index.children_by_parent_id`
    (built from `parent_id`) for "actual" -- exactly the two different
    sources of truth this invariant compares."""
    violations: List[Violation] = []
    for node in tree:
        declared = set(node.children)
        actual = set(index.children_by_parent_id.get(node.node_id, ()))

        for child_id in declared:
            child = index.nodes_by_id.get(child_id)
            if child is None:
                continue  # R1 already reports the dangling reference
            if child.parent_id != node.node_id:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"O2: sequence declares {child_id.value!r} as a child, but "
                            "that node's own parent_id does not equal this node."
                        ),
                    )
                )
        for child_id in actual:
            if child_id not in declared:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"O2: node {child_id.value!r} has parent_id equal to this "
                            "node, but is not listed as a heading-type entry in this "
                            "node's own sequence."
                        ),
                    )
                )
    return _outcome(InvariantId.O2, violations)


# ==========================================================================
# Identity — I1-I3 (architecture §14, §15)
# ==========================================================================

def _recompute_node_id_or_none(node: HeadingNode, index: TreeIndex) -> Optional[NodeId]:
    """Recompute what `node.node_id` *should* be, using only its own
    stored structural-identity fields (`chapter_id`, `level`,
    `parent_id`, `number`) -- exactly `identity.compute_node_id`'s own
    parameters (architecture §14, schema §4). For an unnumbered node,
    the required disambiguator (ordinal position among unnumbered
    siblings) is derived from the parent's own *declared* child order
    (`HeadingNode.children`, schema §11) -- the only place sibling
    order is recorded in this schema.

    Returns `None` when recomputation isn't possible from the tree's
    own data alone (parent missing, or this node absent from its
    parent's declared children) -- callers treat that as "not
    independently checkable here", since the underlying defect is
    already reported by S1/O2, not as an I1/I2 finding of its own
    (avoids double-reporting one defect under two invariant ids)."""
    if node.level.is_root():
        return compute_node_id(node.chapter_id, node.level, None)

    if node.number is not None:
        return compute_node_id(node.chapter_id, node.level, node.parent_id, number=node.number)

    parent = index.nodes_by_id.get(node.parent_id)  # type: ignore[arg-type]
    if parent is None:
        return None
    unnumbered_sibling_ids = [
        cid
        for cid in parent.children
        if (sibling := index.nodes_by_id.get(cid)) is not None and sibling.number is None
    ]
    if node.node_id not in unnumbered_sibling_ids:
        return None
    ordinal = unnumbered_sibling_ids.index(node.node_id)
    return compute_node_id(node.chapter_id, node.level, node.parent_id, unnumbered_ordinal=ordinal)


def check_i1(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """I1 — Determinism: given identical structural inputs and the
    same `identity_scheme_version`, `node_id` derivation is
    deterministic and reproducible. Checked two ways per node: (a)
    recomputing `node_id` twice from the same stored identity fields
    yields the same value both times (call-level reproducibility --
    guards against, e.g., accidental reliance on hash/dict iteration
    order somewhere in the derivation path), and (b) that recomputed
    value equals the `node_id` actually stored on the node (build-
    level reproducibility -- the artifact's own `node_id` is exactly
    what re-running the same, documented derivation would produce)."""
    violations: List[Violation] = []
    for node in tree:
        first = _recompute_node_id_or_none(node, index)
        if first is None:
            continue  # not independently checkable here; S1/O2 report the underlying defect
        second = _recompute_node_id_or_none(node, index)
        if first != second:
            violations.append(
                Violation(
                    node_id=node.node_id,
                    message="I1: node_id derivation was not reproducible across two identical calls.",
                )
            )
            continue
        if first != node.node_id:
            violations.append(
                Violation(
                    node_id=node.node_id,
                    message=(
                        "I1: stored node_id does not match deterministic recomputation "
                        "from this node's own structural-identity fields (chapter_id, "
                        f"level, parent identity, number) — recomputed {first.value!r}."
                    ),
                )
            )
    return _outcome(InvariantId.I1, violations)


def check_i2(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """I2 — Tier 1 stability: for numbered headings, `node_id` is
    unchanged across rebuilds when `chapter_id`, `level`, parent
    identity, and `number` are unchanged. A single already-built
    artifact cannot literally re-run "a rebuild" to compare against,
    so this checks the structural precondition that guarantees the
    stability promise: does the stored `node_id` already equal what
    the Tier-1 rule (`number` as disambiguator, nothing else) would
    derive? If so, any future rebuild holding those same fields fixed
    is guaranteed, by `compute_node_id`'s own construction (it never
    reads `title`/`span`/`sequence` at all), to reproduce this exact
    value. Root headings are excluded (§14: the root has no siblings
    and takes no disambiguator, so "numbered heading" tiering does not
    apply to it); unnumbered headings are Tier 2, out of scope for I2
    (see `check_i1`, which covers both tiers together)."""
    del index
    violations: List[Violation] = []
    for node in tree:
        if node.level.is_root() or node.number is None:
            continue
        recomputed = compute_node_id(node.chapter_id, node.level, node.parent_id, number=node.number)
        if recomputed != node.node_id:
            violations.append(
                Violation(
                    node_id=node.node_id,
                    message=(
                        "I2: this numbered heading's stored node_id does not match the "
                        "Tier-1 derivation from chapter_id/level/parent/number — "
                        f"recomputed {recomputed.value!r}. A future rebuild with these "
                        "fields unchanged would not reproduce this node_id."
                    ),
                )
            )
    return _outcome(InvariantId.I2, violations)


def check_i3(
    tree: Sequence[HeadingNode],
    index: TreeIndex,
    other_chapter_node_ids: Optional[AbstractSet[NodeId]] = None,
) -> ValidationResult:
    """I3 — Scope isolation: no `node_id` collision occurs across
    different `chapter_id` values.

    Unlike R2-R4/B2, the in-chapter half of this check needs no
    external state at all: `index.duplicate_node_ids` (built once by
    `build_index`, since a `node_id -> node` dict alone would silently
    hide a collision by keeping only the last write) already tells us
    whether two nodes in *this* tree share a `node_id` -- always fully
    checkable, so this check is never reported as unverifiable the way
    R2-R4/B2 are.

    True *cross*-chapter comparison requires `node_id`s already
    produced for other chapters, which a single-tree validator run
    does not have on its own -- `other_chapter_node_ids` is an
    optional, caller-supplied strengthening of this check (mirroring
    the registry seam's own optionality), not a requirement: its
    absence does not turn this check into a failure, since the
    in-chapter half remains a complete, honest, positive check on its
    own (contrast R2-R4/B2, where nothing is checkable at all without
    external state)."""
    violations: List[Violation] = []
    for dup_id in index.duplicate_node_ids:
        violations.append(
            Violation(
                node_id=dup_id,
                message=f"I3: node_id {dup_id.value!r} is not unique within this chapter's own tree.",
            )
        )
    if other_chapter_node_ids:
        for node in tree:
            if node.node_id in other_chapter_node_ids:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message=(
                            f"I3: node_id {node.node_id.value!r} collides with a node_id "
                            "already used in a different chapter."
                        ),
                    )
                )
    return _outcome(InvariantId.I3, violations)


# ==========================================================================
# Build Integrity — B1-B3 (architecture §15; schema §6's two B1-adjacent
# schema-level checks folded into B1, per that section's own grouping)
# ==========================================================================

def check_b1(tree: Sequence[HeadingNode], index: TreeIndex) -> ValidationResult:
    """B1 — Schema conformance. Every `HeadingNode`/`SequenceEntry`
    already enforces its own *local* shape at construction time (a
    malformed one cannot exist in `tree` at all -- see those modules'
    own `__post_init__`s), so this re-checks, defensively, the two
    conformance rules schema §6 names as needing whole-tree context
    and therefore not checkable by any single object about itself:

    1. Depth consistency (schema §2.6): for every non-root node,
       `level == parent.level + 1`. None of S1/S2/S4 individually
       catches a `level` inconsistent with true depth in the
       `parent_id` chain (schema §6) -- a node could satisfy all three
       while still carrying a wrong `level`.
    2. Discriminator consistency (schema §6, restated from §11): a
       `heading`-type entry with a present `object_type`, or a
       `content`-type entry with an absent one. Already prevented at
       `SequenceEntry` construction time; re-checked here only as
       defense-in-depth, exactly as schema §6 itself describes it as
       "a direct, mechanical consequence of §11's closed-type
       contract" a conforming validator should still assert."""
    violations: List[Violation] = []
    for node in tree:
        if node.level.is_root():
            continue
        parent = index.nodes_by_id.get(node.parent_id)  # type: ignore[arg-type]
        if parent is None:
            continue  # S1 already reports the dangling parent
        expected_level = parent.level.value + 1
        if node.level.value != expected_level:
            violations.append(
                Violation(
                    node_id=node.node_id,
                    message=(
                        "B1 (schema §2.6 depth consistency): level="
                        f"{node.level.value} but parent's level + 1 = {expected_level}."
                    ),
                )
            )

    for node in tree:
        for entry in node.sequence:
            if entry.entry_type is EntryType.HEADING and entry.object_type is not None:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message="B1 (schema §6 discriminator check): heading-type sequence entry unexpectedly carries object_type.",
                    )
                )
            elif entry.entry_type is EntryType.CONTENT and entry.object_type is None:
                violations.append(
                    Violation(
                        node_id=node.node_id,
                        message="B1 (schema §6 discriminator check): content-type sequence entry is missing object_type.",
                    )
                )
    return _outcome(InvariantId.B1, violations)


def check_b2(
    build_provenance: BuildProvenance,
    registry: Optional[CanonicalRegistrySnapshot],
) -> ValidationResult:
    """B2 — Snapshot consistency: `build_provenance.
    canonical_registry_snapshot_ref` refers to a valid, resolvable
    canonical registry snapshot. Resolving that reference is an
    external-system concern this package does not implement
    (architecture §6); a caller who successfully resolved it supplies
    the resulting `CanonicalRegistrySnapshot` as `registry` (the same
    object R2-R4 call against) -- its mere presence here *is* "the ref
    resolved". `registry=None` means resolution did not happen (or
    failed), which this check reports as a failure rather than
    silently assuming success."""
    violations: List[Violation] = []
    if registry is None:
        violations.append(
            Violation(
                message=(
                    "B2: canonical_registry_snapshot_ref "
                    f"{build_provenance.canonical_registry_snapshot_ref!r} could not be "
                    "resolved — no canonical registry snapshot was supplied to the validator."
                )
            )
        )
    return _outcome(InvariantId.B2, violations)


def compute_chapter_fingerprint(tree: Sequence[HeadingNode]) -> Fingerprint:
    """The canonical `chapter_fingerprint` computation B3 checks
    `artifact_metadata.chapter_fingerprint` against: a SHA-256 digest
    (schema §2.1's "Fingerprint hash algorithm" decision) over exactly
    each node's own structural-identity fields — `chapter_id`,
    `level`, parent identity, `number` (schema §2.3: "no other field
    may influence it, or B3 is violated").

    Deliberately excludes `node_id` itself from the hashed payload,
    even though it is available on every node: `node_id` is *derived
    from* exactly these four fields (architecture §14), so including
    it as a fifth hashed fact would let a bug in `node_id` derivation
    silently double-count rather than surfacing as a clean mismatch,
    and would technically violate the "no other field" rule as
    literally written. It *is* used as the sort key below, since
    `tree`'s own array order carries no meaning (schema §5.2) and
    fingerprinting needs a canonical, order-independent traversal —
    but a value used only to choose traversal order is not a value
    that "influences" the hash's content.

    This function is a validation primitive (it exists so `check_b3`
    has something authoritative to compare against), not artifact
    generation (roadmap M8, out of scope for this milestone) — see
    module docstring."""
    parts = []
    for node in sorted(tree, key=lambda n: n.node_id.value):
        parts.append(
            "|".join(
                [
                    node.chapter_id.value,
                    str(node.level.value),
                    node.parent_id.value if node.parent_id is not None else "ROOT",
                    node.number if node.number is not None else "",
                ]
            )
        )
    payload = "\n".join(parts).encode("utf-8")
    return Fingerprint.of(payload)


def check_b3(tree: Sequence[HeadingNode], artifact_metadata: ArtifactMetadata) -> ValidationResult:
    """B3 — Fingerprint correctness: `artifact_metadata.
    chapter_fingerprint` correctly reflects a hash over all nodes'
    structural-identity fields at build time (compared here against
    `compute_chapter_fingerprint`, this module's own authoritative
    formula for that hash)."""
    violations: List[Violation] = []
    expected = compute_chapter_fingerprint(tree)
    if artifact_metadata.chapter_fingerprint != expected:
        violations.append(
            Violation(
                message=(
                    "B3: artifact_metadata.chapter_fingerprint "
                    f"({artifact_metadata.chapter_fingerprint.value}) does not match the "
                    f"recomputed fingerprint ({expected.value}) over all nodes' "
                    "structural-identity fields."
                )
            )
        )
    return _outcome(InvariantId.B3, violations)


# ==========================================================================
# ValidationMetadata assembly (roadmap M7; schema §2.5)
# ==========================================================================

def run_all_invariants(
    tree: Sequence[HeadingNode],
    artifact_metadata: ArtifactMetadata,
    build_provenance: BuildProvenance,
    *,
    registry: Optional[CanonicalRegistrySnapshot] = None,
    other_chapter_node_ids: Optional[AbstractSet[NodeId]] = None,
) -> ValidationMetadata:
    """Run every invariant in architecture §15 exactly once against
    `tree` (plus the artifact-level facts `B2`/`B3` need), and
    assemble the results into a `ValidationMetadata` (schema §2.5).

    `validation_status = pass` iff every `ValidationResult.status =
    pass` — enforced independently by `ValidationMetadata.
    __post_init__` itself (schema §2.5's closure property), not
    re-derived ad hoc here. That same constructor also enforces
    "exactly one `ValidationResult` per invariant in the closed
    `InvariantId` enumeration" — so a bug here that accidentally
    dropped or duplicated an invariant's result would raise
    `DSTValueError` immediately, rather than silently producing a
    partial report (roadmap M7's own "exhaustiveness" acceptance
    criterion).

    `registry` / `other_chapter_node_ids` are optional strengthenings
    for the invariants that need external state (R2-R4, B2, and I3's
    cross-chapter half) — see `CanonicalRegistrySnapshot` and
    `check_i3`'s own docstrings for what happens when they're absent.
    """
    index = build_index(tree)
    chapter_id = artifact_metadata.chapter_id

    results = (
        check_s1(tree, index),
        check_s2(tree),
        check_s3(tree, index),
        check_s4(tree, index),
        check_r1(tree, index),
        check_r2(tree, index, registry),
        check_r3(tree, index, registry),
        check_r4(tree, index, chapter_id, registry),
        check_o1(tree),
        check_o2(tree, index),
        check_i1(tree, index),
        check_i2(tree, index),
        check_i3(tree, index, other_chapter_node_ids),
        check_b1(tree, index),
        check_b2(build_provenance, registry),
        check_b3(tree, artifact_metadata),
    )

    all_pass = all(result.status is ValidationStatus.PASS for result in results)
    return ValidationMetadata(
        validation_status=ValidationStatus.PASS if all_pass else ValidationStatus.FAIL,
        validation_results=results,
    )


def revalidate(
    dst: DocumentStructureTree,
    *,
    registry: Optional[CanonicalRegistrySnapshot] = None,
    other_chapter_node_ids: Optional[AbstractSet[NodeId]] = None,
) -> ValidationMetadata:
    """Re-run the full §15 invariant suite against an already-
    assembled `DocumentStructureTree`'s own `tree` / `artifact_metadata`
    / `build_provenance` — deliberately ignoring its existing,
    possibly stale or untrusted, `validation_metadata` rather than
    trusting it. The one place this module accepts a full
    `DocumentStructureTree`; see module docstring for why
    `run_all_invariants` itself does not."""
    return run_all_invariants(
        dst.tree,
        dst.artifact_metadata,
        dst.build_provenance,
        registry=registry,
        other_chapter_node_ids=other_chapter_node_ids,
    )