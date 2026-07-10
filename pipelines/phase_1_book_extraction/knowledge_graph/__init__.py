"""
knowledge_graph/ — Phase C0: Knowledge Graph Architecture Foundation.

This package is ARCHITECTURE ONLY as of Phase C0: base schemas
(schema.py), a base node model (node.py), a base edge model (edge.py),
a registry system reusing compiler.RegistryManager (registries.py), a
deterministic identity scheme (identity.py), validation contracts
(validation.py), a documented pipeline order (pipeline_architecture.py),
and state lifecycle plumbing (state.py) mirroring compiler/state.py's
own pattern. No node, no edge, and no populated KnowledgeGraph is ever
constructed anywhere in this package or called from anywhere else in
this codebase as of Phase C0 -- every set_current_*() function in
state.py, every id/urn builder in identity.py, and every dataclass in
schema.py exists but is never invoked/instantiated against real
Compiler IR data yet. See docs/knowledge_graph_architecture.md for the
full architecture writeup.

RELATIONSHIP TO compiler/: this package reads Compiler IR (a populated
compiler.RegistryManager, plus every Phase B artifact --
CompilerManifest, CompilerStatistics, ValidationReport,
CompilerReadinessReport, CompilerBuildSummary) and never writes back
into it -- see this package's own knowledge_graph/registries.py and
knowledge_graph/schema.py docstrings for exactly which compiler/ types
are reused vs. mirrored. compiler/ itself is completely untouched by
this package's existence: no file under compiler/ imports anything from
knowledge_graph/.

Usage (once a future C1+ phase exists -- none of this runs yet):

    from knowledge_graph import create_graph_registry_manager
    from knowledge_graph.identity import graph_id, graph_urn

    manager = create_graph_registry_manager()   # empty node/edge/metadata registries
    gid = graph_id("physics:ch3")
    gurn = graph_urn("physics:ch3")
"""
from .exceptions import (
    KnowledgeGraphError,
    GraphNodeError,
    GraphEdgeError,
    GraphRegistryError,
    UnknownGraphRegistryError,
    GraphValidationError,
    GraphIdentityError,
)
from .schema import (
    KNOWLEDGE_GRAPH_SCHEMA_VERSION,
    KnowledgeGraphMetadata,
    KnowledgeGraph,
    KnowledgeGraphManifest,
    KnowledgeGraphStatistics,
    KnowledgeGraphValidationReport,
    KnowledgeGraphReadinessReport,
    KnowledgeGraphBuildSummary,
    KnowledgeGraphState,
)
from .node import (
    NODE_SCHEMA_VERSION,
    FUTURE_NODE_TYPES,
    GraphNodeBase,
    is_known_future_node_type,
)
from .edge import (
    EDGE_SCHEMA_VERSION,
    FUTURE_EDGE_TYPES,
    GraphEdgeBase,
    is_known_future_edge_type,
)
from .identity import (
    IDENTITY_VERSION,
    URN_ROOT_NAMESPACE,
    KG_URN_NAMESPACE,
    GRAPH_ID_KINDS,
    FingerprintStrategy,
    KNOWLEDGE_GRAPH_FINGERPRINT_STRATEGY,
    slugify,
    graph_id,
    graph_urn,
    node_id,
    node_urn,
    edge_id,
    edge_urn,
    disambiguated_suffix,
)
from .registries import (
    GRAPH_REGISTRY_VERSION,
    NODE_REGISTRY_NAME,
    EDGE_REGISTRY_NAME,
    METADATA_REGISTRY_NAME,
    GRAPH_REGISTRY_NAMES,
    GraphRegistryManager,
    create_graph_registry_manager,
    get_graph_registry,
)
from .validation import (
    VALIDATION_CONTRACT_VERSION,
    NodeValidator,
    EdgeValidator,
    GraphValidator,
    IntegrityValidator,
    DeterminismValidator,
    ReadinessValidator,
)
from .pipeline_architecture import (
    PipelineStageSpec,
    PIPELINE_STAGES,
    stage_names_in_order,
)
from . import state as state

__all__ = [
    "KnowledgeGraphError",
    "GraphNodeError",
    "GraphEdgeError",
    "GraphRegistryError",
    "UnknownGraphRegistryError",
    "GraphValidationError",
    "GraphIdentityError",
    "KNOWLEDGE_GRAPH_SCHEMA_VERSION",
    "KnowledgeGraphMetadata",
    "KnowledgeGraph",
    "KnowledgeGraphManifest",
    "KnowledgeGraphStatistics",
    "KnowledgeGraphValidationReport",
    "KnowledgeGraphReadinessReport",
    "KnowledgeGraphBuildSummary",
    "KnowledgeGraphState",
    "NODE_SCHEMA_VERSION",
    "FUTURE_NODE_TYPES",
    "GraphNodeBase",
    "is_known_future_node_type",
    "EDGE_SCHEMA_VERSION",
    "FUTURE_EDGE_TYPES",
    "GraphEdgeBase",
    "is_known_future_edge_type",
    "IDENTITY_VERSION",
    "URN_ROOT_NAMESPACE",
    "KG_URN_NAMESPACE",
    "GRAPH_ID_KINDS",
    "FingerprintStrategy",
    "KNOWLEDGE_GRAPH_FINGERPRINT_STRATEGY",
    "slugify",
    "graph_id",
    "graph_urn",
    "node_id",
    "node_urn",
    "edge_id",
    "edge_urn",
    "disambiguated_suffix",
    "GRAPH_REGISTRY_VERSION",
    "NODE_REGISTRY_NAME",
    "EDGE_REGISTRY_NAME",
    "METADATA_REGISTRY_NAME",
    "GRAPH_REGISTRY_NAMES",
    "GraphRegistryManager",
    "create_graph_registry_manager",
    "get_graph_registry",
    "VALIDATION_CONTRACT_VERSION",
    "NodeValidator",
    "EdgeValidator",
    "GraphValidator",
    "IntegrityValidator",
    "DeterminismValidator",
    "ReadinessValidator",
    "PipelineStageSpec",
    "PIPELINE_STAGES",
    "stage_names_in_order",
    "state",
]