"""
knowledge_graph/identity.py — Phase C0 Task 5: Knowledge Graph identity
architecture.

SCOPE: this module ONLY defines the deterministic identity RULES the
Knowledge Graph will use once C1+ actually constructs nodes and edges.
It builds small, pure, general-purpose id/urn STRING-BUILDER functions
(the same kind of thing modules/pdf_parser.py's make_urn() already is,
and compiler/relationships.py's own `_relationship_id()` already is) --
functions that turn already-known components into a deterministic
string. It does NOT call any of these functions against real compiler
IR data anywhere in this codebase; no graph id, node id, or edge id is
ever actually generated for a real node/edge by Phase C0. That first
real call is C1/C2's job.

REUSE, DON'T INVENT: the urn scheme below is deliberately the same
hierarchical, slugified `make_urn()` shape already established in
modules/pdf_parser.py (`urn:<board_namespace>:<namespace>:<slug>:...`),
extended with one more, KG-specific namespace segment (`kg`) so a
Knowledge Graph urn can never collide with a Compiler IR urn even
though both ultimately live in the same `ncert-kg:` urn family. This is
the same "layer on top of slugify(), don't invent a second identity
mechanism" principle make_urn()'s own docstring already documents.

WHY A SEPARATE ID/URN NAMESPACE FROM COMPILER IR: a graph node wraps a
canonical object (e.g. a `Concept`) but is not that canonical object --
future milestones may need one canonical object to be represented by
more than one node role (e.g. a `Concept` contributing both a `Concept`
node and, later, a distinct `Prerequisite` framing), or a node with no
1:1 canonical-object counterpart at all (a synthetic grouping node).
Reusing a canonical object's own `id`/`urn` as a graph node's `id`/`urn`
would silently assume 1:1 forever. See NODE IDENTITY below for the
resolution: a node id is DERIVED FROM, but distinct from, the canonical
object id/urn it wraps.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional, Sequence


# --------------------------------------------------------------------------
# Versioning
# --------------------------------------------------------------------------

# This identity scheme's own version marker -- independent of
# KNOWLEDGE_GRAPH_VERSION (schema.py), independent of every compiler-side
# *_VERSION constant, and independent of config.SCHEMA_VERSION. Bump only
# if the ID/URN SHAPE this module defines changes in a way that would
# make an old id/urn stop matching a new one for "the same" input.
IDENTITY_VERSION = "C0.1"


# --------------------------------------------------------------------------
# Namespaces
# --------------------------------------------------------------------------

# Same top-level urn family Compiler IR already uses (see
# modules/pdf_parser.py::make_urn()'s own `board_namespace`), so every
# urn in this project -- Compiler IR or Knowledge Graph -- shares one
# root, human-recognizable as "this project's own urn space".
URN_ROOT_NAMESPACE = "ncert-kg"

# The one segment that distinguishes a Knowledge Graph urn from a
# Compiler IR urn under the same root namespace. Never used bare --
# always followed by a graph-scoped namespace (see graph_urn() below).
KG_URN_NAMESPACE = "kg"

# The closed set of graph-scoped id kinds this identity scheme
# currently defines. Extending this set (e.g. adding a new node/edge
# *category*, not a new node/edge *type* -- see node.py/edge.py for
# types) is additive; removing or renaming an existing entry is a
# breaking urn-shape change and must bump IDENTITY_VERSION.
GRAPH_ID_KINDS = ("graph", "node", "edge")


# --------------------------------------------------------------------------
# Slugification -- same normalization rule make_urn()/slugify() already
# use, duplicated in miniature here rather than importing
# modules/pdf_parser.py (this package intentionally has no dependency on
# the extraction-layer `modules` package -- only on `compiler` and
# `config`, per this task's "Knowledge Graph must consume Compiler IR"
# scope boundary).
# --------------------------------------------------------------------------

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Deterministic, dependency-free slugification: lowercase, then
    collapse every run of non-alphanumeric characters to a single
    hyphen, trimmed. Same normalization contract as
    modules/pdf_parser.py::slugify() (kept independent so this package
    has no import-time dependency on the extraction layer)."""
    slug = _SLUG_STRIP_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "item"


def _short_hash(*parts: str, length: int = 8) -> str:
    """A short, deterministic, content-derived disambiguator -- used
    only when slugified parts alone are not guaranteed unique (e.g. two
    nodes whose canonical-object names slugify identically). SHA-256,
    not SHA-1 like make_urn()'s own helper, since this is a fresh scheme
    (IDENTITY_VERSION) free to pick its own primitive; length=8 hex
    chars matches this scheme's own collision-budget choice, not
    make_urn()'s [:6]."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


# --------------------------------------------------------------------------
# Graph identity
# --------------------------------------------------------------------------

def graph_id(namespace: str) -> str:
    """Deterministic Graph ID for one Knowledge Graph build, scoped to
    `namespace` (expected shape: "<book_slug>:<chapter_slug>", the same
    shape Compiler IR's own `namespace` already takes in make_urn() --
    see module docstring). Pure string transform: given the same
    `namespace` twice, always returns the same id."""
    return f"kg-{slugify(namespace)}"


def graph_urn(namespace: str) -> str:
    """Deterministic Graph URN: `urn:ncert-kg:kg:<namespace-slug>`.
    Every node/edge urn in this graph is nested under this one (see
    node_urn()/edge_urn() below), the same "hierarchical, globally
    unique" property make_urn() already documents for Compiler IR."""
    return f"urn:{URN_ROOT_NAMESPACE}:{KG_URN_NAMESPACE}:{slugify(namespace)}"


