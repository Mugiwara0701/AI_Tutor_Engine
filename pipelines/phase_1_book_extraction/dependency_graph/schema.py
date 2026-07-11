"""
dependency_graph/schema.py — Phase E2: Build Dependency Graph container.

SCOPE: `DependencyGraphMetadata` (graph-level identity/summary) and
`DependencyGraph` (the full container: metadata + every node + every
edge, in insertion order) -- mirrors knowledge_graph/schema.py's own
`KnowledgeGraphMetadata`/`KnowledgeGraph` relationship one package
over. Both are purely data holders; all construction happens in
build.py's `generate_dependency_graph()`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
DEPENDENCY_GRAPH_SCHEMA_VERSION = "E2.1"


@dataclass
class DependencyGraphMetadata:
    """Graph-level identity and summary for one chapter's Dependency
    Graph build.

    FIELD NOTES:
    - `graph_id` / `graph_urn`: built by
      dependency_graph.identity.graph_id()/graph_urn() -- never
      hand-assigned.
    - `namespace`: the same `chapter_reference`
      (`"<book_slug>:<chapter_slug>"`) already used to build this
      chapter's Knowledge Graph graph_id/graph_urn -- reused unchanged,
      never a second, independently computed namespace.
    - `generated_at`: wall-clock timestamp this DependencyGraph was
      assembled, matching every earlier Phase B5/C4/D/E1 artifact's own
      convention.
    - `dependency_graph_schema_version`: this module's own
      DEPENDENCY_GRAPH_SCHEMA_VERSION, stamped per-instance.
    - `node_count` / `edge_count`: the final size of the `nodes`/`edges`
      registries once build.py has finished populating them -- a
      direct read of DependencyRegistryManager.get(...).size(), never
      independently counted.
    """

    graph_id: str
    graph_urn: str
    namespace: str
    generated_at: str
    dependency_graph_schema_version: str
    node_count: int
    edge_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DependencyGraph:
    """The full Phase E2 artifact: this chapter's DependencyGraphMetadata
    plus every DependencyNode and DependencyEdge built for it, each
    already serialized (`.to_dict()`'d) in the owning registry's own
    deterministic insertion order -- the same "registry iteration order
    is the serialization order" guarantee compiler.registry.CanonicalRegistry
    and knowledge_graph.registries already provide."""

    metadata: Dict[str, Any]
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)