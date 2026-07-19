# M5.2D — Semantic Interpretation & Enrichment Engine

## Overview

M5.2D adds the **Semantic Interpretation & Enrichment Engine** — a purely additive
layer that sits above M5.2C's Structural Understanding Engine and interprets *what
educational structures mean*, rather than merely identifying *what structures exist*.

M5.2C answers: "What are the structural components of this educational object?"
M5.2D answers: "What do those components *mean* educationally?"

No LLM involvement. All interpretation is deterministic, evidence-based, and
versioned.

---

## Relationship with Prior Milestones

| Milestone | M5.2D interaction |
|-----------|------------------|
| **M5.1** `educational_object_framework` | Reuses `ValidationResult`, `ValidationDiagnostic`, `DiagnosticSeverity`, `SUCCESS` — never duplicates them |
| **M5.2A** `educational_taxonomy` | Reads `EducationalObjectType` via `CompatibilityInterpreter`; never modifies `TaxonomyRegistry` |
| **M5.2B** `subject_profile_framework` | Reads `SubjectContribution` hint fields via `HintDiagnosticsEngine`; never writes back |
| **M5.2C** `structural_understanding_engine` | Wraps `StructuralAnalysisResult`, `CompatibilityValidator`, `HintResolver`, `StructuralPattern` — modifies none |

---

## Engine Architecture

```
SemanticEnrichmentEngine            ← top-level coordinator
│
├── SemanticInterpretationEngine    ← structural → semantic layer
│   └── SemanticResolver            ← role mapping table (ROLE_MAPPING)
│
├── ConfidenceEvaluator             ← Deliverable #1: evidence-based scoring
│
├── CompatibilityInterpreter        ← Deliverable #2: wraps M5.2C CompatibilityValidator
│
├── HintDiagnosticsEngine           ← Deliverable #3: wraps M5.2C HintResolver
│
├── PatternVersionRegistry          ← Deliverable #4: semantic pattern version layer
│
└── SemanticAnchorBuilder           ← Deliverable #5: deterministic UUID5 anchors
```

### Input / Output

```
StructuralAnalysisResult (M5.2C)
        ↓
SemanticEnrichmentEngine.enrich()
        ↓
SemanticEnrichmentResult
  ├── SemanticObject           (interpreted roles)
  ├── ConfidenceBreakdown      (structural + semantic + enrichment scores)
  ├── CompatibilityResult      (rich compatibility report)
  ├── SemanticAnchor           (stable identifier for M5.2E)
  └── structural_snapshot      (frozen dict copy of M5.2C result)
```

---

## Confidence Model (Deliverable #1)

Confidence is computed deterministically from structural signals — no LLM, no
randomness.

### Dimensions

| Dimension | What it measures |
|-----------|-----------------|
| `structural` | Quality of M5.2C's structural analysis (pattern resolved, outcome complete, no missing roles) |
| `semantic` | Quality of M5.2D's role interpretation (interpretations produced, full coverage) |
| `enrichment` | Overall enrichment quality (blend of structural + semantic + anchor presence) |

### Bands

| Level | Minimum score |
|-------|--------------|
| `HIGH` | ≥ 0.80 |
| `MEDIUM` | ≥ 0.50 |
| `LOW` | ≥ 0.20 |
| `NONE` | < 0.20 |

### Evidence model

Each `ConfidenceScore` carries a tuple of `ConfidenceEvidence` items. Each item
has a `label`, `weight`, `passed` flag, and `detail` string — fully serializable
and auditable without any LLM.

---

## Compatibility Reporting (Deliverable #2)

`CompatibilityInterpreter` wraps M5.2C's `CompatibilityValidator` and produces a
`CompatibilityResult` with:

- `compatible` — boolean pass/fail
- `severity` — `OK` / `WARNING` / `ERROR`
- `reason` — human-readable explanation
- `affected_components` — diagnostic messages from M5.2C
- `suggested_resolution` — actionable fix
- `object_type_key` / `object_type_version` — what was checked

`CompatibilityValidator` is never modified.

---

## Hint Diagnostics (Deliverable #3)

`HintDiagnosticsEngine` wraps M5.2C's `HintResolver` and categorises every
hint key as:

| Category | Meaning |
|----------|---------|
| `resolved_keys` | Known hint keys that were consumed |
| `ignored_keys` | Keys present in input but unknown (landed in `extra`) |
| `unknown_keys` | Keys that don't belong to any hint namespace |
| `defaulted_keys` | Known keys not present in input (took their default) |
| `warnings` | `HintWarning` entries for each ignored/unknown key |

