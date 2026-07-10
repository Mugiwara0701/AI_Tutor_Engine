"""
validation/determinism.py — Phase D2: Determinism & Reproducibility
Validation.

SCOPE: this module proves REPRODUCIBILITY, not correctness -- see task
spec's own "D2 does NOT validate correctness. D2 validates
reproducibility." Phase D1 (validation/system_integrity.py) already
owns cross-artifact CONSISTENCY (does the Knowledge Graph Manifest's
own node_count agree with the Knowledge Graph Statistics' own
total_nodes?); that is frozen and untouched here. This module instead
asks a different question of the SAME artifacts D1 already reads: given
the compiler/graph state already built THIS chapter, would recomputing
a fingerprint / re-serializing a registry / re-canonicalizing a
manifest, statistics block, build summary, or the D1 System Integrity
Report itself, right now, from the exact same inputs, produce a
byte-identical result? Every check below is therefore a REAL, in-
process re-derivation-and-compare -- never a re-run of a second whole
pipeline invocation (out of scope: this module has no way to force a
second chapter compile) and never a guess dressed up as a check.

WHAT THIS IS NOT (task's own DO NOT IMPLEMENT list): this is not D3
Release Readiness, not Incremental Compilation, not Compiler Metadata,
not any Graph Query/Traversal/Search/Optimization, not a Cache, not a
Runtime API, and not Repair logic. Every check below only ever reads
already-computed compiler/knowledge-graph state (via existing, public,
read-only accessors -- `.names()`, `.get()`, `.serialize()`) and the
existing, public, already-frozen fingerprint generators (compiler.
fingerprints.generate_registry_fingerprints()/
generate_compiler_fingerprint(), knowledge_graph.fingerprints.
generate_registry_fingerprints()/generate_graph_fingerprint()) --
nothing here re-implements fingerprinting, re-implements manifest/
statistics/build-summary generation, or touches D1's own checks.

REUSE, DON'T RECOMPUTE (mirrors every earlier phase's own rule, applied
to REPRODUCIBILITY rather than to CONTENT): where an existing generator
already exists (the two `generate_registry_fingerprints()` and the two
`generate_{compiler,graph}_fingerprint()` functions above), this module
calls that SAME function a second time against the SAME already-built
registries/manifest/statistics and compares the two results -- it never
hand-rolls a second, parallel fingerprinting algorithm. Where no
existing generator exists to call twice (registry/manifest/statistics/
build-summary/System-Integrity-Report *key-ordering* stability), this
module instead re-canonicalizes (sort_keys=True JSON, via
canonicalization.canonical_json() -- the single shared implementation
compiler/fingerprints.py and knowledge_graph/fingerprints.py also
consume, so all three modules canonicalize identically by construction
rather than by convention) a key-reordered COPY of the same dict and
confirms the canonical text is unchanged, proving the artifact's own
fingerprint-worthiness does not depend on incidental Python dict/set
iteration order.

READ-ONLY / NEVER MUTATES: nothing in this module calls `.insert()`,
`.update()`, `.upsert()`, `.remove()`, or `.clear()` on any registry,
and no manifest/statistics/fingerprint/build-summary/System-Integrity-
Report dict handed in is ever mutated in place -- every "reorder the
keys" check below operates on a freshly built copy, never the caller's
own dict. `validate_determinism()` is itself a pure function of its
arguments (modulo `generated_at`): same inputs, same report, every run,
on any machine.

NO TIMESTAMP LEAKAGE / NO RANDOM ORDERING: rather than merely asserting
this the way every earlier phase's own docstring already does, this
module actively PROVES it for the fingerprints task spec calls out by
name -- see `_check_fingerprint_timestamp_independence()` below, which
takes a real volatile field (e.g. a manifest's own `generated_at`),
changes it, regenerates the fingerprint from the mutated copy, and
confirms the digest is unchanged. A hypothetical future regression that
accidentally folded a timestamp into a fingerprint would flip this
check from pass to fail immediately.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from canonicalization import (
    VOLATILE_KEYS,
    canonical_json as _canonical_json,
    strip_volatile as _strip_volatile,
)
from compiler.registry_manager import RegistryManager as CompilerRegistryManager
from compiler.fingerprints import (
    generate_compiler_fingerprint,
    generate_registry_fingerprints as generate_compiler_registry_fingerprints,
)
from knowledge_graph.registries import (
    EDGE_REGISTRY_NAME,
    NODE_REGISTRY_NAME,
    GraphRegistryManager,
)
from knowledge_graph.fingerprints import (
    generate_graph_fingerprint,
    generate_registry_fingerprints as generate_graph_registry_fingerprints,
)


# --------------------------------------------------------------------------
# This module's own version marker -- independent of every other
# *_VERSION/*_SCHEMA_VERSION/*_INTEGRITY_VERSION constant in this
# codebase (same convention validation/system_integrity.py's own
# SYSTEM_INTEGRITY_VERSION already establishes one layer down). Bump
# only if this module's own check set or report SHAPE changes.
# --------------------------------------------------------------------------
DETERMINISM_VERSION = "D2.1"


# --------------------------------------------------------------------------
# Small issue-dict helpers -- same shape every existing validator in this
# codebase already uses (compiler/validation.py's, knowledge_graph/
# validation.py's, validation/system_integrity.py's own same-named
# pair). Kept as plain dicts here too, for the same reason.
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


def _record(passed: List[str], failed: List[str], name: str, ok: bool) -> None:
    (passed if ok else failed).append(name)


# --------------------------------------------------------------------------
# Canonicalization helpers -- now the SAME shared implementation
# compiler/fingerprints.py and knowledge_graph/fingerprints.py also
# consume (canonicalization.py), imported above as _strip_volatile/
# _canonical_json so every call site below is unchanged. Previously this
# module reimplemented these two itself because compiler.fingerprints's
# own copies were module-private; now there is exactly one
# implementation and all three modules import it, with a shared parity
# test (tests/test_canonicalization_parity.py) enforcing they can never
# again silently diverge. VOLATILE_KEYS itself (the one piece of actual,
# meaningful state) is imported the same way, from the same shared
# module, never redeclared.
# --------------------------------------------------------------------------


def _reordered_copy(value: Any) -> Any:
    """Returns a deep copy of `value` with every dict's keys rebuilt in
    REVERSED insertion order, at every nesting depth -- lets a check
    prove "same logical content, different incidental key order ->
    identical canonical output" without ever touching the caller's own
    dict (copy.deepcopy() first, then rebuilt, so the original is never
    at risk of mutation)."""
    value = copy.deepcopy(value)

    def _reorder(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: _reorder(v[k]) for k in reversed(list(v.keys()))}
        if isinstance(v, list):
            return [_reorder(item) for item in v]
        return v

    return _reorder(value)


def _key_order_independent(value: Optional[Dict[str, Any]]) -> bool:
    """True iff canonicalizing `value` and canonicalizing a copy of
    `value` with every dict's keys reversed produce byte-identical
    canonical JSON text -- i.e. this artifact's own fingerprint-
    worthiness does not depend on incidental Python dict iteration
    order. `None` (an artifact that was never supplied) is reported as
    False by the caller via a `*_present` field instead; this helper is
    only ever called once presence has already been confirmed."""
    if value is None:
        return False
    return _canonical_json(value) == _canonical_json(_reordered_copy(value))


def _first_volatile_key(value: Any) -> Optional[str]:
    """Finds one VOLATILE_KEYS entry actually present in `value`, at any
    nesting depth, so `_check_fingerprint_timestamp_independence()`
    below has a real field to mutate rather than inventing one that
    might not exist on this artifact. Returns None if none is present
    (e.g. a hand-built test fixture with no timestamp fields at all) --
    the caller treats that as "nothing to prove non-leakage of here"
    rather than a failure, since there is no volatile field that
    COULD have leaked."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in VOLATILE_KEYS and isinstance(v, str):
                return k
            found = _first_volatile_key(v)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _first_volatile_key(item)
            if found is not None:
                return found
    return None


