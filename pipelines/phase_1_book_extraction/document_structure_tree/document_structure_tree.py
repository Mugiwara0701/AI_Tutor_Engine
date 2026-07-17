"""
document_structure_tree/document_structure_tree.py — Milestone 2.1:
the artifact-level models (schema §2.2-2.5, §2.10) and the top-level
`DocumentStructureTree` artifact itself (schema §2.2).

SCOPE: this module implements the models that surround `tree` in the
persisted artifact -- `ArtifactMetadata`, `BuildProvenance` (and its
`HeadingDetectionEntry` supporting record), `ValidationMetadata` (and
its `ValidationResult`/`Violation` supporting records), `DerivedSummary`,
and `DocumentStructureTree` itself -- purely as data holders with the
*local* constructor-time validation each one can perform about its own
fields, plus JSON round-tripping.

Deliberately NOT implemented here (all belong to later milestones):

  - Producing/computing any of this data. `chapter_fingerprint`
    computation (B3), running the §15 invariant suite to populate
    `validation_metadata.validation_results`, and generating the
    artifact end-to-end are all roadmap M7-M10 concerns ("artifact
    generation", explicitly out of scope for this milestone). This
    module's types only *carry* that data once it exists; they never
    compute it.
  - `canonical_registry_snapshot_ref` resolvability (B2) and
    `heading_detection_provenance` node_id cross-referencing against
    `tree` -- both require external/whole-artifact state a single
    `BuildProvenance` cannot verify about itself, and are validation-
    engine concerns (roadmap M4-M6).
  - S1-S4, R1-R4, O1-O2, I1-I3 tree-topology invariants -- all require
    resolving `parent_id`/`ref` chains across the whole `tree`
    ("parent resolution", "hierarchy generation", "validation engine";
    explicitly out of scope). See `heading_node.py` and
    `sequence_entry.py` for the corresponding notes on those types.

What IS in scope and enforced at construction time, because each is a
closure property fully checkable from data the object already holds
(no tree-walk, no external registry, no parent resolution required):

  - `ValidationResult`: `violations` present-and-non-empty iff
    `status = 'fail'`, omitted iff `status = 'pass'` (schema §2.5) --
    a fact about a single `ValidationResult`'s own two fields.
  - `ValidationMetadata`: `validation_status = 'pass'` iff every
    `ValidationResult.status = 'pass'` (schema §2.5) -- a fact about a
    single `ValidationMetadata`'s own two fields. Also: exactly one
    `ValidationResult` per invariant defined by the closed `InvariantId`
    enumeration (schema §6) -- checkable against a closed, already-known
    vocabulary, not against a tree.
  - `DocumentStructureTree`: every node's `chapter_id` equals
    `artifact_metadata.chapter_id` (schema §2.6's "per-node/artifact
    consistency check") -- a flat, O(n) scan comparing two fields this
    object already directly holds (`artifact_metadata` and `tree`); it
    does not resolve `parent_id`, build an index, or walk any hierarchy,
    so it is not "tree construction" or "parent resolution" in the
    sense those terms are used to scope this milestone out -- it is the
    one cross-check the frozen schema attaches directly to this
    object's own two fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .enums import InvariantId, ValidationStatus
from .exceptions import DSTValueError
from .heading_node import HeadingNode
from .primitives import (
    ChapterId,
    CompilerVersion,
    Fingerprint,
    IdentitySchemeVersion,
    NodeId,
    SchemaVersion,
    Timestamp,
)
from .enums import HeadingDetectionMethod
from .serialization import (
    OMIT,
    json_object,
    require_dict,
    require_key,
    require_non_empty_str,
)

__all__ = [
    "ArtifactMetadata",
    "HeadingDetectionEntry",
    "BuildProvenance",
    "Violation",
    "ValidationResult",
    "ValidationMetadata",
    "DerivedSummary",
    "DocumentStructureTree",
]


# ==========================================================================
# ArtifactMetadata (schema §2.3)
# ==========================================================================

@dataclass(frozen=True)
class ArtifactMetadata:
    """Identity of an artifact build and its schema (schema §2.3) --
    answers "what is this artifact and under what rules was it
    produced." Every field is itself a validated primitive type from
    Milestone 1 (`primitives.py`); this type adds no further per-field
    validation of its own beyond composing those. The cross-field rule
    schema §2.3 states ("mutually independent -- none may be inferred
    from another") is a *prohibition on doing something*, not a
    checkable runtime invariant, so there is nothing to enforce for it
    here beyond simply never adding such an inference."""

    schema_version: SchemaVersion
    compiler_version: CompilerVersion
    identity_scheme_version: IdentitySchemeVersion
    chapter_id: ChapterId
    build_timestamp: Timestamp
    chapter_fingerprint: Fingerprint

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("schema_version", self.schema_version.to_json()),
                ("compiler_version", self.compiler_version.to_json()),
                ("identity_scheme_version", self.identity_scheme_version.to_json()),
                ("chapter_id", self.chapter_id.to_json()),
                ("build_timestamp", self.build_timestamp.to_json()),
                ("chapter_fingerprint", self.chapter_fingerprint.to_json()),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "ArtifactMetadata":
        data = require_dict(data, "ArtifactMetadata")
        return cls(
            schema_version=SchemaVersion.from_json(require_key(data, "schema_version", "ArtifactMetadata")),
            compiler_version=CompilerVersion.from_json(require_key(data, "compiler_version", "ArtifactMetadata")),
            identity_scheme_version=IdentitySchemeVersion.from_json(
                require_key(data, "identity_scheme_version", "ArtifactMetadata")
            ),
            chapter_id=ChapterId.from_json(require_key(data, "chapter_id", "ArtifactMetadata")),
            build_timestamp=Timestamp.from_json(require_key(data, "build_timestamp", "ArtifactMetadata")),
            chapter_fingerprint=Fingerprint.from_json(
                require_key(data, "chapter_fingerprint", "ArtifactMetadata")
            ),
        )


# ==========================================================================
# BuildProvenance (schema §2.4) + HeadingDetectionEntry
# ==========================================================================

@dataclass(frozen=True)
class HeadingDetectionEntry:
    """Supporting record of `BuildProvenance.heading_detection_provenance`
    (schema §2.4) -- not independently addressable outside that list.

    `details` is explicitly "implementation-defined" and "not part of
    the validated schema" (schema §2.4): its internal shape is
    unconstrained here by design, so this type performs no validation
    of its contents whatsoever -- it is carried through as opaque,
    already-JSON-compatible data."""

    node_id: NodeId
    method: HeadingDetectionMethod
    details: Optional[Dict[str, Any]] = None

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("node_id", self.node_id.to_json()),
                ("method", self.method.to_json()),
                ("details", self.details if self.details is not None else OMIT),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "HeadingDetectionEntry":
        data = require_dict(data, "HeadingDetectionEntry")
        return cls(
            node_id=NodeId.from_json(require_key(data, "node_id", "HeadingDetectionEntry")),
            method=HeadingDetectionMethod.from_json(require_key(data, "method", "HeadingDetectionEntry")),
            details=data.get("details"),
        )


@dataclass(frozen=True)
class BuildProvenance:
    """Compiler-process facts (schema §2.4): what the artifact was
    validated against, and (optionally) how each heading was detected.
    Deliberately excluded from `HeadingNode` (architecture §18.6) so
    document-structure facts and compilation-process facts never share
    a namespace.

    `canonical_registry_snapshot_ref` resolvability (B2) is a
    validation-engine concern (roadmap M4-M6) requiring external
    registry state; this type only enforces that the reference is a
    non-empty string, per its schema §2.4 type ("String (opaque
    snapshot identifier)")."""

    canonical_registry_snapshot_ref: str
    heading_detection_provenance: Optional[Tuple[HeadingDetectionEntry, ...]] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_registry_snapshot_ref",
            require_non_empty_str(
                self.canonical_registry_snapshot_ref, "BuildProvenance.canonical_registry_snapshot_ref"
            ),
        )
        if self.heading_detection_provenance is not None:
            object.__setattr__(
                self, "heading_detection_provenance", tuple(self.heading_detection_provenance)
            )

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("canonical_registry_snapshot_ref", self.canonical_registry_snapshot_ref),
                (
                    "heading_detection_provenance",
                    [entry.to_json() for entry in self.heading_detection_provenance]
                    if self.heading_detection_provenance is not None
                    else OMIT,
                ),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "BuildProvenance":
        data = require_dict(data, "BuildProvenance")
        raw_provenance = data.get("heading_detection_provenance")
        provenance = (
            tuple(HeadingDetectionEntry.from_json(entry) for entry in raw_provenance)
            if raw_provenance is not None
            else None
        )
        return cls(
            canonical_registry_snapshot_ref=require_key(
                data, "canonical_registry_snapshot_ref", "BuildProvenance"
            ),
            heading_detection_provenance=provenance,
        )


