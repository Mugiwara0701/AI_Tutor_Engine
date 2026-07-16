"""
document_structure_tree/artifact.py — Milestone 4: Artifact Generation
(architecture §9, §13, §17; schema §2.2-2.5, §2.10, §5; roadmap
M8/M9/M11).

SCOPE (this milestone's own "Scope" list):
    - artifact generation            -- `generate_artifact()`, converting
      an already-built, already-validatable `tree` (schema §9.4, a
      `Sequence[HeadingNode]` -- Milestones 2.2/roadmap M2, unchanged)
      into a fully assembled `DocumentStructureTree` (schema §2.2).
    - artifact metadata population   -- `ArtifactMetadata` assembly
      (schema §2.3, roadmap M8), including `chapter_fingerprint`
      computation (delegated to `validation.compute_chapter_fingerprint`,
      Milestone 3 -- never re-derived here, so the two milestones can
      never quietly disagree about what a fingerprint means; see that
      function's own docstring).
    - build provenance population    -- `BuildProvenance` assembly
      (schema §2.4, roadmap M8), plus the one documented-but-unnamed
      build-integrity check schema §2.4 calls out for it: a
      `heading_detection_provenance` entry naming a `node_id` absent
      from `tree` is a build-integrity defect (not a §15 invariant, so
      it is raised here as `DSTArtifactError`, never reported via
      `ValidationResult`/`InvariantId` -- see that enum's own closed-set
      docstring in enums.py for why no seventeenth invariant is added).
    - derived summary generation     -- `compute_derived_summary()`
      (schema §2.10, roadmap M11): convenience statistics regenerable
      at any time from `tree`, deliberately never consulted by
      `run_all_invariants` or any §17 Phase 2 guarantee.
    - deterministic serialization    -- `serialize()` / `to_canonical_json()`
      (schema §5), producing byte-identical output for two artifacts
      that are equal in every field the schema defines, regardless of
      `tree`'s incidental in-memory array order (schema §5.2: "Array
      order within tree carries no meaning").
    - deterministic deserialization  -- `deserialize()`, the exact
      inverse, delegating to `DocumentStructureTree.from_json`
      (Milestone 2.1, unchanged).
    - round-trip support             -- `round_trip_text()`, the
      text-level analogue of `serialization.round_trip()` (Milestone 1)
      for the fully assembled artifact.

WHAT IS DELIBERATELY NOT IN SCOPE (this milestone's own "Out of Scope"
list):
    - Builder changes -- `builder.build_tree()` (roadmap M2) is called
      by callers of this module, never by this module itself; nothing
      here constructs, repairs, or mutates a `HeadingNode`.
    - Validation engine changes -- `generate_artifact()` calls
      `validation.run_all_invariants()` exactly as Milestone 3 exposes
      it; no invariant, `TreeIndex` logic, or `CanonicalRegistrySnapshot`
      behavior is redefined or duplicated here.
    - Compiler pipeline integration -- there is no Chapter JSON adapter,
      canonical-registry client wiring, or "write artifact to disk"
      step here (roadmap M10). `generate_artifact()` takes an
      already-built `tree` and already-resolved inputs (a registry
      snapshot, a registry ref string, ...) as plain arguments; it does
      not resolve any of them itself.
    - Persistence -- `serialize()`/`deserialize()` operate on in-memory
      strings; neither touches a filesystem, database, or network call.
    - OneDrive integration, build orchestration -- not referenced
      anywhere in this package; out of scope for the whole compiler at
      this phase (architecture §7).

PACKAGE BOUNDARY: this module imports nothing outside
`document_structure_tree`, exactly like every prior milestone's module.
`generate_artifact()`'s `registry` parameter is typed against
`validation.CanonicalRegistrySnapshot` (the same narrow Protocol
R2-R4/B2 already call against) -- callers resolving
`canonical_registry_snapshot_ref` against the real canonical registries
do so entirely outside this package (architecture §6); this module
never attempts that resolution itself.

A NOTE ON "GENERATION" VS. "VALIDATION OUTCOME". `generate_artifact()`
raises `DSTArtifactError` only when an artifact *cannot be assembled at
all* (an empty `tree`, a dangling provenance `node_id` -- both
precondition failures, mirroring `builder.build_tree`'s own
`DSTBuildError` for the same kind of failure one milestone earlier).
A `tree` that assembles cleanly but *fails* one or more §15 invariants
is not an error here: `run_all_invariants` reports that as
`validation_metadata.validation_status = 'fail'`, a normal, fully
representable artifact state (architecture §9.3: "must be reported
here and should not be considered safe for Phase 2 consumption" -- a
consumer-side rule, not a generation-time exception). Generation
succeeds either way; safety-for-Phase-2 is a property of the resulting
artifact's own `validation_metadata`, which every caller must inspect.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AbstractSet, Dict, Optional, Sequence, Tuple

from .document_structure_tree import (
    ArtifactMetadata,
    BuildProvenance,
    DerivedSummary,
    DocumentStructureTree,
    HeadingDetectionEntry,
)
from .enums import EntryType
from .exceptions import DSTArtifactError, DSTSerializationError
from .heading_node import HeadingNode
from .identity import IDENTITY_SCHEME_VERSION
from .primitives import (
    ChapterId,
    CompilerVersion,
    IdentitySchemeVersion,
    NodeId,
    SchemaVersion,
    Timestamp,
)
from .validation import (
    CanonicalRegistrySnapshot,
    compute_chapter_fingerprint,
    run_all_invariants,
)

__all__ = [
    "find_dangling_provenance_node_ids",
    "compute_derived_summary",
    "generate_artifact",
    "to_canonical_json",
    "serialize",
    "deserialize",
    "round_trip_text",
]


# ==========================================================================
# Build-timestamp helper
# ==========================================================================

def _utc_now_iso() -> str:
    """Current UTC time as the ISO-8601-with-trailing-`Z` string
    `primitives.Timestamp` requires (schema §2.1's own example format,
    `2026-07-15T09:00:00Z`) -- second precision, no fractional seconds,
    matching that example exactly rather than relying on
    `require_iso8601_utc`'s more permissive optional-fraction branch."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==========================================================================
