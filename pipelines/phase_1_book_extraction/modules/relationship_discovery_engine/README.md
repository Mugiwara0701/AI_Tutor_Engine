# M5.2E — Relationship Discovery & Semantic Graph Engine

## Overview

M5.2E is the **final milestone of the M5.2 Educational Semantic Intelligence Layer**.

It consumes the `SemanticEnrichmentResult` objects produced by M5.2D and:

1. **Discovers** educational relationships between semantic objects.
2. **Validates** every discovered relationship.
3. **Propagates** confidence from semantic anchors through to relationships.
4. **Constructs** a canonical `SemanticGraph`.
5. **Normalizes** the graph (deduplication, canonical refs).
6. **Validates** graph integrity (orphans, broken refs, cycles).
7. **Exports** a deterministic, immutable `GraphExportArtifact` for M5.3.

No LLM involvement. Everything is deterministic.

---

## Relationship with Prior Milestones

| Milestone | M5.2E interaction |
|-----------|------------------|
| **M5.1** `educational_object_framework` | Reuses `ValidationResult`, `ValidationDiagnostic`, `DiagnosticSeverity`, `SUCCESS` — never duplicates them |
| **M5.2A** `educational_taxonomy` | Reads `EducationalObjectType.key` via `SemanticObject.object_type_key`; never modifies `TaxonomyRegistry` |
| **M5.2B** `subject_profile_framework` | Relationship hints consumed indirectly via `SemanticEnrichmentResult.structural_snapshot`; never writes back |
| **M5.2C** `structural_understanding_engine` | Structural data consumed indirectly via M5.2D's snapshot; never modifies M5.2C |
| **M5.2D** `semantic_interpretation_engine` | Consumes `SemanticEnrichmentResult` and `SemanticAnchor`; uses `SemanticAnchor.anchor_id` as immutable graph node IDs — **never regenerated** |

---

## Engine Architecture

```
RelationshipDiscoveryEngine             ← top-level coordinator
│
├── RelationshipResolver                ← Deliverable #1: candidate pair generation
├── RelationshipClassifier              ← Deliverable #1: role-pair → relationship type
├── RelationshipBuilder                 ← Deliverable #1: assemble SemanticRelationship
│   └── ConfidencePropagator            ← Deliverable #3: anchor conf → relationship conf
│
├── RelationshipValidator               ← Deliverable #2: per-relationship validation
│
├── SemanticGraphBuilder                ← Deliverable #4: EnrichmentResults → graph nodes
│
├── GraphNormalizer                     ← Deliverable #5: dedup edges, canonical order
│
├── GraphIntegrityValidator             ← Deliverable #6: orphans, cycles, broken refs
│
└── GraphExporter                       ← Deliverable #7: final artifact for M5.3
```

### Pipeline (Input → Output)

```
List[SemanticEnrichmentResult] (M5.2D)
        ↓
RelationshipResolver     → candidate (source, target) pairs
        ↓
RelationshipClassifier   → ClassificationResult (rule + type + direction)
        ↓
ConfidencePropagator     → RelationshipConfidence
        ↓
RelationshipBuilder      → SemanticRelationship (immutable, UUID5 ID)
        ↓
RelationshipValidator    → validates each relationship
        ↓
SemanticGraphBuilder     → SemanticGraph (nodes + edges)
        ↓
GraphNormalizer          → normalized SemanticGraph (deduped)
        ↓
GraphIntegrityValidator  → integrity report merged into graph diagnostics
        ↓
GraphExporter            → GraphExportArtifact (dict or JSON, for M5.3)
```

---

## Relationship Discovery (Deliverable #1)

### Rule Table (`rules.py`)

Relationships are discovered via the static `RELATIONSHIP_RULES` table:

```python
RELATIONSHIP_RULES: Dict[Tuple[str, str], RelationshipRule] = {
    ("defines_concept", "states_prerequisite"): RelationshipRule(
        RelationshipType.REQUIRES, RelationshipDirection.FORWARD, 0.85, "rule_requires_prerequisite"
    ),
    ("exemplifies_concept", "defines_concept"): RelationshipRule(
        RelationshipType.ILLUSTRATES, RelationshipDirection.FORWARD, 0.85, "rule_illustrates_concept"
    ),
    # ... 30+ rules
}
```