# ==========================================================================
# ValidationMetadata (schema §2.5) + ValidationResult + Violation
# ==========================================================================

@dataclass(frozen=True)
class Violation(object):
    """Supporting record of `ValidationResult.violations` (schema
    §2.5). Carries no severity classification -- the frozen
    architecture treats every invariant failure as equally blocking
    (§15 closing statement), so a `Violation`'s blocking status is
    fully determined by its parent `ValidationResult.status`, never by
    a per-violation field (and none is defined here)."""

    message: str
    node_id: Optional[NodeId] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", require_non_empty_str(self.message, "Violation.message"))

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("node_id", self.node_id.to_json() if self.node_id is not None else OMIT),
                ("message", self.message),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "Violation":
        data = require_dict(data, "Violation")
        node_id = NodeId.from_json(data["node_id"]) if "node_id" in data else None
        return cls(message=require_key(data, "message", "Violation"), node_id=node_id)


@dataclass(frozen=True)
class ValidationResult:
    """One invariant's outcome (schema §2.5) -- one per invariant
    defined in architecture §15, assembled into
    `ValidationMetadata.validation_results`.

    Enforces the single canonical representation schema §2.5 fixes:
    `violations` present and non-empty if and only if `status = fail`;
    omitted (never an empty list) when `status = pass`. This is a fact
    about this object's own two fields, checkable without any tree or
    external state."""

    invariant_id: InvariantId
    status: ValidationStatus
    violations: Optional[Tuple[Violation, ...]] = None

    def __post_init__(self) -> None:
        if self.violations is not None:
            object.__setattr__(self, "violations", tuple(self.violations))

        if self.status is ValidationStatus.PASS and self.violations:
            raise DSTValueError(
                "ValidationResult: violations must be omitted (not present) "
                f"when status='pass' (schema §2.5); got {len(self.violations)} "
                f"violation(s) for invariant {self.invariant_id.value!r}."
            )
        if self.status is ValidationStatus.FAIL and not self.violations:
            raise DSTValueError(
                "ValidationResult: violations must be present and non-empty "
                f"when status='fail' (schema §2.5); got none for invariant "
                f"{self.invariant_id.value!r}."
            )

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("invariant_id", self.invariant_id.to_json()),
                ("status", self.status.to_json()),
                (
                    "violations",
                    [v.to_json() for v in self.violations] if self.violations else OMIT,
                ),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "ValidationResult":
        data = require_dict(data, "ValidationResult")
        raw_violations = data.get("violations")
        violations = (
            tuple(Violation.from_json(v) for v in raw_violations) if raw_violations is not None else None
        )
        return cls(
            invariant_id=InvariantId.from_json(require_key(data, "invariant_id", "ValidationResult")),
            status=ValidationStatus.from_json(require_key(data, "status", "ValidationResult")),
            violations=violations,
        )


