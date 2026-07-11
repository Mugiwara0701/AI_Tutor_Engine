"""
dependency_graph/identity.py — Phase E2: Dependency Graph identity
architecture.

SCOPE: pure, deterministic id/urn STRING-BUILDER functions only --
exactly the same kind of thing knowledge_graph/identity.py already is
one package over (that module's own docstring: "small, pure,
general-purpose id/urn string-builder functions"). No new identity
mechanism is invented here: this reuses the same slugify() +
hierarchical-urn shape modules/pdf_parser.py's make_urn() and
knowledge_graph/identity.py both already establish, given its own urn
namespace segment (`dg`) so a Dependency Graph urn can never collide
with a Knowledge Graph urn (`kg`) or a Compiler IR urn even though all
three live under the same `ncert-kg` urn root.

NODE IDENTITY REUSES EXISTING NAMES, NOT NEW ONES: a dependency node's
identity is built from (node_type, artifact_key) where `artifact_key`
is always an already-existing, deterministic name this codebase
already defines elsewhere -- a compiler.registries.REGISTRY_NAMES
entry, a knowledge_graph.registries.GRAPH_REGISTRY_NAMES entry, or a
fixed stage name (e.g. "compiler_manifest") matching the artifact's
own already-established name in build_metadata/build.py /
compiler/build.py / knowledge_graph/build.py. This module never mints
a fresh, unrelated identifier for something another module already
names -- see this package's own module docstring, "Nodes must use
existing canonical identities whenever possible" (task's own
requirement).
"""
from __future__ import annotations

import re


# --------------------------------------------------------------------------
# Versioning
# --------------------------------------------------------------------------

# This identity scheme's own version marker -- independent of every
# other *_VERSION/*_IDENTITY_VERSION constant in this codebase. Bump
# only if the ID/URN SHAPE this module defines changes in a way that
# would make an old id/urn stop matching a new one for "the same"
# input.
DEPENDENCY_IDENTITY_VERSION = "E2.1"


# --------------------------------------------------------------------------
# Namespaces
# --------------------------------------------------------------------------

# Same top-level urn family Compiler IR and Knowledge Graph already
# use (see knowledge_graph/identity.py's own URN_ROOT_NAMESPACE), so
# every urn in this project -- Compiler IR, Knowledge Graph, or Build
# Dependency Graph -- shares one root, human-recognizable namespace.
URN_ROOT_NAMESPACE = "ncert-kg"

# The one segment that distinguishes a Dependency Graph urn from a
# Knowledge Graph urn (`kg`) or a bare Compiler IR urn under the same
# root namespace.
DG_URN_NAMESPACE = "dg"


# --------------------------------------------------------------------------
# Slugification -- same normalization rule knowledge_graph/identity.py's
# own slugify() already uses, duplicated in miniature here rather than
# importing knowledge_graph.identity (this package intentionally has no
# dependency on the Knowledge Graph layer -- Phase E2 must remain
# completely independent from educational semantics, see this
# package's own __init__.py docstring).
# --------------------------------------------------------------------------

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Deterministic, dependency-free slugification: lowercase, then
    collapse every run of non-alphanumeric characters to a single
    hyphen, trimmed. Same normalization contract as
    knowledge_graph/identity.py::slugify()."""
    slug = _SLUG_STRIP_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "item"


# --------------------------------------------------------------------------
# Graph identity
# --------------------------------------------------------------------------

def graph_id(namespace: str) -> str:
    """Deterministic Graph ID for one Dependency Graph build, scoped to
    `namespace` (expected shape: "<book_slug>:<chapter_slug>" -- the
    same `chapter_reference` value pipeline.py already threads into
    knowledge_graph.identity.graph_id() for this chapter's Knowledge
    Graph, reused here unchanged rather than a second, independently
    computed namespace). Pure string transform: given the same
    `namespace` twice, always returns the same id."""
    return f"dg-{slugify(namespace)}"


def graph_urn(namespace: str) -> str:
    """Deterministic Graph URN: `urn:ncert-kg:dg:<namespace-slug>`.
    Every node/edge urn in this graph is nested under this one (see
    node_urn()/edge_urn() below)."""
    return f"urn:{URN_ROOT_NAMESPACE}:{DG_URN_NAMESPACE}:{slugify(namespace)}"


# --------------------------------------------------------------------------
# Node identity
# --------------------------------------------------------------------------

def node_id(node_type: str, artifact_key: str) -> str:
    """Deterministic Node ID. Shape: "dgnode:<node-type-slug>:<artifact-
    key-slug>". `artifact_key` is always an already-existing name this
    codebase defines elsewhere (see module docstring's NODE IDENTITY
    REUSES EXISTING NAMES section) -- never a freshly minted id. Two
    independent runs over the same chapter always produce the same
    node id for the same (node_type, artifact_key) pair."""
    return f"dgnode:{slugify(node_type)}:{slugify(artifact_key)}"


def node_urn(graph_namespace: str, node_type: str, artifact_key: str) -> str:
    """Deterministic Node URN, nested under this build's graph_urn():
    `urn:ncert-kg:dg:<namespace>:node:<node-type-slug>:<artifact-key-slug>`.
    """
    return (
        f"{graph_urn(graph_namespace)}:node:{slugify(node_type)}:"
        f"{slugify(artifact_key)}"
    )


# --------------------------------------------------------------------------
# Edge identity
# --------------------------------------------------------------------------

def edge_id(edge_type: str, source_node_id: str, target_node_id: str) -> str:
    """Deterministic Edge ID, derived from its own type plus both
    endpoint node ids -- mirrors knowledge_graph/identity.py's own
    edge_id() precedent exactly, one layer over. Shape:
    "dgedge:<edge-type-slug>:<source-node-id>:<target-node-id>"."""
    return f"dgedge:{slugify(edge_type)}:{source_node_id}:{target_node_id}"


def edge_urn(
    graph_namespace: str, edge_type: str, source_node_id: str, target_node_id: str
) -> str:
    """Deterministic Edge URN, nested under this build's graph_urn()."""
    return (
        f"{graph_urn(graph_namespace)}:edge:{slugify(edge_type)}:"
        f"{source_node_id}:{target_node_id}"
    )