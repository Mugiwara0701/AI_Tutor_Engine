# Knowledge Graph (`knowledge_graph/`)

Compiler-level Stage C. Reads a chapter's already-populated Compiler IR
(`compiler.RegistryManager` and every Phase B artifact) and never writes
back into it. One `KnowledgeGraph` is built per chapter, held in
chapter-scoped module state (`knowledge_graph/state.py`), reset at the
start of the next chapter. This is **not** a cross-chapter or
cross-book graph — nothing in this codebase merges knowledge graphs
across compilation runs.

## What is actually implemented vs. reserved

| | Status |
|---|---|
| Node construction (C1) | **Implemented.** `build_nodes.py::build_knowledge_graph_nodes()` |
| Edge construction (C2) | **Implemented.** `build_edges.py::build_knowledge_graph_edges()` |
| Validation & integrity (C3) | **Implemented**, function-based. `validation.py::validate_knowledge_graph()` |
| Manifest/statistics/fingerprints/finalization (C4.1–C4.3) | **Implemented.** `build.py`, `fingerprints.py`, `finalize.py` |
| Six ABC validation contracts (`NodeValidator`, `EdgeValidator`, `GraphValidator`, `IntegrityValidator`, `DeterminismValidator`, `ReadinessValidator` in `validation.py`) | **Not implemented — reserved.** Every method raises `NotImplementedError`; no subclass exists anywhere in the codebase. The module's own docstring states these were "always speculative architecture for a future C5 implementation", and a regression test (`tests/test_c3_graph_validation.py::test_abc_contracts_are_still_unimplemented`) asserts they remain so. Phase C3's real validation (above) is a parallel, function-based implementation deliberately kept separate from these six classes, to avoid the "duplicated implementation" pattern the project's own conventions warn against. |

## Node model (`node.py`, `nodes.py`)

`GraphNodeBase` (dataclass) is the base every concrete node type
inherits: `node_id`, `node_urn`, `node_type`, `source_object_id`,
`source_registry`, `graph_id`, `graph_urn`, `display_name`,
`node_schema_version`, plus an open `metadata: Dict[str, Any]` bag for
anything not already carried by the artifact itself (never a second
source of truth for something the artifact already carries).

`FUTURE_NODE_TYPES` (`node.py`) reserves the closed set of thirteen node
types matching Compiler IR's own registry names: `topic`, `concept`,
`definition`, `glossary`, `equation`, `figure`, `diagram`, `table`,
`activity`, `example`, `box`, `warning`, `note`. `nodes.py` defines one
concrete class per type; `build_nodes.py`'s `build_node()` constructs
exactly one node per canonical Compiler-IR object, one class per
registry, inserted into a `GraphRegistryManager`'s `nodes` registry.

## Edge model (`edge.py`)

`GraphEdgeBase` (dataclass): `edge_id`, `edge_urn`, `edge_type`,
`source_node_id`, `target_node_id`, `graph_id`, `graph_urn`, `directed`
(default `True`), `dependency_edge_schema_version`, `metadata`.

`FUTURE_EDGE_TYPES` reserves twelve edge types: the nine already
produced by Compiler IR's own relationship resolution (`contains`,
`has_definition`, `explains`, `described_by`, `appears_in`,
`belongs_to`, `uses_concept`, `illustrates`, `teaches` — see
`compiler/relationships.py::RELATIONSHIP_TYPES`) plus three additional
types (`prerequisite`, `depends_on`, `related_to`) reserved but **not
yet produced by any edge-construction code** — `build_edges.py` only
ever emits the nine relationship types Compiler IR already resolved; it
never invents a new relationship of its own. Edge construction is pure
re-projection: one graph edge per already-resolved Compiler-IR
relationship, no new relationship logic.

## Identity scheme (`identity.py`)

Deterministic throughout — no random UUIDs, no timestamps in any
identity:

- `graph_id(namespace)` / `graph_urn(namespace)` — one graph identity
  per chapter namespace.
- `node_id(node_type, source_object_id)` / `node_urn(graph_namespace,
  node_type, source_object_id)` — derived from the node type and the
  Compiler-IR object's own already-deterministic id, so a given
  Compiler-IR object always projects to the same graph node id across
  recompilations of unchanged content.
- `edge_id(edge_type, source_node_id, target_node_id)` / `edge_urn(...)`
  — derived from the edge type and its two endpoint node ids.
- `disambiguated_suffix(*parts)` — shared collision-avoidance helper.
- `FingerprintStrategy` — the canonicalization/hashing approach reused
  by `fingerprints.py`, itself built on the shared
  `canonicalization.py` primitives (the same ones `compiler/
  fingerprints.py` and `validation/determinism.py` use — one algorithm,
  not three independent copies).

## Registries (`registries.py`)

`GraphRegistryManager` is a thin subclass of
`compiler.registry_manager.RegistryManager` (reused directly, not
reimplemented), holding two registries: `nodes` and `edges`.

## Artifacts (`schema.py`)

- `KnowledgeGraph` + `KnowledgeGraphMetadata` — the graph container
  itself (id, urn, namespace, node/edge counts).
- `KnowledgeGraphManifest` / `KnowledgeGraphStatistics` — Phase C4.1,
  mirroring `compiler/build.py`'s own manifest/statistics shape one
  layer up.
- `KnowledgeGraphValidationReport` — Phase C3's verdict + per-check
  detail.
- `KnowledgeGraphReadinessReport` / `KnowledgeGraphBuildSummary` — Phase
  C4.2/C4.3: fingerprint-backed readiness checklist and the final
  closed-set status (`STATUS_READY` / `STATUS_READY_WITH_WARNINGS` /
  `STATUS_FAILED`, the same string values `compiler/finalize.py`
  defines — reused verbatim, not redeclared).
- `KnowledgeGraphState` — the dataclass shape `state.py`'s module-level
  slots are typed against.

## Pipeline position

`pipeline.process_chapter()` calls, immediately after Compiler IR
finalizes (see `COMPILER_PIPELINE.md` §3, step 4):

```
build_knowledge_graph_nodes(manager)
-> build_knowledge_graph_edges(manager, graph_registry)
-> validate_knowledge_graph(graph)
-> generate_knowledge_graph_manifest(graph, ...) / generate_knowledge_graph_statistics(...)
-> generate_graph_fingerprints(...)
-> finalize_knowledge_graph(...)
-> kg_state.set_current_knowledge_graph(graph)
```

Immediately after, Stage D's D1 (`validation/system_integrity.py`)
cross-checks this Knowledge Graph against the same chapter's Compiler
IR for consistency (dangling references, node/edge count agreement) —
the only place outside `knowledge_graph/` itself that reads into this
package's output.

## Explicitly out of scope (per this package's own docstrings)

- No cross-chapter or cross-book graph merging.
- No traversal/query API beyond what `change_detection/traversal.py`
  and `incremental_compilation/traversal.py` implement for the
  *separate* Build Dependency Graph (`dependency_graph/`) — not this
  package. A Knowledge Graph traversal helper is explicitly absent; see
  `tests/test_c3_graph_validation.py::test_no_traversal_helpers_are_implemented`.
- No mutation of Compiler IR — read-only consumer only.
