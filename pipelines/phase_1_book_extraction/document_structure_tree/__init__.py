"""
document_structure_tree/ — Phase 1.1, Milestones 1-4: Core DST Models,
DST Builder, Validation Engine, and Artifact Generation.

Implements the Document Structure Tree (DST) compiler's in-memory
models, against the frozen `DST_Architecture_v1.1.md` (Version 1.0)
and `DST_Schema_Design_v1.1.md` (Schema Version 1.0). This package sits
alongside `knowledge_graph/` as DST's counterpart: both are built from
the same upstream inputs (Chapter JSON, canonical registries) and share
canonical object IDs as their only point of contact (architecture §6) --
neither package imports from the other.

MILESTONE 1 SCOPE (carried over unchanged, reused by later milestones):
    - `primitives.py`  — every reusable value type from schema §2.1.
    - `enums.py`        — every closed enumeration the frozen schema
                          defines (`EntryType`, `ValidationStatus`,
                          `HeadingDetectionMethod`, `InvariantId`).
    - `serialization.py`— generic, model-agnostic JSON serialization
                          scaffolding.
    - `identity.py`     — the pure `compute_node_id` function
                          (architecture §14, schema §4).
    - `exceptions.py`   — the error hierarchy the above raise into.

MILESTONE 2.1 SCOPE (carried over unchanged, reused by later
milestones) — the model layer:
    - `sequence_entry.py`         — `SequenceEntry` (schema §2.7) and
                                     the Typed Canonical Reference shape
                                     it carries (schema §2.8).
    - `heading_node.py`           — `HeadingNode` (schema §2.6).
    - `document_structure_tree.py`— `ArtifactMetadata` (§2.3),
                                     `BuildProvenance` /
                                     `HeadingDetectionEntry` (§2.4),
                                     `ValidationMetadata` /
                                     `ValidationResult` / `Violation`
                                     (§2.5), `DerivedSummary` (§2.10),
                                     and the top-level
                                     `DocumentStructureTree` (§2.2).

MILESTONE 2.2 SCOPE (carried over unchanged, reused by later
milestones) — the DST Builder (roadmap M2, "Flat Tree Assembly"):
    - `builder.py` — `build_tree()`, the tree-assembly algorithm
                      (constructs every `HeadingNode` incl. the chapter
                      root, assigns `node_id`/`parent_id`, computes
                      `level` structurally, builds `sequence` in
                      best-effort reading order, and builds the
                      `node_id -> node` / `parent_id -> children`
                      indices), plus `build_tree_from_chapter_json()`,
                      a thin adapter consuming the attached
                      `schemas.chapter_schema.ChapterJSON` Phase 1
                      model read-only. Every node's `span` remains the
                      empty `Span()`, pending span computation (roadmap
                      M3) -- an empty span is a fully valid, defined
                      case (architecture §13), not a defect.

MILESTONE 3 SCOPE (carried over unchanged, reused by this milestone)
— the Validation Engine (roadmap M4-M7):
    - `validation.py` — every §15 invariant check (S1-S4, R1-R4, O1-O2,
                         I1-I3, B1-B3), `compute_chapter_fingerprint`
                         (B3's authoritative formula), and
                         `run_all_invariants()` / `revalidate()`,
                         assembling a `ValidationMetadata` (schema
                         §2.5). The `CanonicalRegistrySnapshot` Protocol
                         (plus an in-memory reference implementation)
                         is the narrow external seam R2-R4/B2 call
                         against.

MILESTONE 4 SCOPE (this package, today) — Artifact Generation (roadmap
M8/M9/M11, schema §2.2-2.5/§2.10/§5):
    - `artifact.py` — `generate_artifact()`, converting an
                       already-built `tree` plus artifact-level inputs
                       into a fully assembled `DocumentStructureTree`:
                       populates `ArtifactMetadata` (delegating
                       `chapter_fingerprint` computation to Milestone
                       3's own authoritative formula) and
                       `BuildProvenance` (including the schema §2.4
                       dangling-`node_id` build-integrity check),
                       drives Milestone 3's `run_all_invariants()` to
                       produce `ValidationMetadata`, and optionally
                       computes a `DerivedSummary` via
                       `compute_derived_summary()`. Also provides
                       deterministic whole-artifact JSON serialization/
                       deserialization (`serialize()` / `deserialize()`
                       / `to_canonical_json()`) and a text-level
                       round-trip harness (`round_trip_text()`). See
                       that module's own docstring for the precise
                       scope boundary (no builder changes, no
                       validation-engine changes, no compiler pipeline
                       integration, no persistence).

Every model implements construction-time validation of the *local*
schema constraints a single object can check about itself (shape,
discriminator consistency, closure properties over its own fields) and
a `to_json`/`from_json` pair following schema §5's serialization rules
exactly. See each module's own docstring for the precise boundary
between what is validated here and what is deferred.

MILESTONE 5 SCOPE (this package, today) — Compiler Integration (roadmap
M10, architecture §7, §9):
    - `state.py`            — chapter-scoped "current DST" lifecycle
                               (`set_current_document_structure_tree()`/
                               `get_current_document_structure_tree()`/
                               `has_current_document_structure_tree()`/
                               `reset_document_structure_tree_state()`),
                               mirroring `knowledge_graph/state.py`'s
                               established idiom.
    - `registry_snapshot.py`— `CompilerRegistrySnapshot`, the concrete
                               `validation.CanonicalRegistrySnapshot`
                               implementation Milestone 3 anticipated but
                               deliberately left unimplemented ("owned
                               upstream") -- adapts this codebase's real
                               canonical registries
                               (`compiler.RegistryManager`, already
                               fully populated by the existing compiler
                               pipeline) to that Protocol, so
                               R2/R3/R4/B2 can run against real chapter
                               data, not just the in-memory fake.
    - `persistence.py`      — `persist_document_structure_tree()`/
                               `load_document_structure_tree()`/
                               `document_structure_tree_exists()`,
                               reusing `artifact.to_canonical_json()`
                               (never re-serializing) and this
                               codebase's existing OneDrive storage
                               surface, mirroring
                               `knowledge_graph/persistence.py`. NOT
                               imported below, by design: it depends on
                               `modules.json_writer`/`storage.exceptions`,
                               external to this package -- exactly why
                               `knowledge_graph/__init__.py` never
                               imports `knowledge_graph/persistence.py`
                               either. Callers (`pipeline.py`) import
                               `document_structure_tree.persistence`
                               directly, mirroring how `pipeline.py`
                               already imports `knowledge_graph.
                               persistence` directly rather than through
                               `knowledge_graph/__init__.py`. This keeps
                               `import document_structure_tree` free of
                               any dependency on those two external
                               modules, exactly as it already was before
                               this milestone.

None of Milestone 5's three files above modify `builder.py`,
`validation.py`, `serialization.py`, `artifact.py`,
`document_structure_tree.py`, `heading_node.py`, `sequence_entry.py`,
`primitives.py`, `identity.py`, `enums.py`, or `exceptions.py` -- every
model, algorithm, and validation invariant Milestones 1-4 already built
is reused exactly as it already exists (this milestone's own "Reuse the
existing builder, validator, serializer, and models" instruction). The
compiler-pipeline wiring itself (invoking these three modules, plus
Milestone 4's `build_tree_from_chapter_json()`/`generate_artifact()`, at
the correct point in `pipeline.py`'s `process_chapter()`) lives in
`pipeline.py`, not in this package, exactly as every other artifact
type's own pipeline integration already does (`knowledge_graph.
build_nodes`/`build_edges` are called directly from `pipeline.py`, never
wrapped in a second orchestration package).

EXPLICITLY NOT IN THIS PACKAGE (out of scope for this milestone too --
this milestone's own "Out of Scope" instructions):
    - Span *computation* over a tree -- every node `build_tree()`
      constructs carries the empty `Span()`; `Span` itself remains only
      a value container, as in Milestone 1. Not part of this
      milestone's own scope list, and not touched here.
    - Any change to the DST Architecture, DST Schema, DST Builder,
      Validation Engine, or Serialization logic.
    - A new compiler architecture, a new artifact system, a new storage
      system, or a new persistence mechanism -- `persistence.py` above
      reuses this codebase's existing OneDrive storage surface exactly
      as every sibling artifact-type persistence module already does.
    - Phase 2 functionality.

Usage:

    from document_structure_tree import (
        ChapterId, Level, NodeId, BlockRange, Span,
        EntryType, ValidationStatus,
        compute_node_id, IDENTITY_SCHEME_VERSION,
        HeadingNode, SequenceEntry, DocumentStructureTree,
        HeadingSource, ContentRef, build_tree,
        SchemaVersion, CompilerVersion, Timestamp,
        generate_artifact, serialize, deserialize,
    )

    root_id = compute_node_id(ChapterId("chap-07"), Level(0), None)
    root = HeadingNode(
        node_id=root_id,
        chapter_id=ChapterId("chap-07"),
        level=Level(0),
        parent_id=None,
        sequence=(),
        span=Span(),
    )

    artifact = generate_artifact(
        tree=(root,),
        chapter_id=ChapterId("chap-07"),
        schema_version=SchemaVersion("1.1.0"),
        compiler_version=CompilerVersion("0.1.0"),
        canonical_registry_snapshot_ref="registry-snap-2026-07-01",
        build_timestamp=Timestamp("2026-07-15T09:00:00Z"),
    )
    artifact_text = serialize(artifact)
    assert deserialize(artifact_text) == artifact
"""
from .artifact import (
    compute_derived_summary,
    deserialize,
    find_dangling_provenance_node_ids,
    generate_artifact,
    round_trip_text,
    serialize,
    to_canonical_json,
)
from .builder import (
    BuiltTree,
    ContentRef,
    HeadingSource,
    ROOT_CONTENT_KEY,
    build_tree,
    build_tree_from_chapter_json,
)
from .document_structure_tree import (
    ArtifactMetadata,
    BuildProvenance,
    DerivedSummary,
    DocumentStructureTree,
    HeadingDetectionEntry,
    ValidationMetadata,
    ValidationResult,
    Violation,
)
from .enums import (
    EntryType,
    HeadingDetectionMethod,
    InvariantId,
    ValidationStatus,
)
from .exceptions import (
    DocumentStructureTreeError,
    DSTArtifactError,
    DSTBuildError,
    DSTIdentityError,
    DSTSerializationError,
    DSTValueError,
)
from .heading_node import HeadingNode
from .identity import IDENTITY_SCHEME_VERSION, compute_node_id
from .primitives import (
    BlockIndex,
    BlockRange,
    CanonicalObjectId,
    ChapterId,
    CompilerVersion,
    Fingerprint,
    IdentitySchemeVersion,
    Level,
    NodeId,
    ObjectType,
    PageLocator,
    PageRange,
    SchemaVersion,
    Span,
    Timestamp,
)
from .registry_snapshot import EXCLUDED_REGISTRY_NAMES, CompilerRegistrySnapshot
from .sequence_entry import SequenceEntry
from .serialization import OMIT, JsonSerializable, json_object, round_trip
from .state import (
    get_current_document_structure_tree,
    has_current_document_structure_tree,
    reset_document_structure_tree_state,
    set_current_document_structure_tree,
)
from .validation import (
    CanonicalRegistrySnapshot,
    InMemoryCanonicalRegistrySnapshot,
    compute_chapter_fingerprint,
    revalidate,
    run_all_invariants,
)

