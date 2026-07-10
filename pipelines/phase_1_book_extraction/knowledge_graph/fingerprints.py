"""
knowledge_graph/fingerprints.py — Phase C4.2: Knowledge Graph
Fingerprints & Readiness.

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C0, Phase C1, Phase C2, Phase C3, and Phase C4.1 are frozen --
this module does not redesign GraphRegistryManager (knowledge_graph/
registries.py), knowledge_graph/state.py's existing _CURRENT_*
lifecycle, knowledge_graph/node.py, knowledge_graph/edge.py,
knowledge_graph/build_nodes.py, knowledge_graph/build_edges.py,
knowledge_graph/validation.py, or knowledge_graph/build.py. It also
does not touch compiler/* or json_writer.py / schemas/chapter_schema.py
/ ChapterJSON. It ONLY adds a fifth, read-only Knowledge Graph pass
that DERIVES deterministic fingerprints and a readiness verdict from
what Phases C1-C4.1 already computed -- it never generates, repairs,
or mutates a single node, edge, or Compiler IR field, and it never
inserts into, updates, or removes from any graph registry.

This module is the direct Knowledge Graph analogue of compiler/
fingerprints.py (Phase B5.2) -- same three-task split (registry
fingerprints -> one overall fingerprint -> a read-only readiness
report), same "reuse, don't recompute" discipline, applied one layer
up. Where compiler/fingerprints.py folds compiler.build's own manifest/
statistics into the compiler fingerprint, this module folds
knowledge_graph.build's own manifest/statistics (Phase C4.1) into the
graph fingerprint.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
Graph Build Summary, not a Final Graph Status Report, not Graph
Finalization, not Graph Queries, not Graph Traversal, not any other
Graph Algorithm, not Graph Optimization, not Graph Caching, and not
Graph Serialization. The readiness report below is READ-ONLY: it
inspects and reports, it never fixes anything it finds missing or
failing.

REUSE, DON'T RECOMPUTE: registry fingerprints are derived from each
graph registry's own `CanonicalRegistry.serialize()` output (already
deterministic, insertion-ordered -- see compiler/registry.py's own
module docstring, inherited unchanged by GraphRegistryManager), never
from a hand-rolled re-walk of registry internals. The graph fingerprint
is derived from the registry fingerprints plus the SAME `manifest`/
`statistics` dicts knowledge_graph.build.generate_knowledge_graph_
manifest()/generate_knowledge_graph_statistics() already produced this
chapter (Phase C4.1) -- nothing here re-derives a manifest or
statistics field a second time. The readiness report's checks read
`graph_registry_manager.names()`/`.has()` (GraphRegistryManager's own
cheap, inherited accessors), `validation_report`'s own `overall_status`
field (Phase C3), and the fingerprints/manifest/statistics already
computed above -- nothing here re-validates the graph itself (that is
Phase C3's job, not this module's) and nothing here re-scans the node/
edge registries for counts already carried on `manifest`/`statistics`.

VOLATILE FIELD FILTERING: this module reuses compiler.fingerprints.
VOLATILE_KEYS verbatim rather than redeclaring an equivalent set --
the exact same key names (`generated_at`, `created_at`, `timestamp`,
...) are volatile here for the exact same reasons that module's own
docstring already documents, PLUS they are the same names that flow
into Knowledge Graph artifacts too: every KG node carries a `provenance`
dict copied from its source Compiler IR item (knowledge_graph/
build_nodes.py), and that provenance dict carries a `timestamp` field
(modules/canonical.py) the same way Compiler IR's own provenance does;
every KG manifest/statistics/validation-report dict carries its own
top-level `generated_at` (knowledge_graph/schema.py), the same way
CompilerManifest/CompilerStatistics/ValidationReport do one layer
down. Reusing the one constant rather than duplicating it means a
future addition to that closed set (a new `whatever_at`-shaped field
some later compiler-side phase introduces) is picked up here too,
automatically, without this module needing its own separate edit.

DETERMINISM GUARANTEE: `generate_registry_fingerprints()` and
`generate_graph_fingerprint()` are pure functions of already-computed,
deterministic Knowledge Graph state. Same graph (same registries, same
manifest/statistics content, modulo volatile fields) -> byte-identical
canonical JSON -> the same SHA-256 digest, on this run and every future
one, on any machine. Different graph -> a different canonical JSON
payload (with overwhelming probability, i.e. barring a SHA-256
collision) -> a different digest. Nothing here reads a timestamp, a
memory address, an object id(), or Python's hash-randomized dict/set
iteration order into a fingerprint -- every registry/manifest/
statistics dict involved already iterates in deterministic (insertion
or explicit sort) order per its own owning module's docstring, and
`_canonical_json()` below additionally `sort_keys=True`s every dict
before hashing, so even a hypothetical future producer that emits keys
in a different order still fingerprints identically.

TASK 3 -- Registry Fingerprints: `generate_registry_fingerprints(
graph_registry_manager)` returns one SHA-256 hex digest per registry
`graph_registry_manager` owns (nodes, edges, metadata -- same keys as
`.names()`), each digest derived from that registry's own `serialize()`
output with volatile fields stripped.

TASK 4 -- Knowledge Graph Fingerprint: `generate_graph_fingerprint(...)`
folds every registry fingerprint (Task 3) together with the C4.1
manifest and statistics (volatile fields stripped) into one SHA-256 hex
digest representing the complete graph build for this chapter.

TASK 5 -- Knowledge Graph Readiness Report: `generate_graph_readiness_
report(...)` runs eight read-only checks (required registries exist,
graph validation passed, graph manifest exists, graph statistics exist,
registry fingerprints generated, graph fingerprint generated, node
count matches statistics, edge count matches statistics) and returns a
structured, read-only verdict -- `ready` (task's own ninth bullet,
"graph ready for downstream phases") is the DERIVED overall verdict
those eight checks produce (`ready = all checks passed`), exactly
mirroring compiler.fingerprints.generate_compiler_readiness_report()'s
own `ready = not failed_checks` derivation, not a ninth, independently
-computed check. It never repairs anything it finds missing -- a
failed check is reported, not fixed.

NO SCHEMA REDESIGN: `knowledge_graph.schema.KnowledgeGraphReadinessReport`
(Phase C0 placeholder) is reused exactly as declared -- no field added,
renamed, or removed (Task 1's own "reuse them instead of creating new
ones"). Its `checks: List[Dict[str, Any]]` field (a different shape
from compiler/fingerprints.py's own separate `passed_checks`/
`failed_checks` string lists, which is a locally-declared dataclass
free to shape itself however Phase B5.2 chose) holds one dict per
check below (`{"name": ..., "passed": ..., "detail": ...}`), the
natural shape for that field's own declared type. Registry fingerprints
and the graph fingerprint have no dedicated top-level dataclass in
schema.py (Task 1's placeholder search found none for either) and are
therefore returned as a plain `Dict[str, str]` / `str` respectively --
matching every earlier plain-dict artifact in this codebase (compiler.
fingerprints.generate_registry_fingerprints()'s own identical return
shape one layer down) rather than inventing a single-purpose dataclass
Phase C4.2 was never asked to add.

PIPELINE INTEGRATION: `generate_graph_fingerprints()` is the one
pipeline.py integration point (mirrors compiler.fingerprints.
generate_compiler_fingerprints()'s own shape one layer down). It must
run AFTER knowledge_graph.build.generate_knowledge_graph_manifest()/
generate_knowledge_graph_statistics() (Phase C4.1, so there is a
manifest/statistics to fold into the graph fingerprint) and BEFORE any
future Phase C4.3 logic -- see pipeline.py's own comment at the call
site. Its three results (registry fingerprints, graph fingerprint,
readiness report) are handed to knowledge_graph.state.
set_current_registry_fingerprints()/set_current_graph_fingerprint()/
set_current_knowledge_graph_readiness_report() immediately after (Task
6), making them "part of Knowledge Graph State" per the task spec,
WITHOUT writing any of them into ChapterJSON or mutating
`graph_registry_manager` itself.

BACKWARD COMPATIBILITY: every field this module reads (from
`graph_registry_manager`, from `manifest`, from `statistics`, from
`validation_report`) is only ever read, never changed. No existing
node, edge, registry, manifest, statistics, validation report,
Compiler IR field, or Chapter JSON output changes as a result of this
module existing. The only new artifacts are the registry fingerprints
dict, the graph fingerprint string, and the readiness report dict (plus
the new, additive get/set/has functions in knowledge_graph/state.py
that now hold them).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from compiler.fingerprints import VOLATILE_KEYS

from .registries import GRAPH_REGISTRY_NAMES, GraphRegistryManager
from .schema import KnowledgeGraphReadinessReport


# --------------------------------------------------------------------------
# This module's own version marker -- independent of every earlier
# Knowledge Graph phase's own *_VERSION constant, and independent of
# compiler.fingerprints.FINGERPRINT_VERSION (which versions the
# Compiler IR fingerprint algorithm, one layer down, not this one).
# Bump only if the fingerprint ALGORITHM this file implements itself
# changes (a different hash function, a different canonicalization
# strategy, or a change to which volatile keys are stripped) in a way
# that would make an old fingerprint and a new fingerprint of the same
# underlying graph legitimately differ. Mirrors compiler/fingerprints.
# py's own FINGERPRINT_VERSION precedent, one layer up.
GRAPH_FINGERPRINT_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Canonicalization helpers -- identical strategy to compiler/
# fingerprints.py's own _strip_volatile()/_canonical_json()/
# _sha256_hexdigest(), reimplemented here (rather than imported) only
# because those three are module-private (leading underscore) in that
# module; VOLATILE_KEYS itself -- the one piece of actual, meaningful
# state ("which key names are volatile") -- IS imported and reused
# verbatim above, never redeclared. See module docstring's VOLATILE
# FIELD FILTERING section for why the same constant applies here too.
# --------------------------------------------------------------------------

def _strip_volatile(value: Any) -> Any:
    """Recursively returns a copy of `value` with every VOLATILE_KEYS
    entry removed from every dict at every nesting depth. Lists are
    walked (not sorted -- every list this module ever fingerprints is
    already produced in a deterministic, insertion/explicit-sort order
    by its owning phase). Scalars pass through unchanged. Never mutates
    `value` itself."""
    if isinstance(value, dict):
        return {
            key: _strip_volatile(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    """Deterministic JSON text for `value`: volatile fields stripped
    (see _strip_volatile), keys sorted (so hash-randomized dict
    iteration order can never affect the result), and a compact, fixed
    separator style (so incidental whitespace differences never affect
    the result either)."""
    return json.dumps(
        _strip_volatile(value),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_hexdigest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Task 3: Registry Fingerprints
# --------------------------------------------------------------------------

def generate_registry_fingerprints(
    graph_registry_manager: GraphRegistryManager,
) -> Dict[str, str]:
    """Phase C4.2 Task 3. One SHA-256 hex digest per registry
    `graph_registry_manager` owns, keyed by registry name (same names
    as `.names()`, same deterministic registration order -- nodes,
    edges, metadata).

    Read-only over `graph_registry_manager`: no registry is inserted
    into, updated, or removed from. Each registry's digest is computed
    from its own `CanonicalRegistry.serialize()` output (already
    deterministic, insertion-ordered, inherited unchanged from
    RegistryManager -- see knowledge_graph/registries.py's own
    GraphRegistryManager docstring) with every VOLATILE_KEYS field
    stripped first. Never rescans registry internals directly; never a
    second pass over node/edge contents beyond what `serialize()`
    itself already walks.

    Same registry contents (modulo volatile fields) -> the same digest,
    every run. A registry with zero items still gets a digest (of its
    empty `{"registry": name, "version": 1, "items": []}` envelope) --
    "empty" is itself a deterministic, fingerprint-worthy state, not a
    reason to skip a registry.
    """
    fingerprints: Dict[str, str] = {}
    for name in graph_registry_manager.names():
        registry = graph_registry_manager.get(name)
        payload = registry.serialize()
        fingerprints[name] = _sha256_hexdigest(_canonical_json(payload))
    return fingerprints


# --------------------------------------------------------------------------
# Task 4: Knowledge Graph Fingerprint
# --------------------------------------------------------------------------

def generate_graph_fingerprint(
    registry_fingerprints: Dict[str, str],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
) -> str:
    """Phase C4.2 Task 4. One SHA-256 hex digest representing the
    complete Knowledge Graph build, derived ONLY from (task's own
    three-item list):

      * `registry_fingerprints` (Task 3's own output -- every per-
        registry digest, sorted by name below so caller-supplied dict
        ordering can never affect the result)
      * `manifest` (knowledge_graph.build.generate_knowledge_graph_
        manifest()'s output this chapter -- Phase C4.1, volatile
        fields stripped)
      * `statistics` (knowledge_graph.build.generate_knowledge_graph_
        statistics()'s output this chapter -- Phase C4.1, volatile
        fields stripped)

    Read-only over all three arguments -- nothing here mutates a
    fingerprint dict, a manifest, or a statistics dict, and nothing
    here re-derives manifest/statistics fields a second time.

    Same graph -> same registry fingerprints + same manifest/statistics
    content (modulo volatile fields) -> the same digest, every run.
    Different graph -> a different digest (barring a SHA-256 collision).
    """
    payload = {
        "fingerprint_version": GRAPH_FINGERPRINT_VERSION,
        "registry_fingerprints": dict(sorted((registry_fingerprints or {}).items())),
        "manifest": manifest or {},
        "statistics": statistics or {},
    }
    return _sha256_hexdigest(_canonical_json(payload))


# --------------------------------------------------------------------------
# Task 5: Knowledge Graph Readiness Report
# --------------------------------------------------------------------------

# The task's own "required registries" list -- every graph registry
# create_graph_registry_manager() always registers (knowledge_graph/
# registries.py's own GRAPH_REGISTRY_NAMES), reused unchanged rather
# than redeclared (same constant knowledge_graph/validation.py's own
# Phase C3 "required registries" check already reads).
REQUIRED_GRAPH_REGISTRY_NAMES: tuple = GRAPH_REGISTRY_NAMES


def _check(name: str, passed: bool, detail: Optional[str] = None) -> Dict[str, Any]:
    """One entry of KnowledgeGraphReadinessReport.checks -- see module
    docstring's NO SCHEMA REDESIGN section for why this dict shape
    (rather than compiler/fingerprints.py's own separate passed/failed
    string lists) is what this module produces."""
    entry: Dict[str, Any] = {"name": name, "passed": passed}
    if detail is not None:
        entry["detail"] = detail
    return entry


def generate_graph_readiness_report(
    graph_registry_manager: GraphRegistryManager,
    validation_report: Optional[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    graph_fingerprint: Optional[str],
) -> Dict[str, Any]:
    """Phase C4.2 Task 5. Runs eight read-only checks and returns a
    structured, deterministic verdict as a plain dict (report.to_dict(),
    where `report` is a reused `knowledge_graph.schema.
    KnowledgeGraphReadinessReport` instance -- Task 1's own "reuse the
    existing placeholder" requirement).

    Read-only over every argument: no registry is inserted into,
    updated, or removed from; nothing is repaired, filled in, or
    regenerated here -- a failed check is reported as failed, never
    silently fixed (architectural requirement's own "Produce findings
    only. Never repair anything.").
    """
    checks: List[Dict[str, Any]] = []

    # -- 1. required registries exist --------------------------------------
    missing_registries = [
        n for n in REQUIRED_GRAPH_REGISTRY_NAMES if not graph_registry_manager.has(n)
    ]
    checks.append(_check(
        "required_registries_exist",
        not missing_registries,
        detail=(
            "missing required registries: " + ", ".join(missing_registries)
            if missing_registries else None
        ),
    ))

    # -- 2. graph validation passed -----------------------------------------
    validation_status = (validation_report or {}).get("overall_status")
    if validation_report is not None and validation_status == "pass":
        checks.append(_check("graph_validation_passed", True))
    else:
        detail = (
            "no validation report available" if validation_report is None
            else f"validation reported overall_status={validation_status!r}"
        )
        checks.append(_check("graph_validation_passed", False, detail=detail))

    # -- 3. graph manifest exists --------------------------------------------
    checks.append(_check("graph_manifest_exists", bool(manifest)))

    # -- 4. graph statistics exist --------------------------------------------
    checks.append(_check("graph_statistics_exists", bool(statistics)))

    # -- 5. registry fingerprints generated ------------------------------------
    expected_registry_names = set(graph_registry_manager.names())
    have_all_registry_fingerprints = bool(registry_fingerprints) and expected_registry_names.issubset(
        set(registry_fingerprints)
    )
    checks.append(_check("registry_fingerprints_generated", have_all_registry_fingerprints))

    # -- 6. graph fingerprint generated ----------------------------------------
    checks.append(_check("graph_fingerprint_generated", bool(graph_fingerprint)))

    # -- 7. node count matches statistics --------------------------------------
    manifest_node_count = (manifest or {}).get("node_count")
    statistics_total_nodes = (statistics or {}).get("total_nodes")
    node_counts_present = manifest is not None and statistics is not None
    node_counts_match = node_counts_present and manifest_node_count == statistics_total_nodes
    checks.append(_check(
        "node_count_matches_statistics",
        node_counts_match,
        detail=(
            None if node_counts_match
            else f"manifest.node_count={manifest_node_count!r} != "
                 f"statistics.total_nodes={statistics_total_nodes!r}"
        ),
    ))

    # -- 8. edge count matches statistics --------------------------------------
    manifest_edge_count = (manifest or {}).get("edge_count")
    statistics_total_edges = (statistics or {}).get("total_edges")
    edge_counts_present = manifest is not None and statistics is not None
    edge_counts_match = edge_counts_present and manifest_edge_count == statistics_total_edges
    checks.append(_check(
        "edge_count_matches_statistics",
        edge_counts_match,
        detail=(
            None if edge_counts_match
            else f"manifest.edge_count={manifest_edge_count!r} != "
                 f"statistics.total_edges={statistics_total_edges!r}"
        ),
    ))

    # Surface validation warnings (not just errors) as a non-blocking
    # signal on the readiness report -- a graph build can be "ready"
    # (every check above passing) while still carrying warnings worth a
    # human's attention. Never affects `ready` below. Mirrors compiler.
    # fingerprints.generate_compiler_readiness_report()'s own identical
    # treatment of validation warnings.
    warnings: List[str] = []
    if validation_report is not None:
        validation_warning_count = len(validation_report.get("warnings") or [])
        if validation_warning_count:
            warnings.append(
                f"validation report carries {validation_warning_count} "
                "warning(s)"
            )

    passed_count = sum(1 for c in checks if c["passed"])
    failed_count = len(checks) - passed_count
    # `ready` (task's own "graph ready for downstream phases" bullet) is
    # the DERIVED overall verdict every check above produces together --
    # never a ninth, independently-computed check. See module
    # docstring's TASK 5 section.
    ready = failed_count == 0

    readiness_summary = {
        "total_checks": len(checks),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "warning_count": len(warnings),
    }

    report = KnowledgeGraphReadinessReport(
        ready=ready,
        checks=checks,
        warnings=warnings,
        readiness_summary=readiness_summary,
    )
    return report.to_dict()


# --------------------------------------------------------------------------
# Task 7: Pipeline Integration -- the one pass pipeline.py calls
# --------------------------------------------------------------------------

def generate_graph_fingerprints(
    graph_registry_manager: GraphRegistryManager,
    *,
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    validation_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase C4.2's single pipeline.py integration point (mirrors
    compiler.fingerprints.generate_compiler_fingerprints()'s own shape
    one layer down). Must run AFTER knowledge_graph.build.
    generate_knowledge_graph_manifest()/generate_knowledge_graph_
    statistics() (Phase C4.1, so `manifest`/`statistics` are available
    to fold into the graph fingerprint) and BEFORE any future Phase
    C4.3 logic -- see module docstring's PIPELINE INTEGRATION section
    and pipeline.py's own comment at the call site.

    Runs Tasks 3-5 in the only order that makes sense (fingerprints
    before the readiness report that checks whether they were
    generated) and returns all three results together as one plain
    dict, ready to be handed to knowledge_graph.state.
    set_current_registry_fingerprints()/set_current_graph_fingerprint()/
    set_current_knowledge_graph_readiness_report() (Task 6's own "store
    inside Knowledge Graph State" requirement).

    Read-only over every argument, and never touches a graph registry,
    the Compiler IR, or Educational JSON -- see module docstring's
    opening SCOPE paragraph.
    """
    registry_fingerprints = generate_registry_fingerprints(graph_registry_manager)
    graph_fingerprint = generate_graph_fingerprint(
        registry_fingerprints, manifest, statistics,
    )
    readiness_report = generate_graph_readiness_report(
        graph_registry_manager,
        validation_report,
        manifest,
        statistics,
        registry_fingerprints,
        graph_fingerprint,
    )
    return {
        "registry_fingerprints": registry_fingerprints,
        "graph_fingerprint": graph_fingerprint,
        "readiness_report": readiness_report,
    }