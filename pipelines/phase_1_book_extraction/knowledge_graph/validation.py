"""
knowledge_graph/validation.py — Phase C0 Task 6: Graph Validation
Contracts.

SCOPE: this module defines ONLY the interfaces (abstract base classes)
a future C5 Validation phase will implement -- mirrors
compiler/validation.py's own overall shape (status/errors/warnings,
per-area summaries -- see knowledge_graph/schema.py's
`KnowledgeGraphValidationReport`, whose field set these contracts are
designed to be able to fill) WITHOUT containing a single concrete
validation rule. No method on any class below is implemented; every one
raises NotImplementedError, exactly the standard-library `abc` pattern's
intended use (a contract describing capability, not behavior).

WHY SIX SEPARATE CONTRACTS, NOT ONE: mirrors compiler/validation.py's
own internal structure, which already splits into distinct private
passes (`_validate_registry_integrity`, `_validate_reference_integrity`,
`_validate_relationship_integrity`, `_validate_compiler_state_integrity`,
`_check_id_determinism`) composed together by one
`validate_compiler_state()` entry point. This module makes that same
split explicit and public, one contract per concern, so a future C5
implementation can implement (or replace) each concern independently --
e.g. swapping in a stricter DeterminismValidator without touching
NodeValidator.

PHASE C3 ADDITION (Knowledge Graph Validation & Integrity): everything
above this note is exactly as Phase C0 left it -- the six ABC contracts
are untouched, still abstract, still raise NotImplementedError if
subclassed and called. This phase does NOT implement them as classes
(doing so alongside a second, function-based implementation of the same
checks would itself be the "duplicated implementation" this project's
own instructions warn against). Instead, this phase adds the concrete,
FUNCTION-based validation pass compiler/validation.py's own
`validate_compiler_state()` already established as this project's real
working pattern for a Compiler-IR-shaped artifact (the six ABC classes
above were always speculative architecture for "a future C5
implementation" per this docstring's own original wording -- Phase C3
fulfills that need the same way Phase B4 already did for Compiler IR,
with private `_validate_*`/`_check_*` module functions composed by one
`validate_knowledge_graph()` entry point, not by finally subclassing
these six ABCs). The ABCs remain available, unused, exactly as
`compiler/validation.py`'s own module never needed an ABC layer either.

See the "PHASE C3" section further down in this file for the concrete
implementation, the volatile-field/id-recomputation determinism
strategy, and the checklist-style passed_checks/failed_checks this
phase's own Task 6 report spec asks for (mirroring
compiler/fingerprints.py's own `generate_compiler_readiness_report()`
checklist convention).
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import identity
from .edge import GraphEdgeBase, FUTURE_EDGE_TYPES, is_known_future_edge_type
from .node import GraphNodeBase, FUTURE_NODE_TYPES, is_known_future_node_type
from .registries import (
    EDGE_REGISTRY_NAME,
    GRAPH_REGISTRY_NAMES,
    METADATA_REGISTRY_NAME,
    NODE_REGISTRY_NAME,
    GraphRegistryManager,
)
from .schema import KnowledgeGraph, KnowledgeGraphValidationReport, KnowledgeGraphReadinessReport

# Compiler IR is read ONLY for the optional, best-effort cross-checks
# Task 1 allows ("Compiler RegistryManager (if required for verification
# only)") -- see _validate_node_integrity()'s/_validate_graph_integrity()'s
# own `compiler_registry_manager` parameter below. Nothing in this module
# ever calls a compiler.* function that mutates anything; only read
# accessors (`.has()`, `.get()`, `.contains()`, `.size()`) are used.
from compiler.registries import REGISTRY_NAMES as COMPILER_REGISTRY_NAMES
from compiler.registry_manager import RegistryManager as CompilerRegistryManager
from compiler.relationships import (
    RELATIONSHIP_REGISTRY_NAME as COMPILER_RELATIONSHIP_REGISTRY_NAME,
)


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
VALIDATION_CONTRACT_VERSION = "C0.1"


class NodeValidator(ABC):
    """Contract for validating one graph node in isolation (shape,
    required fields, node_type membership in
    knowledge_graph.node.FUTURE_NODE_TYPES, compiler_object_id/
    compiler_registry consistency, ...). The Compiler IR analogue this
    mirrors is compiler/validation.py's own
    `_validate_canonical_object_integrity()` -- same concern, one level
    up the stack (a node, not a canonical object)."""

    @abstractmethod
    def validate_node(self, node: GraphNodeBase) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts (empty if the node is valid).
        Never implemented in Phase C0."""
        raise NotImplementedError


