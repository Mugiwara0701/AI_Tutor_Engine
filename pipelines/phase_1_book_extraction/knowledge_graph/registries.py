"""
knowledge_graph/registries.py — Phase C0 Task 4: Graph Registry
Architecture.

SCOPE: this module reuses compiler/registry.py's `CanonicalRegistry` and
compiler/registry_manager.py's `RegistryManager` DIRECTLY -- it does not
reimplement id/urn/name indexing, duplicate detection, or serialization
(Task 4's own "Reuse the RegistryManager design wherever appropriate" /
"Avoid duplicated infrastructure" instructions, and CanonicalRegistry's
own docstring already documents it as generic over any item type exposing
id/urn/name, which GraphNodeBase/GraphEdgeBase (node.py/edge.py) already
do via their `node_id`/`node_urn`/`edge_id`/`edge_urn` fields).

`create_graph_registry_manager()` below creates EMPTY named registries
only -- the exact same "plumbing exists, nothing is populated yet"
relationship compiler/registry_manager.py's own module docstring
describes for Phase B0 relative to Phase B1
(`compiler.registries.create_registry_manager()`/`populate_registries()`).
No node, no edge, and no metadata record is inserted into any registry
anywhere in this module or anywhere else in Phase C0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from compiler.registry import CanonicalRegistry
from compiler.registry_manager import RegistryManager

from .exceptions import UnknownGraphRegistryError
from .node import GraphNodeBase
from .edge import GraphEdgeBase


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
GRAPH_REGISTRY_VERSION = "C0.1"


# --------------------------------------------------------------------------
# The closed set of graph registry roles Phase C0 defines. Mirrors
# compiler/registries.py's own REGISTRY_NAMES precedent (one name per
# concrete registry a RegistryManager will own) -- kept intentionally
# small (role-level, not per-node-type) at C0, since per-node-type
# registries (a "concepts" node registry distinct from a "figures" node
# registry, mirroring compiler/registries.py's own per-type split) are a
# C1 population-time decision, not an architecture-time one. Nothing
# here prevents C1 from creating additional, more granular registries
# under this same manager later -- see GraphRegistryManager.create()
# below, inherited unchanged from RegistryManager.
# --------------------------------------------------------------------------
NODE_REGISTRY_NAME = "nodes"
EDGE_REGISTRY_NAME = "edges"
METADATA_REGISTRY_NAME = "metadata"

GRAPH_REGISTRY_NAMES = (NODE_REGISTRY_NAME, EDGE_REGISTRY_NAME, METADATA_REGISTRY_NAME)


# --------------------------------------------------------------------------
# Item-shape extractors for CanonicalRegistry -- GraphNodeBase/
# GraphEdgeBase already expose id_/urn_/name-shaped attributes
# (node_id/node_urn, edge_id/edge_urn), so these are thin adapters
# reusing CanonicalRegistry's existing `id_of`/`urn_of`/`name_of`
# extractor-callable seam (compiler/registry.py) rather than a new
# indexing mechanism.
# --------------------------------------------------------------------------

def _node_id_of(item: Any) -> Optional[str]:
    return getattr(item, "node_id", None) if not isinstance(item, dict) else item.get("node_id")


def _node_urn_of(item: Any) -> Optional[str]:
    return getattr(item, "node_urn", None) if not isinstance(item, dict) else item.get("node_urn")


def _edge_id_of(item: Any) -> Optional[str]:
    return getattr(item, "edge_id", None) if not isinstance(item, dict) else item.get("edge_id")


def _edge_urn_of(item: Any) -> Optional[str]:
    return getattr(item, "edge_urn", None) if not isinstance(item, dict) else item.get("edge_urn")


class GraphRegistryManager(RegistryManager):
    """The Knowledge Graph's own registry manager -- a thin, additive
    subclass of compiler.registry_manager.RegistryManager, exactly the
    same "reuse the generic base, add nothing but a role vocabulary"
    relationship compiler/registries.py's own per-type registries
    (ConceptRegistry, FigureRegistry, ...) have to
    compiler.registry.CanonicalRegistry at Phase B1. No method is
    overridden -- every RegistryManager method (create/get/statistics/
    serialize/...) is inherited unchanged. This subclass exists purely
    so a Knowledge Graph consumer has a distinctly-named type to type-
    hint against (`GraphRegistryManager`, not a bare `RegistryManager`
    that happens to hold graph data), the same reason
    knowledge_graph.exceptions.GraphRegistryError exists alongside
    compiler.exceptions.RegistryError rather than reusing it directly
    for graph-specific errors.
    """


def create_graph_registry_manager() -> GraphRegistryManager:
    """Creates a GraphRegistryManager with three EMPTY registries
    (`nodes`, `edges`, `metadata`) already created and ready for a
    future C1-C3 phase to populate -- the Knowledge Graph analogue of
    compiler.registries.create_registry_manager(). Populates nothing:
    every registry returned has size() == 0.

    `metadata` is a plain CanonicalRegistry too (not a special type) --
    at C0 it exists as a place a future phase MAY store small,
    graph-scoped auxiliary records (e.g. one KnowledgeGraphMetadata
    instance, keyed by its own graph_id) without inventing a fourth
    registry-shaped mechanism; whether it is actually used that way is
    a C1+ decision, not one this architecture phase makes for it."""
    manager = GraphRegistryManager()
    manager.create(NODE_REGISTRY_NAME, id_of=_node_id_of, urn_of=_node_urn_of)
    manager.create(EDGE_REGISTRY_NAME, id_of=_edge_id_of, urn_of=_edge_urn_of)
    manager.create(METADATA_REGISTRY_NAME)
    return manager


def get_graph_registry(manager: GraphRegistryManager, role: str) -> CanonicalRegistry[Any]:
    """Fetches one of the three known graph registry roles by name,
    raising knowledge_graph.exceptions.UnknownGraphRegistryError (rather
    than compiler.exceptions.ItemNotFoundError) for any role outside
    GRAPH_REGISTRY_NAMES -- a clearer error for a caller that passed a
    typo'd role name, before ever reaching RegistryManager.get()'s own
    lookup."""
    if role not in GRAPH_REGISTRY_NAMES:
        raise UnknownGraphRegistryError(role)
    return manager.get(role)