Keys are `(source_SemanticRole.value, target_SemanticRole.value)` pairs.
Unknown pairs fall back to `RELATED_TO` with a reduced weight (0.30).

### Relationship Types

| Type | Educational meaning |
|------|---------------------|
| `DEFINES` | Definition → Concept |
| `REQUIRES` | Concept → Prerequisite |
| `ILLUSTRATES` | Example → Concept |
| `EXPLAINS` | Figure → Concept |
| `SUPPORTS` | Experiment → Scientific Principle |
| `IMPLEMENTS` | Procedure → Method |
| `EVALUATES` | Assessment → Learning Objective |
| `EXTENDS` | Transfer Task → Concept |
| `CONTRADICTS` | Misconception → Concept |
| `SEQUENCES` | Step A → Step B |
| `CONTEXTUALIZES` | Teaching Intent → Concept |
| `REFERENCES` | Cross-reference |
| `SUMMARIZES` | Teaching Function → Full Structure |
| `RELATED_TO` | Fallback for unknown pairs |

---

## Relationship Validation (Deliverable #2)

`RelationshipValidator` checks each `SemanticRelationship` for:

| Code | Check | Severity |
|------|-------|----------|
| RDE001/002 | Non-empty source/target anchor_ids | ERROR |
| RDE003 | Valid `RelationshipType` value | ERROR |
| RDE004 | Confidence ≥ `min_relationship_confidence` | WARNING |
| RDE005 | No self-loops (unless `allow_self_loops=True`) | ERROR |
| RDE006 | No duplicate `relationship_id` in list | WARNING |

---

## Confidence Propagation (Deliverable #3)

`ConfidencePropagator` produces `RelationshipConfidence` from:

