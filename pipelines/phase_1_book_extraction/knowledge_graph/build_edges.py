"""
knowledge_graph/build_edges.py — Phase C2 Task 2: Edge Builder.

SCOPE: this module is the ONLY place in this codebase that ever
constructs a real `GraphEdgeBase` instance from real data. Per Task 2 /
Task 3, it does exactly four things and nothing else:

  1. Reads an already-populated `compiler.relationships.RelationshipRegistry`
     (Phase B3 Compiler IR -- produced by `compiler.relationships.
     resolve_relationships()`), owned by the same
     `compiler.registry_manager.RegistryManager` Phase C1's Node Builder
     already read.
  2. For each relationship, resolves the source node and the target node
     already sitting in the Knowledge Graph `nodes` registry (Phase C1
     output -- `knowledge_graph.build_nodes.build_knowledge_graph_nodes()`),
     by recomputing each endpoint's deterministic node id
     (`knowledge_graph.identity.node_id()`) from the relationship's own
     `source_type`/`source_id` and `target_type`/`target_id` fields and
     looking it up -- never by guessing, never by re-deriving from
     anything other than the relationship's own already-resolved fields.
  3. Constructs exactly one concrete edge (`knowledge_graph.edges`) per
     relationship.
  4. Inserts every edge into a `knowledge_graph.registries.GraphRegistryManager`'s
     `edges` registry.

It never touches the `nodes` or `metadata` registries beyond reading
`nodes` for lookups, never re-derives a relationship (that is entirely
Phase B3's job -- see compiler/relationships.py), never performs
semantic inference, and never mutates the Compiler IR `RegistryManager`,
the Compiler Relationship Registry, or the Knowledge Graph `nodes`
registry (every read below is read-only -- see `build_edge()`).

ONE COMPILER RELATIONSHIP -> ONE GRAPH EDGE, NEVER DUPLICATED: an edge's
id is deterministic (`knowledge_graph.identity.edge_id(edge_type,
source_node_id, target_node_id)` -- see that module), so the same
relationship always produces the same edge id. Duplicate prevention is
not reimplemented here: it is entirely inherited from
`compiler.registry.CanonicalRegistry.insert()` (via
`knowledge_graph.registries.create_graph_registry_manager()`'s own
`edges` registry, whose `id_of` is `knowledge_graph.registries._edge_id_of`
-- see that module), which already raises
`compiler.exceptions.DuplicateIdError` on a duplicate id -- the exact
same "never overwrite silently" behavior
`knowledge_graph.build_nodes`'s own module docstring already documents
for nodes, one layer up. Since `compiler.relationships.resolve_relationships()`
already guarantees unique relationship ids (see that module's own
`_insert_unique`), this only ever fires if `build_knowledge_graph_edges()`
is run twice against the same `GraphRegistryManager` without a fresh one
in between.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from compiler.registry_manager import RegistryManager
from compiler.relationships import RELATIONSHIP_REGISTRY_NAME

from . import identity
from .edge import GraphEdgeBase
from .edges import EDGE_CLASSES
from .exceptions import GraphEdgeError
from .registries import EDGE_REGISTRY_NAME, NODE_REGISTRY_NAME, GraphRegistryManager

# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
EDGE_BUILDER_VERSION = "C2.0"


# --------------------------------------------------------------------------
# compiler-relationship object-type label -> Knowledge Graph node type.
# `compiler.relationships.py`'s own `_make_relationship()` callers stamp
# each relationship's `source_type`/`target_type` with one of these nine
# labels (see that module's per-relationship-type generators); the
# Knowledge Graph's own node-type vocabulary
# (`knowledge_graph.node.FUTURE_NODE_TYPES`,
# `knowledge_graph.build_nodes.NODE_TYPE_BY_COMPILER_REGISTRY`'s own
# values) spells one of them differently ("glossary", not
# "glossary_entry" -- see knowledge_graph/nodes.py's `GlossaryNode`).
# This is the one place that reconciles the two vocabularies -- every
# other label below is already spelled identically in both.
# --------------------------------------------------------------------------
_NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE: Dict[str, str] = {
    "topic": "topic",
    "concept": "concept",
    "definition": "definition",
    "glossary_entry": "glossary",
    "equation": "equation",
    "figure": "figure",
    "diagram": "diagram",
    "table": "table",
    "activity": "activity",
}


def _resolve_node_id(object_type: str, object_id: str) -> Optional[str]:
    """Recomputes the deterministic node id (knowledge_graph.identity.
    node_id()) a relationship endpoint's own (`object_type`, `object_id`)
    pair would have been given by Phase C1's Node Builder. Returns
    `None` if `object_type` is not one of the nine relationship
    object-type labels this builder knows how to translate -- never
    guesses a node type."""
    node_type = _NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE.get(object_type)
    if node_type is None:
        return None
    return identity.node_id(node_type, object_id)


def build_edge(
    relationship: Dict[str, Any],
    *,
    node_registry: Any,
    graph_namespace: str,
) -> GraphEdgeBase:
    """Builds exactly one concrete `GraphEdgeBase` subclass instance
    wrapping `relationship` -- Task 3's "one compiler relationship -> one
    graph edge", applied to a single relationship. Never mutates
    `relationship` or `node_registry`. Raises `GraphEdgeError` if:

      * `relationship["type"]` isn't one of `knowledge_graph.edges.
        EDGE_CLASSES`'s own keys (i.e. not one of the nine deterministic
        types Phase B3 currently produces -- see that module's own "WHY
        ONLY NINE CLASSES" docstring section);
      * `relationship["source_type"]`/`relationship["target_type"]`
        isn't one of `_NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE`'s own keys;
      * the source or target node this relationship points at is not
        actually present in `node_registry` (a dangling reference --
        should never happen against a `node_registry` Phase C1 already
        fully populated from the SAME Compiler IR this relationship was
        resolved against, so this indicates a caller/upstream-data
        error, not a normal case -- mirrors `knowledge_graph.build_nodes.
        build_node()`'s own treatment of a missing id/urn).

    Every one of these is a refusal to guess, matching this phase's own
    "Never infer new edges" requirement -- this function never
    constructs an edge with a fabricated or best-guess endpoint.
    """
    rel_type = relationship.get("type")
    edge_cls = EDGE_CLASSES.get(rel_type)
    if edge_cls is None:
        raise GraphEdgeError(
            f"knowledge_graph.build_edges: {rel_type!r} is not a known "
            "deterministic edge type -- see knowledge_graph.edges."
            "EDGE_CLASSES for the closed set this builder knows how to "
            "convert into graph edges."
        )

    relationship_id = relationship.get("id")
    source_type = relationship.get("source_type")
    source_id = relationship.get("source_id")
    target_type = relationship.get("target_type")
    target_id = relationship.get("target_id")
    if not relationship_id or not source_id or not target_id:
        raise GraphEdgeError(
            "knowledge_graph.build_edges: cannot build an edge from a "
            "relationship missing its own 'id', 'source_id', and/or "
            "'target_id' -- every Compiler IR relationship is expected "
            "to already carry all three (see "
            "compiler/relationships.py's module docstring)."
        )

    source_node_id = _resolve_node_id(source_type, source_id)
    target_node_id = _resolve_node_id(target_type, target_id)
    if source_node_id is None or target_node_id is None:
        raise GraphEdgeError(
            f"knowledge_graph.build_edges: relationship {relationship_id!r} "
            f"has an unrecognized source_type/target_type "
            f"({source_type!r}/{target_type!r}) -- see "
            "_NODE_TYPE_BY_RELATIONSHIP_OBJECT_TYPE for the closed set "
            "this builder knows how to translate into a node type."
        )

    if node_registry.get_by_id(source_node_id) is None:
        raise GraphEdgeError(
            f"knowledge_graph.build_edges: relationship {relationship_id!r} "
            f"points at a source node ({source_node_id!r}) that does not "
            "exist in the Knowledge Graph node registry -- Phase C1 must "
            "run, against the same Compiler IR, before Phase C2."
        )
    if node_registry.get_by_id(target_node_id) is None:
        raise GraphEdgeError(
            f"knowledge_graph.build_edges: relationship {relationship_id!r} "
            f"points at a target node ({target_node_id!r}) that does not "
            "exist in the Knowledge Graph node registry -- Phase C1 must "
            "run, against the same Compiler IR, before Phase C2."
        )

    return edge_cls(
        edge_id=identity.edge_id(rel_type, source_node_id, target_node_id),
        edge_urn=identity.edge_urn(
            graph_namespace, rel_type, source_node_id, target_node_id
        ),
        edge_type=rel_type,
        graph_id=identity.graph_id(graph_namespace),
        graph_urn=identity.graph_urn(graph_namespace),
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        metadata={"compiler_relationship_id": relationship_id},
    )


def build_knowledge_graph_edges(
    compiler_registry_manager: RegistryManager,
    graph_registry_manager: GraphRegistryManager,
    *,
    graph_namespace: str,
) -> GraphRegistryManager:
    """Task 2/5's Edge Builder entry point.

    Reads `compiler_registry_manager`'s own `relationships` registry
    (Phase B3 Compiler IR -- see module docstring) and
    `graph_registry_manager`'s own already-populated `nodes` registry
    (Phase C1 output -- `knowledge_graph.build_nodes.
    build_knowledge_graph_nodes()` must already have been run against
    the SAME `compiler_registry_manager`, into this SAME
    `graph_registry_manager`, before this function is called), builds
    exactly one edge per relationship, in that registry's own
    deterministic insertion order (`CanonicalRegistry.values()`), and
    inserts every edge into `graph_registry_manager`'s own `edges`
    registry.

    Unlike `build_knowledge_graph_nodes()`, `graph_registry_manager` is
    REQUIRED, not optional: edges reference nodes that must already
    exist, so building against a fresh, empty manager would always fail
    -- this function is only ever meaningfully called with the same
    manager `build_knowledge_graph_nodes()` already populated.

    A `compiler_registry_manager` that does not itself own a
    `relationships` registry (e.g. a deliberately-partial test fixture)
    is silently treated as zero relationships, not an error -- mirrors
    `knowledge_graph.build_nodes.build_knowledge_graph_nodes()`'s own
    "a registry name it does not itself own... is silently skipped, not
    an error" contract, one relationship type up. An empty
    `relationships` registry (size 0) likewise contributes zero edges.

    Returns `graph_registry_manager` -- always the SAME manager instance
    passed in, matching `build_knowledge_graph_nodes()`'s own
    "returns... the SAME manager instance passed in" contract.

    Inserts NOTHING into the `nodes` or `metadata` registries -- after
    this function returns, `graph_registry_manager`'s `nodes` registry
    is exactly as `build_knowledge_graph_nodes()` already left it, and
    no metadata record is ever inserted (future C7 work, out of scope
    here -- see this package's own
    `pipeline_architecture.PIPELINE_STAGES`).
    """
    edge_registry = graph_registry_manager.get(EDGE_REGISTRY_NAME)
    node_registry = graph_registry_manager.get(NODE_REGISTRY_NAME)

    if RELATIONSHIP_REGISTRY_NAME not in compiler_registry_manager:
        return graph_registry_manager

    relationship_registry = compiler_registry_manager.get(RELATIONSHIP_REGISTRY_NAME)
    for relationship in relationship_registry.values():
        edge = build_edge(
            relationship,
            node_registry=node_registry,
            graph_namespace=graph_namespace,
        )
        edge_registry.insert(edge)

    return graph_registry_manager