def _mutate_one_volatile_field(value: Any, key: str) -> Any:
    """Deep copy of `value` with every occurrence of `key` (a
    VOLATILE_KEYS entry) at any nesting depth given a different string
    value than whatever it already held -- used only to prove a
    fingerprint that reads `value` does NOT change when a timestamp-
    shaped field does."""
    value = copy.deepcopy(value)

    def _walk(v: Any) -> Any:
        if isinstance(v, dict):
            return {
                k: ("1970-01-01T00:00:00+00:00#determinism-probe" if k == key else _walk(item))
                for k, item in v.items()
            }
        if isinstance(v, list):
            return [_walk(item) for item in v]
        return v

    return _walk(value)


# --------------------------------------------------------------------------
# Task 5: Determinism Report
# --------------------------------------------------------------------------

@dataclass
class DeterminismReport:
    """The full Phase D2 report artifact -- see this module's own
    docstring and Task 5's own "Suggested fields" list. Purely a data
    holder; all the actual checking happens in validate_determinism()
    below, which reads already-computed compiler/knowledge-graph state
    (and, immediately after D1 in the pipeline, the D1 System Integrity
    Report) and folds it into one of these. Two extra groups beyond
    Task 5's own suggested five (`build_summary_determinism`,
    `system_integrity_determinism`) cover the two Task 3 artifacts
    ("Compiler Build Summary", "Knowledge Graph Build Summary", "System
    Integrity Report") that would otherwise have nowhere to live -- the
    same "suggested, not exhaustive" latitude validation/
    system_integrity.py's own report already takes with its six groups
    against Task 5's smaller suggested list one phase up."""

    generated_at: str = ""
    report_version: str = DETERMINISM_VERSION
    overall_status: str = "unknown"  # "pass" | "fail" | "unknown"
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    summary: str = ""
    fingerprint_determinism: Dict[str, Any] = field(default_factory=dict)
    manifest_determinism: Dict[str, Any] = field(default_factory=dict)
    statistics_determinism: Dict[str, Any] = field(default_factory=dict)
    ordering_determinism: Dict[str, Any] = field(default_factory=dict)
    build_summary_determinism: Dict[str, Any] = field(default_factory=dict)
    system_integrity_determinism: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# 1. Fingerprint Determinism -- Compiler Fingerprints <-> Knowledge Graph