class EdgeValidator(ABC):
    """Contract for validating one graph edge in isolation (shape,
    required fields, edge_type membership in
    knowledge_graph.edge.FUTURE_EDGE_TYPES, directed flag consistency,
    ...). Mirrors compiler/validation.py's own
    `_validate_relationship_integrity()`, one level up."""

    @abstractmethod
    def validate_edge(self, edge: GraphEdgeBase) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts (empty if the edge is valid).
        Never implemented in Phase C0."""
        raise NotImplementedError


class GraphValidator(ABC):
    """Contract for validating an entire KnowledgeGraph as a whole
    (every node + every edge together) -- the composed, top-level
    contract, analogous to compiler/validation.py's own
    `validate_compiler_state()` entry point. A concrete implementation
    is expected to internally use NodeValidator/EdgeValidator/
    IntegrityValidator/DeterminismValidator (this module's own other
    contracts) the same way `validate_compiler_state()` internally calls
    its own private per-area passes."""

    @abstractmethod
    def validate_graph(self, graph: KnowledgeGraph) -> KnowledgeGraphValidationReport:
        """Returns a fully-populated KnowledgeGraphValidationReport.
        Never implemented in Phase C0."""
        raise NotImplementedError


class IntegrityValidator(ABC):
    """Contract for cross-referential integrity: every edge's
    source_node_id/target_node_id actually resolves to a node in the
    graph's own node registry, every node's compiler_object_id/
    compiler_registry actually resolves to a real Compiler IR item, no
    duplicate node/edge ids, etc. Mirrors compiler/validation.py's own
    `_validate_reference_integrity()` +
    `_validate_compiler_state_integrity()`, combined at the graph
    level."""

    @abstractmethod
    def validate_integrity(self, graph: KnowledgeGraph) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts. Never implemented in Phase
        C0."""
        raise NotImplementedError


class DeterminismValidator(ABC):
    """Contract for confirming a graph build is deterministic: given the
    same Compiler IR input twice, the same graph (same node/edge ids,
    same urns, same fingerprint) is produced both times. Mirrors
    compiler/validation.py's own `_check_id_determinism()`, one level
    up the stack."""

    @abstractmethod
    def validate_determinism(
        self, graph_a: KnowledgeGraph, graph_b: KnowledgeGraph
    ) -> List[Dict[str, Any]]:
        """Returns a list of issue dicts describing any divergence
        between two graphs built from the same input. Never implemented
        in Phase C0."""
        raise NotImplementedError


class ReadinessValidator(ABC):
    """Contract for the read-only readiness verdict a future C8/C9 phase
    will compute -- mirrors compiler/fingerprints.py's own
    `generate_compiler_readiness_report()`, one level up. Distinct from
    GraphValidator: readiness asks "is this graph usable downstream?"
    (a checklist of already-computed facts), not "is this graph
    internally correct?" (GraphValidator's own concern) -- the exact
    same validation/readiness split compiler/validation.py vs.
    compiler/fingerprints.py already establishes for Compiler IR."""

    @abstractmethod
    def validate_readiness(self, graph: KnowledgeGraph) -> KnowledgeGraphReadinessReport:
        """Returns a fully-populated KnowledgeGraphReadinessReport.
        Never implemented in Phase C0."""
        raise NotImplementedError


# ============================================================================
# PHASE C3 -- Knowledge Graph Validation & Integrity (concrete
# implementation)
# ============================================================================
#
# Everything below is additive: no class or function above this point was
# changed. This section is the first place in this codebase that ever
# inspects real GraphNodeBase/GraphEdgeBase data for correctness -- and,
# per this phase's own architectural requirements, ONLY inspects it:
# every function below reads `graph_registry_manager` (and, optionally,
# `compiler_registry_manager`, for the cross-checks Task 1 allows "if
# required for verification only") through public, read-only accessors
# (`.has()`, `.get()`, `.ids()`, `.values()`, `.get_by_id()`, `.contains()`,
# `.size()`, `.name`) -- never `.insert()`, `.update()`, `.remove()`, or
# `.clear()`. Nothing here constructs a node, an edge, or a Compiler IR
# item; nothing here repairs, prunes, or reorders anything it finds wrong
# -- it is recorded as a finding and nothing else, exactly this phase's
# own "Validation never repairs" requirement.
#
# ARCHITECTURE: function-based, not the six ABC classes above -- see this
# module's own "PHASE C3 ADDITION" docstring note (top of file) for why.
# Structure mirrors compiler/validation.py's own `validate_compiler_state()`
# closely, one concern per private function, composed by the one public
# `validate_knowledge_graph()` entry point at the bottom:
#
#   _validate_registry_integrity  -- Task 4 (graph registries exist, own
#                                     the size they report, are the right
#                                     class to make duplicate insertion
#                                     structurally impossible)
#   _validate_node_integrity      -- Task 2 (per-node checks)
#   _validate_edge_integrity      -- Task 3 (per-edge checks)
#   _validate_graph_integrity     -- Task 5 (cross-item / whole-graph
#                                     checks, reusing edge_summary's
#                                     already-computed broken-endpoint
#                                     counts rather than rescanning)
#   _check_graph_determinism      -- id/urn shape + recomputation checks
#                                     (mirrors compiler/validation.py's
#                                     own separate `_check_id_determinism`
#                                     pass, one layer up)
#
# No traversal, no adjacency list, no BFS/DFS, no shortest path, no
# prerequisite/dependency/semantic reasoning, no graph optimization or
# querying is implemented anywhere below -- every check is a bounded scan
# over `.ids()`/`.values()` (node registry once, edge registry once) plus
# simple set/count comparisons; nothing follows an edge from one node to
# another to explore the graph's shape.
# --------------------------------------------------------------------------

