"""
knowledge_graph/build_nodes.py — Phase C1 Task 4: Node Builder.

SCOPE: this module is the ONLY place in this codebase that ever
constructs a real `GraphNodeBase` instance from real Compiler IR data.
Per Task 4 / Task 5, it does exactly four things and nothing else:

  1. Reads an already-populated `compiler.registry_manager.RegistryManager`
     (Compiler IR -- produced by Phase B, see `compiler/registries.py`'s
     `create_registry_manager()` / `populate_registries()`).
  2. Iterates every registry `compiler.registries.REGISTRY_NAMES` names,
     in that exact order, and every item within each registry, in that
     registry's own deterministic insertion order.
  3. Constructs exactly one concrete node (`knowledge_graph.nodes`) per
     item.
  4. Inserts every node into a `knowledge_graph.registries.GraphRegistryManager`'s
     `nodes` registry.

It never builds an edge, never touches the `edges` registry, never reads
or writes `compiler.relationships`, and never mutates the Compiler IR
`RegistryManager` or any item inside it (every field read below is read
only -- see `build_node()`).

ONE COMPILER OBJECT -> ONE NODE, NEVER DUPLICATED: a node's id is
deterministic (`knowledge_graph.identity.node_id(node_type,
compiler_object_id)` -- see that module), so the same compiler object
always produces the same node id. Duplicate prevention is not
reimplemented here: it is entirely inherited from
`compiler.registry.CanonicalRegistry.insert()` (via
`knowledge_graph.registries.create_graph_registry_manager()`'s own
`nodes` registry, whose `id_of` is `knowledge_graph.registries._node_id_of`
-- see that module), which already raises
`compiler.exceptions.DuplicateIdError` on a duplicate id. Since Compiler
IR itself already guarantees unique ids per item within one registry
(see `compiler/registries.py`'s own docstring), this only ever fires if
`build_knowledge_graph_nodes()` is run twice against the same
`GraphRegistryManager` without a fresh one in between -- exactly the
"never overwrite silently" behavior Task 1 asks for.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from compiler.registries import REGISTRY_NAMES
from compiler.registry_manager import RegistryManager

from . import identity
from .exceptions import GraphNodeError
from .node import GraphNodeBase
from .nodes import NODE_CLASSES
from .registries import GraphRegistryManager, NODE_REGISTRY_NAME, create_graph_registry_manager

# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
NODE_BUILDER_VERSION = "C1.0"


# --------------------------------------------------------------------------
# compiler registry name -> node type. Keys are exactly
# compiler.registries.REGISTRY_NAMES (asserted below); values are exactly
# knowledge_graph.nodes.NODE_CLASSES's own keys (also asserted below) --
# this dict is the one place that connects Compiler IR's own registry
# vocabulary to the Knowledge Graph's own node-type vocabulary.
# --------------------------------------------------------------------------
NODE_TYPE_BY_COMPILER_REGISTRY: Dict[str, str] = {
    "topics": "topic",
    "definitions": "definition",
    "concepts": "concept",
    "glossary": "glossary",
    "figures": "figure",
    "diagrams": "diagram",
    "tables": "table",
    "equations": "equation",
    "activities": "activity",
    "boxes": "box",
    "warnings": "warning",
    "notes": "note",
    "examples": "example",
}

assert set(NODE_TYPE_BY_COMPILER_REGISTRY) == set(REGISTRY_NAMES), (
    "NODE_TYPE_BY_COMPILER_REGISTRY must name exactly one node type per "
    "compiler.registries.REGISTRY_NAMES entry"
)
assert set(NODE_TYPE_BY_COMPILER_REGISTRY.values()) == set(NODE_CLASSES), (
    "NODE_TYPE_BY_COMPILER_REGISTRY's node types must exactly match "
    "knowledge_graph.nodes.NODE_CLASSES's own keys"
)


# --------------------------------------------------------------------------
# object_type -> which key on the source item dict carries its own
# human-readable label, if any -- see knowledge_graph/node.py's own
# `display_name` FIELD NOTES ("its own `name` for a Concept, `term` for
# a Definition/Glossary entry, `title` for a Figure/Diagram/Table/
# Activity/Box/Example, ..."). `None` means this object type has no such
# key on the item at all (equations -- see modules/canonical.py /
# pipeline.py's own equation-record construction, which never adds a
# "name"/"term"/"title" key) -- `display_name` is left `None` for those,
# exactly as node.py's own docstring already anticipates
# ("`Optional[str]`, not required: some wrapped object types ... may not
# have one").
# --------------------------------------------------------------------------
_DISPLAY_NAME_KEY_BY_NODE_TYPE: Dict[str, Optional[str]] = {
    "concept": "name",
    "definition": "term",
    "glossary": "term",
    "topic": "title",
    "figure": "title",
    "diagram": "title",
    "table": "title",
    "activity": "title",
    "example": "title",
    "box": "title",
    "warning": "title",
    "note": "title",
    "equation": None,
}


def _field(item: Any, key: str) -> Optional[Any]:
    """Reads `key` off `item` without caring whether `item` is a plain
    dict (the shape every Compiler IR item currently is) or an object
    exposing attributes -- same extractor contract
    `compiler/registry.py`'s own `_get()` already uses. Read-only: never
    assigns anything back onto `item`."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _display_name_of(item: Any, node_type: str) -> Optional[str]:
    key = _DISPLAY_NAME_KEY_BY_NODE_TYPE.get(node_type)
    if key is None:
        return None
    value = _field(item, key)
    return value if isinstance(value, str) and value else None