@dataclass(frozen=True)
class ValidationMetadata:
    """The stored outcome of running the §15 invariant suite against a
    build (schema §2.5) -- this milestone stores and validates that
    outcome's *shape*; it never runs the suite itself (roadmap M4-M7,
    out of scope here).

    Enforces two closure properties schema §2.5/§6 state, both fully
    checkable from this object's own two fields against the closed,
    already-known `InvariantId` vocabulary -- no tree-walk or external
    state required:

    1. `validation_status = pass` iff every entry in
       `validation_results` has `status = pass`.
    2. `validation_results` contains exactly one entry per invariant in
       the closed `InvariantId` enumeration -- no duplicates, no gaps.
    """

    validation_status: ValidationStatus
    validation_results: Tuple[ValidationResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "validation_results", tuple(self.validation_results))

        seen: Dict[InvariantId, ValidationResult] = {}
        for result in self.validation_results:
            if result.invariant_id in seen:
                raise DSTValueError(
                    "ValidationMetadata: duplicate validation_results entry "
                    f"for invariant {result.invariant_id.value!r} (schema §6: "
                    "exactly one entry per invariant)."
                )
            seen[result.invariant_id] = result

        missing = set(InvariantId) - set(seen)
        if missing:
            raise DSTValueError(
                "ValidationMetadata: missing validation_results entries for "
                f"invariant(s) {sorted(m.value for m in missing)} (schema §6: "
                "exactly one entry per invariant)."
            )

        all_pass = all(result.status is ValidationStatus.PASS for result in self.validation_results)
        expected_status = ValidationStatus.PASS if all_pass else ValidationStatus.FAIL
        if self.validation_status is not expected_status:
            raise DSTValueError(
                f"ValidationMetadata.validation_status ({self.validation_status.value!r}) "
                "is inconsistent with validation_results (schema §2.5 closure "
                f"property: 'pass' iff every result passes); expected "
                f"{expected_status.value!r}."
            )

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("validation_status", self.validation_status.to_json()),
                ("validation_results", [r.to_json() for r in self.validation_results]),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "ValidationMetadata":
        data = require_dict(data, "ValidationMetadata")
        results = tuple(
            ValidationResult.from_json(r) for r in require_key(data, "validation_results", "ValidationMetadata")
        )
        return cls(
            validation_status=ValidationStatus.from_json(
                require_key(data, "validation_status", "ValidationMetadata")
            ),
            validation_results=results,
        )