# This concrete implementation's own version marker -- independent of
# VALIDATION_CONTRACT_VERSION above (which versions the six ABC
# contracts' own shape, untouched by this phase), independent of every
# compiler-side *_VERSION constant, and independent of
# knowledge_graph.schema.KNOWLEDGE_GRAPH_SCHEMA_VERSION. Bump only if the
# concrete CHECKS this section performs change in a way a consumer of
# `report["validation_version"]` should be able to detect.
GRAPH_VALIDATION_VERSION = "C3.0"


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def _attr(item: Any, key: str) -> Optional[Any]:
    """Reads `key` off `item` without caring whether `item` is a plain
    dict or a real GraphNodeBase/GraphEdgeBase dataclass instance (the
    shape every node/edge actually is once built by
    knowledge_graph.build_nodes/build_edges) -- same dict-or-attribute
    extractor contract knowledge_graph.build_nodes.py's own `_field()`
    and compiler/registry.py's own `_get()` already use. Read-only: never
    assigns anything back onto `item`."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _issue(
    severity: str, rule: str, message: str, *,
    object_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One error or warning, as a plain dict -- KnowledgeGraphValidationReport's
    own `errors`/`warnings` fields are typed `List[Dict[str, Any]]`
    (schema.py), so issues are built directly as dicts here rather than
    via an intermediate dataclass + .to_dict() step compiler/validation.py's
    own ValidationIssue needs (that module's own `errors`/`warnings`
    properties filter a single combined `issues` list by severity; this
    module's schema already keeps them as two separate fields, so there is
    nothing to filter after the fact)."""
    d: Dict[str, Any] = {"severity": severity, "rule": rule, "message": message}
    if object_id is not None:
        d["object_id"] = object_id
    if details:
        d["details"] = details
    return d


def _error(rule: str, message: str, **kw: Any) -> Dict[str, Any]:
    return _issue("error", rule, message, **kw)


def _warning(rule: str, message: str, **kw: Any) -> Dict[str, Any]:
    return _issue("warning", rule, message, **kw)


# --------------------------------------------------------------------------
# Task 4: Registry Integrity
# --------------------------------------------------------------------------

