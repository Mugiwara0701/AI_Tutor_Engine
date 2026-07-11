"""
dependency_graph/node.py — Phase E2: Dependency Node.

SCOPE: `DependencyNode` represents exactly one compiler artifact this
chapter's build actually produced -- a compiler registry, a Knowledge
Graph registry, a manifest, a statistics report, a fingerprint set, a
readiness report, a build summary, or Build Metadata itself. It is a
flat, single, concrete dataclass (unlike knowledge_graph/node.py's own
`GraphNodeBase`, which is a base class future concrete subclasses
inherit from) since Phase E2's node vocabulary is a small, fixed,
closed set (DEPENDENCY_NODE_TYPES below) known in full up front -- no
future per-artifact-type subclass is expected the way Knowledge Graph
node types are.

WHY A NODE CARRIES `artifact_key`, NOT A COMPILER-OBJECT POINTER: unlike
a Knowledge Graph node (which wraps one Compiler IR canonical object,
see knowledge_graph/node.py's own "WHY A NODE WRAPS" section), a
Dependency Node represents an entire ARTIFACT-TYPE-shaped build step
for this chapter (e.g. "the concepts registry", "the compiler
manifest"), not one educational item. `artifact_key` is that artifact's
own already-existing name (a compiler.registries.REGISTRY_NAMES entry,
a knowledge_graph.registries role, or a fixed stage name) -- see
dependency_graph/identity.py's own module docstring for why this reuses
existing names rather than minting new ones.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
DEPENDENCY_NODE_SCHEMA_VERSION = "E2.1"


# --------------------------------------------------------------------------
# The closed set of dependency node types Phase E2 defines. Two
# per-role families (one node per name in each list below) plus a
# fixed set of chapter-singleton stage nodes -- see build.py for
# exactly which of these get instantiated and why.
# --------------------------------------------------------------------------
DEPENDENCY_NODE_TYPES = (
    # Per compiler.registries.REGISTRY_NAMES entry -- represents both
    # "Canonical Object" and "Compiler Registry" from the task's own
    # dependency diagram as one artifact-stage node: in this codebase
    # a canonical object's only persisted, build-tracked form IS its
    # entry in its owning compiler registry (modules/canonical.py's
    # output is inserted directly into a registry by
    # compiler.registries.populate_registries() -- there is no
    # separate, independently-versioned "canonical object" build
    # artifact upstream of that registry to give its own node to).
    "compiler_registry",
    # Per knowledge_graph.registries role ("nodes", "edges") --
    # represents "Knowledge Graph Node" / "Knowledge Graph Edge" from
    # the same diagram, one artifact-stage node per role rather than
    # per individual graph node/edge (an entry per educational item
    # would duplicate Knowledge Graph content inside a graph that must
    # stay independent from educational semantics -- see this
    # package's own __init__.py docstring).
    "knowledge_graph_registry",
    # Chapter-singleton compiler-side stage artifacts.
    "compiler_manifest",
    "compiler_statistics",
    "compiler_fingerprints",
    "compiler_readiness",
    "compiler_build_summary",
    # Chapter-singleton Knowledge-Graph-side stage artifacts.
    "knowledge_graph_manifest",
    "knowledge_graph_statistics",
    "knowledge_graph_fingerprints",
    "knowledge_graph_readiness",
    "knowledge_graph_build_summary",
    # Chapter-singleton, cross-cutting stage artifacts.
    "release_readiness",
    "build_metadata",
)


@dataclass
class DependencyNode:
    """One Dependency Node: one compiler artifact this chapter's build
    actually produced. Purely a data holder; every instance is built
    by build.py's `_add_node()` helper, never hand-constructed
    elsewhere.

    FIELD NOTES:
    - `node_id` / `node_urn`: built by
      dependency_graph.identity.node_id()/node_urn() -- never
      hand-assigned.
    - `node_type`: one of DEPENDENCY_NODE_TYPES.
    - `artifact_key`: the already-existing name this node represents
      (see module docstring) -- e.g. "concepts" for a
      `compiler_registry` node, or "compiler_manifest" for the
      manifest singleton node.
    - `graph_id` / `graph_urn`: which Dependency Graph build (see
      schema.py's `DependencyGraphMetadata`) this node belongs to.
    - `display_name`: an optional, human-readable label (e.g. "Concept
      Registry"), purely for a future consumer's convenience -- never
      used for identity or lookup.
    - `dependency_node_schema_version`: this module's own
      DEPENDENCY_NODE_SCHEMA_VERSION, stamped per-instance.
    - `metadata`: an open bag for whatever small, denormalized context
      a node needs beyond the fields above (e.g. a status string read
      from the artifact it represents) -- never a second source of
      truth for anything the artifact itself already carries.
    """

    node_id: str
    node_urn: str
    node_type: str
    artifact_key: str
    graph_id: str
    graph_urn: str
    display_name: Optional[str] = None
    dependency_node_schema_version: str = DEPENDENCY_NODE_SCHEMA_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_known_dependency_node_type(node_type: str) -> bool:
    """Pure membership check against DEPENDENCY_NODE_TYPES."""
    return node_type in DEPENDENCY_NODE_TYPES