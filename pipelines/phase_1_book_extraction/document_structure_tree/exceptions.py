"""
document_structure_tree/exceptions.py — Milestone 1: exception hierarchy
for the Document Structure Tree (DST) layer.

Mirrors knowledge_graph/exceptions.py's own convention in this project
(small, specific exception classes so callers can catch precisely what
they care about, instead of parsing free-text messages), which itself
mirrors compiler/exceptions.py. Only the exceptions needed by
Milestone 1's scope (primitive/value-type validation, serialization,
identity derivation) are defined here. Exceptions for tree assembly,
validation-invariant reporting, and artifact generation belong to the
milestones that introduce those concerns (see roadmap M2, M4-M7, M9)
and are deliberately not anticipated here.
"""


class DocumentStructureTreeError(Exception):
    """Base class for every error raised anywhere in the
    document_structure_tree package. Mirrors
    knowledge_graph.exceptions.KnowledgeGraphError's role as the one
    catch-all ancestor for its own layer."""


class DSTValueError(DocumentStructureTreeError, ValueError):
    """Raised when a primitive/value-type constructor (schema §2.1) is
    given data that violates that type's own constraints -- e.g. an
    empty identifier, a negative Level, a malformed Timestamp, a
    BlockRange with start > end. Subclasses ValueError as well as
    DocumentStructureTreeError so existing generic `except ValueError`
    handling elsewhere in the codebase still catches these without
    modification."""


class DSTSerializationError(DocumentStructureTreeError, ValueError):
    """Raised by the generic serialization infrastructure
    (serialization.py) when JSON data cannot be decoded into the shape
    a type's `from_json` expects -- a missing required key, a wrong
    JSON type for a field, etc. Distinct from DSTValueError, which is
    raised by a type's own constructor for a value that decoded fine
    but fails that type's constraints; DSTSerializationError is raised
    before a constructor is even reached, when the JSON shape itself is
    unusable."""


class DSTIdentityError(DocumentStructureTreeError, ValueError):
    """Raised by identity.py's node_id derivation when called with
    structurally invalid inputs (e.g. a non-root level paired with no
    parent_id, or both/neither of `number` and `unnumbered_ordinal`
    supplied for a non-root node). Mirrors
    knowledge_graph.exceptions.GraphIdentityError's role for that
    package's own identity module."""


class DSTArtifactError(DocumentStructureTreeError, ValueError):
    """Raised by artifact.py (Milestone 4 -- Artifact Generation) when an
    already-built tree cannot be assembled into a `DocumentStructureTree`
    artifact at all -- e.g. an empty `tree` (no chapter root), or
    `build_provenance.heading_detection_provenance` naming a `node_id`
    absent from `tree` (schema §2.4's documented build-integrity check:
    "a node_id appearing here that doesn't exist in tree is a
    build-integrity defect", explicitly not one of the closed §15
    invariants, so it cannot be reported via `ValidationResult`/
    `InvariantId` and is instead a precondition failure here, mirroring
    `DSTBuildError`'s role for builder.py). Distinct from a *validation*
    outcome (`validation_metadata.validation_status = 'fail'`), which is
    a normal, representable artifact state, not an error -- generation
    itself only raises when the artifact cannot be assembled at all."""


class DSTBuildError(DocumentStructureTreeError, ValueError):
    """Raised by builder.py (Milestone 2.2 -- flat tree assembly, roadmap
    M2) when the *source* structure handed to the builder cannot be
    assembled into a tree at all -- e.g. two headings sharing the same
    source id, a heading naming a `parent_id` that names no other
    heading in the same input, or a parent cycle. These are
    preconditions for constructing anything (a node's `node_id` is
    derived recursively from its parent's identity, so an unresolvable
    parent chain means no `node_id` can be computed in the first
    place) -- distinct from the §15 structural/referential invariants
    (S1-S4, R1-R4, ...) a future validation engine (roadmap M4-M6)
    checks *against an already-built* tree's own data. Deliberately
    NOT raised for a dangling *content* reference (a `sequence` content
    entry naming a canonical object id the builder cannot resolve):
    resolving/validating that reference is R2's job (roadmap M5), not
    the builder's -- see builder.py's own module docstring."""