# BuildProvenance build-integrity check (schema §2.4, documented but
# not a named §15 invariant -- see module docstring)
# ==========================================================================

def find_dangling_provenance_node_ids(
    tree: Sequence[HeadingNode],
    build_provenance: BuildProvenance,
) -> Tuple[NodeId, ...]:
    """Every `node_id` named by `build_provenance.
    heading_detection_provenance` that does not exist in `tree`
    (schema §2.4: "a node_id appearing here that doesn't exist in tree
    is a build-integrity defect ... out of scope for R1-R4 ... and is
    flagged here as an implementation-level check worth adding").
    Returns an empty tuple when `heading_detection_provenance` is
    absent or every entry resolves cleanly. Sorted by `node_id.value`
    for a deterministic, reproducible error message regardless of the
    input list's own order."""
    if build_provenance.heading_detection_provenance is None:
        return ()
    known_ids = {node.node_id for node in tree}
    dangling = {
        entry.node_id
        for entry in build_provenance.heading_detection_provenance
        if entry.node_id not in known_ids
    }
    return tuple(sorted(dangling, key=lambda node_id: node_id.value))


# ==========================================================================
# DerivedSummary generation (schema §2.10, roadmap M11)
# ==========================================================================

def compute_derived_summary(tree: Sequence[HeadingNode]) -> DerivedSummary:
    """Convenience statistics regenerable at any time from `tree`
    (schema §2.10) -- node counts, maximum depth, and a handful of
    other cheap, purely-descriptive aggregates. Explicitly
    non-canonical: nothing below is read by `validation.
    run_all_invariants` or relied upon by any architecture §17 Phase 2
    guarantee (schema §9.5, §2.10), and this function's own output
    shape is free to evolve without a `schema_version` bump (schema
    §5.7: "`derived_summary` is exempt from this discipline
    entirely").

    Safe to call against an empty `tree`: every statistic below has a
    well-defined value (0, or `None`-shaped absence) for an empty
    input, since `compute_derived_summary` never dereferences a
    "first"/"root" node that might not exist -- unlike `generate_artifact`,
    which does require at least a chapter root and raises
    `DSTArtifactError` otherwise (see that function's own docstring)."""
    tree = list(tree)

    heading_entry_count = 0
    content_entry_count = 0
    numbered_heading_count = 0
    unnumbered_heading_count = 0
    leaf_node_count = 0
    nodes_with_block_range = 0
    nodes_with_page_range = 0
    nodes_with_title = 0

    for node in tree:
        for entry in node.sequence:
            if entry.entry_type is EntryType.HEADING:
                heading_entry_count += 1
            else:
                content_entry_count += 1

        if not node.level.is_root():
            if node.number is not None:
                numbered_heading_count += 1
            else:
                unnumbered_heading_count += 1

        if len(node.children) == 0:
            leaf_node_count += 1

        if node.span.block_range is not None:
            nodes_with_block_range += 1
        if node.span.page_range is not None:
            nodes_with_page_range += 1
        if node.title is not None:
            nodes_with_title += 1

    max_depth = max((node.level.value for node in tree), default=0)

    data: Dict[str, Any] = {
        "node_count": len(tree),
        "max_depth": max_depth,
        "leaf_node_count": leaf_node_count,
        "numbered_heading_count": numbered_heading_count,
        "unnumbered_heading_count": unnumbered_heading_count,
        "nodes_with_title": nodes_with_title,
        "heading_sequence_entry_count": heading_entry_count,
        "content_sequence_entry_count": content_entry_count,
        "nodes_with_block_range": nodes_with_block_range,
        "nodes_with_page_range": nodes_with_page_range,
    }
    return DerivedSummary(data=data)


