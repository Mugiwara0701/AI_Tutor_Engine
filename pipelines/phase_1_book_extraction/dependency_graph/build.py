"""
dependency_graph/build.py — Phase E2: Build Dependency Graph generation.

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C, Phase D, and Phase E1 (Build Metadata) are all frozen -- this
module does not redesign compiler/, knowledge_graph/, validation/, or
build_metadata/. It ONLY adds one more read-only pass that DESCRIBES
the build dependencies between artifacts those earlier, frozen phases
already produced -- it never generates, repairs, recomputes, or mutates
a single field anywhere in the Compiler IR, the Knowledge Graph, any
earlier report, Build Metadata, or Chapter JSON, and it never inserts
into, updates, or removes from any Compiler IR or Knowledge Graph
registry.

REUSE, DON'T RECOMPUTE: every artifact this module turns into a
DependencyNode is read from an argument already computed by Phase
B5.1-B5.3/C4.1-C4.3/D3/E1 by the time pipeline.py's own Phase E2
integration point runs (see pipeline.py's own comment at that call
site) -- this module performs no new validation, determinism, or
readiness checking of its own, and reads compiler.registries.
REGISTRY_NAMES / knowledge_graph.registries's own two graph-registry
role names as fixed vocabulary, never by touching the actual populated
RegistryManager/GraphRegistryManager instances.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Change Detection (E3), not Incremental Compilation (E4), not
Validation & Finalization (E5), not a Persistence Store, not an
Incremental Planner, not Dirty Object Detection, not a Minimal Rebuild
Planner, not a Build Cache, and not Dependency Validation -- this
module builds the graph and nothing else; no self-consistency check,
cycle check, or reachability check is performed on the graph it builds.

DEPENDENCY SHAPE: this module encodes exactly the data-flow shape the
task's own diagram describes, at the granularity that shape actually
exists as a build artifact in this codebase (see node.py's own
DEPENDENCY_NODE_TYPES docstring for why "Canonical Object" and
"Compiler Registry" collapse to one node family, and "Knowledge Graph
Node" / "Knowledge Graph Edge" to another):

    compiler_registry[R] (one per compiler.registries.REGISTRY_NAMES)
        -> compiler_manifest
        -> compiler_statistics
        -> compiler_fingerprints
        -> knowledge_graph_registry["nodes"]
    compiler_fingerprints -> compiler_readiness
    compiler_manifest, compiler_statistics, compiler_readiness
        -> compiler_build_summary

    knowledge_graph_registry["nodes"] -> knowledge_graph_registry["edges"]
    knowledge_graph_registry["nodes"], ["edges"]
        -> knowledge_graph_manifest
        -> knowledge_graph_statistics
        -> knowledge_graph_fingerprints
    knowledge_graph_fingerprints -> knowledge_graph_readiness
    knowledge_graph_manifest, knowledge_graph_statistics,
    knowledge_graph_readiness -> knowledge_graph_build_summary

    compiler_build_summary, knowledge_graph_build_summary
        -> release_readiness
    release_readiness, compiler_build_summary,
    knowledge_graph_build_summary -> build_metadata

Every edge above reads "the node on the right depends on (was built
using) the node(s) on the left" -- i.e. a DependencyEdge's
`source_node_id` is the right-hand (later, consuming) node and its
`target_node_id` is the left-hand (earlier, depended-on) node, per
edge.py's own directionality convention.

A node/edge is only ever added for an artifact that is actually present
this chapter (every artifact argument below is `Optional`, mirroring
build_metadata/build.py's own Optional handling) -- a chapter for which
an earlier phase produced nothing (e.g. `compiler_manifest is None`)
simply yields a smaller graph, never a fabricated placeholder node.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from compiler.registries import REGISTRY_NAMES

from . import identity
from .edge import DependencyEdge
from .node import DependencyNode
from .registries import (
    EDGE_REGISTRY_NAME,
    NODE_REGISTRY_NAME,
    DependencyRegistryManager,
    create_dependency_registry_manager,
)
from .schema import DependencyGraph, DependencyGraphMetadata

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase (see e.g. build_metadata/build.py's
# own BUILD_METADATA_VERSION). Bump only if the SHAPE this module
# produces itself changes in a way a consumer of `dependency_graph`
# should be able to detect.
DEPENDENCY_GRAPH_VERSION = "E2.1"

# The two Knowledge Graph registry roles this module builds a
# `knowledge_graph_registry` node for -- exactly
# knowledge_graph.registries.NODE_REGISTRY_NAME /
# knowledge_graph.registries.EDGE_REGISTRY_NAME's own values, duplicated
# here as plain string literals rather than imported, since this
# package intentionally has no dependency on knowledge_graph (Phase E2
# must remain completely independent from educational semantics -- see
# this package's own __init__.py docstring); these two names are build
# vocabulary, not educational content.
KNOWLEDGE_GRAPH_REGISTRY_ROLES = ("nodes", "edges")


@dataclass
class _GraphBuilder:
    """Small, private helper bundling the DependencyRegistryManager plus
    this build's own graph_id/graph_urn/namespace -- exists only to
    keep `_add_node()`/`_add_edge()` below from repeating the same four
    arguments at every call site. Never exposed outside this module."""

    manager: DependencyRegistryManager
    namespace: str
    graph_id: str
    graph_urn: str

    def add_node(
        self, node_type: str, artifact_key: str, display_name: Optional[str] = None
    ) -> str:
        """Builds one DependencyNode, inserts it into the `nodes`
        registry, and returns its node_id. Deterministic: the same
        (node_type, artifact_key) always yields the same node_id (see
        dependency_graph.identity.node_id()), so calling this twice for
        the same artifact within one graph raises
        compiler.exceptions.DuplicateIdError -- inherited from
        CanonicalRegistry.insert(), never reimplemented here."""
        nid = identity.node_id(node_type, artifact_key)
        node = DependencyNode(
            node_id=nid,
            node_urn=identity.node_urn(self.namespace, node_type, artifact_key),
            node_type=node_type,
            artifact_key=artifact_key,
            graph_id=self.graph_id,
            graph_urn=self.graph_urn,
            display_name=display_name,
        )
        self.manager.get(NODE_REGISTRY_NAME).insert(node)
        return nid

    def add_edge(self, source_node_id: str, target_node_id: str) -> str:
        """Builds one `depends_on` DependencyEdge (source_node_id
        depends on target_node_id) and inserts it into the `edges`
        registry. A no-op-safe caller pattern: `_edge_if()` below only
        calls this when both endpoints actually exist this chapter."""
        edge_type = "depends_on"
        eid = identity.edge_id(edge_type, source_node_id, target_node_id)
        edge = DependencyEdge(
            edge_id=eid,
            edge_urn=identity.edge_urn(
                self.namespace, edge_type, source_node_id, target_node_id
            ),
            edge_type=edge_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            graph_id=self.graph_id,
            graph_urn=self.graph_urn,
        )
        self.manager.get(EDGE_REGISTRY_NAME).insert(edge)
        return eid


def generate_dependency_graph(
    *,
    namespace: str,
    # Compiler-side (Phase B5.1-B5.3), already in scope in
    # pipeline.py's process_chapter() by the time E1 has already run.
    compiler_manifest: Optional[Dict[str, Any]],
    compiler_statistics: Optional[Dict[str, Any]],
    compiler_registry_fingerprints: Optional[Dict[str, str]],
    compiler_readiness_report: Optional[Dict[str, Any]],
    compiler_build_summary: Optional[Dict[str, Any]],
    # Knowledge-Graph-side (Phase C4.1-C4.3), already in scope.
    knowledge_graph_manifest: Optional[Dict[str, Any]],
    knowledge_graph_statistics: Optional[Dict[str, Any]],
    knowledge_graph_registry_fingerprints: Optional[Dict[str, str]],
    knowledge_graph_readiness_report: Optional[Dict[str, Any]],
    knowledge_graph_build_summary: Optional[Dict[str, Any]],
    # Release-side (Phase D3), already in scope.
    release_readiness_report: Optional[Dict[str, Any]],
    # Build-Metadata-side (Phase E1), already in scope.
    build_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase E2's single pipeline.py integration point (mirrors
    build_metadata.build.finalize_build_metadata()'s own "one
    aggregation call" shape, one layer up). Must run AFTER
    build_metadata.build.finalize_build_metadata() (so Build Metadata
    itself is available to depend on) and is the LAST artifact computed
    for this chapter before Chapter JSON is assembled -- see
    pipeline.py's own comment at the call site.

    Read-only over every argument, and performs no new analysis, no new
    validation, and no new fingerprinting -- see module docstring's
    opening SCOPE paragraph.

    Returns `{"dependency_graph": <dict>}`, ready to be handed to
    dependency_graph.state.set_current_dependency_graph() (this
    phase's own "store inside Dependency Graph State" requirement,
    mirroring build_metadata's own state-integration convention)."""
    gid = identity.graph_id(namespace)
    gurn = identity.graph_urn(namespace)
    manager = create_dependency_registry_manager()
    builder = _GraphBuilder(manager=manager, namespace=namespace, graph_id=gid, graph_urn=gurn)

    # -- compiler_registry nodes: one per REGISTRY_NAMES entry, only ---
    # when this chapter's Compiler IR actually exists (compiler_manifest
    # is the signal Phase B produced something for this chapter -- the
    # same "manifest presence means the phase ran" convention
    # build_metadata/build.py already relies on for its own Optional
    # handling).
    compiler_registry_node_ids: List[str] = []
    if compiler_manifest is not None:
        for registry_name in REGISTRY_NAMES:
            nid = builder.add_node(
                "compiler_registry", registry_name, display_name=registry_name
            )
            compiler_registry_node_ids.append(nid)

    # -- compiler_manifest / compiler_statistics / compiler_fingerprints
    manifest_node_id = _node_if(builder, "compiler_manifest", compiler_manifest, "compiler_manifest")
    statistics_node_id = _node_if(
        builder, "compiler_statistics", compiler_statistics, "compiler_statistics"
    )
    fingerprints_node_id = _node_if(
        builder,
        "compiler_fingerprints",
        compiler_registry_fingerprints,
        "compiler_fingerprints",
    )
    readiness_node_id = _node_if(
        builder, "compiler_readiness", compiler_readiness_report, "compiler_readiness"
    )
    build_summary_node_id = _node_if(
        builder, "compiler_build_summary", compiler_build_summary, "compiler_build_summary"
    )

    for source_id in (manifest_node_id, statistics_node_id, fingerprints_node_id):
        for target_id in compiler_registry_node_ids:
            _edge_if(builder, source_id, target_id)
    _edge_if(builder, readiness_node_id, fingerprints_node_id)
    for target_id in (manifest_node_id, statistics_node_id, readiness_node_id):
        _edge_if(builder, build_summary_node_id, target_id)

    # -- knowledge_graph_registry nodes: one per KNOWLEDGE_GRAPH_REGISTRY_
    # ROLES entry, only when this chapter's Knowledge Graph actually
    # exists (same "manifest presence" signal as the compiler side).
    kg_registry_node_ids: Dict[str, str] = {}
    if knowledge_graph_manifest is not None:
        for role in KNOWLEDGE_GRAPH_REGISTRY_ROLES:
            kg_registry_node_ids[role] = builder.add_node(
                "knowledge_graph_registry", role, display_name=role
            )
        # "nodes" registry depends on every compiler_registry (Knowledge
        # Graph nodes wrap Compiler IR canonical objects -- see
        # knowledge_graph/build_nodes.py's own module docstring);
        # "edges" registry depends on "nodes" (edges connect nodes).
        for target_id in compiler_registry_node_ids:
            _edge_if(builder, kg_registry_node_ids.get("nodes"), target_id)
        _edge_if(builder, kg_registry_node_ids.get("edges"), kg_registry_node_ids.get("nodes"))

    kg_manifest_node_id = _node_if(
        builder, "knowledge_graph_manifest", knowledge_graph_manifest, "knowledge_graph_manifest"
    )
    kg_statistics_node_id = _node_if(
        builder,
        "knowledge_graph_statistics",
        knowledge_graph_statistics,
        "knowledge_graph_statistics",
    )
    kg_fingerprints_node_id = _node_if(
        builder,
        "knowledge_graph_fingerprints",
        knowledge_graph_registry_fingerprints,
        "knowledge_graph_fingerprints",
    )
    kg_readiness_node_id = _node_if(
        builder,
        "knowledge_graph_readiness",
        knowledge_graph_readiness_report,
        "knowledge_graph_readiness",
    )
    kg_build_summary_node_id = _node_if(
        builder,
        "knowledge_graph_build_summary",
        knowledge_graph_build_summary,
        "knowledge_graph_build_summary",
    )

    for source_id in (kg_manifest_node_id, kg_statistics_node_id, kg_fingerprints_node_id):
        for target_id in kg_registry_node_ids.values():
            _edge_if(builder, source_id, target_id)
    _edge_if(builder, kg_readiness_node_id, kg_fingerprints_node_id)
    for target_id in (kg_manifest_node_id, kg_statistics_node_id, kg_readiness_node_id):
        _edge_if(builder, kg_build_summary_node_id, target_id)

    # -- release_readiness / build_metadata: the final, cross-cutting
    # convergence -- exactly the two inputs
    # build_metadata.build.finalize_build_metadata() itself already
    # aggregates (compiler_build_summary, knowledge_graph_build_summary,
    # release_status), reused here unchanged rather than re-derived.
    release_node_id = _node_if(
        builder, "release_readiness", release_readiness_report, "release_readiness"
    )
    for target_id in (build_summary_node_id, kg_build_summary_node_id):
        _edge_if(builder, release_node_id, target_id)

    build_metadata_node_id = _node_if(
        builder, "build_metadata", build_metadata, "build_metadata"
    )
    for target_id in (release_node_id, build_summary_node_id, kg_build_summary_node_id):
        _edge_if(builder, build_metadata_node_id, target_id)

    node_registry = manager.get(NODE_REGISTRY_NAME)
    edge_registry = manager.get(EDGE_REGISTRY_NAME)

    metadata = DependencyGraphMetadata(
        graph_id=gid,
        graph_urn=gurn,
        namespace=namespace,
        generated_at=datetime.now(timezone.utc).isoformat(),
        dependency_graph_schema_version=DEPENDENCY_GRAPH_VERSION,
        node_count=node_registry.size(),
        edge_count=edge_registry.size(),
    )
    graph = DependencyGraph(
        metadata=metadata.to_dict(),
        nodes=[item.to_dict() for item in node_registry.values()],
        edges=[item.to_dict() for item in edge_registry.values()],
    )
    return {"dependency_graph": graph.to_dict()}


# --------------------------------------------------------------------------
# Private helpers -- keep generate_dependency_graph() above readable by
# factoring out its two repeated "only if the artifact is actually
# present" guards.
# --------------------------------------------------------------------------

def _node_if(
    builder: _GraphBuilder,
    node_type: str,
    artifact: Optional[Any],
    artifact_key: str,
) -> Optional[str]:
    """Adds one `node_type` node keyed by `artifact_key` iff `artifact`
    is not None, else returns None. Centralizes the "reuse, don't
    fabricate" rule every call site in generate_dependency_graph()
    above follows: an artifact this chapter's build never produced
    never gets a node standing in for it."""
    if artifact is None:
        return None
    return builder.add_node(node_type, artifact_key, display_name=artifact_key)


def _edge_if(
    builder: _GraphBuilder, source_node_id: Optional[str], target_node_id: Optional[str]
) -> Optional[str]:
    """Adds one `depends_on` edge iff both endpoints actually exist this
    chapter (neither is None), else returns None -- keeps
    generate_dependency_graph() above from having to guard every single
    add_edge() call site by hand."""
    if source_node_id is None or target_node_id is None:
        return None
    return builder.add_edge(source_node_id, target_node_id)