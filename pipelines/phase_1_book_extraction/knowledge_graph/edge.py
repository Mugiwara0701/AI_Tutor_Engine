"""
knowledge_graph/edge.py — Phase C0 Task 3: Graph Edge Architecture.

SCOPE: this module defines ONLY the base model every future graph edge
type (contains, has_definition, explains, described_by, appears_in,
belongs_to, uses_concept, illustrates, teaches, Prerequisite, DependsOn,
RelatedTo, and others) will eventually inherit from. No concrete edge
type is defined here. No edge instance is ever constructed anywhere in
this codebase as of Phase C0. Mirrors knowledge_graph/node.py's own
relationship to future node types exactly -- see that module's docstring
for the parallel reasoning.

WHY EDGES REFERENCE NODE IDS, NOT CANONICAL OBJECT IDS: an edge connects
two GraphNodeBase instances (via their `node_id`s -- see node.py), never
two Compiler IR canonical objects directly. This is a deliberate layer
boundary: compiler/relationships.py's own `RelationshipRegistry` already
connects canonical objects directly (Compiler IR relationships), and
this module does not duplicate that -- a future C2/C3 edge-construction
phase is expected to read compiler/relationships.py's own relationships
registry as ONE INPUT toward deciding which graph edges to build, not to
be replaced by it. A graph edge is a graph-shaped edge between two graph
nodes; a Compiler IR relationship is a Symbol-Table-shaped link between
two canonical objects. Related concepts, different layers -- exactly the
same "wraps, does not replace" relationship node.py's own GraphNodeBase
has to a canonical object (see that module's docstring).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
EDGE_SCHEMA_VERSION = "C0.1"


# --------------------------------------------------------------------------
# Future edge types (Task 3's own list). Declared here as a closed-set-
# so-far constant, mirroring node.py's own FUTURE_NODE_TYPES precedent
# (and, further back, compiler/relationships.py's own RELATIONSHIP_TYPES
# list). NOT used to construct anything in Phase C0.
#
# Grouped, in comments only (the tuple itself is flat and unordered-
# significance-free, matching RELATIONSHIP_TYPES's own flat-list shape),
# by the two edge "families" the task's own list already implies:
#   - structural/compositional: contains, has_definition, appears_in,
#     belongs_to, described_by
#   - semantic/educational: explains, uses_concept, illustrates,
#     teaches, Prerequisite, DependsOn, RelatedTo
# This grouping is documentation only in Phase C0 -- no subclass or
# validation rule currently branches on it.
# --------------------------------------------------------------------------
FUTURE_EDGE_TYPES = (
    "contains",
    "has_definition",
    "explains",
    "described_by",
    "appears_in",
    "belongs_to",
    "uses_concept",
    "illustrates",
    "teaches",
    "prerequisite",
    "depends_on",
    "related_to",
)


@dataclass
class GraphEdgeBase:
    """Base model every future concrete graph edge type inherits from.

    Every future edge type (see FUTURE_EDGE_TYPES) is expected to
    subclass this dataclass and add only fields specific to that edge's
    own semantics -- mirrors GraphNodeBase's own "shared fields once"
    rationale (node.py). No subclass is defined in Phase C0.

    FIELD NOTES:
    - `edge_id` / `edge_urn`: built by
      knowledge_graph.identity.edge_id()/edge_urn() -- never
      hand-assigned.
    - `edge_type`: one of FUTURE_EDGE_TYPES once a concrete subclass
      exists; kept as a plain `str`, same additive-without-touching-the-
      base rationale as GraphNodeBase.node_type.
    - `source_node_id` / `target_node_id`: both GraphNodeBase.node_id
      values (this module's own node.py) -- an edge is ALWAYS
      node-to-node, never node-to-canonical-object or
      canonical-object-to-canonical-object (see module docstring's WHY
      EDGES REFERENCE NODE IDS section).
    - `directed`: whether this edge type is meaningfully directional
      (e.g. "Prerequisite" -- A is a prerequisite OF B, not symmetric)
      vs. symmetric (e.g. "RelatedTo"). Declared per-instance rather
      than inferred from `edge_type`, since a future concrete edge
      subclass owns that decision for its own type; this base field
      just gives every edge, of every future type, a place to record
      it uniformly.
    - `graph_id` / `graph_urn`: which Knowledge Graph build this edge
      belongs to (mirrors GraphNodeBase's own two fields of the same
      name/purpose).
    - `edge_schema_version`: this module's own EDGE_SCHEMA_VERSION,
      stamped per-instance.
    - `metadata`: open bag for edge-type-specific fields, same rationale
      as GraphNodeBase.metadata.
    """

    edge_id: str
    edge_urn: str
    edge_type: str
    graph_id: str
    graph_urn: str
    source_node_id: str
    target_node_id: str
    directed: bool = True
    edge_schema_version: str = EDGE_SCHEMA_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_known_future_edge_type(edge_type: str) -> bool:
    """Pure membership check against FUTURE_EDGE_TYPES -- provided so a
    future C2 edge builder can validate an edge type without
    duplicating this list. Does not construct or register anything."""
    return edge_type in FUTURE_EDGE_TYPES