def build_node(
    item: Any,
    *,
    compiler_registry_name: str,
    graph_namespace: str,
) -> GraphNodeBase:
    """Builds exactly one concrete `GraphNodeBase` subclass instance
    wrapping `item` -- Task 1's "one compiler object -> one graph node",
    applied to a single item. Never mutates `item`. Raises
    `GraphNodeError` if `compiler_registry_name` isn't one of
    `NODE_TYPE_BY_COMPILER_REGISTRY`'s own keys, or if `item` is missing
    the `id`/`urn` every Compiler IR item is expected to already carry
    unconditionally (see `compiler/registries.py`'s own module
    docstring) -- both indicate a caller/upstream-data error, not a
    normal empty-registry case (see `build_knowledge_graph_nodes()`
    below for that)."""
    node_type = NODE_TYPE_BY_COMPILER_REGISTRY.get(compiler_registry_name)
    if node_type is None:
        raise GraphNodeError(
            f"knowledge_graph.build_nodes: {compiler_registry_name!r} is "
            "not a known compiler registry name -- see "
            "NODE_TYPE_BY_COMPILER_REGISTRY for the closed set this "
            "builder knows how to convert into nodes."
        )
    node_cls = NODE_CLASSES[node_type]

    compiler_object_id = _field(item, "id")
    compiler_object_urn = _field(item, "urn")
    if not compiler_object_id or not compiler_object_urn:
        raise GraphNodeError(
            f"knowledge_graph.build_nodes: cannot build a {node_type!r} "
            f"node from an item in the {compiler_registry_name!r} "
            "registry that is missing its own 'id' and/or 'urn' -- every "
            "Compiler IR item is expected to already carry both (see "
            "compiler/registries.py's module docstring)."
        )
    compiler_object_type = _field(item, "object_type") or node_type

    provenance = _field(item, "provenance")
    provenance = dict(provenance) if isinstance(provenance, dict) else None

    creation_metadata = _field(item, "creation_metadata")
    compiler_version = (
        creation_metadata.get("compiler_version")
        if isinstance(creation_metadata, dict)
        else None
    )

    return node_cls(
        node_id=identity.node_id(node_type, compiler_object_id),
        node_urn=identity.node_urn(graph_namespace, node_type, compiler_object_id),
        node_type=node_type,
        graph_id=identity.graph_id(graph_namespace),
        graph_urn=identity.graph_urn(graph_namespace),
        compiler_object_id=compiler_object_id,
        compiler_object_urn=compiler_object_urn,
        compiler_object_type=compiler_object_type,
        compiler_registry=compiler_registry_name,
        display_name=_display_name_of(item, node_type),
        provenance=provenance,
        compiler_version=compiler_version,
    )


def build_knowledge_graph_nodes(
    compiler_registry_manager: RegistryManager,
    *,
    graph_namespace: str,
    graph_registry_manager: Optional[GraphRegistryManager] = None,
) -> GraphRegistryManager:
    """Task 4's Node Builder entry point.

    Reads `compiler_registry_manager` (Compiler IR, already populated by
    Phase B -- see module docstring), iterates every registry named in
    `compiler.registries.REGISTRY_NAMES`, in that fixed order, and every
    item within each registry, in that registry's own deterministic
    insertion order (`CanonicalRegistry.values()`), builds exactly one
    node per item (`build_node()` above), and inserts every node into
    `graph_registry_manager`'s own `nodes` registry (a fresh one, via
    `create_graph_registry_manager()`, if none is given).

    A registry name in `compiler.registries.REGISTRY_NAMES` that
    `compiler_registry_manager` does not itself own (e.g. a
    deliberately-partial test fixture built by hand rather than
    `compiler.registries.create_registry_manager()`) is silently
    skipped, not an error -- mirrors
    `compiler.registries.populate_registries()`'s own "every argument is
    optional... partial population... is just as valid" contract, one
    layer up. An empty registry (size 0) contributes zero nodes, which
    is likewise not an error.

    Returns `graph_registry_manager` (or the freshly-created one) --
    always the SAME manager instance passed in, if one was, matching
    every other builder-style function in this codebase (e.g.
    `compiler.registries.populate_registries()`) returning the manager
    it was given rather than a copy.

    Inserts NOTHING into the `edges` or `metadata` registries -- after
    this function returns, `graph_registry_manager`'s `edges` registry
    is exactly as empty as `create_graph_registry_manager()` left it
    (Task 5's own "zero graph edges" requirement), and no metadata
    record is ever inserted (that is future C7 work, out of scope here
    -- see this package's own `pipeline_architecture.PIPELINE_STAGES`).
    """
    manager = graph_registry_manager if graph_registry_manager is not None \
        else create_graph_registry_manager()
    node_registry = manager.get(NODE_REGISTRY_NAME)

    for compiler_registry_name in REGISTRY_NAMES:
        if compiler_registry_name not in compiler_registry_manager:
            continue
        source_registry = compiler_registry_manager.get(compiler_registry_name)
        for item in source_registry.values():
            node = build_node(
                item,
                compiler_registry_name=compiler_registry_name,
                graph_namespace=graph_namespace,
            )
            node_registry.insert(node)

    return manager