#    Fingerprints, re-derived and compared, plus timestamp-independence
# --------------------------------------------------------------------------

def _validate_fingerprint_determinism(
    compiler_registry_manager: CompilerRegistryManager,
    compiler_manifest: Optional[Dict[str, Any]],
    compiler_statistics: Optional[Dict[str, Any]],
    compiler_registry_fingerprints: Optional[Dict[str, str]],
    compiler_fingerprint: Optional[str],
    graph_registry_manager: GraphRegistryManager,
    knowledge_graph_manifest: Optional[Dict[str, Any]],
    knowledge_graph_statistics: Optional[Dict[str, Any]],
    knowledge_graph_registry_fingerprints: Optional[Dict[str, str]],
    knowledge_graph_fingerprint: Optional[str],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}

    # -- Compiler side -----------------------------------------------------
    recomputed_compiler_registry_fps = generate_compiler_registry_fingerprints(
        compiler_registry_manager,
    )
    recomputed_compiler_registry_fps_again = generate_compiler_registry_fingerprints(
        compiler_registry_manager,
    )
    result["compiler_registry_fingerprints_reproducible"] = (
        recomputed_compiler_registry_fps == recomputed_compiler_registry_fps_again
    )
    if not result["compiler_registry_fingerprints_reproducible"]:
        issues.append(_error(
            "compiler_registry_fingerprints_not_reproducible",
            "Regenerating compiler registry fingerprints twice from the same "
            "RegistryManager produced two different results.",
        ))

    result["compiler_registry_fingerprints_present"] = compiler_registry_fingerprints is not None
    if compiler_registry_fingerprints is not None:
        result["compiler_registry_fingerprints_match_supplied"] = (
            recomputed_compiler_registry_fps == compiler_registry_fingerprints
        )
        if not result["compiler_registry_fingerprints_match_supplied"]:
            issues.append(_error(
                "compiler_registry_fingerprints_mismatch",
                "Re-deriving compiler registry fingerprints from the current "
                "RegistryManager does not match the fingerprints supplied for "
                "this chapter.",
            ))
    else:
        issues.append(_warning(
            "compiler_registry_fingerprints_missing",
            "No compiler_registry_fingerprints supplied; only in-process "
            "reproducibility (not agreement with a stored value) was checked.",
        ))

    recomputed_compiler_fp = generate_compiler_fingerprint(
        recomputed_compiler_registry_fps, compiler_manifest, compiler_statistics,
    )
    recomputed_compiler_fp_again = generate_compiler_fingerprint(
        recomputed_compiler_registry_fps, compiler_manifest, compiler_statistics,
    )
    result["compiler_fingerprint_reproducible"] = recomputed_compiler_fp == recomputed_compiler_fp_again
    if not result["compiler_fingerprint_reproducible"]:
        issues.append(_error(
            "compiler_fingerprint_not_reproducible",
            "Regenerating the compiler fingerprint twice from the same "
            "registry fingerprints/manifest/statistics produced two "
            "different digests.",
        ))

    result["compiler_fingerprint_present"] = compiler_fingerprint is not None
    if compiler_fingerprint is not None:
        result["compiler_fingerprint_matches_supplied"] = recomputed_compiler_fp == compiler_fingerprint
        if not result["compiler_fingerprint_matches_supplied"]:
            issues.append(_error(
                "compiler_fingerprint_mismatch",
                "Re-deriving the compiler fingerprint from the current "
                "registries/manifest/statistics does not match the "
                "fingerprint supplied for this chapter.",
            ))
    else:
        issues.append(_warning(
            "compiler_fingerprint_missing",
            "No compiler_fingerprint supplied; only in-process "
            "reproducibility (not agreement with a stored value) was checked.",
        ))

    volatile_key = _first_volatile_key(compiler_manifest) or _first_volatile_key(compiler_statistics)
    if volatile_key is not None:
        mutated_manifest = _mutate_one_volatile_field(compiler_manifest, volatile_key)
        mutated_statistics = _mutate_one_volatile_field(compiler_statistics, volatile_key)
        mutated_fp = generate_compiler_fingerprint(
            recomputed_compiler_registry_fps, mutated_manifest, mutated_statistics,
        )
        result["compiler_fingerprint_timestamp_independent"] = mutated_fp == recomputed_compiler_fp
        if not result["compiler_fingerprint_timestamp_independent"]:
            issues.append(_error(
                "compiler_fingerprint_timestamp_leakage",
                f"Changing volatile field '{volatile_key}' changed the "
                "compiler fingerprint; a timestamp-shaped field is leaking "
                "into fingerprint generation.",
            ))
    else:
        result["compiler_fingerprint_timestamp_independent"] = None
        issues.append(_warning(
            "compiler_fingerprint_timestamp_probe_unavailable",
            "No volatile (timestamp-shaped) field found in the supplied "
            "compiler manifest/statistics to probe; timestamp-independence "
            "was not exercised this run.",
        ))

    # -- Knowledge graph side ------------------------------------------------
    recomputed_graph_registry_fps = generate_graph_registry_fingerprints(graph_registry_manager)
    recomputed_graph_registry_fps_again = generate_graph_registry_fingerprints(graph_registry_manager)
    result["graph_registry_fingerprints_reproducible"] = (
        recomputed_graph_registry_fps == recomputed_graph_registry_fps_again
    )
    if not result["graph_registry_fingerprints_reproducible"]:
        issues.append(_error(
            "graph_registry_fingerprints_not_reproducible",
            "Regenerating knowledge graph registry fingerprints twice from "
            "the same GraphRegistryManager produced two different results.",
        ))

    result["graph_registry_fingerprints_present"] = knowledge_graph_registry_fingerprints is not None
    if knowledge_graph_registry_fingerprints is not None:
        result["graph_registry_fingerprints_match_supplied"] = (
            recomputed_graph_registry_fps == knowledge_graph_registry_fingerprints
        )
        if not result["graph_registry_fingerprints_match_supplied"]:
            issues.append(_error(
                "graph_registry_fingerprints_mismatch",
                "Re-deriving knowledge graph registry fingerprints from the "
                "current GraphRegistryManager does not match the "
                "fingerprints supplied for this chapter.",
            ))
    else:
        issues.append(_warning(
            "graph_registry_fingerprints_missing",
            "No knowledge_graph_registry_fingerprints supplied; only "
            "in-process reproducibility was checked.",
        ))

    recomputed_graph_fp = generate_graph_fingerprint(
        recomputed_graph_registry_fps, knowledge_graph_manifest, knowledge_graph_statistics,
    )
    recomputed_graph_fp_again = generate_graph_fingerprint(
        recomputed_graph_registry_fps, knowledge_graph_manifest, knowledge_graph_statistics,
    )
    result["graph_fingerprint_reproducible"] = recomputed_graph_fp == recomputed_graph_fp_again
    if not result["graph_fingerprint_reproducible"]:
        issues.append(_error(
            "graph_fingerprint_not_reproducible",
            "Regenerating the knowledge graph fingerprint twice from the "
            "same registry fingerprints/manifest/statistics produced two "
            "different digests.",
        ))

    result["graph_fingerprint_present"] = knowledge_graph_fingerprint is not None
    if knowledge_graph_fingerprint is not None:
        result["graph_fingerprint_matches_supplied"] = recomputed_graph_fp == knowledge_graph_fingerprint
        if not result["graph_fingerprint_matches_supplied"]:
            issues.append(_error(
                "graph_fingerprint_mismatch",
                "Re-deriving the knowledge graph fingerprint from the "
                "current graph registries/manifest/statistics does not "
                "match the fingerprint supplied for this chapter.",
            ))
    else:
        issues.append(_warning(
            "graph_fingerprint_missing",
            "No knowledge_graph_fingerprint supplied; only in-process "
            "reproducibility was checked.",
        ))

    graph_volatile_key = (
        _first_volatile_key(knowledge_graph_manifest)
        or _first_volatile_key(knowledge_graph_statistics)
    )
    if graph_volatile_key is not None:
        mutated_manifest = _mutate_one_volatile_field(knowledge_graph_manifest, graph_volatile_key)
        mutated_statistics = _mutate_one_volatile_field(knowledge_graph_statistics, graph_volatile_key)
        mutated_fp = generate_graph_fingerprint(
            recomputed_graph_registry_fps, mutated_manifest, mutated_statistics,
        )
        result["graph_fingerprint_timestamp_independent"] = mutated_fp == recomputed_graph_fp
        if not result["graph_fingerprint_timestamp_independent"]:
            issues.append(_error(
                "graph_fingerprint_timestamp_leakage",
                f"Changing volatile field '{graph_volatile_key}' changed "
                "the knowledge graph fingerprint; a timestamp-shaped field "
                "is leaking into fingerprint generation.",
            ))
    else:
        result["graph_fingerprint_timestamp_independent"] = None
        issues.append(_warning(
            "graph_fingerprint_timestamp_probe_unavailable",
            "No volatile (timestamp-shaped) field found in the supplied "
            "knowledge graph manifest/statistics to probe; timestamp-"
            "independence was not exercised this run.",
        ))

    return issues, result


