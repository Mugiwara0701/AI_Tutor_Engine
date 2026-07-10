"""
knowledge_graph/build.py — Phase C4.1: Knowledge Graph Manifest &
Statistics.

SCOPE (read this before touching anything else): Phase A, Phase B, Phase
C0, Phase C1, Phase C2, and Phase C3 are frozen -- this module does not
redesign GraphRegistryManager (knowledge_graph/registries.py),
knowledge_graph/state.py's existing _CURRENT_* lifecycle,
knowledge_graph/node.py, knowledge_graph/edge.py, knowledge_graph/
build_nodes.py, knowledge_graph/build_edges.py, or knowledge_graph/
validation.py. It also does not touch compiler/* or json_writer.py /
schemas/chapter_schema.py / ChapterJSON. It ONLY adds a fourth,
read-only Knowledge Graph pass that DESCRIBES the graph build Phases
C1-C3 already produced -- a manifest and a statistics report -- by
reading fields those earlier, frozen phases already computed. It never
generates, repairs, or mutates a single node, edge, or Compiler IR
field.

This module is the direct Knowledge Graph analogue of compiler/build.py
(Phase B5.1) -- same two-artifact split, same "reuse, don't recompute"
discipline, same manifest-vs-statistics field distinction, applied one
layer up. Where compiler/build.py reads compiler.validation.
validate_compiler_state()'s own already-computed report, this module
reads knowledge_graph.validation.validate_knowledge_graph()'s own
already-computed report (Phase C3) -- never a second scan of the node/
edge registries for anything C3 already counted.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Graph Fingerprints, not Graph Readiness, not a Graph Build Summary, not
a Graph Final Status, not Graph Queries, not Graph Indexes, not Graph
Traversal, not any other Graph Algorithm, not Graph Optimization, and
not Graph Caching. It does not decide whether the graph is "ready" for
anything later -- it only reports what already happened. Every
fingerprint-shaped or readiness-shaped judgment is deliberately left
out, mirroring compiler/build.py's own "COMPILER_STATUS FIELDS" note one
layer down: `graph_status`/`graph_generation_status` below report only
that MANIFEST GENERATION ITSELF completed, never a readiness or
correctness verdict about the graph as a whole (that correctness
verdict is Phase C3's `validation_report["overall_status"]`, already
computed and simply carried forward here, never re-derived; the
still-future readiness verdict is Phase C4.2's job, not this module's).

REUSE, DON'T RECOMPUTE: every node/edge count and every by-type
breakdown below is read directly from `validation_report` -- the exact
dict `knowledge_graph.validation.validate_knowledge_graph()` (Phase C3)
already returned this chapter (`validation_report["node_summary"]`,
`["edge_summary"]`, `["registry_summary"]`, `["validation_statistics"]`)
-- never by a second call to `.ids()`/`.values()` over the node/edge
registries for anything C3 already counted. The one count this module
computes that C3's own report does not already carry -- how many nodes
came from each COMPILER registry (`nodes_by_source_registry`, Task 4's
own "source registry counts" bullet, distinct from Task 4's separate
"source registry counts" meaning "how big is the node/edge registry
itself", which IS already in `registry_summary["registry_sizes"]`) --
is derived by one single, bounded pass over the node registry's own
`.values()`, reading each node's already-stamped `compiler_registry`
field (knowledge_graph/node.py) -- not a rescan of Compiler IR, not a
second validation pass, and the only place in this module that touches
node/edge registry contents directly rather than reading a Phase C3
summary.

MANIFEST vs STATISTICS (mirrors compiler/build.py's own split exactly):
`generate_knowledge_graph_manifest()` (Task 3) produces a small,
fixed-shape identity/versioning record for this graph build (graph_id,
graph_urn, graph_schema_version, identity_version, source_chapter_
identifier, node_registry_versions, node_count, edge_count,
node_type_counts, edge_type_counts, graph_status, graph_generation_
status). `generate_knowledge_graph_statistics()` (Task 4) produces the
larger, descriptive breakdown (registry sizes, edges by type, total
nodes, total edges, nodes by source compiler registry, validation
summary). Both are plain dicts, matching every earlier Knowledge Graph
artifact's own "plain, storable dict" convention (see
knowledge_graph/validation.py's own KnowledgeGraphValidationReport.
to_dict() precedent).

NO SCHEMA REDESIGN: `KnowledgeGraphManifest`/`KnowledgeGraphStatistics`
(knowledge_graph/schema.py, Phase C0) are reused exactly as declared --
no field added, renamed, or removed. Task 3's own example field list
includes "compiler_version", which has no dedicated field on
KnowledgeGraphManifest (that schema instead carries a `node_registry_
versions: Dict[str, str]` pass-name -> version-marker map, the direct
analogue of CompilerManifest's own `registry_versions` field) --
`KnowledgeGraphMetadata.source_compiler_version` (already carried on the
`KnowledgeGraph` object Phase C1 builds, read-only here) is folded into
that existing dict under the key `"source_compiler"` rather than adding
a new top-level field for it, exactly the kind of "reuse the existing
shape" choice Task 1 asks for.

PIPELINE INTEGRATION: generate_knowledge_graph_manifest() is the one
pipeline.py integration point (mirrors validate_knowledge_graph()'s own
shape one phase down). It must run AFTER knowledge_graph.validation.
validate_knowledge_graph() (Phase C3, so there is a validation report to
read counts/summaries from) and is otherwise independent of Compiler
State finalization -- see pipeline.py's own comment at the call site.
The manifest and statistics are handed to knowledge_graph.state.
set_current_knowledge_graph_manifest()/set_current_knowledge_graph_
statistics() immediately after (Task 5), making them "part of Knowledge
Graph State" per the task spec, WITHOUT writing either into ChapterJSON
or mutating `graph_registry_manager`/`graph_metadata` themselves.

DETERMINISM: every field below is either read verbatim from an
already-deterministic Phase C1-C3 artifact, or derived from one
single, order-independent pass over `.values()` collecting counts into
a `dict`/`Counter` (never from Python's own hash-randomized set/dict
iteration order in a way that could change the VALUES produced, only
their insertion order, which `to_dict()`'s own plain-dict equality
never depends on) -- plus `datetime.now(timezone.utc)` for `generated_at`
only, the same single, explicitly-accepted non-deterministic field every
earlier manifest/report in this codebase already carries.

BACKWARD COMPATIBILITY: every field this module reads (from
`validation_report`, from `graph_registry_manager`, from every earlier
Knowledge Graph phase's own *_VERSION constant) is only ever read, never
changed. No existing node, edge, registry, Compiler IR field, or Chapter
JSON output changes as a result of this module existing. The only new
artifacts are the manifest and statistics dicts themselves (plus the
already-existing, previously-unused get/set/has functions in
knowledge_graph/state.py that now hold them).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .edge import EDGE_SCHEMA_VERSION
from .identity import IDENTITY_VERSION
from .node import NODE_SCHEMA_VERSION
from .registries import GRAPH_REGISTRY_VERSION, NODE_REGISTRY_NAME, GraphRegistryManager
from .schema import (
    KNOWLEDGE_GRAPH_SCHEMA_VERSION,
    KnowledgeGraphManifest,
    KnowledgeGraphMetadata,
    KnowledgeGraphStatistics,
)
from .validation import GRAPH_VALIDATION_VERSION


# --------------------------------------------------------------------------
# This module's own version marker -- independent of every earlier
# Knowledge Graph phase's own *_VERSION constant (which each version
# their own separate pass), and independent of
# KNOWLEDGE_GRAPH_SCHEMA_VERSION (which versions the schema shape, not
# this pass). Bump only if the manifest/statistics SHAPE this file
# produces itself changes in a way a consumer of
# `manifest["node_registry_versions"]` should be able to detect. Mirrors
# compiler/build.py's own BUILD_VERSION precedent, one layer up.
GRAPH_BUILD_VERSION = "C4.1"


# --------------------------------------------------------------------------
# Task 3: Knowledge Graph Manifest
# --------------------------------------------------------------------------

def generate_knowledge_graph_manifest(
    graph_registry_manager: GraphRegistryManager,
    validation_report: Dict[str, Any],
    graph_metadata: KnowledgeGraphMetadata,
) -> Dict[str, Any]:
    """Phase C4.1 Task 3 / Task 6's single pipeline.py integration point
    (mirrors knowledge_graph.validation.validate_knowledge_graph()'s own
    shape one phase down). Must run AFTER validate_knowledge_graph() (so
    `validation_report` is available to read counts from) -- see module
    docstring's PIPELINE INTEGRATION section and pipeline.py's own
    comment at the call site.

    Read-only over all three arguments: no graph registry is inserted
    into, updated, or removed from; no node/edge/metadata anywhere is
    mutated; `validation_report` and `graph_metadata` are only ever
    read. Every count below is read from `validation_report["node_
    summary"]`/`["edge_summary"]` (already computed by
    validate_knowledge_graph()) -- never by iterating the node/edge
    registries a second time.

    Returned as a plain dict (manifest.to_dict()) for the same "plain,
    storable dict" reasons validate_knowledge_graph() already documents
    for its own return value, and so it can be handed directly to
    knowledge_graph.state.set_current_knowledge_graph_manifest() (Task
    5's own "the manifest belongs to Knowledge Graph State").
    """
    node_summary = validation_report.get("node_summary") or {}
    edge_summary = validation_report.get("edge_summary") or {}
    overall_status = validation_report.get("overall_status", "unknown")

    manifest = KnowledgeGraphManifest(
        generated_at=datetime.now(timezone.utc).isoformat(),
        graph_schema_version=KNOWLEDGE_GRAPH_SCHEMA_VERSION,
        identity_version=IDENTITY_VERSION,
        graph_id=graph_metadata.graph_id,
        graph_urn=graph_metadata.graph_urn,
        source_chapter_identifier=graph_metadata.source_chapter_identifier,
        # Pass-name -> that pass's own existing version marker -- exactly
        # compiler/build.py's own `registry_versions` convention, reused
        # here rather than reinvented. `source_compiler` folds in
        # `KnowledgeGraphMetadata.source_compiler_version` (see module
        # docstring's NO SCHEMA REDESIGN section for why this lives here
        # rather than as a new top-level manifest field).
        node_registry_versions={
            "node": NODE_SCHEMA_VERSION,
            "edge": EDGE_SCHEMA_VERSION,
            "registry": GRAPH_REGISTRY_VERSION,
            "validation": GRAPH_VALIDATION_VERSION,
            "build": GRAPH_BUILD_VERSION,
            "source_compiler": graph_metadata.source_compiler_version or "",
        },
        node_count=node_summary.get("total", 0),
        edge_count=edge_summary.get("total", 0),
        node_type_counts=dict(node_summary.get("by_node_type") or {}),
        edge_type_counts=dict(edge_summary.get("by_edge_type") or {}),
        # Both fields report only that THIS manifest-generation pass
        # itself completed -- never a readiness or correctness verdict.
        # See module docstring's WHAT THIS IS NOT section. The graph's
        # own correctness verdict (`overall_status`) is read above only
        # to decide nothing here; it is never written into either field.
        graph_status="generated",
        graph_generation_status="generated",
    )
    return manifest.to_dict()


# --------------------------------------------------------------------------
# Task 4: Knowledge Graph Statistics
# --------------------------------------------------------------------------

def generate_knowledge_graph_statistics(
    graph_registry_manager: GraphRegistryManager,
    validation_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Phase C4.1 Task 4. Same reuse rule as
    generate_knowledge_graph_manifest() above: every count/summary below
    is read from `validation_report` (already computed by
    validate_knowledge_graph()) wherever that report already carries it.
    The one exception -- `nodes_by_source_registry` -- is documented at
    the point it is computed below (module docstring's REUSE, DON'T
    RECOMPUTE section explains why this one count cannot be read from
    the C3 report, which never tracked it).

    Read-only over both arguments.
    """
    node_summary = validation_report.get("node_summary") or {}
    edge_summary = validation_report.get("edge_summary") or {}
    registry_summary = validation_report.get("registry_summary") or {}
    overall_status = validation_report.get("overall_status", "unknown")

    # -- nodes by source (Compiler IR) registry -- the one count this
    # report does not already carry (Task 4's own "source registry
    # counts" bullet). One single, bounded, read-only pass over the node
    # registry's own `.values()` -- never `.insert()`/`.update()`/
    # `.remove()`, never a Compiler IR lookup, never a second validation
    # pass. Skipped entirely (empty dict) if the node registry itself is
    # absent, mirroring every C3 `_validate_*` function's own "missing
    # registry -> empty summary" fallback.
    nodes_by_source_registry: Dict[str, int] = {}
    if graph_registry_manager.has(NODE_REGISTRY_NAME):
        node_registry = graph_registry_manager.get(NODE_REGISTRY_NAME)
        counts = Counter(
            getattr(node, "compiler_registry", None)
            if not isinstance(node, dict) else node.get("compiler_registry")
            for node in node_registry.values()
        )
        counts.pop(None, None)
        nodes_by_source_registry = dict(counts)

    statistics = KnowledgeGraphStatistics(
        generated_at=datetime.now(timezone.utc).isoformat(),
        node_registry_sizes=dict(registry_summary.get("registry_sizes") or {}),
        edges_by_type=dict(edge_summary.get("by_edge_type") or {}),
        total_nodes=node_summary.get("total", 0),
        total_edges=edge_summary.get("total", 0),
        nodes_by_source_registry=nodes_by_source_registry,
        validation_summary={
            "status": overall_status,
            **(validation_report.get("validation_statistics") or {}),
        },
    )
    return statistics.to_dict()