# ==========================================================================
# Artifact generation (roadmap M8/M9; schema §2.2)
# ==========================================================================

def generate_artifact(
    *,
    tree: Sequence[HeadingNode],
    chapter_id: ChapterId,
    schema_version: SchemaVersion,
    compiler_version: CompilerVersion,
    canonical_registry_snapshot_ref: str,
    identity_scheme_version: IdentitySchemeVersion = IDENTITY_SCHEME_VERSION,
    build_timestamp: Optional[Timestamp] = None,
    heading_detection_provenance: Optional[Sequence[HeadingDetectionEntry]] = None,
    registry: Optional[CanonicalRegistrySnapshot] = None,
    other_chapter_node_ids: Optional[AbstractSet[NodeId]] = None,
    include_derived_summary: bool = True,
) -> DocumentStructureTree:
    """Assemble a complete `DocumentStructureTree` artifact (schema
    §2.2) from an already-built `tree` (roadmap M2/M3's output,
    unchanged by this milestone) and the artifact-level facts a caller
    already holds.

    `schema_version`, `compiler_version`, and `identity_scheme_version`
    are each independently settable, exactly as schema §2.3 requires
    ("mutually independent ... none may be inferred from another") --
    `identity_scheme_version` defaults to `identity.
    IDENTITY_SCHEME_VERSION` only because that is, as a matter of fact,
    the scheme every `node_id` already on `tree` was derived under
    (Milestone 1); a caller may still override it explicitly (e.g. to
    construct a deliberately-inconsistent fixture for a negative test).

    `chapter_fingerprint` is never computed ad hoc here -- it delegates
    to `validation.compute_chapter_fingerprint`, the one authoritative
    formula B3 itself checks against (Milestone 3), so generation and
    validation can never quietly disagree about what a fingerprint
    means (see that function's own docstring).

    `build_timestamp` defaults to the current UTC time if omitted;
    supplying it explicitly (as every test in this milestone does) is
    what makes two otherwise-identical generations comparable/
    reproducible in tests without a real clock dependency.

    `registry` / `other_chapter_node_ids` are passed straight through
    to `validation.run_all_invariants` (Milestone 3) -- this function
    does not resolve `canonical_registry_snapshot_ref` itself; see
    module docstring.

    Raises:
        DSTArtifactError: if `tree` is empty (no chapter root to
            generate an artifact around), or if
            `heading_detection_provenance` names a `node_id` absent
            from `tree` (schema §2.4's documented build-integrity
            check -- see `find_dangling_provenance_node_ids`). Neither
            condition is a §15 invariant, so neither is reported via
            `validation_metadata`; both are preconditions for assembling
            an artifact at all, exactly like `builder.build_tree`'s own
            `DSTBuildError` preconditions one milestone earlier.
    """
    tree = tuple(tree)
    if not tree:
        raise DSTArtifactError(
            "generate_artifact: tree must contain at least the chapter "
            "root node (architecture §15 S2); got an empty tree."
        )

    build_provenance = BuildProvenance(
        canonical_registry_snapshot_ref=canonical_registry_snapshot_ref,
        heading_detection_provenance=heading_detection_provenance,
    )

    dangling = find_dangling_provenance_node_ids(tree, build_provenance)
    if dangling:
        raise DSTArtifactError(
            "generate_artifact: build_provenance.heading_detection_provenance "
            f"references node_id(s) not present in tree: "
            f"{[node_id.value for node_id in dangling]} (schema §2.4 "
            "build-integrity check)."
        )

    fingerprint = compute_chapter_fingerprint(tree)
    timestamp = build_timestamp if build_timestamp is not None else Timestamp(_utc_now_iso())

    artifact_metadata = ArtifactMetadata(
        schema_version=schema_version,
        compiler_version=compiler_version,
        identity_scheme_version=identity_scheme_version,
        chapter_id=chapter_id,
        build_timestamp=timestamp,
        chapter_fingerprint=fingerprint,
    )

    validation_metadata = run_all_invariants(
        tree,
        artifact_metadata,
        build_provenance,
        registry=registry,
        other_chapter_node_ids=other_chapter_node_ids,
    )

    derived_summary = compute_derived_summary(tree) if include_derived_summary else None

    return DocumentStructureTree(
        artifact_metadata=artifact_metadata,
        build_provenance=build_provenance,
        validation_metadata=validation_metadata,
        tree=tree,
        derived_summary=derived_summary,
    )