# --------------------------------------------------------------------------
# 2. Ordering Determinism -- registry name ordering, node ordering, edge
#    ordering, and whole-registry serialization stability
# --------------------------------------------------------------------------

def _validate_ordering_determinism(
    compiler_registry_manager: CompilerRegistryManager,
    graph_registry_manager: GraphRegistryManager,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}

    compiler_names_1 = compiler_registry_manager.names()
    compiler_names_2 = compiler_registry_manager.names()
    result["compiler_registry_name_ordering_stable"] = compiler_names_1 == compiler_names_2
    if not result["compiler_registry_name_ordering_stable"]:
        issues.append(_error(
            "compiler_registry_name_ordering_unstable",
            "RegistryManager.names() returned a different order across "
            "two calls against the same manager.",
        ))

    graph_names_1 = graph_registry_manager.names()
    graph_names_2 = graph_registry_manager.names()
    result["graph_registry_name_ordering_stable"] = graph_names_1 == graph_names_2
    if not result["graph_registry_name_ordering_stable"]:
        issues.append(_error(
            "graph_registry_name_ordering_unstable",
            "GraphRegistryManager.names() returned a different order "
            "across two calls against the same manager.",
        ))

    unstable_compiler_registries: List[str] = []
    for name in compiler_names_1:
        registry = compiler_registry_manager.get(name)
        if registry.serialize() != registry.serialize():
            unstable_compiler_registries.append(name)
    result["compiler_registry_serialization_stable"] = not unstable_compiler_registries
    result["unstable_compiler_registries"] = unstable_compiler_registries
    if unstable_compiler_registries:
        issues.append(_error(
            "compiler_registry_serialization_unstable",
            "One or more compiler registries produced different "
            "serialize() output across two calls with no mutation in "
            "between.",
            registries=unstable_compiler_registries,
        ))

    unstable_graph_registries: List[str] = []
    for name in graph_names_1:
        registry = graph_registry_manager.get(name)
        if registry.serialize() != registry.serialize():
            unstable_graph_registries.append(name)
    result["graph_registry_serialization_stable"] = not unstable_graph_registries
    result["unstable_graph_registries"] = unstable_graph_registries
    if unstable_graph_registries:
        issues.append(_error(
            "graph_registry_serialization_unstable",
            "One or more knowledge graph registries produced different "
            "serialize() output across two calls with no mutation in "
            "between.",
            registries=unstable_graph_registries,
        ))

    # Node/edge ordering specifically -- Task 4's own "stable node
    # ordering"/"stable edge ordering" rules, called out by name.
    if graph_registry_manager.has(NODE_REGISTRY_NAME):
        node_ids_1 = [item.get("id") for item in graph_registry_manager.get(NODE_REGISTRY_NAME).serialize().get("items", [])]
        node_ids_2 = [item.get("id") for item in graph_registry_manager.get(NODE_REGISTRY_NAME).serialize().get("items", [])]
        result["node_ordering_stable"] = node_ids_1 == node_ids_2
        if not result["node_ordering_stable"]:
            issues.append(_error(
                "node_ordering_unstable",
                "Knowledge graph node ordering differed across two "
                "serialize() calls against the same node registry.",
            ))
    else:
        result["node_ordering_stable"] = None
        issues.append(_warning(
            "node_registry_missing",
            f"No '{NODE_REGISTRY_NAME}' registry present; node ordering "
            "was not checked.",
        ))

    if graph_registry_manager.has(EDGE_REGISTRY_NAME):
        edge_ids_1 = [item.get("id") for item in graph_registry_manager.get(EDGE_REGISTRY_NAME).serialize().get("items", [])]
        edge_ids_2 = [item.get("id") for item in graph_registry_manager.get(EDGE_REGISTRY_NAME).serialize().get("items", [])]
        result["edge_ordering_stable"] = edge_ids_1 == edge_ids_2
        if not result["edge_ordering_stable"]:
            issues.append(_error(
                "edge_ordering_unstable",
                "Knowledge graph edge ordering differed across two "
                "serialize() calls against the same edge registry.",
            ))
    else:
        result["edge_ordering_stable"] = None
        issues.append(_warning(
            "edge_registry_missing",
            f"No '{EDGE_REGISTRY_NAME}' registry present; edge ordering "
            "was not checked.",
        ))

    return issues, result


