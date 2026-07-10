"""
validation/system_integrity.py — Phase D1: System Integrity Validation.

SCOPE (Task 3/Task 4): this module validates consistency ACROSS the
complete compiler pipeline -- Phase A Canonical Objects, Compiler
Registries, Compiler Relationships, Knowledge Graph Nodes, Knowledge
Graph Edges, Compiler Manifest/Statistics/Fingerprints, and Knowledge
Graph Manifest/Statistics/Fingerprints -- treated as ONE integrated
system. This is explicitly NOT a re-implementation of Compiler
Validation (compiler/validation.py's own `validate_compiler_state()`)
or Knowledge Graph Validation (knowledge_graph/validation.py's own
`validate_knowledge_graph()`); both already exist, both already run
earlier in the pipeline, and both are frozen. Every check below either:

  (a) reads a verdict/count/summary those two passes (or the manifest/
      statistics/fingerprints/readiness/build-summary passes downstream
      of them) already computed, and cross-checks it against the
      equivalent value from a *different* artifact in the chain above
      (e.g. does a Knowledge Graph Build Summary's own `graph_
      fingerprint` agree with the graph fingerprint actually generated
      this build?), or reads the verdict outright when one already
      exists (e.g. whether the Knowledge Graph Manifest's own
      `node_count`/`edge_count` agree with the Knowledge Graph
      Statistics' own `total_nodes`/`total_edges` is knowledge_graph.
      fingerprints.generate_graph_readiness_report()'s own checks 7/8 --
      this module reads those two verdicts rather than comparing the
      manifest and statistics a second time itself), or

  (b) performs one genuinely NEW cross-artifact check that no single
      existing pass owns because it spans two artifacts neither
      Compiler Validation nor Knowledge Graph Validation individually
      has both of in scope (e.g. "is every graph node reachable from at
      least one edge" spans the node registry AND the edge registry
      together, at the whole-graph level, not per-edge).

Nothing in this module ever calls `.insert()`, `.update()`, `.upsert()`,
`.remove()`, or `.clear()` on any registry, and nothing here recomputes
a manifest, a statistics block, a fingerprint, a readiness report, or a
build summary from scratch -- every one of those is read, as-given, from
the caller. This mirrors every earlier phase's own "reads already-
computed state, never regenerates it" convention (see e.g.
compiler/build.py's own module docstring, or knowledge_graph/
fingerprints.py's).

READ-ONLY / DETERMINISTIC: like every validation pass in this codebase,
this module only ever calls cheap, read-only accessors on the registry
managers it is handed (`.names()`, `.has()`, `.get()`, `.contains()`,
`.size()`, `.ids()`, `.values()`) -- never a private index, never a
mutator. Given the same inputs, `validate_system_integrity()` always
returns the same report (modulo `generated_at`).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from compiler.registry_manager import RegistryManager as CompilerRegistryManager
from knowledge_graph.registries import (
    EDGE_REGISTRY_NAME,
    GRAPH_REGISTRY_NAMES,
    NODE_REGISTRY_NAME,
    GraphRegistryManager,
)


# --------------------------------------------------------------------------
# This module's own version marker -- independent of every other
# *_VERSION/*_SCHEMA_VERSION constant in this codebase (same convention
# compiler/validation.py's VALIDATION_VERSION and knowledge_graph/
# validation.py's GRAPH_VALIDATION_VERSION already establish, one layer
# down). Bump only if this module's own check set or report SHAPE
# changes.
# --------------------------------------------------------------------------
SYSTEM_INTEGRITY_VERSION = "D1.1"


# --------------------------------------------------------------------------
# Small issue-dict helpers -- same shape (`rule`, `message`, `severity`,
# optional `details`) every existing validator in this codebase already
# uses (compiler/validation.py's `_error()`/`_warning()`,
# knowledge_graph/validation.py's own same-named pair). Kept as plain
# dicts here too (not a ValidationIssue dataclass) for the same reason
# knowledge_graph/validation.py's own module docstring gives for doing
# the same: avoiding an intermediate dataclass + .to_dict() step this
# report's own to_dict() does not need.
# --------------------------------------------------------------------------

def _issue(severity: str, rule: str, message: str, **details: Any) -> Dict[str, Any]:
    issue: Dict[str, Any] = {"severity": severity, "rule": rule, "message": message}
    if details:
        issue["details"] = details
    return issue


def _error(rule: str, message: str, **details: Any) -> Dict[str, Any]:
    return _issue("error", rule, message, **details)


def _warning(rule: str, message: str, **details: Any) -> Dict[str, Any]:
    return _issue("warning", rule, message, **details)


# --------------------------------------------------------------------------
# Task 5: System Integrity Report
# --------------------------------------------------------------------------

@dataclass
class SystemIntegrityReport:
    """The full Phase D1 report artifact -- see this module's own
    docstring and Task 5's own "Suggested fields" list. Purely a data
    holder; all the actual checking happens in
    validate_system_integrity() below, which reads already-computed
    compiler/knowledge-graph state and folds it into one of these."""

    generated_at: str = ""
    integrity_version: str = SYSTEM_INTEGRITY_VERSION
    overall_status: str = "unknown"  # "pass" | "fail" | "unknown"
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    summary: str = ""
    registry_consistency: Dict[str, Any] = field(default_factory=dict)
    graph_consistency: Dict[str, Any] = field(default_factory=dict)
    fingerprint_consistency: Dict[str, Any] = field(default_factory=dict)
    manifest_consistency: Dict[str, Any] = field(default_factory=dict)
    statistics_consistency: Dict[str, Any] = field(default_factory=dict)
    build_summary_consistency: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _record(passed: List[str], failed: List[str], name: str, ok: bool) -> None:
    (passed if ok else failed).append(name)


def _find_readiness_check(
    readiness_report: Optional[Dict[str, Any]], name: str,
) -> Optional[Dict[str, Any]]:
    """Looks up one named check entry (`{"name": ..., "passed": ...,
    "detail": ...}`) inside a readiness report's own `checks` list --
    e.g. knowledge_graph.fingerprints.generate_graph_readiness_report()'s
    own `node_count_matches_statistics`/`edge_count_matches_statistics`
    checks. Returns None if the report is missing or does not carry a
    check under that name, so a caller can tell "verified and failed"
    apart from "never verified" (see _validate_statistics_consistency's
    own use of this, resolving Finding 1: READ the existing verdict,
    never recompute it)."""
    for check in (readiness_report or {}).get("checks") or []:
        if check.get("name") == name:
            return check
    return None


# --------------------------------------------------------------------------
# 1. Registry Consistency -- Phase A Canonical Objects <-> Compiler
#    Registries <-> Compiler Relationships <-> Knowledge Graph Nodes
# --------------------------------------------------------------------------

def _validate_registry_consistency(
    compiler_registry_manager: CompilerRegistryManager,
    compiler_validation_report: Optional[Dict[str, Any]],
    graph_registry_manager: GraphRegistryManager,
    knowledge_graph_validation_report: Optional[Dict[str, Any]],
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Cross-checks the Compiler Registries <-> Knowledge Graph Nodes
    link in the chain: required registries present on both sides, no
    duplicate ids/urns reported by either underlying validation pass,
    every graph node's compiler-object reference already confirmed
    resolvable (read from `knowledge_graph_validation_report`'s own
    node_summary -- NOT re-walked here), and registry-level object
    counts agreeing with graph-level node counts.

    Read-only: only `.names()` is called on either manager."""
    issues: List[Dict[str, Any]] = []

    compiler_registry_names = set(compiler_registry_manager.names())
    graph_registry_names = set(graph_registry_manager.names())
    missing_graph_registries = [n for n in GRAPH_REGISTRY_NAMES if n not in graph_registry_names]
    if missing_graph_registries:
        issues.append(_error(
            "missing_graph_registry",
            "system integrity: knowledge graph is missing required "
            "registrie(s): " + ", ".join(missing_graph_registries),
        ))

    # -- duplicate ids/urns already detected by Compiler Validation /
    # Knowledge Graph Validation -- read, never recomputed. --
    compiler_registry_summary = (compiler_validation_report or {}).get("registry_summary") or {}
    compiler_duplicate_ids = sum(
        rs.get("duplicate_ids", 0) for rs in compiler_registry_summary.values()
    )
    compiler_duplicate_urns = sum(
        rs.get("duplicate_urns", 0) for rs in compiler_registry_summary.values()
    )
    node_summary = (knowledge_graph_validation_report or {}).get("node_summary") or {}
    edge_summary = (knowledge_graph_validation_report or {}).get("edge_summary") or {}
    graph_duplicate_ids = node_summary.get("duplicate_ids", 0) + edge_summary.get("duplicate_ids", 0)
    graph_duplicate_urns = node_summary.get("duplicate_urns", 0) + edge_summary.get("duplicate_urns", 0)

    if compiler_duplicate_ids:
        issues.append(_error(
            "compiler_duplicate_ids",
            f"system integrity: Compiler Validation reported "
            f"{compiler_duplicate_ids} duplicate id(s) across compiler "
            "registries",
        ))
    if compiler_duplicate_urns:
        issues.append(_error(
            "compiler_duplicate_urns",
            f"system integrity: Compiler Validation reported "
            f"{compiler_duplicate_urns} duplicate urn(s) across compiler "
            "registries",
        ))
    if graph_duplicate_ids:
        issues.append(_error(
            "graph_duplicate_ids",
            f"system integrity: Knowledge Graph Validation reported "
            f"{graph_duplicate_ids} duplicate id(s) across node/edge "
            "registries",
        ))
    if graph_duplicate_urns:
        issues.append(_error(
            "graph_duplicate_urns",
            f"system integrity: Knowledge Graph Validation reported "
            f"{graph_duplicate_urns} duplicate urn(s) across node/edge "
            "registries",
        ))

    # -- every graph node maps to exactly one compiler object: Knowledge
    # Graph Validation already resolves every node's compiler_object_id
    # against Compiler IR when it is run with `compiler_registry_manager`
    # supplied (knowledge_graph/validation.py's own
    # `invalid_compiler_reference_count` / `dangling_compiler_object_
    # reference` checks) -- read that verdict here, never re-walk the
    # node registry to re-derive it. --
    cross_check_performed = bool(node_summary.get("compiler_cross_check_performed"))
    invalid_compiler_references = node_summary.get("invalid_compiler_reference_count", 0)
    if not cross_check_performed:
        issues.append(_warning(
            "compiler_reference_cross_check_not_performed",
            "system integrity: Knowledge Graph Validation was not run "
            "with a Compiler RegistryManager, so node -> compiler-object "
            "reference resolution was never verified for this build",
        ))
    elif invalid_compiler_references:
        issues.append(_error(
            "invalid_compiler_object_references",
            f"system integrity: {invalid_compiler_references} graph "
            "node(s) reference a compiler object that could not be "
            "resolved",
        ))

    # -- registry counts match graph counts: Knowledge Graph Validation's
    # own `expected_counts` block (populated only when a compiler
    # registry manager was supplied) already compares node/edge counts
    # against Compiler IR's own object/relationship counts -- read that
    # verdict, never recompute the counts ourselves. --
    integrity_summary = (knowledge_graph_validation_report or {}).get("integrity_summary") or {}
    expected_counts = integrity_summary.get("expected_counts") or {}
    counts_checked = bool(expected_counts.get("checked"))
    node_count_matches = bool(expected_counts.get("node_count_matches"))
    edge_count_matches = bool(expected_counts.get("edge_count_matches"))
    if counts_checked and not node_count_matches:
        issues.append(_error(
            "node_count_mismatch",
            "system integrity: knowledge graph node count does not "
            "match Compiler IR's own canonical object count",
        ))
    if counts_checked and not edge_count_matches:
        issues.append(_error(
            "edge_count_mismatch",
            "system integrity: knowledge graph edge count does not "
            "match Compiler IR's own relationship count",
        ))

    summary = {
        "compiler_registries_present": sorted(compiler_registry_names),
        "graph_registries_present": sorted(graph_registry_names),
        "missing_graph_registries": missing_graph_registries,
        "compiler_duplicate_ids": compiler_duplicate_ids,
        "compiler_duplicate_urns": compiler_duplicate_urns,
        "graph_duplicate_ids": graph_duplicate_ids,
        "graph_duplicate_urns": graph_duplicate_urns,
        "compiler_reference_cross_check_performed": cross_check_performed,
        "invalid_compiler_object_references": invalid_compiler_references,
        "node_edge_counts_checked": counts_checked,
        "node_count_matches": node_count_matches,
        "edge_count_matches": edge_count_matches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 2. Graph Consistency -- Knowledge Graph Nodes <-> Knowledge Graph Edges
# --------------------------------------------------------------------------

def _validate_graph_consistency(
    graph_registry_manager: GraphRegistryManager,
    knowledge_graph_validation_report: Optional[Dict[str, Any]],
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Cross-checks the Knowledge Graph Nodes <-> Knowledge Graph Edges
    link: no orphan/dangling edges (read from Knowledge Graph
    Validation's own edge_summary -- not re-walked), plus one genuinely
    new whole-graph check neither Compiler Validation nor Knowledge
    Graph Validation owns individually: are there graph nodes that no
    edge, in either direction, ever references (a node with zero
    incident edges). This is a system-level, informational check
    (a topic/root node can legitimately have no incoming edges), so it
    is reported as a warning, never an error.

    Read-only: only `.has()`/`.get()`/`.ids()`/`.values()` are called on
    `graph_registry_manager`; nothing is inserted, updated, or removed."""
    issues: List[Dict[str, Any]] = []

    edge_summary = (knowledge_graph_validation_report or {}).get("edge_summary") or {}
    dangling_edges = edge_summary.get("dangling", 0)
    orphan_edges = edge_summary.get("orphans", 0)
    if dangling_edges:
        issues.append(_error(
            "dangling_graph_edges",
            f"system integrity: Knowledge Graph Validation reported "
            f"{dangling_edges} dangling edge(s) (edges whose source "
            "and/or target node does not exist)",
        ))

    orphan_node_ids: List[str] = []
    if graph_registry_manager.has(NODE_REGISTRY_NAME) and graph_registry_manager.has(EDGE_REGISTRY_NAME):
        node_registry = graph_registry_manager.get(NODE_REGISTRY_NAME)
        edge_registry = graph_registry_manager.get(EDGE_REGISTRY_NAME)
        referenced_node_ids: set = set()
        for edge in edge_registry.values():
            source_id = edge.get("source_node_id") if isinstance(edge, dict) else getattr(edge, "source_node_id", None)
            target_id = edge.get("target_node_id") if isinstance(edge, dict) else getattr(edge, "target_node_id", None)
            if source_id:
                referenced_node_ids.add(source_id)
            if target_id:
                referenced_node_ids.add(target_id)
        orphan_node_ids = [n for n in node_registry.ids() if n not in referenced_node_ids]
        if orphan_node_ids:
            issues.append(_warning(
                "orphan_graph_nodes",
                f"system integrity: {len(orphan_node_ids)} graph node(s) "
                "are not referenced as the source or target of any edge",
                orphan_node_count=len(orphan_node_ids),
            ))

    summary = {
        "dangling_edges": dangling_edges,
        "orphan_edges": orphan_edges,
        "orphan_node_count": len(orphan_node_ids),
    }
    return issues, summary


# --------------------------------------------------------------------------
# 3. Fingerprint Consistency -- Compiler Fingerprints <-> Knowledge Graph
#    Fingerprints
# --------------------------------------------------------------------------

def _validate_fingerprint_consistency(
    compiler_registry_manager: CompilerRegistryManager,
    compiler_registry_fingerprints: Optional[Dict[str, str]],
    compiler_fingerprint: Optional[str],
    graph_registry_manager: GraphRegistryManager,
    knowledge_graph_registry_fingerprints: Optional[Dict[str, str]],
    knowledge_graph_fingerprint: Optional[str],
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Fingerprints exist for every registry on both sides, and one
    overall fingerprint exists for each layer -- read from the fingerprint
    dicts already generated by compiler/fingerprints.py and
    knowledge_graph/fingerprints.py, never recomputed here (no
    serialize()/hash call happens in this module)."""
    issues: List[Dict[str, Any]] = []

    compiler_registry_fingerprints = compiler_registry_fingerprints or {}
    knowledge_graph_registry_fingerprints = knowledge_graph_registry_fingerprints or {}

    missing_compiler_fp = [
        n for n in compiler_registry_manager.names() if n not in compiler_registry_fingerprints
    ]
    missing_graph_fp = [
        n for n in graph_registry_manager.names() if n not in knowledge_graph_registry_fingerprints
    ]
    if missing_compiler_fp:
        issues.append(_error(
            "missing_compiler_registry_fingerprints",
            "system integrity: no fingerprint generated for compiler "
            "registrie(s): " + ", ".join(missing_compiler_fp),
        ))
    if missing_graph_fp:
        issues.append(_error(
            "missing_graph_registry_fingerprints",
            "system integrity: no fingerprint generated for knowledge "
            "graph registrie(s): " + ", ".join(missing_graph_fp),
        ))
    if not compiler_fingerprint:
        issues.append(_error(
            "missing_compiler_fingerprint",
            "system integrity: no overall compiler fingerprint was "
            "generated",
        ))
    if not knowledge_graph_fingerprint:
        issues.append(_error(
            "missing_graph_fingerprint",
            "system integrity: no overall knowledge graph fingerprint "
            "was generated",
        ))

    summary = {
        "compiler_registry_fingerprint_count": len(compiler_registry_fingerprints),
        "graph_registry_fingerprint_count": len(knowledge_graph_registry_fingerprints),
        "missing_compiler_registry_fingerprints": missing_compiler_fp,
        "missing_graph_registry_fingerprints": missing_graph_fp,
        "compiler_fingerprint_present": bool(compiler_fingerprint),
        "graph_fingerprint_present": bool(knowledge_graph_fingerprint),
    }
    return issues, summary


# --------------------------------------------------------------------------
# 4. Manifest Consistency -- Compiler Manifest <-> Knowledge Graph
#    Manifest
# --------------------------------------------------------------------------

def _validate_manifest_consistency(
    compiler_manifest: Optional[Dict[str, Any]],
    knowledge_graph_manifest: Optional[Dict[str, Any]],
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Both manifests exist, and the Knowledge Graph Manifest's own
    provenance -- `source_chapter_identifier` directly, and the compiler
    version it was built from via `node_registry_versions["source_
    compiler"]` (knowledge_graph/build.py's own
    generate_knowledge_graph_manifest() folds
    `KnowledgeGraphMetadata.source_compiler_version` in there rather than
    as a new top-level manifest field -- see that module's own docstring
    note; no new metadata is invented here, this reuses that existing
    field) -- agree with the Compiler Manifest they were derived from.
    This is the one link in the chain neither manifest generator
    cross-checks against the other itself (each is generated
    independently, one phase apart)."""
    issues: List[Dict[str, Any]] = []
    compiler_manifest = compiler_manifest or {}
    knowledge_graph_manifest = knowledge_graph_manifest or {}

    if not compiler_manifest:
        issues.append(_error("missing_compiler_manifest", "system integrity: no compiler manifest available"))
    if not knowledge_graph_manifest:
        issues.append(_error("missing_graph_manifest", "system integrity: no knowledge graph manifest available"))

    chapter_identifier_matches = True
    if compiler_manifest and knowledge_graph_manifest:
        compiler_chapter = compiler_manifest.get("chapter_identifier")
        graph_chapter = knowledge_graph_manifest.get("source_chapter_identifier")
        if compiler_chapter != graph_chapter:
            chapter_identifier_matches = False
            issues.append(_error(
                "chapter_identifier_mismatch",
                f"system integrity: compiler manifest chapter_identifier "
                f"{compiler_chapter!r} does not match knowledge graph "
                f"manifest source_chapter_identifier {graph_chapter!r}",
            ))

    compiler_version_matches = True
    if compiler_manifest and knowledge_graph_manifest:
        compiler_version = compiler_manifest.get("compiler_version")
        graph_source_compiler_version = (
            knowledge_graph_manifest.get("node_registry_versions") or {}
        ).get("source_compiler")
        if compiler_version != graph_source_compiler_version:
            compiler_version_matches = False
            issues.append(_error(
                "compiler_version_mismatch",
                f"system integrity: compiler manifest compiler_version "
                f"{compiler_version!r} does not match knowledge graph "
                f"manifest node_registry_versions['source_compiler'] "
                f"{graph_source_compiler_version!r}",
            ))

    summary = {
        "compiler_manifest_present": bool(compiler_manifest),
        "graph_manifest_present": bool(knowledge_graph_manifest),
        "chapter_identifier_matches": chapter_identifier_matches,
        "compiler_version_matches": compiler_version_matches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 5. Statistics Consistency -- Manifest counts <-> Statistics counts, on
#    both the Compiler layer and the Knowledge Graph layer
# --------------------------------------------------------------------------

def _validate_statistics_consistency(
    compiler_manifest: Optional[Dict[str, Any]],
    compiler_statistics: Optional[Dict[str, Any]],
    knowledge_graph_statistics: Optional[Dict[str, Any]],
    knowledge_graph_readiness_report: Optional[Dict[str, Any]],
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Manifest counts match statistics counts -- Task 4's own rule,
    checked on both layers.

    Compiler layer: `compiler_manifest["object_count"]` against
    `compiler_statistics["total_objects"]`, computed here -- there is no
    equivalent check on compiler.fingerprints.
    generate_compiler_readiness_report()'s own seven-check list
    (required_registries_exist / validation_completed / manifest_exists
    / statistics_exist / registry_fingerprints_generated / compiler_
    fingerprint_generated / relationships_registry_available), so this
    is a genuinely new cross-check, not a duplicate of one Compiler
    Readiness already makes.

    Knowledge Graph layer: NOT recomputed here. knowledge_graph.
    fingerprints.generate_graph_readiness_report() already runs this
    exact comparison as its own checks 7/8
    (`node_count_matches_statistics` / `edge_count_matches_statistics`)
    -- this function reads those two verdicts from `knowledge_graph_
    readiness_report["checks"]` via `_find_readiness_check()` instead of
    comparing `knowledge_graph_manifest`/`knowledge_graph_statistics`
    itself a second time (audit finding: this function previously
    duplicated that comparison independently)."""
    issues: List[Dict[str, Any]] = []
    compiler_manifest = compiler_manifest or {}
    compiler_statistics = compiler_statistics or {}
    knowledge_graph_statistics = knowledge_graph_statistics or {}

    if not compiler_statistics:
        issues.append(_error("missing_compiler_statistics", "system integrity: no compiler statistics available"))
    if not knowledge_graph_statistics:
        issues.append(_error("missing_graph_statistics", "system integrity: no knowledge graph statistics available"))

    compiler_object_counts_match = True
    if compiler_manifest and compiler_statistics:
        manifest_objects = compiler_manifest.get("object_count")
        statistics_objects = compiler_statistics.get("total_objects")
        if manifest_objects != statistics_objects:
            compiler_object_counts_match = False
            issues.append(_error(
                "compiler_manifest_statistics_object_count_mismatch",
                f"system integrity: compiler manifest object_count "
                f"{manifest_objects!r} does not match compiler statistics "
                f"total_objects {statistics_objects!r}",
            ))

    # -- graph layer: read, don't recompute (Finding 1) --
    node_count_check = _find_readiness_check(
        knowledge_graph_readiness_report, "node_count_matches_statistics",
    )
    edge_count_check = _find_readiness_check(
        knowledge_graph_readiness_report, "edge_count_matches_statistics",
    )
    graph_node_counts_verified = node_count_check is not None
    graph_edge_counts_verified = edge_count_check is not None
    graph_node_counts_match = graph_node_counts_verified and bool(node_count_check["passed"])
    graph_edge_counts_match = graph_edge_counts_verified and bool(edge_count_check["passed"])

    if graph_node_counts_verified and not graph_node_counts_match:
        issues.append(_error(
            "graph_manifest_statistics_node_count_mismatch",
            "system integrity: knowledge graph readiness reported "
            "node_count_matches_statistics=False"
            + (f" ({node_count_check.get('detail')})" if node_count_check.get("detail") else ""),
        ))
    elif not graph_node_counts_verified:
        issues.append(_warning(
            "graph_node_count_consistency_not_verified",
            "system integrity: knowledge graph readiness report does "
            "not carry a node_count_matches_statistics check result to "
            "consume",
        ))

    if graph_edge_counts_verified and not graph_edge_counts_match:
        issues.append(_error(
            "graph_manifest_statistics_edge_count_mismatch",
            "system integrity: knowledge graph readiness reported "
            "edge_count_matches_statistics=False"
            + (f" ({edge_count_check.get('detail')})" if edge_count_check.get("detail") else ""),
        ))
    elif not graph_edge_counts_verified:
        issues.append(_warning(
            "graph_edge_count_consistency_not_verified",
            "system integrity: knowledge graph readiness report does "
            "not carry an edge_count_matches_statistics check result to "
            "consume",
        ))

    summary = {
        "compiler_statistics_present": bool(compiler_statistics),
        "graph_statistics_present": bool(knowledge_graph_statistics),
        "compiler_object_counts_match": compiler_object_counts_match,
        "graph_node_counts_verified": graph_node_counts_verified,
        "graph_node_counts_match": graph_node_counts_match,
        "graph_edge_counts_verified": graph_edge_counts_verified,
        "graph_edge_counts_match": graph_edge_counts_match,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 6. Build Summary Consistency -- Readiness Reports & Build Summaries,
#    both layers
# --------------------------------------------------------------------------

def _validate_build_summary_consistency(
    compiler_readiness_report: Optional[Dict[str, Any]],
    compiler_build_summary: Optional[Dict[str, Any]],
    compiler_fingerprint: Optional[str],
    knowledge_graph_readiness_report: Optional[Dict[str, Any]],
    knowledge_graph_build_summary: Optional[Dict[str, Any]],
    knowledge_graph_fingerprint: Optional[str],
) -> "tuple[List[Dict[str, Any]], Dict[str, Any]]":
    """Readiness reports exist, build summaries exist (Task 4's own two
    rules), and each build summary's own `*_fingerprint` field agrees
    with the overall fingerprint already generated for that layer --
    the one link in the chain that would otherwise let a build summary
    silently drift from the fingerprint it claims to describe."""
    issues: List[Dict[str, Any]] = []
    compiler_readiness_report = compiler_readiness_report or {}
    compiler_build_summary = compiler_build_summary or {}
    knowledge_graph_readiness_report = knowledge_graph_readiness_report or {}
    knowledge_graph_build_summary = knowledge_graph_build_summary or {}

    if not compiler_readiness_report:
        issues.append(_error("missing_compiler_readiness_report", "system integrity: no compiler readiness report available"))
    if not knowledge_graph_readiness_report:
        issues.append(_error("missing_graph_readiness_report", "system integrity: no knowledge graph readiness report available"))
    if not compiler_build_summary:
        issues.append(_error("missing_compiler_build_summary", "system integrity: no compiler build summary available"))
    if not knowledge_graph_build_summary:
        issues.append(_error("missing_graph_build_summary", "system integrity: no knowledge graph build summary available"))

    compiler_fingerprint_matches = True
    if compiler_build_summary:
        summary_fp = compiler_build_summary.get("compiler_fingerprint")
        if summary_fp != compiler_fingerprint:
            compiler_fingerprint_matches = False
            issues.append(_error(
                "compiler_build_summary_fingerprint_mismatch",
                "system integrity: compiler build summary's own "
                "compiler_fingerprint does not match the compiler "
                "fingerprint generated this build",
            ))

    graph_fingerprint_matches = True
    if knowledge_graph_build_summary:
        summary_fp = knowledge_graph_build_summary.get("graph_fingerprint")
        if summary_fp != knowledge_graph_fingerprint:
            graph_fingerprint_matches = False
            issues.append(_error(
                "graph_build_summary_fingerprint_mismatch",
                "system integrity: knowledge graph build summary's own "
                "graph_fingerprint does not match the graph fingerprint "
                "generated this build",
            ))

    summary = {
        "compiler_readiness_report_present": bool(compiler_readiness_report),
        "graph_readiness_report_present": bool(knowledge_graph_readiness_report),
        "compiler_build_summary_present": bool(compiler_build_summary),
        "graph_build_summary_present": bool(knowledge_graph_build_summary),
        "compiler_ready": bool(compiler_readiness_report.get("ready")),
        "graph_ready": bool(knowledge_graph_readiness_report.get("ready")),
        "compiler_build_summary_fingerprint_matches": compiler_fingerprint_matches,
        "graph_build_summary_fingerprint_matches": graph_fingerprint_matches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Task 6/7: single pipeline.py integration point
# --------------------------------------------------------------------------

def validate_system_integrity(
    compiler_registry_manager: CompilerRegistryManager,
    graph_registry_manager: GraphRegistryManager,
    *,
    compiler_validation_report: Optional[Dict[str, Any]] = None,
    compiler_manifest: Optional[Dict[str, Any]] = None,
    compiler_statistics: Optional[Dict[str, Any]] = None,
    compiler_registry_fingerprints: Optional[Dict[str, str]] = None,
    compiler_fingerprint: Optional[str] = None,
    compiler_readiness_report: Optional[Dict[str, Any]] = None,
    compiler_build_summary: Optional[Dict[str, Any]] = None,
    knowledge_graph_validation_report: Optional[Dict[str, Any]] = None,
    knowledge_graph_manifest: Optional[Dict[str, Any]] = None,
    knowledge_graph_statistics: Optional[Dict[str, Any]] = None,
    knowledge_graph_registry_fingerprints: Optional[Dict[str, str]] = None,
    knowledge_graph_fingerprint: Optional[str] = None,
    knowledge_graph_readiness_report: Optional[Dict[str, Any]] = None,
    knowledge_graph_build_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase D1's single pipeline.py integration point (mirrors
    compiler.validation.validate_compiler_state()'s and knowledge_graph.
    validation.validate_knowledge_graph()'s own shape, one layer up).
    Must run AFTER Phase C is fully complete -- after
    knowledge_graph.finalize.finalize_knowledge_graph() -- so every
    artifact in the chain this module cross-checks (Compiler Manifest/
    Statistics/Fingerprints/Readiness/Build-Summary, Knowledge Graph
    Manifest/Statistics/Fingerprints/Readiness/Build-Summary) already
    exists to read from. See pipeline.py's own comment at the call site.

    Read-only over every argument: no registry is inserted into,
    updated, or removed from; no manifest/statistics/fingerprint/
    readiness-report/build-summary dict anywhere is mutated. Every
    optional artifact defaults to None so this function can also be
    called against a partial/hand-built fixture (e.g. from a test).
    A missing manifest/statistics/fingerprint/readiness-report/build-
    summary is reported as a failed check (an error, plus the relevant
    `*_present` field set False in that check group's own summary) --
    never guessed at. A check that depends on a *verdict* another pass
    was supposed to compute but didn't (e.g. Knowledge Graph Readiness
    run without its own node/edge count checks present) is instead
    OMITTED from both `checks_passed` and `checks_failed`, with a
    warning explaining why -- distinct from a failure, since D1 itself
    never re-derives what that verdict would have been (see Finding 3
    in this module's own change history: a check that never actually
    ran must not be reported as passed, and reporting it as failed would
    equally misrepresent something D1 never checked).

    Returned as a plain dict (report.to_dict()), matching every earlier
    phase's own "plain, storable dict" convention, and so it can be
    handed directly to validation.state.set_current_system_integrity_
    report()."""
    report = SystemIntegrityReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    passed: List[str] = []
    failed: List[str] = []
    all_issues: List[Dict[str, Any]] = []

    registry_issues, registry_consistency = _validate_registry_consistency(
        compiler_registry_manager, compiler_validation_report,
        graph_registry_manager, knowledge_graph_validation_report,
    )
    all_issues.extend(registry_issues)
    report.registry_consistency = registry_consistency
    _record(passed, failed, "no_missing_graph_registries", not registry_consistency["missing_graph_registries"])
    _record(passed, failed, "no_duplicate_ids", registry_consistency["compiler_duplicate_ids"] == 0 and registry_consistency["graph_duplicate_ids"] == 0)
    _record(passed, failed, "no_duplicate_urns", registry_consistency["compiler_duplicate_urns"] == 0 and registry_consistency["graph_duplicate_urns"] == 0)
    if registry_consistency["compiler_reference_cross_check_performed"]:
        _record(passed, failed, "no_invalid_compiler_object_references", registry_consistency["invalid_compiler_object_references"] == 0)
    # else: the cross-check never ran (see the compiler_reference_cross_
    # check_not_performed warning _validate_registry_consistency() already
    # emits above) -- omitted from both checks_passed and checks_failed
    # rather than defaulting to "passed" (Finding 3: do not report a
    # skipped check as passed).
    if registry_consistency["node_edge_counts_checked"]:
        _record(passed, failed, "registry_counts_match_graph_counts", registry_consistency["node_count_matches"] and registry_consistency["edge_count_matches"])

    graph_issues, graph_consistency = _validate_graph_consistency(
        graph_registry_manager, knowledge_graph_validation_report,
    )
    all_issues.extend(graph_issues)
    report.graph_consistency = graph_consistency
    _record(passed, failed, "no_dangling_graph_edges", graph_consistency["dangling_edges"] == 0)
    _record(passed, failed, "no_orphan_graph_edges", graph_consistency["orphan_edges"] == 0)

    fingerprint_issues, fingerprint_consistency = _validate_fingerprint_consistency(
        compiler_registry_manager, compiler_registry_fingerprints, compiler_fingerprint,
        graph_registry_manager, knowledge_graph_registry_fingerprints, knowledge_graph_fingerprint,
    )
    all_issues.extend(fingerprint_issues)
    report.fingerprint_consistency = fingerprint_consistency
    _record(passed, failed, "fingerprints_exist", (
        not fingerprint_consistency["missing_compiler_registry_fingerprints"]
        and not fingerprint_consistency["missing_graph_registry_fingerprints"]
        and fingerprint_consistency["compiler_fingerprint_present"]
        and fingerprint_consistency["graph_fingerprint_present"]
    ))

    manifest_issues, manifest_consistency = _validate_manifest_consistency(
        compiler_manifest, knowledge_graph_manifest,
    )
    all_issues.extend(manifest_issues)
    report.manifest_consistency = manifest_consistency
    _record(passed, failed, "manifests_exist", manifest_consistency["compiler_manifest_present"] and manifest_consistency["graph_manifest_present"])
    _record(passed, failed, "manifest_chapter_identifiers_consistent", manifest_consistency["chapter_identifier_matches"])
    _record(passed, failed, "manifest_compiler_versions_consistent", manifest_consistency["compiler_version_matches"])

    statistics_issues, statistics_consistency = _validate_statistics_consistency(
        compiler_manifest, compiler_statistics,
        knowledge_graph_statistics, knowledge_graph_readiness_report,
    )
    all_issues.extend(statistics_issues)
    report.statistics_consistency = statistics_consistency
    _record(passed, failed, "statistics_exist", statistics_consistency["compiler_statistics_present"] and statistics_consistency["graph_statistics_present"])
    _record(passed, failed, "compiler_manifest_counts_match_statistics", statistics_consistency["compiler_object_counts_match"])
    if statistics_consistency["graph_node_counts_verified"] and statistics_consistency["graph_edge_counts_verified"]:
        _record(passed, failed, "graph_manifest_counts_match_statistics", (
            statistics_consistency["graph_node_counts_match"]
            and statistics_consistency["graph_edge_counts_match"]
        ))
    # else: knowledge graph readiness did not carry one or both of the
    # node/edge count checks to consume -- the graph_node_count_
    # consistency_not_verified/graph_edge_count_consistency_not_verified
    # warnings _validate_statistics_consistency() already emits cover
    # that case; omitted from both checks_passed and checks_failed for
    # the same reason as no_invalid_compiler_object_references above
    # (Finding 3's own principle, applied consistently here too).

    build_summary_issues, build_summary_consistency = _validate_build_summary_consistency(
        compiler_readiness_report, compiler_build_summary, compiler_fingerprint,
        knowledge_graph_readiness_report, knowledge_graph_build_summary, knowledge_graph_fingerprint,
    )
    all_issues.extend(build_summary_issues)
    report.build_summary_consistency = build_summary_consistency
    _record(passed, failed, "readiness_reports_exist", build_summary_consistency["compiler_readiness_report_present"] and build_summary_consistency["graph_readiness_report_present"])
    _record(passed, failed, "build_summaries_exist", build_summary_consistency["compiler_build_summary_present"] and build_summary_consistency["graph_build_summary_present"])
    _record(passed, failed, "build_summary_fingerprints_consistent", build_summary_consistency["compiler_build_summary_fingerprint_matches"] and build_summary_consistency["graph_build_summary_fingerprint_matches"])

    report.errors = [i for i in all_issues if i["severity"] == "error"]
    report.warnings = [i for i in all_issues if i["severity"] == "warning"]
    report.checks_passed = passed
    report.checks_failed = failed
    report.overall_status = "fail" if (report.errors or failed) else "pass"

    total_checks = len(passed) + len(failed)
    report.summary = (
        f"System integrity {report.overall_status}: {total_checks} "
        f"check{'s' if total_checks != 1 else ''} run "
        f"({len(passed)} passed, {len(failed)} failed); "
        f"{len(report.errors)} error(s), {len(report.warnings)} "
        "warning(s) across the complete compiler pipeline."
    )

    return report.to_dict()