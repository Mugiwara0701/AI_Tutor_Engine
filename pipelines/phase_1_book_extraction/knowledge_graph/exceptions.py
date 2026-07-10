"""
knowledge_graph/exceptions.py — Phase C0: exception hierarchy for the
Knowledge Graph layer.

Mirrors compiler/exceptions.py's own convention in this project (small,
specific exception classes so callers can catch precisely what they care
about, instead of parsing free-text messages). Nothing in this module
raises yet -- these classes exist so C1+ construction code has a single,
already-designed place to raise from, exactly the same relationship
compiler/exceptions.py has to compiler/registry.py (defined at B0,
raised starting at B1).
"""


class KnowledgeGraphError(Exception):
    """Base class for every error raised anywhere in the knowledge_graph
    package. Mirrors compiler.exceptions.RegistryError's role as the one
    catch-all ancestor for its own layer."""


class GraphNodeError(KnowledgeGraphError):
    """Base class for node-related errors (invalid node, unknown node
    type, duplicate node id, ...). No subclass is raised yet -- node
    construction is a C1 concern (see docs/knowledge_graph_architecture.md).
    """


class GraphEdgeError(KnowledgeGraphError):
    """Base class for edge-related errors (invalid edge, unknown edge
    type, dangling endpoint, ...). No subclass is raised yet -- edge
    construction is a C2 concern."""


class GraphRegistryError(KnowledgeGraphError):
    """Base class for graph-registry-level errors. Deliberately does not
    duplicate compiler.exceptions.RegistryError's own duplicate-id/urn/
    name subclasses -- knowledge_graph.registries reuses
    compiler.registry.CanonicalRegistry directly (see that module), so
    those specific errors are already raised as
    compiler.exceptions.DuplicateIdError / DuplicateUrnError /
    DuplicateNameError / ItemNotFoundError. This class exists for
    graph-registry-manager-level errors that have no compiler-layer
    equivalent (e.g. an unknown graph registry role)."""


class UnknownGraphRegistryError(GraphRegistryError):
    """Raised when a caller asks knowledge_graph's graph registry
    manager for a registry role (e.g. "nodes", "edges") that isn't one
    of the roles GRAPH_REGISTRY_NAMES declares."""

    def __init__(self, name: str):
        super().__init__(
            f"knowledge_graph: {name!r} is not a known graph registry "
            "role -- see knowledge_graph.registries.GRAPH_REGISTRY_NAMES "
            "for the closed set of valid names."
        )
        self.name = name


class GraphValidationError(KnowledgeGraphError):
    """Base class for errors raised by a Graph Validation Contract
    implementation (knowledge_graph/validation.py). No concrete
    validator exists yet -- see that module's docstring."""


class GraphIdentityError(KnowledgeGraphError):
    """Base class for identity-strategy errors (malformed graph/node/edge
    id or urn, namespace collision, ...). Raised by
    knowledge_graph.identity's id/urn builder functions when given
    malformed input -- see that module."""