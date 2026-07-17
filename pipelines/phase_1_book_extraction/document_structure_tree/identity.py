"""
document_structure_tree/identity.py — Milestone 1: Node Identity
foundation (architecture §14, schema §4).

SCOPE: this module implements ONLY `compute_node_id`, the pure,
side-effect-free `node_id` derivation function, plus the
`identity_scheme_version` token that names this specific derivation
rule (architecture §16). It does NOT implement `HeadingNode`, does NOT
enumerate a tree's siblings to decide who gets which disambiguator, and
is NEVER called against real extraction data anywhere in this
milestone. Sibling enumeration (deciding, for an unnumbered heading,
what its ordinal position among unnumbered siblings actually is) is
tree-assembly logic and belongs to the DST builder (roadmap M2),
explicitly out of scope here -- this function only accepts an
already-decided disambiguator and turns it into a `node_id`.

DERIVATION, restated from schema §4:

    node_id(node) =
        hash_or_encode(
            chapter_id,
            level,
            node_id(parent(node)),   -- recursive; sentinel at the root
            disambiguator(node)
        )

    disambiguator(node) =
        number                                       if number is present
        ordinal position among unnumbered siblings    otherwise

This function reads only identity fields (`chapter_id`, `level`, parent
identity, `number`/ordinal) — never `title`, `span`, or `sequence`.
That exclusion is enforced structurally, not just by omission: the
function's signature has no parameter through which those fields could
even be passed, so a future refactor cannot accidentally thread them in
without changing this function's signature (and therefore being an
obviously reviewable, explicit change) -- the property the roadmap's M1
risk notes specifically ask for ("worth the extra design care ... it
converts an entire class of future bugs into compile-time
impossibilities").

CONCRETE ENCODING: schema §4 leaves the concrete encoding (hash vs.
structured string) as an implementation choice, explicitly deferred to
`identity_scheme_version` (architecture §16) rather than fixed by the
frozen documents. This implementation encodes a node's identity fields
into a deterministic pipe-delimited payload, SHA-256 hashes it, and
prefixes the result with the node's own `chapter_id` for human
traceability and to make cross-chapter scope isolation (I3) true by
construction rather than merely improbable-by-hash-collision.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from .exceptions import DSTIdentityError
from .primitives import ChapterId, IdentitySchemeVersion, Level, NodeId

__all__ = ["IDENTITY_SCHEME_VERSION", "compute_node_id"]


# This derivation rule's own version marker (architecture §16):
# independent of `schema_version` and `compiler_version`. Bump only if
# the node_id derivation *rule* implemented by `compute_node_id` below
# changes in a way that would make an old node_id stop matching a new
# one for "the same" structural inputs (e.g. a fix to sibling
# disambiguation for unnumbered headings, architecture §9.1's own
# example of what changes this token).
IDENTITY_SCHEME_VERSION = IdentitySchemeVersion("1")

# Sentinel standing in for "no parent" in the hashed payload -- only
# ever used for the chapter root. Namespaced so it can never collide
# with a real NodeId's own value (which is always non-empty and, by
# construction below, always contains a ":" separator after the
# chapter_id prefix followed by a 24-hex-char suffix -- this sentinel
# matches neither shape).
_ROOT_PARENT_SENTINEL = "ROOT"

# Tags distinguishing a numbered disambiguator from an unnumbered-
# ordinal one in the hashed payload, so a numbered heading numbered
# "2" and an unnumbered heading at ordinal position 2 under the same
# parent can never hash to the same payload.
_NUMBERED_TAG = "n"
_UNNUMBERED_TAG = "u"

# Length, in hex characters, of the digest suffix kept in a generated
# NodeId. 24 hex chars = 96 bits of a SHA-256 digest -- ample collision
# resistance for identifiers scoped to a single chapter's heading
# count, while keeping generated ids reasonably short.
_DIGEST_SUFFIX_LENGTH = 24


def compute_node_id(
    chapter_id: ChapterId,
    level: Level,
    parent_id: Optional[NodeId],
    *,
    number: Optional[str] = None,
    unnumbered_ordinal: Optional[int] = None,
) -> NodeId:
    """Pure, deterministic `node_id` derivation (architecture §14,
    schema §4).

    Reads only structural-identity fields: `chapter_id`, `level`, the
    already-derived identity of the parent (`parent_id`), and a sibling
    disambiguator -- `number` when the heading has one, else
    `unnumbered_ordinal` (0-based ordinal position among unnumbered
    siblings under the same parent). Deliberately accepts no `title`,
    `span`, or `sequence` parameter at all.

    Root node (architecture §14; S2 -- exactly one `level = 0` node per
    chapter, so the root has no siblings and needs no disambiguator):
    call with `parent_id=None` and both `number`/`unnumbered_ordinal`
    left `None`.

    Non-root node: `parent_id` must be provided, and exactly one of
    `number` / `unnumbered_ordinal` must be provided, mirroring §14's
    disambiguator rule. *Which* one applies is a fact about the
    heading itself (does it have a printed number or not?), decided by
    the caller -- this function encodes an already-decided
    disambiguator, it does not discover one by inspecting a tree.

    Raises `DSTIdentityError` for any input that violates the shape
    architecture §14/§15 requires (e.g. a non-root level with no
    parent, or a root level with a parent).
    """
    if parent_id is None:
        if not level.is_root():
            raise DSTIdentityError(
                "compute_node_id: parent_id=None is only valid for the "
                "chapter root (level=0 — architecture §14, §15 S2); got "
                f"level={level.value}."
            )
        if number is not None or unnumbered_ordinal is not None:
            raise DSTIdentityError(
                "compute_node_id: the chapter root has no siblings and "
                "takes no disambiguator (architecture §14); got "
                f"number={number!r}, unnumbered_ordinal={unnumbered_ordinal!r}."
            )
        parent_component = _ROOT_PARENT_SENTINEL
        disambiguator_component = "root"
    else:
        if level.is_root():
            raise DSTIdentityError(
                "compute_node_id: level=0 is reserved for the chapter "
                "root, which must have parent_id=None (architecture "
                f"§15 S2); got parent_id={parent_id.value!r} with level=0."
            )
        if (number is None) == (unnumbered_ordinal is None):
            raise DSTIdentityError(
                "compute_node_id: exactly one of `number` or "
                "`unnumbered_ordinal` must be provided for a non-root "
                "node (architecture §14 sibling disambiguator); got "
                f"number={number!r}, unnumbered_ordinal={unnumbered_ordinal!r}."
            )
        if number is not None:
            if number == "":
                raise DSTIdentityError("compute_node_id: `number`, when given, must be a non-empty string.")
            disambiguator_component = f"{_NUMBERED_TAG}:{number}"
        else:
            if unnumbered_ordinal < 0:  # type: ignore[operator]
                raise DSTIdentityError(
                    "compute_node_id: `unnumbered_ordinal` must be >= 0 "
                    f"(0-based ordinal position among unnumbered "
                    f"siblings); got {unnumbered_ordinal}."
                )
            disambiguator_component = f"{_UNNUMBERED_TAG}:{unnumbered_ordinal}"
        parent_component = parent_id.value

    payload = "|".join(
        [
            "dst-node-id",
            IDENTITY_SCHEME_VERSION.value,
            chapter_id.value,
            str(level.value),
            parent_component,
            disambiguator_component,
        ]
    )

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    # Chapter-scoped, human-traceable prefix + content hash. node_id is
    # only ever meaningful within chapter_id scope (§14's closing
    # note), so encoding chapter_id directly in the value costs
    # nothing and makes I3 (scope isolation) true by construction, not
    # merely improbable-by-hash-collision.
    return NodeId(f"{chapter_id.value}:{digest[:_DIGEST_SUFFIX_LENGTH]}")
