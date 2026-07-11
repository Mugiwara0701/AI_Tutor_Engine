"""
dependency_graph/edge.py — Phase E2: Dependency Edge.

SCOPE: `DependencyEdge` represents exactly one build-dependency
relationship between two DependencyNodes: "the artifact at
`source_node_id` could not have been built without the artifact at
`target_node_id` already existing." Never educational meaning of any
kind -- see this package's own __init__.py docstring.

WHY A SINGLE EDGE TYPE: the task's own examples ("A depends on B", "B
produces C", "C consumes D") all describe the same one underlying
relation looked at from either end. Rather than modeling "depends_on"
and its inverse "produces" as two edge types that would always appear
in matched pairs (pure, always-redundant duplication of the same fact),
this module defines exactly one directed edge type, `depends_on`:
`source_node_id` is the artifact that was built later and consumed the
other; `target_node_id` is the artifact it depended on. A "produces"
view, if ever needed, is just this same edge read tail-to-head -- no
second edge is required to express it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
DEPENDENCY_EDGE_SCHEMA_VERSION = "E2.1"


# --------------------------------------------------------------------------
# The closed set of dependency edge types Phase E2 defines. Deliberately
# a single entry -- see module docstring's WHY A SINGLE EDGE TYPE
# section.
# --------------------------------------------------------------------------
DEPENDENCY_EDGE_TYPES = ("depends_on",)


@dataclass
class DependencyEdge:
    """One Dependency Edge: `source_node_id` depends_on
    `target_node_id`. Purely a data holder; every instance is built by
    build.py's `_add_edge()` helper, never hand-constructed elsewhere.

    FIELD NOTES:
    - `edge_id` / `edge_urn`: built by
      dependency_graph.identity.edge_id()/edge_urn() -- never
      hand-assigned.
    - `edge_type`: always "depends_on" (see DEPENDENCY_EDGE_TYPES).
    - `source_node_id` / `target_node_id`: both DependencyNode.node_id
      values (node.py) -- an edge is always node-to-node, never
      node-to-raw-artifact-name.
    - `graph_id` / `graph_urn`: which Dependency Graph build this edge
      belongs to (mirrors DependencyNode's own two fields of the same
      name/purpose).
    - `dependency_edge_schema_version`: this module's own
      DEPENDENCY_EDGE_SCHEMA_VERSION, stamped per-instance.
    - `metadata`: open bag for edge-specific context, same rationale
      as DependencyNode.metadata.
    """

    edge_id: str
    edge_urn: str
    edge_type: str
    source_node_id: str
    target_node_id: str
    graph_id: str
    graph_urn: str
    directed: bool = True
    dependency_edge_schema_version: str = DEPENDENCY_EDGE_SCHEMA_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_known_dependency_edge_type(edge_type: str) -> bool:
    """Pure membership check against DEPENDENCY_EDGE_TYPES."""
    return edge_type in DEPENDENCY_EDGE_TYPES