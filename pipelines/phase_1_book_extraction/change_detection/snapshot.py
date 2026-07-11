"""
change_detection/snapshot.py — Phase E3: Build Snapshot (Fingerprint
Comparison, input side).

SCOPE: `build_snapshot()` derives exactly one artifact-keyed fingerprint
map for the CURRENT build -- `{artifact_key: fingerprint_string}` --
from Phase E1's already-computed BuildMetadata and Phase E2's
already-computed DependencyGraph. This is the "CURRENT build" half of
Phase E3's own "Previous Build -> Current Build" comparison (see
engine.py); the "PREVIOUS build" half is never sourced by this module
or any other module in this package -- see NO PERSISTENCE below.

REUSE, DON'T INVENT A SECOND FINGERPRINT SYSTEM (task's own explicit
requirement): every fingerprint this module emits is either:

  (a) an EXISTING fingerprint string, reused byte-for-byte, for every
      artifact that already has one -- compiler_fingerprint,
      graph_fingerprint, configuration_fingerprint, and every
      per-registry fingerprint already inside
      build_metadata.compiler_metadata.registry_fingerprints /
      build_metadata.graph_metadata.registry_fingerprints (Phase
      B5.2/C4.2's own output, unchanged); or

  (b) for the handful of artifacts that have NEVER had a dedicated
      fingerprint of their own (compiler_manifest, compiler_statistics,
      compiler_readiness_report, compiler_build_summary, the Knowledge
      Graph equivalents, release_readiness_report, BuildMetadata itself,
      and the DependencyGraph's own node/edge shape) -- derived with
      the exact SAME shared primitives (canonicalization.canonical_json
      + canonicalization.sha256_hexdigest) every existing fingerprint in
      this codebase already uses (compiler/fingerprints.py,
      knowledge_graph/fingerprints.py, validation/determinism.py,
      build_metadata/configuration_metadata.py). This is not a new
      algorithm -- it is the same algorithm, applied directly to one
      more artifact's own already-computed dict, exactly the precedent
      build_metadata/configuration_metadata.py already set for its own
      configuration_fingerprint field. One exception: the "build_metadata"
      artifact is the entire BuildMetadata dict, which nests
      CompilationMetadata -- and build_metadata/compilation_metadata.py's
      own module docstring already establishes that CompilationMetadata's
      compilation_start/compilation_end/processing_time_seconds fields
      must NEVER participate in any fingerprint (they are wall-clock
      timestamps/durations, not compiler-IR content). Since
      canonicalization.VOLATILE_KEYS only lists field names shared across
      multiple artifacts (e.g. "generated_at"), and these three are
      unique to CompilationMetadata, this module excludes them itself,
      one level up, before handing the result to canonical_json()/
      sha256_hexdigest() -- see `_build_metadata_fingerprint_source()`
      below. Still the same shared primitives; only the input data going
      into them is scoped down.

ARTIFACT KEYS REUSE EXISTING IDENTITY, NOT NEW ONES: every per-node key
in the returned map is exactly that artifact's own
dependency_graph.identity.node_id() value (already unique, already
deterministic, already stable across runs for the same artifact --
Phase E2's own guarantee), read directly off each node dict Phase E2's
DependencyGraph already carries -- never a second, independently
computed key. Two synthetic keys ("configuration", "dependency_graph")
are added for the two fingerprint families Phase E2 has no node type
for (see module docstring's (b) above) -- see CONFIGURATION AND
DEPENDENCY-GRAPH KEYS below.

NO PERSISTENCE (task's own DO NOT IMPLEMENT list): this module has no
notion of "where a previous build's snapshot comes from" -- it only
ever builds the CURRENT one. A "previous build" snapshot, wherever a
caller obtained it (this same process's own prior
`build_snapshot()` call, a test fixture, or -- once a future,
out-of-scope phase adds one -- a persistence layer), is expected to be
in this exact shape, and is handed to change_detection.engine.
detect_changes() as its own `previous_build` argument, never read from
disk by this package itself.

READ-ONLY: every argument is read, never mutated; nothing here inserts
into, updates, or removes from any registry, manifest, statistics,
readiness report, build summary, BuildMetadata dict, or DependencyGraph
dict.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from canonicalization import canonical_json, sha256_hexdigest

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase. Bump only if the SNAPSHOT SHAPE
# this module produces itself changes in a way a consumer (including a
# previously-saved snapshot handed back in as `previous_build`) should
# be able to detect.
SNAPSHOT_VERSION = "E3.1"

# The two synthetic, non-DependencyNode keys this module adds to every
# snapshot -- see module docstring's CONFIGURATION AND DEPENDENCY-GRAPH
# KEYS. Exposed as constants so compare.py/engine.py/tests never
# hand-roll these strings a second time.
CONFIGURATION_ARTIFACT_KEY = "configuration"
DEPENDENCY_GRAPH_ARTIFACT_KEY = "dependency_graph"


def _fingerprint_of(value: Optional[Dict[str, Any]]) -> Optional[str]:
    """Derives a fingerprint for one artifact dict that has no
    dedicated fingerprint of its own yet, using the exact same shared
    canonicalization primitives every existing fingerprint in this
    codebase already uses (see module docstring's (b)). Returns None
    for `None` (an artifact this chapter's build never produced never
    gets a fabricated fingerprint -- same "reuse, don't fabricate" rule
    dependency_graph/build.py's own `_node_if()` already follows)."""
    if value is None:
        return None
    return sha256_hexdigest(canonical_json(value))


# The BuildMetadata sub-block whose own operational fields must never
# enter a fingerprint -- see build_metadata/compilation_metadata.py's
# own module docstring ("NEVER PARTICIPATES IN ANY FINGERPRINT":
# compilation_start/compilation_end/processing_time_seconds are
# wall-clock timestamps and durations, exactly the kind of run-to-run-
# varying field canonicalization.VOLATILE_KEYS already excludes by name
# elsewhere). canonicalization.VOLATILE_KEYS does not itself list these
# three, because they are unique to CompilationMetadata, not shared
# vocabulary the way "generated_at" is across every other artifact --
# so this module (the only place that ever folds the *entire*
# BuildMetadata dict into one fingerprint, for the "build_metadata"
# DependencyNode -- see build_snapshot() below) excludes them itself,
# one level up, immediately before handing the result to the exact same
# shared canonical_json()/sha256_hexdigest() primitives every other
# fingerprint in this codebase already uses. This is data scoping, not
# a second fingerprint algorithm.
_COMPILATION_METADATA_VOLATILE_KEYS = (
    "compilation_start",
    "compilation_end",
    "processing_time_seconds",
)


def _build_metadata_fingerprint_source(
    build_metadata: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Returns a copy of `build_metadata` suitable for fingerprinting as
    a whole (the "build_metadata" DependencyNode artifact -- see
    build_snapshot() below): identical in every field except with
    `compilation_metadata`'s own wall-clock operational fields removed
    (see `_COMPILATION_METADATA_VOLATILE_KEYS` above). Never mutates the
    `build_metadata` argument itself -- returns a new top-level dict
    (shallow copy) with a new, sanitized `compilation_metadata` sub-dict;
    every other key/value, including every other artifact's own already-
    fingerprinted sub-block (`compiler_metadata`, `graph_metadata`,
    `configuration_metadata`, `version_metadata`), is reused unchanged.
    Returns `None` for `None` unchanged (see `_fingerprint_of()`'s own
    "never fabricate" handling)."""
    if build_metadata is None:
        return None
    compilation_metadata = build_metadata.get("compilation_metadata")
    if not compilation_metadata:
        return build_metadata
    sanitized_compilation_metadata = {
        key: value
        for key, value in compilation_metadata.items()
        if key not in _COMPILATION_METADATA_VOLATILE_KEYS
    }
    return {**build_metadata, "compilation_metadata": sanitized_compilation_metadata}


def _compiler_artifact_fingerprints(
    compiler_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """Resolves the fingerprint for every `compiler_*`-family
    DependencyNode artifact_key, reusing
    compiler_metadata.compiler_fingerprint /
    compiler_metadata.registry_fingerprints as-is wherever they already
    exist (module docstring's (a)), and deriving one via
    `_fingerprint_of()` for the rest (module docstring's (b))."""
    compiler_metadata = compiler_metadata or {}
    registry_fingerprints = compiler_metadata.get("registry_fingerprints") or {}
    return {
        "__registry__": registry_fingerprints,  # per-registry_name lookup table
        "compiler_manifest": _fingerprint_of(compiler_metadata.get("compiler_manifest")),
        "compiler_statistics": _fingerprint_of(compiler_metadata.get("compiler_statistics")),
        # Reused as-is -- compiler/fingerprints.py already derived this.
        "compiler_fingerprints": compiler_metadata.get("compiler_fingerprint"),
        "compiler_readiness": _fingerprint_of(compiler_metadata.get("compiler_readiness_report")),
        "compiler_build_summary": _fingerprint_of(compiler_metadata.get("compiler_build_summary")),
    }


def _knowledge_graph_artifact_fingerprints(
    graph_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """Knowledge-Graph-side equivalent of
    `_compiler_artifact_fingerprints()`, one artifact family over."""
    graph_metadata = graph_metadata or {}
    registry_fingerprints = graph_metadata.get("registry_fingerprints") or {}
    return {
        "__registry__": registry_fingerprints,
        "knowledge_graph_manifest": _fingerprint_of(graph_metadata.get("knowledge_graph_manifest")),
        "knowledge_graph_statistics": _fingerprint_of(graph_metadata.get("knowledge_graph_statistics")),
        # Reused as-is -- knowledge_graph/fingerprints.py already derived this.
        "knowledge_graph_fingerprints": graph_metadata.get("graph_fingerprint"),
        "knowledge_graph_readiness": _fingerprint_of(graph_metadata.get("knowledge_graph_readiness_report")),
        "knowledge_graph_build_summary": _fingerprint_of(graph_metadata.get("knowledge_graph_build_summary")),
    }


def build_snapshot(
    *,
    namespace: str,
    dependency_graph: Optional[Dict[str, Any]],
    build_metadata: Optional[Dict[str, Any]],
    release_readiness_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Builds this chapter's CURRENT BuildSnapshot: one
    `{artifact_key: fingerprint}` map, keyed by every artifact Phase E2's
    DependencyGraph currently models (by `node_id`, reused unchanged)
    plus the two synthetic keys CONFIGURATION_ARTIFACT_KEY /
    DEPENDENCY_GRAPH_ARTIFACT_KEY (see module docstring).

    Every argument is already in scope in pipeline.py's
    process_chapter() by the time Phase E3's own integration point runs
    (immediately after Phase E2 -- see pipeline.py's own comment at
    that call site). Read-only over every argument; performs no new
    validation, no new registry access, and derives a fingerprint only
    for the small, fixed set of artifacts that never had one (module
    docstring's (b)) -- see canonicalization.py for the shared
    primitives used.

    An artifact this chapter's build never produced (e.g.
    `compiler_manifest is None`) is simply absent from the returned
    `artifact_fingerprints` map -- never a fabricated `None`-valued
    entry -- mirroring dependency_graph/build.py's own "a chapter for
    which an earlier phase produced nothing simply yields a smaller
    graph" rule.

    Returns:
        {
            "namespace": str,
            "generated_at": str,
            "snapshot_version": str,
            "artifact_fingerprints": {artifact_key: fingerprint_string, ...},
        }
    This exact shape is also what `previous_build` (engine.py) is
    expected to look like -- this chapter's own returned snapshot can be
    handed back in, unchanged, as a future run's `previous_build`.
    """
    artifact_fingerprints: Dict[str, str] = {}

    build_metadata = build_metadata or None
    compiler_metadata = (build_metadata or {}).get("compiler_metadata") if build_metadata else None
    graph_metadata = (build_metadata or {}).get("graph_metadata") if build_metadata else None
    configuration_metadata = (build_metadata or {}).get("configuration_metadata") if build_metadata else None

    compiler_fp = _compiler_artifact_fingerprints(compiler_metadata)
    kg_fp = _knowledge_graph_artifact_fingerprints(graph_metadata)

    # -- per-DependencyNode fingerprints, one per node Phase E2's
    # DependencyGraph currently carries -- reused node_id, never a
    # second identity.
    nodes = (dependency_graph or {}).get("nodes") or []
    for node in nodes:
        node_id = node.get("node_id")
        node_type = node.get("node_type")
        artifact_key = node.get("artifact_key")
        if node_id is None or node_type is None:
            continue

        if node_type == "compiler_registry":
            fp = compiler_fp["__registry__"].get(artifact_key)
        elif node_type == "knowledge_graph_registry":
            fp = kg_fp["__registry__"].get(artifact_key)
        elif node_type in compiler_fp:
            fp = compiler_fp[node_type]
        elif node_type in kg_fp:
            fp = kg_fp[node_type]
        elif node_type == "release_readiness":
            fp = _fingerprint_of(release_readiness_report)
        elif node_type == "build_metadata":
            fp = _fingerprint_of(_build_metadata_fingerprint_source(build_metadata))
        else:
            # Unknown node type -- Phase E2's own DEPENDENCY_NODE_TYPES
            # is a closed set this module does not re-validate (that
            # would be Phase E2's own concern, not Phase E3's); simply
            # skip fingerprinting an artifact this module doesn't
            # recognize rather than guessing.
            fp = None

        # NOTE: a compiler_fingerprints/knowledge_graph_fingerprints node
        # can exist here (Phase E2 gates its presence on
        # compiler_registry_fingerprints/knowledge_graph_registry_
        # fingerprints, the per-registry dict, being non-None -- see
        # dependency_graph/build.py's own _node_if() call for this node
        # type) while still resolving to fp=None here (this module reuses
        # compiler_fingerprint/graph_fingerprint, the separate aggregate
        # scalar, which Phase E1 computes independently and could in
        # principle be None even when the per-registry dict is not). Per
        # the "never fabricate" rule below, that just means this one node
        # id is quietly absent from the snapshot rather than guessed at.
        if fp is not None:
            artifact_fingerprints[node_id] = fp

    # -- CONFIGURATION_ARTIFACT_KEY: reused as-is from
    # ConfigurationMetadata (Phase E1) -- never re-derived.
    configuration_fingerprint = (configuration_metadata or {}).get("configuration_fingerprint")
    if configuration_fingerprint is not None:
        artifact_fingerprints[CONFIGURATION_ARTIFACT_KEY] = configuration_fingerprint

    # -- DEPENDENCY_GRAPH_ARTIFACT_KEY: Phase E2 has no fingerprint of
    # its own shape, so one is derived here, over exactly the nodes/
    # edges Phase E2 already built (module docstring's (b)) -- never
    # written back onto the DependencyGraph dict itself.
    if dependency_graph is not None:
        dg_fingerprint = _fingerprint_of(
            {"nodes": dependency_graph.get("nodes") or [], "edges": dependency_graph.get("edges") or []}
        )
        if dg_fingerprint is not None:
            artifact_fingerprints[DEPENDENCY_GRAPH_ARTIFACT_KEY] = dg_fingerprint

    return {
        "namespace": namespace,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_version": SNAPSHOT_VERSION,
        "artifact_fingerprints": artifact_fingerprints,
    }