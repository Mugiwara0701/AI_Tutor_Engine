# Knowledge Graph Architecture — Phase C0

**Status: Phase C0 (Knowledge Graph Architecture Foundation) is
complete, including the Phase C0.1 audit-findings refinement pass
(Topic Registry + GraphNodeBase field expansion — see §3 and §5). No
graph has been built. No node or edge has been created.**

This document describes the architecture the `knowledge_graph/` package
establishes for the AI Tutor project's future Phase C (Knowledge Graph
construction), and how it relates to the frozen, production-ready
Phase A (Schema Foundation) and Phase B (Compiler Backend).

---

## 1. Purpose

Phase B's compiler produces a deterministic **Compiler Intermediate
Representation (Compiler IR)**: a populated, enriched, normalized,
reference-resolved, relationship-resolved `RegistryManager` (thirteen
educational-object registries — the original twelve plus `topics`,
added in the Phase C0.1 audit-findings refinement, see
`compiler/registries.py`'s own "TOPIC REGISTRY" docstring section —
plus a `relationships` registry), plus a validated, fingerprinted,
finalized set of Phase B artifacts (see
`docs/phase_b_completion_report.md`).

The Knowledge Graph's purpose is to **re-express that Compiler IR as a
graph** — nodes (one per meaningful canonical object, or per derived
educational grouping) connected by typed, directed-or-symmetric edges —
so a future tutoring/reasoning layer can traverse "what does this
concept depend on", "what figures illustrate this equation", "what is
the prerequisite chain for this topic", and similar graph-shaped
questions that a flat set of registries does not answer directly.

Phase C0 builds **none of that graph**. It builds the architecture every
later Phase C milestone (C1–C9) will build the graph _with_.

## 2. Architecture

```
compiler/                          knowledge_graph/
─────────                          ────────────────
CanonicalRegistry[T]        ──►     (reused directly, not reimplemented)
RegistryManager              ──►    GraphRegistryManager (thin subclass)
CanonicalObjectBase (schema) ──►    GraphNodeBase (schema.py's own peer, node.py)
compiler/relationships.py    ──►    GraphEdgeBase (edge.py) — reads Compiler IR
  RelationshipRegistry              relationships as ONE input, does not replace it
compiler/build.py            ──►    knowledge_graph/schema.py:
  CompilerManifest                    KnowledgeGraphManifest
  CompilerStatistics                  KnowledgeGraphStatistics
compiler/validation.py       ──►    knowledge_graph/schema.py:
  ValidationReport                    KnowledgeGraphValidationReport
  (+ knowledge_graph/validation.py's NodeValidator/EdgeValidator/
     GraphValidator/IntegrityValidator/DeterminismValidator contracts)
compiler/fingerprints.py     ──►    knowledge_graph/schema.py:
  CompilerReadinessReport             KnowledgeGraphReadinessReport
  (+ knowledge_graph/validation.py's ReadinessValidator contract)
  (+ knowledge_graph/identity.py's FingerprintStrategy — strategy only,
     no fingerprint computed)
compiler/finalize.py         ──►    knowledge_graph/schema.py:
  CompilerBuildSummary                KnowledgeGraphBuildSummary
compiler/state.py            ──►    knowledge_graph/state.py
  (module-level "current chapter"     (module-level "current graph"
   slot idiom)                        slot idiom — identical shape)
```

Every arrow above is a **read-only, one-directional dependency**:
`knowledge_graph/` imports from `compiler/` (specifically
`compiler.registry.CanonicalRegistry` and
`compiler.registry_manager.RegistryManager`); no file under `compiler/`
imports anything from `knowledge_graph/`. This is enforced by the
package boundary itself, not just by convention — `knowledge_graph/`
has no import-time dependency on `pipeline.py`, `modules/`, or
`prompt_manager/` either, only on `compiler/` (for registry reuse) and
Python's standard library.