# ==========================================================================
# Deterministic JSON serialization / deserialization (schema §5)
# ==========================================================================

def to_canonical_json(dst: DocumentStructureTree) -> Dict[str, Any]:
    """`dst.to_json()` (Milestone 2.1, unchanged), with `tree`'s array
    order canonicalized by sorting on `node_id` -- schema §5.2's own
    words are "Array order within `tree` carries no meaning and must
    not be relied upon by any consumer", which is exactly the property
    that makes sorting it a safe, meaning-preserving canonicalization
    rather than a schema change: any two artifacts equal in every field
    the schema defines produce identical output here, regardless of
    which order their `tree` happened to be built or stored in.

    This is the one place this milestone imposes an ordering `tree`
    itself does not have -- `DocumentStructureTree.to_json()` itself is
    left untouched (still whatever order its own `tree` tuple holds),
    so this function, not that one, is what "deterministic
    serialization" means in this milestone's deliverables."""
    encoded = dst.to_json()
    encoded["tree"] = sorted(encoded["tree"], key=lambda node: node["node_id"])
    return encoded


def serialize(dst: DocumentStructureTree) -> str:
    """Deterministic JSON text for a `DocumentStructureTree`: two
    artifacts equal in every schema-defined field always serialize to
    byte-identical text, regardless of in-memory `tree` order (see
    `to_canonical_json`). Fixed `indent=2`, insertion-preserving key
    order (schema §5.1 field order, as written by each type's own
    `to_json`; never alphabetized -- alphabetizing would scramble the
    intentional field groupings §5.5's object hierarchy documents), and
    a single trailing newline, every call, every time."""
    return json.dumps(to_canonical_json(dst), indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def deserialize(text: str) -> DocumentStructureTree:
    """The exact inverse of `serialize`/`to_canonical_json`: parse JSON
    text and delegate to `DocumentStructureTree.from_json` (Milestone
    2.1, unchanged). Raises `DSTSerializationError` -- the same
    exception every other `from_json` in this package raises for
    unusable JSON shape -- rather than letting a raw
    `json.JSONDecodeError` escape this module's boundary."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DSTSerializationError(f"deserialize: input is not valid JSON ({exc}).") from exc
    return DocumentStructureTree.from_json(data)


def round_trip_text(dst: DocumentStructureTree) -> Tuple[str, DocumentStructureTree, str]:
    """The text-level analogue of `serialization.round_trip()`
    (Milestone 1) for a fully assembled artifact: encode -> decode ->
    re-encode. Returns `(text_once, decoded, text_twice)` so a caller
    can assert both `text_once == text_twice` (serialization is
    deterministic) and `decoded == dst` (deserialization recovers an
    equal artifact) -- the same two halves of round-trip fidelity every
    earlier milestone's own round-trip tests already check, now proven
    at the whole-artifact granularity roadmap M9 calls for."""
    text_once = serialize(dst)
    decoded = deserialize(text_once)
    text_twice = serialize(decoded)
    return text_once, decoded, text_twice