`HintResolver` is never modified.

---

## Pattern Versioning (Deliverable #4)

`PatternVersionRegistry` provides a semantic interpretation layer *above*
M5.2C's `StructuralPatternRegistry`. It associates `(pattern_key, semantic_version)`
pairs with `PatternVersion` entries containing:

- `PatternMetadata` — description, typical object types, deprecation status
- `PatternCompatibility` — engine version range where this entry is valid
- `PatternSelection` — result of selecting the best compatible version

`StructuralPattern` is never modified.

### Selection strategy

1. Prefer the newest compatible, non-deprecated `PatternVersion`.
2. If no compatible version exists, fall back to the newest (setting `fallback_used=True`).

---

## Semantic Anchors (Deliverable #5)

`SemanticAnchorBuilder` produces a `SemanticAnchor` for each enriched object:

```python
SemanticAnchor(
    anchor_id="<UUID5>",           # deterministic: UUID5(NAMESPACE, f"{object_key}:{role}")
    semantic_role=SemanticRole.DEFINES_CONCEPT,
    object_reference="obj_001",
    confidence=ConfidenceScore(...),
    pattern_key="definition",
)
```

**anchor_id is deterministic**: same `object_key` + `semantic_role` always produces
the same UUID5, regardless of which engine instance or process generates it.

`SemanticAnchors` are the primary inputs M5.2E (Relationship Discovery) will
consume. M5.2D does not implement relationship discovery.

---

## Validation

M5.2D reuses M5.1's `ValidationResult` / `ValidationDiagnostic` / `DiagnosticSeverity`
contracts. Three validation functions are provided:

| Function | Checks |
|----------|--------|
| `validate_semantic_enrichment_result` | object_key non-empty, COMPLETE outcome has semantic_object, scores in range, key consistency |
| `validate_anchor_uniqueness` | No duplicate `anchor_id` values across a result set |
| `validate_confidence_consistency` | Confidence level bands are consistent with score values |

---

## Preparation for M5.2E

M5.2D prepares for M5.2E (Relationship Discovery) in three ways:

1. **SemanticAnchors** — stable, unique, deterministic identifiers for each
   educational object. M5.2E will use these as nodes in relationship graphs.

2. **SemanticRole vocabulary** — a subject-independent ontology of educational
   roles (e.g. `DEFINES_CONCEPT`, `STATES_PREREQUISITE`, `ENABLES_TRANSFER`).
   M5.2E's relationship logic can inspect these roles to identify edges.

3. **SemanticEnrichmentResult** — a fully serializable, frozen result that M5.2E
   can consume without re-running M5.2C or M5.2D.

M5.2D does NOT implement relationship discovery, knowledge graph generation, or
graph construction. Those belong to M5.2E and later milestones.

---

## Module Layout

```
modules/semantic_interpretation_engine/
├── __init__.py                    # Full public API
├── enums.py                       # SemanticRole, PedagogicalRole, LearningIntent,
│                                  # InstructionalContext, ConfidenceLevel,
│                                  # EnrichmentOutcome, CompatibilitySeverity
├── models.py                      # ConfidenceEvidence, ConfidenceScore,
│                                  # ConfidenceBreakdown, SemanticInterpretation,
│                                  # SemanticObject, CompatibilityResult,
│                                  # SemanticAnchor, SemanticEnrichmentResult
├── config.py                      # SemanticInterpretationEngineConfig, default_config
├── exceptions.py                  # SemanticInterpretationError hierarchy
├── confidence.py                  # ConfidenceEvaluator, default_confidence_evaluator
├── semantic_resolver.py           # SemanticResolver, ROLE_MAPPING
├── anchor_builder.py              # SemanticAnchorBuilder, ANCHOR_NAMESPACE
├── hint_diagnostics.py            # HintDiagnosticsEngine (Deliverable #3)
├── pattern_versioning.py          # PatternVersionRegistry (Deliverable #4)
├── compatibility_interpreter.py   # CompatibilityInterpreter (Deliverable #2)
├── engine.py                      # SemanticInterpretationEngine,
│                                  # SemanticEnrichmentEngine, enrich()
├── validation.py                  # Validation contracts
└── README.md                      # This file
```

---

## Out of Scope

- Relationship Discovery (M5.2E)
- Knowledge Graph generation
- LLM integration
- Copyright normalization
- Master JSON generation
- Graph construction