- **Source anchor confidence** (from M5.2D's `SemanticAnchor.confidence.value`)
- **Target anchor confidence** (from M5.2D's `SemanticAnchor.confidence.value`)
- **Rule base_weight** (from `RELATIONSHIP_RULES`)

Formula:
```
raw_score = weighted_score(evidence_items)
anchor_mean = (source_confidence + target_confidence) / 2
final_score = raw_score × base_weight × (0.5 + 0.5 × anchor_mean)
```

Evidence items:
- `rule_match` (weight 0.40): exact rule found vs. fallback
- `source_anchor_confidence` (weight 0.30): ≥ 0.50 passes
- `target_anchor_confidence` (weight 0.30): ≥ 0.50 passes

---

## Semantic Graph Construction (Deliverable #4)

`SemanticGraphBuilder` converts:
- Each `SemanticEnrichmentResult` with a valid anchor → `SemanticNode`
- Each `SemanticRelationship` above the confidence threshold → `SemanticEdge`

**Critical invariant**: `SemanticNode.node_id = SemanticAnchor.anchor_id` (M5.2D).  
Node IDs are **never regenerated**.

`GraphMetadata.graph_id` is a UUID5 derived from the sorted set of node IDs — fully deterministic.

---

## Graph Normalization (Deliverable #5)

`GraphNormalizer` removes duplicate edges with the same `(source, target, relationship_type)`:

| Strategy | Behaviour |
|----------|-----------|
| `KEEP_HIGHEST_CONFIDENCE` (default) | Keep the edge with the highest confidence score |
| `KEEP_FIRST` | Keep the first edge seen |
| `MERGE_EVIDENCE` | Keep highest confidence (future: merge evidence) |

Updated `GraphStatistics.duplicate_edges_removed` reflects the count.

---

## Graph Validation (Deliverable #6)

`GraphIntegrityValidator` runs 7 checks:

| Code | Check | Severity |
|------|-------|----------|
| GIV001 | Duplicate node_ids | ERROR |
| GIV002 | Duplicate edge_ids | WARNING |
| GIV003/004 | Broken edge references (src/tgt not in node set) | ERROR (strict) / WARNING |
| GIV005 | Invalid relationship_type value | ERROR |
| GIV006 | Edge confidence out of [0.0, 1.0] | ERROR |
| GIV007 | Orphan nodes (no connecting edges) | WARNING |
| GIV008 | Cycles detected (when `detect_cycles=True`) | WARNING |

---

## Graph Export (Deliverable #7)

`GraphExporter.export()` produces a `GraphExportArtifact`:

```python
artifact = engine.export(graph, format=GraphExportFormat.JSON, indent=2)
# artifact.payload → JSON string
# artifact.graph   → the original SemanticGraph (unchanged)
# artifact.graph_id, artifact.node_count, artifact.edge_count
```

The graph `to_dict()` output is:
- **Immutable** (frozen dataclasses, no mutation)
- **Serializable** (pure Python dicts and strings)
- **Versioned** (`version` field on every model)
- **Deterministic** (same input → same output, always)

---

## Module Layout

```
modules/relationship_discovery_engine/
├── __init__.py                        # Full public API
├── enums.py                           # RelationshipType, RelationshipDirection,
│                                      # DiscoveryOutcome, GraphBuildOutcome,
│                                      # NormalizationStrategy, GraphExportFormat,
│                                      # NodeStatus, EdgeStatus
├── models.py                          # RelationshipEvidence, RelationshipConfidence,
│                                      # SemanticRelationship, RelationshipDiscoveryResult,
│                                      # SemanticNode, SemanticEdge, GraphMetadata,
│                                      # GraphStatistics, SemanticGraph
├── config.py                          # RelationshipDiscoveryEngineConfig, default_config
├── exceptions.py                      # Exception hierarchy
├── rules.py                           # RELATIONSHIP_RULES table, lookup_rule
├── confidence_propagator.py           # ConfidencePropagator (Deliverable #3)
├── relationship_resolver.py           # RelationshipResolver (Deliverable #1)
├── relationship_classifier.py         # RelationshipClassifier (Deliverable #1)
├── relationship_builder.py            # RelationshipBuilder (Deliverable #1)
├── relationship_validator.py          # RelationshipValidator (Deliverable #2)
├── graph_builder.py                   # SemanticGraphBuilder (Deliverable #4)
├── graph_normalizer.py                # GraphNormalizer (Deliverable #5)
├── graph_integrity_validator.py       # GraphIntegrityValidator (Deliverable #6)
├── graph_exporter.py                  # GraphExporter (Deliverable #7)
├── engine.py                          # RelationshipDiscoveryEngine, discover()
├── validation.py                      # validate_* functions (reuse M5.1)
└── README.md                          # This file
```

---

## How M5.2E Completes the Educational Semantic Intelligence Layer

The M5.2 layer spans five milestones:

| Milestone | Question answered |
|-----------|------------------|
| M5.2A | What educational object types exist? (taxonomy) |
| M5.2B | How do subjects contribute to those types? (profiles) |
| M5.2C | What is the internal structure of each object? (structural) |
| M5.2D | What do those structures mean educationally? (semantic) |
| **M5.2E** | **How do these objects relate to each other? (graph)** |

M5.2E's `SemanticGraph` is the **complete, canonical semantic representation** of an educational document — nodes are semantic objects, edges are educational relationships, and everything is fully typed, versioned, and validated.

---

## How M5.2E Prepares for M5.3

M5.3 (Knowledge Graph integration, Master JSON generation, Teacher Brain) will consume:

1. **`SemanticGraph`** — the canonical graph artifact, fully serializable to JSON.
2. **`SemanticNode.node_id`** (= M5.2D's `SemanticAnchor.anchor_id`) — stable, permanent identifiers for graph nodes.
3. **`SemanticEdge`** — typed, confidence-scored, directional relationships.
4. **`GraphMetadata`** — provenance and version information.
5. **`GraphStatistics`** — aggregate information for quality reporting.

M5.3 does **not** need to re-run any M5.2 engine. The exported graph is the complete output.

---

## Out of Scope

- Knowledge Graph reasoning
- LLM integration
- Master JSON generation
- Teacher Brain / Adaptive tutoring
- Graph database persistence