# --------------------------------------------------------------------------
# 3. Manifest Determinism -- Compiler Manifest <-> Knowledge Graph
#    Manifest, key-order independence
# --------------------------------------------------------------------------

def _validate_manifest_determinism(
    compiler_manifest: Optional[Dict[str, Any]],
    knowledge_graph_manifest: Optional[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}

    result["compiler_manifest_present"] = compiler_manifest is not None
    if compiler_manifest is not None:
        result["compiler_manifest_key_order_independent"] = _key_order_independent(compiler_manifest)
        if not result["compiler_manifest_key_order_independent"]:
            issues.append(_error(
                "compiler_manifest_key_order_dependent",
                "Reordering the compiler manifest's own dict keys changed "
                "its canonical representation.",
            ))
    else:
        issues.append(_error("compiler_manifest_missing", "No compiler_manifest supplied."))

    result["graph_manifest_present"] = knowledge_graph_manifest is not None
    if knowledge_graph_manifest is not None:
        result["graph_manifest_key_order_independent"] = _key_order_independent(knowledge_graph_manifest)
        if not result["graph_manifest_key_order_independent"]:
            issues.append(_error(
                "graph_manifest_key_order_dependent",
                "Reordering the knowledge graph manifest's own dict keys "
                "changed its canonical representation.",
            ))
    else:
        issues.append(_error("graph_manifest_missing", "No knowledge_graph_manifest supplied."))

    return issues, result


# --------------------------------------------------------------------------
# 4. Statistics Determinism -- Compiler Statistics <-> Knowledge Graph
#    Statistics, key-order independence
# --------------------------------------------------------------------------

def _validate_statistics_determinism(
    compiler_statistics: Optional[Dict[str, Any]],
    knowledge_graph_statistics: Optional[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}

    result["compiler_statistics_present"] = compiler_statistics is not None
    if compiler_statistics is not None:
        result["compiler_statistics_key_order_independent"] = _key_order_independent(compiler_statistics)
        if not result["compiler_statistics_key_order_independent"]:
            issues.append(_error(
                "compiler_statistics_key_order_dependent",
                "Reordering the compiler statistics' own dict keys changed "
                "its canonical representation.",
            ))
    else:
        issues.append(_error("compiler_statistics_missing", "No compiler_statistics supplied."))

    result["graph_statistics_present"] = knowledge_graph_statistics is not None
    if knowledge_graph_statistics is not None:
        result["graph_statistics_key_order_independent"] = _key_order_independent(knowledge_graph_statistics)
        if not result["graph_statistics_key_order_independent"]:
            issues.append(_error(
                "graph_statistics_key_order_dependent",
                "Reordering the knowledge graph statistics' own dict keys "
                "changed its canonical representation.",
            ))
    else:
        issues.append(_error("graph_statistics_missing", "No knowledge_graph_statistics supplied."))

    return issues, result


# --------------------------------------------------------------------------
# 5. Build Summary Determinism -- Compiler Build Summary <-> Knowledge
#    Graph Build Summary (Task 3's own two remaining named artifacts)
# --------------------------------------------------------------------------

def _validate_build_summary_determinism(
    compiler_build_summary: Optional[Dict[str, Any]],
    compiler_fingerprint: Optional[str],
    knowledge_graph_build_summary: Optional[Dict[str, Any]],
    knowledge_graph_fingerprint: Optional[str],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}

    result["compiler_build_summary_present"] = compiler_build_summary is not None
    if compiler_build_summary is not None:
        result["compiler_build_summary_key_order_independent"] = _key_order_independent(compiler_build_summary)
        if not result["compiler_build_summary_key_order_independent"]:
            issues.append(_error(
                "compiler_build_summary_key_order_dependent",
                "Reordering the compiler build summary's own dict keys "
                "changed its canonical representation.",
            ))
        stored_fp = compiler_build_summary.get("compiler_fingerprint")
        if stored_fp is not None and compiler_fingerprint is not None:
            result["compiler_build_summary_fingerprint_consistent"] = stored_fp == compiler_fingerprint
            if not result["compiler_build_summary_fingerprint_consistent"]:
                issues.append(_error(
                    "compiler_build_summary_fingerprint_mismatch",
                    "The compiler build summary's own stored fingerprint "
                    "does not match the compiler fingerprint supplied for "
                    "this chapter.",
                ))
    else:
        issues.append(_error("compiler_build_summary_missing", "No compiler_build_summary supplied."))

    result["graph_build_summary_present"] = knowledge_graph_build_summary is not None
    if knowledge_graph_build_summary is not None:
        result["graph_build_summary_key_order_independent"] = _key_order_independent(knowledge_graph_build_summary)
        if not result["graph_build_summary_key_order_independent"]:
            issues.append(_error(
                "graph_build_summary_key_order_dependent",
                "Reordering the knowledge graph build summary's own dict "
                "keys changed its canonical representation.",
            ))
        stored_fp = knowledge_graph_build_summary.get("graph_fingerprint")
        if stored_fp is not None and knowledge_graph_fingerprint is not None:
            result["graph_build_summary_fingerprint_consistent"] = stored_fp == knowledge_graph_fingerprint
            if not result["graph_build_summary_fingerprint_consistent"]:
                issues.append(_error(
                    "graph_build_summary_fingerprint_mismatch",
                    "The knowledge graph build summary's own stored "
                    "fingerprint does not match the knowledge graph "
                    "fingerprint supplied for this chapter.",
                ))
    else:
        issues.append(_error("graph_build_summary_missing", "No knowledge_graph_build_summary supplied."))

    return issues, result


# --------------------------------------------------------------------------
# 6. System Integrity Report Determinism -- Task 3's own eleventh named
#    artifact, optional (only exists once D1 has already run this
#    chapter -- see validate_determinism()'s own docstring)
# --------------------------------------------------------------------------

def _validate_system_integrity_determinism(
    system_integrity_report: Optional[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}

    result["system_integrity_report_present"] = system_integrity_report is not None
    if system_integrity_report is not None:
        result["system_integrity_report_key_order_independent"] = _key_order_independent(system_integrity_report)
        if not result["system_integrity_report_key_order_independent"]:
            issues.append(_error(
                "system_integrity_report_key_order_dependent",
                "Reordering the D1 System Integrity Report's own dict keys "
                "changed its canonical representation.",
            ))
    else:
        # Not an error: D2 can run (and be tested) without a D1 report
        # handed in -- e.g. a fixture that only cares about the other
        # ten Task 3 artifacts. Pipeline.py's own real integration point
        # (Task 7) always has one available, since D2 runs immediately
        # after D1 -- see this module's own docstring.
        issues.append(_warning(
            "system_integrity_report_not_supplied",
            "No system_integrity_report supplied; its own determinism "
            "was not checked this run.",
        ))

    return issues, result


# --------------------------------------------------------------------------
# Task 2/6/7: validate_determinism() -- the one pipeline.py integration
# point (Task 7), executed immediately after Phase D1
# --------------------------------------------------------------------------

def validate_determinism(
    compiler_registry_manager: CompilerRegistryManager,
    graph_registry_manager: GraphRegistryManager,
    *,
    compiler_manifest: Optional[Dict[str, Any]] = None,
    compiler_statistics: Optional[Dict[str, Any]] = None,
    compiler_registry_fingerprints: Optional[Dict[str, str]] = None,
    compiler_fingerprint: Optional[str] = None,
    compiler_build_summary: Optional[Dict[str, Any]] = None,
    knowledge_graph_manifest: Optional[Dict[str, Any]] = None,
    knowledge_graph_statistics: Optional[Dict[str, Any]] = None,
    knowledge_graph_registry_fingerprints: Optional[Dict[str, str]] = None,
    knowledge_graph_fingerprint: Optional[str] = None,
    knowledge_graph_build_summary: Optional[Dict[str, Any]] = None,
    system_integrity_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase D2's single pipeline.py integration point (mirrors
    validation.system_integrity.validate_system_integrity()'s own shape,
    one artifact over). Must run AFTER Phase D1 -- after validation.
    system_integrity.validate_system_integrity() -- so `
    system_integrity_report` is available to check for its OWN
    determinism (Task 3's eleventh named artifact); every other artifact
    checked here already exists as soon as Phase C is complete, exactly
    like D1's own inputs.

    Read-only over every argument and over `compiler_registry_manager`/
    `graph_registry_manager` themselves: no registry is inserted into,
    updated, or removed from; no manifest/statistics/fingerprint/build-
    summary/System-Integrity-Report dict anywhere is mutated (every
    reordering/mutation check below operates on a fresh deep copy, never
    the caller's own object -- see `_reordered_copy()`/
    `_mutate_one_volatile_field()`). Every optional artifact defaults to
    None so this function can also be called against a partial/hand-
    built fixture (e.g. from a test); a missing artifact is reported as
    a failed/omitted check (see each `_validate_*_determinism()` helper
    above for exactly which), never guessed at.

    Returned as a plain dict (report.to_dict()), matching every earlier
    phase's own "plain, storable dict" convention, and so it can be
    handed directly to validation.state.set_current_determinism_
    report()."""
    report = DeterminismReport(generated_at=datetime.now(timezone.utc).isoformat())

    passed: List[str] = []
    failed: List[str] = []
    all_issues: List[Dict[str, Any]] = []

    fingerprint_issues, fingerprint_determinism = _validate_fingerprint_determinism(
        compiler_registry_manager, compiler_manifest, compiler_statistics,
        compiler_registry_fingerprints, compiler_fingerprint,
        graph_registry_manager, knowledge_graph_manifest, knowledge_graph_statistics,
        knowledge_graph_registry_fingerprints, knowledge_graph_fingerprint,
    )
    all_issues.extend(fingerprint_issues)
    report.fingerprint_determinism = fingerprint_determinism
    _record(passed, failed, "compiler_registry_fingerprints_reproducible", fingerprint_determinism["compiler_registry_fingerprints_reproducible"])
    _record(passed, failed, "compiler_fingerprint_reproducible", fingerprint_determinism["compiler_fingerprint_reproducible"])
    if fingerprint_determinism.get("compiler_registry_fingerprints_present"):
        _record(passed, failed, "compiler_registry_fingerprints_match_supplied", fingerprint_determinism["compiler_registry_fingerprints_match_supplied"])
    if fingerprint_determinism.get("compiler_fingerprint_present"):
        _record(passed, failed, "compiler_fingerprint_matches_supplied", fingerprint_determinism["compiler_fingerprint_matches_supplied"])
    if fingerprint_determinism.get("compiler_fingerprint_timestamp_independent") is not None:
        _record(passed, failed, "compiler_fingerprint_timestamp_independent", fingerprint_determinism["compiler_fingerprint_timestamp_independent"])
    _record(passed, failed, "graph_registry_fingerprints_reproducible", fingerprint_determinism["graph_registry_fingerprints_reproducible"])
    _record(passed, failed, "graph_fingerprint_reproducible", fingerprint_determinism["graph_fingerprint_reproducible"])
    if fingerprint_determinism.get("graph_registry_fingerprints_present"):
        _record(passed, failed, "graph_registry_fingerprints_match_supplied", fingerprint_determinism["graph_registry_fingerprints_match_supplied"])
    if fingerprint_determinism.get("graph_fingerprint_present"):
        _record(passed, failed, "graph_fingerprint_matches_supplied", fingerprint_determinism["graph_fingerprint_matches_supplied"])
    if fingerprint_determinism.get("graph_fingerprint_timestamp_independent") is not None:
        _record(passed, failed, "graph_fingerprint_timestamp_independent", fingerprint_determinism["graph_fingerprint_timestamp_independent"])

    ordering_issues, ordering_determinism = _validate_ordering_determinism(
        compiler_registry_manager, graph_registry_manager,
    )
    all_issues.extend(ordering_issues)
    report.ordering_determinism = ordering_determinism
    _record(passed, failed, "compiler_registry_name_ordering_stable", ordering_determinism["compiler_registry_name_ordering_stable"])
    _record(passed, failed, "graph_registry_name_ordering_stable", ordering_determinism["graph_registry_name_ordering_stable"])
    _record(passed, failed, "compiler_registry_serialization_stable", ordering_determinism["compiler_registry_serialization_stable"])
    _record(passed, failed, "graph_registry_serialization_stable", ordering_determinism["graph_registry_serialization_stable"])
    if ordering_determinism.get("node_ordering_stable") is not None:
        _record(passed, failed, "node_ordering_stable", ordering_determinism["node_ordering_stable"])
    if ordering_determinism.get("edge_ordering_stable") is not None:
        _record(passed, failed, "edge_ordering_stable", ordering_determinism["edge_ordering_stable"])

    manifest_issues, manifest_determinism = _validate_manifest_determinism(
        compiler_manifest, knowledge_graph_manifest,
    )
    all_issues.extend(manifest_issues)
    report.manifest_determinism = manifest_determinism
    _record(passed, failed, "manifests_present", manifest_determinism["compiler_manifest_present"] and manifest_determinism["graph_manifest_present"])
    if manifest_determinism.get("compiler_manifest_key_order_independent") is not None:
        _record(passed, failed, "compiler_manifest_key_order_independent", manifest_determinism["compiler_manifest_key_order_independent"])
    if manifest_determinism.get("graph_manifest_key_order_independent") is not None:
        _record(passed, failed, "graph_manifest_key_order_independent", manifest_determinism["graph_manifest_key_order_independent"])

    statistics_issues, statistics_determinism = _validate_statistics_determinism(
        compiler_statistics, knowledge_graph_statistics,
    )
    all_issues.extend(statistics_issues)
    report.statistics_determinism = statistics_determinism
    _record(passed, failed, "statistics_present", statistics_determinism["compiler_statistics_present"] and statistics_determinism["graph_statistics_present"])
    if statistics_determinism.get("compiler_statistics_key_order_independent") is not None:
        _record(passed, failed, "compiler_statistics_key_order_independent", statistics_determinism["compiler_statistics_key_order_independent"])
    if statistics_determinism.get("graph_statistics_key_order_independent") is not None:
        _record(passed, failed, "graph_statistics_key_order_independent", statistics_determinism["graph_statistics_key_order_independent"])

    build_summary_issues, build_summary_determinism = _validate_build_summary_determinism(
        compiler_build_summary, compiler_fingerprint,
        knowledge_graph_build_summary, knowledge_graph_fingerprint,
    )
    all_issues.extend(build_summary_issues)
    report.build_summary_determinism = build_summary_determinism
    _record(passed, failed, "build_summaries_present", build_summary_determinism["compiler_build_summary_present"] and build_summary_determinism["graph_build_summary_present"])
    if build_summary_determinism.get("compiler_build_summary_key_order_independent") is not None:
        _record(passed, failed, "compiler_build_summary_key_order_independent", build_summary_determinism["compiler_build_summary_key_order_independent"])
    if build_summary_determinism.get("graph_build_summary_key_order_independent") is not None:
        _record(passed, failed, "graph_build_summary_key_order_independent", build_summary_determinism["graph_build_summary_key_order_independent"])
    if build_summary_determinism.get("compiler_build_summary_fingerprint_consistent") is not None:
        _record(passed, failed, "compiler_build_summary_fingerprint_consistent", build_summary_determinism["compiler_build_summary_fingerprint_consistent"])
    if build_summary_determinism.get("graph_build_summary_fingerprint_consistent") is not None:
        _record(passed, failed, "graph_build_summary_fingerprint_consistent", build_summary_determinism["graph_build_summary_fingerprint_consistent"])

    system_integrity_issues, system_integrity_determinism = _validate_system_integrity_determinism(
        system_integrity_report,
    )
    all_issues.extend(system_integrity_issues)
    report.system_integrity_determinism = system_integrity_determinism
    if system_integrity_determinism.get("system_integrity_report_key_order_independent") is not None:
        _record(passed, failed, "system_integrity_report_key_order_independent", system_integrity_determinism["system_integrity_report_key_order_independent"])

    report.errors = [i for i in all_issues if i["severity"] == "error"]
    report.warnings = [i for i in all_issues if i["severity"] == "warning"]
    report.checks_passed = passed
    report.checks_failed = failed
    report.overall_status = "fail" if (report.errors or failed) else "pass"

    total_checks = len(passed) + len(failed)
    report.summary = (
        f"Determinism {report.overall_status}: {total_checks} "
        f"check{'s' if total_checks != 1 else ''} run "
        f"({len(passed)} passed, {len(failed)} failed); "
        f"{len(report.errors)} error(s), {len(report.warnings)} "
        "warning(s) verifying reproducibility across the complete "
        "compiler pipeline."
    )

    return report.to_dict()