# --------------------------------------------------------------------------
# Node identity
# --------------------------------------------------------------------------

def node_id(node_type: str, source_object_id: str) -> str:
    """Deterministic Node ID, derived from (never equal to) the
    canonical object id it wraps -- see module docstring's WHY A
    SEPARATE ID/URN NAMESPACE section for why this is a derivation, not
    a reuse. Shape: "node:<node-type-slug>:<source-object-id>". Two
    independent runs over the same canonical object, building the same
    node type, always produce the same node id (determinism); two
    different node types wrapping the same canonical object never
    collide (the node-type-slug prefix keeps them distinct)."""
    return f"node:{slugify(node_type)}:{source_object_id}"


def node_urn(graph_namespace: str, node_type: str, source_object_id: str) -> str:
    """Deterministic Node URN, nested under this build's graph_urn():
    `urn:ncert-kg:kg:<namespace>:node:<node-type-slug>:<source-object-id>`.
    """
    return f"{graph_urn(graph_namespace)}:node:{slugify(node_type)}:{source_object_id}"


# --------------------------------------------------------------------------
# Edge identity
# --------------------------------------------------------------------------

def edge_id(edge_type: str, source_node_id: str, target_node_id: str) -> str:
    """Deterministic Edge ID, derived from its own type plus both
    endpoint node ids -- mirrors compiler/relationships.py's own
    `_relationship_id()` precedent (a relationship's id is derived from
    its type + both endpoint ids, never a fresh random id), extended one
    level: a Knowledge Graph edge's *endpoints* are node ids (this
    module's own node_id() output), not raw canonical-object ids like a
    Compiler IR relationship's endpoints are. Shape:
    "edge:<edge-type-slug>:<source-node-id>:<target-node-id>"."""
    return f"edge:{slugify(edge_type)}:{source_node_id}:{target_node_id}"


def edge_urn(
    graph_namespace: str, edge_type: str, source_node_id: str, target_node_id: str
) -> str:
    """Deterministic Edge URN, nested under this build's graph_urn()."""
    return (
        f"{graph_urn(graph_namespace)}:edge:{slugify(edge_type)}:"
        f"{source_node_id}:{target_node_id}"
    )


# --------------------------------------------------------------------------
# Disambiguation helper -- available to C1+ node/edge construction for
# the rare case two distinct source items slugify to the same node_type
# + source_object_id (e.g. object ids that differ only by characters
# slugify() strips). Defined here (identity architecture) but not
# invoked anywhere in Phase C0.
# --------------------------------------------------------------------------

def disambiguated_suffix(*parts: str) -> str:
    """An 8-hex-char, content-derived suffix a C1+ node/edge builder MAY
    append to node_id()/edge_id() output if it detects a same-id
    collision between two otherwise-distinct items. Not applied by
    default (node_id()/edge_id() above never call this) -- collision
    handling policy (raise vs. disambiguate) is a C1/C2 decision, this
    module only provides the deterministic primitive either policy would
    need."""
    return _short_hash(*parts)


# --------------------------------------------------------------------------
# Fingerprint strategy (Task 5's own "Do NOT generate any fingerprints"
# item) -- documented here as data, not as a callable. Mirrors
# compiler/fingerprints.py's own strategy (canonical-JSON + sha256 +
# strip-volatile-fields-first) closely enough that C-phase fingerprint
# generation can reuse that module's helpers directly rather than
# reinventing them; this dataclass exists only to name and freeze the
# *strategy decision* now, before any fingerprint is ever computed.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FingerprintStrategy:
    """Describes HOW a future Knowledge Graph fingerprint pass (not part
    of Phase C0) will compute fingerprints, without computing one
    itself. Purely declarative -- no method on this class produces a
    hash."""

    algorithm: str = "sha256"
    # Mirrors compiler/fingerprints.py's own _canonical_json(): sort
    # keys, no incidental whitespace, so two structurally-identical
    # graphs always canonicalize identically regardless of dict
    # insertion order.
    canonicalization: str = "sorted-key JSON, no whitespace"
    # Fields a future fingerprint pass must strip before hashing --
    # exactly the same "volatile field" concept
    # compiler/fingerprints.py::_strip_volatile() already applies to
    # Compiler IR (timestamps, memory-size-derived counts, etc.).
    volatile_fields: Sequence[str] = ("generated_at",)
    # What gets fingerprinted individually vs. as one whole -- mirrors
    # compiler/fingerprints.py's own two-level strategy (one fingerprint
    # per registry, plus one overall compiler fingerprint).
    granularity: str = "one fingerprint per node/edge registry, plus one overall graph fingerprint"


# The one strategy instance this identity scheme currently specifies.
# Frozen/constant -- not mutated, not used to compute anything in Phase
# C0. A future fingerprint-generating module (mirrors
# compiler/fingerprints.py's own relationship to compiler/build.py) is
# expected to import this constant rather than re-deciding these
# choices.
KNOWLEDGE_GRAPH_FINGERPRINT_STRATEGY = FingerprintStrategy()