# ==========================================================================
# DerivedSummary (schema §2.10) — optional, non-canonical
# ==========================================================================

@dataclass(frozen=True)
class DerivedSummary:
    """Convenience statistics regenerable at any time from `tree`
    (schema §2.10) -- e.g. node counts, maximum depth. Deliberately
    non-canonical: "never referenced by any §15 validation invariant or
    §17 Phase 2 guarantee" (schema §2.10), and the schema explicitly
    does not fix its internal shape ("nothing depends on it being any
    particular shape").

    This type therefore carries an arbitrary JSON-object payload with
    zero interpretation or validation of its contents -- doing anything
    more here would invent structure the frozen schema deliberately
    declines to define, and would misrepresent this milestone's
    "no artifact generation" scope by implying this type computes
    summary statistics, which it does not."""

    data: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        return dict(self.data)

    @classmethod
    def from_json(cls, data: Any) -> "DerivedSummary":
        data = require_dict(data, "DerivedSummary")
        return cls(data=dict(data))


# ==========================================================================
# DocumentStructureTree (schema §2.2) — the top-level artifact
# ==========================================================================

@dataclass(frozen=True)
class DocumentStructureTree:
    """The single persisted artifact representing a chapter's
    structural map (schema §2.2) -- the root object a Phase 2 consumer
    loads.

    This milestone implements this type as a pure data holder over
    already-constructed `ArtifactMetadata`/`BuildProvenance`/
    `ValidationMetadata`/`HeadingNode` values: it does not build a
    `tree` from a source structure, does not resolve `parent_id`
    references, does not run the §15 invariant suite, and does not
    compute `chapter_fingerprint`/`validation_metadata` -- all of that
    is compiler/validation-engine work assembled by later milestones
    (roadmap M2-M10) and explicitly out of scope here.

    The one cross-field check enforced at construction is schema
    §2.6's "per-node/artifact consistency check": every node's
    `chapter_id` must equal `artifact_metadata.chapter_id`. This is a
    flat scan over two fields this object already directly holds --
    not tree construction, not parent resolution, not a §15 invariant
    -- so it stays within this milestone's "schema-defined validation"
    deliverable rather than crossing into the validation engine.
    """

    artifact_metadata: ArtifactMetadata
    build_provenance: BuildProvenance
    validation_metadata: ValidationMetadata
    tree: Tuple[HeadingNode, ...]
    derived_summary: Optional[DerivedSummary] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tree", tuple(self.tree))

        expected_chapter_id = self.artifact_metadata.chapter_id
        for node in self.tree:
            if node.chapter_id != expected_chapter_id:
                raise DSTValueError(
                    f"DocumentStructureTree: node {node.node_id.value!r} has "
                    f"chapter_id {node.chapter_id.value!r}, which does not "
                    f"match artifact_metadata.chapter_id "
                    f"{expected_chapter_id.value!r} (schema §2.6)."
                )

    def to_json(self) -> Dict[str, Any]:
        return json_object(
            [
                ("artifact_metadata", self.artifact_metadata.to_json()),
                ("build_provenance", self.build_provenance.to_json()),
                ("validation_metadata", self.validation_metadata.to_json()),
                ("tree", [node.to_json() for node in self.tree]),
                (
                    "derived_summary",
                    self.derived_summary.to_json() if self.derived_summary is not None else OMIT,
                ),
            ]
        )

    @classmethod
    def from_json(cls, data: Any) -> "DocumentStructureTree":
        data = require_dict(data, "DocumentStructureTree")
        tree = tuple(
            HeadingNode.from_json(node) for node in require_key(data, "tree", "DocumentStructureTree")
        )
        derived_summary = (
            DerivedSummary.from_json(data["derived_summary"]) if "derived_summary" in data else None
        )
        return cls(
            artifact_metadata=ArtifactMetadata.from_json(
                require_key(data, "artifact_metadata", "DocumentStructureTree")
            ),
            build_provenance=BuildProvenance.from_json(
                require_key(data, "build_provenance", "DocumentStructureTree")
            ),
            validation_metadata=ValidationMetadata.from_json(
                require_key(data, "validation_metadata", "DocumentStructureTree")
            ),
            tree=tree,
            derived_summary=derived_summary,
        )
