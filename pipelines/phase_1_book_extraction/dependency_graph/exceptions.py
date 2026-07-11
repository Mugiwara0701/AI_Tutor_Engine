"""
dependency_graph/exceptions.py — Phase E2: exception hierarchy for the
Build Dependency Graph layer.

Mirrors knowledge_graph/exceptions.py's own convention exactly, one
package over: small, specific exception classes so a caller can catch
precisely what it cares about instead of parsing free-text messages.
"""


class DependencyGraphError(Exception):
    """Base class for every error raised anywhere in the
    dependency_graph package. Mirrors
    knowledge_graph.exceptions.KnowledgeGraphError's role as the one
    catch-all ancestor for its own layer."""


class DependencyNodeError(DependencyGraphError):
    """Base class for node-related errors (invalid node, unknown node
    type, duplicate node id, ...)."""


class DependencyEdgeError(DependencyGraphError):
    """Base class for edge-related errors (invalid edge, unknown edge
    type, dangling endpoint, ...)."""


class DependencyRegistryError(DependencyGraphError):
    """Base class for dependency-registry-level errors. Deliberately
    does not duplicate compiler.exceptions.RegistryError's own
    duplicate-id/urn/name subclasses -- dependency_graph.registries
    reuses compiler.registry.CanonicalRegistry directly (see that
    module), so those specific errors are already raised as
    compiler.exceptions.DuplicateIdError / DuplicateUrnError /
    DuplicateNameError / ItemNotFoundError. This class exists for
    dependency-registry-manager-level errors that have no
    compiler-layer equivalent (e.g. an unknown dependency registry
    role)."""


class UnknownDependencyRegistryError(DependencyRegistryError):
    """Raised when a caller asks dependency_graph's registry manager
    for a registry role (e.g. "nodes", "edges") that isn't one of the
    roles DEPENDENCY_REGISTRY_NAMES declares."""

    def __init__(self, name: str):
        super().__init__(
            f"dependency_graph: {name!r} is not a known dependency "
            "registry role -- see "
            "dependency_graph.registries.DEPENDENCY_REGISTRY_NAMES for "
            "the closed set of valid names."
        )
        self.name = name


class DependencyIdentityError(DependencyGraphError):
    """Base class for identity-strategy errors (malformed graph/node/
    edge id or urn, namespace collision, ...)."""