"""
dependency_graph/registries.py — Phase E2: Dependency Registry
Architecture.

SCOPE: this module reuses compiler/registry.py's `CanonicalRegistry` and
compiler/registry_manager.py's `RegistryManager` DIRECTLY -- it does not
reimplement id/urn indexing, duplicate detection, or serialization. This
is the exact same "reuse the generic base, add nothing but a role
vocabulary" relationship knowledge_graph/registries.py's own
`GraphRegistryManager` already has to the same base classes, one
package over (task's own "Follow the exact architectural conventions
already used by ... Do not invent a new registry architecture").

`create_dependency_registry_manager()` below creates two EMPTY named
registries -- `nodes` and `edges` -- ready for build.py to populate.
Nothing is inserted into either registry anywhere in this module.
"""
from __future__ import annotations

from typing import Any, Optional

from compiler.registry import CanonicalRegistry
from compiler.registry_manager import RegistryManager

from .exceptions import UnknownDependencyRegistryError


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
DEPENDENCY_REGISTRY_VERSION = "E2.1"


# --------------------------------------------------------------------------
# The closed set of dependency registry roles Phase E2 defines. Mirrors
# knowledge_graph/registries.py's own GRAPH_REGISTRY_NAMES precedent
# exactly (role-level, one registry per role). No `metadata` bucket is
# defined here (unlike knowledge_graph/registries.py's own third role)
# -- Phase E2's own graph-level metadata is DependencyGraphMetadata
# (schema.py), carried directly on the DependencyGraph container rather
# than stashed in a third, generic registry.
# --------------------------------------------------------------------------
NODE_REGISTRY_NAME = "nodes"
EDGE_REGISTRY_NAME = "edges"

DEPENDENCY_REGISTRY_NAMES = (NODE_REGISTRY_NAME, EDGE_REGISTRY_NAME)


# --------------------------------------------------------------------------
# Item-shape extractors for CanonicalRegistry -- DependencyNode/
# DependencyEdge already expose id/urn-shaped attributes (node_id/
# node_urn, edge_id/edge_urn), so these are thin adapters reusing
# CanonicalRegistry's existing `id_of`/`urn_of` extractor-callable seam,
# exactly mirroring knowledge_graph/registries.py's own
# `_node_id_of`/`_node_urn_of`/`_edge_id_of`/`_edge_urn_of` precedent.
# --------------------------------------------------------------------------

def _node_id_of(item: Any) -> Optional[str]:
    return getattr(item, "node_id", None) if not isinstance(item, dict) else item.get("node_id")


def _node_urn_of(item: Any) -> Optional[str]:
    return getattr(item, "node_urn", None) if not isinstance(item, dict) else item.get("node_urn")


def _edge_id_of(item: Any) -> Optional[str]:
    return getattr(item, "edge_id", None) if not isinstance(item, dict) else item.get("edge_id")


def _edge_urn_of(item: Any) -> Optional[str]:
    return getattr(item, "edge_urn", None) if not isinstance(item, dict) else item.get("edge_urn")


class DependencyRegistryManager(RegistryManager):
    """The Dependency Graph's own registry manager -- a thin, additive
    subclass of compiler.registry_manager.RegistryManager, exactly the
    same relationship knowledge_graph.registries.GraphRegistryManager
    already has to the same base class. No method is overridden --
    every RegistryManager method (create/get/statistics/serialize/...)
    is inherited unchanged. Exists purely so a Dependency Graph
    consumer has a distinctly-named type to type-hint against."""


def create_dependency_registry_manager() -> DependencyRegistryManager:
    """Creates a DependencyRegistryManager with two EMPTY registries
    (`nodes`, `edges`) already created and ready for build.py to
    populate -- the Dependency Graph analogue of
    knowledge_graph.registries.create_graph_registry_manager(). Populates
    nothing: both registries returned have size() == 0."""
    manager = DependencyRegistryManager()
    manager.create(NODE_REGISTRY_NAME, id_of=_node_id_of, urn_of=_node_urn_of)
    manager.create(EDGE_REGISTRY_NAME, id_of=_edge_id_of, urn_of=_edge_urn_of)
    return manager


def get_dependency_registry(
    manager: DependencyRegistryManager, role: str
) -> CanonicalRegistry[Any]:
    """Fetches one of the two known dependency registry roles by name,
    raising dependency_graph.exceptions.UnknownDependencyRegistryError
    (rather than compiler.exceptions.ItemNotFoundError) for any role
    outside DEPENDENCY_REGISTRY_NAMES -- a clearer error for a caller
    that passed a typo'd role name, before ever reaching
    RegistryManager.get()'s own lookup."""
    if role not in DEPENDENCY_REGISTRY_NAMES:
        raise UnknownDependencyRegistryError(role)
    return manager.get(role)