**The Knowledge Graph must consume Compiler IR. It must never change
Compiler IR.** Nothing in `knowledge_graph/` inserts into, updates, or
removes from any `compiler.CanonicalRegistry`; nothing in
`knowledge_graph/` writes into `compiler/state.py`'s slots. A future
C1+ phase reads a chapter's Compiler IR (via
`compiler.state.get_current_registry_manager()` and the rest of that
module's getters) and builds an entirely separate, new set of graph
artifacts from it.

## 3. Node Model

`knowledge_graph/node.py`'s `GraphNodeBase` is the base class every
future concrete node type (`Topic`, `Concept`, `Definition`, `Glossary`,
`Equation`, `Figure`, `Diagram`, `Table`, `Activity`, `Example`, `Box`,
`Warning`, `Note` — see `FUTURE_NODE_TYPES`) will subclass. It carries:

- **Identity**: `node_id` / `node_urn`, built by
  `knowledge_graph.identity.node_id()`/`node_urn()`.
- **Type**: `node_type` (a plain string, additive without touching the
  base class — mirrors `CanonicalObjectBase.object_type`).
- **Provenance back into Compiler IR**: `compiler_object_id` /
  `compiler_object_urn` / `compiler_object_type` / `compiler_registry` —
  a node _wraps_ a canonical object, it does not copy or duplicate its
  fields (see `node.py`'s own docstring, "WHY A NODE WRAPS, RATHER THAN
  IS, A CANONICAL OBJECT"). If a future phase needs a wrapped object's
  own fields beyond the small, denormalized `display_name`/`provenance`
  below, it reads them from Compiler IR via this pointer, never from a
  cached snapshot that could drift.
- **Display/debug convenience**: `display_name` (the wrapped object's
  own name/title/term), `provenance` (a copy of the wrapped object's
  own `provenance` dict), and `compiler_version` (the wrapped object's
  own `creation_metadata.compiler_version`) — small, deliberately
  denormalized fields every graph consumer needs without a second
  Compiler IR lookup per node. Never authoritative; `compiler_registry`/
  `compiler_object_id` remain the source of truth (see `node.py`'s own
  "C0.1 FIELD EXPANSION" docstring section, added when an independent
  Phase C0 architecture audit found these fields, plus
  `compiler_object_urn`, missing from the original implementation).
- **Graph membership**: `graph_id` / `graph_urn`.
- **Extensibility**: an open `metadata: Dict[str, Any]` bag, mirroring
  `CanonicalObjectBase`'s own `extra="allow"` escape hatch.

No concrete node subclass exists yet. No node is ever instantiated
anywhere in this codebase as of Phase C0.

## 4. Edge Model

`knowledge_graph/edge.py`'s `GraphEdgeBase` is the base class every
future concrete edge type (`contains`, `has_definition`, `explains`,
`described_by`, `appears_in`, `belongs_to`, `uses_concept`,
`illustrates`, `teaches`, `Prerequisite`, `DependsOn`, `RelatedTo`, and
others — see `FUTURE_EDGE_TYPES`) will subclass. It carries:

- **Identity**: `edge_id` / `edge_urn`, built by
  `knowledge_graph.identity.edge_id()`/`edge_urn()` from the edge's own
  type plus both endpoint **node** ids.
- **Endpoints**: `source_node_id` / `target_node_id` — both
  `GraphNodeBase.node_id` values. An edge always connects two graph
  nodes, never two raw Compiler IR canonical objects directly (that is
  what `compiler.relationships.RelationshipRegistry` already does, one
  layer down — a future C2 edge-construction phase reads that registry
  as _one input_ toward deciding which graph edges to build, it does
  not replace it).
- **Directionality**: `directed: bool` — whether this edge type is
  meaningfully directional (e.g. `Prerequisite`) or symmetric (e.g.
  `RelatedTo`).
- **Graph membership** and **extensibility metadata**, mirroring
  `GraphNodeBase`'s own fields of the same names/purpose.

No concrete edge subclass exists yet. No edge is ever instantiated
anywhere in this codebase as of Phase C0.

## 5. Registry Design

`knowledge_graph/registries.py` reuses `compiler.registry.CanonicalRegistry`
and `compiler.registry_manager.RegistryManager` **directly** — no
id/urn/name indexing, duplicate detection, or serialization logic is
reimplemented. `GraphRegistryManager` is a thin, unmodified subclass of
`RegistryManager` (exists only so callers have a distinctly-named type
to hint against). `create_graph_registry_manager()` creates three
**empty** registries — `nodes`, `edges`, `metadata` — the Knowledge
Graph analogue of `compiler.registries.create_registry_manager()` at
Phase B0/B1's own boundary. Nothing is populated by Phase C0; every
registry `create_graph_registry_manager()` returns has `size() == 0`.

(This is the Knowledge Graph's own `nodes`/`edges`/`metadata` registry
set, distinct from Compiler IR's own thirteen educational-object
registries described in §1 — `compiler.registries.TopicRegistry`, added
in the C0.1 refinement pass, is a Compiler IR registry pipeline.py
populates, not a `knowledge_graph/` one; see
`compiler/registries.py`'s own "TOPIC REGISTRY" docstring section.)

`knowledge_graph/state.py` mirrors `compiler/state.py`'s own
module-level "current compilation state" slot idiom exactly, one slot
per artifact declared in `knowledge_graph/schema.py`'s
`KnowledgeGraphState` (the graph itself, its manifest, statistics,
validation report, readiness report, build summary, and final status
string), plus `reset_knowledge_graph_state()`. No `set_current_*()`
function in that module is ever called anywhere in Phase C0 — every
slot stays `None`.

## 6. Identity Strategy

`knowledge_graph/identity.py` defines deterministic id/urn rules,
layered on the same slugification principle
`modules/pdf_parser.py::make_urn()` already established for Compiler
IR, extended with one new `kg` namespace segment so a graph urn can
never collide with a Compiler IR urn:

| Kind      | Shape                                                                 | Built by                               |
| --------- | --------------------------------------------------------------------- | -------------------------------------- |
| Graph ID  | `kg-<namespace-slug>`                                                 | `graph_id(namespace)`                  |
| Graph URN | `urn:ncert-kg:kg:<namespace-slug>`                                    | `graph_urn(namespace)`                 |
| Node ID   | `node:<node-type-slug>:<source-object-id>`                            | `node_id(node_type, source_object_id)` |
| Node URN  | `<graph_urn>:node:<node-type-slug>:<source-object-id>`                | `node_urn(...)`                        |
| Edge ID   | `edge:<edge-type-slug>:<source-node-id>:<target-node-id>`             | `edge_id(...)`                         |
| Edge URN  | `<graph_urn>:edge:<edge-type-slug>:<source-node-id>:<target-node-id>` | `edge_urn(...)`                        |

A node id is **derived from, but distinct from**, the canonical object
id it wraps — see `identity.py`'s own docstring for why a graph node
cannot simply reuse a canonical object's own id/urn forever (a future
milestone may need >1 node per canonical object, or a node with no 1:1
canonical-object counterpart).

**Fingerprint strategy** (`FingerprintStrategy` /
`KNOWLEDGE_GRAPH_FINGERPRINT_STRATEGY`) is declared — algorithm
(`sha256`), canonicalization rule (sorted-key JSON, mirroring
`compiler/fingerprints.py`'s own `_canonical_json()`), volatile fields
to strip before hashing, and fingerprint granularity — but **no
fingerprint is ever computed** anywhere in Phase C0. This is data
describing a future computation, not the computation itself.

## 7. Validation Contracts

`knowledge_graph/validation.py` declares six `abc.ABC` interfaces, each
mirroring one of `compiler/validation.py`'s own internal passes, one
level up the stack:

| Contract               | Mirrors (compiler/validation.py)                                           |
| ---------------------- | -------------------------------------------------------------------------- |
| `NodeValidator`        | `_validate_canonical_object_integrity()`                                   |
| `EdgeValidator`        | `_validate_relationship_integrity()`                                       |
| `GraphValidator`       | `validate_compiler_state()` (the composed entry point)                     |
| `IntegrityValidator`   | `_validate_reference_integrity()` + `_validate_compiler_state_integrity()` |
| `DeterminismValidator` | `_check_id_determinism()`                                                  |
| `ReadinessValidator`   | `compiler.fingerprints.generate_compiler_readiness_report()`               |

Every method on every contract raises `NotImplementedError` — these are
interfaces a future C5 (Validation) / C8 (Finalization) phase
implements, not working validators.

## 8. Pipeline (future — not implemented)

`knowledge_graph/pipeline_architecture.py` declares the fixed execution
order the future Phase C pipeline will follow, as inert
`PipelineStageSpec` data (no stage's own module exists yet):

```
compiler.RegistryManager (Compiler IR, frozen, from Phase B)
        │
        ▼
C1  Node Construction        (knowledge_graph.build_nodes)
        │
        ▼
C2  Edge Construction        (knowledge_graph.build_edges)
        │
        ▼
C3  Cross-Link Resolution    (knowledge_graph.resolve_cross_links)
        │
        ▼
C4  Educational Semantics    (knowledge_graph.educational_semantics)
        │
        ▼
C5  Validation                (knowledge_graph.graph_validation)
        │
        ▼
C6  Optimization              (knowledge_graph.optimize)
        │
        ▼
C7  Metadata                  (knowledge_graph.graph_metadata)
        │
        ▼
C8  Finalization               (knowledge_graph.finalize)
        │
        ▼
C9  Freeze                     (knowledge_graph.freeze)
        │
        ▼
knowledge_graph.state.set_current_*(...)
```

Phase C0 itself is not a pipeline stage — like Phase A relative to
Phase B's own pipeline, it is a prerequisite the pipeline stands on, not
a step the pipeline executes. `PIPELINE_STAGES` is not iterated or
executed anywhere in this codebase yet.

## 9. Compiler IR → Knowledge Graph flow (once C1+ exists)

1. `pipeline.py`'s `process_chapter()` finishes Phase B exactly as it
   does today — `compiler.state.get_current_*()` slots are populated.
2. A future Phase C entry point calls
   `knowledge_graph.state.reset_knowledge_graph_state()`, then reads
   Compiler IR via `compiler.state.get_current_registry_manager()` (and
   the rest of that module's getters) — **read-only**.
3. C1–C9 (§8 above) run in order, each producing one more
   `knowledge_graph/schema.py` artifact, culminating in a frozen
   `KnowledgeGraph`.
4. `knowledge_graph.state.set_current_knowledge_graph()` (and the other
   `set_current_*()` functions) promote those artifacts to "current
   graph compilation state" — mirroring exactly how
   `compiler.state.set_current_registry_manager()` etc. already work.
5. Compiler IR itself is never written to at any point in this flow.

## 10. Future milestones

- **C1** — Node Construction: populate the `nodes` registry from
  Compiler IR's thirteen object registries (including `topics`, see §1).
- **C2** — Edge Construction: populate the `edges` registry, informed
  by `compiler.relationships.RelationshipRegistry`.
- **C3** — Cross-Link Resolution.
- **C4** — Educational Semantics.
- **C5** — Validation: implement `NodeValidator`/`EdgeValidator`/
  `GraphValidator`/`IntegrityValidator`/`DeterminismValidator`.
- **C6** — Optimization.
- **C7** — Metadata: implement `KnowledgeGraphManifest`/
  `KnowledgeGraphStatistics` generation.
- **C8** — Finalization: implement `ReadinessValidator`, generate
  `KnowledgeGraphBuildSummary`.
- **C9** — Freeze.

None of the above is implemented, started, or scaffolded beyond the
architecture this document describes.

---

## Confirmation

- ✓ No graph nodes were created.
- ✓ No graph edges were created.
- ✓ No Knowledge Graph was built.
- ✓ Compiler IR remains unchanged.
- ✓ Educational JSON remains unchanged.
- ✓ **Phase C0 is complete.**