__all__ = [
    # enums
    "EntryType",
    "ValidationStatus",
    "HeadingDetectionMethod",
    "InvariantId",
    # exceptions
    "DocumentStructureTreeError",
    "DSTValueError",
    "DSTSerializationError",
    "DSTIdentityError",
    "DSTBuildError",
    "DSTArtifactError",
    # identity
    "compute_node_id",
    "IDENTITY_SCHEME_VERSION",
    # primitives
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
    # Milestone 2.1: core DST models
    "SequenceEntry",
    "HeadingNode",
    "ArtifactMetadata",
    "HeadingDetectionEntry",
    "BuildProvenance",
    "Violation",
    "ValidationResult",
    "ValidationMetadata",
    "DerivedSummary",
    "DocumentStructureTree",
    # Milestone 2.2: DST builder
    "HeadingSource",
    "ContentRef",
    "BuiltTree",
    "ROOT_CONTENT_KEY",
    "build_tree",
    "build_tree_from_chapter_json",
    # Milestone 3: validation engine
    "CanonicalRegistrySnapshot",
    "InMemoryCanonicalRegistrySnapshot",
    "compute_chapter_fingerprint",
    "run_all_invariants",
    "revalidate",
    # Milestone 4: artifact generation
    "generate_artifact",
    "compute_derived_summary",
    "find_dangling_provenance_node_ids",
    "serialize",
    "deserialize",
    "to_canonical_json",
    "round_trip_text",
    # serialization infrastructure
    "OMIT",
    "JsonSerializable",
    "json_object",
    "round_trip",
    # Milestone 5: compiler integration -- chapter-scoped state
    "set_current_document_structure_tree",
    "get_current_document_structure_tree",
    "has_current_document_structure_tree",
    "reset_document_structure_tree_state",
    # Milestone 5: compiler integration -- canonical registry adapter
    "CompilerRegistrySnapshot",
    "EXCLUDED_REGISTRY_NAMES",
    # Milestone 5: compiler integration -- persistence.py is NOT
    # imported here (see module docstring); import it directly, e.g.
    # `from document_structure_tree.persistence import
    # persist_document_structure_tree`.
]