def _validate_registry_integrity(
    graph_registry_manager: GraphRegistryManager,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """node registry exists, edge registry exists, registry sizes,
    duplicate insertion impossible, registry ownership correct -- see
    task's own "Registry Integrity" list. Read-only over
    `graph_registry_manager`: only `.has()`/`.get()`/`.size()`/`.name`
    are ever called."""
    from compiler.registry import CanonicalRegistry  # local import: this
    # is the one place this module needs the concrete class (for an
    # isinstance check only -- see "duplicate_insertion_structurally_
    # impossible" below), and every other function in this module only
    # ever needs the registry's public API, not its concrete type.

    issues: List[Dict[str, Any]] = []
    missing = [n for n in GRAPH_REGISTRY_NAMES if not graph_registry_manager.has(n)]
    for n in missing:
        issues.append(_error(
            "missing_graph_registry",
            f"required graph registry {n!r} is missing from the "
            "GraphRegistryManager", object_id=n,
        ))

    sizes: Dict[str, int] = {}
    ownership_mismatches: List[str] = []
    all_canonical_registry = True
    for name in GRAPH_REGISTRY_NAMES:
        if not graph_registry_manager.has(name):
            continue
        registry = graph_registry_manager.get(name)
        sizes[name] = registry.size()
        if not isinstance(registry, CanonicalRegistry):
            all_canonical_registry = False
        if registry.name != name:
            ownership_mismatches.append(name)
            issues.append(_error(
                "graph_registry_ownership_mismatch",
                f"graph registry stored under key {name!r} reports its "
                f"own name as {registry.name!r}", object_id=name,
            ))

    summary = {
        "required_registries_present": len(missing) == 0,
        "missing_registries": missing,
        "registry_sizes": sizes,
        "registry_ownership_ok": len(ownership_mismatches) == 0,
        "registries_present": [n for n in GRAPH_REGISTRY_NAMES if graph_registry_manager.has(n)],
        # Duplicate insertion is structurally impossible, not merely
        # untested: knowledge_graph.registries.create_graph_registry_manager()
        # builds every graph registry as a compiler.registry.CanonicalRegistry
        # instance, whose own insert() already raises DuplicateIdError/
        # DuplicateUrnError before a duplicate could ever be stored (see
        # that module's own docstring) -- confirmed here by isinstance
        # check, never by attempting an insert (this pass is read-only).
        "duplicate_insertion_structurally_impossible": all_canonical_registry,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Task 2: Node Integrity
# --------------------------------------------------------------------------

_REQUIRED_NODE_FIELDS: Tuple[str, ...] = (
    "node_id", "node_urn", "node_type", "graph_id", "graph_urn",
    "compiler_object_id", "compiler_object_urn", "compiler_object_type",
    "compiler_registry",
)

_GRAPH_ID_PREFIX = "kg-"
_GRAPH_URN_PREFIX = f"urn:{identity.URN_ROOT_NAMESPACE}:{identity.KG_URN_NAMESPACE}:"


def _validate_node_integrity(
    graph_registry_manager: GraphRegistryManager,
    compiler_registry_manager: Optional[CompilerRegistryManager] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """unique node ids, unique node urns, required fields present, node
    type valid, graph namespace valid, graph schema version present,
    compiler object references valid -- see task's own "Node Integrity"
    list. Never modifies a node (only `.ids()`/`.get_by_id()` are called
    on the node registry). `compiler_registry_manager` is optional (Task
    1's own "if required for verification only") -- when given, adds one
    further, deeper check per node (does the compiler object it points at
    actually exist in that Compiler IR); when omitted, that one check is
    simply skipped, not guessed at."""
    if not graph_registry_manager.has(NODE_REGISTRY_NAME):
        return [], {
            "total": 0, "duplicate_ids": 0, "duplicate_urns": 0,
            "missing_required_field_count": 0, "invalid_node_type_count": 0,
            "invalid_namespace_count": 0, "missing_schema_version_count": 0,
            "invalid_compiler_reference_count": 0,
            "by_node_type": {t: 0 for t in FUTURE_NODE_TYPES},
        }

    node_registry = graph_registry_manager.get(NODE_REGISTRY_NAME)
    ids = node_registry.ids()
    issues: List[Dict[str, Any]] = []

    if len(ids) != len(set(ids)):
        issues.append(_error(
            "duplicate_node_id", "nodes: registry.ids() contains duplicate id(s)",
        ))

    urn_owner: Dict[str, str] = {}
    dup_urns = 0
    missing_field_count = 0
    invalid_type_count = 0
    invalid_namespace_count = 0
    missing_schema_version_count = 0
    invalid_compiler_ref_count = 0
    by_node_type: Dict[str, int] = {t: 0 for t in FUTURE_NODE_TYPES}

    for node_id_ in ids:
        node = node_registry.get_by_id(node_id_)

        # -- required fields present --
        missing = [f for f in _REQUIRED_NODE_FIELDS if not _attr(node, f)]
        if missing:
            missing_field_count += 1
            issues.append(_error(
                "missing_required_node_field",
                f"nodes: node {node_id_!r} is missing required field(s): "
                + ", ".join(missing),
                object_id=node_id_, details={"missing_fields": missing},
            ))

        # -- unique node urns --
        urn = _attr(node, "node_urn")
        if urn:
            if urn in urn_owner and urn_owner[urn] != node_id_:
                dup_urns += 1
                issues.append(_error(
                    "duplicate_node_urn",
                    f"nodes: urn {urn!r} shared by {urn_owner[urn]!r} and "
                    f"{node_id_!r}",
                    object_id=node_id_,
                    details={"urn": urn, "other_id": urn_owner[urn]},
                ))
            else:
                urn_owner[urn] = node_id_

        # -- node type valid --
        node_type = _attr(node, "node_type")
        if node_type in by_node_type:
            by_node_type[node_type] += 1
        else:
            invalid_type_count += 1
            issues.append(_error(
                "invalid_node_type",
                f"nodes: node {node_id_!r} has unrecognized node_type "
                f"{node_type!r}",
                object_id=node_id_, details={"node_type": node_type},
            ))

        # -- graph namespace valid (shape of graph_id/graph_urn) --
        graph_id_val = _attr(node, "graph_id")
        graph_urn_val = _attr(node, "graph_urn")
        if not (isinstance(graph_id_val, str) and graph_id_val.startswith(_GRAPH_ID_PREFIX)):
            invalid_namespace_count += 1
            issues.append(_warning(
                "node_graph_id_shape_unexpected",
                f"nodes: node {node_id_!r} graph_id {graph_id_val!r} does "
                f"not match the expected {_GRAPH_ID_PREFIX!r}-prefixed shape "
                "identity.graph_id() produces",
                object_id=node_id_,
            ))
        if not (isinstance(graph_urn_val, str) and graph_urn_val.startswith(_GRAPH_URN_PREFIX)):
            invalid_namespace_count += 1
            issues.append(_warning(
                "node_graph_urn_shape_unexpected",
                f"nodes: node {node_id_!r} graph_urn {graph_urn_val!r} does "
                f"not match the expected {_GRAPH_URN_PREFIX!r}-prefixed "
                "shape identity.graph_urn() produces",
                object_id=node_id_,
            ))

        # -- graph schema version present --
        if not _attr(node, "node_schema_version"):
            missing_schema_version_count += 1
            issues.append(_error(
                "missing_node_schema_version",
                f"nodes: node {node_id_!r} is missing node_schema_version",
                object_id=node_id_,
            ))

        # -- compiler object references valid --
        compiler_object_id = _attr(node, "compiler_object_id")
        compiler_registry_name = _attr(node, "compiler_registry")
        if compiler_registry_name and compiler_registry_name not in COMPILER_REGISTRY_NAMES:
            invalid_compiler_ref_count += 1
            issues.append(_error(
                "invalid_compiler_registry_reference",
                f"nodes: node {node_id_!r} references unknown compiler "
                f"registry {compiler_registry_name!r}",
                object_id=node_id_,
                details={"compiler_registry": compiler_registry_name},
            ))
        elif compiler_registry_manager is not None and compiler_registry_name and compiler_object_id:
            exists = (
                compiler_registry_manager.has(compiler_registry_name)
                and compiler_registry_manager.get(compiler_registry_name).contains(compiler_object_id)
            )
            if not exists:
                invalid_compiler_ref_count += 1
                issues.append(_error(
                    "dangling_compiler_object_reference",
                    f"nodes: node {node_id_!r} references compiler object "
                    f"{compiler_object_id!r} in registry "
                    f"{compiler_registry_name!r}, which does not exist in "
                    "the supplied Compiler IR",
                    object_id=node_id_,
                    details={
                        "compiler_registry": compiler_registry_name,
                        "compiler_object_id": compiler_object_id,
                    },
                ))

    summary = {
        "total": len(ids),
        "duplicate_ids": len(ids) - len(set(ids)),
        "duplicate_urns": dup_urns,
        "missing_required_field_count": missing_field_count,
        "invalid_node_type_count": invalid_type_count,
        "invalid_namespace_count": invalid_namespace_count,
        "missing_schema_version_count": missing_schema_version_count,
        "invalid_compiler_reference_count": invalid_compiler_ref_count,
        "by_node_type": by_node_type,
        "compiler_cross_check_performed": compiler_registry_manager is not None,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Task 3: Edge Integrity
# --------------------------------------------------------------------------

_REQUIRED_EDGE_FIELDS: Tuple[str, ...] = (
    "edge_id", "edge_urn", "edge_type", "graph_id", "graph_urn",
    "source_node_id", "target_node_id",
)


def _validate_edge_integrity(
    graph_registry_manager: GraphRegistryManager,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """unique edge ids, unique edge urns, edge type valid, source node
    exists, target node exists, no orphan endpoints -- see task's own
    "Edge Integrity" list. ("Deterministic edge identity", that same
    list's last bullet, is covered by `_check_graph_determinism()` below
    -- mirrors compiler/validation.py's own choice to keep relationship-id
    recomputation in a separate `_check_id_determinism()` pass rather
    than inside `_validate_relationship_integrity()`, so this phase
    follows the same split rather than inventing a new one.) Never
    modifies an edge or a node (only `.ids()`/`.get_by_id()`/`.contains()`
    are called)."""
    if not graph_registry_manager.has(EDGE_REGISTRY_NAME):
        return [], {
            "total": 0, "duplicate_ids": 0, "duplicate_urns": 0,
            "missing_required_field_count": 0, "invalid_edge_type_count": 0,
            "by_edge_type": {t: 0 for t in FUTURE_EDGE_TYPES},
            "broken_source": 0, "broken_target": 0, "orphans": 0, "dangling": 0,
        }

    edge_registry = graph_registry_manager.get(EDGE_REGISTRY_NAME)
    node_registry = (
        graph_registry_manager.get(NODE_REGISTRY_NAME)
        if graph_registry_manager.has(NODE_REGISTRY_NAME) else None
    )
    ids = edge_registry.ids()
    issues: List[Dict[str, Any]] = []

    if len(ids) != len(set(ids)):
        issues.append(_error(
            "duplicate_edge_id", "edges: registry.ids() contains duplicate id(s)",
        ))

    urn_owner: Dict[str, str] = {}
    dup_urns = 0
    missing_field_count = 0
    invalid_type_count = 0
    broken_source = 0
    broken_target = 0
    orphans = 0
    dangling = 0
    by_edge_type: Dict[str, int] = {t: 0 for t in FUTURE_EDGE_TYPES}

    for edge_id_ in ids:
        edge = edge_registry.get_by_id(edge_id_)

        # -- required fields present --
        missing = [f for f in _REQUIRED_EDGE_FIELDS if not _attr(edge, f)]
        if missing:
            missing_field_count += 1
            issues.append(_error(
                "missing_required_edge_field",
                f"edges: edge {edge_id_!r} is missing required field(s): "
                + ", ".join(missing),
                object_id=edge_id_, details={"missing_fields": missing},
            ))

        # -- unique edge urns --
        urn = _attr(edge, "edge_urn")
        if urn:
            if urn in urn_owner and urn_owner[urn] != edge_id_:
                dup_urns += 1
                issues.append(_error(
                    "duplicate_edge_urn",
                    f"edges: urn {urn!r} shared by {urn_owner[urn]!r} and "
                    f"{edge_id_!r}",
                    object_id=edge_id_,
                    details={"urn": urn, "other_id": urn_owner[urn]},
                ))
            else:
                urn_owner[urn] = edge_id_

        # -- edge type valid --
        edge_type = _attr(edge, "edge_type")
        if edge_type in by_edge_type:
            by_edge_type[edge_type] += 1
        else:
            invalid_type_count += 1
            issues.append(_error(
                "invalid_edge_type",
                f"edges: edge {edge_id_!r} has unrecognized edge_type "
                f"{edge_type!r}",
                object_id=edge_id_, details={"edge_type": edge_type},
            ))

        # -- source/target node exist; no orphan endpoints --
        source_node_id = _attr(edge, "source_node_id")
        target_node_id = _attr(edge, "target_node_id")
        source_ok = bool(source_node_id) and node_registry is not None and node_registry.contains(source_node_id)
        target_ok = bool(target_node_id) and node_registry is not None and node_registry.contains(target_node_id)

        if not source_ok:
            broken_source += 1
            issues.append(_error(
                "missing_source_node",
                f"edges: edge {edge_id_!r} source node {source_node_id!r} "
                "does not exist in the node registry",
                object_id=edge_id_, details={"source_node_id": source_node_id},
            ))
        if not target_ok:
            broken_target += 1
            issues.append(_error(
                "missing_target_node",
                f"edges: edge {edge_id_!r} target node {target_node_id!r} "
                "does not exist in the node registry",
                object_id=edge_id_, details={"target_node_id": target_node_id},
            ))
        if not source_ok and not target_ok:
            orphans += 1
        if not source_ok or not target_ok:
            dangling += 1

    summary = {
        "total": len(ids),
        "duplicate_ids": len(ids) - len(set(ids)),
        "duplicate_urns": dup_urns,
        "missing_required_field_count": missing_field_count,
        "invalid_edge_type_count": invalid_type_count,
        "by_edge_type": by_edge_type,
        "broken_source": broken_source,
        "broken_target": broken_target,
        "orphans": orphans,
        "dangling": dangling,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Task 5: Graph Integrity
# --------------------------------------------------------------------------

def _validate_graph_integrity(
    graph_registry_manager: GraphRegistryManager,
    edge_summary: Dict[str, Any],
    *,
    compiler_registry_manager: Optional[CompilerRegistryManager] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """every edge connects existing nodes, no dangling edges, no orphan
    edge endpoints, graph namespace consistency, graph URN consistency,
    graph contains expected node/edge counts -- see task's own "Graph
    Integrity" list. No traversal, no adjacency list, no cycle detection:
    "every edge connects existing nodes"/"no dangling edges"/"no orphan
    edge endpoints" are reused directly from `edge_summary` (already
    computed by `_validate_edge_integrity()` above -- never rescanned
    here), and "namespace/URN consistency" is one pass collecting the
    distinct `graph_id`/`graph_urn` values already stamped on every node
    and edge, not a graph walk. "Expected node/edge counts" is only
    checked when `compiler_registry_manager` is supplied (Task 1's own
    "if required for verification only") -- omitted, not guessed at,
    otherwise."""
    node_registry = (
        graph_registry_manager.get(NODE_REGISTRY_NAME)
        if graph_registry_manager.has(NODE_REGISTRY_NAME) else None
    )
    edge_registry = (
        graph_registry_manager.get(EDGE_REGISTRY_NAME)
        if graph_registry_manager.has(EDGE_REGISTRY_NAME) else None
    )
    issues: List[Dict[str, Any]] = []

    graph_ids = set()
    graph_urns = set()
    for registry in (node_registry, edge_registry):
        if registry is None:
            continue
        for item in registry.values():
            gid = _attr(item, "graph_id")
            gurn = _attr(item, "graph_urn")
            if gid:
                graph_ids.add(gid)
            if gurn:
                graph_urns.add(gurn)

    namespace_consistent = len(graph_ids) <= 1
    urn_consistent = len(graph_urns) <= 1
    if not namespace_consistent:
        issues.append(_error(
            "graph_namespace_inconsistent",
            "nodes/edges disagree on graph_id -- expected exactly one "
            f"distinct value, found {sorted(graph_ids)!r}",
            details={"graph_ids": sorted(graph_ids)},
        ))
    if not urn_consistent:
        issues.append(_error(
            "graph_urn_inconsistent",
            "nodes/edges disagree on graph_urn -- expected exactly one "
            f"distinct value, found {sorted(graph_urns)!r}",
            details={"graph_urns": sorted(graph_urns)},
        ))

    dangling_edges = edge_summary.get("dangling", 0)
    orphan_edges = edge_summary.get("orphans", 0)
    if dangling_edges:
        issues.append(_error(
            "dangling_edges_present",
            f"{dangling_edges} edge(s) have a source and/or target node "
            "that does not exist in the node registry",
            details={"dangling_edges": dangling_edges, "orphan_edges": orphan_edges},
        ))

    expected_counts: Dict[str, Any]
    if compiler_registry_manager is not None:
        expected_node_count = sum(
            compiler_registry_manager.get(n).size()
            for n in COMPILER_REGISTRY_NAMES if compiler_registry_manager.has(n)
        )
        expected_edge_count = (
            compiler_registry_manager.get(COMPILER_RELATIONSHIP_REGISTRY_NAME).size()
            if compiler_registry_manager.has(COMPILER_RELATIONSHIP_REGISTRY_NAME) else 0
        )
        actual_node_count = node_registry.size() if node_registry is not None else 0
        actual_edge_count = edge_registry.size() if edge_registry is not None else 0
        node_count_matches = actual_node_count == expected_node_count
        edge_count_matches = actual_edge_count == expected_edge_count
        if not node_count_matches:
            issues.append(_error(
                "node_count_mismatch",
                f"expected {expected_node_count} node(s) (one per Compiler "
                f"IR object), found {actual_node_count}",
                details={"expected": expected_node_count, "actual": actual_node_count},
            ))
        if not edge_count_matches:
            issues.append(_error(
                "edge_count_mismatch",
                f"expected {expected_edge_count} edge(s) (one per Compiler "
                f"IR relationship), found {actual_edge_count}",
                details={"expected": expected_edge_count, "actual": actual_edge_count},
            ))
        expected_counts = {
            "checked": True,
            "expected_node_count": expected_node_count,
            "actual_node_count": actual_node_count,
            "node_count_matches": node_count_matches,
            "expected_edge_count": expected_edge_count,
            "actual_edge_count": actual_edge_count,
            "edge_count_matches": edge_count_matches,
        }
    else:
        expected_counts = {"checked": False}

    summary = {
        "graph_namespace_consistent": namespace_consistent,
        "graph_urn_consistent": urn_consistent,
        "distinct_graph_ids": sorted(graph_ids),
        "distinct_graph_urns": sorted(graph_urns),
        "dangling_edges": dangling_edges,
        "orphan_edges": orphan_edges,
        "expected_counts": expected_counts,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Determinism check (mirrors compiler/validation.py's own separate
# `_check_id_determinism()` pass -- see _validate_edge_integrity()'s own
# docstring for why "deterministic edge identity" lives here rather than
# there)
# --------------------------------------------------------------------------

_NODE_ID_PATTERN = re.compile(r"^node:[a-z0-9-]+:.+$")
_EDGE_ID_PATTERN = re.compile(r"^edge:[a-z0-9-]+:.+:.+$")


def _check_graph_determinism(
    graph_registry_manager: GraphRegistryManager,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Structural id-shape check (against the `node:<type>:<id>`/
    `edge:<type>:<source>:<target>` shape `knowledge_graph.identity`'s own
    node_id()/edge_id() always produce) PLUS, for every node/edge, a
    genuine recomputation: `identity.node_id(node.node_type,
    node.compiler_object_id)` / `identity.edge_id(edge.edge_type,
    edge.source_node_id, edge.target_node_id)`, each compared against the
    id actually stored -- the strongest available proof that a given
    node/edge id really is a pure function of its own content, not a
    random or otherwise non-reproducible value. Both id() calls need no
    external namespace argument (see knowledge_graph/identity.py's own
    node_id()/edge_id() signatures), so this is a genuine call to the real
    identity functions, never a re-derived copy of their formula. A
    mismatch is a WARNING, not an error -- mirrors compiler/validation.py's
    own `_check_id_determinism()` treatment of a relationship-id
    recomputation mismatch (a node/edge built under a since-changed
    knowledge_graph.identity.IDENTITY_VERSION could legitimately have used
    a different-but-still-deterministic scheme)."""
    issues: List[Dict[str, Any]] = []

    node_id_shape_violations = 0
    node_id_mismatches = 0
    if graph_registry_manager.has(NODE_REGISTRY_NAME):
        node_registry = graph_registry_manager.get(NODE_REGISTRY_NAME)
        for node_id_ in node_registry.ids():
            node = node_registry.get_by_id(node_id_)
            if not node_id_ or not _NODE_ID_PATTERN.match(node_id_):
                node_id_shape_violations += 1
                issues.append(_warning(
                    "node_id_shape_unexpected",
                    f"nodes: node id {node_id_!r} does not match the "
                    "'node:<type>:<compiler-object-id>' shape "
                    "identity.node_id() always produces",
                    object_id=node_id_,
                ))
            node_type = _attr(node, "node_type")
            compiler_object_id = _attr(node, "compiler_object_id")
            if node_type and compiler_object_id:
                expected_id = identity.node_id(node_type, compiler_object_id)
                if expected_id != node_id_:
                    node_id_mismatches += 1
                    issues.append(_warning(
                        "node_id_not_reproducible",
                        f"nodes: node {node_id_!r} does not match "
                        "recomputing identity.node_id() from its own "
                        "stored node_type/compiler_object_id",
                        object_id=node_id_, details={"expected_id": expected_id},
                    ))

    edge_id_shape_violations = 0
    edge_id_mismatches = 0
    if graph_registry_manager.has(EDGE_REGISTRY_NAME):
        edge_registry = graph_registry_manager.get(EDGE_REGISTRY_NAME)
        for edge_id_ in edge_registry.ids():
            edge = edge_registry.get_by_id(edge_id_)
            if not edge_id_ or not _EDGE_ID_PATTERN.match(edge_id_):
                edge_id_shape_violations += 1
                issues.append(_warning(
                    "edge_id_shape_unexpected",
                    f"edges: edge id {edge_id_!r} does not match the "
                    "'edge:<type>:<source-node-id>:<target-node-id>' "
                    "shape identity.edge_id() always produces",
                    object_id=edge_id_,
                ))
            edge_type = _attr(edge, "edge_type")
            source_node_id = _attr(edge, "source_node_id")
            target_node_id = _attr(edge, "target_node_id")
            if edge_type and source_node_id and target_node_id:
                expected_id = identity.edge_id(edge_type, source_node_id, target_node_id)
                if expected_id != edge_id_:
                    edge_id_mismatches += 1
                    issues.append(_warning(
                        "edge_id_not_reproducible",
                        f"edges: edge {edge_id_!r} does not match "
                        "recomputing identity.edge_id() from its own "
                        "stored edge_type/source_node_id/target_node_id",
                        object_id=edge_id_, details={"expected_id": expected_id},
                    ))

    summary = {
        "node_id_shape_violations": node_id_shape_violations,
        "node_id_recomputation_mismatches": node_id_mismatches,
        "edge_id_shape_violations": edge_id_shape_violations,
        "edge_id_recomputation_mismatches": edge_id_mismatches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Task 6 / Task 8 -- top-level entry point, pipeline.py's single
# integration point
# --------------------------------------------------------------------------

def validate_knowledge_graph(
    graph_registry_manager: GraphRegistryManager,
    *,
    compiler_registry_manager: Optional[CompilerRegistryManager] = None,
) -> Dict[str, Any]:
    """Phase C3's single pipeline.py integration point (mirrors
    compiler.validation.validate_compiler_state()'s own shape one layer
    up). Must run AFTER knowledge_graph.build_edges.build_knowledge_graph_edges()
    (so there is a fully-populated node AND edge registry to validate)
    and is otherwise entirely independent of when Compiler State is
    finalized -- see pipeline.py's own comment at the call site.

    Read-only over both arguments: no graph registry is inserted into,
    updated, or removed from; no node/edge dict or dataclass instance
    anywhere is mutated; `compiler_registry_manager`, if supplied, is only
    ever read via `.has()`/`.get()`/`.contains()`/`.size()`. Runs all five
    validation categories the task spec lists (registry integrity, node
    integrity, edge integrity, graph integrity, determinism) and folds
    their issues/summaries into one KnowledgeGraphValidationReport,
    returned here as a plain dict (report.to_dict()) for the same "plain,
    storable dict" reasons validate_compiler_state() already documents
    for its own return value, and so it can be handed directly to
    knowledge_graph.state.set_current_knowledge_graph_validation_report()
    (task's own "store the current validation report" requirement,
    reusing that module's already-existing, unmodified get/set/has
    trio -- see this module's own PHASE C3 ADDITION docstring note).

    `compiler_registry_manager` is optional throughout (Task 1's own "if
    required for verification only"): omitting it still runs every check
    that only needs the Knowledge Graph's own registries (all of Task
    2/3/4 and most of Task 5); supplying it additionally verifies every
    node's compiler-object reference actually resolves, and that the
    graph's own node/edge counts match Compiler IR's own object/
    relationship counts exactly.
    """
    report = KnowledgeGraphValidationReport(
        validation_version=GRAPH_VALIDATION_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    registry_issues, registry_summary = _validate_registry_integrity(graph_registry_manager)
    report.registry_summary = registry_summary

    node_issues, node_summary = _validate_node_integrity(
        graph_registry_manager, compiler_registry_manager,
    )
    report.node_summary = node_summary

    edge_issues, edge_summary = _validate_edge_integrity(graph_registry_manager)
    report.edge_summary = edge_summary

    graph_issues, integrity_summary = _validate_graph_integrity(
        graph_registry_manager, edge_summary,
        compiler_registry_manager=compiler_registry_manager,
    )
    report.integrity_summary = integrity_summary

    determinism_issues, determinism_summary = _check_graph_determinism(graph_registry_manager)
    report.determinism_summary = determinism_summary

    all_issues = registry_issues + node_issues + edge_issues + graph_issues + determinism_issues
    report.errors = [i for i in all_issues if i["severity"] == "error"]
    report.warnings = [i for i in all_issues if i["severity"] == "warning"]

    # -- checklist-style passed_checks/failed_checks (Task 6's own field
    # list; mirrors compiler/fingerprints.py's own
    # generate_compiler_readiness_report() checklist convention) --
    passed: List[str] = []
    failed: List[str] = []

    def _record(name: str, ok: bool) -> None:
        (passed if ok else failed).append(name)

    _record("node_registry_exists", graph_registry_manager.has(NODE_REGISTRY_NAME))
    _record("edge_registry_exists", graph_registry_manager.has(EDGE_REGISTRY_NAME))
    _record("metadata_registry_exists", graph_registry_manager.has(METADATA_REGISTRY_NAME))
    _record("registry_ownership_correct", bool(registry_summary.get("registry_ownership_ok")))
    _record("no_duplicate_node_ids", node_summary.get("duplicate_ids", 1) == 0)
    _record("no_duplicate_edge_ids", edge_summary.get("duplicate_ids", 1) == 0)
    _record("no_dangling_edges", integrity_summary.get("dangling_edges", 1) == 0)
    _record("graph_namespace_consistent", bool(integrity_summary.get("graph_namespace_consistent")))
    _record("graph_urn_consistent", bool(integrity_summary.get("graph_urn_consistent")))
    expected_counts = integrity_summary.get("expected_counts") or {}
    if expected_counts.get("checked"):
        _record(
            "node_edge_counts_match_compiler_ir",
            bool(expected_counts.get("node_count_matches")) and bool(expected_counts.get("edge_count_matches")),
        )

    report.passed_checks = passed
    report.failed_checks = failed
    report.status = "fail" if (report.errors or failed) else "pass"

    report.statistics = {
        "total_nodes": node_summary.get("total", 0),
        "total_edges": edge_summary.get("total", 0),
        "total_errors": len(report.errors),
        "total_warnings": len(report.warnings),
        "total_checks": len(passed) + len(failed),
        "passed_check_count": len(passed),
        "failed_check_count": len(failed),
        "compiler_cross_check_performed": compiler_registry_manager is not None,
    }

    return report.to_dict()